#!/bin/bash
# Launch EC2 Windows instances for tournament evaluation
# Usage: bash aws/launch_tournament.sh [INSTANCE_TYPE] [NUM_ROUNDS] [VM_MULTIPLIER] [NUM_INSTANCES]
#
# Environment variables:
#   WEIGHTS_KEY  - S3 key for neural weights (default: deploy/asset/config/neural_weights.bin)
#   MODEL_LABEL  - Label for instance tags (default: "default")
#   USE_SPOT     - "true" to use spot instances (default: false, auto-fills on-demand first)
#
# Examples:
#   bash aws/launch_tournament.sh c5.2xlarge 42 1.3 1
#   WEIGHTS_KEY=deploy/neural_weights_512h.bin MODEL_LABEL=512h bash aws/launch_tournament.sh c5.2xlarge 42 1.3 12
#
# Runs NeuralAB_vs_Original (AB) against OriginalHardestAI.
# Each process runs the tournament independently. Multiple instances = more games.
# Results uploaded to s3://prismata-selfplay-data/eval-results/<runId>/

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

INSTANCE_TYPE="${1:-c5.2xlarge}"
NUM_ROUNDS="${2:-1500}"
VM_MULTIPLIER="${3:-1}"
NUM_INSTANCES="${4:-1}"
WEIGHTS_KEY="${WEIGHTS_KEY:-deploy/asset/config/neural_weights.bin}"
MODEL_LABEL="${MODEL_LABEL:-default}"
USE_SPOT="${USE_SPOT:-false}"
REGION="eu-north-1"
AMI="ami-0adc3f10e1311b184"  # Windows Server 2022 Base
KEY_NAME="prismata-selfplay"
SG_ID="sg-02117c219481e8e6a"
PROFILE="PrismataSelfPlayEC2"
BUCKET="prismata-selfplay-data"

echo "=== Prismata Tournament Eval EC2 Launch ==="
echo "  Instance:   $INSTANCE_TYPE x $NUM_INSTANCES"
echo "  Rounds:     $NUM_ROUNDS (per process)"
echo "  VM mult:    ${VM_MULTIPLIER}x think time"
echo "  Weights:    $WEIGHTS_KEY"
echo "  Model:      $MODEL_LABEL"
echo "  Region:     $REGION"
echo "  Bucket:     $BUCKET"
echo ""

# Determine process count from instance type (4 threads per process, x86 OOM limit)
case "$INSTANCE_TYPE" in
  t3.micro|t3.small|t4g.micro|t4g.small)  PROCESSES=1 ;;
  c7i-flex.large|m7i-flex.large)           PROCESSES=1 ;;
  c5.xlarge)   PROCESSES=1 ;;
  c5.2xlarge)  PROCESSES=2 ;;
  c5.4xlarge)  PROCESSES=4 ;;
  c5.9xlarge)  PROCESSES=9 ;;
  c5.12xlarge) PROCESSES=12 ;;
  c5.18xlarge) PROCESSES=18 ;;
  *)           PROCESSES=1 ;;
esac

# Compute adjusted think time: base 7000ms * multiplier
TIME_LIMIT_MS=$(python -c "print(int(7000 * $VM_MULTIPLIER))")
GAMES_PER_INSTANCE=$(( NUM_ROUNDS * 2 * PROCESSES ))  # rounds * 2(color swap) * processes
TOTAL_GAMES=$(( GAMES_PER_INSTANCE * NUM_INSTANCES ))
echo "  Processes:   $PROCESSES per instance (4 threads each)"
echo "  Think time:  7000ms x ${VM_MULTIPLIER} = ${TIME_LIMIT_MS}ms"
echo "  Games/inst:  $GAMES_PER_INSTANCE"
echo "  Total games: ~$TOTAL_GAMES"
echo ""

# Check that deploy files exist on S3
echo "Verifying S3 deploy files..."
if ! aws s3 ls "s3://$BUCKET/deploy/Prismata_Testing.exe" --region "$REGION" > /dev/null 2>&1; then
    echo "ERROR: Prismata_Testing.exe not found on S3. Upload first:"
    echo "  bash aws/deploy_for_eval.sh"
    exit 1
fi
if ! aws s3 ls "s3://$BUCKET/$WEIGHTS_KEY" --region "$REGION" > /dev/null 2>&1; then
    echo "ERROR: Weights not found at s3://$BUCKET/$WEIGHTS_KEY"
    exit 1
fi

