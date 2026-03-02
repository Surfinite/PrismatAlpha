#!/bin/bash
# Launch Azure Windows VM instance for self-play generation
# Usage: bash azure/launch_selfplay.sh [VM_SIZE] [NUM_GAMES] [THINK_TIME_S] [VM_MULTIPLIER] [NUM_INSTANCES]
#
# Examples:
#   bash azure/launch_selfplay.sh                                    # Standard_D8als_v7, 5000 games, 1s, 2x, 1 instance
#   bash azure/launch_selfplay.sh Standard_D8als_v7 5000 1 2 4      # 4 instances
#   USE_SPOT=true bash azure/launch_selfplay.sh Standard_D8als_v7 5000 1 2 8  # 8 spot instances

AZ="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az"
export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

# Verify Azure CLI is available
if [ ! -f "$AZ" ]; then
    echo "ERROR: Azure CLI not found at $AZ"
    echo "Install: winget install -e --id Microsoft.AzureCLI"
    exit 1
fi

VM_SIZE="${1:-Standard_D8als_v7}"
NUM_GAMES="${2:-5000}"
THINK_TIME="${3:-1}"
VM_MULTIPLIER="${4:-2}"
NUM_INSTANCES="${5:-1}"
USE_SPOT="${USE_SPOT:-false}"
RESOURCE_GROUP="prismata-selfplay"
LOCATION="${LOCATION:-northeurope}"
BUCKET="prismata-selfplay-data"
IMAGE="Win2022AzureEditionCore"
ADMIN_USER="prismata"
# Generate a password that meets Azure complexity requirements
ADMIN_PASS="Pr1sm4t4$(date +%s | tail -c 5)!"

# Load AWS credentials for S3 uploads (injected into VM startup script)
CRED_FILE="$(cd "$(dirname "$0")" && pwd)/.aws_credentials"
if [ ! -f "$CRED_FILE" ]; then
    echo "ERROR: AWS credentials not found at $CRED_FILE"
    echo "Create it with:"
    echo "  AWS_ACCESS_KEY_ID=..."
    echo "  AWS_SECRET_ACCESS_KEY=..."
    exit 1
fi
source "$CRED_FILE"

echo "=== Prismata Self-Play Azure Launch ==="
echo "  VM Size:  $VM_SIZE"
echo "  Games:    $NUM_GAMES"
echo "  Think:    ${THINK_TIME}s x ${VM_MULTIPLIER} multiplier"
echo "  Location: $LOCATION"
echo "  Count:    $NUM_INSTANCES"
echo "  Spot:     $USE_SPOT"
echo ""

# Determine process count from VM size (vCPUs / 4)
case "$VM_SIZE" in
  Standard_F2*|Standard_D2*)    PROCESSES=1 ;;
  Standard_F4*|Standard_D4*)    PROCESSES=1 ;;
  Standard_F8*|Standard_D8*)    PROCESSES=2 ;;
  Standard_F16*|Standard_D16*)  PROCESSES=4 ;;
  Standard_F32*|Standard_D32*)  PROCESSES=8 ;;
  *)                                                    PROCESSES=1 ;;
esac

GAMES_PER_PROCESS=$(( (NUM_GAMES + PROCESSES - 1) / PROCESSES ))
TIME_LIMIT_MS=$(python -c "print(int($THINK_TIME * $VM_MULTIPLIER * 1000))")
echo "  Processes: $PROCESSES (4 threads each)"
echo "  Games/process: $GAMES_PER_PROCESS"
echo "  Think time: ${THINK_TIME}s x ${VM_MULTIPLIER} = ${TIME_LIMIT_MS}ms"
echo ""

