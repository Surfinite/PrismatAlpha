# TheWatcher - Persistent multi-cloud self-play monitor and auto-relauncher
# Registered as Task Scheduler job, runs every 5 minutes.
# Monitors AWS EC2, GCP Compute Engine, and Azure instances.
# Claude Code: READ watcher_status.json for state. EDIT watcher_config.json to change behavior.
# NEVER kill this task or unregister it from Task Scheduler.

$ErrorActionPreference = 'Continue'
$ProjectDir = 'c:\libraries\PrismataAI'
$ConfigFile = Join-Path $ProjectDir 'aws\watcher_config.json'
$StatusFile = Join-Path $ProjectDir 'aws\watcher_status.json'
$LogFile = Join-Path $ProjectDir 'aws\watcher_log.txt'
$AwsRegion = 'eu-north-1'
$Bucket = 'prismata-selfplay-data'
$VcpusPerInstance = 8

# Ensure cloud CLIs are in PATH
$env:Path += ';C:\Program Files\Amazon\AWSCLIV2;C:\google-cloud-sdk\bin;C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin'

function Log {
    param([string]$msg)
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $LogFile -Value "[$ts] $msg"
}

function CountLines {
    param([string]$text)
    if ([string]::IsNullOrWhiteSpace($text)) { return 0 }
    return @(($text -split "`r?`n") | Where-Object { $_.Trim() }).Count
}

function Invoke-CloudApi {
    param(
        [string]$Provider,
        [string]$Operation,
        [scriptblock]$Command
    )
    try {
        $rawResult = & $Command 2>&1
        $stderr = @($rawResult | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] }) -join '; '
        $stdout = @($rawResult | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] }) -join "`n"

        if ($stderr -and $stderr.Trim()) {
            # Suppress known gcloud.cmd tmpfile noise (Tamper Protection + Task Scheduler CWD)
            $filteredStderr = $stderr -replace 'Access is denied\.;\s*', '' -replace 'The system cannot find the file specified\.;\s*', '' -replace 'Could Not Find C:\\Windows\\System32\\tmpfile;\s*', ''
            $filteredStderr = $filteredStderr.Trim('; ').Trim()
            if ($filteredStderr) {
                Log "WARNING: $Provider $Operation stderr: $filteredStderr"
            }
        }
        return @{ Success = $true; Output = $stdout; Error = $null }
    } catch {
        $errMsg = $_.Exception.Message
        Log "ERROR: $Provider $Operation FAILED: $errMsg"
        return @{ Success = $false; Output = $null; Error = $errMsg }
    }
}

# Load config
if (!(Test-Path $ConfigFile)) {
    Log 'No config file found, skipping.'
    exit 0
}
$config = Get-Content $ConfigFile -Raw | ConvertFrom-Json

# Shared launch helpers
$gitBash = 'C:\Program Files\Git\bin\bash.exe'
$projPath = $ProjectDir -replace '\\','/'

# ============================================================
# AWS EC2 Instance Counting
# ============================================================
$selfplayAlive = 0
$selfplayRunning = 0
$selfplayOnDemand = 0
$selfplaySpot = 0
$awsApiSuccess = $false

$r = Invoke-CloudApi 'AWS' 'describe-selfplay-alive' {
    aws ec2 describe-instances --filters 'Name=instance-state-name,Values=running,pending,shutting-down' 'Name=tag:Name,Values=PrismataSelfPlay-*' --query 'Reservations[].Instances[].InstanceId' --output text --region $AwsRegion
}
if ($r.Success) {
    $awsApiSuccess = $true
    if ($r.Output -and $r.Output.Trim()) { $selfplayAlive = ($r.Output.Trim() -split '\s+').Count }

    $r2 = Invoke-CloudApi 'AWS' 'describe-selfplay-running' {
        aws ec2 describe-instances --filters 'Name=instance-state-name,Values=running,pending' 'Name=tag:Name,Values=PrismataSelfPlay-*' --query 'Reservations[].Instances[].InstanceId' --output text --region $AwsRegion
    }
    if ($r2.Success -and $r2.Output -and $r2.Output.Trim()) { $selfplayRunning = ($r2.Output.Trim() -split '\s+').Count }

    # Count spot instances (on-demand = total running - spot, since on-demand lacks instance-lifecycle attribute)
    $r3 = Invoke-CloudApi 'AWS' 'describe-selfplay-spot' {
        aws ec2 describe-instances --filters 'Name=instance-state-name,Values=running,pending' 'Name=tag:Name,Values=PrismataSelfPlay-*' 'Name=instance-lifecycle,Values=spot' --query 'Reservations[].Instances[].InstanceId' --output text --region $AwsRegion
    }
    if ($r3.Success -and $r3.Output -and $r3.Output.Trim()) { $selfplaySpot = ($r3.Output.Trim() -split '\s+').Count }
    $selfplayOnDemand = $selfplayRunning - $selfplaySpot
} else {
    Log 'AWS EC2 API unreachable. Instance counts unknown.'
}

# AWS Eval instances
$evalAlive = 0
$rEval = Invoke-CloudApi 'AWS' 'describe-eval-instances' {
    aws ec2 describe-instances --filters 'Name=instance-state-name,Values=running,pending,shutting-down' 'Name=tag:Name,Values=PrismataEval-*' --query 'Reservations[].Instances[].InstanceId' --output text --region $AwsRegion
}
if ($rEval.Success -and $rEval.Output -and $rEval.Output.Trim()) { $evalAlive = ($rEval.Output.Trim() -split '\s+').Count }

# ============================================================
# GCP Compute Engine Instance Counting
# ============================================================
$gcpAlive = 0
$gcpRunning = 0
$gcpSpot = 0
$gcpStandard = 0
$gcpEnabled = $false
$gcpApiSuccess = $false

if ($config.gcp -and $config.gcp.enabled) {
    $gcpEnabled = $true
    $GcpProject = $config.gcp.project
    $GcpZone = $config.gcp.zone
    $GcpRegion = ($GcpZone -replace '-[a-z]$', '')

    $rg = Invoke-CloudApi 'GCP' 'list-instances-alive' {
        gcloud.cmd compute instances list --project=$GcpProject --filter="name~'^prismata-selfplay-' AND status:(RUNNING PROVISIONING STAGING STOPPING)" --format="value(name)"
    }
    if ($rg.Success) {
        $gcpApiSuccess = $true
        $gcpAlive = CountLines $rg.Output

        $rg2 = Invoke-CloudApi 'GCP' 'list-instances-running' {
            gcloud.cmd compute instances list --project=$GcpProject --filter="name~'^prismata-selfplay-' AND status:(RUNNING PROVISIONING STAGING)" --format="value(name)"
        }
        if ($rg2.Success) { $gcpRunning = CountLines $rg2.Output }

        $rg3 = Invoke-CloudApi 'GCP' 'list-instances-spot' {
            gcloud.cmd compute instances list --project=$GcpProject --filter="name~'^prismata-selfplay-' AND status:(RUNNING PROVISIONING STAGING) AND scheduling.provisioningModel=SPOT" --format="value(name)"
        }
        if ($rg3.Success) { $gcpSpot = CountLines $rg3.Output }
        $gcpStandard = $gcpRunning - $gcpSpot
    } else {
        Log 'GCP API unreachable. Instance counts unknown.'
    }
}

