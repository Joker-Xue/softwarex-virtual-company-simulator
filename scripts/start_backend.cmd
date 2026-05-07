@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~1"
set "PYTHON_EXE=%~2"

if "%PROJECT_DIR%"=="" set "PROJECT_DIR=%CP_PROJECT_DIR%"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=%CP_PYTHON_EXE%"

if "%PROJECT_DIR%"=="" (
    echo [ERROR] PROJECT_DIR missing
    exit /b 1
)
if "%PYTHON_EXE%"=="" (
    echo [ERROR] PYTHON_EXE missing
    exit /b 1
)

pushd "%PROJECT_DIR%"
if errorlevel 1 (
    echo [ERROR] Unable to enter project dir: %PROJECT_DIR%
    exit /b 1
)

set "BACKEND_PORT=8000"

for /f %%a in ('powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %BACKEND_PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess; if($c){Write-Output $c}"') do (
    set "PORT_PID=%%a"
)
if defined PORT_PID (
    echo [ERROR] Backend port %BACKEND_PORT% is already in use. PID=%PORT_PID%
    echo Stop existing backend process before starting a new one.
    exit /b 1
)

for /f %%a in ('powershell -NoProfile -Command "$procs=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue ^| Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'app\.main:app' }; if($procs){$procs ^| ForEach-Object { $_.ProcessId }}"') do (
    set "UVICORN_PID=%%a"
)
if defined UVICORN_PID (
    echo [ERROR] Existing uvicorn app.main:app process detected. PID=%UVICORN_PID%
    echo Refusing to start duplicate backend instance.
    exit /b 1
)

set "CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174"
echo [INFO] Starting backend with %PYTHON_EXE%
"%PYTHON_EXE%" -m uvicorn app.main:app --host localhost --port 8000 --reload
exit /b %errorlevel%
