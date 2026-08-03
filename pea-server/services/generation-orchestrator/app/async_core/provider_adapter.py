"""Provider 适配器: 把"规范请求"翻译成第三方真实调用, 并归一化其响应.

Agnes 当前是 poll 模式 (提交拿 task_id, 我们按 /v1/videos/{task_id} 轮询).
未来支持回调的厂商实现 WebhookCapableMixin 即可零改动接入.

本模块为**同步**实现 (与编排器整体线程栈一致, 不引入 asyncio 栈风险);
慢 I/O (图像同步出图 / 视频状态查询) 由 Dispatcher 的线程池与 Completer 的后台线程承载,
消费线程本身永不阻塞 -> 头阻塞消除.
"""
from __future__ import annotations

import abc
import logging
import time
import uuid
from typing import Any

from app.agnes_provider import _swap_host
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
from app.agnes_provider import (
    OpenAICompatibleProvider,
    _extract_video_url,
    _parse_video_status,
)

logger = logging.getLogger(__name__)


class BaseProviderAdapter(abc.ABC):
    """所有 provider 适配器的抽象基类(正式接口 / abc.ABC).

    加新模型 = 写一个子类(实现 capabilities / submit / query_status 三个抽象方法,
    视频参考图解析 resolve_refs 有默认实现, 一般不用重写), 再用 @register_provider
    注册到 PROVIDER_REGISTRY 一行即可, 完全不碰 build_adapter 工厂逻辑。
    """

    # 参考图解析策略 (Strategy): 默认 None = 沿用 resolve_refs 的"转公网 URL"实现。
    # 子类若声明 Base64InlineStrategy 并覆写 resolve_refs, 即可完全跳过公网转存
    # (MiniMax / Anthropic 都直接吃 data URI, 少一整条隧道故障链)。
    ref_strategy: Any = None

    def __init__(self, cfg: dict):
        self.base_url: str = cfg.get("base_url", "")
        self.api_key: str = cfg.get("api_key", "")
        self.model_name: str = cfg.get("model_name", "")
        self.provider_name: str = cfg.get("provider_name") or cfg.get("provider_id") or "provider"
        self.name = self.provider_name
        # 每个 provider 各自的公网参考图基址(per-provider, 替代全局 PEA_EXTERNAL_REF_BASE_URL)。
        # 为空回退到全局 settings.external_ref_base_url。新增模型可带自己的隧道/域名,
        # 从而消除"一个隧道死=全模型挂"的单点故障。
        self.ref_base_url: str = (cfg.get("external_ref_base_url") or settings.external_ref_base_url or "").rstrip("/")

    @property
    @abc.abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """声明本 provider 的能力(完成模式 / 是否接受回调 / 状态查询模板)."""
        ...

    @abc.abstractmethod
    async def submit(self, req: dict) -> "SubmitOutcome":
        """提交任务. 同步模式返回 result; 异步模式返回 AsyncHandle."""
        ...

    @abc.abstractmethod
    def query_status(self, handle: AsyncHandle) -> PollStatus:
        """poll 模式: 查询任务状态 (webhook 模式不需要)."""
        ...

    def resolve_refs(self, refs: list[str]) -> list[str]:
        """把参考图解析为外部模型可下载的 URL(默认实现, 子类可覆写).

        默认复用视频参考图解析逻辑(转存 data URI + per-provider 前缀替换)。
        子类(AgnesAdapter 等)直接继承; 若某模型参考图喂法不同, 覆写即可,
        无需复制函数 —— 这正是"加模型=只传参"的边界。
        """
        from app.agnes_provider import _ensure_http_refs_for_video

        return _ensure_http_refs_for_video(
            refs,
            public_base=(self.ref_base_url or None),
            cdn_base=settings.cdn_base_url,
        )


# ---- Provider 注册表: 加新模型 = 实现类 + 一行 @register_provider ----
# 注册键为 (protocol, vendor) 元组 (方案 A: 协议与厂商解耦):
#   - 协议无关适配器 (OpenAI/Anthropic/mock) 注册为 (protocol, None)
#   - 厂商原生协议注册为 (protocol, vendor), 如 MiniMax 原生 -> ("vendor-native", "minimax")
PROVIDER_REGISTRY: dict[tuple[str, str | None], type["BaseProviderAdapter"]] = {}


def register_provider(protocol: str, vendor: str | None = None):
    """类装饰器: 把适配器登记进 PROVIDER_REGISTRY。

    注册键是 ``(protocol, vendor)`` 二元组, 与「协议族 / 厂商」两个正交维度一一对应::

        @register_provider("openai-compatible")
        class AgnesAdapter(BaseProviderAdapter): ...

        @register_provider("vendor-native", "minimax")
        class MiniMaxAdapter(BaseProviderAdapter): ...

    ``build_adapter`` 路由时先按 (protocol, vendor) 精确匹配, 再按 (protocol, None) 模糊匹配,
    最后回退 openai-compatible。无需修改工厂分支。
    """
    def _deco(cls: type["BaseProviderAdapter"]) -> type["BaseProviderAdapter"]:
        if not (isinstance(cls, type) and issubclass(cls, BaseProviderAdapter)):
            raise TypeError(f"{cls!r} 必须继承 BaseProviderAdapter")
        PROVIDER_REGISTRY[(protocol, vendor)] = cls
        return cls

    return _deco


