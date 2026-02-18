#!/bin/bash
# Launch GCP Compute Engine Windows instance for self-play generation
# Usage: bash gcp/launch_selfplay.sh [INSTANCE_TYPE] [NUM_GAMES] [THINK_TIME_S] [VM_MULTIPLIER] [NUM_INSTANCES]
#
# Examples:
#   bash gcp/launch_selfplay.sh                              # n2-standard-8, 5000 games, 1s, 2x, 1 instance
#   bash gcp/launch_selfplay.sh n2-standard-8 5000 1 2 4     # 4 instances
#   USE_SPOT=true bash gcp/launch_selfplay.sh n2-standard-8 5000 1 2 8  # 8 spot instances

export PATH="$PATH:/c/google-cloud-sdk/bin:/c/Program Files/Amazon/AWSCLIV2"

# Verify gcloud is available
if ! command -v gcloud &>/dev/null; then
    echo "ERROR: gcloud not found in PATH. Install Google Cloud SDK or check PATH."
    echo "  PATH=$PATH"
    exit 1
fi

INSTANCE_TYPE="${1:-n2-standard-8}"
NUM_GAMES="${2:-5000}"
THINK_TIME="${3:-1}"
VM_MULTIPLIER="${4:-2}"
NUM_INSTANCES="${5:-1}"
USE_SPOT="${USE_SPOT:-false}"
PROJECT="prismata-selfplay"
ZONE="us-central1-a"
BUCKET="prismata-selfplay-data"
IMAGE_FAMILY="windows-2022"
IMAGE_PROJECT="windows-cloud"

# Load AWS credentials for S3 uploads
CRED_FILE="$(cd "$(dirname "$0")" && pwd)/.aws_credentials"
if [ ! -f "$CRED_FILE" ]; then
    echo "ERROR: AWS credentials not found at $CRED_FILE"
    echo "Create it with:"
    echo "  AWS_ACCESS_KEY_ID=..."
    echo "  AWS_SECRET_ACCESS_KEY=..."
    exit 1
fi
source "$CRED_FILE"

echo "=== Prismata Self-Play GCP Launch ==="
echo "  Instance: $INSTANCE_TYPE"
echo "  Games:    $NUM_GAMES"
echo "  Think:    ${THINK_TIME}s x ${VM_MULTIPLIER} multiplier"
echo "  Zone:     $ZONE"
echo "  Count:    $NUM_INSTANCES"
echo "  Spot:     $USE_SPOT"
echo ""

# Determine process count from instance type
case "$INSTANCE_TYPE" in
  n2-standard-2|n2-highcpu-2|e2-standard-2)   PROCESSES=1 ;;
  n2-standard-4|n2-highcpu-4|e2-standard-4)   PROCESSES=1 ;;
  n2-standard-8|n2-highcpu-8|e2-standard-8)   PROCESSES=2 ;;
  n2-standard-16|n2-highcpu-16)               PROCESSES=4 ;;
  n2-standard-32|n2-highcpu-32)               PROCESSES=8 ;;
  *)                                           PROCESSES=1 ;;
esac

GAMES_PER_PROCESS=$(( (NUM_GAMES + PROCESSES - 1) / PROCESSES ))
TIME_LIMIT_MS=$(python -c "print(int($THINK_TIME * $VM_MULTIPLIER * 1000))")
echo "  Processes: $PROCESSES (4 threads each)"
echo "  Games/process: $GAMES_PER_PROCESS"
echo "  Think time: ${THINK_TIME}s x ${VM_MULTIPLIER} = ${TIME_LIMIT_MS}ms"
echo ""

