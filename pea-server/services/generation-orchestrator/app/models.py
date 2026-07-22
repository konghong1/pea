"""生成任务状态机 (queued -> running -> done/failed -> refunded)."""
from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REFUNDED = "refunded"


# 合法转移表 (违反则拒绝)
_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.FAILED},
    JobStatus.RUNNING: {JobStatus.DONE, JobStatus.FAILED},
    JobStatus.FAILED: {JobStatus.REFUNDED},
    JobStatus.DONE: set(),       # 终态
    JobStatus.REFUNDED: set(),   # 终态
}


def can_transition(current: str, target: str) -> bool:
    cur = JobStatus(current)
    tgt = JobStatus(target)
    return tgt in _TRANSITIONS[cur]


def is_terminal(status: str) -> bool:
    return len(_TRANSITIONS[JobStatus(status)]) == 0
