@echo off
chcp 65001 >nul 2>&1

echo ============================================
echo   DingtalkFriday - Docker Production Deploy
echo ============================================
echo.

docker --version >nul 2>&1
if errorlevel 1 goto :no_docker

docker compose version >nul 2>&1
if errorlevel 1 goto :no_compose

if not exist .env goto :no_env

if not exist backend\data mkdir backend\data

echo [1/3] Stopping old containers...
docker compose down

echo.
echo [2/3] Building and starting containers...
docker compose up -d --build
if errorlevel 1 goto :build_fail

echo.
echo [3/3] Waiting for services...
timeout /t 5 /nobreak >nul

:: Read ports from .env
set "FRONTEND_PORT=80"
set "BACKEND_PORT=8000"
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="FRONTEND_PORT" set "FRONTEND_PORT=%%B"
    if "%%A"=="BACKEND_PORT" set "BACKEND_PORT=%%B"
)

curl -sf http://localhost:%BACKEND_PORT%/api/health >nul 2>&1
if errorlevel 1 goto :not_ready

echo [OK] Backend is ready.
goto :done

:no_docker
echo [ERROR] Docker not found. Please install Docker Desktop.
goto :end

:no_compose
echo [ERROR] Docker Compose not found.
goto :end

:no_env
echo [ERROR] .env not found in project root.
echo Please copy .env.example to .env and fill in config.
goto :end

:build_fail
echo [ERROR] Build failed. Check errors above.
goto :end

:not_ready
echo [INFO] Backend is still starting, please wait...

:done
echo.
echo ============================================
echo   Deploy complete!
echo   Frontend: http://localhost:%FRONTEND_PORT%
echo   Backend:  http://localhost:%BACKEND_PORT%/api/health
echo   Logs:     docker compose logs -f
echo   Stop:     docker compose down
echo ============================================

:end
pause