@register_provider("openai-compatible")
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
            "external_ref_base_url": self.ref_base_url,
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
        fb = None
        if self._real.gateway_base:
            try:
                fb = _swap_host(handle.status_query, self._real.gateway_base)
            except Exception:
                fb = None
        raw = self._real._query_video_status_raw(handle.status_query, fallback_url=fb)
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




_builtin_loaded = False


def _ensure_builtin_providers() -> None:
    """延迟导入 app.providers 包, 触发各适配器的 @register_provider 注册。

    为什么延迟: 适配器模块要 ``from app.async_core.provider_adapter import
    BaseProviderAdapter``, 若本模块顶层反过来 import app.providers 就成环。
    在工厂函数体内导入即可打断, 且只付一次代价 (_builtin_loaded 幂等)。
    """
    global _builtin_loaded
    if _builtin_loaded:
        return
    _builtin_loaded = True
    try:
        import app.providers  # noqa: F401  (import 即注册)

        logger.info("[provider] 内置适配器已注册: %s", sorted(PROVIDER_REGISTRY))
    except Exception as exc:  # noqa: BLE001
        # 不让某个厂商模块的导入错误拖垮整个编排器 —— 已注册的仍可用
        logger.error("[provider] 内置适配器加载失败: %s", exc, exc_info=exc)


def build_adapter(cfg: dict) -> BaseProviderAdapter:
    """工厂: 按 (protocol, vendor) 从 PROVIDER_REGISTRY 解析适配器 (方案 A 多维路由)。

    匹配顺序 (优先级从高到低):
      1. 精确匹配 (protocol, vendor)  —— 如 ("vendor-native", "minimax") -> MiniMaxAdapter
      2. 仅 protocol 匹配 (protocol, None) —— 如 ("openai-compatible", None) -> AgnesAdapter
      3. 回退 openai-compatible (仅通用协议族未知时; vendor-native 缺失实现会直接报错而非回退)

    protocol 字段缺失时回退读 provider_type (向后兼容老数据/老调用方);
    vendor 字段缺失视为 None (仅 vendor-native 协议需要它)。
    """
    _ensure_builtin_providers()
    protocol = (cfg.get("protocol") or cfg.get("provider_type") or "openai-compatible").strip().lower()
    vendor = (cfg.get("vendor") or "").strip().lower() or None

    # 向后兼容: 历史数据里 provider_type 可能直接写成厂商名 (如 'minimax'),
    # 此时规整到 vendor-native + vendor=minimax, 避免静默回退到 openai-compatible。
    if protocol == "minimax":
        protocol, vendor = "vendor-native", "minimax"

    # 厂商原生协议: 必须有该 (vendor) 的专用实现, 否则明确报错, 不允许静默回退。
    if protocol == "vendor-native":
        if not vendor:
            raise ValueError(
                "厂商原生协议(vendor-native)必须指定 vendor (如 minimax); "
                "请在下拉中选择厂商, 或在编排器实现该厂商的原生适配器并 "
                "@register_provider('vendor-native', <vendor>)。"
            )
        cls = PROVIDER_REGISTRY.get((protocol, vendor))
        if cls is None:
            raise ValueError(
                f"厂商 {vendor!r} 的原生协议尚未实现: 未在 PROVIDER_REGISTRY 注册 "
                f"('vendor-native', {vendor!r})。请选择 OpenAI 兼容 / Anthropic 兼容, "
                f"或先为该厂商实现原生适配器。"
            )
        return cls(cfg)

    # 1. 精确匹配 (protocol, vendor)
    cls = PROVIDER_REGISTRY.get((protocol, vendor))
    if cls is not None:
        return cls(cfg)
    # 2. 仅 protocol 匹配 (vendor 不敏感, 如 openai-compatible / anthropic-compatible)
    cls = PROVIDER_REGISTRY.get((protocol, None))
    if cls is not None:
        return cls(cfg)
    # 3. 未知协议族, 回退 openai-compatible
    logger.warning(
        "[provider] 未知 (protocol=%r, vendor=%r), 回退 openai-compatible (已注册: %s)",
        protocol, vendor, sorted(f"{p}+{v}" for (p, v) in PROVIDER_REGISTRY),
    )
    return PROVIDER_REGISTRY.get(("openai-compatible", None), AgnesAdapter)(cfg)
