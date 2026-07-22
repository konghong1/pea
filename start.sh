#!/usr/bin/env bash
#
# pea Creative OS — 一键启动脚本
# 用法:
#   ./start.sh            构建并前台启动全栈 (日志实时可见, Ctrl+C 停止)
#   ./start.sh -d         后台启动, 等待 healthy 后自动打开浏览器
#   ./start.sh --logs     仅查看日志
#   ./start.sh --down     停止并移除容器
#   ./start.sh --build    强制重新构建镜像后启动
#
set -euo pipefail

# ----- 定位到 pea-server 目录（脚本放在项目根目录） -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$SCRIPT_DIR/pea-server"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "❌ 找不到 $COMPOSE_FILE" >&2
  exit 1
fi
cd "$COMPOSE_DIR"

# ----- 颜色 -----
if [ -t 1 ]; then
  C_B="\033[1;34m"; C_G="\033[1;32m"; C_Y="\033[1;33m"; C_R="\033[1;31m"; C_0="\033[0m"
else
  C_B=""; C_G=""; C_Y=""; C_R=""; C_0=""
fi
info()  { echo -e "${C_B}[pea]${C_0} $*"; }
ok()    { echo -e "${C_G}[✓]${C_0} $*"; }
warn()  { echo -e "${C_Y}[!]${C_0} $*"; }
err()   { echo -e "${C_R}[✗]${C_0} $*" >&2; }

# ----- 解析参数 -----
DETACH=0; DOWN=0; LOGS=0; BUILD=0
for a in "$@"; do
  case "$a" in
    -d|--detach) DETACH=1 ;;
    --down)      DOWN=1 ;;
    --logs)      LOGS=1 ;;
    --build)     BUILD=1 ;;
    -h|--help)   sed -n '2,9p' "$0"; exit 0 ;;
    *) err "未知参数: $a"; exit 1 ;;
  esac
done

# ----- 依赖检查 -----
if ! command -v docker >/dev/null 2>&1; then
  err "未检测到 docker，请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop"
  exit 1
fi
# 兼容 docker compose 插件 与 老的 docker-compose
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  err "未检测到 docker compose 插件，请升级 Docker Desktop (≥ 2.x)"
  exit 1
fi

# docker 守护进程是否可用
if ! docker info >/dev/null 2>&1; then
  err "Docker 守护进程未运行，请先启动 Docker Desktop。"
  exit 1
fi

open_browser() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url"
  elif command -v open >/dev/null 2>&1;     then open "$url"
  elif command -v start >/dev/null 2>&1;    then start "$url"
  fi
}

# ----- 动作 -----
if [ "$DOWN" -eq 1 ]; then
  info "停止并移除容器..."
  $DC down
  ok "已停止。"
  exit 0
fi

if [ "$LOGS" -eq 1 ]; then
  info "跟踪日志 (Ctrl+C 退出)..."
  exec $DC logs -f
fi

# 检测是否已在运行
RUNNING=$($DC ps -q 2>/dev/null | head -n1 || true)
if [ -n "$RUNNING" ] && [ "$BUILD" -eq 0 ]; then
  warn "已有容器在运行。直接跟踪日志 (如需重建请加 --build)。"
  exec $DC logs -f
fi

# 构建并启动
if [ "$BUILD" -eq 1 ]; then
  info "重新构建镜像并启动..."
  $DC up --build --force-recreate
else
  info "构建并启动全栈 (首次会拉镜像/建表，请稍候)..."
  $DC up --build
fi

# 若前台模式，启动命令会阻塞到这里；以下仅对 --detach 生效
if [ "$DETACH" -eq 1 ]; then
  info "后台启动中，等待依赖健康检查..."
  # 最多等 120s 让 mysql/redis/minio 变 healthy
  for i in $(seq 1 120); do
    healthy=$($DC ps --format '{{.Service}} {{.Health}}' 2>/dev/null | grep -c "healthy" || true)
    [ "$healthy" -ge 3 ] && break
    sleep 1
  done
  ok "服务已就绪："
  echo -e "   ${C_G}Web${C_0}          http://localhost:8080"
  echo -e "   ${C_G}BFF API${C_0}      http://localhost:4000"
  echo -e "   ${C_G}Orchestrator${C_0} http://localhost:8000/api/health"
  echo -e "   ${C_G}MinIO 控制台${C_0}  http://localhost:9001  (minioadmin/minioadmin)"
  open_browser "http://localhost:8080" || true
  info "查看日志: ./start.sh --logs   停止: ./start.sh --down"
fi
