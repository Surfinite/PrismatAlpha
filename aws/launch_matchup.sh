#!/bin/bash
# Launch EC2 Windows instances for MCDSAI vs C++ AI matchup games
# Usage: bash aws/launch_matchup.sh [INSTANCE_TYPE] [NUM_GAMES] [NUM_INSTANCES] [THINK_TIME_MS]
#
# Environment variables:
#   WEIGHTS_KEY      - S3 key for neural weights (default: deploy/asset/config/neural_weights.bin)
#   MODEL_LABEL      - Label for instance tags (default: "default")
#   USE_SPOT         - "true" to use spot instances (default: false)
#   CPP_PLAYER       - C++ player name (default: OriginalHardestAI)
#   MCDSAI_DIFFICULTY - MCDSAI difficulty level (default: HardestAI)
#
# Examples:
#   bash aws/launch_matchup.sh c5.2xlarge 1000 12 7000
#   CPP_PLAYER=LiveHardestAI bash aws/launch_matchup.sh c5.2xlarge 100 1 3000
#   WEIGHTS_KEY=deploy/neural_weights_512h.bin MODEL_LABEL=512h bash aws/launch_matchup.sh c5.2xlarge 1000 12 7000
#
# Runs matchup_main.js (MCDSAI vs C++ AI via --suggest) on Windows EC2 instances.
# Each instance runs multiple Node.js worker processes in parallel.
# Results uploaded to s3://$CLOUD_BUCKET/matchup-results/<runId>/

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

INSTANCE_TYPE="${1:-c5.2xlarge}"
NUM_GAMES="${2:-1000}"
NUM_INSTANCES="${3:-1}"
THINK_TIME_MS="${4:-7000}"
WEIGHTS_KEY="${WEIGHTS_KEY:-deploy/asset/config/neural_weights.bin}"
MODEL_LABEL="${MODEL_LABEL:-default}"
USE_SPOT="${USE_SPOT:-false}"
CPP_PLAYER="${CPP_PLAYER:-OriginalHardestAI}"
MCDSAI_DIFFICULTY="${MCDSAI_DIFFICULTY:-HardestAI}"
REGION="${AWS_REGION:-eu-north-1}"
AMI="${AWS_AMI_WINDOWS:?Set AWS_AMI_WINDOWS in cloud-config.env}"
KEY_NAME="${AWS_KEY_NAME:?Set AWS_KEY_NAME in cloud-config.env}"
SG_ID="${AWS_SG_ID:?Set AWS_SG_ID in cloud-config.env}"
PROFILE="${AWS_IAM_PROFILE:?Set AWS_IAM_PROFILE in cloud-config.env}"
BUCKET="${CLOUD_BUCKET:?Set CLOUD_BUCKET in cloud-config.env}"

# Determine worker count from instance type
# Each matchup game uses ~1 core average (MCDSAI and C++ alternate, never overlap)
case "$INSTANCE_TYPE" in
  c5.xlarge)   WORKERS=3 ;;   # 4 vCPU
  c5.2xlarge)  WORKERS=4 ;;   # 8 vCPU
  c5.4xlarge)  WORKERS=8 ;;   # 16 vCPU
  c5.9xlarge)  WORKERS=16 ;;  # 36 vCPU
  *)           WORKERS=2 ;;
esac

# Compute game distribution
GAMES_PER_INSTANCE=$(( (NUM_GAMES + NUM_INSTANCES - 1) / NUM_INSTANCES ))
GAMES_PER_WORKER=$(( (GAMES_PER_INSTANCE + WORKERS - 1) / WORKERS ))
TOTAL_ESTIMATED=$(( GAMES_PER_WORKER * WORKERS * NUM_INSTANCES ))

echo "=== Prismata MCDSAI Matchup EC2 Launch ==="
echo "  Instance:    $INSTANCE_TYPE x $NUM_INSTANCES"
echo "  Total games: $NUM_GAMES (estimated actual: $TOTAL_ESTIMATED)"
echo "  Workers:     $WORKERS per instance"
echo "  Games/inst:  $GAMES_PER_INSTANCE ($GAMES_PER_WORKER per worker)"
echo "  Think time:  ${THINK_TIME_MS}ms (C++)"
echo "  C++ player:  $CPP_PLAYER"
echo "  MCDSAI diff: $MCDSAI_DIFFICULTY"
echo "  Weights:     $WEIGHTS_KEY"
echo "  Model:       $MODEL_LABEL"
echo "  Region:      $REGION"
echo "  Bucket:      $BUCKET"
echo ""

