# Generation Orchestrator (FastAPI) 镜像
FROM python:3.12-slim

# 构建参数: 默认用国内 PyPI 镜像 (海外部署可覆盖:
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple)
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=$PIP_INDEX_URL \
    PIP_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app
COPY services/generation-orchestrator/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/generation-orchestrator/ ./
COPY services/shared ./services/shared
ENV PYTHONPATH=/ PYTHONUNBUFFERED=1
EXPOSE 8000
# uvicorn 已在 requirements.txt 中, 直接启动; 不在运行时 pip install (避免启动期网络超时)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