# Create the PowerShell user-data script
USERDATA=$(cat <<'ENDSCRIPT'
<powershell>
$ErrorActionPreference = "Continue"
$bucket = "prismata-selfplay-data"
$runId = "eval_" + (Get-Date -Format "yyyy-MM-dd_HH-mm-ss") + "_" + $env:COMPUTERNAME

Start-Transcript -Path "C:\eval_boot.log" -Append

Write-Host "=== Prismata Tournament Eval Worker Starting ==="
Write-Host "Run ID: $runId"

# Install VC++ Redistributable
Write-Host "Installing VC++ Redistributable..."
$vcUrl = "https://aka.ms/vs/17/release/vc_redist.x86.exe"
Invoke-WebRequest -Uri $vcUrl -OutFile "C:\vc_redist.x86.exe"
Start-Process -Wait -FilePath "C:\vc_redist.x86.exe" -ArgumentList "/install /quiet /norestart"
Write-Host "VC++ Redistributable installed"

# Download files from S3
Write-Host "Downloading from S3..."
New-Item -ItemType Directory -Force -Path "C:\eval\asset\config" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\eval\tests" | Out-Null

Read-S3Object -BucketName $bucket -Key "deploy/Prismata_Testing.exe" -File "C:\eval\Prismata_Testing.exe"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/config.txt" -File "C:\eval\asset\config\config.txt"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/cardLibrary.jso" -File "C:\eval\asset\config\cardLibrary.jso"
ENDSCRIPT
)

# Inject dynamic values (weights key, rounds, processes, think time)
USERDATA+="
\$weightsKey = \"$WEIGHTS_KEY\"
\$numRounds = $NUM_ROUNDS
\$numProcesses = $PROCESSES
\$timeLimitMs = $TIME_LIMIT_MS
"