# Build the PowerShell startup script
# Part 1: Static header -- download, install, setup
STARTUP_SCRIPT=$(cat <<'ENDSCRIPT'
$ErrorActionPreference = "Continue"
$bucket = "prismata-selfplay-data"
$runId = (Get-Date -Format "yyyy-MM-dd_HH-mm-ss")

Start-Transcript -Path "C:\selfplay_boot.log" -Append
Write-Host "=== Prismata Self-Play Azure Worker Starting ==="
Write-Host "Run ID: $runId"

# Get instance name from Azure Instance Metadata Service
$metadataHeaders = @{"Metadata" = "true"}
try {
    $metadata = Invoke-RestMethod -Uri "http://169.254.169.254/metadata/instance?api-version=2021-02-01" -Headers $metadataHeaders
    $vmName = $metadata.compute.name
    $vmLocation = $metadata.compute.location
    $resourceGroup = $metadata.compute.resourceGroupName
    $subscriptionId = $metadata.compute.subscriptionId
    Write-Host "VM: $vmName in $vmLocation (RG: $resourceGroup)"
} catch {
    $vmName = $env:COMPUTERNAME
    Write-Host "Warning: Could not fetch Azure metadata, using hostname: $vmName"
}

# Install VC++ Redistributable
Write-Host "Installing VC++ Redistributable..."
$vcUrl = "https://aka.ms/vs/17/release/vc_redist.x86.exe"
Invoke-WebRequest -Uri $vcUrl -OutFile "C:\vc_redist.x86.exe"
Start-Process -Wait -FilePath "C:\vc_redist.x86.exe" -ArgumentList "/install /quiet /norestart"
Write-Host "VC++ Redistributable installed"

# Install AWS CLI
Write-Host "Installing AWS CLI..."
$awsUrl = "https://awscli.amazonaws.com/AWSCLIV2.msi"
Invoke-WebRequest -Uri $awsUrl -OutFile "C:\AWSCLIV2.msi"
Start-Process msiexec.exe -Wait -ArgumentList "/i C:\AWSCLIV2.msi /quiet"
$env:Path += ";C:\Program Files\Amazon\AWSCLIV2"
Write-Host "AWS CLI installed"

# Configure AWS credentials (injected by launch script)
ENDSCRIPT
)

# Part 2: Inject dynamic values (AWS credentials, game config)
STARTUP_SCRIPT+="
\$env:AWS_ACCESS_KEY_ID = \"$AWS_ACCESS_KEY_ID\"
\$env:AWS_SECRET_ACCESS_KEY = \"$AWS_SECRET_ACCESS_KEY\"
\$env:AWS_DEFAULT_REGION = \"eu-north-1\"
\$gamesPerProcess = $GAMES_PER_PROCESS
\$numProcesses = $PROCESSES
\$timeLimitMs = $TIME_LIMIT_MS
"

# Part 3: S3 download, config patching, worker launch, sync, shutdown
STARTUP_SCRIPT+=$(cat <<'ENDSCRIPT2'

# Verify AWS access
aws s3 ls s3://$bucket/ --region eu-north-1 2>&1 | Select-Object -First 3
Write-Host "AWS S3 access verified"

# Download files from S3
Write-Host "Downloading from S3..."
New-Item -ItemType Directory -Force -Path "C:\selfplay\asset\config" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\selfplay\training\data\selfplay" | Out-Null

aws s3 cp "s3://$bucket/deploy/Prismata_Testing.exe" "C:\selfplay\Prismata_Testing.exe" --region eu-north-1
aws s3 cp "s3://$bucket/deploy/asset/config/config.txt" "C:\selfplay\asset\config\config.txt" --region eu-north-1
aws s3 cp "s3://$bucket/deploy/asset/config/cardLibrary.jso" "C:\selfplay\asset\config\cardLibrary.jso" --region eu-north-1
aws s3 cp "s3://$bucket/deploy/asset/config/neural_weights.bin" "C:\selfplay\asset\config\neural_weights.bin" --region eu-north-1
Write-Host "Download complete"

# Patch config
$config = Get-Content "C:\selfplay\asset\config\config.txt" -Raw

# Patch config line-by-line: disable all tournaments, enable SelfPlay_CI
$lines = $config -split "`n"
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '"SelfPlay_CI"') {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*false', '"run":true'
        $lines[$i] = $lines[$i] -replace '"rounds"\s*:\s*\d+', '"rounds":250'
        $lines[$i] = $lines[$i] -replace '"Threads"\s*:\s*\d+', '"Threads":4'
        Write-Host "Enabled SelfPlay_CI on line $i"
    } else {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*true', '"run":false'
    }
}
$config = $lines -join "`n"

# Patch player TimeLimit
$config = $config -replace '("OriginalHardestAI_1s"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("OriginalHardestAI_Copy_1s"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"

