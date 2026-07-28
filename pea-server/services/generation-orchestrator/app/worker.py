"""生成 Worker: 消费 Redis Streams -> 调 Dispatcher 快提交 -> ACK.

架构 (资深复核):
- 消费线程只做"毫秒级提交 + ACK", 不等待第三方渲染 -> 头阻塞消除.
- 长任务等待由 Dispatcher 线程池 (同步出图) 与 Completer 后台回路 (视频轮询) 承载.
- 每用户并发上限改由 Redis 原子计数 (async_core.concurrency) 统一管控.
"""
from __future__ import annotations

import json
import threading
import time

from app.async_core.dispatcher import dispatch, finalize_job
from app.config import settings
from app.redis_conn import client, publish_event
from services.shared.events import GEN_QUEUE

GROUP = "pea-workers"
CONSUMER = "worker-1"
FAST_QUEUE = f"{GEN_QUEUE}:fast"
STREAMS = [GEN_QUEUE, FAST_QUEUE]
_stop = False


def _ensure_group() -> None:
    r = client()
    for stream in STREAMS:
        try:
            r.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except Exception:  # noqa: BLE001  (BUSYGROUP 已存在)
            pass


def _process(job_id: str, payload: dict) -> bool:
    """消费线程入口: 调 Dispatcher. 始终返回 True (ACK), 异常由兜底判失败."""
    try:
        dispatch(job_id, payload)
        return True
    except Exception as e:  # noqa: BLE001
        # 兜底: 任何异常都判失败, 避免消息无限卡 pending 拖垮队列
        print(f"[worker] dispatch crashed job={job_id}: {e}")
        try:
            user_id = int(payload.get("user_id", 0) or 0)
            finalize_job(job_id, user_id, payload.get("type", "image"), False,
                        error=f"worker dispatch crash: {e}")
        except Exception as e2:  # noqa: BLE001
            print(f"[worker] fallback finalize failed job={job_id}: {e2}")
        return True


def run_once() -> None:
    r = client()
    resp = r.xreadgroup(
        GROUP, CONSUMER,
        {GEN_QUEUE: ">", FAST_QUEUE: ">"},
        count=2, block=200,
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


def _ensure_public_policy_safe() -> None:
    # 后台尽力设置 gen/ 公开读策略(幂等, 不阻塞生成热路径)
    try:
        from app import storage

        storage.ensure_public_policy()
    except Exception as e:  # noqa: BLE001
        print(f"[worker] ensure_public_policy failed: {e}")


def run_forever() -> None:
    _ensure_group()
    threading.Thread(target=_ensure_public_policy_safe, daemon=True).start()
    print("[worker] started")
    while not _stop:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001
            print(f"[worker] loop error: {e}")
            time.sleep(1)


def start() -> threading.Thread:
    t = threading.Thread(target=run_forever, daemon=True, name="worker")
    t.start()
    return t
