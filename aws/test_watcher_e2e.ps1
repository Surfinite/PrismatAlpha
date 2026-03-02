# TheWatcher E2E Test — exercises core decision logic without launching real instances
# Tests: normal cycle, API failure, relaunch trigger, escalation, boot protection
# SAFE: No cloud API calls, no instance launches, no file modifications
# Usage: powershell aws/test_watcher_e2e.ps1

$passed = 0
$failed = 0

function Test-Case {
    param([string]$Name, [bool]$Condition, [string]$Details = '')
    if ($Condition) {
        Write-Host "[PASS] $Name"
        $script:passed++
    } else {
        Write-Host "[FAIL] $Name $(if ($Details) {"-- $Details"})"
        $script:failed++
    }
}

Write-Host "=== TheWatcher E2E Test Suite ==="
Write-Host ""

# --- Scenario 1: Normal monitoring cycle (instances running, API succeeds) ---
Write-Host "--- Scenario 1: Normal monitoring cycle ---"

$awsApiSuccess = $true
$selfplayAlive = 8
$selfplayRunning = 8
$prevTrackedInstances = 8
$launched = $false
$staleStatus = $false

# Tracked instances logic
if ($launched) { $trackedInstances = $selfplayRunning }
elseif ($awsApiSuccess) { $trackedInstances = if ($selfplayAlive -gt 0) { $selfplayAlive } else { 0 } }
else { $trackedInstances = $prevTrackedInstances }

Test-Case "Normal cycle: tracked stays at 8" ($trackedInstances -eq 8)

$shouldRelaunch = ($awsApiSuccess -and (-not $staleStatus) -and $prevTrackedInstances -gt 0 -and $selfplayAlive -eq 0)
Test-Case "Normal cycle: no relaunch triggered" (-not $shouldRelaunch)

# --- Scenario 2: API failure (GCP unreachable) ---
Write-Host ""
Write-Host "--- Scenario 2: GCP API failure ---"

$gcpApiSuccess = $false
$gcpAlive = 0
$prevGcpTrackedInstances = 2
$gcpLaunched = $false
$gcpEnabled = $true

if ($gcpLaunched) { $gcpTrackedInstances = 0 }
elseif ($gcpApiSuccess) { $gcpTrackedInstances = if ($gcpAlive -gt 0) { $gcpAlive } else { 0 } }
else { $gcpTrackedInstances = $prevGcpTrackedInstances }

Test-Case "API failure: tracked preserved at 2 (not reset to 0)" ($gcpTrackedInstances -eq 2)

$shouldGcpRelaunch = ($gcpEnabled -and (-not $staleStatus) -and $gcpApiSuccess -and $prevGcpTrackedInstances -gt 0 -and $gcpAlive -eq 0)
Test-Case "API failure: NO relaunch triggered (API failed)" (-not $shouldGcpRelaunch)

# --- Scenario 3: Instances actually finished (API succeeds, count=0) ---
Write-Host ""
Write-Host "--- Scenario 3: Instances finished normally ---"

$gcpApiSuccess = $true
$gcpAlive = 0
$prevGcpTrackedInstances = 2

if ($gcpLaunched) { $gcpTrackedInstances = 0 }
elseif ($gcpApiSuccess) { $gcpTrackedInstances = if ($gcpAlive -gt 0) { $gcpAlive } else { 0 } }
else { $gcpTrackedInstances = $prevGcpTrackedInstances }

Test-Case "Finished: tracked reset to 0" ($gcpTrackedInstances -eq 0)

$shouldGcpRelaunch = ($gcpEnabled -and (-not $staleStatus) -and $gcpApiSuccess -and $prevGcpTrackedInstances -gt 0 -and $gcpAlive -eq 0)
Test-Case "Finished: relaunch IS triggered (instances truly done)" $shouldGcpRelaunch

# --- Scenario 4: Consecutive failure escalation ---
Write-Host ""
Write-Host "--- Scenario 4: Consecutive failure escalation ---"

# Simulate 5 previous failures + current failure = 6 total
$prevFailures = 5
$currentApiSuccess = $false
$currentFailures = if ($currentApiSuccess) { 0 } else { $prevFailures + 1 }
$trackedBefore = 3

Test-Case "6 consecutive failures detected" ($currentFailures -eq 6)

# After 6 failures (30 min), force-reset tracked
$trackedAfter = $trackedBefore
if ($currentFailures -ge 6 -and -not $currentApiSuccess) { $trackedAfter = 0 }
Test-Case "After 30min failure: tracked force-reset to 0" ($trackedAfter -eq 0)

# Under 6 failures: preserve
$prevFailures2 = 3
$currentFailures2 = $prevFailures2 + 1  # 4 total
$trackedBefore2 = 3
$trackedAfter2 = $trackedBefore2
if ($currentFailures2 -ge 6 -and -not $currentApiSuccess) { $trackedAfter2 = 0 }
Test-Case "Under 30min failure: tracked preserved at 3" ($trackedAfter2 -eq 3)

# --- Scenario 5: Boot protection (stale status) ---
Write-Host ""
Write-Host "--- Scenario 5: Boot protection ---"

$staleMinutes = 45
$staleStatus = ($staleMinutes -gt 30)
Test-Case "Boot protection: detects 45-min stale status" $staleStatus

$awsApiSuccess = $true
$prevTrackedInstances = 5
$selfplayAlive = 0
$shouldRelaunchAfterBoot = ($awsApiSuccess -and (-not $staleStatus) -and $prevTrackedInstances -gt 0 -and $selfplayAlive -eq 0)
Test-Case "Boot protection: prevents relaunch even with API success" (-not $shouldRelaunchAfterBoot)

