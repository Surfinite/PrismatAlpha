#!/bin/bash
# Launch EC2 Windows instance for self-play generation
# Usage: bash aws/launch_selfplay.sh [INSTANCE_TYPE] [NUM_GAMES] [THINK_TIME_S] [VM_MULTIPLIER]
#
# Examples:
#   bash aws/launch_selfplay.sh                        # t3.micro, 2500 games, 1s, 2x
#   bash aws/launch_selfplay.sh t3.micro 2500 2 2      # 2s think, 2x multiplier = 4s actual
#   bash aws/launch_selfplay.sh c5.4xlarge 5000 1 1.3  # 1s think, 1.3x = 1.3s actual

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

# Load cloud config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../cloud-config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "ERROR: Missing cloud-config.env. Copy cloud-config.env.example and fill in your values."
    exit 1
fi

INSTANCE_TYPE="${1:-t3.micro}"
NUM_GAMES="${2:-2500}"
THINK_TIME="${3:-1}"
VM_MULTIPLIER="${4:-2}"
USE_SPOT="${USE_SPOT:-false}"  # Set USE_SPOT=true to use spot pricing
REGION="${AWS_REGION:-eu-north-1}"
AMI="${AWS_AMI_WINDOWS:?Set AWS_AMI_WINDOWS in cloud-config.env}"
KEY_NAME="${AWS_KEY_NAME:?Set AWS_KEY_NAME in cloud-config.env}"
SG_ID="${AWS_SG_ID:?Set AWS_SG_ID in cloud-config.env}"
PROFILE="${AWS_IAM_PROFILE:?Set AWS_IAM_PROFILE in cloud-config.env}"
BUCKET="${CLOUD_BUCKET:?Set CLOUD_BUCKET in cloud-config.env}"

echo "=== Prismata Self-Play EC2 Launch ==="
echo "  Instance: $INSTANCE_TYPE"
echo "  Games:    $NUM_GAMES"
echo "  Think:    ${THINK_TIME}s x ${VM_MULTIPLIER} multiplier"
echo "  Region:   $REGION"
echo "  Bucket:   $BUCKET"
echo ""

# Determine thread count and process count from instance type
# c5.xlarge=4vcpu, c5.2xlarge=8, c5.4xlarge=16, c5.9xlarge=36
case "$INSTANCE_TYPE" in
  # Free Tier eligible (2 vCPUs)
  t3.micro|t3.small|t4g.micro|t4g.small)  PROCESSES=1 ;;
  c7i-flex.large|m7i-flex.large)           PROCESSES=1 ;;
  # Compute-optimized (4 threads per process)
  c5.xlarge)   PROCESSES=1 ;;
  c5.2xlarge)  PROCESSES=2 ;;
  c5.4xlarge)  PROCESSES=4 ;;
  c5.9xlarge)  PROCESSES=9 ;;
  c5.12xlarge) PROCESSES=12 ;;
  c5.18xlarge) PROCESSES=18 ;;
  *)           PROCESSES=1 ;;
esac

GAMES_PER_PROCESS=$(( (NUM_GAMES + PROCESSES - 1) / PROCESSES ))
# Compute actual time limit in ms: think_time * multiplier * 1000
TIME_LIMIT_MS=$(python -c "print(int($THINK_TIME * $VM_MULTIPLIER * 1000))")
echo "  Processes: $PROCESSES (4 threads each)"
echo "  Games/process: $GAMES_PER_PROCESS"
echo "  Think time: ${THINK_TIME}s x ${VM_MULTIPLIER} = ${TIME_LIMIT_MS}ms"
echo ""

