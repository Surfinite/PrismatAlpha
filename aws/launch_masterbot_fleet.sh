#!/bin/bash
# Launch a fleet of EC2 instances for large-scale MasterBot selfplay data generation.
# Splits total games across on-demand + spot instances to maximize throughput.
#
# Usage: bash aws/launch_masterbot_fleet.sh [TOTAL_GAMES] [THINK_TIME_MS]
#   bash aws/launch_masterbot_fleet.sh 200000        # 200K games, 1s think
#   bash aws/launch_masterbot_fleet.sh 200000 2000   # 200K games, 2s think
#
# Prerequisites:
#   1. Upload deploy files: bash aws/launch_masterbot_selfplay.sh --upload
#   2. IAM role PrismataSelfPlayEC2 with S3 access
#
# Each instance syncs to S3 every 5 minutes — spot termination is safe.
# All instances auto-terminate on completion.

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

REGION="eu-north-1"
AMI="ami-0adc3f10e1311b184"  # Windows Server 2022 Base
KEY_NAME="prismata-selfplay"
SG_ID="sg-02117c219481e8e6a"
PROFILE="PrismataSelfPlayEC2"
BUCKET="prismata-selfplay-data"
INSTANCE_TYPE="c5.4xlarge"
WORKERS_PER_INSTANCE=14

# vCPU quotas (c5.4xlarge = 16 vCPU)
OD_VCPU_QUOTA=192
SPOT_VCPU_QUOTA=512
VCPU_PER_INSTANCE=16

TOTAL_GAMES="${1:-200000}"
THINK_TIME_MS="${2:-1000}"

OD_INSTANCES=$((OD_VCPU_QUOTA / VCPU_PER_INSTANCE))
SPOT_INSTANCES=$((SPOT_VCPU_QUOTA / VCPU_PER_INSTANCE))
TOTAL_INSTANCES=$((OD_INSTANCES + SPOT_INSTANCES))
GAMES_PER_INSTANCE=$(( (TOTAL_GAMES + TOTAL_INSTANCES - 1) / TOTAL_INSTANCES ))

# Estimate: ~882 games/hr per c5.4xlarge at 1s think time
EST_HOURS=$(python -c "print(f'{$GAMES_PER_INSTANCE / 882:.1f}')" 2>/dev/null || echo "?")
EST_COST_OD=$(python -c "print(f'{$OD_INSTANCES * 1.044 * $GAMES_PER_INSTANCE / 882:.0f}')" 2>/dev/null || echo "?")
EST_COST_SPOT=$(python -c "print(f'{$SPOT_INSTANCES * 0.83 * $GAMES_PER_INSTANCE / 882:.0f}')" 2>/dev/null || echo "?")
EST_COST_TOTAL=$(python -c "print(f'{$OD_INSTANCES * 1.044 * $GAMES_PER_INSTANCE / 882 + $SPOT_INSTANCES * 0.83 * $GAMES_PER_INSTANCE / 882:.0f}')" 2>/dev/null || echo "?")

echo "=== Prismata MasterBot Fleet Launch ==="
echo ""
echo "  Total games:    $TOTAL_GAMES"
echo "  Think time:     ${THINK_TIME_MS}ms"
echo "  Instance type:  $INSTANCE_TYPE ($WORKERS_PER_INSTANCE workers each)"
echo ""
echo "  On-demand:      $OD_INSTANCES instances (${OD_VCPU_QUOTA} vCPUs)"
echo "  Spot:           $SPOT_INSTANCES instances (${SPOT_VCPU_QUOTA} vCPUs)"
echo "  Total:          $TOTAL_INSTANCES instances"
echo "  Games/instance: $GAMES_PER_INSTANCE"
echo ""
echo "  Est. runtime:   ~${EST_HOURS} hours"
echo "  Est. cost:      ~\$${EST_COST_OD} (OD) + ~\$${EST_COST_SPOT} (spot) = ~\$${EST_COST_TOTAL} total"
echo ""
read -p "Launch fleet? (y/N) " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

FLEET_ID="fleet_$(date +%Y-%m-%d_%H-%M-%S)"
echo ""
echo "Fleet ID: $FLEET_ID"
echo ""

