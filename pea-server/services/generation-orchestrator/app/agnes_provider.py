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
from app.async_core.types import GenerationResult
from app.param_adapters import (
    normalize_image_params,
    get_image_adapter,
    PublicUrlStrategy,
)
import base64
import re

logger = logging.getLogger(__name__)

_VIDEO_DONE = ("completed", "succeeded", "success", "done", "finished", "ready")
_VIDEO_FAIL = ("failed", "error", "cancelled", "canceled", "rejected")

# ── 速率限制(429)与瞬时 5xx 拆分 (RC-2 修复) ──
# 429 = 限流(上游配额窗口), 必须按真实窗口整段等待后最多重试 1 次; 不能当秒级 5xx 退避。
#   把限流当 4s 退避重试, 在 60s 窗口内必败且白烧额度(每个逻辑请求实际打 2 个 POST 全失败)。
# 真正的瞬时服务端错误(5xx / Cloudflare)才走指数退避。
_TRANSIENT_5XX = frozenset({
    500, 502, 503, 504,
    520, 521, 522, 523, 524, 525, 526, 527, 530,
})
_RATE_LIMIT_RE_MIN = re.compile(r"per\s+(\d+)\s+minute", re.I)
_RATE_LIMIT_RE_SEC = re.compile(r"per\s+(\d+)\s+second", re.I)


def _parse_rate_limit_wait_s(resp, default_s: int) -> int:
    """从 429 响应解析应等待的秒数: 优先 Retry-After 头, 否则报文里的 'per N minute(s)'/'per N second(s)'。"""
    try:
        ra = getattr(resp, "headers", {}).get("Retry-After")
        if ra:
            return max(1, int(float(ra)))
    except (TypeError, ValueError):
        pass
    body = ""
    try:
        body = (resp.text or "")[:200]
    except Exception:  # noqa: BLE001
        pass
    m = _RATE_LIMIT_RE_SEC.search(body)
    if m:
        return max(1, int(m.group(1)))
    m = _RATE_LIMIT_RE_MIN.search(body)
    if m:
        return max(1, int(m.group(1)) * 60)
    return default_s


