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
    if result:
        try:
            result_url = json.loads(result).get("url")
        except Exception:  # noqa: BLE001
            pass
    return JobStatusResponse(
        jobId=row["id"],
        userId=row["user_id"],
        type=row["type"],
        status=row["status"],
        cost_tapies=row.get("cost_tapies", 0),
        resultUrl=result_url,
        error=None,
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
    cursor: int = Query(0),
):
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM generation_jobs WHERE user_id=%s "
                "ORDER BY created_at DESC LIMIT %s", [user_id, limit + 1],
            )
            rows = cur.fetchall()
    items = [_row_to_dto(r) for r in rows[:limit]]
    nxt = cursor + limit if len(rows) > limit else None
    return ListJobsResponse(items=items, next=nxt)
