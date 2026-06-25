@echo off
:: danmaku-tool 状态检查脚本
echo [INFO] 检查 danmaku-tool 状态...
curl -s http://localhost:8000/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] danmaku-tool 正在运行
    echo.
    curl -s http://localhost:8000/api/health
    echo.
) else (
    echo [STOPPED] danmaku-tool 未运行
)
