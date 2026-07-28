"""Orchestrator HTTP API: 受理/查询生成任务 (生成域拥有者)."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Query

from app import db, models
from app.config import settings
from app.redis_conn import enqueue_job
from app.schemas import (
    AcceptJobRequest,
    AcceptJobResponse,
    JobStatusResponse,
    ListJobsResponse,
)

router = APIRouter(prefix="/api")


def _row_to_dto(row: dict) -> JobStatusResponse:
    result = row.get("result_json")
    result_url = None
    result_urls = None
    if result:
        try:
            parsed = json.loads(result)
            result_url = parsed.get("url")
            result_urls = parsed.get("urls")
        except Exception:  # noqa: BLE001
            pass
    return JobStatusResponse(
        jobId=row["id"],
        userId=row["user_id"],
        type=row["type"],
        status=row["status"],
        cost_tapies=row.get("cost_tapies", 0),
        resultUrl=result_url,
        resultUrls=result_urls,
        # T-FIX-ERROR-2026-07-28: 失败详情从库读出, 节点失败卡可展示真实原因.
        # row.get 保证旧库 (error 列不存在) 也不会 KeyError.
        error=row.get("error"),
        createdAt=str(row.get("created_at")),
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.service_name}


@router.post("/jobs", response_model=AcceptJobResponse)
def accept_job(req: AcceptJobRequest):
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # 幂等: 相同 idempotency_key 直接返回已有 job
            if req.idempotency_key:
                cur.execute(
                    "SELECT id, status, cost_tapies FROM generation_jobs "
                    "WHERE idempotency_key=%s", [req.idempotency_key],
                )
                existing = cur.fetchone()
                if existing:
                    return AcceptJobResponse(
                        jobId=existing["id"], status=existing["status"],
                        cost_tapies=existing["cost_tapies"],
                    )
            job_id = str(uuid.uuid4())
            cost = req.cost_tapies or settings.default_cost_tapies
            cur.execute(
                "INSERT INTO generation_jobs "
                "(id, user_id, type, status, payload_json, cost_tapies, idempotency_key) "
                "VALUES (%s,%s,%s,'queued',%s,%s,%s)",
                [job_id, req.user_id, req.type,
                 json.dumps(req.model_dump(), ensure_ascii=False), cost,
                 req.idempotency_key],
            )
        conn.commit()

    enqueue_job(job_id, {**req.model_dump(), "job_id": job_id}, priority=req.priority)
    return AcceptJobResponse(jobId=job_id, status="queued", cost_tapies=cost)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM generation_jobs WHERE id=%s", [job_id])
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return _row_to_dto(row)


@router.get("/jobs", response_model=ListJobsResponse)
def list_jobs(
    user_id: int = Query(...),
    limit: int = Query(20, le=100),
    cursor: str = Query(None),  # ISO 时间戳游标; None/'0'/'' 表示从头
):
    # 真实游标分页 (keyset): created_at < cursor 向后翻, 避免 OFFSET 深翻 + 漏页 (资深开发复核 T-GEN-08)
    sql = "SELECT * FROM generation_jobs WHERE user_id=%s"
    params: list = [user_id]
    if cursor and cursor not in ("0", "0.0"):
        sql += " AND created_at < %s"
        params.append(cursor)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit + 1)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    items = [_row_to_dto(r) for r in rows[:limit]]
    nxt = str(rows[limit]["created_at"]) if len(rows) > limit else None
    return ListJobsResponse(items=items, next=nxt)
