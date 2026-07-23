"""生成 Worker: 消费 Redis Streams -> 调外部模型 -> 回写状态 -> 发布事件.

失败 -> 置 failed -> 补偿退款 -> 通知 (ARCH D5/D9/D10).
每用户并发上限为软护栏(见 _in_flight); 生产环境替换为 Redis 原子计数器以防单用户打满。
"""
from __future__ import annotations

import json
import threading
import time

from app import db, models
from app.compensation import refund_on_failure
from app.config import settings
from app.llm_router import route
from app.redis_conn import client, publish_event
from services.shared.events import GEN_QUEUE, job_updated, notification

GROUP = "pea-workers"
CONSUMER = "worker-1"
FAST_QUEUE = f"{GEN_QUEUE}:fast"
STREAMS = [GEN_QUEUE, FAST_QUEUE]

_in_flight_lock = threading.Lock()
_in_flight: dict[int, int] = {}
_stop = False


def _enter(user_id: int) -> bool:
    with _in_flight_lock:
        cur = _in_flight.get(user_id, 0)
        if cur >= settings.per_user_concurrency:
            return False
        _in_flight[user_id] = cur + 1
        return True


def _leave(user_id: int) -> None:
    with _in_flight_lock:
        _in_flight[user_id] = max(0, _in_flight.get(user_id, 1) - 1)


def _ensure_group() -> None:
    r = client()
    for stream in STREAMS:
        try:
            r.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except Exception:  # noqa: BLE001  (BUSYGROUP 已存在)
            pass


def _process(job_id: str, payload: dict) -> None:
    user_id = int(payload.get("user_id", 0))
    if not _enter(user_id):
        # 超过每用户并发: 本轮跳过(不 ack), 留给下次调度。生产应走 Redis 令牌桶。
        print(f"[worker] user {user_id} at concurrency cap, defer {job_id}")
        time.sleep(0.5)
        return
    try:
        db.update_job_status(job_id, models.JobStatus.RUNNING.value)
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="running", progress=0.1,
        ))
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="running", progress=0.6,
        ))
        result = route(payload)
        db.update_job_status(
            job_id, models.JobStatus.DONE.value,
            result_json=json.dumps({"url": result.url, "provider": result.provider}, ensure_ascii=False),
            cost_tapies=int(payload.get("cost_tapies", settings.default_cost_tapies)),
        )
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="done", result_url=result.url,
            cost=int(payload.get("cost_tapies", settings.default_cost_tapies)),
        ))
    except Exception as e:  # noqa: BLE001
        db.update_job_status(job_id, models.JobStatus.FAILED.value)
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=payload.get("type", "image"),
            status="failed", error=str(e)[:500],
        ))
        publish_event(notification(
            user_id=user_id, title="生成失败", body=str(e)[:200], level="error",
        ))
        refunded = refund_on_failure(job_id, user_id, int(payload.get("cost_tapies", 0)))
        if refunded:
            # 退款成功 -> 状态机 FAILED -> REFUNDED 合法跳转 (原实现永远停在 FAILED, refunded 状态形同虚设)
            try:
                db.update_job_status(job_id, models.JobStatus.REFUNDED.value)
            except Exception as e:  # noqa: BLE001
                print(f"[worker] mark refunded failed {job_id}: {e}")
    finally:
        _leave(user_id)


def run_once() -> None:
    r = client()
    resp = r.xreadgroup(
        GROUP, CONSUMER,
        {GEN_QUEUE: ">", FAST_QUEUE: ">"},
        count=2, block=1000,
    )
    if not resp:
        return
    for _stream, messages in resp:
        for msg_id, fields in messages:
            try:
                job_id = fields["job_id"]
                payload = json.loads(fields["payload"])
                _process(job_id, payload)
                r.xack(_stream, GROUP, msg_id)
            except Exception as e:  # noqa: BLE001
                print(f"[worker] bad message {msg_id}: {e}")


def run_forever() -> None:
    _ensure_group()
    print("[worker] started")
    while not _stop:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001
            print(f"[worker] loop error: {e}")
            time.sleep(1)


def start() -> threading.Thread:
    t = threading.Thread(target=run_forever, daemon=True)
    t.start()
    return t
