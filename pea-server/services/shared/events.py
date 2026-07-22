"""pea Creative OS — 跨服务事件契约 (Python 镜像).

与 services/shared/events.ts 完全一致。修改任一侧必须同步另一侧。
事件经 Redis 频道 `pea:events` 发布, 由 BFF 订阅并转发给前端 WebSocket。
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union

JobType = Literal["image", "video", "text"]
JobStatus = Literal["queued", "running", "done", "failed", "refunded"]


class EventKind(str, Enum):
    JOB_UPDATED = "job.updated"
    BALANCE_CHANGED = "balance.changed"
    NOTIFICATION = "notification"


EVENTS_CHANNEL = "pea:events"
GEN_QUEUE = "pea:gen:queue"


def job_updated(
    *,
    job_id: str,
    user_id: int,
    type: str,
    status: str,
    progress: Optional[float] = None,
    result_url: Optional[str] = None,
    error: Optional[str] = None,
    cost: Optional[int] = None,
) -> dict:
    return {
        "kind": EventKind.JOB_UPDATED.value,
        "jobId": job_id,
        "userId": user_id,
        "type": type,
        "status": status,
        "progress": progress,
        "resultUrl": result_url,
        "error": error,
        "cost": cost,
        "ts": __import__("time").time_ns() // 1_000_000,
    }


def balance_changed(
    *, user_id: int, balance: int, delta: int,
    reason: Literal["preauth", "confirm", "refund"],
) -> dict:
    return {
        "kind": EventKind.BALANCE_CHANGED.value,
        "userId": user_id,
        "balance": balance,
        "delta": delta,
        "reason": reason,
        "ts": __import__("time").time_ns() // 1_000_000,
    }


def notification(
    *, user_id: int, title: str, body: str,
    level: Literal["info", "success", "warning", "error"] = "info",
) -> dict:
    return {
        "kind": EventKind.NOTIFICATION.value,
        "userId": user_id,
        "title": title,
        "body": body,
        "level": level,
        "ts": __import__("time").time_ns() // 1_000_000,
    }
