# TheWatcher Smoke Test — is it running and producing fresh status?
# Exit codes: 0=healthy, 1=warning, 2=error
# Usage: powershell aws/test_watcher_smoke.ps1

$StatusFile = 'c:\libraries\PrismataAI\aws\watcher_status.json'
$LogFile = 'c:\libraries\PrismataAI\aws\watcher_log.txt'
$exitCode = 0

Write-Host "=== TheWatcher Smoke Test ==="
Write-Host ""

# 1. Status file exists and is recent
if (Test-Path $StatusFile) {
    $status = Get-Content $StatusFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $lastCheck = [datetime]::Parse($status.last_check)
    $ageMins = [int]((Get-Date) - $lastCheck).TotalMinutes

    if ($ageMins -le 6) {
        Write-Host "[PASS] Status file updated $ageMins min ago (within 5-min cycle)"
    } elseif ($ageMins -le 15) {
        Write-Host "[WARN] Status file is $ageMins min old (1-3 missed cycles)"
        $exitCode = [math]::Max($exitCode, 1)
    } else {
        Write-Host "[FAIL] Status file is $ageMins min old (TheWatcher may be dead)"
        $exitCode = 2
    }
} else {
    Write-Host "[FAIL] Status file not found at $StatusFile"
    exit 2
}

# 2. Task Scheduler job exists and is enabled
$task = Get-ScheduledTask -TaskName 'PrismataAI-TheWatcher' -ErrorAction SilentlyContinue
if ($task) {
    if ($task.State -eq 'Ready' -or $task.State -eq 'Running') {
        Write-Host "[PASS] Task Scheduler job exists (state: $($task.State))"
    } else {
        Write-Host "[WARN] Task Scheduler job exists but state is: $($task.State)"
        $exitCode = [math]::Max($exitCode, 1)
    }
} else {
    Write-Host "[FAIL] Task Scheduler job 'PrismataAI-TheWatcher' not found"
    $exitCode = 2
}

# 3. Log file exists and is growing
if (Test-Path $LogFile) {
    $logSize = (Get-Item $LogFile).Length
    $logAge = [int]((Get-Date) - (Get-Item $LogFile).LastWriteTime).TotalMinutes
    Write-Host "[$(if ($logAge -le 10) {'PASS'} else {'WARN'})] Log file: $([math]::Round($logSize/1024))KB, last write $logAge min ago"
    if ($logAge -gt 10) { $exitCode = [math]::Max($exitCode, 1) }
} else {
    Write-Host "[WARN] Log file not found"
    $exitCode = [math]::Max($exitCode, 1)
}

# 4. API health
if ($status.api_health) {
    $awsOk = $status.api_health.aws_api_success
    $gcpOk = $status.api_health.gcp_api_success
    $awsFails = [int]$status.api_health.consecutive_aws_failures
    $gcpFails = [int]$status.api_health.consecutive_gcp_failures

    Write-Host "[$(if ($awsOk) {'PASS'} else {'FAIL'})] AWS API: $(if ($awsOk) {'reachable'} else {"FAILED ($awsFails consecutive)"})"
    Write-Host "[$(if ($gcpOk) {'PASS'} else {'FAIL'})] GCP API: $(if ($gcpOk) {'reachable'} else {"FAILED ($gcpFails consecutive)"})"

    if (-not $awsOk -or -not $gcpOk) { $exitCode = [math]::Max($exitCode, 1) }
    if ($awsFails -ge 3 -or $gcpFails -ge 3) { $exitCode = 2 }
} else {
    Write-Host "[INFO] API health fields not present (pre-upgrade status file)"
}

# 5. Shard activity
if ($status.shard_activity) {
    $shardsLastHour = [int]$status.shard_activity.shards_last_hour
    $lastShard = $status.shard_activity.last_new_shard
    Write-Host "[INFO] S3 shards in last hour: $shardsLastHour (last: $lastShard)"

    $totalRunning = [int]$status.selfplay.ec2_running + [int]$status.gcp.running
    if ($totalRunning -gt 0 -and $shardsLastHour -eq 0) {
        Write-Host "[WARN] $totalRunning instances running but 0 shards in last hour!"
        $exitCode = [math]::Max($exitCode, 1)
    }
}

# 6. Health warnings
if ($status.health -and $status.health.warnings -and $status.health.warnings.Count -gt 0) {
    foreach ($w in $status.health.warnings) {
        Write-Host "[WARN] $w"
    }
    $exitCode = [math]::Max($exitCode, 1)
}

Write-Host ""
Write-Host "Result: $(if ($exitCode -eq 0) {'HEALTHY'} elseif ($exitCode -eq 1) {'WARNING'} else {'ERROR'})"
exit $exitCode
