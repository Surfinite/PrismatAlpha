#!/bin/bash
# Launch EC2 spot instances for heuristic improvement evaluation
# Runs 3 tournaments: Neural+improved vs Original, Playout+improved vs Original, Neural improved vs legacy
# Usage: bash aws/launch_heuristic_eval.sh [NUM_INSTANCES]

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

INSTANCE_TYPE="c5.2xlarge"
NUM_INSTANCES="${1:-12}"
VM_MULTIPLIER="1"
REGION="eu-north-1"
AMI="ami-0adc3f10e1311b184"  # Windows Server 2022 Base
KEY_NAME="prismata-selfplay"
SG_ID="sg-02117c219481e8e6a"
PROFILE="PrismataSelfPlayEC2"
BUCKET="prismata-selfplay-data"
WEIGHTS_KEY="deploy/asset/config/neural_weights.bin"
PROCESSES=2  # c5.2xlarge = 8 vCPUs, 2 processes x 4 threads

# Compute adjusted think time: base 7000ms * multiplier
TIME_LIMIT_MS=$(python -c "print(int(7000 * $VM_MULTIPLIER))")

# Games estimate per instance (2 processes, color swap):
# Run A: 42 rounds x 2 x 2 = 168 games
# Run B: 16 rounds x 2 x 2 = 64 games
# Run C: 16 rounds x 2 x 2 = 64 games
# Total: 296 games/instance
TOTAL_GAMES=$(( 296 * NUM_INSTANCES ))

echo "=== Heuristic Improvement Evaluation ==="
echo "  Instance:   $INSTANCE_TYPE x $NUM_INSTANCES (spot)"
echo "  Think time: ${TIME_LIMIT_MS}ms"
echo "  Tournaments:"
echo "    A: NeuralAB(improved) vs OriginalHardestAI  - 42 rounds/process"
echo "    B: HardestAI(improved) vs OriginalHardestAI - 16 rounds/process"
echo "    C: NeuralAB(improved) vs NeuralAB(legacy)   - 16 rounds/process"
echo "  Total games: ~$TOTAL_GAMES"
echo ""

# Check that deploy files exist on S3
echo "Verifying S3 deploy files..."
if ! aws s3 ls "s3://$BUCKET/deploy/Prismata_Testing.exe" --region "$REGION" > /dev/null 2>&1; then
    echo "ERROR: Prismata_Testing.exe not found on S3. Run: bash aws/deploy_for_eval.sh"
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
$runId = "heuristic_eval_" + (Get-Date -Format "yyyy-MM-dd_HH-mm-ss") + "_" + $env:COMPUTERNAME

Start-Transcript -Path "C:\eval_boot.log" -Append

Write-Host "=== Heuristic Improvement Eval Worker Starting ==="
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

# Inject dynamic values
USERDATA+="
\$weightsKey = \"$WEIGHTS_KEY\"
\$numProcesses = $PROCESSES
\$timeLimitMs = $TIME_LIMIT_MS
"

