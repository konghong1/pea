"""Dispatcher: 毫秒级提交并立即 ACK, 长任务交给 Completer / Webhook.

worker 消费线程调用 submit_job_sync(payload):
  1) 并发护栏: Redis 原子计数 (决策④, 每用户上限 12)
  2) 快提交 (POST 第三方, 通常 <1s)
  3) 同步模式 -> 直接 finalize(done)
  4) 异步模式 -> 写 AsyncHandle + 置 running + 立即返回 (worker ACK)
整个调用不等待第三方渲染, 头阻塞消除.

finalize_job (Completer/Webhook 共用):
  - 成功: 决策① 转存外部临时 URL -> 自有稳定 CDN URL
  - 失败: 决策③ 连续失败滑动窗口告警 + 退款
  - 终态统一 release 并发名额 (决策④)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from app import db, models, usage, storage
from app.async_core.types import AsyncHandle, CompletionMode, SubmitResult
from app.async_core.provider_adapter import build_adapter
from app.async_core.db_async import insert_handle, load_provider_cfg
from app.async_core import concurrency
from app.config import settings
from app.redis_conn import publish_event, client as redis_client
from app.compensation import refund_on_failure
from services.shared.events import job_updated, notification

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """单例异步 HTTP 客户端 (连接池上限由配置控制). 绑定到调用它的事件循环."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=settings.provider_http_pool,
                max_keepalive_connections=settings.provider_http_pool,
            ),
            timeout=httpx.Timeout(
                connect=settings.provider_http_connect_timeout_s, read=300
            ),
        )
    return _client


def _rehost(url: str, jtype: str, user_id: int) -> str:
    """决策①: 外部临时 URL -> 自有稳定 CDN URL (转存到 MinIO).

    转存失败 -> 降级用原始 URL (前端至少能显示, 虽不稳定) + 告警,
    不因存储抖动让生成整体失败. storage 模块转存异常会抛出, 这里兜底捕获.
    """
    try:
        return storage.store_from_url(url, jtype, user_id=user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[dispatcher] rehost failed type=%s url=%s: %s", jtype, url[:80], e)
        return url


def _record_failure(user_id: int) -> None:
    """决策③: 连续失败滑动窗口告警.

    近 failure_alert_window_s 秒内失败数达 failure_alert_threshold ->
    发系统级告警 (level=warning, user_id=0 表示运维告警) 并重置计数避免重复轰炸.
    """
    try:
        r = redis_client()
        key = "alert:fail:recent"
        n = r.incr(key)
        if n == 1:
            r.expire(key, settings.failure_alert_window_s)
        if n >= settings.failure_alert_threshold:
            publish_event(notification(
                user_id=0,
                title="生成链路异常",
                body=f"近 {settings.failure_alert_window_s}s 内连续 {n} 个任务失败，请检查第三方服务状态",
                level="warning",
            ))
            r.delete(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[dispatcher] failure alert incr failed: %s", e)


def finalize_job(
    job_id: str,
    user_id: int,
    jtype: str,
    ok: bool,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """统一终态处理: 写结果/退款 + 发布事件. Completer 与 Webhook 共用."""
    try:
        if ok:
            result = result or {}
            # 决策①: 外部临时 URL -> 自有稳定 CDN URL (转存)
            if result.get("url"):
                result["url"] = _rehost(result["url"], jtype, user_id)
            if result.get("urls"):
                result["urls"] = [
                    _rehost(u, jtype, user_id) if isinstance(u, str) else u
                    for u in result["urls"]
                ]
            cost = int(result.get("cost_tapies", settings.default_cost_tapies))
            usage_dict = result.get("usage", {}) or {}
            db.update_job_status(
                job_id, models.JobStatus.DONE.value,
                result_json=json.dumps(result, ensure_ascii=False),
                cost_tapies=cost,
                usage_json=json.dumps(usage_dict, ensure_ascii=False),
            )
            publish_event(job_updated(
                job_id=job_id, user_id=user_id, type=jtype,
                status="done", result_url=result.get("url"),
                result_urls=result.get("urls"), cost=cost,
            ))
            usage.record_usage(
                job_id=job_id, user_id=user_id, node_type=jtype,
                model=None, provider=result.get("provider"), usage=usage_dict,
            )
        else:
            db.update_job_status(job_id, models.JobStatus.FAILED.value)
            publish_event(job_updated(
                job_id=job_id, user_id=user_id, type=jtype,
                status="failed", error=(error or "")[:500],
            ))
            publish_event(notification(
                user_id=user_id, title="生成失败",
                body=(error or "")[:200], level="error",
            ))
            refunded = refund_on_failure(
                job_id, user_id, int((result or {}).get("cost_tapies", 0))
            )
            if refunded:
                try:
                    db.update_job_status(job_id, models.JobStatus.REFUNDED.value)
                except Exception as e:  # noqa: BLE001
                    logger.warning("mark refunded failed %s: %s", job_id, e)
            _record_failure(user_id)  # 决策③: 连续失败告警
    except Exception as e:  # noqa: BLE001
        logger.exception("finalize_job error job=%s", job_id)
    finally:
        concurrency.release(user_id)  # 决策④: 释放并发名额


async def submit_job(payload: dict) -> None:
    job_id = payload.get("job_id") or payload.get("id")
    user_id = int(payload.get("user_id", 0))
    jtype = payload.get("type", "image")

    # 决策④: 每用户并发上限 (Redis 共享计数). 达上限 -> 直接判失败, 不占资源.
    if not concurrency.acquire(user_id):
        finalize_job(job_id, user_id, jtype, False,
                     error=f"超过每用户并发上限 {settings.per_user_concurrency}")
        return

    cfg = load_provider_cfg(payload.get("provider_id") or payload.get("model"))
    if cfg is None:
        finalize_job(job_id, user_id, jtype, False, error="provider config not found")
        return

    adapter = build_adapter(cfg)
    try:
        res: SubmitResult = await adapter.submit(payload, get_client())
    except Exception as e:
        logger.warning("[dispatcher] submit failed job=%s: %s", job_id, e)
        finalize_job(job_id, user_id, jtype, False, error=f"submit error: {e}")
        return

    if res.mode == CompletionMode.SYNC:
        finalize_job(job_id, user_id, jtype, True, result=res.result)
        return

    # 异步: 写 handle, 置 running, 立即返回 (worker 负责 ACK)
    h: AsyncHandle = res.handle
    h.job_id = job_id
    h.user_id = user_id
    h.provider = cfg["provider_name"]
    insert_handle(h)
    db.update_job_status(job_id, models.JobStatus.RUNNING.value)
    publish_event(job_updated(
        job_id=job_id, user_id=user_id, type=jtype,
        status="running", progress=0.1,
    ))


def submit_job_sync(payload: dict) -> None:
    """供同步 worker 线程调用: 每次起一个短生命周期 asyncio loop (提交很快)."""
    asyncio.run(submit_job(payload))
