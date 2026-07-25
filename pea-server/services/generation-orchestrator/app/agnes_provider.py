"""OpenAI 兼容 (Agnes) 真实生成适配器.

复刻自参考实现 D:\\workspace\\ai-agent\\app\\media.py 的调用约定:
- 图像: POST {base}/v1/images/generations, Agnes 用 extra_body.response_format=url;
         图生图参考图放 extra_body.image (Agnes) / 顶层 image (其它兼容实现)。
- 视频: POST {base}/v1/videos 异步提交 -> 轮询 GET {base}/v1/videos/{task_id} 直至完成。
- 文本: POST {base}/v1/chat/completions。

设计要点 (资深复核):
- 密钥/base_url 由编排器从 DB (ai_providers) 读取, 不经队列/日志传播。
- 所有网络调用都设 (连接, 读取) 双超时; 读取超时按图像/视频区分。
- 出错一律抛出 -> worker 置 FAILED -> 触发退款; 绝不静默返回占位, 避免"扣了费给假图"。
- 外部返回的临时媒体 URL 一律转存到自有对象存储, 得到稳定可读地址。

并发注意: 视频轮询会阻塞当前 worker 线程 (最长 video_poll_max_s)。当前单消费者模型下
属可接受的折中; 生产应改为独立轮询回路 / 回调, 避免长任务占满队列 (见 worker 软护栏)。
"""
from __future__ import annotations

import base64
import binascii
import logging
import time
from typing import Any

import requests

from app import storage
from app.config import settings
from app.llm_router import GenerationResult

logger = logging.getLogger(__name__)

# 尺寸档位 -> 具体像素 (前端只选 1K/2K/4K, 提供商需要真实尺寸)。
_SIZE_MAP = {"1k": "1024x1024", "2k": "2048x2048", "4k": "4096x4096"}

_VIDEO_DONE = ("completed", "succeeded", "success", "done", "finished", "ready")
_VIDEO_FAIL = ("failed", "error", "cancelled", "canceled", "rejected")


def _api_base(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}{path}"


def _is_agnes(base_url: str) -> bool:
    return "agnes" in (base_url or "").lower()


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _map_size(size: Any) -> str | None:
    """'1K'/'2K'/'4K' -> 像素; 已是 'WxH' 直接透传; 空 -> None (用模型默认尺寸)。"""
    if not size:
        return None
    s = str(size).strip()
    low = s.lower()
    if low in _SIZE_MAP:
        return _SIZE_MAP[low]
    if "x" in low and any(c.isdigit() for c in low):
        return s
    return None


def _normalize_refs(refs: Any) -> list[str]:
    """仅保留提供商可达的参考图: http(s) 外链或 data: 内联; 内部代理/相对路径丢弃。上限 8。"""
    if not refs:
        return []
    if isinstance(refs, str):
        refs = [refs]
    out: list[str] = []
    for r in list(refs)[:8]:
        if isinstance(r, str) and (r.startswith("http") or r.startswith("data:")):
            out.append(r)
    return out


