#!/bin/bash
# Launch EC2 Windows instance for MasterBot (SteamAI) self-play training data generation
# Usage: bash aws/launch_masterbot_selfplay.sh [--spot] [INSTANCE_TYPE] [NUM_GAMES] [THINK_TIME_MS] [PARALLEL]
#
# Both sides use Steam's PrismataAI.exe (SteamAI player) — no C++ Prismata_Testing.exe needed.
# Training data exported as JSONL via --export-training with parallel worker threads.
# S3 sync every 5 minutes — spot termination loses at most ~5 min of in-flight work.
#
# Examples:
#   bash aws/launch_masterbot_selfplay.sh                              # c5.4xlarge, 1000 games, 1s, 14 workers
#   bash aws/launch_masterbot_selfplay.sh --spot                       # same but spot pricing (~20% off Windows)
#   bash aws/launch_masterbot_selfplay.sh --spot c5.4xlarge 5000 1000 14
#   bash aws/launch_masterbot_selfplay.sh c5.xlarge 500 2000 3         # smaller instance, 3 workers
#
# Prerequisites:
#   1. Upload deploy files first: bash aws/launch_masterbot_selfplay.sh --upload
#   2. Ensure IAM role PrismataSelfPlayEC2 has S3 read/write access to prismata-selfplay-data

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

REGION="eu-north-1"
AMI="ami-0adc3f10e1311b184"  # Windows Server 2022 Base
KEY_NAME="prismata-selfplay"
SG_ID="sg-02117c219481e8e6a"
PROFILE="PrismataSelfPlayEC2"
BUCKET="prismata-selfplay-data"

