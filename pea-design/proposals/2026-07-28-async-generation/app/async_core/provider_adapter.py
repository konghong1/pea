"""Provider 适配器: 把"规范请求"翻译成第三方真实调用, 并归一化其响应.

Agnes 当前是 poll 模式 (提交拿 task_id, 我们按 /v1/videos/{task_id} 轮询)。
未来支持回调的厂商实现 WebhookCapableMixin 即可零改动接入。
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.async_core.types import (
    AsyncHandle,
    CompletionMode,
    NormalizedStatus,
    PollStatus,
    ProviderCapabilities,
    SubmitResult,
)
from app.config import settings

logger = logging.getLogger(__name__)


def _api_base(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}{path}"


def _extract_video_url(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    meta = data.get("metadata") or {}
    for cand in (
        data.get("url"),
        data.get("video_url"),
        data.get("output"),
        data.get("remixed_from_video_id"),
        meta.get("url"),
    ):
        if isinstance(cand, str) and cand.startswith("http"):
            return cand
    return None


class BaseProviderAdapter:
    """所有 provider 适配器的抽象基类."""

    def __init__(self, cfg: dict):
        self.base_url: str = cfg["base_url"]
        self.api_key: str = cfg["api_key"]
        self.model_name: str = cfg["model_name"]
        self.provider_name: str = cfg.get("provider_name") or cfg.get("provider_id") or "provider"
        self.name = self.provider_name

    @property
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def submit(self, req: dict, client: httpx.AsyncClient) -> SubmitResult:
        """提交任务. 同步模式返回 result; 异步模式返回 AsyncHandle."""
        raise NotImplementedError

    async def query_status(self, handle: AsyncHandle, client: httpx.AsyncClient) -> PollStatus:
        """poll 模式: 查询任务状态 (webhook 模式不需要)."""
        raise NotImplementedError


class AgnesAdapter(BaseProviderAdapter):
    """Agnes: OpenAI 兼容, 视频异步提交 + 轮询, 不支持 webhook."""

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            completion_mode=CompletionMode.POLL,
            accepts_callback=False,
            # 旧版兼容查询地址 (现有代码已验证可用); 文档推荐 /agnesapi?video_id= 亦可
            status_query_template="/v1/videos/{task_id}",
            status_parser=self._parse_status,
        )

    def _parse_status(self, data: dict) -> PollStatus:
        raw = (data.get("status") or data.get("state") or "").lower().strip()
        if raw in ("completed", "succeeded", "success", "done", "finished", "ready"):
            url = _extract_video_url(data)
            return PollStatus(NormalizedStatus.DONE, raw,
                              progress=data.get("progress"), result_url=url)
        if raw in ("failed", "error", "cancelled", "canceled", "rejected"):
            return PollStatus(NormalizedStatus.FAILED, raw,
                              progress=data.get("progress"),
                              error=data.get("error") or data.get("message") or raw)
        if raw in ("queued", "pending", "waiting"):
            return PollStatus(NormalizedStatus.PENDING, raw, progress=data.get("progress"))
        # in_progress / running / 其它
        return PollStatus(NormalizedStatus.PROCESSING, raw, progress=data.get("progress"))

    async def submit(self, req: dict, client: httpx.AsyncClient) -> SubmitResult:
        params: dict = req.get("params") or {}
        frame_rate = _clamp(params.get("frame_rate", 24), 1, 60, 24)
        duration = _clamp(params.get("duration", 5), 1, 60, 5)
        num_frames = duration * frame_rate + 1
        width = _clamp(params.get("width", 1152), 64, 4096, 1152)
        height = _clamp(params.get("height", 768), 64, 4096, 768)
        refs = _normalize_refs(params.get("reference_images"))

        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": req["prompt"],
            "height": height, "width": width,
            "num_frames": num_frames, "frame_rate": frame_rate,
        }
        if params.get("seed") is not None:
            payload["seed"] = params["seed"]
        if refs:
            payload.setdefault("extra_body", {})["image"] = refs
            if len(refs) > 1:
                payload["extra_body"]["mode"] = "keyframes"

        url = _api_base(self.base_url, "/v1/videos")
        logger.info("[agnes] video submit model=%s frames=%d refs=%d",
                    self.model_name, num_frames, len(refs))
        resp = await client.post(url, json=payload, headers=self._headers(),
                                 timeout=(settings.provider_http_connect_timeout_s,
                                          settings.provider_video_submit_timeout_s))
        _raise_for_status(resp, "video-submit")
        sub = resp.json()

        # 极少情况同步返回成品
        direct = _extract_video_url(sub)
        if direct:
            return SubmitResult(mode=CompletionMode.SYNC, result={"url": direct, "urls": [direct]})

        task_id = (sub.get("id") or sub.get("task_id")
                   or (sub.get("data") or {}).get("id"))
        video_id = sub.get("video_id")
        if not task_id:
            raise RuntimeError(f"video submit returned no task id: {str(sub)[:300]}")
        status_query = _api_base(self.base_url, f"/v1/videos/{task_id}")
        handle = AsyncHandle(
            job_id=req.get("job_id", ""),
            provider=self.provider_name,
            completion_mode=CompletionMode.POLL,
            provider_task_id=str(task_id),
            provider_video_id=str(video_id) if video_id else None,
            status_query=status_query,
        )
        return SubmitResult(mode=CompletionMode.POLL, handle=handle)

    async def query_status(self, handle: AsyncHandle, client: httpx.AsyncClient) -> PollStatus:
        resp = await client.get(handle.status_query, headers=self._headers(),
                                timeout=(settings.provider_http_connect_timeout_s, 60))
        _raise_for_status(resp, "video-status")
        return self._parse_status(resp.json())


class WebhookCapableMixin:
    """支持回调的 provider 混入: 提交时附签名 callback_url."""

    def build_callback_url(self, job_id: str, provider_task_id: str) -> str:
        from app.async_core.webhook import sign_webhook
        base = settings.webhook_base_url.rstrip("/")
        sig = sign_webhook(job_id, provider_task_id)
        return f"{base}/api/v1/generation/webhook?job_id={job_id}&sig={sig}"

    def decorate_submit_payload(self, payload: dict, job_id: str) -> dict:
        """若 provider 接受 callback_url 字段, 追加之. 子类在 submit 里调用."""
        if self.capabilities.accepts_callback and settings.webhook_base_url:
            # provider_task_id 此刻尚不知, 用 job_id 占位; 真实 task_id 由 webhook 体带回来
            payload["callback_url"] = self.build_callback_url(job_id, job_id)
        return payload


def _clamp(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _normalize_refs(refs: Any) -> list[str]:
    if not refs:
        return []
    if isinstance(refs, str):
        return [refs]
    return [r for r in refs if isinstance(r, str)]


def _raise_for_status(resp: httpx.Response, what: str) -> None:
    if resp.status_code // 100 == 2:
        return
    body = ""
    try:
        body = resp.text[:500]
    except Exception:  # noqa: BLE001
        pass
    raise RuntimeError(f"{what} HTTP {resp.status_code}: {body}")


def build_adapter(cfg: dict) -> BaseProviderAdapter:
    """工厂: 按 provider 类型选择适配器. 现仅 Agnes(poll); 未来扩展."""
    base = (cfg.get("base_url") or "").lower()
    if "agnes" in base:
        return AgnesAdapter(cfg)
    # 默认按 Agnes 兼容处理 (OpenAI 风格异步视频)
    return AgnesAdapter(cfg)