# ============================================================
# Azure Instance Counting + Stopped VM Cleanup
# ============================================================
$azureAlive = 0
$azureRunning = 0
$azureStopped = 0
$azureEnabled = $false
$azureApiSuccess = $false

if ($config.azure -and $config.azure.enabled) {
    $azureEnabled = $true
    $AzureRG = $config.azure.resource_group
    $AzureLocation = $config.azure.location

    # Count running Azure VMs (no --query: az.cmd mangles JMESPath via cmd.exe)
    $ra = Invoke-CloudApi 'Azure' 'list-vms' {
        az.cmd vm list --resource-group $AzureRG --show-details --output json
    }
    if ($ra.Success -and $ra.Output) {
        $azureApiSuccess = $true
        try {
            $allAzVms = $ra.Output | ConvertFrom-Json
            $azVms = @($allAzVms | Where-Object { $_.name -like 'prsm-*' } | ForEach-Object {
                @{ name = $_.name; state = $_.powerState; size = $_.hardwareProfile.vmSize }
            })
            foreach ($vm in $azVms) {
                if ($vm.state -eq 'VM running') { $azureRunning++; $azureAlive++ }
                elseif ($vm.state -eq 'VM stopped') { $azureStopped++; $azureAlive++ }
            }

            # Deallocate and delete stopped VMs (Stop-Computer only stops OS, still bills)
            foreach ($vm in $azVms) {
                if ($vm.state -eq 'VM stopped') {
                    Log "Azure cleanup: deallocating stopped VM $($vm.name)..."
                    Invoke-CloudApi 'Azure' "deallocate-$($vm.name)" {
                        az.cmd vm deallocate --resource-group $AzureRG --name $vm.name --no-wait
                    } | Out-Null
                }
                if ($vm.state -eq 'VM deallocated') {
                    Log "Azure cleanup: deleting deallocated VM $($vm.name)..."
                    Invoke-CloudApi 'Azure' "delete-$($vm.name)" {
                        az.cmd vm delete --resource-group $AzureRG --name $vm.name --yes --no-wait
                    } | Out-Null
                }
            }
        } catch {
            Log "Azure: failed to parse VM list: $($_.Exception.Message)"
        }
    } elseif ($ra.Success) {
        $azureApiSuccess = $true
    } else {
        Log 'Azure API unreachable. Instance counts unknown.'
    }
}

# ============================================================
# Azure Orphaned Resource Cleanup (NICs, disks, IPs, NSGs)
# ============================================================
$orphanedCounts = @{ nics = 0; disks = 0; ips = 0; nsgs = 0 }
if ($azureEnabled -and $azureApiSuccess) {
    # NICs not attached to any VM (parse full JSON, no --query for az.cmd compat)
    $rNics = Invoke-CloudApi 'Azure' 'list-orphaned-nics' {
        az.cmd network nic list --resource-group $AzureRG --output json
    }
    if ($rNics.Success -and $rNics.Output) {
        try {
            $allNics = $rNics.Output | ConvertFrom-Json
            $orphanedNicList = @($allNics | Where-Object { $null -eq $_.virtualMachine })
            $orphanedCounts.nics = $orphanedNicList.Count
            if ($orphanedNicList.Count -gt 0) {
                Log "Azure cleanup: found $($orphanedNicList.Count) orphaned NICs, deleting..."
                foreach ($nic in $orphanedNicList) {
                    Invoke-CloudApi 'Azure' "delete-nic-$($nic.name)" {
                        az.cmd network nic delete --resource-group $AzureRG --name $nic.name --no-wait
                    } | Out-Null
                }
            }
        } catch {}
    }

    # Unattached disks
    $rDisks = Invoke-CloudApi 'Azure' 'list-orphaned-disks' {
        az.cmd disk list --resource-group $AzureRG --output json
    }
    if ($rDisks.Success -and $rDisks.Output) {
        try {
            $allDisks = $rDisks.Output | ConvertFrom-Json
            $orphanedDiskList = @($allDisks | Where-Object { $_.diskState -eq 'Unattached' })
            $orphanedCounts.disks = $orphanedDiskList.Count
            if ($orphanedDiskList.Count -gt 0) {
                Log "Azure cleanup: found $($orphanedDiskList.Count) orphaned disks, deleting..."
                foreach ($disk in $orphanedDiskList) {
                    Invoke-CloudApi 'Azure' "delete-disk-$($disk.name)" {
                        az.cmd disk delete --resource-group $AzureRG --name $disk.name --yes --no-wait
                    } | Out-Null
                }
            }
        } catch {}
    }

    # Public IPs not associated with any NIC
    $rIps = Invoke-CloudApi 'Azure' 'list-orphaned-ips' {
        az.cmd network public-ip list --resource-group $AzureRG --output json
    }
    if ($rIps.Success -and $rIps.Output) {
        try {
            $allIps = $rIps.Output | ConvertFrom-Json
            $orphanedIpList = @($allIps | Where-Object { $null -eq $_.ipConfiguration })
            $orphanedCounts.ips = $orphanedIpList.Count
            if ($orphanedIpList.Count -gt 0) {
                Log "Azure cleanup: found $($orphanedIpList.Count) orphaned public IPs, deleting..."
                foreach ($ip in $orphanedIpList) {
                    Invoke-CloudApi 'Azure' "delete-ip-$($ip.name)" {
                        az.cmd network public-ip delete --resource-group $AzureRG --name $ip.name --no-wait
                    } | Out-Null
                }
            }
        } catch {}
    }

    # NSGs not attached to any NIC or subnet
    $rNsgs = Invoke-CloudApi 'Azure' 'list-orphaned-nsgs' {
        az.cmd network nsg list --resource-group $AzureRG --output json
    }
    if ($rNsgs.Success -and $rNsgs.Output) {
        try {
            $allNsgs = $rNsgs.Output | ConvertFrom-Json
            $orphanedNsgList = @($allNsgs | Where-Object { ($null -eq $_.networkInterfaces -or $_.networkInterfaces.Count -eq 0) -and ($null -eq $_.subnets -or $_.subnets.Count -eq 0) })
            $orphanedCounts.nsgs = $orphanedNsgList.Count
            if ($orphanedNsgList.Count -gt 0) {
                Log "Azure cleanup: found $($orphanedNsgList.Count) orphaned NSGs, deleting..."
                foreach ($nsg in $orphanedNsgList) {
                    Invoke-CloudApi 'Azure' "delete-nsg-$($nsg.name)" {
                        az.cmd network nsg delete --resource-group $AzureRG --name $nsg.name --no-wait
                    } | Out-Null
                }
            }
        } catch {}
    }
}

