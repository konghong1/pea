"""Completer: 后台线程轮询回路 + webhook 漏触发兜底 (Safety Net).

单线程调度 + 线程池并发查状态: 每 tick 只处理"到点(next_poll_at)的那批",
用线程池并发 GET 状态; 生成期间除"到点那一下 GET"外不占服务端资源.
崩溃安全: 句柄状态在 DB, 进程重启后 claim_due_handles 自动续跑; 多副本靠
claimed_by 乐观锁 + 过期回收防双轮询.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.async_core.backoff import next_interval
from app.async_core.db_async import claim_due_handles, load_provider_cfg, update_handle_status
from app.async_core.dispatcher import finalize_job
from app.async_core.provider_adapter import build_adapter
from app.async_core.types import AsyncHandle, NormalizedStatus
from app.config import settings

logger = logging.getLogger(__name__)

_stop = False
_executor = ThreadPoolExecutor(max_workers=settings.completer_batch, thread_name_prefix="completer")


def stop() -> None:
    global _stop
    _stop = True


def _process_one(row: dict) -> None:
    job_id = row["job_id"]
    user_id = int(row.get("user_id", 0) or 0)
    provider = row["provider"]
    mode = row["completion_mode"]
    raw = row.get("raw_status")
    progress = row.get("progress")
    attempts = int(row.get("poll_attempts", 0) or 0)
    created = row.get("created_at")
    elapsed = time.time() - (created.timestamp() if created else time.time())

    # ── webhook 兜底 (Safety Net) ──────────────────────────────
    # 声明 webhook 但超过 grace 仍未收到回调:
    #   有状态查询地址 -> 降级为 poll 续跑; 没有 -> 直接失败, 绝不永久挂起.
    if mode == "webhook" and row.get("webhook_received_at") is None \
            and elapsed > settings.webhook_grace_s:
        if not row.get("status_query"):
            finalize_job(job_id, user_id, "video", False,
                         error="webhook not received within grace and no status query")
            update_handle_status(job_id, "failed", raw, progress, time.time(), attempts + 1,
                                 error="webhook timeout")
            return
        # 否则落到下方 poll 逻辑

    # webhook 已收到回调: 由 webhook 端点负责 finalize, 这里不再处理, 避免重复
    if mode == "webhook" and row.get("webhook_received_at") is not None:
        return

    cfg = load_provider_cfg(provider)
    if cfg is None:
        finalize_job(job_id, user_id, "video", False, error="provider config missing at completion")
        update_handle_status(job_id, "failed", raw, progress, time.time(), attempts + 1,
                             error="provider missing")
        return

    adapter = build_adapter(cfg)
    try:
        st = adapter.query_status(AsyncHandle(
            job_id=job_id, provider=provider,
            provider_task_id=row.get("provider_task_id"),
            status_query=row.get("status_query"),
        ))
    except Exception as e:  # noqa: BLE001
        logger.warning("[completer] status query failed job=%s: %s", job_id, e)
        # 瞬时网络错: 退避 30s 后重试, 不改终态
        update_handle_status(job_id, "processing", raw, progress, time.time() + 30, attempts + 1)
        return

    if st.normalized == NormalizedStatus.DONE:
        if not st.result_url:
            finalize_job(job_id, user_id, "video", False, error="completed but no url")
            update_handle_status(job_id, "failed", st.raw_status, progress, time.time(),
                                 attempts + 1, error="no url")
            return
        finalize_job(job_id, user_id, "video", True,
                     result={"url": st.result_url, "urls": [st.result_url],
                             "provider": provider, "usage": {}})
        update_handle_status(job_id, "done", st.raw_status, progress, time.time(), attempts + 1)
        return

    if st.normalized == NormalizedStatus.FAILED:
        finalize_job(job_id, user_id, "video", False, error=f"provider: {st.error}")
        update_handle_status(job_id, "failed", st.raw_status, progress, time.time(),
                            attempts + 1, error=st.error)
        return

    # PENDING / PROCESSING -> 退避续轮
    nxt = time.time() + next_interval(elapsed)
    update_handle_status(job_id, "processing", st.raw_status, progress, nxt, attempts + 1)
    if elapsed > settings.video_poll_max_s:
        finalize_job(job_id, user_id, "video", False,
                     error=f"poll timeout after {settings.video_poll_max_s}s (last={st.raw_status})")
        update_handle_status(job_id, "failed", st.raw_status, progress, time.time(),
                            attempts + 1, error="timeout")


def completer_loop() -> None:
    owner = f"completer-{os.getpid()}-{threading.get_ident()}"
    logger.info("[completer] started owner=%s", owner)
    while not _stop:
        try:
            due = claim_due_handles(settings.completer_batch, owner, time.time())
            if due:
                logger.debug("[completer] tick batch=%d", len(due))
                list(_executor.map(_process_one, due))
        except Exception as e:  # noqa: BLE001
            logger.exception("[completer] tick error: %s", e)
        time.sleep(settings.completer_tick_s)
    logger.info("[completer] stopped")


def start() -> threading.Thread:
    t = threading.Thread(target=completer_loop, daemon=True, name="completer")
    t.start()
    return t