# Build the PowerShell startup script
STARTUP_SCRIPT=$(cat <<'ENDSCRIPT'
$ErrorActionPreference = "Continue"
$bucket = "prismata-selfplay-data"
$runId = (Get-Date -Format "yyyy-MM-dd_HH-mm-ss")

Start-Transcript -Path "C:\selfplay_boot.log" -Append
Write-Host "=== Prismata Self-Play GCP Worker Starting ==="
Write-Host "Run ID: $runId"

# Get instance metadata
$metadataBase = "http://metadata.google.internal/computeMetadata/v1"
$headers = @{"Metadata-Flavor" = "Google"}
$instanceName = Invoke-RestMethod -Uri "$metadataBase/instance/name" -Headers $headers
$instanceZone = (Invoke-RestMethod -Uri "$metadataBase/instance/zone" -Headers $headers).Split("/")[-1]
$awsKeyId = Invoke-RestMethod -Uri "$metadataBase/instance/attributes/aws-key-id" -Headers $headers
$awsSecretKey = Invoke-RestMethod -Uri "$metadataBase/instance/attributes/aws-secret-key" -Headers $headers

Write-Host "Instance: $instanceName in $instanceZone"

# Windows Defender fix: full desktop image (windows-2022) is less aggressive than Server Core.
# Previous windows-2022-core + exclusions still killed exe after ~8 games.
# Add exclusions, disable monitoring, verify, then wait for settings to apply.
Add-MpPreference -ExclusionPath 'C:\selfplay' -ErrorAction SilentlyContinue
Add-MpPreference -ExclusionProcess 'Prismata_Testing.exe' -ErrorAction SilentlyContinue
Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5
$prefs = Get-MpPreference
Write-Host "Defender exclusion paths: $($prefs.ExclusionPath -join ', ')"
Write-Host "Defender exclusion processes: $($prefs.ExclusionProcess -join ', ')"
Write-Host "Defender realtime disabled: $($prefs.DisableRealtimeMonitoring)"

# Enable WER crash dumps for the exe
$werKey = "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\Prismata_Testing.exe"
New-Item -Path $werKey -Force | Out-Null
Set-ItemProperty -Path $werKey -Name "DumpFolder" -Value "C:\selfplay\crashdumps" -Type ExpandString
Set-ItemProperty -Path $werKey -Name "DumpType" -Value 2 -Type DWord
Set-ItemProperty -Path $werKey -Name "DumpCount" -Value 5 -Type DWord
New-Item -ItemType Directory -Force -Path "C:\selfplay\crashdumps" | Out-Null
Write-Host "WER crash dumps enabled (full dumps to C:\selfplay\crashdumps)"

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

# Configure AWS credentials
$env:AWS_ACCESS_KEY_ID = $awsKeyId
$env:AWS_SECRET_ACCESS_KEY = $awsSecretKey
$env:AWS_DEFAULT_REGION = "eu-north-1"

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
ENDSCRIPT
)

# Inject dynamic values
STARTUP_SCRIPT+="
\$gamesPerProcess = $GAMES_PER_PROCESS
\$numProcesses = $PROCESSES
\$timeLimitMs = $TIME_LIMIT_MS
"

STARTUP_SCRIPT+=$(cat <<'ENDSCRIPT2'

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

# Patch player TimeLimit
$config = $config -replace '("OriginalHardestAI_1s"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"
$config = $config -replace '("OriginalHardestAI_Copy_1s"\s*:\s*\{[^}]*"TimeLimit"\s*:\s*)\d+', "`${1}$timeLimitMs"

Set-Content "C:\selfplay\asset\config\config.txt" $config -Encoding ascii
Write-Host "Config patched: $gamesPerProcess games/process, $numProcesses processes, TimeLimit=${timeLimitMs}ms"

# Upload patched config for inspection
aws s3 cp "C:\selfplay\asset\config\config.txt" "s3://$bucket/results/$runId/patched_config.txt" --region eu-north-1

# Launch workers
$jobs = @()
for ($i = 0; $i -lt $numProcesses; $i++) {
    Write-Host "Launching worker $i..."
    $job = Start-Process -FilePath "C:\selfplay\Prismata_Testing.exe" `
        -WorkingDirectory "C:\selfplay" `
        -RedirectStandardOutput "C:\selfplay\log_stdout_$i.txt" `
        -RedirectStandardError "C:\selfplay\log_worker_$i.txt" `
        -PassThru
    $jobs += $job
    Write-Host "Worker $i PID: $($job.Id)"
    Start-Sleep -Seconds 3
}

Write-Host "All $numProcesses workers launched. Waiting with periodic S3 sync..."

# S3 sync function — copies files to temp dir first to avoid lock conflicts
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
            $stdoutLog = "C:\selfplay\log_stdout_$i.txt"
            if (Test-Path $stdoutLog) {
                Copy-Item $stdoutLog "$tempBase\log_stdout_$i.txt" -Force
                aws s3 cp "$tempBase\log_stdout_$i.txt" "s3://$bucket/results/$runId/log_stdout_$i.txt" --region eu-north-1 2>&1 | Out-Null
            }
        } catch { }
    }
    Remove-Item $tempBase -Recurse -Force -ErrorAction SilentlyContinue
    return $syncCount
}