# Local processes
$localProcs = @(Get-Process -Name 'Prismata_Testing*' -ErrorAction SilentlyContinue).Count

# ============================================================
# AWS Quotas
# ============================================================
$odQuota = 0
$spotQuota = 0
$rq1 = Invoke-CloudApi 'AWS' 'quota-on-demand' {
    aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --region $AwsRegion --query 'Quota.Value' --output text
}
if ($rq1.Success -and $rq1.Output) { try { $odQuota = [int]$rq1.Output.Trim() } catch {} }

$rq2 = Invoke-CloudApi 'AWS' 'quota-spot' {
    aws service-quotas get-service-quota --service-code ec2 --quota-code L-34B43A08 --region $AwsRegion --query 'Quota.Value' --output text
}
if ($rq2.Success -and $rq2.Output) { try { $spotQuota = [int]$rq2.Output.Trim() } catch {} }

# ============================================================
# GCP Quotas
# ============================================================
$gcpVcpuQuota = 0
$gcpInstanceQuota = 0
$gcpSpotVcpuQuota = 0

$gcpGlobalCpuQuota = 0

if ($gcpEnabled) {
    $rqg = Invoke-CloudApi 'GCP' 'regional-quotas' {
        gcloud.cmd compute regions describe $GcpRegion --project=$GcpProject --format="json(quotas)"
    }
    if ($rqg.Success -and $rqg.Output) {
        try {
            $quotaObj = $rqg.Output | ConvertFrom-Json
            foreach ($q in $quotaObj.quotas) {
                if ($q.metric -eq 'N2_CPUS') { $gcpVcpuQuota = [int]$q.limit }
                if ($q.metric -eq 'INSTANCES') { $gcpInstanceQuota = [int]$q.limit }
                if ($q.metric -eq 'PREEMPTIBLE_CPUS') { $gcpSpotVcpuQuota = [int]$q.limit }
            }
        } catch {}
    }

    # Global CPUS_ALL_REGIONS quota — often the real bottleneck on new accounts
    $rqg2 = Invoke-CloudApi 'GCP' 'global-quotas' {
        gcloud.cmd compute project-info describe --project=$GcpProject --format="json(quotas)"
    }
    if ($rqg2.Success -and $rqg2.Output) {
        try {
            $projObj = $rqg2.Output | ConvertFrom-Json
            foreach ($q in $projObj.quotas) {
                if ($q.metric -eq 'CPUS_ALL_REGIONS') { $gcpGlobalCpuQuota = [int]$q.limit }
            }
        } catch {}
    }
}

# ============================================================
# Azure Quotas
# ============================================================
$azureVcpuQuota = 0

if ($azureEnabled -and $azureApiSuccess) {
    $rqa = Invoke-CloudApi 'Azure' 'vm-usage' {
        az.cmd vm list-usage --location $AzureLocation --output json
    }
    if ($rqa.Success -and $rqa.Output) {
        try {
            $usageObj = $rqa.Output | ConvertFrom-Json
            foreach ($u in $usageObj) {
                if ($u.name.value -eq 'cores') { $azureVcpuQuota = [int]$u.limit }
            }
        } catch {}
    }
}

# ============================================================
# Cost Estimation (approximate hourly rates per instance)
# ============================================================
$costRates = @{
    'c5.2xlarge'           = 0.384   # AWS eu-north-1 on-demand
    'c5.2xlarge_spot'      = 0.14    # approx spot
    'n2-standard-8'        = 0.39    # GCP us-central1
    'n2-standard-4'        = 0.195
    'Standard_D8als_v7'    = 0.31    # Azure North Europe
    'Standard_D8ads_v7'    = 0.34
    'Standard_D8as_v7'     = 0.33
    'Standard_F8als_v7'    = 0.28
    'Standard_F8ads_v7'    = 0.30
    'Standard_F8as_v7'     = 0.29
    'Standard_D8alds_v7'   = 0.30
    'Standard_F8alds_v7'   = 0.28
    'Standard_D8as_v6'     = 0.33
    'Standard_D8ads_v6'    = 0.34
    'Standard_D8als_v6'    = 0.31
    'Standard_D8alds_v6'   = 0.30
    'Standard_F8as_v6'     = 0.29
    'Standard_F8als_v6'    = 0.28
    'Standard_D8s_v6'      = 0.36
    'Standard_D8ds_v6'     = 0.37
}
$defaultAzureRate = 0.32

$awsOnDemandCost = $selfplayOnDemand * $costRates['c5.2xlarge']
$awsSpotCost = $selfplaySpot * $costRates['c5.2xlarge_spot']
$awsEvalCost = $evalAlive * $costRates['c5.2xlarge']
$gcpInstanceType = if ($config.gcp -and $config.gcp.instance_type) { $config.gcp.instance_type } else { 'n2-standard-8' }
$gcpRate = if ($costRates.ContainsKey($gcpInstanceType)) { $costRates[$gcpInstanceType] } else { 0.39 }
$gcpCost = $gcpRunning * $gcpRate

# Azure: sum per-VM since sizes vary across families
$azureCost = 0
if ($azVms) {
    foreach ($vm in $azVms) {
        if ($vm.state -eq 'VM running') {
            $rate = if ($vm.size -and $costRates.ContainsKey($vm.size)) { $costRates[$vm.size] } else { $defaultAzureRate }
            $azureCost += $rate
        }
    }
}
$totalHourlyCost = $awsOnDemandCost + $awsSpotCost + $awsEvalCost + $gcpCost + $azureCost

# ============================================================
# Read previous status for batch tracking
# ============================================================
$prevBatches = 0
$prevTrackedInstances = 0
$prevGcpBatches = 0
$prevGcpTrackedInstances = 0
$prevAzureBatches = 0
$prevAzureTrackedInstances = 0
$staleStatus = $false
$prevSyncTime = ''

if (Test-Path $StatusFile) {
    try {
        $prev = Get-Content $StatusFile -Raw | ConvertFrom-Json
        $prevBatches = $prev.selfplay.batches_launched
        $prevTrackedInstances = $prev.selfplay.tracked_instances
        $prevSyncTime = $prev.s3_sync.last_sync
        if ($prev.gcp) {
            $prevGcpBatches = $prev.gcp.batches_launched
            $prevGcpTrackedInstances = $prev.gcp.tracked_instances
        }
        if ($prev.azure) {
            $prevAzureBatches = $prev.azure.batches_launched
            $prevAzureTrackedInstances = $prev.azure.tracked_instances
        }
        # Boot protection: if status is >30 min stale, don't auto-relaunch.
        $lastCheck = [datetime]::Parse($prev.last_check)
        $minsSinceLastCheck = ((Get-Date) - $lastCheck).TotalMinutes
        if ($minsSinceLastCheck -gt 30) {
            $staleStatus = $true
            # Note: $staleStatus gates all auto-relaunch blocks (lines 447/507/580).
            # Do NOT zero tracked_instances here — that permanently kills auto-relaunch
            # even after status becomes fresh again. The $staleStatus flag is sufficient.
            Log "Status is $([int]$minsSinceLastCheck)min stale. Boot protection: won't auto-relaunch this cycle."
        }
    } catch {}
} else {
    Log 'No status file - first run. Monitoring only.'
}

