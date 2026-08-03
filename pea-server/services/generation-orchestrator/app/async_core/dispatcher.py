"""Dispatcher: 毫秒级提交并立即 ACK, 长任务交给 Completer / Webhook.

worker 消费线程调用 dispatch(payload):
  1) 并发护栏: Redis 原子计数 (决策④, 每用户上限 12)
  2) 快提交 (提交第三方, 视频通常 <1s; 图像异步出图走事件循环, 不占消费线程/OS线程)
  3) 同步模式 -> 直接 finalize(done)
  4) 异步模式 -> 写 AsyncHandle + 置 running + 立即返回 (worker ACK)
整个链路消费线程不等待第三方渲染, 头阻塞消除.

finalize_job (Dispatcher / Completer / Webhook 共用):
  - 成功: 决策① 转存外部临时 URL -> 自有稳定 CDN URL
  - 失败: 决策③ 连续失败滑动窗口告警 + 退款
  - 终态统一 release 并发名额 (决策④)
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

from app import db, models, usage, storage
from app.async_core.provider_adapter import build_adapter
from app.async_core.db_async import insert_handle, load_model_provider_cfg
from app.async_core import concurrency
from app.async_core.engine import schedule, run_finalize
from app.config import settings
from app.redis_conn import publish_event
from app.compensation import refund_on_failure
from services.shared.events import job_updated, notification

logger = logging.getLogger(__name__)


def _rehost(url: str, jtype: str, user_id: int, provider: str) -> str:
    """决策①: 外部临时 URL -> 自有稳定 CDN URL (转存到 MinIO).

    跳过: 非 http(s) (如 data-URI) 直接原样返回, 无需转存.
    跳过: 已经是自有 CDN 地址的 (幂等). 有些适配器必须在自己内部就完成转存 ——
      典型是 Gemini/Veo: 结果 URI 要带 x-goog-api-key 头才能下载, 而本函数是**匿名** GET,
      交给它必然 403。这类适配器返回的已是稳定地址, 再转存一次纯属浪费带宽,
      且在 cdn_base_url 指向容器外地址的开发环境下还会失败告警, 制造噪音。
    转存失败 -> 降级用原始 URL (前端至少能显示, 虽不稳定) + 告警,
    不因存储抖动让生成整体失败.
    """
    if not url or not url.startswith("http"):
        return url
    cdn_base = (settings.cdn_base_url or "").rstrip("/")
    if cdn_base.startswith("http") and url.startswith(cdn_base + "/"):
        return url
    try:
        return storage.store_from_url(url, jtype, user_id=user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[dispatcher] rehost failed type=%s url=%s: %s", jtype, url[:80], e)
        return url


def _record_failure() -> None:
    """决策③: 连续失败滑动窗口告警.

    近 failure_alert_window_s 秒内失败数达 failure_alert_threshold ->
    发系统级告警 (level=warning, user_id=0 表示运维告警) 并重置计数避免重复轰炸.
    """
    try:
        from app.redis_conn import client as redis_client

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
    """统一终态处理: 写结果/退款 + 发布事件. Dispatcher / Completer / Webhook 共用."""
    try:
        if ok:
            result = result or {}
            provider = result.get("provider")
            # 决策①: 外部临时 URL -> 自有稳定 CDN URL (转存)
            if result.get("url"):
                result["url"] = _rehost(result["url"], jtype, user_id, provider)
            if result.get("urls"):
                result["urls"] = [
                    _rehost(u, jtype, user_id, provider) if isinstance(u, str) else u
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
                model=None, provider=provider, platform_config_id=None, usage=usage_dict,
            )
        else:
            # T-FIX-ERROR-2026-07-28: 失败详情落库 (之前只发 WS 事件, 节点 GET 拿不到).
            # 截断 500 字符, 跟之前 WS 事件一致, 避免超 TEXT 65535 上限.
            error_text = (error or "")[:500]
            db.update_job_status(job_id, models.JobStatus.FAILED.value, error=error_text)
            publish_event(job_updated(
                job_id=job_id, user_id=user_id, type=jtype,
                status="failed", error=error_text,
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
            _record_failure()  # 决策③: 连续失败告警
    except Exception as e:  # noqa: BLE001
        logger.exception("finalize_job error job=%s", job_id)
    finally:
        concurrency.release(user_id)  # 决策④: 释放并发名额


def _finalize_sync(job_id: str, user_id: int, jtype: str, ok: bool,
                   result: Optional[dict], error: Optional[str]) -> None:
    """在收尾线程池(非事件循环)执行终态处理, 避免阻塞事件循环。"""
    finalize_job(job_id, user_id, jtype, ok, result=result, error=error)


def _persist_handle_sync(job_id: str, user_id: int, jtype: str, h) -> None:
    """在收尾线程池写入异步句柄并广播 running, 不卡事件循环。"""
    insert_handle(h)
    publish_event(job_updated(
        job_id=job_id, user_id=user_id, type=jtype,
        status="running", progress=0.6,
    ))


async def _execute_async(job_id: str, user_id: int, jtype: str, req: dict, cfg: dict, adapter) -> None:
    """在事件循环协程中执行真实提交 (异步出图 / 异步提交).

    等待外部模型响应的 5~10min 期间协程 await 让出控制权, 单线程并发承载上千在途请求;
    收尾(转存下载 + 写库 + 发事件)交给收尾线程池, 不卡事件循环.
    """
    try:
        outcome = await adapter.submit(req)
        if outcome.sync:
            res = outcome.result
            await run_finalize(
                _finalize_sync, job_id, user_id, jtype, True,
                {
                    "url": res.url,
                    "urls": res.urls,
                    "provider": res.provider,
                    "usage": res.usage or {},
                },
                None,
            )
            return
        # 异步: 写 handle, 置 running, 不释放并发 (Completer 终态时释放)
        h = outcome.handle
        h.job_id = job_id
        h.user_id = user_id
        h.provider = cfg.get("provider_name") or adapter.name
        await run_finalize(_persist_handle_sync, job_id, user_id, jtype, h)
    except Exception as e:  # noqa: BLE001
        logger.warning("[dispatcher] submit failed job=%s: %s", job_id, f"{type(e).__name__}: {e}")
        await run_finalize(_finalize_sync, job_id, user_id, jtype, False, None,
                           f"submit error: {type(e).__name__}: {e}")


def dispatch(job_id: str, payload: dict) -> bool:
    """消费线程入口. 返回 True=已处理(可 ACK), False=需延迟重投(不 ACK).

    False 仅发生在并发护栏拒绝时; 此时不写任何状态, 让 Redis Stream 重新投递.
    """
    user_id = int(payload.get("user_id", 0) or 0)
    jtype = payload.get("type", "image")

    cfg = load_model_provider_cfg(payload.get("model"))
    if cfg is None or not cfg.get("provider_enabled"):
        logger.warning("[dispatcher] model %s unavailable (cfg=%s)", payload.get("model"), bool(cfg))
        finalize_job(job_id, user_id, jtype, False,
                     error=f"model '{payload.get('model')}' unavailable")
        return True

    adapter = build_adapter(cfg)

    # 决策④: 每用户并发上限 (Redis 共享计数). 达上限 -> 判失败 + 退款 (不占资源).
    if not concurrency.acquire(user_id):
        finalize_job(job_id, user_id, jtype, False,
                     error=f"超过每用户并发上限 {settings.per_user_concurrency}")
        return True

    try:
        db.update_job_status(job_id, models.JobStatus.RUNNING.value)
        publish_event(job_updated(
            job_id=job_id, user_id=user_id, type=jtype,
            status="running", progress=0.1,
        ))
        req = {**payload, "job_id": job_id}
        schedule(_execute_async(job_id, user_id, jtype, req, cfg, adapter))
        return True
    except Exception as e:  # noqa: BLE001
        logger.exception("[dispatcher] dispatch error job=%s", job_id)
        concurrency.release(user_id)
        finalize_job(job_id, user_id, jtype, False, error=f"dispatch error: {e}")
        return True
