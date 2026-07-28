"""Generation Orchestrator 入口.

职责: 受理生成任务(写 generation_jobs + 入队) + 启动 Worker 消费队列。
BFF 通过 HTTP 调用本服务的 /api/jobs; 本服务通过 Redis 事件反向通知 BFF。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许从任意工作目录启动: 将仓库根(含 services/shared)与 app 包所在目录加入 sys.path。
# 容器布局: /app/app/main.py + /app/services/shared -> 解析到 /app
# 开发布局: pea-server/services/generation-orchestrator/app/main.py + pea-server/services/shared -> 解析到 pea-server
_HERE = Path(__file__).resolve()


def _repo_root(p: Path) -> Path | None:
    for cand in (_HERE, *_HERE.parents):
        if (cand / "services" / "shared").exists():
            return cand
    return None


_ROOT = _repo_root(_HERE) or _HERE.parents[1]
_APP_PARENT = _HERE.parents[1]
for _p in (_ROOT, _APP_PARENT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fastapi import FastAPI

from app.api import router
from app.async_core import webhook as webhook_module
from app.async_core import completer as completer_module
from app.async_core import engine as engine_module
from app.config import settings
from app.worker import start as start_worker

app = FastAPI(title="pea generation-orchestrator", version="0.1.0")
app.include_router(router)
app.include_router(webhook_module.router)  # 异步完成层: 第三方回调端点

if settings.worker_enabled:
    start_worker()
    completer_module.start()  # 异步完成层: 后台轮询回路 (视频状态维护)
    engine_module.ensure_started()  # 异步生成引擎: 预热事件循环 + httpx 客户端


@app.on_event("startup")
def _startup() -> None:
    # worker + completer 已在 import 时 daemon 启动; 此处可挂健康检查/指标
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)
