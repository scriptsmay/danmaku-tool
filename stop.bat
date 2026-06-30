@echo off
:: danmaku-tool 停止脚本
echo [INFO] 停止 danmaku-tool...
taskkill /FI "WINDOWTITLE eq danmaku-tool*" /F 2>nul
taskkill /F /IM uvicorn.exe 2>nul
:: Stop sleep prevention via PID file
set "AWAKER_PID="
if exist "%TEMP%\danmaku-awaker.pid" (
    set /p AWAKER_PID=<"%TEMP%\danmaku-awaker.pid" 2>nul
    del "%TEMP%\danmaku-awaker.pid" >nul 2>&1
)
if defined AWAKER_PID (
    taskkill /PID %AWAKER_PID% /F >nul 2>&1
)

if %errorlevel% equ 0 (
    echo [INFO] 已停止（含防休眠进程）
) else (
    echo [INFO] 未找到运行中的实例
)