# Source the user-data template from the single-instance script
# We generate it inline to avoid coupling issues
generate_userdata() {
    local NUM_GAMES=$1
    local THINK_TIME_MS=$2
    local PARALLEL=$3
    local FLEET_ID=$4
    local INSTANCE_NUM=$5

    cat <<ENDSCRIPT
<powershell>
\$ErrorActionPreference = "Continue"
\$bucket = "prismata-selfplay-data"
\$runId = "${FLEET_ID}_i${INSTANCE_NUM}"

Start-Transcript -Path "C:\masterbot_boot.log" -Append

Write-Host "=== Prismata MasterBot Self-Play Worker Starting ==="
Write-Host "Run ID: \$runId"
Write-Host "Fleet: ${FLEET_ID}, Instance: ${INSTANCE_NUM}"

# --- Install Node.js ---
Write-Host "Installing Node.js LTS..."
\$nodeUrl = "https://nodejs.org/dist/v20.11.1/node-v20.11.1-x86.msi"
\$nodeInstaller = "C:\node_installer.msi"
Invoke-WebRequest -Uri \$nodeUrl -OutFile \$nodeInstaller -UseBasicParsing
Start-Process -Wait -FilePath "msiexec.exe" -ArgumentList "/i \`"\$nodeInstaller\`" /quiet /norestart"
\$env:Path = "C:\Program Files (x86)\nodejs;C:\Program Files\nodejs;" + \$env:Path
Write-Host "Node.js installed: \$(& node --version 2>&1)"

# --- Download deploy files from S3 ---
Write-Host "Downloading deploy files from S3..."

New-Item -ItemType Directory -Force -Path "C:\masterbot\js_engine" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\masterbot\bin\asset\config" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\masterbot\training_output" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\masterbot\tmp_swf_extract" | Out-Null

\$steamAIDir = "C:\Program Files (x86)\Steam\steamapps\common\Prismata\AI"
New-Item -ItemType Directory -Force -Path \$steamAIDir | Out-Null
Read-S3Object -BucketName \$bucket -Key "deploy/masterbot/PrismataAI.exe" -File "\$steamAIDir\PrismataAI.exe"

Read-S3Object -BucketName \$bucket -Key "deploy/masterbot/bin/asset/config/cardLibrary.jso" -File "C:\masterbot\bin\asset\config\cardLibrary.jso"
Read-S3Object -BucketName \$bucket -Key "deploy/masterbot/js_engine/matchup_config.json" -File "C:\masterbot\js_engine\matchup_config.json"

Write-Host "Downloading js_engine files..."
\$jsFiles = Get-S3Object -BucketName \$bucket -KeyPrefix "deploy/masterbot/js_engine/" | Where-Object { \$_.Key -match '\.js$' }
\$jsCount = 0
foreach (\$obj in \$jsFiles) {
    \$fileName = \$obj.Key -replace '^deploy/masterbot/js_engine/', ''
    Read-S3Object -BucketName \$bucket -Key \$obj.Key -File "C:\masterbot\js_engine\\\$fileName"
    \$jsCount++
}
Write-Host "Downloaded \$jsCount .js files"

Read-S3Object -BucketName \$bucket -Key "deploy/masterbot/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" -File "C:\masterbot\tmp_swf_extract\148_AI.AIThreadHandler_aiParamTextLoad.bin"
Read-S3Object -BucketName \$bucket -Key "deploy/masterbot/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" -File "C:\masterbot\tmp_swf_extract\93_AI.AIThreadHandler_aiParam_shortTextLoad.bin"
Write-Host "AI parameter files installed"

\$numGames = $NUM_GAMES
\$thinkTimeMs = $THINK_TIME_MS
\$parallel = $PARALLEL

Write-Host "Config: \$numGames games, \${thinkTimeMs}ms think time, \$parallel parallel workers"

\$nodeExe = "node"
if (-not (Get-Command \$nodeExe -ErrorAction SilentlyContinue)) {
    if (Test-Path "C:\Program Files\nodejs\node.exe") {
        \$nodeExe = "C:\Program Files\nodejs\node.exe"
    } elseif (Test-Path "C:\Program Files (x86)\nodejs\node.exe") {
        \$nodeExe = "C:\Program Files (x86)\nodejs\node.exe"
    } else {
        Write-Host "ERROR: Node.js not found"
        Stop-Transcript
        Write-S3Object -BucketName \$bucket -Key "results/\$runId/masterbot_boot.log" -File "C:\masterbot_boot.log"
        Stop-Computer -Force
        exit 1
    }
}

Write-Host "Using Node.js: \$(& \$nodeExe --version 2>&1)"

\$matchupArgs = @(
    "C:\masterbot\js_engine\matchup_clean.js",
    "--games", "\$numGames",
    "--player", "SteamAI",
    "--steam-difficulty", "HardestAI",
    "--think-time", "\$thinkTimeMs",
    "--parallel", "\$parallel",
    "--export-training", "C:\masterbot\training_output\\",
    "--resign", "0"
)

Write-Host "Command: \$nodeExe \$(\$matchupArgs -join ' ')"
Write-S3Object -BucketName \$bucket -Key "results/\$runId/matchup_config.json" -File "C:\masterbot\js_engine\matchup_config.json"

\$matchupProcess = Start-Process -FilePath \$nodeExe \`
    -ArgumentList \$matchupArgs \`
    -WorkingDirectory "C:\masterbot" \`
    -RedirectStandardOutput "C:\masterbot\matchup_stdout.log" \`
    -RedirectStandardError "C:\masterbot\matchup.log" \`
    -PassThru

Write-Host "Matchup runner PID: \$(\$matchupProcess.Id)"

function Sync-ToS3 {
    param(\$bucket, \$runId)
    \$syncCount = 0
    \$tempDir = "C:\masterbot\sync_temp"
    New-Item -ItemType Directory -Force -Path \$tempDir | Out-Null

    \$trainingFiles = Get-ChildItem "C:\masterbot\training_output\*" -File -ErrorAction SilentlyContinue
    foreach (\$f in \$trainingFiles) {
        try {
            Copy-Item \$f.FullName "\$tempDir\\\$(\$f.Name)" -Force
            Write-S3Object -BucketName \$bucket -Key "results/\$runId/training/\$(\$f.Name)" -File "\$tempDir\\\$(\$f.Name)"
            \$syncCount++
        } catch { Write-Host "[Sync] Warning: \$(\$f.Name): \$_" }
    }

    foreach (\$logFile in @("C:\masterbot\matchup.log", "C:\masterbot\matchup_stdout.log")) {
        if (Test-Path \$logFile) {
            try {
                \$logName = [System.IO.Path]::GetFileName(\$logFile)
                Copy-Item \$logFile "\$tempDir\\\$logName" -Force
                Write-S3Object -BucketName \$bucket -Key "results/\$runId/\$logName" -File "\$tempDir\\\$logName"
            } catch { }
        }
    }

    Remove-Item \$tempDir -Recurse -Force -ErrorAction SilentlyContinue
    return \$syncCount
}

\$syncIntervalSec = 300
while (-not \$matchupProcess.HasExited) {
    Start-Sleep -Seconds \$syncIntervalSec
    \$count = Sync-ToS3 \$bucket \$runId
    Write-Host "[Sync] Uploaded \$count training files. Process running: \$(-not \$matchupProcess.HasExited)"
}

Write-Host "Matchup runner exited with code \$(\$matchupProcess.ExitCode)"

Write-Host "Final S3 sync..."
\$count = Sync-ToS3 \$bucket \$runId
Write-Host "[Sync] Final upload: \$count files"

Write-Host "=== MasterBot self-play complete. Shutting down. ==="
Stop-Transcript
Write-S3Object -BucketName \$bucket -Key "results/\$runId/masterbot_boot.log" -File "C:\masterbot_boot.log"
Stop-Computer -Force
</powershell>
ENDSCRIPT
}

# --- Launch on-demand instances ---
OD_IDS=()
echo "Launching $OD_INSTANCES on-demand instances..."
for i in $(seq 1 $OD_INSTANCES); do
    USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_fleet_tmp.ps1"
    generate_userdata $GAMES_PER_INSTANCE $THINK_TIME_MS $WORKERS_PER_INSTANCE "$FLEET_ID" "od${i}" > "$USERDATA_FILE"

    IID=$(aws ec2 run-instances \
      --image-id "$AMI" \
      --instance-type "$INSTANCE_TYPE" \
      --key-name "$KEY_NAME" \
      --security-group-ids "$SG_ID" \
      --iam-instance-profile Name="$PROFILE" \
      --user-data "file://$USERDATA_FILE" \
      --instance-initiated-shutdown-behavior terminate \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=MB-${FLEET_ID}-od${i}}]" \
      --query 'Instances[0].InstanceId' \
      --output text \
      --region "$REGION" 2>&1)

    if [[ "$IID" == i-* ]]; then
        OD_IDS+=("$IID")
        echo "  [OD $i/$OD_INSTANCES] $IID"
    else
        echo "  [OD $i/$OD_INSTANCES] FAILED: $IID"
    fi
done
rm -f "$USERDATA_FILE"

# --- Launch spot instances ---
SPOT_IDS=()
echo ""
echo "Launching $SPOT_INSTANCES spot instances..."
for i in $(seq 1 $SPOT_INSTANCES); do
    USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_fleet_tmp.ps1"
    generate_userdata $GAMES_PER_INSTANCE $THINK_TIME_MS $WORKERS_PER_INSTANCE "$FLEET_ID" "sp${i}" > "$USERDATA_FILE"

    IID=$(aws ec2 run-instances \
      --image-id "$AMI" \
      --instance-type "$INSTANCE_TYPE" \
      --key-name "$KEY_NAME" \
      --security-group-ids "$SG_ID" \
      --iam-instance-profile Name="$PROFILE" \
      --user-data "file://$USERDATA_FILE" \
      --instance-initiated-shutdown-behavior terminate \
      --instance-market-options '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"one-time","InstanceInterruptionBehavior":"terminate"}}' \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=MB-${FLEET_ID}-sp${i}}]" \
      --query 'Instances[0].InstanceId' \
      --output text \
      --region "$REGION" 2>&1)

    if [[ "$IID" == i-* ]]; then
        SPOT_IDS+=("$IID")
        echo "  [Spot $i/$SPOT_INSTANCES] $IID"
    else
        echo "  [Spot $i/$SPOT_INSTANCES] FAILED: $IID"
    fi
done
rm -f "$USERDATA_FILE"

echo ""
echo "=== Fleet Launched ==="
echo "  Fleet ID:       $FLEET_ID"
echo "  On-demand:      ${#OD_IDS[@]}/$OD_INSTANCES launched"
echo "  Spot:           ${#SPOT_IDS[@]}/$SPOT_INSTANCES launched"
echo "  Games/instance: $GAMES_PER_INSTANCE"
echo "  Total games:    $(( (${#OD_IDS[@]} + ${#SPOT_IDS[@]}) * GAMES_PER_INSTANCE ))"
echo "  Est. runtime:   ~${EST_HOURS} hours"
echo "  Est. cost:      ~\$${EST_COST_TOTAL}"
echo ""
echo "Monitor:"
echo "  aws ec2 describe-instances --filters 'Name=tag:Name,Values=MB-${FLEET_ID}-*' --query 'Reservations[].Instances[].[InstanceId,State.Name,Tags[?Key==\`Name\`].Value|[0]]' --output table --region $REGION"
echo ""
echo "Check progress:"
echo "  aws s3 ls s3://$BUCKET/results/ --region $REGION | grep $FLEET_ID"
echo ""
echo "Download all results:"
echo "  aws s3 sync s3://$BUCKET/results/ bin/training/data/masterbot/ --exclude '*' --include '${FLEET_ID}_*/training/*' --region $REGION"
echo ""
echo "Emergency stop all:"
echo "  aws ec2 terminate-instances --instance-ids ${OD_IDS[*]} ${SPOT_IDS[*]} --region $REGION"