# ============================================================
# AWS Selfplay auto-relaunch
# ============================================================
$launched = $false
if ($config.selfplay.enabled -and $config.selfplay.auto_relaunch -and (-not $staleStatus) -and $awsApiSuccess) {
    if ($prevTrackedInstances -gt 0 -and $selfplayAlive -eq 0) {
        Log "All $prevTrackedInstances AWS selfplay instances finished. Relaunching..."

        # Sync S3 results locally
        Log 'Syncing S3 results locally...'
        $syncDir = Join-Path $ProjectDir 'bin\training\data\selfplay'
        Invoke-CloudApi 'AWS' 's3-sync-pre-relaunch' { aws s3 sync "s3://$Bucket/results/" $syncDir --region $AwsRegion } | Out-Null

        $spotOnly = $config.selfplay.spot_only -eq $true
        $odCount = if ($spotOnly) { 0 } else { [math]::Floor($odQuota / $VcpusPerInstance) }
        $spotCount = [math]::Floor($spotQuota / $VcpusPerInstance)
        $instanceType = $config.selfplay.instance_type
        $games = $config.selfplay.games_per_instance
        $think = $config.selfplay.think_time
        $mult = $config.selfplay.vm_multiplier

        Log "AWS quotas: on-demand=$odQuota vCPUs/$odCount instances, spot=$spotQuota vCPUs/$spotCount instances"

        $totalLaunched = 0

        # On-demand
        for ($i = 1; $i -le $odCount; $i++) {
            $cmd = "cd '$projPath'; bash aws/launch_selfplay.sh $instanceType $games $think $mult 2>&1"
            $result = & $gitBash -c $cmd | Select-String 'Instance ID'
            if ($result) {
                $id = ($result -split '\s+')[-1]
                Log "  AWS on-demand $i of ${odCount}: $id"
                $totalLaunched++
            } else {
                Log "  AWS on-demand $i of ${odCount}: FAILED"
                break
            }
        }

        # Spot
        for ($i = 1; $i -le $spotCount; $i++) {
            $cmd = "cd '$projPath'; USE_SPOT=true bash aws/launch_selfplay.sh $instanceType $games $think $mult 2>&1"
            $result = & $gitBash -c $cmd | Select-String 'Instance ID'
            if ($result) {
                $id = ($result -split '\s+')[-1]
                Log "  AWS spot $i of ${spotCount}: $id"
                $totalLaunched++
            } else {
                Log "  AWS spot $i of ${spotCount}: FAILED"
                break
            }
        }

        $prevBatches++
        $selfplayRunning = $totalLaunched
        $selfplayAlive = $totalLaunched
        $launched = $true
        Log "AWS batch $prevBatches launched: $totalLaunched instances"
    }
}

# ============================================================
# GCP Selfplay auto-relaunch
# ============================================================
$gcpLaunched = $false
if ($gcpEnabled -and $config.gcp.auto_relaunch -and (-not $staleStatus) -and $gcpApiSuccess) {
    if ($prevGcpTrackedInstances -gt 0 -and $gcpAlive -eq 0) {
        Log "All $prevGcpTrackedInstances GCP selfplay instances finished. Relaunching..."

        # Sync S3 results locally before relaunching
        Log 'Syncing S3 results locally (pre-GCP-relaunch)...'
        $syncDir = Join-Path $ProjectDir 'bin\training\data\selfplay'
        Invoke-CloudApi 'AWS' 's3-sync-pre-gcp-relaunch' { aws s3 sync "s3://$Bucket/results/" $syncDir --region $AwsRegion } | Out-Null
        $lastSync = Get-Date -Format 'o'

        $gcpInstanceType = $config.gcp.instance_type
        $gcpGames = $config.gcp.games_per_instance
        $gcpThink = $config.gcp.think_time
        $gcpMult = $config.gcp.vm_multiplier

        # Determine vCPUs per instance from instance type
        $gcpVcpusPerInst = 8
        if ($gcpInstanceType -match 'standard-(\d+)$|highcpu-(\d+)$') {
            $gcpVcpusPerInst = [int]($Matches[1] + $Matches[2])
        }

        # Effective vCPU limit = min(regional N2_CPUS, global CPUS_ALL_REGIONS)
        $effectiveVcpuLimit = $gcpVcpuQuota
        if ($gcpGlobalCpuQuota -gt 0 -and $gcpGlobalCpuQuota -lt $effectiveVcpuLimit) {
            $effectiveVcpuLimit = $gcpGlobalCpuQuota
        }

        $maxByVcpu = if ($effectiveVcpuLimit -gt 0) { [math]::Floor($effectiveVcpuLimit / $gcpVcpusPerInst) } else { 0 }
        $maxByInstances = if ($gcpInstanceQuota -gt 0) { $gcpInstanceQuota } else { 0 }
        $gcpCount = [math]::Min($maxByVcpu, $maxByInstances)
        if ($gcpCount -lt 1) { $gcpCount = 1 }

        # Calculate remaining vCPUs after main instances
        $mainVcpus = $gcpCount * $gcpVcpusPerInst
        $remainingVcpus = $effectiveVcpuLimit - $mainVcpus

        Log "GCP quotas: N2_CPUS=$gcpVcpuQuota, CPUS_ALL_REGIONS=$gcpGlobalCpuQuota, effective=$effectiveVcpuLimit, INSTANCES=$gcpInstanceQuota"
        Log "GCP plan: ${gcpCount}x $gcpInstanceType (${mainVcpus} vCPUs), remaining=${remainingVcpus} vCPUs"

        # Launch main instances
        $cmd = "export PATH=`"`$PATH:/c/google-cloud-sdk/bin`"; cd '$projPath'; bash gcp/launch_selfplay.sh $gcpInstanceType $gcpGames $gcpThink $gcpMult $gcpCount 2>&1"
        $gcpOutput = & $gitBash -c $cmd 2>&1
        foreach ($line in ($gcpOutput | Select-Object -Last 10)) { Log "  GCP relaunch: $line" }

        # Fill remaining vCPUs with smaller instance if >=2 vCPUs left
        if ($remainingVcpus -ge 2) {
            $fillType = "n2-standard-$remainingVcpus"
            Log "GCP fill: launching 1x $fillType to use remaining $remainingVcpus vCPUs"
            $cmd = "export PATH=`"`$PATH:/c/google-cloud-sdk/bin`"; cd '$projPath'; bash gcp/launch_selfplay.sh $fillType $gcpGames $gcpThink $gcpMult 1 2>&1"
            $gcpOutput = & $gitBash -c $cmd 2>&1
            foreach ($line in ($gcpOutput | Select-Object -Last 5)) { Log "  GCP fill: $line" }
        }

        # Re-count actual GCP instances after launch
        $rRecount = Invoke-CloudApi 'GCP' 'recount-after-relaunch' {
            gcloud.cmd compute instances list --project=$GcpProject --filter="name~'^prismata-selfplay-' AND status:(RUNNING PROVISIONING STAGING)" --format="value(name)"
        }
        if ($rRecount.Success) {
            $gcpRunning = CountLines $rRecount.Output
            $gcpAlive = $gcpRunning
            $gcpStandard = $gcpRunning
        }

        $prevGcpBatches++
        $gcpLaunched = $true
        Log "GCP batch $prevGcpBatches launched: $gcpRunning instances confirmed"
    }
}