# --- Upload mode: push deploy files to S3 ---
if [ "$1" = "--upload" ]; then
    echo "=== Uploading MasterBot deploy files to S3 ==="
    echo ""

    STEAM_EXE="C:/Program Files (x86)/Steam/steamapps/common/Prismata/AI/PrismataAI.exe"
    if [ ! -f "$STEAM_EXE" ]; then
        echo "ERROR: PrismataAI.exe not found at: $STEAM_EXE"
        echo "Install Prismata via Steam or provide the path manually."
        exit 1
    fi

    echo "Uploading PrismataAI.exe..."
    aws s3 cp "$STEAM_EXE" "s3://$BUCKET/deploy/masterbot/PrismataAI.exe" --region "$REGION"

    echo "Uploading cardLibrary.jso..."
    aws s3 cp "c:/libraries/PrismataAI/bin/asset/config/cardLibrary.jso" \
        "s3://$BUCKET/deploy/masterbot/bin/asset/config/cardLibrary.jso" --region "$REGION"

    echo "Uploading matchup_config.json..."
    aws s3 cp "c:/libraries/PrismataAI/js_engine/matchup_config.json" \
        "s3://$BUCKET/deploy/masterbot/js_engine/matchup_config.json" --region "$REGION"

    echo "Uploading js_engine/*.js files..."
    # Upload all .js files (matchup_clean.js and all its dependencies)
    JS_COUNT=0
    for f in c:/libraries/PrismataAI/js_engine/*.js; do
        fname=$(basename "$f")
        aws s3 cp "$f" "s3://$BUCKET/deploy/masterbot/js_engine/$fname" --region "$REGION" --quiet
        JS_COUNT=$((JS_COUNT + 1))
    done
    echo "  Uploaded $JS_COUNT .js files"

    echo "Uploading SWF-extracted AI parameter files..."
    aws s3 cp "c:/libraries/PrismataAI/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" \
        "s3://$BUCKET/deploy/masterbot/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" --region "$REGION"
    aws s3 cp "c:/libraries/PrismataAI/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" \
        "s3://$BUCKET/deploy/masterbot/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" --region "$REGION"

    echo ""
    echo "=== Upload complete ==="
    echo "Deploy files in s3://$BUCKET/deploy/masterbot/"
    echo ""
    echo "Verify with: aws s3 ls s3://$BUCKET/deploy/masterbot/ --recursive --region $REGION"
    exit 0
fi

# --- Parse --spot flag ---
USE_SPOT=false
if [ "$1" = "--spot" ]; then
    USE_SPOT=true
    shift
fi

# --- Launch mode ---
INSTANCE_TYPE="${1:-c5.4xlarge}"
NUM_GAMES="${2:-1000}"
THINK_TIME_MS="${3:-1000}"
PARALLEL="${4:-14}"

PRICING_MODE="on-demand"
if $USE_SPOT; then PRICING_MODE="spot"; fi

echo "=== Prismata MasterBot Self-Play EC2 Launch ==="
echo "  Instance: $INSTANCE_TYPE"
echo "  Pricing:  $PRICING_MODE"
echo "  Games:    $NUM_GAMES"
echo "  Think:    ${THINK_TIME_MS}ms"
echo "  Parallel: $PARALLEL workers"
echo "  Region:   $REGION"
echo "  Bucket:   $BUCKET"
echo "  Player:   SteamAI (both sides, difficulty=HardestAI)"
echo ""

# Create the PowerShell user-data script
USERDATA=$(cat <<'ENDSCRIPT'
<powershell>
$ErrorActionPreference = "Continue"
$bucket = "prismata-selfplay-data"
$runId = "masterbot_" + (Get-Date -Format "yyyy-MM-dd_HH-mm-ss")

# Log everything
Start-Transcript -Path "C:\masterbot_boot.log" -Append

Write-Host "=== Prismata MasterBot Self-Play Worker Starting ==="
Write-Host "Run ID: $runId"

# --- Install Node.js ---
Write-Host "Installing Node.js LTS..."
$nodeUrl = "https://nodejs.org/dist/v20.11.1/node-v20.11.1-x86.msi"
$nodeInstaller = "C:\node_installer.msi"
Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeInstaller -UseBasicParsing
Start-Process -Wait -FilePath "msiexec.exe" -ArgumentList "/i `"$nodeInstaller`" /quiet /norestart"
# Add Node.js to PATH for this session
$env:Path = "C:\Program Files (x86)\nodejs;C:\Program Files\nodejs;" + $env:Path
Write-Host "Node.js installed: $(& node --version 2>&1)"

# --- Download deploy files from S3 ---
Write-Host "Downloading deploy files from S3..."

# Create directory structure
New-Item -ItemType Directory -Force -Path "C:\masterbot\js_engine" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\masterbot\bin\asset\config" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\masterbot\training_output" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\masterbot\tmp_swf_extract" | Out-Null

# PrismataAI.exe — place at Steam's default path so steam_ai.js finds it
$steamAIDir = "C:\Program Files (x86)\Steam\steamapps\common\Prismata\AI"
New-Item -ItemType Directory -Force -Path $steamAIDir | Out-Null
Read-S3Object -BucketName $bucket -Key "deploy/masterbot/PrismataAI.exe" -File "$steamAIDir\PrismataAI.exe"
Write-Host "PrismataAI.exe installed to $steamAIDir"

# Card library
Read-S3Object -BucketName $bucket -Key "deploy/masterbot/bin/asset/config/cardLibrary.jso" -File "C:\masterbot\bin\asset\config\cardLibrary.jso"

# matchup_config.json
Read-S3Object -BucketName $bucket -Key "deploy/masterbot/js_engine/matchup_config.json" -File "C:\masterbot\js_engine\matchup_config.json"

# JS engine files — download all .js files from the deploy prefix
Write-Host "Downloading js_engine files..."
$jsFiles = Get-S3Object -BucketName $bucket -KeyPrefix "deploy/masterbot/js_engine/" | Where-Object { $_.Key -match '\.js$' }
$jsCount = 0
foreach ($obj in $jsFiles) {
    $fileName = $obj.Key -replace '^deploy/masterbot/js_engine/', ''
    Read-S3Object -BucketName $bucket -Key $obj.Key -File "C:\masterbot\js_engine\$fileName"
    $jsCount++
}
Write-Host "Downloaded $jsCount .js files"

# SWF-extracted AI parameter files (needed by ai_params.js)
Read-S3Object -BucketName $bucket -Key "deploy/masterbot/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" -File "C:\masterbot\tmp_swf_extract\148_AI.AIThreadHandler_aiParamTextLoad.bin"
Read-S3Object -BucketName $bucket -Key "deploy/masterbot/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" -File "C:\masterbot\tmp_swf_extract\93_AI.AIThreadHandler_aiParam_shortTextLoad.bin"
Write-Host "AI parameter files installed"

ENDSCRIPT
)

# Inject dynamic values
USERDATA+="
\$numGames = $NUM_GAMES
\$thinkTimeMs = $THINK_TIME_MS
\$parallel = $PARALLEL
"

USERDATA+=$(cat <<'ENDSCRIPT2'

Write-Host "Config: $numGames games, ${thinkTimeMs}ms think time, $parallel parallel workers"

# --- Launch matchup runner ---
Write-Host "Starting MasterBot self-play..."

$nodeExe = "node"
# Try common Node.js paths if not in PATH
if (-not (Get-Command $nodeExe -ErrorAction SilentlyContinue)) {
    if (Test-Path "C:\Program Files\nodejs\node.exe") {
        $nodeExe = "C:\Program Files\nodejs\node.exe"
    } elseif (Test-Path "C:\Program Files (x86)\nodejs\node.exe") {
        $nodeExe = "C:\Program Files (x86)\nodejs\node.exe"
    } else {
        Write-Host "ERROR: Node.js not found in PATH or standard locations"
        Stop-Transcript
        Write-S3Object -BucketName $bucket -Key "results/$runId/masterbot_boot.log" -File "C:\masterbot_boot.log"
        Stop-Computer -Force
        exit 1
    }
}

Write-Host "Using Node.js: $(& $nodeExe --version 2>&1)"

# Build the matchup command arguments
$matchupArgs = @(
    "C:\masterbot\js_engine\matchup_clean.js",
    "--games", "$numGames",
    "--player", "SteamAI",
    "--steam-difficulty", "HardestAI",
    "--think-time", "$thinkTimeMs",
    "--parallel", "$parallel",
    "--export-training", "C:\masterbot\training_output\",
    "--resign", "0"
)

Write-Host "Command: $nodeExe $($matchupArgs -join ' ')"

# Upload the patched config for inspection
Write-S3Object -BucketName $bucket -Key "results/$runId/matchup_config.json" -File "C:\masterbot\js_engine\matchup_config.json"

# Start the matchup process
$matchupProcess = Start-Process -FilePath $nodeExe `
    -ArgumentList $matchupArgs `
    -WorkingDirectory "C:\masterbot" `
    -RedirectStandardOutput "C:\masterbot\matchup_stdout.log" `
    -RedirectStandardError "C:\masterbot\matchup.log" `
    -PassThru

Write-Host "Matchup runner PID: $($matchupProcess.Id)"

# --- Periodic S3 sync function ---
function Sync-ToS3 {
    param($bucket, $runId)
    $syncCount = 0
    $tempDir = "C:\masterbot\sync_temp"
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

    # Sync training output JSONL files
    $trainingFiles = Get-ChildItem "C:\masterbot\training_output\*" -File -ErrorAction SilentlyContinue
    foreach ($f in $trainingFiles) {
        try {
            Copy-Item $f.FullName "$tempDir\$($f.Name)" -Force
            Write-S3Object -BucketName $bucket -Key "results/$runId/training/$($f.Name)" -File "$tempDir\$($f.Name)"
            $syncCount++
        } catch { Write-Host "[Sync] Warning: $($f.Name): $_" }
    }

    # Sync logs
    foreach ($logFile in @("C:\masterbot\matchup.log", "C:\masterbot\matchup_stdout.log")) {
        if (Test-Path $logFile) {
            try {
                $logName = [System.IO.Path]::GetFileName($logFile)
                Copy-Item $logFile "$tempDir\$logName" -Force
                Write-S3Object -BucketName $bucket -Key "results/$runId/$logName" -File "$tempDir\$logName"
            } catch { }
        }
    }

    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    return $syncCount
}

# --- Wait with periodic sync every 5 minutes ---
$syncIntervalSec = 300
while (-not $matchupProcess.HasExited) {
    Start-Sleep -Seconds $syncIntervalSec
    $count = Sync-ToS3 $bucket $runId
    Write-Host "[Sync] Uploaded $count training files. Process running: $(-not $matchupProcess.HasExited)"
}

Write-Host "Matchup runner exited with code $($matchupProcess.ExitCode)"

# --- Final sync ---
Write-Host "Final S3 sync..."
$count = Sync-ToS3 $bucket $runId
Write-Host "[Sync] Final upload: $count files"

# Upload boot log
Write-Host "=== MasterBot self-play complete. Shutting down. ==="
Stop-Transcript
Write-S3Object -BucketName $bucket -Key "results/$runId/masterbot_boot.log" -File "C:\masterbot_boot.log"

# Self-terminate
Stop-Computer -Force
</powershell>
ENDSCRIPT2
)

# Write user data to temp file
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_mb_tmp.ps1"
echo "$USERDATA" > "$USERDATA_FILE"

echo "Launching instance ($PRICING_MODE)..."

SPOT_OPTS=""
if $USE_SPOT; then
    SPOT_OPTS='--instance-market-options {"MarketType":"spot","SpotOptions":{"SpotInstanceType":"one-time","InstanceInterruptionBehavior":"terminate"}}'
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
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataMB-$NUM_GAMES-$PRICING_MODE}]" \
  --query 'Instances[0].InstanceId' \
  --output text \
  --region "$REGION" 2>&1)

rm -f "$USERDATA_FILE"

echo ""
echo "=== Instance Launched ==="
echo "  Instance ID: $INSTANCE_ID"
echo "  Type:        $INSTANCE_TYPE ($PRICING_MODE)"
echo "  Games:       $NUM_GAMES (--parallel $PARALLEL, --export-training)"
echo "  Think time:  ${THINK_TIME_MS}ms"
echo "  Player:      SteamAI (HardestAI) vs SteamAI (HardestAI)"
echo ""
echo "The instance will:"
echo "  1. Boot Windows Server (~3 min)"
echo "  2. Install Node.js LTS (~2 min)"
echo "  3. Download PrismataAI.exe + js_engine from S3 (~1 min)"
echo "  4. Run MasterBot self-play ($NUM_GAMES games, $PARALLEL parallel workers)"
echo "  5. Sync training JSONL to s3://$BUCKET/results/masterbot_*/"
echo "  6. Auto-terminate (no ongoing charges)"
echo ""
echo "Monitor progress:"
echo "  aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].State.Name' --region $REGION"
echo "  aws s3 ls s3://$BUCKET/results/ --region $REGION | grep masterbot | tail -1"
echo ""
echo "Download results when done:"
echo "  aws s3 sync s3://$BUCKET/results/ bin/training/data/masterbot/ --exclude '*' --include 'masterbot_*/training/*' --region $REGION"
