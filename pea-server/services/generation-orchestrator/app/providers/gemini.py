"""Google Gemini (Generative Language API) 原生适配器: 文本 + 图像 + 视频(Veo).

为什么单独一个文件 (而不是复用 openai-compatible)
--------------------------------------------------
Google 确实提供了 OpenAI 兼容层 (``/v1beta/openai/chat/completions``), **但只覆盖文本**。
图像与视频完全是自有协议:

  - 图像(Gemini Image / nano-banana): ``:generateContent`` 返回 ``inlineData`` base64,
    **不是** OpenAI ``{data:[{url}]}`` 形状;
  - 图像(Imagen):                    ``:predict`` + ``instances/parameters``;
  - 视频(Veo):                        ``:predictLongRunning`` + Operation 轮询 +
    **带鉴权头才能下载**的结果 URI。

按项目既定边界 (注册表 + @register_provider), 新厂商 = 一个自洽适配器文件 + 一行注册,
不碰工厂逻辑, 也不去改 agnes_provider._api_base (那条路会波及 Agnes/MiniMax/Volcengine)。

注册键: ("vendor-native", "gemini") —— 与前端「协议=厂商原生协议」「厂商=Google Gemini」对应。

真实 API (2026-08-03 实测 + 官方文档核对)
-----------------------------------------
鉴权: 请求头 ``x-goog-api-key: <API_KEY>`` (Google 原生; **不是** Authorization Bearer)。
Base: ``https://generativelanguage.googleapis.com/v1beta``

【文本】POST /models/{model}:generateContent
    {contents:[{role:"user",parts:[{text}]}], systemInstruction?, generationConfig:{...}}
    -> {candidates:[{content:{parts:[{text}]}, finishReason}], usageMetadata:{...}}
    ⚠️ Gemini 3 思考模型会返回 ``parts[i].thought == true`` 的思维摘要片段,
       必须过滤, 否则思维链会被当成正文返回给用户。

【图像 A - Gemini Image (nano-banana 系)】POST /models/{model}:generateContent
    {contents:[{parts:[{text}, {inlineData:{mimeType,data}}...]}],
     generationConfig:{responseModalities:["IMAGE"], imageConfig:{aspectRatio,imageSize}}}
    -> candidates[0].content.parts[i].inlineData.{mimeType,data(base64)}
    ⚠️ 只出 1 张 (candidateCount>1 会 400), n>1 只能靠多次调用 —— 见 _gen_image 注释。

【图像 B - Imagen】POST /models/{model}:predict
    {instances:[{prompt}], parameters:{sampleCount, aspectRatio}}
    -> {predictions:[{bytesBase64Encoded, mimeType}]}
    ⚠️ 2026-08 实测 imagen-4.0-* 对新 key 返回 404 "no longer available to new users",
       保留该分支仅为兼容存量账号。

【视频 - Veo】POST /models/{model}:predictLongRunning
    {instances:[{prompt, image?:{inlineData:{mimeType,data}}, lastFrame?:{...}}],
     parameters:{aspectRatio, resolution, negativePrompt}}
    -> {name:"models/veo-.../operations/xxx"}
    GET /{operation_name}
    -> {done:bool, error?:{...}, response:{generateVideoResponse:{generatedSamples:[{video:{uri}}]}}}
    ⚠️⚠️ 结果 uri **必须带 x-goog-api-key 头才能下载**, 匿名 GET 会 403。
        因此不能像 MiniMax/火山那样把 uri 交给 dispatcher._rehost (它匿名拉取),
        本适配器在 query_status 里就地带头下载 + storage.store_bytes 落自有存储,
        返回稳定地址。这是 Gemini 与其它厂商最大的结构性差异。

错误处理
--------
Google 错误体统一为 ``{"error":{"code","message","status"}}``, status 是枚举字符串
(RESOURCE_EXHAUSTED / PERMISSION_DENIED / INVALID_ARGUMENT / NOT_FOUND ...)。
按 status 优先、HTTP code 兜底做中文归类, 完整原文只进 logger, 不外泄给前端。
另有 **HTTP 200 但被安全策略拦截** 的情形 (promptFeedback.blockReason /
finishReason=SAFETY|IMAGE_SAFETY|PROHIBITED_CONTENT), 必须显式抛错 ——
绝不静默返回空结果 (扣了费给空白图是不可接受的)。
"""
from __future__ import annotations