# Monitor workers every 30s with periodic S3 sync every 5 min
$monitorCount = 0
while ($true) {
    Start-Sleep -Seconds 30
    $monitorCount++
    $running = @($jobs | Where-Object { -not $_.HasExited })
    $elapsed = $monitorCount * 30
    Write-Host "[Monitor ${elapsed}s] Workers alive: $($running.Count)/$numProcesses"
    if ($running.Count -eq 0) {
        Write-Host "[Monitor] All workers dead. Checking event log..."
        $crashEvents = Get-WinEvent -FilterHashtable @{LogName='Application'; Level=1,2; StartTime=(Get-Date).AddMinutes(-10)} -MaxEvents 20 -ErrorAction SilentlyContinue
        foreach ($evt in $crashEvents) {
            Write-Host "[EventLog] $($evt.TimeCreated) $($evt.Id) $($evt.ProviderName): $($evt.Message.Substring(0, [Math]::Min(800, $evt.Message.Length)))"
        }
        break
    }
    # S3 sync every 5 minutes (every 10th 30s interval)
    if ($monitorCount % 10 -eq 0) {
        $syncCount = Sync-ToS3 $bucket $runId $numProcesses
        Write-Host "[Sync ${elapsed}s] Uploaded $syncCount files"
    }
}

foreach ($job in $jobs) {
    Write-Host "Worker PID $($job.Id) finished with exit code $($job.ExitCode)"
}

# Final sync
Write-Host "All workers complete. Final S3 sync..."
$count = Sync-ToS3 $bucket $runId $numProcesses
Write-Host "[Sync] Final upload: $count files"

# Upload crash dumps if any
$dumps = Get-ChildItem "C:\selfplay\crashdumps\*.dmp" -ErrorAction SilentlyContinue
if ($dumps) {
    Write-Host "Found $($dumps.Count) crash dump(s), uploading..."
    foreach ($d in $dumps) {
        aws s3 cp $d.FullName "s3://$bucket/results/$runId/crashdumps/$($d.Name)" --region eu-north-1
        Write-Host "Uploaded crash dump: $($d.Name) ($([math]::Round($d.Length/1MB))MB)"
    }
} else {
    Write-Host "No crash dumps found"
}

# Upload boot log
aws s3 cp "C:\selfplay_boot.log" "s3://$bucket/results/$runId/selfplay_boot.log" --region eu-north-1

Write-Host "=== Upload complete. Self-deleting instance. ==="
Stop-Transcript

# Self-delete the instance
& gcloud compute instances delete $instanceName --zone=$instanceZone --quiet 2>&1
# Fallback: shutdown if delete fails
Stop-Computer -Force
ENDSCRIPT2
)

# Write startup script to temp file
STARTUP_FILE="c:/libraries/PrismataAI/gcp/.startup_tmp.ps1"
echo "$STARTUP_SCRIPT" > "$STARTUP_FILE"

SPOT_OPTS=""
if [ "$USE_SPOT" = "true" ]; then
    SPOT_OPTS="--provisioning-model=SPOT --instance-termination-action=DELETE"
    echo "(Using SPOT/Preemptible pricing)"
fi

# Launch instances
for i in $(seq 1 $NUM_INSTANCES); do
    INSTANCE_NAME="prismata-selfplay-$(date +%H%M%S)-$i"
    echo "Launching instance $i/$NUM_INSTANCES: $INSTANCE_NAME..."

    gcloud compute instances create "$INSTANCE_NAME" \
        --project="$PROJECT" \
        --zone="$ZONE" \
        --machine-type="$INSTANCE_TYPE" \
        --image-family="$IMAGE_FAMILY" \
        --image-project="$IMAGE_PROJECT" \
        --boot-disk-size=50GB \
        --boot-disk-type=pd-standard \
        --metadata="aws-key-id=$AWS_ACCESS_KEY_ID,aws-secret-key=$AWS_SECRET_ACCESS_KEY" \
        --metadata-from-file="windows-startup-script-ps1=$STARTUP_FILE" \
        --scopes=compute-rw \
        $SPOT_OPTS \
        --no-restart-on-failure \
        2>&1

    echo ""
done

rm -f "$STARTUP_FILE"

echo "=== $NUM_INSTANCES Instance(s) Launched ==="
echo "  Type:        $INSTANCE_TYPE"
echo "  Games:       $NUM_GAMES ($PROCESSES processes x $GAMES_PER_PROCESS per instance)"
echo "  Zone:        $ZONE"
echo ""
echo "Each instance will:"
echo "  1. Boot Windows Server (~3 min)"
echo "  2. Install VC++ runtime + AWS CLI (~2 min)"
echo "  3. Download exe + config from S3 (~1 min)"
echo "  4. Run self-play ($NUM_GAMES games)"
echo "  5. Upload results to s3://$BUCKET/results/"
echo "  6. Self-delete (no ongoing charges)"
echo ""
echo "Monitor instances:"
echo "  gcloud compute instances list --project=$PROJECT"
echo ""
echo "View serial console (startup logs):"
echo "  gcloud compute instances get-serial-port-output INSTANCE_NAME --zone=$ZONE --project=$PROJECT"
echo ""
echo "Download results (same as EC2):"
echo "  aws s3 sync s3://$BUCKET/results/ bin/training/data/selfplay/ --region eu-north-1"
