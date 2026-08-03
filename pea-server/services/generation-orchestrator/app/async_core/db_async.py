"""异步完成层 DB 访问: generation_task_handles 读写 + provider 配置加载.

全部走 app.db 的 pymysql 连接池 (与既有 db.py 一致), 不引入新的 DB 客户端。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from app import db
from app.config import settings
from app.async_core.types import AsyncHandle, CompletionMode


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts)


# ───────────────────────── 句柄表 ─────────────────────────

def insert_handle(h: AsyncHandle) -> None:
    """写入/更新异步任务句柄. 幂等 (同一 job_id 重复提交不报错)."""
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
    """乐观锁抢占: 仅认领 phase 未终态且 next_poll_at 到期的, 多副本不双轮询.

    实现: UPDATE ... WHERE phase IN ('submitted','processing') AND next_poll_at<=now
          AND claimed_by IS NULL ORDER BY next_poll_at LIMIT n, 置 claimed_by=owner;
    随后 SELECT claimed_by=owner 的行返回. 单连接事务保证原子性.
    """
    now = _dt(now_ts)
    # 回收"被已死实例占住"的句柄: 用 datetime 比较, 不能传 unix 浮点 (MySQL 无法转换)
    stale_dt = _dt(now_ts - settings.completer_stale_s)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE generation_task_handles
                   SET claimed_by=%s, next_poll_at=%s
                   WHERE phase IN ('submitted','processing')
                     AND next_poll_at <= %s
                     AND (claimed_by IS NULL OR next_poll_at < %s)
                   ORDER BY next_poll_at ASC LIMIT %s""",
                [owner, now, now, stale_dt, batch],
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


# ───────────────────────── provider 配置 ─────────────────────────

def load_model_provider_cfg(model_id: Optional[str]) -> Optional[dict]:
    """按 ai_models.id 联表取模型 + 提供商配置 (含异步完成层新增契约列).

    返回: model_name / provider_type / provider_name / base_url / api_key /
          completion_mode / accepts_callback / webhook_secret.
    找不到或提供商停用返回 None.
    """
    if not model_id:
        return None
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.model_name    AS model_name,
                       p.id            AS provider_id,
                       p.name          AS provider_name,
                       p.provider_type AS provider_type,
                       p.protocol      AS protocol,
                       p.vendor        AS vendor,
                       p.base_url      AS base_url,
                       p.api_key       AS api_key,
                       p.enabled       AS provider_enabled,
                       p.completion_mode   AS completion_mode,
                       p.accepts_callback AS accepts_callback,
                       p.webhook_secret   AS webhook_secret,
                       p.external_ref_base_url AS external_ref_base_url
                FROM ai_models m
                JOIN ai_providers p ON p.id = m.provider_id
                WHERE m.id = %s
                """,
                [model_id],
            )
            return cur.fetchone()


def load_provider_cfg(key: Optional[str]) -> Optional[dict]:
    """按 provider id / name 匹配 ai_providers (Completer/Webhook 用).

    返回含 webhook_secret (决策②: 每厂商各一把回调密钥, 不再用全局 settings.webhook_secret).
    """
    if not key:
        return None
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT base_url, api_key, provider_type, protocol, vendor, name AS provider_name,
                          completion_mode, accepts_callback, webhook_secret,
                          external_ref_base_url
                   FROM ai_providers
                   WHERE id=%s OR name=%s
                   LIMIT 1""",
                [key, key],
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "base_url": row["base_url"],
        "api_key": row["api_key"],
        "provider_type": row.get("provider_type"),
        "protocol": row.get("protocol") or row.get("provider_type"),
        "vendor": row.get("vendor") or "",
        "provider_name": row["provider_name"],
        "completion_mode": row.get("completion_mode") or "poll",
        "accepts_callback": bool(row.get("accepts_callback")),
        "webhook_secret": row.get("webhook_secret") or "",
        "external_ref_base_url": (row.get("external_ref_base_url") or "").strip(),
    }
