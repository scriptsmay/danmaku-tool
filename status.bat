@echo off
setlocal
set PORT=18000

echo [INFO] Checking danmaku-tool status...
echo.
echo [INFO] Port %PORT% listeners:
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess | Sort-Object OwningProcess,LocalAddress | Format-Table -AutoSize"

echo.
echo [INFO] Listener process details:
powershell -NoProfile -Command "$listenerPids = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique); if ($listenerPids.Count -eq 0) { Write-Host 'No listening process.' } else { Get-CimInstance Win32_Process | Where-Object { $listenerPids -contains $_.ProcessId } | Select-Object ProcessId,ParentProcessId,Name,CreationDate,CommandLine | Format-List }"

echo.
curl.exe --noproxy "*" -s http://127.0.0.1:%PORT%/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] danmaku-tool is running: http://127.0.0.1:%PORT%
    echo.
    curl.exe --noproxy "*" -s http://127.0.0.1:%PORT%/api/health
    echo.
) else (
    echo [STOPPED] danmaku-tool did not respond at http://127.0.0.1:%PORT%
)

endlocal
