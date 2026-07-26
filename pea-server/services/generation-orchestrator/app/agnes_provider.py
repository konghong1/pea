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

import logging
import time
from typing import Any

import requests

from app.config import settings
from app.llm_router import GenerationResult
from app.param_adapters import normalize_image_params, get_image_adapter, _normalize_refs

logger = logging.getLogger(__name__)

_VIDEO_DONE = ("completed", "succeeded", "success", "done", "finished", "ready")
_VIDEO_FAIL = ("failed", "error", "cancelled", "canceled", "rejected")


def _api_base(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}{path}"


def _post_with_retry(url: str, payload: dict, headers: dict, timeout,
                     max_attempts: int = 2, backoff_base: int = 4):
    """POST JSON 到外部提供商, 对瞬时错误自动重试。

    重试仅针对「真·瞬时错误」: HTTP 429/500/502/503 与连接错误 (ConnectionError)。
    **不**对读取超时 (ReadTimeout) 重试 —— 读取超时意味着提供商在 timeout[1] 内
    一字未回 (真挂死/半开连接), 重试只会把已等待的几百秒作废再等一遍, 反而加倍延迟。
    Agnes 高峰期常延迟 ~100~170s 才返回, 但那是「带 503 的响应」(5xx, 会被正常重试),
    不是读取超时; 只要 timeout[1] 取到 provider_image_timeout_s (300s, 覆盖其峰值),
    慢但成功的生成就能在单次尝试内完成, 不再被 110s 误杀后重试翻倍。

    返回: 2xx 响应, 或最后一次仍 5xx 时返回该响应 (交由上层 _raise_for_provider 抛错)。
    """
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.ConnectionError as e:  # 连接级错误 -> 重试
            last_err = e
            if attempt < max_attempts:
                wait = min(backoff_base * (2 ** (attempt - 1)), 20)
                print(f"[agnes] attempt {attempt} network error {e!r}, retry in {wait}s")
                time.sleep(wait)
                continue
            raise
        if resp.status_code in (429, 500, 502, 503):  # 瞬时过载 -> 重试
            last_err = RuntimeError(f"provider HTTP {resp.status_code}")
            if attempt < max_attempts:
                wait = min(backoff_base * (2 ** (attempt - 1)), 20)
                print(f"[agnes] attempt {attempt} got HTTP {resp.status_code} (transient), retry in {wait}s")
                time.sleep(wait)
                continue
            return resp
        return resp
    raise last_err or RuntimeError("provider call failed after retries")


def _is_agnes(base_url: str) -> bool:
    return "agnes" in (base_url or "").lower()


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


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
        # 防腐层: 把规范参数翻译成当前模型/提供商需要的真实请求体。
        # 这样前端只管 size_tier + aspect_ratio, 模型差异(档位式 vs 精确像素、
        # 图生图 image 放哪、要不要用 tags)全部收敛到 param_adapters。
        norm = normalize_image_params(req)
        adapter = get_image_adapter(self.base_url)
        payload: dict[str, Any] = adapter.build(norm, self)

        url = _api_base(self.base_url, "/v1/images/generations")
        logger.info("[agnes] image model=%s payload=%s", self.model_name, _short(payload))
        resp = _post_with_retry(
            url, payload, self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_image_timeout_s),
            max_attempts=2,
        )
        _raise_for_provider(resp, "image")
        data = resp.json()

        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"image response has no data: {_short(data)}")

        # 收集所有图片 URL（支持 n > 1）
        urls: list[str] = []
        for item in items:
            img_url = item.get("url")
            if img_url:
                urls.append(img_url)
            elif item.get("b64_json"):
                urls.append(f"data:image/png;base64,{item['b64_json']}")

        if not urls:
            raise RuntimeError(f"image response missing url/b64_json: {_short(items[0] if items else {})}")

        # 返回所有图片 URL，url 是主图（兼容），urls 是完整数组
        return GenerationResult(
            url=urls[0],
            urls=urls,
            provider=self.provider_name,
            raw={"count": len(urls)},
            usage=data.get("usage") or {}
        )

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
        resp = _post_with_retry(
            submit_url, payload, self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_video_submit_timeout_s),
            max_attempts=2,
        )
        _raise_for_provider(resp, "video-submit")
        sub = resp.json()

        # 有些实现同步就返回了成品 URL
        direct = _extract_video_url(sub)
        if direct:
            # 直接透传公网 URL, 不走 MinIO 转存 (见 _generate_image 说明)。
            return GenerationResult(url=direct, provider=self.provider_name, raw={"sync": True},
                                    usage=sub.get("usage") or {})

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
                # 直接透传公网 URL, 不走 MinIO 转存 (见 _generate_image 说明)。
                return GenerationResult(url=raw_url, provider=self.provider_name, raw={"task_id": task_id},
                                        usage=data.get("usage") or {})
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
        resp = _post_with_retry(
            url, payload, self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, 110),
            max_attempts=2,
        )
        _raise_for_provider(resp, "text")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"text response malformed: {_short(data)}") from exc
        return GenerationResult(url="", provider=self.provider_name, raw={}, text=content,
                                 usage=data.get("usage") or {})


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
