#!/bin/bash
# Auto-relaunch EC2 selfplay when current batch finishes.
# Usage: bash aws/relaunch_when_done.sh
# Run from project root. Polls every 5 minutes.

set -e
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

REGION="${AWS_REGION:-eu-north-1}"
BUCKET="${CLOUD_BUCKET:?Set CLOUD_BUCKET in cloud-config.env}"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Count how many are running right now (to detect when batch ends)
INITIAL=$(aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running,pending" \
              "Name=tag:Name,Values=PrismataSelfPlay-*" \
    --query 'Reservations[].Instances[].InstanceId' \
    --output text --region "$REGION" 2>/dev/null | wc -w)

BATCH=1
echo "[$(date)] Currently running: $INITIAL selfplay instances"
echo "[$(date)] Continuous mode: will keep relaunching max capacity batches forever."

while true; do
    # Count running + pending + shutting-down (still alive in some form)
    ALIVE=$(aws ec2 describe-instances \
        --filters "Name=instance-state-name,Values=running,pending,shutting-down" \
                  "Name=tag:Name,Values=PrismataSelfPlay-*" \
        --query 'Reservations[].Instances[].InstanceId' \
        --output text --region "$REGION" 2>/dev/null | wc -w)

    echo "[$(date)] Alive selfplay instances: $ALIVE (started with $INITIAL)"

    if [ "$ALIVE" -eq 0 ] && [ "$INITIAL" -gt 0 ]; then
        echo "[$(date)] All instances finished/terminated! Launching batch $BATCH..."

        # Sync results to S3 summary
        echo "[$(date)] Syncing S3 results locally before next batch..."
        aws s3 sync "s3://$BUCKET/results/" "$PROJECT_DIR/bin/training/data/selfplay/" --region "$REGION" 2>/dev/null

        # Check current quotas to use maximum capacity
        VCPUS_PER_INSTANCE=8  # c5.2xlarge
        OD_QUOTA=$(aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --region "$REGION" --query 'Quota.Value' --output text 2>/dev/null | cut -d. -f1)
        SPOT_QUOTA=$(aws service-quotas get-service-quota --service-code ec2 --quota-code L-34B43A08 --region "$REGION" --query 'Quota.Value' --output text 2>/dev/null | cut -d. -f1)
        OD_COUNT=$((OD_QUOTA / VCPUS_PER_INSTANCE))
        SPOT_COUNT=$((SPOT_QUOTA / VCPUS_PER_INSTANCE))
        echo "[$(date)] Quotas: on-demand=${OD_QUOTA} vCPUs (${OD_COUNT} instances), spot=${SPOT_QUOTA} vCPUs (${SPOT_COUNT} instances)"

        # Launch on-demand
        OD_LAUNCHED=0
        echo "[$(date)] Launching ${OD_COUNT}x c5.2xlarge on-demand..."
        for i in $(seq 1 $OD_COUNT); do
            ID=$(cd "$PROJECT_DIR" && bash aws/launch_selfplay.sh c5.2xlarge 5000 1 2 2>&1 | grep "Instance ID" | awk '{print $NF}')
            if [ -n "$ID" ]; then
                echo "[$(date)]   On-demand $i: $ID"
                OD_LAUNCHED=$((OD_LAUNCHED + 1))
            else
                echo "[$(date)]   On-demand $i: FAILED (quota limit?)"
                break
            fi
        done

        # Launch spot
        SPOT_LAUNCHED=0
        echo "[$(date)] Launching ${SPOT_COUNT}x c5.2xlarge spot..."
        for i in $(seq 1 $SPOT_COUNT); do
            ID=$(cd "$PROJECT_DIR" && USE_SPOT=true bash aws/launch_selfplay.sh c5.2xlarge 5000 1 2 2>&1 | grep "Instance ID" | awk '{print $NF}')
            if [ -n "$ID" ]; then
                echo "[$(date)]   Spot $i: $ID"
                SPOT_LAUNCHED=$((SPOT_LAUNCHED + 1))
            else
                echo "[$(date)]   Spot $i: FAILED (quota limit?)"
                break
            fi
        done

        INITIAL=$((OD_LAUNCHED + SPOT_LAUNCHED))
        echo "[$(date)] Batch $BATCH launched: $OD_LAUNCHED on-demand + $SPOT_LAUNCHED spot = $INITIAL instances"
        BATCH=$((BATCH + 1))
    fi

    sleep 300  # Check every 5 minutes
done