USERDATA+=$(cat <<'ENDSCRIPT2'

Write-Host "Downloading weights from: $weightsKey"
Read-S3Object -BucketName $bucket -Key $weightsKey -File "C:\eval\asset\config\neural_weights.bin"
Write-Host "Download complete"

# Patch config: enable only HeuristicEval_ tournaments, disable all others
$config = Get-Content "C:\eval\asset\config\config.txt" -Raw
$lines = $config -split "`n"
for ($i = 0; $i -lt $lines.Length; $i++) {
    if ($lines[$i] -match '"HeuristicEval_') {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*false', '"run":true'
        $lines[$i] = $lines[$i] -replace '"Threads"\s*:\s*\d+', '"Threads":4'
        if ($lines[$i] -notmatch '"Threads"') {
            $lines[$i] = $lines[$i] -replace '"rounds"', '"Threads":4, "rounds"'
        }
        Write-Host "Enabled tournament on line $i: $($lines[$i].Substring(0, [Math]::Min(100, $lines[$i].Length)))"
    } else {
        $lines[$i] = $lines[$i] -replace '"run"\s*:\s*true', '"run":false'
    }
}
$config = $lines -join "`n"

# Patch player TimeLimits for VM speed adjustment
$config = $config -replace '("PrismatAlpha_AB"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("PrismatAlpha_AB_Legacy"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("HardestAI"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("OriginalHardestAI"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"

Set-Content "C:\eval\asset\config\config.txt" $config -Encoding ascii
Write-Host "Config patched: $numProcesses processes, TimeLimit=${timeLimitMs}ms"

# Debug: show patched tournament lines
$debugConfig = Get-Content "C:\eval\asset\config\config.txt" -Raw
$debugConfig -split "`n" | ForEach-Object {
    if ($_ -match 'HeuristicEval_|PrismatAlpha_AB|HardestAI|OriginalHardestAI') {
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
    Start-Sleep -Seconds 3
}

Write-Host "All $numProcesses workers launched. Waiting with periodic S3 sync..."

# Periodic S3 sync function
function Sync-EvalToS3 {
    param($bucket, $runId, $numProcesses)
    $syncCount = 0
    $tempBase = "C:\eval\sync_temp"
    New-Item -ItemType Directory -Force -Path $tempBase | Out-Null
    $htmlFiles = Get-ChildItem "C:\eval\tests\Tournament_*.html" -ErrorAction SilentlyContinue
    foreach ($f in $htmlFiles) {
        try {
            Copy-Item $f.FullName "$tempBase\$($f.Name)" -Force
            Write-S3Object -BucketName $bucket -Key "eval-results/$runId/tests/$($f.Name)" -File "$tempBase\$($f.Name)"
            $syncCount++
        } catch { Write-Host "[Sync] Warning: $($f.Name): $_" }
    }
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
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_heuristic_eval_tmp.ps1"
echo "$USERDATA" > "$USERDATA_FILE"

# Launch spot instances
LAUNCHED=0
INSTANCE_IDS=""

for ((i=1; i<=NUM_INSTANCES; i++)); do
    INSTANCE_ID=$(aws ec2 run-instances \
      --image-id "$AMI" \
      --instance-type "$INSTANCE_TYPE" \
      --key-name "$KEY_NAME" \
      --security-group-ids "$SG_ID" \
      --iam-instance-profile Name="$PROFILE" \
      --user-data "file://$USERDATA_FILE" \
      --instance-initiated-shutdown-behavior terminate \
      --instance-market-options MarketType=spot \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataEval-heuristic}]" \
      --query 'Instances[0].InstanceId' \
      --output text \
      --region "$REGION" 2>&1)

    if [[ "$INSTANCE_ID" == i-* ]]; then
        LAUNCHED=$((LAUNCHED + 1))
        INSTANCE_IDS="$INSTANCE_IDS $INSTANCE_ID"
        echo "  [$LAUNCHED/$NUM_INSTANCES] $INSTANCE_ID (spot)"
    else
        echo "  [$i/$NUM_INSTANCES] FAILED: $INSTANCE_ID"
    fi
done

rm -f "$USERDATA_FILE"

echo ""
echo "=== Fleet Launch Complete ==="
echo "  Launched:    $LAUNCHED / $NUM_INSTANCES spot instances"
echo "  Games/inst:  ~296 (168 Run A + 64 Run B + 64 Run C)"
echo "  Total games: ~$(( 296 * LAUNCHED ))"
echo ""
echo "Expected results:"
echo "  Run A (Neural+improved vs Original):    ~$(( 168 * LAUNCHED )) games"
echo "  Run B (Playout+improved vs Original):   ~$(( 64 * LAUNCHED )) games"
echo "  Run C (Neural improved vs legacy):      ~$(( 64 * LAUNCHED )) games"
echo ""
echo "Monitor:"
echo "  aws ec2 describe-instances --region $REGION --filters 'Name=tag:Name,Values=PrismataEval-heuristic' 'Name=instance-state-name,Values=running' --query 'Reservations[].Instances[].[InstanceId,State.Name,LaunchTime]' --output table"
echo ""
echo "Download results:"
echo "  aws s3 sync s3://$BUCKET/eval-results/ eval-results/ --region $REGION --exclude '*' --include 'heuristic_eval_*'"