def _api_base(base_url: str, path: str) -> str:
    """把相对路径拼到 base_url 之下 (版本前缀自适应, 关键修复: 接入 Volcengine 方舟)。

    - base 以 /api/v3 结尾 (Volcengine 方舟实际前缀): 去掉路径开头的 /v1 再拼回 /api/v3,
      因为火山方舟的 OpenAI 兼容接口是 /api/v3/chat/completions, 而非 /api/v3/v1/chat/completions。
    - base 以 /v1 结尾 (Agnes): 维持原行为, 剥 /v1 后拼 /v1/...。
    - 其它 (MiniMax 裸域名): 原样拼接 —— 路径里的 /v1、/v2 是 MiniMax 真实路由前缀,
      绝不能当"版本段"剥离 (否则 MiniMax-H3 的 /v2/video_generation 会被错误改写)。
    """
    base = (base_url or "").rstrip("/")
    if base.endswith("/api/v3"):
        root = base[: -len("/api/v3")]
        rel = path[len("/v1"):] if path.startswith("/v1") else path
        return f"{root}/api/v3{rel}"
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
                     backoff_cap: int = 20,
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
    last_err: Exception | None = None
    target = url
    for attempt in range(1, max_attempts + 1):
        try:
            # proxies=None: 与 httpx(trust_env=False) 一致 —— 强制不走 HTTPS_PROXY 环境变量,
            # 直接出网(服务器直连外部 AI 可达, 同机 ai-agent 已验证)。避免被注入的死代理劫持。
            resp = requests.post(
                target, json=payload, headers=headers, timeout=timeout,
                proxies={"http": None, "https": None},
            )
        except requests.ConnectionError as e:  # 连接级错误 -> 重试/兜底切换
            last_err = e
            if fallback_url and target != fallback_url:
                target = fallback_url
                print(f"[agnes] attempt {attempt} primary unreachable, fallback to gateway {fallback_url}")
                if attempt < max_attempts:
                    time.sleep(min(backoff_base * (2 ** (attempt - 1)), backoff_cap))
                    continue
            elif attempt < max_attempts:
                wait = min(backoff_base * (2 ** (attempt - 1)), 20)
                time.sleep(wait)
                continue
            raise
        # 429 = 限流(上游配额窗口): 按真实窗口整段等待, 最多重试 1 次, 绝不烧额度。
        if resp.status_code == 429:
            if attempt < 2:
                wait = _parse_rate_limit_wait_s(resp, settings.provider_rate_limit_default_window_s)
                wait = min(wait, settings.rate_limit_max_wait_s)
                print(f"[agnes] attempt {attempt} got 429 rate limit, wait {wait}s then retry once")
                time.sleep(wait)
                continue
            # 重试后仍 429 -> 返回, 交由 _raise_for_provider 抛错(干净失败 + 退款)
            return resp
        if resp.status_code in _TRANSIENT_5XX:  # 真正瞬时过载 / Cloudflare 源站异常 -> 退避重试
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
                            backoff_cap: int = 20,
                            fallback_url: str | None = None):
    """异步版 POST (httpx): 仅对连接级错误与瞬时 5xx 重试, 不对读取超时重试。

    语义与 _post_with_retry 完全一致, 区别仅在用 ``await client.post(...)`` ——
    等待外部响应期间让出事件循环, 不占 OS 线程 (见 async_core/engine.py)。
    """
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
                    await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), backoff_cap))
                    continue
            elif attempt < max_attempts:
                await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), backoff_cap))
                continue
            raise RuntimeError(
                f"provider connection failed ({type(e).__name__}): {url}"
            ) from e
        except httpx.TimeoutException as e:  # 超时(含读取超时) -> 同址重试, 不切换
            last_err = e
            if attempt < max_attempts:
                await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), backoff_cap))
                continue
            raise RuntimeError(
                f"provider timeout failed ({type(e).__name__}): {url}"
            ) from e
        # 429 = 限流(上游配额窗口): 按真实窗口整段等待, 最多重试 1 次, 绝不烧额度。
        if resp.status_code == 429:
            if attempt < 2:
                wait = _parse_rate_limit_wait_s(resp, settings.provider_rate_limit_default_window_s)
                wait = min(wait, settings.rate_limit_max_wait_s)
                print(f"[agnes] attempt {attempt} got 429 rate limit, wait {wait}s then retry once")
                await asyncio.sleep(wait)
                continue
            # 重试后仍 429 -> 返回, 交由 _raise_for_provider 抛错(干净失败 + 退款)
            return resp
        if resp.status_code in _TRANSIENT_5XX:  # 真正瞬时过载 / Cloudflare 源站异常 -> 退避重试
            last_err = RuntimeError(f"provider HTTP {resp.status_code}")
            if attempt < max_attempts:
                await asyncio.sleep(min(backoff_base * (2 ** (attempt - 1)), backoff_cap))
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
        # 每个 provider 各自声明「外部模型下载参考图用的公网基址」(per-provider)。
        # 为空则回退到全局 settings.external_ref_base_url(PEA_EXTERNAL_REF_BASE_URL),
        # 再回退 cdn_base_url。目的: 不同模型可用不同隧道/域名, 避免"一个隧道死=全挂"。
        self.external_ref_base_url: str = (cfg.get("external_ref_base_url") or "").strip()

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
        # 按适配器声明的参考图策略解析: 图片=内联 base64 (不经公网);
        # 视频=转公网 URL (PublicUrlStrategy)。策略由适配器单一决定。
        norm.reference_images = adapter.ref_strategy.resolve(norm.reference_images, self)
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
        # 同 _generate_image: 参考图按适配器声明的策略解析 (图片=base64内联, 不经公网)。
        norm.reference_images = adapter.ref_strategy.resolve(norm.reference_images, self)
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
    # ── 参考图解析(抽象钩子) ──────────────────────────────────────
    def resolve_refs(self, refs: list[str]) -> list[str]:
        """把参考图解析为外部模型可下载的 URL(抽象钩子, 代理层 BaseProviderAdapter 同签名).

        默认实现: data URI 转存到公开 gen/ 前缀, 并按 per-provider external_ref_base_url
        前缀替换为公网地址(Agnes 视频接口只接受 http(s) URL)。
        新增模型若参考图喂法不同(如接受 data URI / 签名 URL / 不同 CDN),
        覆写本方法即可, 无需复制整个提交逻辑 —— 这就是"加模型=只传参"的边界。
        """
        return _ensure_http_refs_for_video(
            refs,
            public_base=(self.external_ref_base_url or None),
            cdn_base=settings.cdn_base_url,
        )

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
        raw_refs = params.get("reference_images")
        # ★ 视频接口的 image 字段只接受可下载的 http(s) URL (不认 base64);
        # 用 PublicUrlStrategy 把 data:/内部 URL 经 MinIO 转 base64 后, 再转存到
        # 公开存储得到 Agnes 可访问的公网 URL (PEA_EXTERNAL_REF_BASE_URL/CDN 兜底)。
        refs = PublicUrlStrategy().resolve(raw_refs, self)
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
            # 视频队列在晚高峰常被上游打满 (video_queue_full, HTTP 503, 上游明示 "retry later")。
            # 原 max_attempts=2 只重试 1 次(4s)就放弃 -> 立即 FAILED+退款, 把可自愈的瞬时饱和
            # 误判成永久故障。这里放大到 5 次、退避 15/30/60/60s (封顶 60s), 总等待 ~165s,
            # 足以桥接观察到的数分钟级饱和窗口; 若持续满则照常 FAILED+退款(用户不为失败付费)。
            max_attempts=5,
            backoff_base=15,
            backoff_cap=60,
            fallback_url=submit_fb,
        )
        # 视频端点 404/405 = 该提供商根本没有 /v1/videos 这条路由。
        #
        # 背景: "OpenAI 兼容"只在 chat/completions 那一层是业界事实标准。图像层各家
        # 参数方言不同(靠 param_adapters 消化), 视频层则**根本没有 OpenAI 标准**——
        # /v1/videos + /agnesapi?video_id= 是 Agnes 自己设计的。火山方舟用
        # /api/v3/contents/generations/tasks, MiniMax 用 /v2/video_generation, 各不相同。
        #
        # 这里不做厂商白名单(会误伤 one-api 这类确实转发 /v1/videos 的中转网关),
        # 而是在上游明确回 404/405 时把裸状态码翻译成可操作的结论, 避免使用者
        # 对着 "video-submit HTTP 404" 猜半天。
        if resp.status_code in (404, 405):
            raise RuntimeError(
                f"video-submit HTTP {resp.status_code}: 提供商 {self.provider_name} 的 "
                f"{submit_url} 不存在。视频生成没有 OpenAI 标准协议, 该厂商用的是自有端点, "
                f"需要为其实现专用适配器 (参考 app/providers/minimax.py, "
                f"用 @register_provider('vendor-native', '<vendor>') 注册)。"
                f"该提供商的文本/图像能力不受影响。"
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
                # proxies=None: 强制直连(同 httpx trust_env=False), 不被死代理劫持。
                resp = requests.get(
                    target, headers=self._headers(),
                    timeout=(settings.provider_http_connect_timeout_s, 60),
                    proxies={"http": None, "https": None},
                )
                sc = resp.status_code
                if sc // 100 == 2:
                    return resp.json()
                # 4xx(客户端错误, 非 429 限流): 任务被拒/不存在/内容策略违规 —— 这是**终态**,
                # 不应当作瞬时错误无限重试。归一为 {status:failed} 让上层走失败分支:
                #   - Completer 据此标记 job=FAILED(用户能看到明确原因, 而非永久转圈);
                #   - 同步路径 _generate_video 据此抛 "video generation failed"。
                # 否则会像 2026-08-01 的 job(9726cebc) 那样卡 processing 重试上百次、一天都出不来。
                if 400 <= sc < 500 and sc != 429:
                    body = _safe_status_body(resp)
                    logger.warning(
                        "[agnes] video-status 终态 4xx (任务被拒/内容策略): HTTP %d %s",
                        sc, body[:200],
                    )
                    return {"status": "failed", "error": f"video-status HTTP {sc}: {body}"}
                # 429 限流 / 5xx 服务端错: 仍属瞬时, 抛出由上层退避重试
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
        """同步全量路径 (提交 + 轮询). 保留给测试/同步调用方; 新消费链路走 _submit_video_only + Completer."""
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


def _verify_public_ref_reachable(url: str) -> None:
    """提交前预检：从编排器侧先拉一次参考图 URL, 确认它对「外部模型视角」是可达的图片。

    背景：视频接口的 image 字段只接受 http(s) URL, 而外部模型(Agnes)处在公网上,
    必须由 ``PEA_EXTERNAL_REF_BASE_URL`` 指向的隧道/公网域名把参考图暴露出去。
    一旦该隧道子域过期(典型如花生壳/ngrok 子域失效), 外部请求会被隧道服务方回一个
    HTTP 200 的 HTML 占位页 —— Agnes 拿到 HTML 而非图片就会报晦涩的
    ``image URL could not be downloaded or did not return a valid supported image`` (HTTP 400)。

    编排器与 Agnes 同为「外部」视角(都需经公网/隧道到达用户服务器), 故本侧拉取结果
    可近似预测 Agnes 侧可达性。预检发现「非 2xx」或「Content-Type 非 image/*」时,
    **提前抛出清晰错误**, 把原本要在 Agnes 侧才暴露的 400 变成一眼能定位的失败,
    而不是静默把垃圾 URL 交给上游。

    仅当本侧拉取本身网络异常(非内容问题, 如编排器出口被限)时才只告警不阻断 ——
    这种情况可能是编排器侧的瞬时/出口限制, 仍交给 Agnes 最终判定, 避免误杀其实可达的 URL。
    """
    try:
        resp = requests.get(
            url,
            timeout=(settings.provider_http_connect_timeout_s, 20),
            stream=True,
            proxies={"http": None, "https": None},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[video-ref] 预检拉取参考图异常(不阻断, 交 Agnes 最终判定): %s | %s",
            url[:120], exc,
        )
        return
    try:
        ct = resp.headers.get("Content-Type", "") or ""
        if resp.status_code // 100 == 2 and ct.startswith("image/"):
            return
        # 确属「不可达 / 非图片」: 抓一点响应体辅助定位(如隧道占位页 HTML)。
        snippet = ""
        try:
            chunk = next(resp.iter_content(256), b"")
            snippet = chunk.decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            "视频参考图 URL 对外部模型不可达或返回非图片内容: "
            f"{url[:140]} (HTTP {resp.status_code}, Content-Type={ct!r})。"
            "请核查 PEA_EXTERNAL_REF_BASE_URL 指向的隧道/公网域名是否仍有效且能返回图片"
            + (f"；疑似隧道占位页: {snippet!r}" if snippet else "")
        )
    finally:
        resp.close()


