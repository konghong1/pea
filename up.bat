@echo off
REM pea Creative OS - minimal direct start, detached (start then exit)
set COMPOSE_PROJECT_NAME=pea-server
cd /d "%~dp0pea-server"
docker compose up --build -d
echo [pea] Started in background. Logs: docker compose logs -f   Stop: docker compose down

