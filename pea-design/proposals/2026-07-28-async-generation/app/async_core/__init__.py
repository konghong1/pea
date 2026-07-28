"""异步完成层 (async completion core).

把"任务存活期"与"线程存活期"彻底解耦:
- Dispatcher 只做毫秒级提交并立即 ACK;
- 长任务(视频渲染)的等待移到 Completer 的 asyncio 事件循环, 或第三方 webhook 推送;
- 统一兼容 sync / poll / webhook 三种完成模式.
"""
from app.async_core.types import (
    AsyncHandle,
    CompletionMode,
    NormalizedStatus,
    PollStatus,
    ProviderCapabilities,
    SubmitResult,
)
from app.async_core.provider_adapter import (
    AgnesAdapter,
    BaseProviderAdapter,
    WebhookCapableMixin,
)
from app.async_core.backoff import next_interval
from app.async_core.state_machine import JobPhase, can_transition
from app.async_core.dispatcher import submit_job
from app.async_core.completer import completer_loop
from app.async_core.webhook import router as webhook_router

__all__ = [
    "AsyncHandle",
    "CompletionMode",
    "NormalizedStatus",
    "PollStatus",
    "ProviderCapabilities",
    "SubmitResult",
    "AgnesAdapter",
    "BaseProviderAdapter",
    "WebhookCapableMixin",
    "next_interval",
    "JobPhase",
    "can_transition",
    "submit_job",
    "completer_loop",
    "webhook_router",
]
