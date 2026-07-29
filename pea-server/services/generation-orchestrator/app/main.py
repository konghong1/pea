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

import logging
import os
import socket
from urllib.parse import urlparse

from fastapi import FastAPI

from app.api import router
from app.async_core import webhook as webhook_module
from app.async_core import completer as completer_module
from app.async_core import engine as engine_module
from app.config import settings
from app.worker import start as start_worker

_proxy_logger = logging.getLogger("egress-proxy")


def _proxy_can_tunnel(
    proxy_host: str, proxy_port: int, target_host: str, target_port: int, timeout: float = 3.0
) -> bool:
    """经 HTTP 代理向 (target_host, target_port) 发起 CONNECT, 验证能否真正出网。

    仅 TCP 连通会漏报“端口有人听但代理是废的/无法出网”的情况(那样出网请求会
    read ECONNRESET 且原因被掩盖)。这里真的建一次隧道到外部 AI, 收到 2xx 才判可用。
    """
    try:
        with socket.create_connection((proxy_host, proxy_port), timeout=timeout) as s:
            s.settimeout(timeout)
            req = (
                f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
                f"Host: {target_host}:{target_port}\r\n\r\n"
            ).encode()
            s.sendall(req)
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf += chunk
            status_line = buf.split(b"\r\n", 1)[0].decode(errors="ignore")
            parts = status_line.split()
            return len(parts) >= 2 and parts[1].startswith("2")
    except OSError:
        return False


def _ensure_proxy_strategy() -> None:
    """死代理防护 (与 bff bootstrap-proxy 行为对齐).

    requests/httpx 默认 trust_env=True, 会读取 HTTP(S)_PROXY 环境变量走代理。
    若 compose 注入了代理 (PEA_PROXY_FIX=1) 但代理进程实际没在运行 / 无法出网(常见:
    把开发机 .env 原样搬上服务器, 33210 是开发沙箱专属代理), 则所有出网调用
    (生成/拉模型)都会 ECONNREFUSED/ECONNRESET 且报错掩盖真实原因。
    这里在进程启动时探测一次: 代理端口无人监听 或 无法经它建隧道出网到外部 AI
    => 清掉代理 env, 退回直连, 让后续错误暴露真实原因。
    """
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") \
        or os.environ.get("https_proxy") or os.environ.get("http_proxy")
    if not proxy:
        return
    try:
        u = urlparse(proxy)
        host = u.hostname
        port = u.port or (443 if u.scheme == "https" else 80)
        if not host:
            raise ValueError(f"bad proxy url: {proxy}")
        # 1) TCP 连通性
        with socket.create_connection((host, port), timeout=2):
            pass
        # 2) 真实隧道测试: 经代理 CONNECT 到外部 AI (apihub:443), 验证能否出网
        if not _proxy_can_tunnel(host, port, "apihub.agnes-ai.com", 443):
            raise OSError("proxy port open but cannot tunnel to external AI")
        _proxy_logger.info("egress proxy %s reachable and can egress, keep proxy env", proxy)
    except OSError as e:
        for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            os.environ.pop(k, None)
        _proxy_logger.warning(
            "egress proxy %s cannot egress (%s), cleared proxy env vars (fallback to direct)",
            proxy, e,
        )


# 必须在 worker / httpx 客户端启动前执行, 保证首个出网请求前代理策略已定型。
_ensure_proxy_strategy()

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
