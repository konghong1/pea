# Generation Orchestrator (FastAPI) 镜像
FROM python:3.12-slim
WORKDIR /app
COPY services/generation-orchestrator/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/generation-orchestrator/ ./
COPY services/shared ./services/shared
ENV PYTHONPATH=/ PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "pip install uvicorn && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
