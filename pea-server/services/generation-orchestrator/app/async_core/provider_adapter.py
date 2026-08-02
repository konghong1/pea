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
PROVIDER_REGISTRY: dict[str, type["BaseProviderAdapter"]] = {}


def register_provider(provider_type: str):
    """类装饰器: 把适配器登记进 PROVIDER_REGISTRY。

    用法::

        @register_provider("replicate")
        class ReplicateAdapter(BaseProviderAdapter):
            ...

    之后 ``build_adapter({"provider_type": "replicate", ...})`` 即返回该适配器,
    无需修改工厂分支。
    """
    def _deco(cls: type["BaseProviderAdapter"]) -> type["BaseProviderAdapter"]:
        if not (isinstance(cls, type) and issubclass(cls, BaseProviderAdapter)):
            raise TypeError(f"{cls!r} 必须继承 BaseProviderAdapter")
        PROVIDER_REGISTRY[provider_type] = cls
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


class MockProvider:
    """本地可跑通的占位 provider: 不调外部, 直接返回确定性占位媒体 URL.

    占位图改为自包含 data-URI SVG, 浏览器可直接渲染, 不依赖对象存储里是否存在该文件。
    (原实现返回 cdn_base_url/mock/<id>.png, 该文件在 minio 中不存在 -> 画廊/画布显示裂图。)
    """

    name = "mock"

    def generate(self, req: dict) -> GenerationResult:
        # 模拟出图耗时
        time.sleep(0.3)
        job_id = req.get("job_id", uuid.uuid4().hex)
        kind = req.get("type")
        # 从参数中获取出图数量
        n = 1
        try:
            n = max(1, min(4, int(req.get("params", {}).get("n", 1))))
        except (TypeError, ValueError):
            n = 1
        # mock 模式也产出占位 usage, 便于无密钥联调时验证 token 计量链路
        usage = {
            "input_tokens": max(1, len(req.get("prompt", "")) // 4),
            "output_tokens": 0,
            "total_tokens": max(1, len(req.get("prompt", "")) // 4),
        }
        if kind == "video":
            url = f"{settings.cdn_base_url}/mock/{job_id}.mp4"
            return GenerationResult(url=url, provider=self.name, usage=usage)
        elif kind == "text":
            return GenerationResult(
                url="", provider=self.name, text=f"[mock] {req.get('prompt', '')[:200]}",
                usage=usage,
            )
        else:
            # 图片生成：支持多张
            urls = [self._placeholder_image(f"{job_id}_{i}", req.get("prompt", "")) for i in range(n)]
            return GenerationResult(
                url=urls[0],
                urls=urls,
                provider=self.name,
                usage=usage,
            )

    @staticmethod
    def _placeholder_image(job_id: str, prompt: str) -> str:
        from urllib.parse import quote

        safe = (prompt or "pea mock").replace("\n", " ")[:48]
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='512' height='512'>"
            "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            "<stop offset='0' stop-color='#1fa2dc'/>"
            "<stop offset='1' stop-color='#8b5cf6'/>"
            "</linearGradient></defs>"
            "<rect width='512' height='512' rx='28' fill='url(#g)'/>"
            "<text x='50%' y='46%' fill='white' font-size='30' font-family='sans-serif' "
            "text-anchor='middle' font-weight='700'>pea 生成预览</text>"
            f"<text x='50%' y='55%' fill='white' font-size='17' font-family='sans-serif' "
            f"text-anchor='middle' opacity='0.9'>{safe}</text>"
            f"<text x='50%' y='92%' fill='white' font-size='13' font-family='sans-serif' "
            f"text-anchor='middle' opacity='0.6'>{job_id[:8]}</text>"
            "</svg>"
        )
        return "data:image/svg+xml;utf8," + quote(svg)


_mock = MockProvider()


@register_provider("mock")
class MockAdapter(BaseProviderAdapter):
    """本地占位 provider: 同步返回一个确定性结果 (联调用的极速路径)."""

    def __init__(self, cfg: dict | None = None) -> None:
        super().__init__(cfg or {"provider_name": "mock"})
        self._mock = _mock

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(completion_mode=CompletionMode.SYNC, accepts_callback=False)

    async def submit(self, req: dict) -> "SubmitOutcome":
        res = self._mock.generate(req)
        return SubmitOutcome(sync=True, result=res)

    def query_status(self, handle: AsyncHandle) -> PollStatus:
        raise NotImplementedError("mock provider is always synchronous")


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
    """工厂: 按 provider_type 从 PROVIDER_REGISTRY 解析适配器; 未知类型回退 OpenAI 兼容。

    加新模型无需改动本函数 —— 只需在其适配器类上加 ``@register_provider("xxx")``,
    并在 ``app/providers/__init__.py`` import 一行。
    """
    _ensure_builtin_providers()
    ptype = (cfg.get("provider_type") or "openai-compatible").strip()
    cls = PROVIDER_REGISTRY.get(ptype)
    if cls is None:
        logger.warning(
            "[provider] 未知 provider_type=%r, 回退 openai-compatible (已注册: %s)",
            ptype, sorted(PROVIDER_REGISTRY),
        )
        cls = PROVIDER_REGISTRY.get("openai-compatible", AgnesAdapter)
    return cls(cfg)
