"""Pydantic DTOs for orchestrator HTTP API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AcceptJobRequest(BaseModel):
    user_id: int
    type: str = Field(pattern="^(image|video|text)$")
    prompt: str = Field(min_length=1, max_length=4000)
    # 模型标识: 对应 ai_models.id。编排器据此从 DB 解析真实模型名 + 提供商密钥。
    model: str | None = None
    # 生成参数 (size/duration/n/reference_images/seed 等)。BFF 已据此算价, 编排器据此调外部模型。
    params: dict[str, Any] = Field(default_factory=dict)
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