# Check that deploy files exist on S3
echo "Verifying S3 deploy files..."
MISSING=0
for KEY in \
    "deploy/Prismata_Testing.exe" \
    "deploy/js_engine/matchup_main.js" \
    "deploy/tmp_browser_client/MCDSAI3441.js" \
    "deploy/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" \
    "deploy/asset/config/cardLibrary.jso" \
    "$WEIGHTS_KEY"; do
    if ! aws s3 ls "s3://$BUCKET/$KEY" --region "$REGION" > /dev/null 2>&1; then
        echo "  MISSING: s3://$BUCKET/$KEY"
        MISSING=$((MISSING + 1))
    fi
done
if [ "$MISSING" -gt 0 ]; then
    echo ""
    echo "ERROR: $MISSING required file(s) missing on S3. Deploy first:"
    echo "  bash aws/deploy_for_matchup.sh"
    exit 1
fi
echo "  All deploy files verified."
echo ""

# === Section 1: Static PowerShell heredoc (single-quoted to protect PS syntax) ===
# Uses __PLACEHOLDER__ pattern for values that come from cloud-config.env
USERDATA=$(cat <<'ENDSCRIPT'
<powershell>
$ErrorActionPreference = "Continue"
$bucket = "__CLOUD_BUCKET__"
$region = "__AWS_REGION__"
$runId = "matchup_" + (Get-Date -Format "yyyy-MM-dd_HH-mm-ss") + "_" + $env:COMPUTERNAME

Start-Transcript -Path "C:\matchup_boot.log" -Append

Write-Host "=== Prismata MCDSAI Matchup Worker Starting ==="
Write-Host "Run ID: $runId"

# Install VC++ Redistributable (required for Prismata_Testing.exe)
Write-Host "Installing VC++ Redistributable..."
$vcUrl = "https://aka.ms/vs/17/release/vc_redist.x86.exe"
Invoke-WebRequest -Uri $vcUrl -OutFile "C:\vc_redist.x86.exe"
Start-Process -Wait -FilePath "C:\vc_redist.x86.exe" -ArgumentList "/install /quiet /norestart"
Write-Host "VC++ Redistributable installed"

# Install Node.js (portable zip — no MSI, no admin prompts)
Write-Host "Installing Node.js..."
$nodeVer = "v20.11.0"
$nodeUrl = "https://nodejs.org/dist/$nodeVer/node-$nodeVer-win-x64.zip"
Invoke-WebRequest -Uri $nodeUrl -OutFile "C:\node.zip"
Expand-Archive -Path "C:\node.zip" -DestinationPath "C:\"
$env:PATH = "C:\node-$nodeVer-win-x64;$env:PATH"
[Environment]::SetEnvironmentVariable("PATH", $env:PATH, "Process")
Write-Host "Node.js installed: $(node --version)"

# Create directory structure matching local project layout
# CRITICAL: matchup_main.js uses relative paths from js_engine/:
#   ../bin/Prismata_Testing.exe
#   ../bin/asset/config/cardLibrary.jso
#   ../tmp_browser_client/MCDSAI3441.js
#   ../tmp_swf_extract/*.bin
New-Item -ItemType Directory -Force -Path "C:\matchup\js_engine" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\bin\asset\config" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\tmp_browser_client" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\tmp_swf_extract" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\output" | Out-Null

# Download JS engine files from S3
Write-Host "Downloading JS engine..."
$jsFiles = Get-S3Object -BucketName $bucket -KeyPrefix "deploy/js_engine/" -Region $region
foreach ($f in $jsFiles) {
    if ($f.Key -match '\.js$') {
        $localName = $f.Key -replace '^deploy/js_engine/', ''
        Read-S3Object -BucketName $bucket -Key $f.Key -File "C:\matchup\js_engine\$localName" -Region $region
    }
}

Write-Host "Downloading MCDSAI + AI params..."
Read-S3Object -BucketName $bucket -Key "deploy/tmp_browser_client/MCDSAI3441.js" `
    -File "C:\matchup\tmp_browser_client\MCDSAI3441.js" -Region $region
Read-S3Object -BucketName $bucket -Key "deploy/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" `
    -File "C:\matchup\tmp_swf_extract\148_AI.AIThreadHandler_aiParamTextLoad.bin" -Region $region
Read-S3Object -BucketName $bucket -Key "deploy/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" `
    -File "C:\matchup\tmp_swf_extract\93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" -Region $region

Write-Host "Downloading C++ exe + config..."
Read-S3Object -BucketName $bucket -Key "deploy/Prismata_Testing.exe" `
    -File "C:\matchup\bin\Prismata_Testing.exe" -Region $region
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/config.txt" `
    -File "C:\matchup\bin\asset\config\config.txt" -Region $region
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/cardLibrary.jso" `
    -File "C:\matchup\bin\asset\config\cardLibrary.jso" -Region $region
Read-S3Object -BucketName $bucket -Key "__WEIGHTS_KEY__" `
    -File "C:\matchup\bin\asset\config\neural_weights.bin" -Region $region

Write-Host "Download complete."
ENDSCRIPT
)

# === Section 2: Placeholder replacement (single-quoted heredoc can't expand bash vars) ===
USERDATA="${USERDATA/__CLOUD_BUCKET__/$BUCKET}"
USERDATA="${USERDATA//__AWS_REGION__/$REGION}"
USERDATA="${USERDATA/__WEIGHTS_KEY__/$WEIGHTS_KEY}"

# === Section 3: Dynamic value injection (bash concatenation for computed values) ===
USERDATA+="
\$numWorkers = $WORKERS
\$gamesPerWorker = $GAMES_PER_WORKER
\$thinkTime = $THINK_TIME_MS
\$cppPlayer = \"$CPP_PLAYER\"
\$mcdsaiDifficulty = \"$MCDSAI_DIFFICULTY\"
"

# === Section 4: Worker launch + S3 sync + auto-terminate (single-quoted heredoc) ===
USERDATA+=$(cat <<'ENDSCRIPT2'

Write-Host "Config: $numWorkers workers, $gamesPerWorker games/worker, ${thinkTime}ms think"
Write-Host "C++ player: $cppPlayer, MCDSAI difficulty: $mcdsaiDifficulty"

# Launch parallel matchup workers
$jobs = @()
for ($i = 0; $i -lt $numWorkers; $i++) {
    Write-Host "Launching matchup worker $i ($gamesPerWorker games)..."

    $nodeArgs = "matchup_main.js" +
        " --games $gamesPerWorker" +
        " --think-time $thinkTime" +
        " --player $cppPlayer" +
        " --difficulty $mcdsaiDifficulty" +
        " --exe ..\bin\Prismata_Testing.exe" +
        " --jsonl ..\output\matchup_worker_${i}.jsonl" +
        " --summary-json ..\output\summary_${i}.json"

    $job = Start-Process -FilePath "node" `
        -ArgumentList $nodeArgs `
        -WorkingDirectory "C:\matchup\js_engine" `
        -RedirectStandardOutput "C:\matchup\output\stdout_worker_$i.txt" `
        -RedirectStandardError "C:\matchup\output\log_worker_$i.txt" `
        -PassThru

    $jobs += $job
    Start-Sleep -Seconds 2   # stagger for unique PIDs (temp file naming)
}

