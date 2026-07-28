"""Webhook 端点: 接收第三方主动回调 (webhook 模式, 零轮询完成).

安全: HMAC 签名校验, secret 取自该 provider 自身 (决策②: 每厂商各一把);
幂等: 已 done/failed 的 job 直接 200 忽略, 防第三方重复投递导致重复退款;
未知 job 静默 200, 防探测.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Optional

from fastapi import APIRouter, Query, Request

from app.async_core.db_async import load_handle, mark_webhook_received, load_provider_cfg
from app.async_core.dispatcher import finalize_job
from app.async_core.provider_adapter import _extract_video_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/generation", tags=["generation"])


def _sign(job_id: str, provider_task_id: str, secret: str) -> str:
    msg = f"{job_id}:{provider_task_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _verify(job_id: str, provider_task_id: str, sig: str, secret: str) -> bool:
    if not secret or not sig:
        return False
    return hmac.compare_digest(_sign(job_id, provider_task_id, secret), sig)


@router.post("/webhook")
async def webhook(
    request: Request,
    job_id: str = Query(...),
    sig: str = Query(...),
):
    body: dict = await request.json()
    provider_task_id = str(body.get("task_id") or body.get("id") or "")

    handle = load_handle(job_id)
    if handle is None:
        return {"ok": True}  # 未知 job, 静默忽略
    provider = handle.get("provider", "")
    # 决策②: 按 provider_name 取该厂商自己的 secret (每厂商各一把)
    cfg = load_provider_cfg(provider)
    secret = (cfg or {}).get("webhook_secret") or ""
    if not _verify(job_id, provider_task_id, sig, secret):
        logger.warning("[webhook] bad signature job=%s", job_id)
        return {"ok": False, "error": "bad signature"}

    if handle.get("phase") in ("done", "failed"):
        return {"ok": True}  # 幂等

    mark_webhook_received(job_id, time.time())

    url = _extract_video_url(body)
    if body.get("status") in ("failed", "error") or not url:
        finalize_job(job_id, int(handle.get("user_id", 0)), "video", False,
                     error=f"webhook failed: {body.get('error')}")
    else:
        finalize_job(job_id, int(handle.get("user_id", 0)), "video", True,
                     result={"url": url, "urls": [url], "provider": provider, "usage": {}})
    return {"ok": True}
