"""Redis 连接: 生成队列(Redis Streams) + 事件发布/订阅."""
from __future__ import annotations

import json
from typing import Any

import redis

from app.config import settings
from services.shared.events import EVENTS_CHANNEL, GEN_QUEUE

_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def client() -> redis.Redis:
    return _client


def publish_event(event: dict[str, Any]) -> None:
    """发布跨服务事件 (BFF 订阅)."""
    _client.publish(EVENTS_CHANNEL, json.dumps(event, ensure_ascii=False))


def enqueue_job(job_id: str, payload: dict[str, Any], priority: str = "normal") -> None:
    """将生成任务压入 Redis Streams. priority=fast 进极速队列, 否则普通队列."""
    stream = f"{GEN_QUEUE}:{priority}" if priority == "fast" else GEN_QUEUE
    _client.xadd(
        stream,
        {"job_id": job_id, "payload": json.dumps(payload, ensure_ascii=False)},
    )