import base64
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

# ── 模型族识别 ────────────────────────────────────────────────────────
# 铁律(与 BFF suggestModelType 同源教训): 只匹配**能力级**词根, 绝不匹配裸厂商名。
# 'gemini' 是 Google 全谱系品牌 (文本/图像/TTS/机器人全叫 gemini-*), 匹配它等于没匹配。
_VIDEO_MODEL_RE = re.compile(r"\bveo\b|veo-", re.IGNORECASE)
_IMAGEN_MODEL_RE = re.compile(r"^imagen", re.IGNORECASE)
_IMAGE_MODEL_RE = re.compile(r"-image|nano-banana", re.IGNORECASE)
# Omni 走 generateContent 出视频, 与 Veo 的 LRO 协议不同, 当前未实现 -> 明确报错而非乱调。
_OMNI_MODEL_RE = re.compile(r"omni", re.IGNORECASE)

# Gemini imageConfig.aspectRatio 白名单 (官方支持集)
_GEMINI_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
# Gemini imageConfig.imageSize 档位 (与系统内部 size_tier 同构, 直接可用)
_GEMINI_IMAGE_SIZES = {"1K", "2K", "4K"}
# Veo parameters.resolution 白名单
_VEO_RESOLUTIONS = {"720p", "1080p", "4k"}
# 内部档位 -> Veo 分辨率 (1K/2K/3K/4K 非 Veo 原生枚举, 需映射)
_TIER_TO_VEO_RES = {"1k": "720p", "2k": "720p", "3k": "1080p", "4k": "4k"}
# Veo 官方支持的宽高比 (仅横竖两种, 其余一律回落 16:9)
_VEO_RATIOS = {"16:9", "9:16"}

# 视频结果下载上限 (字节)。Veo 单条 8s/1080p 约 10~30MB, 4k 更大;
# 给 512MB 上限纯粹是防御异常响应把编排器内存打爆。
_MAX_VIDEO_BYTES = 512 * 1024 * 1024


