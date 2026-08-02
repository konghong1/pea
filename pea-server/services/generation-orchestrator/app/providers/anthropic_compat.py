"""Anthropic Messages API 兼容适配器 (provider_type = "anthropic-compatible").

适用范围
--------
任何实现了 Anthropic ``POST /v1/messages`` 协议的服务端:
  - Anthropic 官方          base_url = https://api.anthropic.com
  - MiniMax Anthropic 兼容层 base_url = https://api.minimaxi.com/anthropic
  - 各类自建/第三方兼容网关

与 OpenAI 协议的关键差异 (踩过才知道)
------------------------------------
1. **鉴权头不同**: Anthropic 用 ``x-api-key`` 而非 ``Authorization: Bearer``。
   但 MiniMax 的兼容层**两个都要**(只给 x-api-key 会 401)。故本适配器两个都发 ——
   官方端点会忽略多余的 Authorization, 兼容层则两个都能读到, 一套代码通吃。
2. **必须显式带 ``anthropic-version``**, 缺失直接 400。
3. **``max_tokens`` 是必填字段**, 不像 OpenAI 可省略。缺省给 4096。
4. **``system`` 是顶层参数**, 不是 messages 里的一条 role=system。塞进 messages 会 400。
5. **响应是 content 块数组**, 不是 ``choices[0].message.content``:
   ``{"content":[{"type":"thinking",...},{"type":"text","text":"..."}]}``
   —— 只能拼接 ``type=="text"`` 的块; thinking 块是推理链, 不该给终端用户看。
6. **usage 字段名不同**: ``{input_tokens, output_tokens}``, 没有 total。

多模态: 支持把参考图作为视觉输入 (``{"type":"image","source":{...}}``), data URI
自动拆成 ``base64`` source, 公网 URL 走 ``url`` source —— 因此"图片"在本协议下
是作为**输入**被理解, 而非生成 (Anthropic Messages 协议本身不产图)。
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.agnes_provider import _apost_with_retry, _short
from app.async_core.provider_adapter import BaseProviderAdapter, register_provider
from app.async_core.types import (
    AsyncHandle,
    CompletionMode,
    GenerationResult,
    PollStatus,
    ProviderCapabilities,
    SubmitOutcome,
)
from app.config import settings
from app.param_adapters import Base64InlineStrategy

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "2023-06-01"

_DATA_URI_RE = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$", re.DOTALL)
# Anthropic 官方支持的图片 MIME 白名单; 其余一律按 image/png 上送避免 400
_ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _messages_url(base_url: str) -> str:
    """推导 Messages 端点。

    - base 已含 ``/anthropic``            -> {base}/v1/messages
    - base 是 minimax 域名但没带 /anthropic -> {base}/anthropic/v1/messages (自动补)
    - 其余 (官方 / 自建)                   -> {base}/v1/messages
    末尾已经是 /v1 时不重复拼。
    """
    base = (base_url or "").rstrip("/")
    if base.endswith("/v1/messages"):
        return base
    if base.endswith("/v1"):
        return f"{base}/messages"
    if "/anthropic" in base:
        return f"{base}/v1/messages"
    if "minimax" in base.lower():
        return f"{base}/anthropic/v1/messages"
    return f"{base}/v1/messages"


def _image_block(ref: str) -> dict | None:
    """把一张参考图转成 Anthropic 视觉内容块。无法识别返回 None。"""
    m = _DATA_URI_RE.match(ref or "")
    if m:
        mime = m.group("mime").lower()
        if mime not in _ALLOWED_IMAGE_MIME:
            logger.warning("[anthropic] 不支持的图片 MIME=%s, 按 image/png 上送", mime)
            mime = "image/png"
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": m.group("data")},
        }
    if isinstance(ref, str) and ref.startswith("http"):
        return {"type": "image", "source": {"type": "url", "url": ref}}
    return None


def _raise_for_anthropic(resp, what: str) -> dict:
    """Anthropic 错误语义: 真实 HTTP 码 + ``{"type":"error","error":{type,message}}``。"""
    if resp.status_code // 100 != 2:
        detail = ""
        try:
            body = resp.json()
            err = (body or {}).get("error") or {}
            detail = err.get("message") or _short(body, 200)
        except Exception:  # noqa: BLE001
            try:
                detail = resp.text[:200]
            except Exception:  # noqa: BLE001
                detail = ""
        if detail.lstrip().startswith(("<!DOCTYPE", "<!doctype", "<html")):
            reason = getattr(resp, "reason_phrase", None) or "upstream error"
            raise RuntimeError(f"anthropic {what} HTTP {resp.status_code}: {reason}")
        raise RuntimeError(f"anthropic {what} HTTP {resp.status_code}: {detail}")
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"anthropic {what} 响应非 JSON: {_short(getattr(resp, 'text', ''))}") from exc
    if isinstance(data, dict) and data.get("type") == "error":
        err = data.get("error") or {}
        raise RuntimeError(f"anthropic {what} error: {err.get('message') or _short(err)}")
    return data


@register_provider("anthropic-compatible")
class AnthropicCompatAdapter(BaseProviderAdapter):
    """Anthropic Messages 协议适配器 (纯同步 SYNC 模式, 无异步任务句柄)。"""

    ref_strategy = Base64InlineStrategy()

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            completion_mode=CompletionMode.SYNC,
            accepts_callback=False,
        )

    def resolve_refs(self, refs: list[str]) -> list[str]:
        """覆写: 视觉输入内联 base64, 不做公网转存。"""
        return self.ref_strategy.resolve(refs, provider=self)

    def _headers(self) -> dict:
        return {
            # 官方鉴权头
            "x-api-key": self.api_key,
            # MiniMax 兼容层额外要求 Bearer; 官方会忽略, 两个都发最稳
            "Authorization": f"Bearer {self.api_key}",
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    def _build_payload(self, req: dict) -> dict:
        p = req.get("params") or {}
        blocks: list[dict] = []

        # 视觉输入在前、文本在后 —— Anthropic 官方建议的顺序, 图文关联更准
        refs = self.ref_strategy.resolve(p.get("reference_images") or [], provider=self)
        for r in refs[:8]:
            blk = _image_block(r)
            if blk:
                blocks.append(blk)
            else:
                logger.warning("[anthropic] 丢弃无法识别的参考图: %s", (r or "")[:60])
        blocks.append({"type": "text", "text": req.get("prompt") or ""})

        payload: dict[str, Any] = {
            "model": self.model_name,
            # max_tokens 在 Anthropic 协议里是**必填**, 缺失直接 400。
            # 下限抬到 1024: 推理模型给太小会把预算全烧在 thinking 块, 正文为空。
            "max_tokens": max(1024, min(int(p.get("max_tokens") or 4096), 1_000_000)),
            "messages": [{"role": "user", "content": blocks}],
        }
        # system 是顶层参数, 不能塞进 messages
        if p.get("system"):
            payload["system"] = str(p["system"])
        if p.get("temperature") is not None:
            payload["temperature"] = float(p["temperature"])
        if p.get("top_p") is not None:
            payload["top_p"] = float(p["top_p"])
        if p.get("stop_sequences"):
            payload["stop_sequences"] = list(p["stop_sequences"])[:8]
        if p.get("thinking_budget"):
            # 扩展思考: 官方形状 {"type":"enabled","budget_tokens":N}
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": int(p["thinking_budget"]),
            }
        return payload

    async def submit(self, req: dict) -> "SubmitOutcome":
        kind = (req.get("type") or "text").lower()
        if kind in ("image", "video", "audio"):
            # 明确报错优于静默返回空结果 —— 让管理员一眼看出模型配错了族
            raise RuntimeError(
                f"anthropic-compatible 协议不产出 {kind}; 该 provider 仅支持文本/视觉理解。"
                f"请把 {kind} 模型挂到 minimax / openai-compatible 提供商下。"
            )
        return SubmitOutcome(sync=True, result=await self._gen_text(req))

    async def _gen_text(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        payload = self._build_payload(req)
        url = _messages_url(self.base_url)
        resp = await _apost_with_retry(
            get_client(), url, payload, self._headers(),
            httpx.Timeout(300, connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_anthropic(resp, "messages")

        # 响应是 content 块数组: 只取 text 块; thinking 块是推理链, 不外露
        parts: list[str] = []
        thinking_chars = 0
        for blk in (data.get("content") or []):
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "text" and isinstance(blk.get("text"), str):
                parts.append(blk["text"])
            elif blk.get("type") == "thinking":
                thinking_chars += len(str(blk.get("thinking") or ""))
        if not parts:
            # 推理模型的典型翻车: max_tokens 被扩展思考吃光, 只回了 thinking 块。
            # 给出能直接定位的错误, 而不是含糊的 "无 text 块"。
            if thinking_chars:
                raise RuntimeError(
                    f"anthropic messages 正文为空: {self.model_name} 的扩展思考消耗了全部 "
                    f"max_tokens={payload['max_tokens']} (thinking {thinking_chars} 字符, "
                    f"stop_reason={data.get('stop_reason')})。请调大 max_tokens。"
                )
            raise RuntimeError(f"anthropic messages 无 text 块: {_short(data)}")
        if thinking_chars:
            logger.info("[anthropic] 已剥离 thinking 块 (%d 字符)", thinking_chars)

        u = data.get("usage") or {}
        it = int(u.get("input_tokens") or 0)
        ot = int(u.get("output_tokens") or 0)
        return GenerationResult(
            url="", provider=self.provider_name, text="".join(parts),
            raw={"id": data.get("id"), "stop_reason": data.get("stop_reason")},
            usage={"input_tokens": it, "output_tokens": ot, "total_tokens": it + ot},
        )

    def query_status(self, handle: AsyncHandle) -> PollStatus:
        raise NotImplementedError("anthropic-compatible 为同步协议, 不产生异步句柄")
