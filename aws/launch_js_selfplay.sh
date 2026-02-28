#!/bin/bash
# Launch EC2 Linux spot instance for JS self-play data generation
# Usage: bash aws/launch_js_selfplay.sh [NUM_GAMES] [NUM_INSTANCES] [INSTANCE_TYPE]
#
# Examples:
#   bash aws/launch_js_selfplay.sh 1000              # 1K games on 1x c5.2xlarge spot
#   bash aws/launch_js_selfplay.sh 100000 5           # 100K games on 5x c5.2xlarge spot
#   bash aws/launch_js_selfplay.sh 100000 5 c5.xlarge # 100K on 5x c5.xlarge
#
# Prerequisites:
#   bash aws/deploy_js_selfplay.sh   # Upload JS engine + deps to S3

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

NUM_GAMES="${1:-1000}"
NUM_INSTANCES="${2:-1}"
INSTANCE_TYPE="${3:-c5.2xlarge}"
THINK_TIME="${THINK_TIME:-1000}"       # ms, default 1s
REGION="eu-north-1"
AMI="ami-0d5323a080e2e5b40"           # Amazon Linux 2023 x86_64
KEY_NAME="prismata-selfplay"
SG_ID="sg-02117c219481e8e6a"
PROFILE="PrismataSelfPlayEC2"
BUCKET="prismata-selfplay-data"

# Determine worker count from instance type
case "$INSTANCE_TYPE" in
  c5.xlarge)   WORKERS=3 ;;   # 4 vCPU — 3 workers (each = main + 2 MCDSAI child processes)
  c5.2xlarge)  WORKERS=6 ;;   # 8 vCPU — 6 workers
  c5.4xlarge)  WORKERS=12 ;;  # 16 vCPU — 12 workers
  c5.9xlarge)  WORKERS=24 ;;  # 36 vCPU
  *)           WORKERS=3 ;;
esac

GAMES_PER_INSTANCE=$(( (NUM_GAMES + NUM_INSTANCES - 1) / NUM_INSTANCES ))
GAMES_PER_WORKER=$(( (GAMES_PER_INSTANCE + WORKERS - 1) / WORKERS ))

echo "=== JS Self-Play EC2 Spot Launch ==="
echo "  Total games:      $NUM_GAMES"
echo "  Instances:         $NUM_INSTANCES x $INSTANCE_TYPE (SPOT)"
echo "  Workers/instance:  $WORKERS"
echo "  Games/worker:      $GAMES_PER_WORKER"
echo "  Think time:        ${THINK_TIME}ms"
echo "  Region:            $REGION"
echo ""

# Verify deploy exists
DEPLOY_CHECK=$(aws s3 ls "s3://$BUCKET/deploy/js_engine/selfplay_main.js" --region "$REGION" 2>&1)
if [[ "$DEPLOY_CHECK" == *"NoSuchKey"* ]] || [[ -z "$DEPLOY_CHECK" ]]; then
    echo "ERROR: JS engine not deployed to S3. Run: bash aws/deploy_js_selfplay.sh"
    exit 1
fi
echo "Deploy verified on S3."
echo ""

