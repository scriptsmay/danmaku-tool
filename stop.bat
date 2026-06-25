@echo off
:: danmaku-tool 停止脚本
echo [INFO] 停止 danmaku-tool...
taskkill /FI "WINDOWTITLE eq danmaku-tool*" /F 2>nul
taskkill /F /IM uvicorn.exe 2>nul
if %errorlevel% equ 0 (
    echo [INFO] 已停止
) else (
    echo [INFO] 未找到运行中的实例
)