def _clamp(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _strip_model_prefix(model: str) -> str:
    """``models/gemini-3-flash-preview`` -> ``gemini-3-flash-preview``。

    Google 的 /models 列表返回带 ``models/`` 前缀的资源名, 而端点路径本身已经是
    ``/models/{id}:method``。不剥前缀会拼成 ``/models/models/xxx:generateContent`` (404)。
    BFF 侧落库时已剥一次, 这里再剥一次纯属**防御**: 管理员手填模型名时很容易复制粘贴
    带前缀的版本, 没理由让用户吃一个 404。
    """
    m = (model or "").strip()
    return m[len("models/"):] if m.startswith("models/") else m


def _split_data_uri(uri: str) -> tuple[str, str] | None:
    """``data:image/png;base64,xxxx`` -> ``("image/png", "xxxx")``; 非法返回 None。"""
    m = re.match(r"^data:([^;,]+);base64,(.+)$", uri or "", re.DOTALL)
    if not m:
        return None
    mime = m.group(1).strip() or "image/png"
    body = m.group(2)
    # 补齐 base64 padding (前端/中转有时会截掉尾部 '=')
    pad = (-len(body)) % 4
    return mime, body + ("=" * pad)


def _classify_gemini_error(status: int, body: Any, what: str) -> tuple[str, str]:
    """把 Google 错误归类为 ``(friendly_msg, technical)``。

    - friendly_msg: 给前端 toast 的简短中文 (≤ 40 字), 且必须**可操作**;
    - technical:    完整原文, 仅进 logger。

    优先读 ``error.status`` 枚举而非裸 HTTP code —— Google 同一个 429 既可能是
    "免费额度用尽(需开通计费)" 也可能是 "每分钟限流(等一下就好)", 光看数字给不出
    正确建议。message 里含 "billing"/"quota" 时倾向前者。
    """
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        err = {}
    gstatus = str(err.get("status") or "").upper()
    msg = str(err.get("message") or "")
    code = err.get("code") or status
    technical = f"http={status} status={gstatus or '-'} code={code} msg={msg}"

    if gstatus == "RESOURCE_EXHAUSTED" or status == 429:
        # 用户当前 key 就在这个分支 (免费额度对图像/视频为 0)。
        friendly = "Gemini 配额已用尽，请在 Google AI Studio 开通计费或稍后重试"
        return friendly, technical
    if gstatus in ("UNAUTHENTICATED", "PERMISSION_DENIED") or status in (401, 403):
        return "Gemini 鉴权失败，请检查 API Key 是否有效/已启用", technical
    if gstatus == "NOT_FOUND" or status == 404:
        # Google 会下线旧模型: "no longer available to new users" —— 这不是配置错误,
        # 是模型本身对新账号不可用, 必须提示换模型而不是让人去查 base_url。
        if "no longer available" in msg.lower():
            return "该 Gemini 模型已对新账号下线，请改用较新的模型", technical
        return "Gemini 模型不存在，请检查模型名称", technical
    if gstatus == "INVALID_ARGUMENT" or status == 400:
        return "Gemini 参数错误，请检查提示词/分辨率/参考图格式", technical
    if gstatus in ("UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED") or status // 100 == 5:
        return "Gemini 服务暂不可用，请稍后再试", technical
    return f"Gemini 调用失败（HTTP {status}）", technical


def _raise_for_gemini(resp, what: str) -> dict:
    """统一错误检查: HTTP 非 2xx 或响应体带 error 字段都抛 RuntimeError(友好文案)。"""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = None

    if resp.status_code // 100 != 2:
        friendly, technical = _classify_gemini_error(resp.status_code, body, what)
        raw = ""
        try:
            raw = resp.text[:200]
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[gemini] %s -> %s | technical=%s | body=%s", what, friendly, technical, raw)
        raise RuntimeError(friendly)

    if not isinstance(body, dict):
        raise RuntimeError(f"gemini {what} 响应非 JSON 对象: {_short(getattr(resp, 'text', ''))}")
    # 少数接口 HTTP 200 仍带 error 体
    if isinstance(body.get("error"), dict) and body["error"].get("code"):
        friendly, technical = _classify_gemini_error(resp.status_code, body, what)
        logger.warning("[gemini] %s -> %s | technical=%s", what, friendly, technical)
        raise RuntimeError(friendly)
    return body


def _assert_not_blocked(data: dict, what: str) -> list[dict]:
    """检查安全拦截并返回 candidates[0].content.parts。

    Gemini 被安全策略拦截时是 **HTTP 200 + 空 candidates**(或 finishReason=SAFETY),
    这是最容易写出"静默成功但没结果"的坑。这里把它翻译成明确失败, 让上层
    置 FAILED 并触发退款 —— 用户不为一张空白图付费。
    """
    feedback = data.get("promptFeedback") or {}
    block = feedback.get("blockReason")
    if block:
        logger.warning("[gemini] %s 被提示词安全策略拦截: %s", what, _short(feedback))
        raise RuntimeError(f"内容被 Gemini 安全策略拦截（{block}），请调整提示词")

    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini 未返回任何结果（{what}），请调整提示词后重试")

    cand = candidates[0] or {}
    finish = str(cand.get("finishReason") or "").upper()
    if finish in ("SAFETY", "IMAGE_SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        logger.warning("[gemini] %s finishReason=%s", what, finish)
        raise RuntimeError(f"内容被 Gemini 安全策略拦截（{finish}），请调整提示词")
    if finish == "RECITATION":
        raise RuntimeError("Gemini 因疑似复述受版权保护内容而中止，请调整提示词")

    return ((cand.get("content") or {}).get("parts")) or []


def _map_usage(data: dict) -> dict:
    """usageMetadata -> 系统内部统一的 token 用量结构。"""
    u = data.get("usageMetadata") or {}
    if not isinstance(u, dict):
        return {}
    out = {
        "input_tokens": u.get("promptTokenCount"),
        "output_tokens": u.get("candidatesTokenCount"),
        "total_tokens": u.get("totalTokenCount"),
    }
    return {k: v for k, v in out.items() if v is not None}


@register_provider("vendor-native", "gemini")
class GeminiAdapter(BaseProviderAdapter):
    """Google Gemini 原生适配器: 文本(generateContent) / 图像(inlineData 或 Imagen predict) / 视频(Veo LRO)。

    完成模式声明为 POLL —— 视频走句柄轮询; 文本/图像在 submit 里直接
    ``SubmitOutcome(sync=True)`` 返回 (与 MiniMax / Volcengine 同构)。
    """

    # Gemini 的参考图一律走 inlineData(base64), 不需要公网可达地址 ——
    # 这天然规避了"隧道失效 -> 参考图全挂"那条故障链 (见 agnes_provider 的 PublicUrlStrategy)。
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
    def _root(self) -> str:
        """返回 API 根 (含 /v1beta), 容忍管理员填写 ``.../v1beta`` 或裸域名两种形态。"""
        base = (self.base_url or "").rstrip("/")
        if not base:
            base = "https://generativelanguage.googleapis.com"
        # 已带版本段就原样用 (允许将来切 /v1); 否则补默认 /v1beta。
        if re.search(r"/v\d[\w.]*$", base):
            return base
        return f"{base}/v1beta"

    def _url(self, path: str) -> str:
        return f"{self._root()}{path}"

    def _model_url(self, method: str) -> str:
        return self._url(f"/models/{_strip_model_prefix(self.model_name)}:{method}")

    def _headers(self) -> dict:
        # Google 原生 API 用 x-goog-api-key; 不要写成 Authorization: Bearer
        # (那是 /v1beta/openai/* 兼容层的约定, 两者不通用)。
        return {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    # ── 类型分发 ────────────────────────────────────────────────
    def _kind(self, req: dict) -> str:
        """确定实际端点族 (image / video / text)。前端声明优先, 回退按模型名推断。"""
        t = (req.get("type") or "").lower()
        if t in ("image", "img"):
            return "image"
        if t in ("video", "vid"):
            return "video"
        if t in ("text", "chat"):
            return "text"
        m = _strip_model_prefix(self.model_name)
        if _VIDEO_MODEL_RE.search(m):
            return "video"
        if _IMAGEN_MODEL_RE.search(m) or _IMAGE_MODEL_RE.search(m):
            return "image"
        return "text"

    async def submit(self, req: dict) -> "SubmitOutcome":
        if not self.api_key:
            raise RuntimeError("Gemini 未配置 API Key，请在管理后台补全")
        kind = self._kind(req)
        if kind == "image":
            return SubmitOutcome(sync=True, result=await self._gen_image(req))
        if kind == "video":
            return await self._submit_video(req)
        return SubmitOutcome(sync=True, result=await self._gen_text(req))

    # ── 字段映射辅助 ────────────────────────────────────────────
    @staticmethod
    def _map_ratio(ratio: str | None) -> str | None:
        r = (ratio or "").strip()
        return r if r in _GEMINI_RATIOS else None

    @staticmethod
    def _map_image_size(tier: str | None) -> str | None:
        t = (tier or "").upper()
        if t in _GEMINI_IMAGE_SIZES:
            return t
        # 3K 不在 Gemini 枚举内, 就近下取到 2K, 免得整单 400。
        return "2K" if t == "3K" else None

    @staticmethod
    def _map_veo_resolution(tier: str | None) -> str:
        t = (tier or "").lower()
        if t in _VEO_RESOLUTIONS:
            return t
        return _TIER_TO_VEO_RES.get(t, "720p")

    @staticmethod
    def _map_veo_ratio(ratio: str | None) -> str:
        r = (ratio or "").strip()
        return r if r in _VEO_RATIOS else "16:9"

    @staticmethod
    def _inline_part(data_uri: str) -> dict | None:
        """data URI -> Gemini ``{inlineData:{mimeType,data}}`` part。"""
        parsed = _split_data_uri(data_uri)
        if not parsed:
            return None
        mime, b64 = parsed
        return {"inlineData": {"mimeType": mime, "data": b64}}

    def _ref_parts(self, refs: list[str]) -> list[dict]:
        """把参考图列表转成 Gemini parts, 丢弃无法内联的项 (并告警, 不静默)。"""
        parts: list[dict] = []
        for r in refs:
            part = self._inline_part(r)
            if part:
                parts.append(part)
            else:
                # 走到这里说明 Base64InlineStrategy 没能把它转成 data URI
                # (典型: 公网 http 图片被原样保留)。Gemini 不接受远端 URL, 只能丢弃。
                logger.warning("[gemini] 参考图无法内联为 base64, 已丢弃: %s", (r or "")[:80])
        return parts

    # ── 文本 (generateContent) ─────────────────────────────────
    async def _gen_text(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        p = req.get("params") or {}
        gen_cfg: dict[str, Any] = {
            "maxOutputTokens": _clamp(p.get("max_tokens") or 8192, 256, 65536, 8192),
        }
        if p.get("temperature") is not None:
            try:
                gen_cfg["temperature"] = float(p["temperature"])
            except (TypeError, ValueError):
                pass
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": req.get("prompt") or ""}]}],
            "generationConfig": gen_cfg,
        }
        if p.get("system"):
            payload["systemInstruction"] = {"parts": [{"text": str(p["system"])}]}

        resp = await _apost_with_retry(
            get_client(), self._model_url("generateContent"), payload, self._headers(),
            httpx.Timeout(300, connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_gemini(resp, "text")
        parts = _assert_not_blocked(data, "text")
        # ⚠️ 过滤 thought 片段: Gemini 3 思考模型把思维摘要也放在 parts 里,
        # 混进正文会让用户看到一堆内部推理。
        text = "".join(
            str(pt.get("text") or "")
            for pt in parts
            if isinstance(pt, dict) and not pt.get("thought") and pt.get("text")
        )
        if not text.strip():
            raise RuntimeError(f"Gemini 文本返回空内容: {_short(data)}")
        return GenerationResult(
            url="", provider=self.provider_name, raw={}, text=text, usage=_map_usage(data),
        )

    # ── 图像 ────────────────────────────────────────────────────
    async def _gen_image(self, req: dict) -> GenerationResult:
        model = _strip_model_prefix(self.model_name)
        if _IMAGEN_MODEL_RE.search(model):
            return await self._gen_image_imagen(req)
        return await self._gen_image_generate_content(req)

    def _build_image_payload(self, req: dict) -> dict:
        """Gemini Image (nano-banana 系) 的 generateContent 请求体。"""
        norm = normalize_image_params(req)
        refs = self.ref_strategy.resolve(norm.reference_images, provider=self)

        parts: list[dict] = [{"text": norm.prompt}]
        ref_parts = self._ref_parts(refs)
        if ref_parts:
            parts.extend(ref_parts)
            logger.info("[gemini] image refs=%d (img2img via inlineData)", len(ref_parts))

        image_cfg: dict[str, Any] = {}
        ratio = self._map_ratio(norm.aspect_ratio)
        if ratio:
            image_cfg["aspectRatio"] = ratio
        size = self._map_image_size(norm.size_tier)
        if size:
            image_cfg["imageSize"] = size

        gen_cfg: dict[str, Any] = {"responseModalities": ["IMAGE"]}
        if image_cfg:
            gen_cfg["imageConfig"] = image_cfg

        # n>1: Gemini 图像模型只出单图, candidateCount>1 会直接 400。
        # 与其把整单打挂, 不如出 1 张 + 明确告警 (前端拿到 1 张总比 0 张强)。
        if norm.n > 1:
            logger.warning(
                "[gemini] 模型 %s 单次仅出 1 张图, 已忽略 n=%d (如需多图请多次生成)",
                _strip_model_prefix(self.model_name), norm.n,
            )
        return {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen_cfg}

    async def _gen_image_generate_content(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        payload = self._build_image_payload(req)
        resp = await _apost_with_retry(
            get_client(), self._model_url("generateContent"), payload, self._headers(),
            httpx.Timeout(settings.provider_image_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=settings.provider_image_retry_attempts,
        )
        data = _raise_for_gemini(resp, "image")
        parts = _assert_not_blocked(data, "image")

        blobs: list[tuple[str, str]] = []  # (mime, base64)
        for pt in parts:
            inline = (pt or {}).get("inlineData") or (pt or {}).get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                blobs.append((inline.get("mimeType") or inline.get("mime_type") or "image/png",
                              inline["data"]))
        if not blobs:
            # 模型可能只回了文字解释 (例如拒绝执行), 把它带进错误里, 便于定位。
            note = "".join(str(pt.get("text") or "") for pt in parts if isinstance(pt, dict))[:160]
            raise RuntimeError(f"Gemini 未返回图片{('：' + note) if note else ''}")

        urls = self._store_blobs(blobs, "image", req)
        return GenerationResult(
            url=urls[0], urls=urls, provider=self.provider_name,
            raw={"model": _strip_model_prefix(self.model_name)}, usage=_map_usage(data),
        )

    async def _gen_image_imagen(self, req: dict) -> GenerationResult:
        """Imagen 系: ``:predict`` 协议 (与 generateContent 完全不同的请求/响应形状)。"""
        from app.async_core.engine import get_client

        norm = normalize_image_params(req)
        params: dict[str, Any] = {"sampleCount": _clamp(norm.n, 1, 4, 1)}
        ratio = self._map_ratio(norm.aspect_ratio)
        if ratio:
            params["aspectRatio"] = ratio
        payload = {"instances": [{"prompt": norm.prompt}], "parameters": params}
        if norm.reference_images:
            # Imagen 的 :predict 是纯文生图, 没有参考图入口 —— 显式告警胜过静默丢弃。
            logger.warning("[gemini] Imagen :predict 不支持参考图, 已忽略 %d 张",
                           len(norm.reference_images))

        resp = await _apost_with_retry(
            get_client(), self._model_url("predict"), payload, self._headers(),
            httpx.Timeout(settings.provider_image_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=settings.provider_image_retry_attempts,
        )
        data = _raise_for_gemini(resp, "imagen")
        preds = data.get("predictions") or []
        blobs = [
            (pr.get("mimeType") or "image/png", pr["bytesBase64Encoded"])
            for pr in preds
            if isinstance(pr, dict) and pr.get("bytesBase64Encoded")
        ]
        if not blobs:
            raise RuntimeError(f"Imagen 未返回图片: {_short(data)}")
        urls = self._store_blobs(blobs, "image", req)
        return GenerationResult(
            url=urls[0], urls=urls, provider=self.provider_name,
            raw={"model": _strip_model_prefix(self.model_name)}, usage={},
        )

    def _store_blobs(self, blobs: list[tuple[str, str]], media_type: str, req: dict) -> list[str]:
        """把 base64 结果落自有对象存储, 返回稳定 URL。

        为什么不直接返回 ``data:image/png;base64,...``:
        dispatcher._rehost 对 data URI 是**跳过**的, 那 1~3MB 的 base64 会原样写进
        jobs.result_json (MySQL TEXT 上限 65535) —— 一张图就能把这一列撑爆。
        自己落存储是唯一正确解。
        """
        from app import storage

        user_id = req.get("user_id") or 0
        urls: list[str] = []
        for mime, b64 in blobs:
            try:
                raw = base64.b64decode(b64)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[gemini] 结果 base64 解码失败, 跳过一项: %s", exc)
                continue
            urls.append(storage.store_bytes(raw, media_type, user_id=user_id, content_type=mime))
            logger.info("[gemini] %s 已落自有存储 (%d bytes, %s)", media_type, len(raw), mime)
        if not urls:
            raise RuntimeError("Gemini 结果解码失败，未能保存任何媒体")
        return urls

    # ── 视频 (Veo: predictLongRunning + Operation 轮询) ──────────
    def _build_video_payload(self, req: dict) -> dict:
        p = req.get("params") or {}
        instance: dict[str, Any] = {"prompt": req.get("prompt") or ""}

        refs = self.ref_strategy.resolve(p.get("reference_images") or [], provider=self)
        ref_parts = self._ref_parts(refs)
        if ref_parts:
            # 图生视频: 首张作首帧 image; 若给了两张且显式声明 keyframes, 第二张作 lastFrame。
            instance["image"] = ref_parts[0]
            mode = str(p.get("gen_mode") or p.get("mode") or "").lower()
            if len(ref_parts) > 1 and mode == "keyframes":
                instance["lastFrame"] = ref_parts[1]
                extra = len(ref_parts) - 2
            else:
                extra = len(ref_parts) - 1
            if extra > 0:
                logger.warning("[gemini] Veo 仅用首帧%s, 丢弃其余 %d 张参考图",
                               "/尾帧" if "lastFrame" in instance else "", extra)

        params: dict[str, Any] = {
            "aspectRatio": self._map_veo_ratio(p.get("aspectRatio")),
            "resolution": self._map_veo_resolution(p.get("resolution") or p.get("size")),
        }
        if p.get("negative_prompt"):
            params["negativePrompt"] = str(p["negative_prompt"])
        return {"instances": [instance], "parameters": params}

    async def _submit_video(self, req: dict) -> "SubmitOutcome":
        from app.async_core.engine import get_client

        model = _strip_model_prefix(self.model_name)
        if _OMNI_MODEL_RE.search(model):
            # Omni 用 generateContent 直出视频, 是另一套协议(且当前为 preview)。
            # 明确报错 > 用 Veo 的 LRO 去打它然后吃一个看不懂的 404。
            raise RuntimeError(
                f"模型 {model} 走 Gemini Omni 协议，当前适配器仅支持 Veo 系列视频模型，"
                f"请改用 veo-* 模型"
            )

        payload = self._build_video_payload(req)
        resp = await _apost_with_retry(
            get_client(), self._model_url("predictLongRunning"), payload, self._headers(),
            httpx.Timeout(settings.provider_video_submit_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_gemini(resp, "video submit")
        op_name = str(data.get("name") or "").strip()
        if not op_name:
            raise RuntimeError(f"Veo 未返回 operation name: {_short(data)}")
        logger.info("[gemini] veo submitted operation=%s model=%s", op_name, model)
        return SubmitOutcome(sync=False, handle=AsyncHandle(
            job_id=req.get("job_id", ""),
            user_id=int(req.get("user_id", 0) or 0),
            provider=self.provider_name,
            completion_mode=CompletionMode.POLL,
            provider_task_id=op_name,
            # operation name 形如 models/veo-.../operations/xxx, 直接挂到 /v1beta 之下。
            status_query=self._url(f"/{op_name.lstrip('/')}"),
        ))

    # ── 状态查询 (Completer 后台线程调用, 同步实现) ─────────────────
    def query_status(self, handle: AsyncHandle) -> PollStatus:
        sq = handle.status_query or ""
        resp = requests.get(
            sq, headers=self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, 60),
            proxies={"http": None, "https": None},
        )
        data = _raise_for_gemini(resp, "video status")

        if not data.get("done"):
            # Google 的 LRO 不给百分比进度, 只有 done 布尔量。
            return PollStatus(normalized=NormalizedStatus.PROCESSING, raw_status="running")

        # done=true 的失败分支: error 是 google.rpc.Status
        err = data.get("error")
        if isinstance(err, dict) and (err.get("message") or err.get("code")):
            friendly, technical = _classify_gemini_error(int(err.get("code") or 500),
                                                         {"error": err}, "video")
            logger.warning("[gemini] veo operation failed | technical=%s", technical)
            return PollStatus(normalized=NormalizedStatus.FAILED, raw_status="failed", error=friendly)

        uri = self._extract_video_uri(data)
        if not uri:
            return PollStatus(
                normalized=NormalizedStatus.FAILED, raw_status="done",
                error=f"Veo 已完成但未返回视频地址: {_short(data)}",
            )
        try:
            stored = self._download_and_store_video(uri, handle.user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[gemini] veo 结果下载/转存失败: %s", exc)
            return PollStatus(normalized=NormalizedStatus.FAILED, raw_status="done",
                              error=f"Veo 视频转存失败: {exc}")
        return PollStatus(normalized=NormalizedStatus.DONE, raw_status="done", result_url=stored)

    @staticmethod
    def _extract_video_uri(data: dict) -> str | None:
        """从 Operation 响应里取视频 URI, 兼容 Google 两代字段命名。

        文档 REST 示例是 ``generatedSamples[].video.uri``, 而 SDK 侧文档/部分响应用
        ``generatedVideos[].video.uri``。两个都试, 免得因为 Google 改字段名就整条链路失效。
        """
        resp_obj = data.get("response") or {}
        gvr = resp_obj.get("generateVideoResponse") or resp_obj
        for key in ("generatedSamples", "generatedVideos", "generated_samples", "generated_videos"):
            samples = gvr.get(key)
            if isinstance(samples, list) and samples:
                video = (samples[0] or {}).get("video") or {}
                uri = video.get("uri") or video.get("url")
                if isinstance(uri, str) and uri.startswith("http"):
                    return uri
        return None

    def _download_and_store_video(self, uri: str, user_id: int) -> str:
        """带鉴权头下载 Veo 结果并落自有存储, 返回稳定 URL。

        ⚠️ 这一步不能交给 dispatcher._rehost —— 它是匿名 GET, 而 Google 的
        files download 端点必须带 ``x-goog-api-key`` (否则 403)。
        """
        from app import storage

        resp = requests.get(
            uri,
            headers={"x-goog-api-key": self.api_key},
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_image_timeout_s),
            allow_redirects=True,   # Google 会 302 到实际存储地址
            stream=True,
            proxies={"http": None, "https": None},
        )
        if resp.status_code // 100 != 2:
            body = ""
            try:
                body = resp.text[:200]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"下载 Veo 视频失败 HTTP {resp.status_code}: {body}")

        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(1 << 20):
            if not chunk:
                continue
            total += len(chunk)
            if total > _MAX_VIDEO_BYTES:
                resp.close()
                raise RuntimeError("Veo 视频超出大小上限，已中止下载")
            chunks.append(chunk)
        resp.close()
        data = b"".join(chunks)
        if not data:
            raise RuntimeError("Veo 视频下载为空")
        content_type = (resp.headers.get("Content-Type") or "video/mp4").split(";")[0].strip()
        if not content_type.startswith("video/"):
            content_type = "video/mp4"
        url = storage.store_bytes(data, "video", user_id=user_id, content_type=content_type)
        logger.info("[gemini] veo 视频已落自有存储 (%d bytes) -> %s", total, url[:100])
        return url
