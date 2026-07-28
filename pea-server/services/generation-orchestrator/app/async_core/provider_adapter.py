"""Provider 适配器: 把"规范请求"翻译成第三方真实调用, 并归一化其响应.

Agnes 当前是 poll 模式 (提交拿 task_id, 我们按 /v1/videos/{task_id} 轮询).
未来支持回调的厂商实现 WebhookCapableMixin 即可零改动接入.

本模块为**同步**实现 (与编排器整体线程栈一致, 不引入 asyncio 栈风险);
慢 I/O (图像同步出图 / 视频状态查询) 由 Dispatcher 的线程池与 Completer 的后台线程承载,
消费线程本身永不阻塞 -> 头阻塞消除.
"""
from __future__ import annotations

import logging
from typing import Any

from app.async_core.types import (
    AsyncHandle,
    CompletionMode,
    NormalizedStatus,
    PollStatus,
    ProviderCapabilities,
    SubmitOutcome,
)
from app.config import settings
from app.agnes_provider import (
    OpenAICompatibleProvider,
    GenerationResult,
    _extract_video_url,
    _parse_video_status,
)

logger = logging.getLogger(__name__)


class BaseProviderAdapter:
    """所有 provider 适配器的抽象基类."""

    def __init__(self, cfg: dict):
        self.base_url: str = cfg.get("base_url", "")
        self.api_key: str = cfg.get("api_key", "")
        self.model_name: str = cfg.get("model_name", "")
        self.provider_name: str = cfg.get("provider_name") or cfg.get("provider_id") or "provider"
        self.name = self.provider_name

    @property
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    def submit(self, req: dict) -> SubmitOutcome:
        """提交任务. 同步模式返回 result; 异步模式返回 AsyncHandle."""
        raise NotImplementedError

    def query_status(self, handle: AsyncHandle) -> PollStatus:
        """poll 模式: 查询任务状态 (webhook 模式不需要)."""
        raise NotImplementedError


class AgnesAdapter(BaseProviderAdapter):
    """Agnes: OpenAI 兼容, 视频异步提交 + 轮询, 不支持 webhook."""

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        # 真实执行器; 缺 model_name (仅状态查询场景) 时留空不影响 query_status
        self._real = OpenAICompatibleProvider({
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model_name": self.model_name,
            "provider_name": self.provider_name,
        })

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            completion_mode=CompletionMode.POLL,
            accepts_callback=False,
            # 状态查询: 提交时按文档推荐渲染 /agnesapi?video_id= (video_id 优先),
            # 旧版 /v1/videos/{task_id} 仅作兜底 (详见 agnes_provider._submit_video_only)。
            status_query_template="/agnesapi?video_id={video_id}",
        )

    async def submit(self, req: dict) -> "SubmitOutcome":
        kind = req.get("type", "image")
        if kind == "image":
            res = await self._real._generate_image_async(req)
            return SubmitOutcome(sync=True, result=res)
        if kind == "text":
            res = await self._real._generate_text_async(req)
            return SubmitOutcome(sync=True, result=res)
        # video: 仅提交(快操作), 不轮询; 在收尾线程池跑同步实现, 不卡事件循环
        from app.async_core.engine import run_finalize

        sub = await run_finalize(self._real._submit_video_only, req)
        if sub.get("direct_url"):
            return SubmitOutcome(sync=True, result=GenerationResult(
                url=sub["direct_url"], provider=self.provider_name,
                raw={"sync": True}, usage={},
            ))
        h = AsyncHandle(
            job_id=req.get("job_id", ""),
            user_id=int(req.get("user_id", 0) or 0),
            provider=self.provider_name,
            completion_mode=CompletionMode.POLL,
            provider_task_id=str(sub["task_id"]) if sub.get("task_id") else "",
            provider_video_id=str(sub["video_id"]) if sub.get("video_id") else None,
            status_query=sub["status_query"],
        )
        return SubmitOutcome(sync=False, handle=h)

    def query_status(self, handle: AsyncHandle) -> PollStatus:
        raw = self._real._query_video_status_raw(handle.status_query)
        norm_str, url, err = _parse_video_status(raw)
        return PollStatus(
            normalized=NormalizedStatus(norm_str),
            raw_status=str(raw.get("status") or raw.get("state") or ""),
            progress=raw.get("progress"),
            result_url=url,
            error=err,
        )


class WebhookCapableMixin:
    """支持回调的 provider 混入: 提交时附签名 callback_url (未来厂商用)."""

    def build_callback_url(self, job_id: str, provider_task_id: str) -> str:
        from app.async_core.webhook import sign_webhook

        base = settings.webhook_base_url.rstrip("/")
        sig = sign_webhook(job_id, provider_task_id)
        return f"{base}/api/v1/generation/webhook?job_id={job_id}&sig={sig}"

    def decorate_submit_payload(self, payload: dict, job_id: str) -> dict:
        if self.capabilities.accepts_callback and settings.webhook_base_url:
            payload["callback_url"] = self.build_callback_url(job_id, job_id)
        return payload


class MockAdapter(BaseProviderAdapter):
    """本地占位 provider: 同步返回一个确定性结果 (联调用的极速路径)."""

    def __init__(self) -> None:
        from app.llm_router import _mock

        self._mock = _mock
        self.provider_name = "mock"
        self.name = "mock"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(completion_mode=CompletionMode.SYNC, accepts_callback=False)

    async def submit(self, req: dict) -> "SubmitOutcome":
        res = self._mock.generate(req)
        return SubmitOutcome(sync=True, result=res)

    def query_status(self, handle: AsyncHandle) -> PollStatus:
        raise NotImplementedError("mock provider is always synchronous")


def build_adapter(cfg: dict) -> BaseProviderAdapter:
    """工厂: 按 provider 类型选择适配器. 现仅 Agnes(poll) / Mock; 未来扩展."""
    if cfg.get("provider_type") == "mock":
        return MockAdapter()
    # 默认按 Agnes 兼容处理 (OpenAI 风格异步视频)
    return AgnesAdapter(cfg)
