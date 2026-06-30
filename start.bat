@echo off
cd /d "%~dp0"

where.exe uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv not installed. Install: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

where.exe ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg not in PATH. Set DANMAKU_FFMPEG_PATH in .env
)

echo [INFO] Syncing dependencies...
uv sync --quiet

echo [INFO] Starting danmaku-tool (check .env for host/port)...
start "danmaku-tool" /min uv run python -m danmaku_tool.main

:: Prevent Windows idle sleep while service is running
echo [INFO] Starting sleep prevention...
start "danmaku-awaker" /min powershell -ExecutionPolicy Bypass -WindowStyle Hidden -Command "& \"%~dp0scripts\awaker.ps1\""

echo [INFO] Service started. Run stop.bat to stop.
echo [INFO] Sleep prevention active - laptop won't auto-sleep during tasks.