def _ensure_http_refs_for_video(refs: list[str], public_base: str | None = None,
                                cdn_base: str | None = None) -> list[str]:
    """确保视频参考图全部为 http(s) URL（Agnes 视频 API 的 image 字段只接受可下载 URL）。

    _normalize_refs 对内部 URL(localhost/私有IP/容器别名)会降级成 base64 data URI，
    这对图片接口（extra_body.image[] 数组）可以工作，但视频接口的顶层 image 字符串
    字段只接受 http(s) URL，data URI 会被静默忽略 → 视频与参考图无关。

    策略：检测到 data: URI 时，解码后通过 storage.store_bytes 上传到公开 gen/ 前缀，
    再按 per-provider public_base（优先）/ 全局 PEA_EXTERNAL_REF_BASE_URL / PEA_CDN_BASE_URL
    返回外部模型可下载的 URL。这样前端展示可走相对路径 /media（本站 nginx 代理 MinIO），
    而 Agnes 拿到的是公网 URL。

    public_base / cdn_base 由调用方(per-provider)显式传入；缺省时回退到全局 settings。
    """
    if not refs:
        return refs

    # 外部模型实际看到的基址；未传入则回退到全局 external_ref_base_url，再回退 cdn_base_url。
    cdn_base = (cdn_base or settings.cdn_base_url or "").rstrip("/")
    public_base = (public_base or settings.external_ref_base_url or cdn_base).rstrip("/")

    out: list[str] = []
    for r in refs:
        if r.startswith("data:"):
            # 解码 data URI → 上传到公开存储 → 得到内部 CDN URL
            try:
                match = re.match(r"data:([^;]+);base64,(.+)", r, re.DOTALL)
                if not match:
                    logger.warning("[video-ref] 无法解析 data URI 格式, 跳过 (前80字符): %s", r[:80])
                    continue
                mime = match.group(1)
                b64_body = match.group(2)
                # 补齐 base64 padding
                padding = 4 - len(b64_body) % 4
                if padding != 4:
                    b64_body += "=" * padding
                image_data = base64.b64decode(b64_body)
                media_type = "image" if mime.startswith("image/") else "image"

                # 延迟导入避免循环依赖
                from app import storage
                internal_url = storage.store_bytes(image_data, media_type, content_type=mime)
                # 若外部参考图基址与内部 CDN 基址不同，则替换前缀给 Agnes
                public_url = internal_url
                if public_base and cdn_base and public_base != cdn_base and internal_url.startswith(cdn_base + "/"):
                    public_url = public_base + internal_url[len(cdn_base):]
            except Exception as exc:
                logger.warning("[video-ref] data URI 转 HTTP URL 失败, 该参考图将被跳过: %s", exc)
                continue
            # 转存成功后做提交前可达性预检: 隧道失效会在此**清晰暴露**为可读错误,
            # 而非把垃圾 URL 丢给 Agnes 吃晦涩的 "image URL could not be downloaded" 400。
            # 预检失败(RuntimeError)直接上抛 -> 任务 FAILED + 退款, 用户能看到明确原因。
            _verify_public_ref_reachable(public_url)
            out.append(public_url)
            logger.info(
                "[video-ref] data URI (%d bytes) 已转存为公开 URL: %s",
                len(image_data), public_url[:120],
            )
        else:
            # 已是 http(s) URL: 同样做可达性预检(可能是已失效的公网地址 / 失效隧道子域)。
            _verify_public_ref_reachable(r)
            out.append(r)

    # 检查最终给 Agnes 的 URL 是否真正公网可达
    check_base = public_base or cdn_base
    if out and ("localhost" in check_base or "127.0.0.1" in check_base or check_base.startswith("/")):
        logger.warning(
            "[video-ref] ⚠️ 外部参考图基址=%s 含 localhost 或相对路径 —— "
            "Agnes 等**外部模型**可能无法下载转存后的参考图 URL。"
            "请设置 PEA_EXTERNAL_REF_BASE_URL 为公网可达地址（如 https://your-domain.com/media）。"
            "当前 %d 张参考图可能仍被 Agnes 忽略。",
            check_base, len(out),
        )

    return out


def _safe_status_body(resp) -> str:
    """截断并规整状态查询的错误响应体(与 _raise_for_provider 同样剥离 HTML 页)。

    用于 video-status 终态 4xx 的 error 文案, 避免把整页 HTML/超长 JSON 灌进 job 错误字段。
    """
    try:
        body = resp.text[:200]
    except Exception:  # noqa: BLE001
        body = ""
    if body.lstrip().startswith(("<!DOCTYPE", "<!doctype", "<html", "<HTML")):
        return getattr(resp, "reason_phrase", None) or getattr(resp, "reason", "") or "upstream error"
    return body


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
