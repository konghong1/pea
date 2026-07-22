# pea-server 便捷脚本
.PHONY: up down logs bff orch web infra db

up:        # 一键起全栈 (含 MySQL/Redis/MinIO)
	docker compose up --build

down:      # 停止并移除容器
	docker compose down

infra:     # 仅起依赖 (MySQL/Redis/MinIO)
	docker compose up -d mysql redis minio

logs:      # 看日志
	docker compose logs -f

bff:
	cd services/bff && npm install && npm run start:dev

orch:
	cd services/generation-orchestrator && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

web:
	cd web && npm install && npm run dev
