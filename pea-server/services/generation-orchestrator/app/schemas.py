"""Pydantic DTOs for orchestrator HTTP API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AcceptJobRequest(BaseModel):
    user_id: int
    type: str = Field(pattern="^(image|video|text)$")
    prompt: str = Field(min_length=1, max_length=4000)
    model: str | None = None
    priority: str = Field(default="normal", pattern="^(normal|fast)$")
    idempotency_key: str | None = None
    # 预扣的 Tapies (由 BFF 在受理时确认已扣, 这里仅记录成本用于回写)
    cost_tapies: int = Field(default=0, ge=0)


class AcceptJobResponse(BaseModel):
    jobId: str
    status: str
    cost_tapies: int


class JobStatusResponse(BaseModel):
    jobId: str
    userId: int
    type: str
    status: str
    cost_tapies: int
    resultUrl: str | None = None
    error: str | None = None
    createdAt: str | None = None


class ListJobsResponse(BaseModel):
    items: list[JobStatusResponse]
    next: int | None = None