# Create the PowerShell user-data script that runs on first boot
USERDATA=$(cat <<'ENDSCRIPT'
<powershell>
$ErrorActionPreference = "Continue"
$bucket = "prismata-selfplay-data"
$runId = (Get-Date -Format "yyyy-MM-dd_HH-mm-ss")

# Log everything
Start-Transcript -Path "C:\selfplay_boot.log" -Append

Write-Host "=== Prismata Self-Play Worker Starting ==="
Write-Host "Run ID: $runId"

# Install VC++ Redistributable (needed for Release builds)
Write-Host "Installing VC++ Redistributable..."
$vcUrl = "https://aka.ms/vs/17/release/vc_redist.x86.exe"
Invoke-WebRequest -Uri $vcUrl -OutFile "C:\vc_redist.x86.exe"
Start-Process -Wait -FilePath "C:\vc_redist.x86.exe" -ArgumentList "/install /quiet /norestart"
Write-Host "VC++ Redistributable installed"

# Download files from S3
Write-Host "Downloading from S3..."
New-Item -ItemType Directory -Force -Path "C:\selfplay\asset\config" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\selfplay\training\data\selfplay" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\selfplay\tests" | Out-Null

Read-S3Object -BucketName $bucket -Key "deploy/Prismata_Testing.exe" -File "C:\selfplay\Prismata_Testing.exe"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/config.txt" -File "C:\selfplay\asset\config\config.txt"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/cardLibrary.jso" -File "C:\selfplay\asset\config\cardLibrary.jso"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/neural_weights.bin" -File "C:\selfplay\asset\config\neural_weights.bin"
Write-Host "Download complete"

# Patch config: set games and threads
$config = Get-Content "C:\selfplay\asset\config\config.txt" -Raw
ENDSCRIPT
)

# Inject sourced config values into userdata (heredoc is single-quoted to protect PS syntax)
USERDATA="${USERDATA/\$bucket = \"prismata-selfplay-data\"/\$bucket = \"$BUCKET\"}"

# Inject the dynamic values
USERDATA+="
\$gamesPerProcess = $GAMES_PER_PROCESS
\$numProcesses = $PROCESSES
\$timeLimitMs = $TIME_LIMIT_MS
"

USERDATA+=$(cat <<'ENDSCRIPT2'

# Patch config line-by-line: disable all tournaments, enable SelfPlay_CI
$lines = $config -split "`n"
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '"SelfPlay_CI"') {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*false', '"run":true'
        $lines[$i] = $lines[$i] -replace '"rounds"\s*:\s*\d+', "`"rounds`":$gamesPerProcess"
        $lines[$i] = $lines[$i] -replace '"Threads"\s*:\s*\d+', '"Threads":4'
        Write-Host "Enabled SelfPlay_CI on line $i"
    } else {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*true', '"run":false'
    }
}
$config = $lines -join "`n"

# Patch player TimeLimit for the players used by SelfPlay_CI
$config = $config -replace '("OriginalHardestAI_1s"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("OriginalHardestAI_Copy_1s"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"

Set-Content "C:\selfplay\asset\config\config.txt" $config -Encoding ascii
Write-Host "Config patched: $gamesPerProcess games/process, $numProcesses processes, TimeLimit=${timeLimitMs}ms"

# Debug: show the patched player and tournament lines
$debugConfig = Get-Content "C:\selfplay\asset\config\config.txt" -Raw
$debugConfig -split "`n" | ForEach-Object {
    if ($_ -match 'SelfPlay_CI|OriginalHardestAI_1s|OriginalHardestAI_Copy_1s') {
        Write-Host "DEBUG: $_"
    }
}

# Also upload the patched config for inspection
Write-S3Object -BucketName $bucket -Key "results/$runId/patched_config.txt" -File "C:\selfplay\asset\config\config.txt"

# Launch multiple self-play processes
$jobs = @()
for ($i = 0; $i -lt $numProcesses; $i++) {
    Write-Host "Launching worker $i..."
    $job = Start-Process -FilePath "C:\selfplay\Prismata_Testing.exe" `
        -WorkingDirectory "C:\selfplay" `
        -RedirectStandardOutput "C:\selfplay\log_stdout_$i.txt" `
        -RedirectStandardError "C:\selfplay\log_worker_$i.txt" `
        -PassThru
    $jobs += $job
    Start-Sleep -Seconds 3  # stagger for unique run_* dirs
}

Write-Host "All $numProcesses workers launched. Waiting with periodic S3 sync..."

# Periodic S3 sync function — copies files to temp dir first to avoid lock conflicts
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
                $key = "results/$runId/$($dir.Name)/$($f.Name)"
                Write-S3Object -BucketName $bucket -Key $key -File "$tempRunDir\$($f.Name)"
                $syncCount++
            } catch { Write-Host "[Sync] Warning: $($f.Name): $_" }
        }
    }
    for ($i = 0; $i -lt $numProcesses; $i++) {
        try {
            $logFile = "C:\selfplay\log_worker_$i.txt"
            if (Test-Path $logFile) {
                Copy-Item $logFile "$tempBase\log_worker_$i.txt" -Force
                Write-S3Object -BucketName $bucket -Key "results/$runId/log_worker_$i.txt" -File "$tempBase\log_worker_$i.txt"
            }
            $stdoutLog = "C:\selfplay\log_stdout_$i.txt"
            if (Test-Path $stdoutLog) {
                Copy-Item $stdoutLog "$tempBase\log_stdout_$i.txt" -Force
                Write-S3Object -BucketName $bucket -Key "results/$runId/log_stdout_$i.txt" -File "$tempBase\log_stdout_$i.txt"
            }
        } catch { }
    }
    Remove-Item $tempBase -Recurse -Force -ErrorAction SilentlyContinue
    return $syncCount
}

