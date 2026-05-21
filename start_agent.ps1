# Pulse v2.4 -- Trading Agent Loop
# Runs one cycle every 5 minutes from 10:00 to 15:00 ET
# Usage: .\start_agent.ps1
# Stop: Ctrl+C

$AGENT_SECRET = "5f0c9188ec1a5697f3c37a9ab6f133c009ae3f6fd93eb5ea5790aa6ff65335c9"
$PROMPT_FILE  = Join-Path $PSScriptRoot "strategies\cycle_prompt.md"
$LOG_FILE     = Join-Path $PSScriptRoot "logs\agent_$(Get-Date -Format 'yyyyMMdd').log"
$CYCLE_SECS   = 300   # 5 minutes

$null = New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "logs")

function Get-ET {
    [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId(
        [DateTime]::UtcNow, "Eastern Standard Time")
}

function Write-Log($msg) {
    $line = "[$((Get-ET).ToString('HH:mm:ss'))] $msg"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8
}

function Run-Cycle {
    $rawPrompt = Get-Content $PROMPT_FILE -Raw -Encoding UTF8
    $prompt    = $rawPrompt -replace "\{\{AGENT_SECRET\}\}", $AGENT_SECRET

    $tmpFile = [System.IO.Path]::GetTempFileName() + ".md"
    Set-Content -Path $tmpFile -Value $prompt -Encoding UTF8

    Write-Log "Cycle start"
    $output = Get-Content $tmpFile | claude --print --dangerously-skip-permissions 2>&1
    Remove-Item $tmpFile -ErrorAction SilentlyContinue

    $output | ForEach-Object { Write-Log "  $_" }
    Write-Log "Cycle end"
}

# Main loop
Write-Log "Agent starting. Ctrl+C to stop."

while ($true) {
    $et = Get-ET
    $h  = $et.Hour
    $m  = $et.Minute

    if ($h -lt 10) {
        $wait = ((10 - $h) * 60 - $m) * 60
        Write-Log "Pre-market. Market opens in ~$([int]($wait/60)) min. Waiting..."
        Start-Sleep -Seconds ([Math]::Min($wait, 300))
        continue
    }

    if ($h -ge 15 -and $m -gt 0) {
        Write-Log "Session ended (ET $($et.ToString('HH:mm'))). Exiting."
        break
    }

    if ($h -eq 15 -and $m -eq 0) {
        Write-Log "15:00 ET -- running final passive cycle."
        Run-Cycle
        Write-Log "Done for today."
        break
    }

    # Active window: 10:00-15:00 ET
    Run-Cycle
    Write-Log "Sleeping $CYCLE_SECS seconds..."
    Start-Sleep -Seconds $CYCLE_SECS
}
