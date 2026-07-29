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

import asyncio
import logging
import time
from typing import Any

import httpx
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


def _swap_host(url: str, new_base: str) -> str:
    """把 URL 的 host 换成 new_base, 保留 path/query。用于网关兜底时复用同一路径。"""
    from urllib.parse import urlsplit, urlunsplit
    p = urlsplit(url)
    b = urlsplit(new_base)
    return urlunsplit((b.scheme, b.netloc, p.path, p.query, p.fragment))


def _post_with_retry(url: str, payload: dict, headers: dict, timeout,
                     max_attempts: int = 3, backoff_base: int = 4,
                     fallback_url: str | None = None):
    """POST JSON 到外部提供商, 对瞬时错误自动重试。

    重试仅针对「真·瞬时错误」: HTTP 429/500/502/503 与连接错误 (ConnectionError)。
    **不**对读取超时 (ReadTimeout) 重试 —— 读取超时意味着提供商在 timeout[1] 内
    一字未回 (真挂死/半开连接), 重试只会把已等待的几百秒作废再等一遍, 反而加倍延迟。
    Agnes 高峰期常延迟 ~100~170s 才返回, 但那是「带 503 的响应」(5xx, 会被正常重试),
    不是读取超时; 只要 timeout[1] 取到 provider_image_timeout_s (300s, 覆盖其峰值),
    慢但成功的生成就能在单次尝试内完成, 不再被 110s 误杀后重试翻倍。

    返回: 2xx 响应, 或最后一次仍 5xx 时返回该响应 (交由上层 _raise_for_provider 抛错)。
    """
    # 5xx 但属于「瞬时 / 源站异常」的都重试：
    #  - 429/500/502/503/504: 标准 HTTP 语义 (限流 / 服务端错 / 网关超时)
    #  - 520/521/522/523/524/525/526/527/530: Cloudflare 5xx (Web server unknown error /
    #    connection timeout / origin unreachable 等), 这些基本是源站暂时抽风, 重试常可恢复.
    transient_5xx = frozenset({
        429, 500, 502, 503, 504,
        520, 521, 522, 523, 524, 525, 526, 527, 530,
    })
    last_err: Exception | None = None
    target = url
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(target, json=payload, headers=headers, timeout=timeout)
        except requests.ConnectionError as e:  # 连接级错误 -> 重试/兜底切换
            last_err = e
            if fallback_url and target != fallback_url:
                target = fallback_url
                print(f"[agnes] attempt {attempt} primary unreachable, fallback to gateway {fallback_url}")
                if attempt < max_attempts:
                    time.sleep(min(backoff_base * (2 ** (attempt - 1)), 20))
                    continue
            elif attempt < max_attempts:
                wait = min(backoff_base * (2 ** (attempt - 1)), 20)
                time.sleep(wait)
                continue
            raise
        if resp.status_code in transient_5xx:  # 瞬时过载 / Cloudflare 源站异常 -> 重试
            last_err = RuntimeError(f"provider HTTP {resp.status_code}")
            if attempt < max_attempts:
                wait = min(backoff_base * (2 ** (attempt - 1)), 20)
                print(f"[agnes] attempt {attempt} got HTTP {resp.status_code} (transient), retry in {wait}s")
                time.sleep(wait)
                continue
            return resp
        return resp
    raise last_err or RuntimeError("provider call failed after retries")


async def _apost_with_retry(client, url, payload, headers, timeout,
                            max_attempts: int = 3, backoff_base: int = 4,
                            fallback_url: str | None = None):
    """异步版 POST (httpx): 仅对连接级错误与瞬时 5xx 重试, 不对读取超时重试。

    语义与 _post_with_retry 完全一致, 区别仅在用 ``await client.post(...)`` ——
    等待外部响应期间让出事件循环, 不占 OS 线程 (见 async_core/engine.py)。
    """
    transient_5xx = frozenset({
        429, 500, 502, 503, 504,
        520, 521, 522, 523, 524, 525, 526, 527, 530,
    })
    last_err: Exception | None = None
    target = url
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await client.post(target, json=payload, headers=headers, timeout=timeout)
        except httpx.ConnectError as e:  # 真·连不上 -> 兜底切换
            last_err = e
            if fallback_url and target != fallback_url:
                target = fallback_url
                print(f"[agnes] attempt {attempt} primary unreachable, fallback to gateway {fallback_url}")
                if attempt < max_attempts:
                    await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), 20))
                    continue
            elif attempt < max_attempts:
                await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), 20))
                continue
            raise RuntimeError(
                f"provider connection failed ({type(e).__name__}): {url}"
            ) from e
        except httpx.TimeoutException as e:  # 超时(含读取超时) -> 同址重试, 不切换
            last_err = e
            if attempt < max_attempts:
                await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), 20))
                continue
            raise RuntimeError(
                f"provider timeout failed ({type(e).__name__}): {url}"
            ) from e
        if resp.status_code in transient_5xx:  # 瞬时过载 / Cloudflare 源站异常 -> 重试
            last_err = RuntimeError(f"provider HTTP {resp.status_code}")
            if attempt < max_attempts:
                await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), 20))
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