USERDATA+=$(cat <<'ENDSCRIPT2'

Write-Host "Downloading weights from: $weightsKey"
Read-S3Object -BucketName $bucket -Key $weightsKey -File "C:\eval\asset\config\neural_weights.bin"
Write-Host "Download complete"

# Patch config
$config = Get-Content "C:\eval\asset\config\config.txt" -Raw

# Patch config line-by-line: disable all, enable NeuralAB_vs_Original only
$lines = $config -split "`n"
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '"NeuralAB_vs_Original"') {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*false', '"run":true'
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*true', '"run":true'
        $lines[$i] = $lines[$i] -replace '"rounds"\s*:\s*\d+', "`"rounds`":$numRounds"
        $lines[$i] = $lines[$i] -replace '"Threads"\s*:\s*\d+', '"Threads":4'
        if ($lines[$i] -notmatch '"Threads"') {
            $lines[$i] = $lines[$i] -replace '"rounds"', '"Threads":4, "rounds"'
        }
        Write-Host "Enabled NeuralAB_vs_Original on line $i"
    } else {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*true', '"run":false'
    }
}
$config = $lines -join "`n"

# Patch player TimeLimits for VM speed adjustment
$config = $config -replace '("PrismatAI_AB_Legacy"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("OriginalHardestAI"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"

Set-Content "C:\eval\asset\config\config.txt" $config -Encoding ascii
Write-Host "Config patched: $numRounds rounds, $numProcesses processes, TimeLimit=${timeLimitMs}ms"

# Debug: show patched tournament and player lines
$debugConfig = Get-Content "C:\eval\asset\config\config.txt" -Raw
$debugConfig -split "`n" | ForEach-Object {
    if ($_ -match 'NeuralAB_vs_Original|PrismatAI_AB_Legacy|OriginalHardestAI') {
        Write-Host "DEBUG: $_"
    }
}

# Upload patched config for inspection
Write-S3Object -BucketName $bucket -Key "eval-results/$runId/patched_config.txt" -File "C:\eval\asset\config\config.txt"

# Launch multiple eval processes
$jobs = @()
for ($i = 0; $i -lt $numProcesses; $i++) {
    Write-Host "Launching worker $i..."
    New-Item -ItemType Directory -Force -Path "C:\eval\asset\replays" | Out-Null
    $job = Start-Process -FilePath "C:\eval\Prismata_Testing.exe" `
        -WorkingDirectory "C:\eval" `
        -RedirectStandardOutput "C:\eval\log_stdout_$i.txt" `
        -RedirectStandardError "C:\eval\log_worker_$i.txt" `
        -PassThru
    $jobs += $job
    Start-Sleep -Seconds 3  # stagger for unique seeds (srand uses time(NULL) ^ PID)
}

Write-Host "All $numProcesses workers launched. Waiting with periodic S3 sync..."

# Periodic S3 sync function — copies files to temp dir first to avoid lock conflicts
function Sync-EvalToS3 {
    param($bucket, $runId, $numProcesses)
    $syncCount = 0
    $tempBase = "C:\eval\sync_temp"
    New-Item -ItemType Directory -Force -Path $tempBase | Out-Null
    # HTML results
    $htmlFiles = Get-ChildItem "C:\eval\tests\Tournament_*.html" -ErrorAction SilentlyContinue
    foreach ($f in $htmlFiles) {
        try {
            Copy-Item $f.FullName "$tempBase\$($f.Name)" -Force
            Write-S3Object -BucketName $bucket -Key "eval-results/$runId/tests/$($f.Name)" -File "$tempBase\$($f.Name)"
            $syncCount++
        } catch { Write-Host "[Sync] Warning: $($f.Name): $_" }
    }
    # Logs
    for ($i = 0; $i -lt $numProcesses; $i++) {
        try {
            $logFile = "C:\eval\log_worker_$i.txt"
            if (Test-Path $logFile) {
                Copy-Item $logFile "$tempBase\log_worker_$i.txt" -Force
                Write-S3Object -BucketName $bucket -Key "eval-results/$runId/log_worker_$i.txt" -File "$tempBase\log_worker_$i.txt"
                $syncCount++
            }
            $stdoutLog = "C:\eval\log_stdout_$i.txt"
            if (Test-Path $stdoutLog) {
                Copy-Item $stdoutLog "$tempBase\log_stdout_$i.txt" -Force
                Write-S3Object -BucketName $bucket -Key "eval-results/$runId/log_stdout_$i.txt" -File "$tempBase\log_stdout_$i.txt"
                $syncCount++
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
    $count = Sync-EvalToS3 $bucket $runId $numProcesses
    $running = @($jobs | Where-Object { -not $_.HasExited })
    Write-Host "[Sync] Uploaded $count files. Workers running: $($running.Count)/$numProcesses"
}

foreach ($job in $jobs) {
    Write-Host "Worker PID $($job.Id) finished with exit code $($job.ExitCode)"
}

# Final sync
Write-Host "All workers complete. Final S3 sync..."
$count = Sync-EvalToS3 $bucket $runId $numProcesses
Write-Host "[Sync] Final upload: $count files"

Write-Host "=== Upload complete. Shutting down. ==="
Stop-Transcript
Write-S3Object -BucketName $bucket -Key "eval-results/$runId/eval_boot.log" -File "C:\eval_boot.log"
Stop-Computer -Force
</powershell>
ENDSCRIPT2
)

# Write user data to temp file
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_eval_tmp.ps1"
echo "$USERDATA" > "$USERDATA_FILE"

# Launch instances
LAUNCHED=0
INSTANCE_IDS=""

for ((i=1; i<=NUM_INSTANCES; i++)); do
    SPOT_OPTS=""
    LAUNCH_TYPE="on-demand"
    if [ "$USE_SPOT" = "true" ]; then
        SPOT_OPTS="--instance-market-options MarketType=spot"
        LAUNCH_TYPE="spot"
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
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataEval-${MODEL_LABEL}-${NUM_ROUNDS}r}]" \
      --query 'Instances[0].InstanceId' \
      --output text \
      --region "$REGION" 2>&1)

    if [[ "$INSTANCE_ID" == i-* ]]; then
        LAUNCHED=$((LAUNCHED + 1))
        INSTANCE_IDS="$INSTANCE_IDS $INSTANCE_ID"
        echo "  [$LAUNCHED/$NUM_INSTANCES] $INSTANCE_ID ($LAUNCH_TYPE)"
    else
        echo "  [$i/$NUM_INSTANCES] FAILED: $INSTANCE_ID"
    fi
done

rm -f "$USERDATA_FILE"

echo ""
echo "=== Fleet Launch Complete ==="
echo "  Launched:    $LAUNCHED / $NUM_INSTANCES instances"
echo "  Model:       $MODEL_LABEL"
echo "  Rounds/inst: $NUM_ROUNDS x $PROCESSES processes = $(( NUM_ROUNDS * PROCESSES )) rounds"
echo "  Games/inst:  $GAMES_PER_INSTANCE"
echo "  Total games: ~$(( GAMES_PER_INSTANCE * LAUNCHED ))"
echo ""
echo "Each instance will:"
echo "  1. Boot Windows Server (~3 min)"
echo "  2. Install VC++ runtime (~1 min)"
echo "  3. Download exe + config + weights from S3 (~1 min)"
echo "  4. Run NeuralAB_vs_Original tournament"
echo "  5. Upload results to s3://$BUCKET/eval-results/"
echo "  6. Auto-terminate"
echo ""
echo "Monitor:"
echo "  aws ec2 describe-instances --region $REGION --filters 'Name=tag:Name,Values=PrismataEval-*' 'Name=instance-state-name,Values=running' --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==\`Name\`].Value|[0],State.Name]' --output table"
echo ""
echo "Download results:"
echo "  aws s3 sync s3://$BUCKET/eval-results/ eval-results/ --region $REGION"
