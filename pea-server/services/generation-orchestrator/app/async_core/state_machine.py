"""任务状态机: 业务相位 + 第三方归一化状态的转换规则."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from app.async_core.types import NormalizedStatus


class JobPhase(str, Enum):
    """generation_task_handles.phase —— 我们的内部调度相位."""
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# 第三方归一化状态 -> 我们的相位
_NORMALIZED_TO_PHASE = {
    NormalizedStatus.PENDING: JobPhase.PROCESSING,
    NormalizedStatus.PROCESSING: JobPhase.PROCESSING,
    NormalizedStatus.DONE: JobPhase.DONE,
    NormalizedStatus.FAILED: JobPhase.FAILED,
}

# 合法相位跃迁
_ALLOWED = {
    JobPhase.SUBMITTED: {JobPhase.PROCESSING, JobPhase.FAILED},
    JobPhase.PROCESSING: {JobPhase.PROCESSING, JobPhase.DONE, JobPhase.FAILED},
    JobPhase.DONE: set(),       # 终态
    JobPhase.FAILED: set(),     # 终态
}


def phase_for(norm: NormalizedStatus) -> JobPhase:
    return _NORMALIZED_TO_PHASE[norm]


def can_transition(frm: JobPhase, to: JobPhase) -> bool:
    """终态不可再变; 其余按白名单."""
    return to in _ALLOWED.get(frm, set())


def next_phase(current: JobPhase, norm: NormalizedStatus) -> Optional[JobPhase]:
    """根据一次状态查询结果, 计算应迁移到的相位 (None 表示非法/忽略)."""
    target = phase_for(norm)
    if can_transition(current, target):
        return target
    return None