def _parse_video_status(data: dict):
    """把第三方视频状态响应归一化为 (normalized, result_url, error).

    normalized ∈ {'done','processing','failed'} (与 async_core NormalizedStatus 对齐).
    供同步 _generate_video 与异步适配器 query_status 共用, 避免重复解析逻辑.
    """
    raw = (data.get("status") or data.get("state") or "").lower().strip()
    url = _extract_video_url(data)
    if raw in _VIDEO_DONE:
        return ("done", url, None)
    if raw in _VIDEO_FAIL:
        return ("failed", None, data.get("error") or data.get("message") or raw)
    return ("processing", None, None)


class OpenAICompatibleProvider:
    """按 DB 中 ai_providers 行构造的真实适配器 (Agnes / OpenAI 兼容)。"""

    def __init__(self, cfg: dict):
        self.base_url: str = cfg.get("base_url", "")
        self.api_key: str = cfg.get("api_key", "")
        self.model_name: str = cfg.get("model_name", "")
        self.provider_name: str = cfg.get("provider_name") or cfg.get("provider_id") or "provider"
        self.name = self.provider_name
        # 网关兜底地址: 官方 base_url 不可达时回退。默认空(不兜底);
        # 仅当显式配置 PEA_AI_GATEWAY 时启用。与 base_url 相同则视为无兜底。
        self.gateway_base: str = (settings.ai_gateway or "").strip()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _fb(self, path: str) -> tuple[str, str | None]:
        """返回 (官方URL, 网关兜底URL|None)。base_url 与网关相同则无兜底。"""
        primary = _api_base(self.base_url, path)
        if self.gateway_base and self.gateway_base.rstrip("/") != (self.base_url or "").rstrip("/"):
            return primary, _api_base(self.gateway_base, path)
        return primary, None

    def _fb_status(self, status_query: str) -> str | None:
        """视频状态查询的网关兜底 URL: 复用官方 status_query 的 path/query, 仅换 host。"""
        if self.gateway_base and self.gateway_base.rstrip("/") != (self.base_url or "").rstrip("/"):
            try:
                return _swap_host(status_query, self.gateway_base)
            except Exception:
                return None
        return None

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

        url, fb = self._fb("/v1/images/generations")
        logger.info("[agnes] image model=%s payload=%s", self.model_name, _short(payload))
        resp = _post_with_retry(
            url, payload, self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_image_timeout_s),
            max_attempts=settings.provider_image_retry_attempts,
            fallback_url=fb,
        )
        _raise_for_provider(resp, "image")
        return self._build_image_result(resp.json(), self.provider_name)

    async def _generate_image_async(self, req: dict) -> "GenerationResult":
        """异步版图像生成: 用 httpx 异步客户端, 等待外部响应期间让出事件循环, 不占 OS 线程。"""
        from app.async_core.engine import get_client

        norm = normalize_image_params(req)
        adapter = get_image_adapter(self.base_url)
        payload: dict[str, Any] = adapter.build(norm, self)

        url, fb = self._fb("/v1/images/generations")
        logger.info("[agnes] image model=%s payload=%s", self.model_name, _short(payload))
        client = get_client()
        timeout = httpx.Timeout(
            settings.provider_image_timeout_s,
            connect=settings.provider_http_connect_timeout_s,
        )
        resp = await _apost_with_retry(
            client, url, payload, self._headers(), timeout,
            max_attempts=settings.provider_image_retry_attempts,
            fallback_url=fb,
        )
        _raise_for_provider(resp, "image")
        return self._build_image_result(resp.json(), self.provider_name)

    @staticmethod
    def _build_image_result(data: dict, provider: str) -> "GenerationResult":
        """从响应 JSON 收齐图片 URL (支持 n>1), 归一为 GenerationResult。"""
        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"image response has no data: {_short(data)}")
        urls: list[str] = []
        for item in items:
            img_url = item.get("url")
            if img_url:
                urls.append(img_url)
            elif item.get("b64_json"):
                urls.append(f"data:image/png;base64,{item['b64_json']}")
        if not urls:
            raise RuntimeError(f"image response missing url/b64_json: {_short(items[0] if items else {})}")
        return GenerationResult(
            url=urls[0],
            urls=urls,
            provider=provider,
            raw={"count": len(urls)},
            usage=data.get("usage") or {},
        )

    # ── 视频 (异步提交 + 轮询) ───────────────────────────────────────
    def _build_video_payload(self, req: dict):
        params: dict = req.get("params") or {}
        # frame_rate: 1–60。必须是 8 的倍数才能保证 num_frames 满足 8n+1 (见下方归一化)。
        frame_rate = _clamp_int(params.get("frame_rate", 24), 1, 60, 24)
        # duration: 前端传的是字符串 "5s"，先剥单位再转整秒；否则 int("5s") 抛错被 _clamp_int 兜底成默认 5s。
        raw_dur = params.get("duration", 5)
        if isinstance(raw_dur, str):
            raw_dur = raw_dur.rstrip("sS")
        duration = _clamp_int(raw_dur, 1, 60, 5)
        # num_frames 必须 ≤ 441 且遵循 8n+1 (Agnes 硬性约束, 否则 400)。
        # 先按秒数算, 再强制归一化到最近的合法值, 避免 frame_rate 非 8 倍数 / duration 过大导致越界。
        num_frames = duration * frame_rate + 1
        num_frames = min(num_frames, 441)
        rem = (num_frames - 1) % 8
        if rem:
            num_frames -= rem          # 向下取整到最近的 8n+1
        if num_frames < 9:
            num_frames = 9             # 至少 8*1+1
        width = _clamp_int(params.get("width", 1152), 64, 4096, 1152)
        height = _clamp_int(params.get("height", 768), 64, 4096, 768)
        seed = params.get("seed")
        # 兼容前端可能显式传 gen_mode (ti2vid/keyframes); 缺省时按参考图数量推断。
        # 注意: 旧实现完全忽略 gen_mode, 导致 UI 选择的生成模式无效。
        gen_mode = (params.get("gen_mode") or params.get("mode") or "").lower()
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
            if len(refs) == 1 and gen_mode != "keyframes":
                # 图生视频: 单图走顶层 image (字符串) + mode=ti2vid (官方文档形态)。
                # 旧实现错把单图塞进 extra_body.image=[url] 数组且无 mode -> 既非 img2vid 也非 keyframes。
                payload["image"] = refs[0]
                payload["mode"] = "ti2vid"
            else:
                # 关键帧动画: extra_body.image 数组 + extra_body.mode=keyframes (官方文档形态)。
                extra = payload.setdefault("extra_body", {})
                extra["image"] = refs
                extra["mode"] = "keyframes"
        elif gen_mode == "ti2vid":
            payload["mode"] = "ti2vid"
        return payload, num_frames, len(refs)

    def _submit_video_only(self, req: dict) -> dict:
        """仅提交视频任务, 不轮询. 返回 {'task_id','status_query'} 或 {'direct_url'}.

        供异步完成层适配器调用 —— 提交是快操作(<提交超时), 真正的长轮询交给 Completer.
        """
        payload, num_frames, nrefs = self._build_video_payload(req)
        submit_url, submit_fb = self._fb("/v1/videos")
        logger.info("[agnes] video submit model=%s frames=%d refs=%d", self.model_name, num_frames, nrefs)
        resp = _post_with_retry(
            submit_url, payload, self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_video_submit_timeout_s),
            max_attempts=2,
            fallback_url=submit_fb,
        )
        _raise_for_provider(resp, "video-submit")
        sub = resp.json()
        direct = _extract_video_url(sub)
        if direct:
            return {"direct_url": direct}
        # 文档: 提交同时返回 task_id 与 video_id; 新接入推荐用 video_id + /agnesapi?video_id= 查询。
        # 旧版 /v1/videos/{task_id} 仅作兜底 (video_id 缺失时)。实测旧版接口对不存在任务返回
        # HTTP 400 + 顶层 {code,message} 结构, 与文档标准 {status,metadata.url} 形态不一致,
        # 故优先走 video_id 推荐接口, 避免解析不到 completed 导致一直轮询。
        task_id = sub.get("id") or sub.get("task_id") or (sub.get("data") or {}).get("id")
        video_id = sub.get("video_id") or (sub.get("data") or {}).get("video_id")
        if not task_id and not video_id:
            raise RuntimeError(f"video submit returned no task/video id: {_short(sub)}")
        if video_id:
            status_query = _api_base(self.base_url, f"/agnesapi?video_id={video_id}")
        else:
            status_query = _api_base(self.base_url, f"/v1/videos/{task_id}")
        return {
            "task_id": str(task_id) if task_id else None,
            "video_id": str(video_id) if video_id else None,
            "status_query": status_query,
        }

    def _query_video_status_raw(self, status_query: str, fallback_url: str | None = None) -> dict:
        """查询视频任务状态, 返回原始 JSON dict (异常上抛). 供异步适配器轮询.

        status_query 为提交时已渲染好的完整状态查询 URL:
        推荐 /agnesapi?video_id=<VIDEO_ID>, 或兜底 /v1/videos/<TASK_ID>。
        官方地址不可达(连接错误)时回退到 fallback_url(网关)。
        """
        target = status_query
        last_err: Exception | None = None
        for attempt in range(1, 3):
            try:
                resp = requests.get(
                    target, headers=self._headers(),
                    timeout=(settings.provider_http_connect_timeout_s, 60),
                )
                _raise_for_provider(resp, "video-status")
                return resp.json()
            except requests.ConnectionError as e:
                last_err = e
                if fallback_url and target != fallback_url:
                    target = fallback_url
                    print(f"[agnes] video-status primary unreachable, fallback to gateway {fallback_url}")
                    continue
                if attempt < 2:
                    time.sleep(2)
                    continue
                raise
        raise last_err or RuntimeError("video status query failed")

    def _generate_video(self, req: dict) -> GenerationResult:
        """同步全量路径 (提交 + 轮询). 保留给 route()/测试; 新消费链路走 _submit_video_only + Completer."""
        sub = self._submit_video_only(req)
        if sub.get("direct_url"):
            # 直接透传公网 URL, 不走 MinIO 转存 (见 _generate_image 说明)。
            return GenerationResult(url=sub["direct_url"], provider=self.provider_name,
                                    raw={"sync": True}, usage={})
        status_query = sub["status_query"]
        sq_fb = self._fb_status(status_query)
        deadline = time.time() + settings.video_poll_max_s
        last_status = "queued"
        while time.time() < deadline:
            time.sleep(settings.video_poll_interval_s)
            data = self._query_video_status_raw(status_query, fallback_url=sq_fb)
            last_status = (data.get("status") or data.get("state") or "").lower().strip() or last_status
            norm, url, err = _parse_video_status(data)
            if norm == "done":
                if not url:
                    raise RuntimeError(f"video completed but no url: {_short(data)}")
                return GenerationResult(url=url, provider=self.provider_name,
                                        raw={"task_id": task_id}, usage=data.get("usage") or {})
            if norm == "failed":
                raise RuntimeError(f"video generation failed: {err}")
            # 其余状态 (queued/processing/running...) 继续轮询
        raise TimeoutError(f"video poll timeout after {settings.video_poll_max_s}s (last={last_status})")

    # ── 文本 ────────────────────────────────────────────────────────
    def _generate_text(self, req: dict) -> GenerationResult:
        url, fb = self._fb("/v1/chat/completions")
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": req["prompt"]}],
        }
        resp = _post_with_retry(
            url, payload, self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, 110),
            max_attempts=2,
            fallback_url=fb,
        )
        _raise_for_provider(resp, "text")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"text response malformed: {_short(data)}") from exc
        return GenerationResult(url="", provider=self.provider_name, raw={}, text=content,
                                 usage=data.get("usage") or {})

    async def _generate_text_async(self, req: dict) -> "GenerationResult":
        """异步版文本生成: 用 httpx 异步客户端, 不占 OS 线程。"""
        from app.async_core.engine import get_client

        url, fb = self._fb("/v1/chat/completions")
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": req["prompt"]}],
        }
        client = get_client()
        timeout = httpx.Timeout(
            110,
            connect=settings.provider_http_connect_timeout_s,
        )
        resp = await _apost_with_retry(
            client, url, payload, self._headers(), timeout,
            max_attempts=2,
            fallback_url=fb,
        )
        _raise_for_provider(resp, "text")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"text response malformed: {_short(data)}") from exc
        return GenerationResult(url="", provider=self.provider_name, raw={}, text=content,
                                 usage=data.get("usage") or {})


