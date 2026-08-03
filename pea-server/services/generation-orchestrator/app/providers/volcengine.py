"""Volcengine 方舟 (ARK) 原生适配器: 图像(Seedream/SeedEdit) + 视频(Seedance/Seaweed) + 文本(chat).

为什么单独一个文件
------------------
火山方舟的**图像/视频端点与 OpenAI 不兼容** (独立 SDK / 独立路径), 硬塞进
OpenAICompatibleProvider(Agnes 适配器) 只会 404 或参数错配。按项目既定边界
(注册表 + @register_provider), 新厂商 = 一个自洽的适配器文件 + 一行注册, 不碰工厂逻辑。

注册键: ("vendor-native", "volcengine") —— 协议=vendor-native (厂商自有协议), 厂商=volcengine。
与前端「协议=厂商原生协议」「厂商=火山方舟」两个下拉一一对应, 与 MiniMax 同款模式。

火山方舟真实 API (2026-08-03 官方文档核对):
【图像 generation】
  POST /api/v3/images/generations
    {model, prompt, size:"2K", n, response_format:"url", watermark:false,
     image:[<data URI 或 https URL>] (图生图/SeedEdit, 可多张)}
    -> {data:[{url|b64_json}], created, model}
  ⚠️ size 用档位式 "1K"/"2K"/"4K" (与 Seedream 文档示例一致); 也接受 "宽x高" 像素值。
【视频 generation】
  POST /api/v3/contents/generations/tasks
    {model, content:[{type:"text",text} | {type:"image_url",image_url:{url}}],
     duration, resolution:"720p", ratio:"16:9", generate_audio:true, watermark:false, seed}
    -> {id}   (异步任务 id)
  GET  /api/v3/contents/generations/tasks/{id}
    -> {id, status:"succeeded"|"processing"|"failed"|..., content:{video_url, ...}}
  ⚠️ video_url 有效期仅 24h, 由 dispatcher._rehost 转存到 MinIO (与 Agnes/MiniMax 一致),
     否则 24h 后前端裂图。
【文本 chat (OpenAI 兼容)】
  POST /api/v3/chat/completions (标准 OpenAI 形状) —— 编排器侧文本生成走这条,
  与 BFF 侧 buildOpenAIChatUrl 各自处理 /api/v3 前缀。

错误处理:
  - 402 / insufficient_balance -> 友好"余额不足" (用户当前 key 无钱会命中此分支, 不崩溃、不静默给假图)。
  - 4xx/5xx -> 友好中文消息 + 完整 technical 进 logger, 由上层置 FAILED 触发退款。
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx
import requests

from app.agnes_provider import _apost_with_retry, _short
from app.async_core.provider_adapter import BaseProviderAdapter, register_provider
from app.async_core.types import (
    AsyncHandle,
    CompletionMode,
    GenerationResult,
    NormalizedStatus,
    PollStatus,
    ProviderCapabilities,
    SubmitOutcome,
)
from app.config import settings
from app.param_adapters import Base64InlineStrategy, normalize_image_params

logger = logging.getLogger(__name__)

# ── 模型族正则 (前缀/关键词匹配, 大小写不敏感) ───────────────────────
_IMAGE_MODEL_RE = re.compile(r"seedream|seededit", re.IGNORECASE)
_VIDEO_MODEL_RE = re.compile(r"seedance|seaweed", re.IGNORECASE)
_3D_MODEL_RE = re.compile(r"seed3d|hyper3d|hitem3d", re.IGNORECASE)

# 火山方舟图像 size 白名单 (档位式; 也接受 "宽x高" 像素值)
_VOLC_IMAGE_SIZES = {"1K", "2K", "3K", "4K"}
# 火山方舟视频 resolution 白名单 (p 制)
_VOLC_VIDEO_RES = {"480p", "720p", "1080p", "4k"}
# 火山方舟视频 ratio 白名单 (另支持 "adaptive" 自适应内容/首帧尺寸)
_VOLC_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "3:2", "2:3"}
# 档位式 -> 火山 p 制 (1K/2K/3K/4K 非火山原生枚举, 需映射)
_TIER_TO_VOLC_VIDEO_RES = {"1k": "480p", "2k": "720p", "3k": "1080p", "4k": "1080p"}


def _clamp(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _classify_volcengine_error(status: int, body: dict | None, what: str) -> tuple[str, str]:
    """把火山方舟原始错误归类为 ``(friendly_msg, technical)`` (与 MiniMax 同构)。

    - friendly_msg: 给前端 toast 的简短中文消息 (≤ 40 字符)。
    - technical: 完整原始错误, 仅进 logger, 不向前端暴露。
    """
    err = body.get("error") if isinstance(body, dict) else None
    code = (err or {}).get("code") if isinstance(err, dict) else None
    msg = (err or {}).get("message") if isinstance(err, dict) else None
    if not msg and isinstance(body, dict):
        msg = body.get("message")
    code_s = str(code or "").lower()
    msg_s = str(msg or "")

    # 余额不足 (最常见, 用户当前 key 无钱会命中)
    if status == 402 or "balance" in code_s or "余额" in msg_s:
        friendly = "火山方舟账户余额不足，请充值后重试"
        technical = f"insufficient balance | http={status} code={code} msg={msg}"
        return friendly, technical
    # 鉴权失败
    if status in (401, 403):
        friendly = "火山方舟鉴权失败，请检查 API Key"
        technical = f"auth failed | http={status} code={code} msg={msg}"
        return friendly, technical
    # 限流
    if status == 429:
        friendly = "火山方舟限流，请稍后再试"
        technical = f"rate limited | http={status} code={code} msg={msg}"
        return friendly, technical
    # 参数非法
    if status == 400:
        friendly = "火山方舟参数错误，请检查模型参数（时长/分辨率/参考图等）"
        technical = f"invalid params | http={status} code={code} msg={msg}"
        return friendly, technical
    # 上游异常
    if status // 100 == 5:
        friendly = "火山方舟服务暂不可用，请稍后再试"
        technical = f"upstream 5xx | http={status} code={code} msg={msg}"
        return friendly, technical
    friendly = f"火山方舟调用失败（HTTP {status}）"
    technical = f"unknown | http={status} code={code} msg={msg}"
    return friendly, technical


def _raise_for_volcengine(resp, what: str, body: dict | None = None) -> dict:
    """火山方舟统一错误检查: HTTP 非 2xx 或响应带 error 字段都抛 RuntimeError。

    抛出时 message 是友好摘要 (适配前端 toast); 完整 technical 仅进 logger。
    绝不静默返回空结果 (扣费给假图不可接受)。
    """
    if resp.status_code // 100 != 2:
        txt = ""
        try:
            txt = resp.text[:300]
        except Exception:  # noqa: BLE001
            pass
        try:
            parsed = resp.json()
        except Exception:
            parsed = {}
        friendly, technical = _classify_volcengine_error(resp.status_code, parsed, what)
        logger.warning("[volcengine] %s %s | technical=%s | body=%s", what, friendly, technical, txt[:200])
        raise RuntimeError(friendly)

    if body is None:
        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"volcengine {what} 响应非 JSON: {_short(getattr(resp, 'text', ''))}") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"volcengine {what} 响应结构异常: {_short(body)}")

    # 任务类接口可能 HTTP 200 但带 error 字段
    err = body.get("error")
    if isinstance(err, dict) and err.get("code"):
        friendly, technical = _classify_volcengine_error(resp.status_code, body, what)
        logger.warning("[volcengine] %s %s | technical=%s", what, friendly, technical)
        raise RuntimeError(friendly)
    return body


@register_provider("vendor-native", "volcengine")
class VolcengineAdapter(BaseProviderAdapter):
    """火山方舟原生适配器: 覆盖图像/视频/文本(chat, OpenAI 兼容)。

    完成模式声明为 POLL —— 视频异步走句柄轮询; 图像/文本在 submit 里直接
    ``SubmitOutcome(sync=True)`` 返回, 不进句柄表 (与 MiniMaxAdapter / AgnesAdapter 同构)。
    """

    # 火山方舟图像 API 的 image[] 与视频 content[].image_url 接受 base64 data URI,
    # 故参考图直接内联 (省掉公网转存, 与 MiniMax 同策略)。
    # ⚠️ 若真机验证发现视频 content.image_url 不接受 base64, 改走 PublicUrlStrategy 即可。
    ref_strategy = Base64InlineStrategy()

    # ── 契约声明 ────────────────────────────────────────────────
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            completion_mode=CompletionMode.POLL,
            accepts_callback=False,
        )

    def resolve_refs(self, refs: list[str]) -> list[str]:
        """覆写: 参考图内联 base64 data URI, 不经公网转存。"""
        return self.ref_strategy.resolve(refs, provider=self)

    # ── HTTP 基建 ───────────────────────────────────────────────
    def _url(self, path: str) -> str:
        """拼火山方舟真实端点。

        火山 base_url 形如 ``https://ark.cn-beijing.volces.com/api/v3``,
        其原生端点是 ``/api/v3/<path>`` (非 /v1)。这里显式剥离可能的 /api/v3 尾部再拼回,
        **不**复用 agnes 的 _api_base (那会把 /api/v3 末端的 base 误当版本段处理, 造成双前缀)。
        """
        root = (self.base_url or "").rstrip("/")
        if root.endswith("/api/v3"):
            root = root[: -len("/api/v3")]
        return f"{root}/api/v3{path}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ── 类型分发 ────────────────────────────────────────────────
    def _kind(self, req: dict) -> str:
        """确定实际要走的火山端点族 (image / video / text)。

        优先用前端声明的 type; 回退按 model_name 关键词 (seedream/seededit=图像,
        seedance/seaweed=视频, 其余默认图像)。
        """
        t = (req.get("type") or "").lower()
        if t in ("image", "img"):
            return "image"
        if t in ("video", "vid"):
            return "video"
        if t in ("3d", "threed", "three-d", "model3d"):
            return "3d"
        if t in ("audio", "music", "speech"):
            return "audio"
        if t in ("text", "chat"):
            return "text"
        m = (self.model_name or "").lower()
        if _VIDEO_MODEL_RE.search(m):
            return "video"
        if _3D_MODEL_RE.search(m):
            return "3d"
        if _IMAGE_MODEL_RE.search(m):
            return "image"
        return "image"

    async def submit(self, req: dict) -> "SubmitOutcome":
        kind = self._kind(req)
        if kind == "image":
            return SubmitOutcome(sync=True, result=await self._gen_image(req))
        if kind == "video":
            return await self._submit_video(req)
        if kind == "3d":
            return await self._submit_3d(req)
        if kind == "audio":
            # 火山方舟音乐/语音走独立 IAM 网关(imagination), 与 ARK /api/v3 凭证体系不同。
            # 占位分支: 待开通服务并接入 IAM AK/SK 后实现; 当前明确报错而非静默失败。
            raise RuntimeError(
                "火山方舟音乐/语音生成走独立 IAM 网关(imagination), 尚未接入；"
                "请改用 MiniMax 音乐模型, 或联系管理员配置 IAM 凭据"
            )
        return SubmitOutcome(sync=True, result=await self._gen_text(req))

    # ── 字段映射辅助 ────────────────────────────────────────────
    @staticmethod
    def _map_image_size(tier: str | None) -> str:
        if tier in _VOLC_IMAGE_SIZES:
            return tier  # 档位式 1K/2K/3K/4K
        if tier and re.match(r"^\d+x\d+$", tier or ""):
            return tier  # 像素值如 1024x1024 透传
        return "2K"

    @staticmethod
    def _map_video_resolution(tier: str | None) -> str:
        t = (tier or "").lower()
        if t in _VOLC_VIDEO_RES:
            return t
        return _TIER_TO_VOLC_VIDEO_RES.get(t, "720p")

    @staticmethod
    def _map_ratio(ratio: str | None) -> str:
        r = (ratio or "").strip()
        return r if r in _VOLC_RATIOS else "adaptive"

    # ── 图像 (Seedream / SeedEdit) ─────────────────────────────
    def _build_image_payload(self, req: dict) -> dict:
        norm = normalize_image_params(req)
        refs = self.ref_strategy.resolve(norm.reference_images, provider=self)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": norm.prompt,
            "size": self._map_image_size(norm.size_tier),
            "n": _clamp(norm.n, 1, 4, 1),
            "response_format": "url",
            "watermark": False,
        }
        if norm.seed is not None:
            payload["seed"] = norm.seed
        if refs:
            # 图生图 / SeedEdit: image[] 数组, 内联 base64 data URI (顺序保持)
            payload["image"] = refs
            logger.info("[volcengine] image refs=%d (img2img via image[])", len(refs))
        return payload

    async def _gen_image(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        payload = self._build_image_payload(req)
        resp = await _apost_with_retry(
            get_client(), self._url("/images/generations"), payload, self._headers(),
            httpx.Timeout(settings.provider_image_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=settings.provider_image_retry_attempts,
        )
        data = _raise_for_volcengine(resp, "image")
        items = data.get("data") or []
        urls = [it.get("url") for it in items if isinstance(it, dict) and it.get("url")]
        if not urls:
            # 退化: 上游若返回 b64_json, 包成 data URI
            b64 = [it.get("b64_json") for it in items if isinstance(it, dict) and it.get("b64_json")]
            if b64:
                urls = [f"data:image/png;base64,{b}" for b in b64]
        if not urls:
            raise RuntimeError(f"volcengine image 未返回图片地址: {_short(data)}")
        return GenerationResult(
            url=urls[0], urls=urls, provider=self.provider_name,
            raw={"id": data.get("id")}, usage={},
        )

    # ── 视频 (Seedance / Seaweed) ──────────────────────────────
    def _build_video_payload(self, req: dict) -> dict:
        p = req.get("params") or {}
        content: list[dict] = [{"type": "text", "text": req.get("prompt") or ""}]
        refs = self.ref_strategy.resolve(p.get("reference_images") or [], provider=self)
        if refs:
            # 图生视频 (i2v): 仅取首张作首帧; 火山 content.image_url 接受 base64 data URI
            content.append({"type": "image_url", "image_url": {"url": refs[0]}})
            if len(refs) > 1:
                logger.warning(
                    "[volcengine] video 仅取首张参考图作为首帧, 丢弃其余 %d 张 (model=%s)",
                    len(refs) - 1, self.model_name,
                )
        payload: dict[str, Any] = {
            "model": self.model_name,
            "content": content,
            "duration": _clamp(p.get("duration"), 5, 20, 5),
            "resolution": self._map_video_resolution(p.get("resolution") or p.get("size")),
            "ratio": self._map_ratio(p.get("aspectRatio")),
            "generate_audio": bool(p.get("generate_audio", True)),
            "watermark": bool(p.get("watermark", False)),
        }
        if p.get("seed") is not None:
            try:
                payload["seed"] = int(p["seed"])
            except (TypeError, ValueError):
                pass
        return payload

    async def _submit_video(self, req: dict) -> "SubmitOutcome":
        from app.async_core.engine import get_client

        payload = self._build_video_payload(req)
        resp = await _apost_with_retry(
            get_client(), self._url("/contents/generations/tasks"), payload, self._headers(),
            httpx.Timeout(settings.provider_video_submit_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_volcengine(resp, "video submit")
        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise RuntimeError(f"volcengine video 未返回任务 id: {_short(data)}")
        logger.info("[volcengine] video submitted task_id=%s model=%s", task_id, self.model_name)
        return SubmitOutcome(sync=False, handle=AsyncHandle(
            job_id=req.get("job_id", ""),
            user_id=int(req.get("user_id", 0) or 0),
            provider=self.provider_name,
            completion_mode=CompletionMode.POLL,
            provider_task_id=str(task_id),
            status_query=self._url(f"/contents/generations/tasks/{task_id}"),
        ))

    # ── 3D (Seed3D / Hyper3D / HiMeta3D) ──────────────────────────
    # 复用视频的 /contents/generations/tasks 异步任务端点 (火山方舟 3D 与视频同族),
    # 区别: 输入是单张参考图(image_url), 结果在 content.file_url (glb/obj/...)。
    def _build_3d_payload(self, req: dict) -> dict:
        p = req.get("params") or {}
        refs = self.ref_strategy.resolve(p.get("reference_images") or [], provider=self)
        content: list[dict] = []
        if refs:
            content.append({"type": "image_url", "image_url": {"url": refs[0]}})
        else:
            # hyper3d 等支持文生3D: 退化为文本输入
            content.append({"type": "text", "text": req.get("prompt") or ""})
        return {
            "model": self.model_name,
            "content": content,
        }

    async def _submit_3d(self, req: dict) -> "SubmitOutcome":
        from app.async_core.engine import get_client

        payload = self._build_3d_payload(req)
        resp = await _apost_with_retry(
            get_client(), self._url("/contents/generations/tasks"), payload, self._headers(),
            httpx.Timeout(settings.provider_video_submit_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_volcengine(resp, "3d submit")
        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise RuntimeError(f"volcengine 3d 未返回任务 id: {_short(data)}")
        logger.info("[volcengine] 3d submitted task_id=%s model=%s", task_id, self.model_name)
        return SubmitOutcome(sync=False, handle=AsyncHandle(
            job_id=req.get("job_id", ""),
            user_id=int(req.get("user_id", 0) or 0),
            provider=self.provider_name,
            completion_mode=CompletionMode.POLL,
            provider_task_id=str(task_id),
            status_query=self._url(f"/contents/generations/tasks/{task_id}"),
        ))

    # ── 状态查询 (Completer 后台线程调用, 同步实现) ─────────────────
    def query_status(self, handle: AsyncHandle) -> PollStatus:
        sq = handle.status_query or ""
        resp = requests.get(
            sq, headers=self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, 60),
            proxies={"http": None, "https": None},
        )
        data = _raise_for_volcengine(resp, "video status")
        raw = str(data.get("status") or "").strip().lower()
        content = data.get("content") or {}
        if raw in ("succeeded", "success", "completed", "done"):
            url = (
                content.get("video_url")
                or content.get("url")
                or content.get("file_url")
                or ""
            )
            if not url:
                return PollStatus(
                    normalized=NormalizedStatus.FAILED, raw_status=raw,
                    error=f"video 已完成但无下载地址: {_short(data)}",
                )
            return PollStatus(normalized=NormalizedStatus.DONE, raw_status=raw, result_url=url)
        if raw in ("failed", "error", "cancelled", "canceled", "expired"):
            err = content.get("message") or data.get("message") or f"video {raw}"
            return PollStatus(normalized=NormalizedStatus.FAILED, raw_status=raw, error=err)
        # submitted / processing / running / queued
        return PollStatus(
            normalized=NormalizedStatus.PROCESSING if raw in ("processing", "running") else NormalizedStatus.PENDING,
            raw_status=raw or "submitted",
            progress=content.get("progress"),
        )

    # ── 文本 (OpenAI 兼容 chat/completions) ─────────────────────
    async def _gen_text(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        p = req.get("params") or {}
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": req.get("prompt") or ""}],
        }
        if p.get("system"):
            payload["messages"].insert(0, {"role": "system", "content": p["system"]})
        payload["max_tokens"] = _clamp(p.get("max_tokens") or 8192, 1024, 1_000_000, 8192)
        if p.get("temperature") is not None:
            try:
                payload["temperature"] = float(p["temperature"])
            except (TypeError, ValueError):
                pass
        resp = await _apost_with_retry(
            get_client(), self._url("/chat/completions"), payload, self._headers(),
            httpx.Timeout(300, connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_volcengine(resp, "text")
        try:
            choice = data["choices"][0]
            content = (choice.get("message") or {}).get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"volcengine text 响应结构异常: {_short(data)}") from exc
        if not content.strip():
            raise RuntimeError(f"volcengine text 返回空内容: {_short(data)}")
        return GenerationResult(
            url="", provider=self.provider_name, raw={}, text=content, usage={},
        )
