"""异步完成层 DB 访问: generation_task_handles 读写 + provider 配置加载."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from app import db
from app.async_core.types import AsyncHandle, CompletionMode


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts)


def insert_handle(h: AsyncHandle) -> None:
    now = time.time()
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO generation_task_handles
                   (job_id, user_id, provider, completion_mode, provider_task_id,
                    provider_video_id, status_query, phase, raw_status, progress,
                    next_poll_at, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'processing',%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                     provider=%s, completion_mode=%s, provider_task_id=%s,
                     provider_video_id=%s, status_query=%s, updated_at=%s""",
                [h.job_id, h.user_id, h.provider, h.completion_mode.value,
                 h.provider_task_id, h.provider_video_id, h.status_query,
                 h.raw_status, h.progress, _dt(now), _dt(now), _dt(now),
                 h.provider, h.completion_mode.value, h.provider_task_id,
                 h.provider_video_id, h.status_query, _dt(now)],
            )
        conn.commit()


def claim_due_handles(batch: int, owner: str, now_ts: float) -> list[dict]:
    """乐观锁抢占: 仅认领 phase 未终态且 next_poll_at 到期的, 多副本不双轮询."""
    now = _dt(now_ts)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE generation_task_handles
                   SET claimed_by=%s, next_poll_at=%s
                   WHERE phase IN ('submitted','processing')
                     AND next_poll_at <= %s AND claimed_by IS NULL
                   ORDER BY next_poll_at ASC LIMIT %s""",
                [owner, now, now, batch],
            )
            if cur.rowcount == 0:
                return []
            cur.execute(
                """SELECT job_id, user_id, provider, completion_mode, provider_task_id,
                          provider_video_id, status_query, phase, raw_status, progress,
                          poll_attempts, webhook_received_at, created_at
                   FROM generation_task_handles WHERE claimed_by=%s""",
                [owner],
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def update_handle_status(
    job_id: str,
    phase,  # JobPhase 或 str
    raw_status: Optional[str],
    progress: Optional[int],
    next_poll_at_ts: float,
    poll_attempts: int,
    error: Optional[str] = None,
) -> None:
    phase_val = phase.value if hasattr(phase, "value") else phase
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE generation_task_handles
                   SET phase=%s, raw_status=%s, progress=%s, next_poll_at=%s,
                       poll_attempts=%s, error=%s, claimed_by=NULL, updated_at=%s
                   WHERE job_id=%s""",
                [phase_val, raw_status, progress, _dt(next_poll_at_ts),
                 poll_attempts, error, _dt(time.time()), job_id],
            )
        conn.commit()


def mark_webhook_received(job_id: str, ts: float) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE generation_task_handles SET webhook_received_at=%s, updated_at=%s WHERE job_id=%s",
                [_dt(ts), _dt(time.time()), job_id],
            )
        conn.commit()


def load_handle(job_id: str) -> Optional[dict]:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM generation_task_handles WHERE job_id=%s", [job_id])
            row = cur.fetchone()
    return dict(row) if row else None


def load_provider_cfg(key: Optional[str]) -> Optional[dict]:
    """按 provider_id / model_name / id / provider_name 任一匹配 ai_providers.

    返回含 webhook_secret (决策②: 每厂商各一把回调密钥, 不再用全局 settings.webhook_secret).
    """
    if not key:
        return None
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT base_url, api_key, model_name, provider_name,
                          completion_mode, accepts_callback, webhook_secret
                   FROM ai_providers
                   WHERE provider_id=%s OR model_name=%s OR id=%s OR provider_name=%s
                   LIMIT 1""",
                [key, key, key, key],
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "base_url": row["base_url"],
        "api_key": row["api_key"],
        "model_name": row["model_name"],
        "provider_name": row["provider_name"],
        "completion_mode": row.get("completion_mode") or "poll",
        "accepts_callback": bool(row.get("accepts_callback")),
        "webhook_secret": row.get("webhook_secret") or "",
    }