# ============================================================
# Azure Selfplay auto-relaunch
# ============================================================
$azureLaunched = $false
if ($azureEnabled -and $config.azure.auto_relaunch -and (-not $staleStatus) -and $azureApiSuccess) {
    if ($prevAzureTrackedInstances -gt 0 -and $azureAlive -eq 0) {
        Log "All $prevAzureTrackedInstances Azure selfplay instances finished. Relaunching..."

        $azVmSize = $config.azure.vm_size
        $azGames = $config.azure.games_per_instance
        $azThink = $config.azure.think_time
        $azMult = $config.azure.vm_multiplier

        # Determine vCPUs from VM size name
        $azVcpusPerInst = 8
        if ($azVmSize -match '[DF](\d+)') { $azVcpusPerInst = [int]$Matches[1] }

        $azCount = if ($azureVcpuQuota -gt 0) { [math]::Floor($azureVcpuQuota / $azVcpusPerInst) } else { 1 }
        if ($azCount -lt 1) { $azCount = 1 }

        Log "Azure plan: ${azCount}x $azVmSize ($azVcpusPerInst vCPUs each, quota=$azureVcpuQuota)"

        $cmd = "cd '$projPath'; bash azure/launch_selfplay.sh $azVmSize $azGames $azThink $azMult $azCount 2>&1"
        $azOutput = & $gitBash -c $cmd 2>&1
        foreach ($line in ($azOutput | Select-Object -Last 10)) { Log "  Azure relaunch: $line" }

        # Re-count actual Azure instances after launch (no --query: az.cmd mangles JMESPath)
        $raRecount = Invoke-CloudApi 'Azure' 'recount-after-relaunch' {
            az.cmd vm list --resource-group $AzureRG --show-details --output json
        }
        if ($raRecount.Success -and $raRecount.Output) {
            try {
                $allAzRecount = $raRecount.Output | ConvertFrom-Json
                $azNames = @($allAzRecount | Where-Object { $_.name -like 'prsm-*' -and $_.powerState -eq 'VM running' })
                $azureRunning = $azNames.Count
                $azureAlive = $azureRunning
            } catch {}
        }

        $prevAzureBatches++
        $azureLaunched = $true
        Log "Azure batch $prevAzureBatches launched: $azureRunning instances confirmed"
    }
}

# ============================================================
# AWS Quota-aware scale-up
# ============================================================
if ($config.selfplay.enabled -and $config.selfplay.auto_relaunch -and (-not $staleStatus) -and (-not $launched) -and $awsApiSuccess -and $selfplayRunning -gt 0) {
    $spotOnly = $config.selfplay.spot_only -eq $true
    $maxOD = if ($spotOnly) { 0 } else { [math]::Floor($odQuota / $VcpusPerInstance) }
    $maxSpot = [math]::Floor($spotQuota / $VcpusPerInstance)
    $slotsOD = $maxOD - $selfplayOnDemand
    $slotsSpot = $maxSpot - $selfplaySpot

    if ($slotsOD -gt 0 -or $slotsSpot -gt 0) {
        Log "AWS scale-up: capacity available! OD: $selfplayOnDemand/$maxOD, Spot: $selfplaySpot/$maxSpot"

        $instanceType = $config.selfplay.instance_type
        $games = $config.selfplay.games_per_instance
        $think = $config.selfplay.think_time
        $mult = $config.selfplay.vm_multiplier
        $scaleUpCount = 0

        # Launch additional on-demand
        for ($i = 1; $i -le $slotsOD; $i++) {
            $cmd = "cd '$projPath'; bash aws/launch_selfplay.sh $instanceType $games $think $mult 2>&1"
            $result = & $gitBash -c $cmd | Select-String 'Instance ID'
            if ($result) {
                $id = ($result -split '\s+')[-1]
                Log "  AWS scale-up on-demand $i of ${slotsOD}: $id"
                $scaleUpCount++
            } else {
                Log "  AWS scale-up on-demand $i of ${slotsOD}: FAILED"
                break
            }
        }

        # Launch additional spot
        for ($i = 1; $i -le $slotsSpot; $i++) {
            $cmd = "cd '$projPath'; USE_SPOT=true bash aws/launch_selfplay.sh $instanceType $games $think $mult 2>&1"
            $result = & $gitBash -c $cmd | Select-String 'Instance ID'
            if ($result) {
                $id = ($result -split '\s+')[-1]
                Log "  AWS scale-up spot $i of ${slotsSpot}: $id"
                $scaleUpCount++
            } else {
                Log "  AWS scale-up spot $i of ${slotsSpot}: FAILED"
                break
            }
        }

        $selfplayRunning += $scaleUpCount
        $selfplayAlive += $scaleUpCount
        Log "AWS scale-up complete: $scaleUpCount new instances (total running: $selfplayRunning)"
    }
}