Set-Content "C:\selfplay\asset\config\config.txt" $config -Encoding ascii
$batchSize = 250
Write-Host "Config patched: $gamesPerProcess games/process ($batchSize per batch), $numProcesses processes, TimeLimit=${timeLimitMs}ms"

# Upload patched config for inspection
aws s3 cp "C:\selfplay\asset\config\config.txt" "s3://$bucket/results/$runId/patched_config.txt" --region eu-north-1

# Periodic S3 sync -- copies files to temp dir first to avoid lock conflicts
function Sync-ToS3 {
    param($bucket, $runId, $numProcesses)
    $syncCount = 0
    $tempBase = "C:\selfplay\sync_temp"
    New-Item -ItemType Directory -Force -Path $tempBase | Out-Null
    $runDirs = Get-ChildItem "C:\selfplay\training\data\selfplay\run_*" -Directory -ErrorAction SilentlyContinue
    foreach ($dir in $runDirs) {
        $tempRunDir = "$tempBase\$($dir.Name)"
        New-Item -ItemType Directory -Force -Path $tempRunDir | Out-Null
        $files = Get-ChildItem $dir.FullName -File -ErrorAction SilentlyContinue
        foreach ($f in $files) {
            try {
                Copy-Item $f.FullName "$tempRunDir\$($f.Name)" -Force
                aws s3 cp "$tempRunDir\$($f.Name)" "s3://$bucket/results/$runId/$($dir.Name)/$($f.Name)" --region eu-north-1 2>&1 | Out-Null
                $syncCount++
            } catch { Write-Host "[Sync] Warning: $($f.Name): $_" }
        }
    }
    for ($i = 0; $i -lt $numProcesses; $i++) {
        try {
            $logFile = "C:\selfplay\log_worker_$i.txt"
            if (Test-Path $logFile) {
                Copy-Item $logFile "$tempBase\log_worker_$i.txt" -Force
                aws s3 cp "$tempBase\log_worker_$i.txt" "s3://$bucket/results/$runId/log_worker_$i.txt" --region eu-north-1 2>&1 | Out-Null
            }
        } catch { }
    }
    Remove-Item $tempBase -Recurse -Force -ErrorAction SilentlyContinue
    return $syncCount
}

# Launch workers in batch loop (250 rounds per batch to avoid x86 OOM)
# Each process runs 250 games then exits; we restart until target reached
$totalBatches = [math]::Ceiling($gamesPerProcess / $batchSize)
Write-Host "Running $totalBatches batches of $batchSize games per process ($numProcesses processes)..."

$lastSyncTime = Get-Date
$syncIntervalSec = 300

for ($batch = 1; $batch -le $totalBatches; $batch++) {
    Write-Host "=== Batch $batch/$totalBatches ==="

    $jobs = @()
    for ($i = 0; $i -lt $numProcesses; $i++) {
        $job = Start-Process -FilePath "C:\selfplay\Prismata_Testing.exe" `
            -WorkingDirectory "C:\selfplay" `
            -RedirectStandardOutput "C:\selfplay\log_stdout_$i.txt" `
            -RedirectStandardError "C:\selfplay\log_worker_$i.txt" `
            -PassThru
        $jobs += $job
        Start-Sleep -Seconds 2
    }

    # Wait for all workers in this batch
    while ($true) {
        $running = @($jobs | Where-Object { -not $_.HasExited })
        if ($running.Count -eq 0) { break }

        # Periodic sync while waiting
        $elapsed = ((Get-Date) - $lastSyncTime).TotalSeconds
        if ($elapsed -ge $syncIntervalSec) {
            $count = Sync-ToS3 $bucket $runId $numProcesses
            $lastSyncTime = Get-Date
            Write-Host "[Sync] Batch ${batch}: uploaded $count files. Workers: $($running.Count)/$numProcesses"
        }
        Start-Sleep -Seconds 30
    }

    foreach ($job in $jobs) {
        Write-Host "  Worker PID $($job.Id) exit code: $($job.ExitCode)"
    }

    # Sync after each batch
    $count = Sync-ToS3 $bucket $runId $numProcesses
    $lastSyncTime = Get-Date
    Write-Host "[Sync] Batch ${batch} complete: uploaded $count files"
}