# Wait for workers with periodic sync every 5 minutes
$syncIntervalSec = 300
while ($true) {
    $running = @($jobs | Where-Object { -not $_.HasExited })
    if ($running.Count -eq 0) { break }
    Start-Sleep -Seconds $syncIntervalSec
    $count = Sync-ToS3 $bucket $runId $numProcesses
    $running = @($jobs | Where-Object { -not $_.HasExited })
    Write-Host "[Sync] Uploaded $count files. Workers running: $($running.Count)/$numProcesses"
}

foreach ($job in $jobs) {
    Write-Host "Worker PID $($job.Id) finished with exit code $($job.ExitCode)"
}

# Final sync to catch anything from the last interval
Write-Host "All workers complete. Final S3 sync..."
$count = Sync-ToS3 $bucket $runId $numProcesses
Write-Host "[Sync] Final upload: $count files"

Write-Host "=== Upload complete. Shutting down. ==="
Stop-Transcript

# Upload boot log
Write-S3Object -BucketName $bucket -Key "results/$runId/selfplay_boot.log" -File "C:\selfplay_boot.log"

# Self-terminate
Stop-Computer -Force
</powershell>
ENDSCRIPT2
)

# Write user data to temp file (let AWS CLI handle base64 encoding)
# Use Windows-friendly path since AWS CLI is a native Windows program
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_tmp.ps1"
echo "$USERDATA" > "$USERDATA_FILE"

echo "Launching instance..."

SPOT_OPTS=""
if [ "$USE_SPOT" = "true" ]; then
  SPOT_OPTS="--instance-market-options MarketType=spot"
  echo "(Using SPOT pricing)"
fi

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name="$PROFILE" \
  --user-data "file://$USERDATA_FILE" \
  --instance-initiated-shutdown-behavior terminate \
  $SPOT_OPTS \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataSelfPlay-$NUM_GAMES}]" \
  --query 'Instances[0].InstanceId' \
  --output text \
  --region "$REGION" 2>&1)

rm -f "$USERDATA_FILE"

echo ""
echo "=== Instance Launched ==="
echo "  Instance ID: $INSTANCE_ID"
echo "  Type:        $INSTANCE_TYPE"
echo "  Games:       $NUM_GAMES ($PROCESSES processes x $GAMES_PER_PROCESS)"
echo ""
echo "The instance will:"
echo "  1. Boot Windows Server (~3 min)"
echo "  2. Install VC++ runtime (~1 min)"
echo "  3. Download exe + config from S3 (~1 min)"
echo "  4. Run self-play ($NUM_GAMES games)"
echo "  5. Upload results to s3://$BUCKET/results/"
echo "  6. Auto-terminate (no ongoing charges)"
echo ""
echo "Monitor progress:"
echo "  aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].State.Name' --region $REGION"
echo ""
echo "Download results when done:"
echo "  aws s3 sync s3://$BUCKET/results/ bin/training/data/selfplay/ --region $REGION"
