"""Generation Orchestrator 入口.

职责: 受理生成任务(写 generation_jobs + 入队) + 启动 Worker 消费队列。
BFF 通过 HTTP 调用本服务的 /api/jobs; 本服务通过 Redis 事件反向通知 BFF。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许从任意工作目录启动: 将仓库根加入 sys.path, 使 services.shared 跨包导入可用。
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI

from app.api import router
from app.config import settings
from app.worker import start as start_worker

app = FastAPI(title="pea generation-orchestrator", version="0.1.0")
app.include_router(router)

if settings.worker_enabled:
    start_worker()


@app.on_event("startup")
def _startup() -> None:
    # worker 已在 import 时 daemon 启动; 此处可挂健康检查/指标
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)
