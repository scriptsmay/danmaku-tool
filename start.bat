@echo off
:: danmaku-tool 启动脚本
cd /d "%~dp0"

:: 检查 uv
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv 未安装，请先安装: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

:: 检查 FFmpeg
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg 不在 PATH 中，请确保 .env 中已配置 DANMAKU_FFMPEG_PATH
)

:: 同步依赖
echo [INFO] 同步依赖...
uv sync --quiet

:: 启动服务
echo [INFO] 启动 danmaku-tool...
echo [INFO] 访问地址: http://localhost:8000
start "danmaku-tool" /min uv run uvicorn danmaku_tool.main:app --host 127.0.0.1 --port 8000

echo [INFO] 服务已在后台启动
echo [INFO] 停止请运行 stop.bat
