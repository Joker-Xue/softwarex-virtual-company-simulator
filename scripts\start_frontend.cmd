@echo off
setlocal EnableExtensions

set "FRONTEND_DIR=%~1"

if "%FRONTEND_DIR%"=="" set "FRONTEND_DIR=%CP_FRONTEND_DIR%"

if "%FRONTEND_DIR%"=="" (
    echo [ERROR] FRONTEND_DIR missing
    exit /b 1
)

pushd "%FRONTEND_DIR%"
if errorlevel 1 (
    echo [ERROR] Unable to enter frontend dir: %FRONTEND_DIR%
    exit /b 1
)

set "VITE_API_BASE=http://localhost:8000"
set "FRONTEND_PROJECT_ROOT=%FRONTEND_DIR%"
echo [INFO] Starting frontend in %FRONTEND_DIR%
npm run dev -- --host localhost --port 5173
exit /b %errorlevel%

