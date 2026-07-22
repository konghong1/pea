@echo off
REM ============================================================
REM  pea Creative OS - one-click startup (Windows native, double-click)
REM  Usage:
REM    start.cmd            build and start full stack in foreground
REM    start.cmd -d         start in background, open browser when ready
REM    start.cmd --logs     follow logs only
REM    start.cmd --down     stop and remove containers
REM    start.cmd --build    force rebuild images then start
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0pea-server"
if not exist "docker-compose.yml" (
  echo [X] docker-compose.yml not found
  pause
  exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
  echo [X] docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop
  pause
  exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo [X] Docker is not running. Start Docker Desktop first (wait for the whale icon to turn green).
  pause
  exit /b 1
)

set DETACH=0
set DOWN=0
set LOGS=0
set BUILD=0
:parse
if "%~1"=="" goto :done
if "%~1"=="-d"      ( set DETACH=1 & shift & goto :parse )
if "%~1"=="--detach" ( set DETACH=1 & shift & goto :parse )
if "%~1"=="--down"   ( set DOWN=1   & shift & goto :parse )
if "%~1"=="--logs"   ( set LOGS=1   & shift & goto :parse )
if "%~1"=="--build"  ( set BUILD=1  & shift & goto :parse )
shift
goto :parse
:done

if %DOWN%==1 (
  echo [pea] Stopping and removing containers...
  docker compose down
  echo [OK] Stopped.
  goto :eof
)

if %LOGS%==1 (
  echo [pea] Following logs (Ctrl+C to exit)...
  docker compose logs -f
  goto :eof
)

docker compose ps -q > "%TEMP%\pea_ps.tmp" 2>nul
set RUNNING=
for /f %%i in (%TEMP%\pea_ps.tmp) do set RUNNING=1
if defined RUNNING if %BUILD%==0 (
  echo [!] Containers already running, following logs (use --build to rebuild).
  docker compose logs -f
  goto :eof
)

if %BUILD%==1 (
  echo [pea] Rebuilding images and starting...
  docker compose up --build --force-recreate
) else (
  echo [pea] Building and starting full stack (first run pulls images and creates tables, please wait)...
  docker compose up --build
)

if %DETACH%==1 (
  echo [pea] Starting in background, waiting for dependencies...
  timeout /t 20 >nul
  echo [OK] Service URLs:
  echo    Web            http://localhost:8080
  echo    BFF API        http://localhost:4000
  echo    Orchestrator   http://localhost:8000/api/health
  echo    MinIO console  http://localhost:9001  (minioadmin/minioadmin)
  start "" "http://localhost:8080"
  echo [pea] Logs: start.cmd --logs    Stop: start.cmd --down
)
endlocal