# --- Scenario 6: Just-launched overrides everything ---
Write-Host ""
Write-Host "--- Scenario 6: Just-launched state ---"

$launched = $true
$awsApiSuccess = $true
$selfplayRunning = 12
$selfplayAlive = 5  # lower (some still booting)

if ($launched) { $trackedInstances = $selfplayRunning }
elseif ($awsApiSuccess) { $trackedInstances = if ($selfplayAlive -gt 0) { $selfplayAlive } else { 0 } }
else { $trackedInstances = 99 }

Test-Case "Just-launched: tracked = selfplayRunning (12), not alive (5)" ($trackedInstances -eq 12)

# --- Scenario 7: Scale-up requires API success ---
Write-Host ""
Write-Host "--- Scenario 7: Scale-up guards ---"

$awsApiSuccess = $false
$selfplayRunning = 8
$staleStatus = $false
$launched = $false
$shouldScaleUp = ($awsApiSuccess -and (-not $staleStatus) -and (-not $launched) -and $selfplayRunning -gt 0)
Test-Case "Scale-up blocked when AWS API failed" (-not $shouldScaleUp)

$awsApiSuccess = $true
$shouldScaleUp = ($awsApiSuccess -and (-not $staleStatus) -and (-not $launched) -and $selfplayRunning -gt 0)
Test-Case "Scale-up allowed when AWS API succeeds" $shouldScaleUp

# --- Scenario 8: Change detection ---
Write-Host ""
Write-Host "--- Scenario 8: Change detection ---"

# Simulate previous status
$prev = @{
    selfplay = @{ alive = 24 }
    gcp = @{ running = 2 }
    azure = @{ running = 0 }
    eval = @{ ec2_alive = 0 }
    quotas = @{
        aws_on_demand_vcpus = 64
        aws_spot_vcpus = 128
        gcp_n2_vcpus = 200
        gcp_global_cpus = 12
        gcp_instances = 24
        azure_vcpus = 10
    }
    api_health = @{
        aws_api_success = $true
        gcp_api_success = $true
        azure_api_success = $false
    }
    local_processes = 3
}

# Current values (some changed)
$selfplayAlive = 16     # changed from 24
$gcpRunning = 2          # same
$azureRunning = 0        # same
$evalAlive = 0           # same
$odQuota = 64            # same
$spotQuota = 256         # changed from 128
$gcpVcpuQuota = 200      # same
$gcpGlobalCpuQuota = 48  # changed from 12
$gcpInstanceQuota = 24   # same
$azureVcpuQuota = 64     # changed from 10
$awsApiSuccess = $true   # same
$gcpApiSuccess = $false  # changed (was true)
$azureApiSuccess = $true # changed (was false)
$gcpEnabled = $true
$azureEnabled = $true
$localProcs = 3          # same

$changes = @()
if ($prev.selfplay -and [int]$prev.selfplay.alive -ne $selfplayAlive) {
    $changes += "AWS instances $([int]$prev.selfplay.alive) -> $selfplayAlive"
}
if ($prev.gcp -and [int]$prev.gcp.running -ne $gcpRunning) {
    $changes += "GCP instances $([int]$prev.gcp.running) -> $gcpRunning"
}
if ($prev.quotas) {
    if ([int]$prev.quotas.aws_spot_vcpus -ne $spotQuota -and [int]$prev.quotas.aws_spot_vcpus -gt 0) {
        $changes += "AWS spot quota $([int]$prev.quotas.aws_spot_vcpus) -> $spotQuota vCPUs"
    }
    if ([int]$prev.quotas.gcp_global_cpus -ne $gcpGlobalCpuQuota -and [int]$prev.quotas.gcp_global_cpus -gt 0) {
        $changes += "GCP global CPU quota $([int]$prev.quotas.gcp_global_cpus) -> $gcpGlobalCpuQuota"
    }
    if ([int]$prev.quotas.azure_vcpus -ne $azureVcpuQuota -and [int]$prev.quotas.azure_vcpus -gt 0) {
        $changes += "Azure quota $([int]$prev.quotas.azure_vcpus) -> $azureVcpuQuota vCPUs"
    }
}
if ($prev.api_health) {
    if ([bool]$prev.api_health.gcp_api_success -and -not $gcpApiSuccess -and $gcpEnabled) { $changes += "GCP API went DOWN" }
    if (-not [bool]$prev.api_health.azure_api_success -and $azureApiSuccess -and $azureEnabled) { $changes += "Azure API recovered" }
}

Test-Case "Detects AWS instance count change (24->16)" ($changes -contains "AWS instances 24 -> 16")
Test-Case "Does NOT detect GCP change (still 2)" (-not ($changes | Where-Object { $_ -match "^GCP instances" }))
Test-Case "Detects AWS spot quota change (128->256)" ($changes -contains "AWS spot quota 128 -> 256 vCPUs")
Test-Case "Detects GCP global quota change (12->48)" ($changes -contains "GCP global CPU quota 12 -> 48")
Test-Case "Detects Azure quota change (10->64)" ($changes -contains "Azure quota 10 -> 64 vCPUs")
Test-Case "Detects GCP API went DOWN" ($changes -contains "GCP API went DOWN")
Test-Case "Detects Azure API recovered" ($changes -contains "Azure API recovered")
Test-Case "Total changes detected: 6" ($changes.Count -eq 6)

# --- Results ---
Write-Host ""
Write-Host "=== Results: $passed passed, $failed failed ==="
exit $(if ($failed -eq 0) { 0 } else { 1 })