# Build userdata script
USERDATA=$(cat <<ENDSCRIPT
#!/bin/bash
set -eo pipefail

# Auto-terminate on any exit (success, error, or spot interruption)
trap 'echo "=== Uploading final results ===" ; upload_results ; echo "=== Shutting down ===" ; shutdown -h now' EXIT

BUCKET="$BUCKET"
REGION="$REGION"
WORKERS=$WORKERS
GAMES_PER_WORKER=$GAMES_PER_WORKER
THINK_TIME=$THINK_TIME
RUN_ID="js_selfplay_\$(date +%Y-%m-%d_%H-%M-%S)"

exec > /tmp/boot.log 2>&1
echo "=== JS Self-Play Worker Starting ==="
echo "Run ID: \$RUN_ID"
echo "Workers: \$WORKERS, Games/worker: \$GAMES_PER_WORKER, Think: \${THINK_TIME}ms"

# Install Node.js (AL2023 has dnf)
echo "Installing Node.js..."
dnf install -y nodejs tar gzip 2>/dev/null || yum install -y nodejs tar gzip 2>/dev/null
node --version
echo "Node.js installed."

# Download JS engine from S3
echo "Downloading JS engine from S3..."
mkdir -p /opt/prismata/js_engine /opt/prismata/tmp_browser_client /opt/prismata/tmp_swf_extract /opt/prismata/bin/asset/config /opt/prismata/output

aws s3 sync "s3://\$BUCKET/deploy/js_engine/" /opt/prismata/js_engine/ --region "\$REGION" --quiet
aws s3 cp "s3://\$BUCKET/deploy/tmp_browser_client/MCDSAI3441.js" /opt/prismata/tmp_browser_client/MCDSAI3441.js --region "\$REGION" --quiet
aws s3 sync "s3://\$BUCKET/deploy/tmp_swf_extract/" /opt/prismata/tmp_swf_extract/ --region "\$REGION" --quiet
aws s3 cp "s3://\$BUCKET/deploy/asset/config/cardLibrary.jso" /opt/prismata/bin/asset/config/cardLibrary.jso --region "\$REGION" --quiet
echo "Download complete."

ls -la /opt/prismata/js_engine/selfplay_main.js
ls -la /opt/prismata/tmp_browser_client/MCDSAI3441.js

# Upload function
upload_results() {
    echo "Uploading results..."
    aws s3 sync /opt/prismata/output/ "s3://\$BUCKET/js_results/\$RUN_ID/" --region "\$REGION" --quiet 2>/dev/null || true
    aws s3 cp /tmp/boot.log "s3://\$BUCKET/js_results/\$RUN_ID/boot.log" --region "\$REGION" --quiet 2>/dev/null || true
    for f in /opt/prismata/output/worker_*.log; do
        [ -f "\$f" ] && aws s3 cp "\$f" "s3://\$BUCKET/js_results/\$RUN_ID/\$(basename \$f)" --region "\$REGION" --quiet 2>/dev/null || true
    done
    echo "Upload done."
}

# Launch workers in parallel
echo "Launching \$WORKERS workers..."
PIDS=()
for i in \$(seq 0 \$((\$WORKERS - 1))); do
    OUT_FILE="/opt/prismata/output/selfplay_worker_\${i}.jsonl"
    LOG_FILE="/opt/prismata/output/worker_\${i}.log"
    cd /opt/prismata/js_engine
    node selfplay_main.js \\
        --games \$GAMES_PER_WORKER \\
        --think-time \$THINK_TIME \\
        --jsonl "\$OUT_FILE" \\
        > "\$LOG_FILE" 2>&1 &
    PIDS+=(\$!)
    echo "  Worker \$i started (PID \$!), \$GAMES_PER_WORKER games -> \$OUT_FILE"
    sleep 1  # stagger spawns
done

# Periodic upload every 5 minutes while workers run
echo "Workers running. Periodic uploads every 5 min..."
while true; do
    sleep 300
    # Check if any workers still alive
    ALIVE=0
    for pid in "\${PIDS[@]}"; do
        kill -0 \$pid 2>/dev/null && ALIVE=\$((\$ALIVE + 1))
    done
    if [ \$ALIVE -eq 0 ]; then
        echo "All workers finished."
        break
    fi
    echo "[\$(date)] \$ALIVE/\$WORKERS workers running. Uploading interim results..."
    upload_results
done

# Wait for all workers to finish
for pid in "\${PIDS[@]}"; do
    wait \$pid 2>/dev/null || true
done

# Count total examples
TOTAL=0
for f in /opt/prismata/output/selfplay_worker_*.jsonl; do
    [ -f "\$f" ] && COUNT=\$(wc -l < "\$f") && TOTAL=\$((\$TOTAL + \$COUNT))
done
echo "=== COMPLETE: \$TOTAL total training examples ==="

# EXIT trap handles upload + shutdown
ENDSCRIPT
)

echo "Launching $NUM_INSTANCES spot instance(s)..."
echo ""

for i in $(seq 1 "$NUM_INSTANCES"); do
    INSTANCE_ID=$(aws ec2 run-instances \
      --image-id "$AMI" \
      --instance-type "$INSTANCE_TYPE" \
      --key-name "$KEY_NAME" \
      --security-group-ids "$SG_ID" \
      --iam-instance-profile Name="$PROFILE" \
      --user-data "$USERDATA" \
      --instance-initiated-shutdown-behavior terminate \
      --instance-market-options MarketType=spot \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataJS-${NUM_GAMES}g-${i}}]" \
      --query 'Instances[0].InstanceId' \
      --output text \
      --region "$REGION" 2>&1)

    echo "  Instance $i: $INSTANCE_ID ($INSTANCE_TYPE spot)"
done

echo ""
echo "=== Launch Complete ==="
echo "  Total:     $NUM_GAMES games across $NUM_INSTANCES instances"
echo "  Cost est:  ~\$$(python -c "
rate = {'c5.xlarge': 0.07, 'c5.2xlarge': 0.14, 'c5.4xlarge': 0.28}.get('$INSTANCE_TYPE', 0.14)
games_per_min = 2.0 * $WORKERS  # ~2 games/min/worker from benchmark
hours = $NUM_GAMES / (games_per_min * 60)
total = hours * rate * $NUM_INSTANCES / $NUM_INSTANCES  # cost spread across instances
print(f'{total:.2f}')
") (spot)"
echo ""
echo "Monitor:"
echo "  aws ec2 describe-instances --region $REGION --filters 'Name=tag:Name,Values=PrismataJS-*' 'Name=instance-state-name,Values=running' --query 'Reservations[].Instances[].[InstanceId,LaunchTime]' --output table"
echo ""
echo "Results will be at:"
echo "  aws s3 ls s3://$BUCKET/js_results/ --region $REGION"
echo ""
echo "Download:"
echo "  aws s3 sync s3://$BUCKET/js_results/ js_engine/cloud_results/ --region $REGION"
