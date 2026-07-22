@echo off
REM pea Creative OS - minimal direct start (no args, no loops)
cd /d "%~dp0pea-server"
docker compose up --build