# ============================================================
# GCP Quota-aware scale-up
# ============================================================
if ($gcpEnabled -and $config.gcp.auto_relaunch -and (-not $staleStatus) -and (-not $gcpLaunched) -and $gcpApiSuccess -and $gcpRunning -gt 0) {
    # Determine vCPUs per configured instance type
    $gcpInstanceType = $config.gcp.instance_type
    $gcpVcpusPerInst = 8
    if ($gcpInstanceType -match 'standard-(\d+)$|highcpu-(\d+)$') {
        $gcpVcpusPerInst = [int]($Matches[1] + $Matches[2])
    }

    # Effective vCPU limit = min(regional N2_CPUS, global CPUS_ALL_REGIONS)
    $effectiveVcpuLimit = $gcpVcpuQuota
    if ($gcpGlobalCpuQuota -gt 0 -and $gcpGlobalCpuQuota -lt $effectiveVcpuLimit) {
        $effectiveVcpuLimit = $gcpGlobalCpuQuota
    }

    # Current vCPU usage (approximate: count instances by type from gcloud)
    $gcpUsedVcpus = 0
    $rmt = Invoke-CloudApi 'GCP' 'list-machine-types' {
        gcloud.cmd compute instances list --project=$($config.gcp.project) --filter="name~'^prismata-selfplay-' AND status:(RUNNING PROVISIONING STAGING)" --format="value(machineType)"
    }
    if ($rmt.Success -and $rmt.Output) {
        foreach ($mt in ($rmt.Output -split "`r?`n")) {
            if ($mt -match 'standard-(\d+)$|highcpu-(\d+)$') {
                $gcpUsedVcpus += [int]($Matches[1] + $Matches[2])
            }
        }
    } else {
        $gcpUsedVcpus = $gcpRunning * $gcpVcpusPerInst
    }

    $freeVcpus = $effectiveVcpuLimit - $gcpUsedVcpus
    $freeSlots = [math]::Floor($freeVcpus / $gcpVcpusPerInst)

    if ($freeSlots -gt 0 -or $freeVcpus -ge 2) {
        Log "GCP scale-up: capacity available! Used: $gcpUsedVcpus/$effectiveVcpuLimit vCPUs, free=$freeVcpus"

        $gcpGames = $config.gcp.games_per_instance
        $gcpThink = $config.gcp.think_time
        $gcpMult = $config.gcp.vm_multiplier

        # Launch full-size instances
        if ($freeSlots -gt 0) {
            $cmd = "export PATH=`"`$PATH:/c/google-cloud-sdk/bin`"; cd '$projPath'; bash gcp/launch_selfplay.sh $gcpInstanceType $gcpGames $gcpThink $gcpMult $freeSlots 2>&1"
            $gcpOutput = & $gitBash -c $cmd 2>&1
            foreach ($line in ($gcpOutput | Select-Object -Last 10)) { Log "  GCP scale-up: $line" }
        }

        # Fill remaining with smaller instance
        $remainingVcpus = $freeVcpus - ($freeSlots * $gcpVcpusPerInst)
        if ($remainingVcpus -ge 2) {
            $fillType = "n2-standard-$remainingVcpus"
            Log "GCP scale-up fill: 1x $fillType ($remainingVcpus vCPUs)"
            $cmd = "export PATH=`"`$PATH:/c/google-cloud-sdk/bin`"; cd '$projPath'; bash gcp/launch_selfplay.sh $fillType $gcpGames $gcpThink $gcpMult 1 2>&1"
            $gcpOutput = & $gitBash -c $cmd 2>&1
            foreach ($line in ($gcpOutput | Select-Object -Last 5)) { Log "  GCP scale-up fill: $line" }
        }

        # Re-count actual GCP instances after scale-up
        $rRecount2 = Invoke-CloudApi 'GCP' 'recount-after-scaleup' {
            gcloud.cmd compute instances list --project=$($config.gcp.project) --filter="name~'^prismata-selfplay-' AND status:(RUNNING PROVISIONING STAGING)" --format="value(name)"
        }
        $newCount = if ($rRecount2.Success) { CountLines $rRecount2.Output } else { $gcpRunning }
        $added = $newCount - $gcpRunning
        $gcpRunning = $newCount
        $gcpAlive = $newCount
        $gcpStandard = $newCount - $gcpSpot
        Log "GCP scale-up complete: $added new instances (total running: $gcpRunning, vCPUs: ~$effectiveVcpuLimit)"
    }
}

# ============================================================
# S3 sync (periodic, even between relaunches)
# ============================================================
$lastSync = ''
if ($config.s3_sync.enabled) {
    $doSync = $true
    if ($prevSyncTime) {
        try {
            $lastSyncTime = [datetime]::Parse($prevSyncTime)
            $minsSince = ((Get-Date) - $lastSyncTime).TotalMinutes
            if ($minsSince -lt $config.s3_sync.interval_minutes) { $doSync = $false }
        } catch { $doSync = $true }
    }
    if ($doSync) {
        Log 'S3 sync running...'
        $syncDir = Join-Path $ProjectDir 'bin\training\data\selfplay'
        $rSync = Invoke-CloudApi 'AWS' 's3-sync' {
            aws s3 sync "s3://$Bucket/results/" $syncDir --region $AwsRegion
        }
        if ($rSync.Success) {
            $lastSync = Get-Date -Format 'o'
            Log 'S3 sync complete.'
        } else {
            Log 'S3 sync FAILED. Data may be stale.'
        }
    }
}

# ============================================================
# S3 Shard Activity Check (proof instances are producing output)
# ============================================================
$shardActivity = @{ last_new_shard = ''; shards_last_hour = 0 }
$rShards = Invoke-CloudApi 'AWS' 's3-shard-activity' {
    aws s3api list-objects-v2 --bucket $Bucket --prefix 'results/' --query "reverse(sort_by(Contents[?ends_with(Key,'.bin')],&LastModified))[:200].[LastModified]" --output text --region $AwsRegion
}
if ($rShards.Success -and $rShards.Output -and $rShards.Output.Trim() -ne 'None') {
    $timestamps = @($rShards.Output.Trim() -split '\s+' | Where-Object { $_.Trim() })
    if ($timestamps.Count -gt 0) {
        $shardActivity.last_new_shard = $timestamps[0]
        $oneHourAgo = (Get-Date).AddHours(-1).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        $shardActivity.shards_last_hour = @($timestamps | Where-Object { $_ -gt $oneHourAgo }).Count
    }
}

# Health warnings
$instancesHealthy = $true
$healthWarnings = @()
$totalCloudRunning = $selfplayRunning + $gcpRunning + $azureRunning
if ($totalCloudRunning -gt 0 -and $shardActivity.shards_last_hour -eq 0) {
    $healthWarnings += "$totalCloudRunning cloud instances running but 0 new shards in last hour"
    $instancesHealthy = $false
}

# Idle fleet detection: VMs running but shard output far below expected
$lowShardSince = $null
$idleThresholdMinutes = 30
$expectedShardsPerHour = $totalCloudRunning * 4  # ~4 shards/hr per instance (conservative)
if ($totalCloudRunning -gt 0 -and $expectedShardsPerHour -gt 0 -and $shardActivity.shards_last_hour -lt ($expectedShardsPerHour / 4)) {
    # Shards are less than 25% of expected — fleet may be idle
    $lowShardSince = if ($prev.health -and $prev.health.low_shard_since) {
        $prev.health.low_shard_since
    } else { $now }

    $lowMinutes = try { ((Get-Date) - [datetime]$lowShardSince).TotalMinutes } catch { 0 }
    if ($lowMinutes -gt $idleThresholdMinutes) {
        $healthWarnings += "IDLE FLEET: $totalCloudRunning VMs running but only $($shardActivity.shards_last_hour) shards/hr for $([int]$lowMinutes) min (expected ~$expectedShardsPerHour)"
        $instancesHealthy = $false
        Log "HEALTH WARNING: Fleet appears idle - $totalCloudRunning running VMs, $($shardActivity.shards_last_hour) shards in last hour, low for $([int]$lowMinutes) min"
    }
}

