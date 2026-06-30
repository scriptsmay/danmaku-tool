# Prevents Windows idle sleep while danmaku-tool is running.
# Calls Win32 SetThreadExecutionState to signal "system required".
# When this process is terminated, Windows resets the flags automatically.

$pidFile = Join-Path $env:TEMP "danmaku-awaker.pid"
$PID | Out-File -FilePath $pidFile -Encoding ascii -Force

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class PowerManager {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
    public const uint ES_CONTINUOUS       = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED  = 0x00000001;
    public const uint ES_RESET            = 0x00000000;
}
"@

# ES_CONTINUOUS | ES_SYSTEM_REQUIRED: tell Windows "I'm busy, don't sleep"
$result = [PowerManager]::SetThreadExecutionState(
    [PowerManager]::ES_CONTINUOUS -bor [PowerManager]::ES_SYSTEM_REQUIRED
)

if ($result -eq 0) {
    Write-Warning "SetThreadExecutionState failed, sleep prevention not active"
    exit 1
}

Write-Host "[awaker] Sleep prevention active (PID $PID)"

# Keep the thread alive. Ctrl+C or taskkill triggers the finally block.
try {
    while ($true) { Start-Sleep 30 }
} finally {
    [PowerManager]::SetThreadExecutionState([PowerManager]::ES_RESET)
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}
