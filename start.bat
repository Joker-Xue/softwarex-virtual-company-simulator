@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Career Planner - Full Stack Launcher

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "FRONTEND_DIR=%PROJECT_DIR%\src\frontend"
set "BACKEND_BOOTSTRAP=%PROJECT_DIR%\scripts\start_backend.cmd"
set "FRONTEND_BOOTSTRAP=%PROJECT_DIR%\scripts\start_frontend.cmd"
set "CHECK_ONLY=0"

if /I "%~1"=="--check-only" set "CHECK_ONLY=1"

echo ============================================
echo   Career Planner Full Stack Launcher
echo ============================================
echo Project dir: %PROJECT_DIR%
echo.

if not exist "%PROJECT_DIR%\.env" (
    echo [ERROR] Missing .env file
    echo Create .env from .env.example before starting the stack
    exit /b 1
)

set "PYTHON_EXE="
if exist "%PROJECT_DIR%\venv_new\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%\venv_new\Scripts\python.exe"
) else if exist "%PROJECT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_DIR%\venv\Scripts\python.exe"
)

if not defined PYTHON_EXE (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python was not found
        echo Prepare venv_new in the project root or install Python 3.11+
        exit /b 1
    )
    set "PYTHON_EXE=python"
)

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found. Install Node.js 20+
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm was not found. Check the Node.js installation
    exit /b 1
)

echo [CHECK] Python: %PYTHON_EXE%
call "%PYTHON_EXE%" --version
if errorlevel 1 (
    echo [ERROR] Python could not be executed
    exit /b 1
)

echo [CHECK] Node:
call node --version
if errorlevel 1 (
    echo [ERROR] Node.js could not be executed
    exit /b 1
)

echo [CHECK] npm:
call npm --version
if errorlevel 1 (
    echo [ERROR] npm could not be executed
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] Frontend package.json not found: %FRONTEND_DIR%
    exit /b 1
)

echo [CHECK] Python packages
call "%PYTHON_EXE%" -m pip install -r "%PROJECT_DIR%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed
    exit /b 1
)

echo [CHECK] Frontend packages
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] node_modules not found. Installing frontend dependencies
    pushd "%FRONTEND_DIR%"
    if exist "%FRONTEND_DIR%\package-lock.json" (
        call npm ci
    ) else (
        call npm install
    )
    if errorlevel 1 (
        popd
        echo [ERROR] Frontend dependency installation failed
        exit /b 1
    )
    popd
)

echo [CHECK] Ports
call :check_port 8000 "backend"
if errorlevel 1 exit /b 1
call :check_port 5174 "frontend"
if errorlevel 1 exit /b 1

echo [CHECK] Bootstrap scripts
if not exist "%BACKEND_BOOTSTRAP%" (
    echo [ERROR] Missing backend bootstrap script: %BACKEND_BOOTSTRAP%
    exit /b 1
)
if not exist "%FRONTEND_BOOTSTRAP%" (
    echo [ERROR] Missing frontend bootstrap script: %FRONTEND_BOOTSTRAP%
    exit /b 1
)

if "%CHECK_ONLY%"=="1" (
    echo.
    echo [OK] Preflight check passed
    exit /b 0
)

echo.
echo [START] Backend window
set "CP_PROJECT_DIR=%PROJECT_DIR%"
set "CP_PYTHON_EXE=%PYTHON_EXE%"
start "Career Planner Backend" /D "%PROJECT_DIR%" cmd /k call "%BACKEND_BOOTSTRAP%"

echo [CHECK] Backend route gate (wait up to 45s)
set "SIM_ROUTE_OK="
set "SIM_PATHS="
set /a RETRIES=15
:route_gate_retry
for /f "delims=" %%a in ('powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; try { $paths=(Invoke-RestMethod 'http://localhost:8000/openapi.json').paths.PSObject.Properties.Name | Where-Object { $_ -like '/api/simulation*' }; if($paths){ $joined=($paths -join ','); if(($paths -contains '/api/simulation/rebuild-npcs') -and ($paths -contains '/api/simulation/diagnostics')){ Write-Output ('OK|' + $joined) } else { Write-Output ('MISS|' + $joined) } } else { Write-Output 'WAIT|' } } catch { Write-Output 'WAIT|' }"') do (
    set "SIM_GATE_RAW=%%a"
)
for /f "tokens=1,* delims=|" %%a in ("!SIM_GATE_RAW!") do (
    set "SIM_ROUTE_OK=%%a"
    set "SIM_PATHS=%%b"
)

if /I "!SIM_ROUTE_OK!"=="OK" goto route_gate_pass

set /a RETRIES-=1
if !RETRIES! LEQ 0 goto route_gate_fail
timeout /t 3 /nobreak >nul
goto route_gate_retry

:route_gate_pass
echo [OK] Backend route gate passed

goto after_route_gate

:route_gate_fail
echo [ERROR] Backend route gate failed: missing /api/simulation/rebuild-npcs or /api/simulation/diagnostics
if not "!SIM_PATHS!"=="" (
    echo [ERROR] Current /api/simulation routes: !SIM_PATHS!
) else (
    echo [ERROR] Backend did not respond with openapi within timeout window.
)
echo [ERROR] This usually means an old backend instance is being served or backend startup is blocked.
echo [ERROR] Please close backend windows/processes and rerun start.bat.
exit /b 1

:after_route_gate

echo [START] Frontend window
set "CP_FRONTEND_DIR=%FRONTEND_DIR%"
start "Career Planner Frontend" /D "%FRONTEND_DIR%" cmd /k call "%FRONTEND_BOOTSTRAP%"

echo.
echo ============================================
echo   Stack started
echo ============================================
echo Frontend: http://localhost:5174
echo Backend:  http://localhost:8000
echo Docs:     http://localhost:8000/docs
echo Alt loopback (also supported): http://127.0.0.1:5174
echo.
echo Close the two spawned terminal windows to stop the stack
echo.
exit /b 0

:check_port
set "PORT=%~1"
set "PORT_NAME=%~2"
set "PORT_BUSY="
for /f %%a in ('powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess; if(-not $c){$line=(netstat -ano ^| Select-String ':%PORT%\s+.*LISTENING' ^| Select-Object -First 1).Line; if($line){$parts=$line -split '\s+'; $c=$parts[-1]}}; if($c){Write-Output $c}"') do (
    set "PORT_BUSY=%%a"
)
if defined PORT_BUSY (
    echo [ERROR] %PORT_NAME% port %PORT% is already in use. PID=!PORT_BUSY!
    echo Stop the conflicting process first, then rerun this script
    exit /b 1
)
echo [OK] %PORT_NAME% port %PORT% is free
exit /b 0