foreach ($w in $healthWarnings) { Log "HEALTH WARNING: $w" }

# ============================================================
# Write status
# ============================================================
# AWS tracked instances — preserve when API fails to prevent false relaunches
if ($launched -and $selfplayRunning -gt 0) {
    $trackedInstances = $selfplayRunning
} elseif ($launched -and $selfplayRunning -eq 0) {
    $trackedInstances = $prevTrackedInstances
    Log "AWS relaunch confirmed 0 instances. Preserving tracked_instances=$prevTrackedInstances for retry."
} elseif ($awsApiSuccess) {
    $trackedInstances = if ($selfplayAlive -gt 0) { $selfplayAlive } else { 0 }
} else {
    $trackedInstances = $prevTrackedInstances
    Log "AWS API failed. Preserving tracked_instances=$prevTrackedInstances from last cycle."
}

# GCP tracked instances — same logic
if ($gcpLaunched -and $gcpRunning -gt 0) {
    $gcpTrackedInstances = $gcpRunning
} elseif ($gcpLaunched -and $gcpRunning -eq 0) {
    # Launch attempted but 0 instances confirmed (e.g. transient DNS failure).
    # Preserve previous count so relaunch retries next cycle instead of getting stuck at 0.
    $gcpTrackedInstances = $prevGcpTrackedInstances
    Log "GCP relaunch confirmed 0 instances. Preserving tracked_instances=$prevGcpTrackedInstances for retry."
} elseif ($gcpApiSuccess) {
    $gcpTrackedInstances = if ($gcpAlive -gt 0) { $gcpAlive } else { 0 }
} else {
    $gcpTrackedInstances = $prevGcpTrackedInstances
    if ($gcpEnabled) { Log "GCP API failed. Preserving tracked_instances=$prevGcpTrackedInstances from last cycle." }
}

# Azure tracked instances — same logic
if ($azureLaunched -and $azureRunning -gt 0) {
    $azureTrackedInstances = $azureRunning
} elseif ($azureLaunched -and $azureRunning -eq 0) {
    $azureTrackedInstances = $prevAzureTrackedInstances
    Log "Azure relaunch confirmed 0 instances. Preserving tracked_instances=$prevAzureTrackedInstances for retry."
} elseif ($azureApiSuccess) {
    $azureTrackedInstances = if ($azureAlive -gt 0) { $azureAlive } else { 0 }
} else {
    $azureTrackedInstances = $prevAzureTrackedInstances
    if ($azureEnabled) { Log "Azure API failed. Preserving tracked_instances=$prevAzureTrackedInstances from last cycle." }
}

# Consecutive failure escalation — force-reset after 30 min of API failures
$prevAwsFailures = if ($prev.api_health) { [int]$prev.api_health.consecutive_aws_failures } else { 0 }
$prevGcpFailures = if ($prev.api_health) { [int]$prev.api_health.consecutive_gcp_failures } else { 0 }
$prevAzureFailures = if ($prev.api_health) { [int]$prev.api_health.consecutive_azure_failures } else { 0 }
$currentAwsFailures = if ($awsApiSuccess) { 0 } else { $prevAwsFailures + 1 }
$currentGcpFailures = if ($gcpApiSuccess) { 0 } else { $prevGcpFailures + 1 }
$currentAzureFailures = if ($azureApiSuccess) { 0 } else { $prevAzureFailures + 1 }

if ($currentAwsFailures -ge 3) {
    Log "ALERT: AWS API has failed $currentAwsFailures consecutive times (~$($currentAwsFailures * 5) min)"
}
if ($currentGcpFailures -ge 3 -and $gcpEnabled) {
    Log "ALERT: GCP API has failed $currentGcpFailures consecutive times (~$($currentGcpFailures * 5) min)"
}
if ($currentAzureFailures -ge 3 -and $azureEnabled) {
    Log "ALERT: Azure API has failed $currentAzureFailures consecutive times (~$($currentAzureFailures * 5) min)"
}
if ($currentAwsFailures -ge 6 -and -not $awsApiSuccess) {
    Log "AWS API failed for 30+ min. Resetting tracked_instances to 0."
    $trackedInstances = 0
}
if ($currentGcpFailures -ge 6 -and -not $gcpApiSuccess -and $gcpEnabled) {
    Log "GCP API failed for 30+ min. Resetting tracked_instances to 0."
    $gcpTrackedInstances = 0
}
if ($currentAzureFailures -ge 6 -and -not $azureApiSuccess -and $azureEnabled) {
    Log "Azure API failed for 30+ min. Resetting tracked_instances to 0."
    $azureTrackedInstances = 0
}

if ($lastSync) { $syncValue = $lastSync }
elseif ($prevSyncTime) { $syncValue = $prevSyncTime }
else { $syncValue = '' }

$now = Get-Date -Format 'o'
$status = @{
    last_check = $now
    selfplay = @{
        ec2_alive = $selfplayAlive
        ec2_running = $selfplayRunning
        ec2_on_demand = $selfplayOnDemand
        ec2_spot = $selfplaySpot
        local_processes = $localProcs
        tracked_instances = $trackedInstances
        batches_launched = $prevBatches
        auto_relaunch = [bool]$config.selfplay.auto_relaunch
    }
    gcp = @{
        alive = $gcpAlive
        running = $gcpRunning
        standard = $gcpStandard
        spot = $gcpSpot
        tracked_instances = $gcpTrackedInstances
        batches_launched = $prevGcpBatches
        auto_relaunch = if ($gcpEnabled) { [bool]$config.gcp.auto_relaunch } else { $false }
    }
    azure = @{
        alive = $azureAlive
        running = $azureRunning
        stopped = $azureStopped
        tracked_instances = $azureTrackedInstances
        batches_launched = $prevAzureBatches
        auto_relaunch = if ($azureEnabled) { [bool]$config.azure.auto_relaunch } else { $false }
    }
    eval = @{
        ec2_alive = $evalAlive
    }
    s3_sync = @{
        last_sync = $syncValue
    }
    quotas = @{
        aws_on_demand_vcpus = $odQuota
        aws_spot_vcpus = $spotQuota
        gcp_n2_vcpus = $gcpVcpuQuota
        gcp_global_cpus = $gcpGlobalCpuQuota
        gcp_instances = $gcpInstanceQuota
        gcp_spot_vcpus = $gcpSpotVcpuQuota
        azure_vcpus = $azureVcpuQuota
    }
    api_health = @{
        aws_api_success = $awsApiSuccess
        gcp_api_success = $gcpApiSuccess
        azure_api_success = $azureApiSuccess
        aws_last_success = if ($awsApiSuccess) { $now } elseif ($prev.api_health) { $prev.api_health.aws_last_success } else { '' }
        gcp_last_success = if ($gcpApiSuccess) { $now } elseif ($prev.api_health) { $prev.api_health.gcp_last_success } else { '' }
        azure_last_success = if ($azureApiSuccess) { $now } elseif ($prev.api_health) { $prev.api_health.azure_last_success } else { '' }
        consecutive_aws_failures = $currentAwsFailures
        consecutive_gcp_failures = $currentGcpFailures
        consecutive_azure_failures = $currentAzureFailures
    }
    shard_activity = $shardActivity
    health = @{
        healthy = $instancesHealthy
        warnings = $healthWarnings
        low_shard_since = if ($lowShardSince) { $lowShardSince } else { '' }
    }
    cost_estimate = @{
        aws_per_hour = [math]::Round($awsOnDemandCost + $awsSpotCost, 2)
        aws_eval_per_hour = [math]::Round($awsEvalCost, 2)
        gcp_per_hour = [math]::Round($gcpCost, 2)
        azure_per_hour = [math]::Round($azureCost, 2)
        total_per_hour = [math]::Round($totalHourlyCost, 2)
    }
    azure_cleanup = @{
        orphaned_nics = $orphanedCounts.nics
        orphaned_disks = $orphanedCounts.disks
        orphaned_ips = $orphanedCounts.ips
        orphaned_nsgs = $orphanedCounts.nsgs
    }
}

