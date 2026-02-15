#!/bin/bash
# Launch EC2 Windows instance for self-play generation
# Usage: bash aws/launch_selfplay.sh [INSTANCE_TYPE] [NUM_GAMES]
#
# Examples:
#   bash aws/launch_selfplay.sh              # c5.4xlarge, 2500 games
#   bash aws/launch_selfplay.sh c5.2xlarge 1000
#   bash aws/launch_selfplay.sh c5.9xlarge 5000

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

INSTANCE_TYPE="${1:-t3.small}"
NUM_GAMES="${2:-2500}"
REGION="eu-north-1"
AMI="ami-0adc3f10e1311b184"  # Windows Server 2022 Base
KEY_NAME="prismata-selfplay"
SG_ID="sg-02117c219481e8e6a"
PROFILE="PrismataSelfPlayEC2"
BUCKET="prismata-selfplay-data"

echo "=== Prismata Self-Play EC2 Launch ==="
echo "  Instance: $INSTANCE_TYPE"
echo "  Games:    $NUM_GAMES"
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
echo "  Processes: $PROCESSES (4 threads each)"
echo "  Games/process: $GAMES_PER_PROCESS"
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

Read-S3Object -BucketName $bucket -Key "deploy/Prismata_Testing.exe" -File "C:\selfplay\Prismata_Testing.exe"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/config.txt" -File "C:\selfplay\asset\config\config.txt"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/cardLibrary.jso" -File "C:\selfplay\asset\config\cardLibrary.jso"
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/neural_weights.bin" -File "C:\selfplay\asset\config\neural_weights.bin"
Write-Host "Download complete"

# Patch config: set games and threads
$config = Get-Content "C:\selfplay\asset\config\config.txt" -Raw
ENDSCRIPT
)

# Inject the dynamic values
USERDATA+="
\$gamesPerProcess = $GAMES_PER_PROCESS
\$numProcesses = $PROCESSES
"

USERDATA+=$(cat <<'ENDSCRIPT2'

# Disable all tournaments, enable SelfPlay_CI with correct game count
$config = $config -replace '"run":true', '"run":false'
$config = $config -replace '("name":"SelfPlay_CI"[^}]*"run":)false', '${1}true'
$config = $config -replace '("name":"SelfPlay_CI"[^}]*"rounds":)\d+', "`${1}$gamesPerProcess"

# Keep Threads at 4 (already set in config)
Set-Content "C:\selfplay\asset\config\config.txt" $config
Write-Host "Config patched: $gamesPerProcess games/process, $numProcesses processes"

# Launch multiple self-play processes
$jobs = @()
for ($i = 0; $i -lt $numProcesses; $i++) {
    Write-Host "Launching worker $i..."
    $job = Start-Process -FilePath "C:\selfplay\Prismata_Testing.exe" `
        -WorkingDirectory "C:\selfplay" `
        -RedirectStandardOutput "C:\selfplay\log_worker_$i.txt" `
        -PassThru
    $jobs += $job
    Start-Sleep -Seconds 3  # stagger for unique run_* dirs
}

Write-Host "All $numProcesses workers launched. Waiting for completion..."

# Wait for all to finish
foreach ($job in $jobs) {
    $job.WaitForExit()
    Write-Host "Worker PID $($job.Id) finished with exit code $($job.ExitCode)"
}

Write-Host "All workers complete. Uploading results..."

# Upload all selfplay data to S3
$runDirs = Get-ChildItem "C:\selfplay\training\data\selfplay\run_*" -Directory
foreach ($dir in $runDirs) {
    $files = Get-ChildItem $dir.FullName -File
    foreach ($f in $files) {
        $key = "results/$runId/$($dir.Name)/$($f.Name)"
        Write-S3Object -BucketName $bucket -Key $key -File $f.FullName
        Write-Host "Uploaded: $key"
    }
}

# Upload logs
for ($i = 0; $i -lt $numProcesses; $i++) {
    $logFile = "C:\selfplay\log_worker_$i.txt"
    if (Test-Path $logFile) {
        Write-S3Object -BucketName $bucket -Key "results/$runId/log_worker_$i.txt" -File $logFile
    }
}

Write-Host "=== Upload complete. Shutting down. ==="
Stop-Transcript

# Upload boot log
Write-S3Object -BucketName $bucket -Key "results/$runId/selfplay_boot.log" -File "C:\selfplay_boot.log"

# Self-terminate
Stop-Computer -Force
</powershell>
ENDSCRIPT2
)

# Base64 encode the user data
USERDATA_B64=$(echo "$USERDATA" | base64 -w 0)

# Wait a moment for IAM instance profile propagation
echo "Launching instance..."

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name="$PROFILE" \
  --user-data "$USERDATA_B64" \
  --instance-initiated-shutdown-behavior terminate \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataSelfPlay-$NUM_GAMES}]" \
  --query 'Instances[0].InstanceId' \
  --output text \
  --region "$REGION" 2>&1)

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
