"""异步完成层: 核心类型定义."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class CompletionMode(str, Enum):
    """第三方任务的完成契约."""
    SYNC = "sync"        # 同步返回结果 (部分图像/文本接口)
    POLL = "poll"        # 提交后给状态查询地址, 我们轮询 (Agnes 当前走这条)
    WEBHOOK = "webhook"  # 支持 callback_url, 第三方主动回调


class NormalizedStatus(str, Enum):
    """第三方原始状态归一化, 供状态机内部判定."""
    PENDING = "pending"        # queued
    PROCESSING = "processing"  # in_progress / running
    DONE = "done"              # completed / succeeded
    FAILED = "failed"          # failed / error / cancelled


@dataclass
class PollStatus:
    """一次状态查询的归一化结果."""
    normalized: NormalizedStatus
    raw_status: str
    progress: Optional[int] = None
    result_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ProviderCapabilities:
    """声明式契约: 这个 provider 怎么才算"做完"."""
    completion_mode: CompletionMode
    accepts_callback: bool = False
    status_query_template: Optional[str] = None
    webhook_task_field: str = "task_id"
    status_parser: Optional[Callable[[dict], PollStatus]] = None


@dataclass
class SubmitOutcome:
    """submit() 的返回.

    - sync=True : result 直接有值, handle=None (图像/文本直出)
    - sync=False: handle 有值 (含 task_id + 状态查询), result=None (视频异步)
    """
    sync: bool
    result: Any = None
    handle: Optional["AsyncHandle"] = None


@dataclass
class AsyncHandle:
    """第三方异步任务的持久化句柄 (落 generation_task_handles)."""
    job_id: str
    user_id: int = 0
    provider: str = ""
    completion_mode: CompletionMode = CompletionMode.POLL
    provider_task_id: Optional[str] = None
    provider_video_id: Optional[str] = None
    status_query: Optional[str] = None      # 渲染后的完整状态查询 URL
    raw_status: Optional[str] = None
    progress: Optional[int] = None
    poll_attempts: int = 0
    webhook_received_at: Optional[float] = None
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)
