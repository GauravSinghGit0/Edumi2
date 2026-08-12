@echo off
title EduMi 2 Startup Manager
echo ===================================================
echo             EduMi 2 - Windows One-Click Launcher
echo ===================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .\venv
    echo Please create it first using: python -m venv venv
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

if not exist ".env" (
    echo [INFO] Creating .env from config\.env.example...
    copy config\.env.example .env
)

echo [1/5] Checking Database Migrations...
python manage.py migrate --noinput

echo [2/5] Starting LiveKit SFU Server...
if exist "livekit-bin\livekit-server.exe" (
    start "EduMi2 - LiveKit Server" cmd /k "venv\Scripts\activate.bat && .\livekit-bin\livekit-server.exe --config config\livekit.yaml"
) else (
    echo [WARNING] livekit-server.exe not found in .\livekit-bin\. Skipping LiveKit startup.
)

echo [3/5] Starting Camera Microservice...
start "EduMi2 - Camera Service (Port 8003)" cmd /k "venv\Scripts\activate.bat && python camera_service/serve.py"

echo [4/5] Starting Celery Worker...
start "EduMi2 - Celery Worker" cmd /k "venv\Scripts\activate.bat && celery -A school_project worker -l info -P threads"

echo [5/5] Starting Daphne Web Server (HTTPS)...
echo.
echo ===================================================
echo  EduMi 2 is starting!
echo  Access URL: https://localhost:8002
echo ===================================================
echo.
python run_ssl_server.py

pause
