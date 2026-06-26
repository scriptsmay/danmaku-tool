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

echo [INFO] Service started. Run stop.bat to stop.