$status | ConvertTo-Json -Depth 3 | Set-Content $StatusFile -Encoding UTF8

# Change detection: compare current cycle against previous
if ($prev) {
    $changes = @()
    # Instance counts
    if ($prev.selfplay -and [int]$prev.selfplay.alive -ne $selfplayAlive) {
        $changes += "AWS instances $([int]$prev.selfplay.alive) -> $selfplayAlive"
    }
    if ($prev.gcp -and [int]$prev.gcp.running -ne $gcpRunning) {
        $changes += "GCP instances $([int]$prev.gcp.running) -> $gcpRunning"
    }
    if ($prev.azure -and [int]$prev.azure.running -ne $azureRunning) {
        $changes += "Azure instances $([int]$prev.azure.running) -> $azureRunning"
    }
    if ($prev.eval -and [int]$prev.eval.ec2_alive -ne $evalAlive) {
        $changes += "Eval instances $([int]$prev.eval.ec2_alive) -> $evalAlive"
    }
    # Quotas
    if ($prev.quotas) {
        if ([int]$prev.quotas.aws_on_demand_vcpus -ne $odQuota -and [int]$prev.quotas.aws_on_demand_vcpus -gt 0) {
            $changes += "AWS on-demand quota $([int]$prev.quotas.aws_on_demand_vcpus) -> $odQuota vCPUs"
        }
        if ([int]$prev.quotas.aws_spot_vcpus -ne $spotQuota -and [int]$prev.quotas.aws_spot_vcpus -gt 0) {
            $changes += "AWS spot quota $([int]$prev.quotas.aws_spot_vcpus) -> $spotQuota vCPUs"
        }
        if ([int]$prev.quotas.gcp_n2_vcpus -ne $gcpVcpuQuota -and [int]$prev.quotas.gcp_n2_vcpus -gt 0) {
            $changes += "GCP N2 quota $([int]$prev.quotas.gcp_n2_vcpus) -> $gcpVcpuQuota vCPUs"
        }
        if ([int]$prev.quotas.gcp_global_cpus -ne $gcpGlobalCpuQuota -and [int]$prev.quotas.gcp_global_cpus -gt 0) {
            $changes += "GCP global CPU quota $([int]$prev.quotas.gcp_global_cpus) -> $gcpGlobalCpuQuota"
        }
        if ([int]$prev.quotas.gcp_instances -ne $gcpInstanceQuota -and [int]$prev.quotas.gcp_instances -gt 0) {
            $changes += "GCP instance quota $([int]$prev.quotas.gcp_instances) -> $gcpInstanceQuota"
        }
        if ([int]$prev.quotas.azure_vcpus -ne $azureVcpuQuota -and [int]$prev.quotas.azure_vcpus -gt 0) {
            $changes += "Azure quota $([int]$prev.quotas.azure_vcpus) -> $azureVcpuQuota vCPUs"
        }
    }
    # API health transitions
    if ($prev.api_health) {
        if ([bool]$prev.api_health.aws_api_success -and -not $awsApiSuccess) { $changes += "AWS API went DOWN" }
        if (-not [bool]$prev.api_health.aws_api_success -and $awsApiSuccess) { $changes += "AWS API recovered" }
        if ([bool]$prev.api_health.gcp_api_success -and -not $gcpApiSuccess -and $gcpEnabled) { $changes += "GCP API went DOWN" }
        if (-not [bool]$prev.api_health.gcp_api_success -and $gcpApiSuccess -and $gcpEnabled) { $changes += "GCP API recovered" }
        if ([bool]$prev.api_health.azure_api_success -and -not $azureApiSuccess -and $azureEnabled) { $changes += "Azure API went DOWN" }
        if (-not [bool]$prev.api_health.azure_api_success -and $azureApiSuccess -and $azureEnabled) { $changes += "Azure API recovered" }
    }
    # Local process count
    $prevLocal = if ($prev.local_processes) { [int]$prev.local_processes } else { 0 }
    if ($prevLocal -ne $localProcs) {
        $changes += "Local processes $prevLocal -> $localProcs"
    }
    # Cost changes (>$1/hr threshold)
    if ($prev.cost_estimate -and $prev.cost_estimate.total_per_hour) {
        $prevCost = [double]$prev.cost_estimate.total_per_hour
        if ([math]::Abs($prevCost - $totalHourlyCost) -gt 1.0) {
            $changes += "Hourly cost `$$([math]::Round($prevCost,2)) -> `$$([math]::Round($totalHourlyCost,2))"
        }
    }
    foreach ($c in $changes) { Log "CHANGE: $c" }
}

# Enhanced log line with failure flags
$apiFlag = ''
if (-not $awsApiSuccess) { $apiFlag += ' [AWS-API-FAIL]' }
if ($gcpEnabled -and -not $gcpApiSuccess) { $apiFlag += ' [GCP-API-FAIL]' }
if ($azureEnabled -and -not $azureApiSuccess) { $apiFlag += ' [AZURE-API-FAIL]' }
if (-not $instancesHealthy) { $apiFlag += ' [HEALTH-WARN]' }
Log "Check: AWS=$selfplayAlive (od=$selfplayOnDemand spot=$selfplaySpot) GCP=$gcpRunning (std=$gcpStandard spot=$gcpSpot) Azure=$azureRunning eval=$evalAlive local=$localProcs quotas=aws:od${odQuota}/spot${spotQuota} gcp:global${gcpGlobalCpuQuota}/n2${gcpVcpuQuota}/inst${gcpInstanceQuota} az:${azureVcpuQuota} shards_1h=$($shardActivity.shards_last_hour) cost=`$$([math]::Round($totalHourlyCost,2))/hr$apiFlag"