Write-Host "All $numWorkers workers launched. Waiting with periodic S3 sync..."

# Periodic S3 sync function — copies files to temp dir first to avoid lock conflicts
function Sync-MatchupToS3 {
    param($bucket, $runId, $region, $numWorkers)
    $syncCount = 0
    $tempBase = "C:\matchup\sync_temp"
    New-Item -ItemType Directory -Force -Path $tempBase | Out-Null

    # Summary JSONs (structured results)
    $summaryFiles = Get-ChildItem "C:\matchup\output\summary_*.json" -ErrorAction SilentlyContinue
    foreach ($f in $summaryFiles) {
        try {
            Copy-Item $f.FullName "$tempBase\$($f.Name)" -Force
            Write-S3Object -BucketName $bucket -Key "matchup-results/$runId/$($f.Name)" `
                -File "$tempBase\$($f.Name)" -Region $region
            $syncCount++
        } catch { Write-Host "[Sync] Warning: $($f.Name): $_" }
    }

    # JSONL training data
    $jsonlFiles = Get-ChildItem "C:\matchup\output\matchup_worker_*.jsonl" -ErrorAction SilentlyContinue
    foreach ($f in $jsonlFiles) {
        try {
            Copy-Item $f.FullName "$tempBase\$($f.Name)" -Force
            Write-S3Object -BucketName $bucket -Key "matchup-results/$runId/$($f.Name)" `
                -File "$tempBase\$($f.Name)" -Region $region
            $syncCount++
        } catch { }
    }

    # Worker logs (stderr + stdout)
    for ($i = 0; $i -lt $numWorkers; $i++) {
        foreach ($prefix in @("log_worker", "stdout_worker")) {
            $logFile = "C:\matchup\output\${prefix}_$i.txt"
            if (Test-Path $logFile) {
                try {
                    Copy-Item $logFile "$tempBase\${prefix}_$i.txt" -Force
                    Write-S3Object -BucketName $bucket `
                        -Key "matchup-results/$runId/${prefix}_$i.txt" `
                        -File "$tempBase\${prefix}_$i.txt" -Region $region
                    $syncCount++
                } catch { }
            }
        }
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
    $count = Sync-MatchupToS3 $bucket $runId $region $numWorkers
    $running = @($jobs | Where-Object { -not $_.HasExited })
    Write-Host "[Sync] Uploaded $count files. Workers running: $($running.Count)/$numWorkers"
}

# Report exit codes
foreach ($job in $jobs) {
    Write-Host "Worker PID $($job.Id) finished with exit code $($job.ExitCode)"
}

# Final sync
Write-Host "All workers complete. Final S3 sync..."
$count = Sync-MatchupToS3 $bucket $runId $region $numWorkers
Write-Host "[Sync] Final upload: $count files"

Write-Host "=== Upload complete. Shutting down. ==="
Stop-Transcript
Write-S3Object -BucketName $bucket -Key "matchup-results/$runId/matchup_boot.log" `
    -File "C:\matchup_boot.log" -Region $region
Stop-Computer -Force
</powershell>
ENDSCRIPT2
)

# Write user data to temp file
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_matchup_tmp.ps1"
echo "$USERDATA" > "$USERDATA_FILE"

# Launch instances
echo "Launching $NUM_INSTANCES instance(s)..."
echo ""

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
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataMatchup-${MODEL_LABEL}-${NUM_GAMES}g}]" \
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
echo "  Launched:       $LAUNCHED / $NUM_INSTANCES instances"
echo "  Model:          $MODEL_LABEL"
echo "  Workers/inst:   $WORKERS"
echo "  Games/worker:   $GAMES_PER_WORKER"
echo "  Games/inst:     $(( GAMES_PER_WORKER * WORKERS ))"
echo "  Total games:    ~$(( GAMES_PER_WORKER * WORKERS * LAUNCHED ))"
echo "  Think time:     ${THINK_TIME_MS}ms"
echo "  C++ player:     $CPP_PLAYER"
echo "  MCDSAI diff:    $MCDSAI_DIFFICULTY"
echo ""
echo "Each instance will:"
echo "  1. Boot Windows Server (~3 min)"
echo "  2. Install VC++ runtime + Node.js (~2 min)"
echo "  3. Download JS engine + exe + config + weights from S3 (~1 min)"
echo "  4. Run $WORKERS matchup_main.js workers ($GAMES_PER_WORKER games each)"
echo "  5. Upload results to s3://$BUCKET/matchup-results/"
echo "  6. Auto-terminate"
echo ""
echo "Monitor:"
echo "  aws ec2 describe-instances --region $REGION --filters 'Name=tag:Name,Values=PrismataMatchup-*' 'Name=instance-state-name,Values=running' --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==\`Name\`].Value|[0],State.Name]' --output table"
echo ""
echo "Download results:"
echo "  aws s3 sync s3://$BUCKET/matchup-results/ matchup-results/ --region $REGION"