def _extract_video_url(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    meta = data.get("metadata") or {}
    for cand in (
        data.get("video_url"),
        data.get("output"),
        data.get("url"),
        data.get("remixed_from_video_id"),
        meta.get("url"),
    ):
        if isinstance(cand, str) and cand.startswith("http"):
            return cand
    return None


class OpenAICompatibleProvider:
    """按 DB 中 ai_providers 行构造的真实适配器 (Agnes / OpenAI 兼容)。"""

    def __init__(self, cfg: dict):
        self.base_url: str = cfg["base_url"]
        self.api_key: str = cfg["api_key"]
        self.model_name: str = cfg["model_name"]
        self.provider_name: str = cfg.get("provider_name") or cfg.get("provider_id") or "provider"
        self.name = self.provider_name

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ── 分发 ────────────────────────────────────────────────────────
    def generate(self, req: dict) -> GenerationResult:
        if not self.base_url or not self.api_key:
            raise RuntimeError(f"provider {self.provider_name} misconfigured (base_url/api_key)")
        kind = req.get("type", "image")
        if kind == "image":
            return self._generate_image(req)
        if kind == "video":
            return self._generate_video(req)
        if kind == "text":
            return self._generate_text(req)
        raise ValueError(f"unsupported generation type: {kind}")

    # ── 图像 ────────────────────────────────────────────────────────
    def _generate_image(self, req: dict) -> GenerationResult:
        params: dict = req.get("params") or {}
        user_id = req.get("user_id")
        n = _clamp_int(params.get("n", 1), 1, 8, 1)
        size = _map_size(params.get("size"))
        seed = params.get("seed")
        refs = _normalize_refs(params.get("reference_images"))

        payload: dict[str, Any] = {"model": self.model_name, "prompt": req["prompt"], "n": n}
        if size:
            payload["size"] = size
        if seed is not None:
            payload["seed"] = seed

        extra_body: dict[str, Any] = {}
        if _is_agnes(self.base_url):
            extra_body["response_format"] = "url"
        if refs:
            extra_body["image"] = refs
            if "agnes-image-2.0" in self.model_name.lower():
                extra_body["tags"] = ["img2img"]
            if not _is_agnes(self.base_url):
                payload["image"] = refs[0] if len(refs) == 1 else refs
        if extra_body:
            payload["extra_body"] = extra_body

        url = _api_base(self.base_url, "/v1/images/generations")
        logger.info("[agnes] image model=%s n=%d size=%s refs=%d", self.model_name, n, size, len(refs))
        resp = requests.post(
            url, json=payload, headers=self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_image_timeout_s),
        )
        _raise_for_provider(resp, "image")
        data = resp.json()

        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"image response has no data: {_short(data)}")
        first = items[0] or {}
        img_url = first.get("url")
        if img_url:
            stored = storage.store_from_url(img_url, "image", user_id=user_id)
        elif first.get("b64_json"):
            try:
                raw = base64.b64decode(first["b64_json"])
            except (binascii.Error, ValueError) as exc:
                raise RuntimeError(f"invalid b64_json image: {exc}") from exc
            stored = storage.store_bytes(raw, "image", user_id=user_id, content_type="image/png")
        else:
            raise RuntimeError(f"image response missing url/b64_json: {_short(first)}")
        return GenerationResult(url=stored, provider=self.provider_name, raw={"count": len(items)})

    # ── 视频 (异步提交 + 轮询) ───────────────────────────────────────
    def _generate_video(self, req: dict) -> GenerationResult:
        params: dict = req.get("params") or {}
        user_id = req.get("user_id")
        frame_rate = _clamp_int(params.get("frame_rate", 24), 1, 60, 24)
        duration = _clamp_int(params.get("duration", 5), 1, 60, 5)
        num_frames = duration * frame_rate + 1
        width = _clamp_int(params.get("width", 1152), 64, 4096, 1152)
        height = _clamp_int(params.get("height", 768), 64, 4096, 768)
        seed = params.get("seed")
        refs = _normalize_refs(params.get("reference_images"))

        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": req["prompt"],
            "height": height,
            "width": width,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }
        if seed is not None:
            payload["seed"] = seed
        if refs:
            if _is_agnes(self.base_url):
                extra = payload.setdefault("extra_body", {})
                extra["image"] = refs
                if len(refs) > 1:
                    extra["mode"] = "keyframes"
            else:
                payload["image"] = refs[0] if len(refs) == 1 else refs

        submit_url = _api_base(self.base_url, "/v1/videos")
        logger.info("[agnes] video submit model=%s frames=%d refs=%d", self.model_name, num_frames, len(refs))
        resp = requests.post(
            submit_url, json=payload, headers=self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_video_submit_timeout_s),
        )
        _raise_for_provider(resp, "video-submit")
        sub = resp.json()

        # 有些实现同步就返回了成品 URL
        direct = _extract_video_url(sub)
        if direct:
            stored = storage.store_from_url(direct, "video", user_id=user_id, timeout=settings.provider_image_timeout_s)
            return GenerationResult(url=stored, provider=self.provider_name, raw={"sync": True})

        task_id = sub.get("id") or sub.get("task_id") or (sub.get("data") or {}).get("id")
        if not task_id:
            raise RuntimeError(f"video submit returned no task id: {_short(sub)}")

        return self._poll_video(str(task_id), user_id)

    def _poll_video(self, task_id: str, user_id: Any) -> GenerationResult:
        status_url = _api_base(self.base_url, f"/v1/videos/{task_id}")
        deadline = time.time() + settings.video_poll_max_s
        last_status = "queued"
        while time.time() < deadline:
            time.sleep(settings.video_poll_interval_s)
            resp = requests.get(
                status_url, headers=self._headers(),
                timeout=(settings.provider_http_connect_timeout_s, 60),
            )
            _raise_for_provider(resp, "video-status")
            data = resp.json()
            last_status = (data.get("status") or data.get("state") or "").lower().strip() or last_status
            if last_status in _VIDEO_DONE:
                raw_url = _extract_video_url(data)
                if not raw_url:
                    raise RuntimeError(f"video completed but no url: {_short(data)}")
                stored = storage.store_from_url(
                    raw_url, "video", user_id=user_id, timeout=settings.provider_image_timeout_s
                )
                return GenerationResult(url=stored, provider=self.provider_name, raw={"task_id": task_id})
            if last_status in _VIDEO_FAIL:
                reason = data.get("error") or data.get("message") or last_status
                raise RuntimeError(f"video generation failed: {reason}")
            # 其余状态 (queued/processing/running...) 继续轮询
        raise TimeoutError(f"video poll timeout after {settings.video_poll_max_s}s (last={last_status})")

    # ── 文本 ────────────────────────────────────────────────────────
    def _generate_text(self, req: dict) -> GenerationResult:
        url = _api_base(self.base_url, "/v1/chat/completions")
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": req["prompt"]}],
        }
        resp = requests.post(
            url, json=payload, headers=self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_image_timeout_s),
        )
        _raise_for_provider(resp, "text")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"text response malformed: {_short(data)}") from exc
        return GenerationResult(url="", provider=self.provider_name, raw={}, text=content)


def _raise_for_provider(resp: requests.Response, what: str) -> None:
    """把非 2xx 转成带截断响应体的异常, 便于定位提供商侧报错。"""
    if resp.status_code // 100 == 2:
        return
    body = ""
    try:
        body = resp.text[:500]
    except Exception:  # noqa: BLE001
        pass
    raise RuntimeError(f"{what} HTTP {resp.status_code}: {body}")


def _short(obj: Any, limit: int = 300) -> str:
    s = str(obj)
    return s if len(s) <= limit else s[:limit] + "..."
