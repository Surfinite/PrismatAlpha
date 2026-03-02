# TheWatcher Log Health Analyzer — detect anomalies in watcher_log.txt
# Detects: repeated errors, stale patterns, rapid relaunch cycles
# Usage: powershell aws/test_watcher_log_health.ps1

$LogFile = 'c:\libraries\PrismataAI\aws\watcher_log.txt'
$problems = @()

if (-not (Test-Path $LogFile)) {
    Write-Host "[FAIL] Log file not found"
    exit 2
}

$lines = Get-Content $LogFile -Tail 200

Write-Host "=== Watcher Log Health Analysis ==="
Write-Host "Analyzing last $($lines.Count) log entries..."
Write-Host ""

# 1. Count error types
$apiErrors = @($lines | Where-Object { $_ -match 'ERROR:' })
$warnings = @($lines | Where-Object { $_ -match 'WARNING:' })
$alerts = @($lines | Where-Object { $_ -match 'ALERT:' })
$apiFailFlags = @($lines | Where-Object { $_ -match '\[.*-API-FAIL\]' })
$healthWarns = @($lines | Where-Object { $_ -match 'HEALTH WARNING:' })

Write-Host "Errors:        $($apiErrors.Count)"
Write-Host "Warnings:      $($warnings.Count)"
Write-Host "Alerts:        $($alerts.Count)"
Write-Host "API fail flags: $($apiFailFlags.Count)"
Write-Host "Health warns:  $($healthWarns.Count)"
Write-Host ""

# 2. Detect repeated identical check lines (sign of stuck state)
$recentChecks = @($lines | Where-Object { $_ -match 'Check: ' })
if ($recentChecks.Count -ge 5) {
    $lastFive = $recentChecks[-5..-1] | ForEach-Object { ($_ -split '] ')[1] }
    $uniqueChecks = $lastFive | Sort-Object -Unique
    if ($uniqueChecks.Count -eq 1) {
        Write-Host "[WARN] Last 5 check lines are IDENTICAL (possible stuck state)"
        Write-Host "  $($lastFive[0])"
        $problems += "5+ identical check lines"
    } else {
        Write-Host "[PASS] Recent checks show variation ($($uniqueChecks.Count) unique patterns in last 5)"
    }
}

# 3. Detect GCP scale-up failures
$gcpScaleUpZero = @($lines | Where-Object { $_ -match 'GCP scale-up complete: 0 new instances' })
if ($gcpScaleUpZero.Count -gt 3) {
    Write-Host "[WARN] GCP scale-up failed $($gcpScaleUpZero.Count) times (0 new instances)"
    $problems += "GCP scale-up repeatedly fails"
} elseif ($gcpScaleUpZero.Count -gt 0) {
    Write-Host "[INFO] GCP scale-up returned 0 new instances $($gcpScaleUpZero.Count) time(s)"
}

# 4. Detect rapid relaunch cycles (sign of launch-fail-relaunch thrashing)
$gcpRelaunches = @($lines | Where-Object { $_ -match 'GCP selfplay instances finished\. Relaunching' })
if ($gcpRelaunches.Count -gt 0) {
    $relaunchTimes = @()
    foreach ($r in $gcpRelaunches) {
        if ($r -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]') {
            $relaunchTimes += [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
        }
    }
    if ($relaunchTimes.Count -ge 2) {
        $intervals = @()
        for ($i = 1; $i -lt $relaunchTimes.Count; $i++) {
            $intervals += ($relaunchTimes[$i] - $relaunchTimes[$i-1]).TotalMinutes
        }
        $avgInterval = ($intervals | Measure-Object -Average).Average
        Write-Host "[INFO] GCP relaunches: $($gcpRelaunches.Count) total, avg interval: $([math]::Round($avgInterval, 1)) min"
        if ($avgInterval -lt 20) {
            Write-Host "[WARN] GCP relaunching very frequently (<20 min avg) -- possible thrashing"
            $problems += "GCP relaunch thrashing"
        }
    } else {
        Write-Host "[INFO] GCP relaunches: $($gcpRelaunches.Count) total"
    }
}

# Same for AWS
$awsRelaunches = @($lines | Where-Object { $_ -match 'AWS selfplay instances finished\. Relaunching' })
if ($awsRelaunches.Count -gt 0) {
    Write-Host "[INFO] AWS relaunches: $($awsRelaunches.Count) in last $($lines.Count) log lines"
}

# 5. Show recent errors
if ($apiErrors.Count -gt 0) {
    Write-Host ""
    Write-Host "Recent errors (last 5):"
    $apiErrors | Select-Object -Last 5 | ForEach-Object { Write-Host "  $_" }
}

# 6. Show recent alerts
if ($alerts.Count -gt 0) {
    Write-Host ""
    Write-Host "Recent alerts (last 5):"
    $alerts | Select-Object -Last 5 | ForEach-Object { Write-Host "  $_" }
}

Write-Host ""
if ($problems.Count -eq 0) {
    Write-Host "Result: LOG HEALTHY (no anomalies detected)"
} else {
    Write-Host "Result: ISSUES DETECTED"
    foreach ($p in $problems) { Write-Host "  - $p" }
}
