"""Completer: 异步轮询回路 + webhook 漏触发兜底 (Safety Net).

单 asyncio 事件循环 + httpx 连接池, 同时 hold 数千 in-flight 状态查询;
每 tick 只处理"到点(next_poll_at)的那批", 用 asyncio.gather 并发查询,
HTTP 并发由 provider_http_pool 封顶. 生成期间除"到点那一下 GET"外不占服务端资源.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.async_core.backoff import next_interval
from app.async_core.db_async import (
    claim_due_handles,
    load_provider_cfg,
    update_handle_status,
)
from app.async_core.dispatcher import finalize_job, get_client
from app.async_core.provider_adapter import build_adapter, _extract_video_url
from app.async_core.state_machine import JobPhase
from app.async_core.types import AsyncHandle, CompletionMode, NormalizedStatus
from app.config import settings

logger = logging.getLogger(__name__)

_stop = False


def stop() -> None:
    global _stop
    _stop = True


def _row_to_handle(row: dict) -> AsyncHandle:
    return AsyncHandle(
        job_id=row["job_id"],
        user_id=row.get("user_id", 0),
        provider=row["provider"],
        completion_mode=CompletionMode(row["completion_mode"]),
        provider_task_id=row.get("provider_task_id"),
        provider_video_id=row.get("provider_video_id"),
        status_query=row.get("status_query"),
        raw_status=row.get("raw_status"),
        progress=row.get("progress"),
        poll_attempts=row.get("poll_attempts", 0),
    )


async def _process_one(row: dict, client: httpx.AsyncClient) -> None:
    job_id = row["job_id"]
    provider = row["provider"]
    mode = row["completion_mode"]
    raw = row["raw_status"]
    progress = row["progress"]
    attempts = row["poll_attempts"]
    created: Optional[datetime] = row.get("created_at")
    submitted_ts = created.timestamp() if created else time.time()
    elapsed = time.time() - submitted_ts
    user_id = int(row.get("user_id", 0))

    # ── webhook 兜底 (Safety Net) ──────────────────────────────
    # 声明 webhook 但超过 grace 仍未收到回调:
    #   有状态查询地址 -> 降级为 poll 续跑; 没有 -> 直接失败, 绝不永久挂起.
    if mode == "webhook" and row.get("webhook_received_at") is None \
            and elapsed > settings.webhook_grace_s:
        if not row.get("status_query"):
            finalize_job(job_id, user_id, "video", False,
                         error="webhook not received within grace and no status query")
            update_handle_status(job_id, JobPhase.FAILED, raw, progress,
                                 time.time(), attempts + 1, error="webhook timeout")
            return
        # 否则落到下方 poll 逻辑

    cfg = load_provider_cfg(provider)
    if cfg is None:
        finalize_job(job_id, user_id, "video", False, error="provider config missing at completion")
        update_handle_status(job_id, JobPhase.FAILED, raw, progress,
                             time.time(), attempts + 1, error="provider missing")
        return

    adapter = build_adapter(cfg)
    try:
        st = await adapter.query_status(_row_to_handle(row), client)
    except Exception as e:  # noqa: BLE001
        logger.warning("[completer] status query failed job=%s: %s", job_id, e)
        # 瞬时网络错: 退避 30s 后重试, 不改终态
        update_handle_status(job_id, JobPhase.PROCESSING, raw, progress,
                             time.time() + 30, attempts + 1)
        return

    if st.normalized == NormalizedStatus.DONE:
        if not st.result_url:
            finalize_job(job_id, user_id, "video", False, error="completed but no url")
            return
        finalize_job(job_id, user_id, "video", True,
                     result={"url": st.result_url, "urls": [st.result_url],
                             "provider": provider, "usage": {}})
        update_handle_status(job_id, JobPhase.DONE, st.raw_status, st.progress,
                             time.time(), attempts + 1)
        return

    if st.normalized == NormalizedStatus.FAILED:
        finalize_job(job_id, user_id, "video", False, error=f"provider: {st.error}")
        update_handle_status(job_id, JobPhase.FAILED, st.raw_status, st.progress,
                             time.time(), attempts + 1, error=st.error)
        return

    # PENDING / PROCESSING -> 退避续轮
    nxt = time.time() + next_interval(elapsed)
    update_handle_status(job_id, JobPhase.PROCESSING, st.raw_status, st.progress,
                         nxt, attempts + 1)
    if elapsed > settings.video_poll_max_s:
        finalize_job(job_id, user_id, "video", False,
                     error=f"poll timeout after {settings.video_poll_max_s}s (last={st.raw_status})")
        update_handle_status(job_id, JobPhase.FAILED, st.raw_status, st.progress,
                             time.time(), attempts + 1, error="timeout")


async def completer_loop() -> None:
    import os
    owner = f"completer-{os.getpid()}-{id(asyncio.current_task())}"
    client = get_client()
    logger.info("[completer] started owner=%s", owner)
    while not _stop:
        try:
            now = time.time()
            due = claim_due_handles(settings.completer_batch, owner, now)
            if due:
                logger.debug("[completer] tick batch=%d", len(due))
                await asyncio.gather(
                    *[_process_one(row, client) for row in due],
                    return_exceptions=True,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("[completer] tick error: %s", e)
        await asyncio.sleep(settings.completer_tick_s)
    logger.info("[completer] stopped")