# Final sync
Write-Host "All workers complete. Final S3 sync..."
$count = Sync-ToS3 $bucket $runId $numProcesses
Write-Host "[Sync] Final upload: $count files"

# Upload boot log
aws s3 cp "C:\selfplay_boot.log" "s3://$bucket/results/$runId/selfplay_boot.log" --region eu-north-1

Write-Host "=== Upload complete. Shutting down. ==="
Stop-Transcript

# Shutdown -- Stop-Computer only stops OS (still bills!).
# TheWatcher detects "VM stopped" and deallocates/deletes to stop billing.
Stop-Computer -Force
ENDSCRIPT2
)

# Write startup script to temp file
STARTUP_FILE="c:/libraries/PrismataAI/azure/.startup_tmp.ps1"
printf '%s' "$STARTUP_SCRIPT" > "$STARTUP_FILE"

SPOT_OPTS=""
if [ "$USE_SPOT" = "true" ]; then
    SPOT_OPTS="--priority Spot --eviction-policy Delete --max-price -1"
    echo "(Using SPOT pricing)"
fi

# Launch instances
# Azure approach: pass startup script via --custom-data, then use Custom Script Extension to execute it
# custom-data gets written to C:\AzureData\CustomData.bin on Windows VMs
for i in $(seq 1 $NUM_INSTANCES); do
    VM_NAME="prsm-$(date +%H%M%S)-$i"
    echo "Launching instance $i/$NUM_INSTANCES: $VM_NAME..."

    # Create the VM with custom-data carrying the startup script
    PYTHONUTF8=1 "$AZ" vm create \
        --resource-group "$RESOURCE_GROUP" \
        --name "$VM_NAME" \
        --image "$IMAGE" \
        --size "$VM_SIZE" \
        --location "$LOCATION" \
        --admin-username "$ADMIN_USER" \
        --admin-password "$ADMIN_PASS" \
        --public-ip-sku Standard \
        --custom-data "$STARTUP_FILE" \
        --tags "purpose=selfplay" "games=$NUM_GAMES" \
        $SPOT_OPTS \
        2>&1

    echo "  VM created. Applying Custom Script Extension to execute startup..."

    # Custom Script Extension copies custom-data to .ps1 and runs it
    "$AZ" vm extension set \
        --resource-group "$RESOURCE_GROUP" \
        --vm-name "$VM_NAME" \
        --name CustomScriptExtension \
        --publisher Microsoft.Compute \
        --version 1.10 \
        --settings '{"commandToExecute":"powershell -ExecutionPolicy Unrestricted -Command \"Copy-Item C:\\AzureData\\CustomData.bin C:\\startup.ps1; & C:\\startup.ps1\""}' \
        --no-wait \
        2>&1

    echo "  Extension applied for $VM_NAME"
    echo ""
done

rm -f "$STARTUP_FILE"

echo "=== $NUM_INSTANCES Instance(s) Launched ==="
echo "  Size:        $VM_SIZE"
echo "  Games:       $NUM_GAMES ($PROCESSES processes x $GAMES_PER_PROCESS per instance)"
echo "  Location:    $LOCATION"
echo ""
echo "Each instance will:"
echo "  1. Boot Windows Server (~3 min)"
echo "  2. Custom Script Extension runs startup.ps1 (~1 min)"
echo "  3. Install VC++ runtime + AWS CLI (~2 min)"
echo "  4. Download exe + config from S3 (~1 min)"
echo "  5. Run self-play ($NUM_GAMES games)"
echo "  6. Upload results to s3://$BUCKET/results/"
echo "  7. Stop-Computer (deallocates, stops billing)"
echo ""
echo "Monitor instances:"
echo "  \"$AZ\" vm list --resource-group $RESOURCE_GROUP --output table"
echo ""
echo "Check VM status:"
echo "  \"$AZ\" vm get-instance-view --resource-group $RESOURCE_GROUP --name VM_NAME --query instanceView.statuses"
echo ""
echo "Download results (same as EC2):"
echo "  aws s3 sync s3://$BUCKET/results/ bin/training/data/selfplay/ --region eu-north-1"