def _raise_for_provider(resp, what: str) -> None:
    """把非 2xx 转成带截断响应体的异常, 便于定位提供商侧报错。

    同时兼容 requests.Response 与 httpx.Response (reason / reason_phrase 字段名不同)。

    响应体只截前 160 字符 (避免 500 字符 HTML 把错误信息撑爆),
    且检测到 HTML 头 (`<!DOCTYPE` / `<html`) 时只保留状态码 + 标题, 不让 HTML
    详情流入用户界面 (UI 那边会用更友好的归类展示).
    """
    if resp.status_code // 100 == 2:
        return
    body = ""
    try:
        body = resp.text[:160]
    except Exception:  # noqa: BLE001
        pass
    reason = getattr(resp, "reason_phrase", None) or getattr(resp, "reason", "") or "upstream error"
    # HTML 错误页 (Cloudflare 5xx/网关) — 只保留状态码, 不让 <!DOCTYPE ...> 露在错误里
    if body.lstrip().startswith(("<!DOCTYPE", "<!doctype", "<html", "<HTML")):
        raise RuntimeError(f"{what} HTTP {resp.status_code}: {reason}")
    raise RuntimeError(f"{what} HTTP {resp.status_code}: {body}")


def _short(obj: Any, limit: int = 300) -> str:
    s = str(obj)
    return s if len(s) <= limit else s[:limit] + "..."
