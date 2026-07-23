@echo off
REM pea Creative OS - minimal direct start (no args, no loops)
set COMPOSE_PROJECT_NAME=pea-server
cd /d "%~dp0pea-server"
docker compose up --build
