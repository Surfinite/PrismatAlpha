#!/bin/bash
# Launch GPU EC2 instance for DeepSets training on HUMAN REPLAY data only
# Usage: bash aws/launch_human_training.sh [OPTIONS]
#
# Trains on human_1500_no6s_v2.h5 (2.5M records from 97,822 expert replays,
# both players ≥1500 rated, 6s bullet excluded, balance-validated).
#
# Options (via env vars):
#   LR=3e-4              Learning rate (default: 3e-4)
#   EPOCHS=100           Max epochs (default: 100)
#   BATCH_SIZE=512       Batch size (default: 512)
#   PATIENCE=15          Early stopping patience (default: 15)
#   MAX_RECORDS=0        Max records to load, 0=all (default: 0)
#   LABEL=human_1500     Run label for S3 output dir (default: human_1500)
#   INSTANCE_TYPE=g6.2xlarge   Instance type (default: g6.2xlarge)
#   USE_SPOT=true        Use spot pricing (default: true)
#   DRY_RUN=true         Print userdata script without launching (default: false)
#
# Data files (must exist locally):
#   training/data/human_1500_no6s_v2.h5   — Human expert replays (~2.5M records)
#   training/data/local_mbvmb.h5          — Validation set (~414K records)
#   training/property_table.json

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

# Hyperparameters
LR="${LR:-3e-4}"
EPOCHS="${EPOCHS:-100}"
BATCH_SIZE="${BATCH_SIZE:-512}"
PATIENCE="${PATIENCE:-15}"
MAX_RECORDS="${MAX_RECORDS:-0}"
SEED="${SEED:-42}"

# Infrastructure
INSTANCE_TYPE="${INSTANCE_TYPE:-g6.2xlarge}"
USE_SPOT="${USE_SPOT:-true}"
DRY_RUN="${DRY_RUN:-false}"
REGION="eu-north-1"
AMI="ami-0bd05d88ea8c3e277"  # Deep Learning OSS PyTorch 2.6, Amazon Linux 2023
KEY_NAME="prismata-selfplay"
SG_ID="sg-02117c219481e8e6a"
PROFILE="PrismataSelfPlayEC2"
BUCKET="prismata-selfplay-data"

# Auto-generate label if not provided
if [ -z "$LABEL" ]; then
  LABEL="human_1500"
fi

# Training data files — human only
TRAIN_FILE="training/data/human_1500_no6s_v2.h5"
VAL_FILE="training/data/local_mbvmb.h5"
PROP_TABLE="training/property_table.json"

# Verify all files exist
for f in "$TRAIN_FILE" "$VAL_FILE" "$PROP_TABLE"; do
  if [ ! -f "$f" ]; then
    echo "ERROR: Required file not found: $f"
    exit 1
  fi
done

echo "=== Prismata DeepSets Training — HUMAN REPLAYS ONLY ==="
echo "  Instance:   $INSTANCE_TYPE"
echo "  GPU:        $(if [[ $INSTANCE_TYPE == g6* ]]; then echo 'NVIDIA L4 (24GB)'; else echo 'NVIDIA T4 (16GB)'; fi)"
echo "  Label:      $LABEL"
echo "  LR:         $LR"
echo "  Epochs:     $EPOCHS"
echo "  Batch size: $BATCH_SIZE"
echo "  Patience:   $PATIENCE"
echo "  Max records: $MAX_RECORDS (0=all)"
echo "  Seed:       $SEED"
echo "  Region:     $REGION"
echo "  Spot:       $USE_SPOT"
echo "  Mode:       streaming (chunk-buffered, minimal RAM)"
echo ""
echo "  Training data:"
echo "    $TRAIN_FILE ($(du -h "$TRAIN_FILE" | cut -f1))"
echo "  Val data:   $VAL_FILE ($(du -h "$VAL_FILE" | cut -f1))"
echo ""

# ============================================================
# Step 1: Upload data and code to S3
# ============================================================
if [ "${SKIP_UPLOAD:-false}" = "true" ]; then
  echo "=== Skipping upload (SKIP_UPLOAD=true, data already in S3) ==="
else
  echo "=== Uploading training code and data to S3 ==="

  echo "  Uploading training code..."
  aws s3 cp training/train.py s3://$BUCKET/deploy/deepsets/train.py --region $REGION
  aws s3 cp training/model_deepsets.py s3://$BUCKET/deploy/deepsets/model_deepsets.py --region $REGION
  aws s3 cp training/export_weights_v2.py s3://$BUCKET/deploy/deepsets/export_weights_v2.py --region $REGION
  aws s3 cp "$PROP_TABLE" s3://$BUCKET/deploy/deepsets/property_table.json --region $REGION

  echo "  Uploading HDF5 data files..."
  TRAIN_BASENAME=$(basename "$TRAIN_FILE")
  echo "    $TRAIN_BASENAME..."
  aws s3 cp "$TRAIN_FILE" "s3://$BUCKET/deploy/deepsets/$TRAIN_BASENAME" --region $REGION

  VAL_BASENAME=$(basename "$VAL_FILE")
  echo "    $VAL_BASENAME..."
  aws s3 cp "$VAL_FILE" "s3://$BUCKET/deploy/deepsets/$VAL_BASENAME" --region $REGION

  echo "  Upload complete."
fi
echo ""

# ============================================================
# Step 2: Build userdata script
# ============================================================
TRAIN_BASENAME=$(basename "$TRAIN_FILE")
VAL_BASENAME=$(basename "$VAL_FILE")

USERDATA=$(cat <<ENDSCRIPT
#!/bin/bash
set -eo pipefail

# Ensure instance self-terminates on ANY exit
cleanup_and_shutdown() {
    echo "[trap] Script exiting (code \$?) — uploading logs and shutting down..."
    if [ -f training_output.log ] && [ -n "\${BUCKET:-}" ] && [ -n "\${S3_PREFIX:-}" ]; then
        aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$REGION 2>/dev/null || true
    fi
    kill \$SYNC_PID 2>/dev/null || true
    sudo shutdown -h now
}
trap cleanup_and_shutdown EXIT

BUCKET="$BUCKET"
REGION="$REGION"
LABEL="$LABEL"
LR=$LR
EPOCHS=$EPOCHS
BATCH_SIZE=$BATCH_SIZE
PATIENCE=$PATIENCE
MAX_RECORDS=$MAX_RECORDS
SEED=$SEED

RUN_ID=\$(date +%Y-%m-%d_%H-%M-%S)
WORK="/home/ec2-user/training"
LOG="/home/ec2-user/training_boot.log"

exec > >(tee -a "\$LOG") 2>&1

echo "=== Prismata DeepSets Training — HUMAN REPLAYS ONLY ==="
echo "Run ID: \$RUN_ID"
echo "Label: \$LABEL"
IMDS_TOKEN=\$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300" 2>/dev/null || true)
echo "Instance: \$(curl -s -H "X-aws-ec2-metadata-token: \$IMDS_TOKEN" http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo unknown)"
date

# Setup environment
echo "Activating PyTorch venv..."
export PATH="/opt/pytorch/bin:\$PATH"

echo "GPU check:"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}'); print(f'PyTorch: {torch.__version__}')"

pip install tqdm h5py --quiet 2>/dev/null || true

export HDF5_USE_FILE_LOCKING=FALSE
export PYTHONUNBUFFERED=1

# Download code and data from S3
echo "Downloading training code and data from S3..."
mkdir -p \$WORK/training \$WORK/data \$WORK/models

aws s3 cp s3://\$BUCKET/deploy/deepsets/train.py \$WORK/training/train.py --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/deepsets/model_deepsets.py \$WORK/training/model_deepsets.py --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/deepsets/export_weights_v2.py \$WORK/training/export_weights_v2.py --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/deepsets/property_table.json \$WORK/training/property_table.json --region \$REGION

echo "Downloading HDF5 data..."
aws s3 cp s3://\$BUCKET/deploy/deepsets/$TRAIN_BASENAME \$WORK/data/$TRAIN_BASENAME --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/deepsets/$VAL_BASENAME \$WORK/data/$VAL_BASENAME --region \$REGION

echo "Download complete."

# Count records
TOTAL_N=\$(python -c "
import h5py
with h5py.File('\$WORK/data/$TRAIN_BASENAME', 'r') as h:
    print(h['label_A'].shape[0])
")
echo "Dataset: \$TOTAL_N training records (human replays, 1500+ rated, no 6s bullet)"

# Upload run config
S3_PREFIX="training-runs/\$LABEL/\$RUN_ID"
cat > /tmp/run_config.json <<CONFIGEOF
{
  "run_id": "\$RUN_ID",
  "label": "\$LABEL",
  "model": "deepsets",
  "mode": "streaming",
  "data": "human_1500_no6s (97,822 games, both players 1500+, no 6s bullet)",
  "lr": \$LR,
  "epochs": \$EPOCHS,
  "batch_size": \$BATCH_SIZE,
  "patience": \$PATIENCE,
  "max_records": \$MAX_RECORDS,
  "seed": \$SEED,
  "total_records": \$TOTAL_N,
  "instance_type": "\$(curl -s -H \"X-aws-ec2-metadata-token: \$IMDS_TOKEN\" http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo unknown)"
}
CONFIGEOF
aws s3 cp /tmp/run_config.json s3://\$BUCKET/\$S3_PREFIX/run_config.json --region \$REGION

# Build training command
echo ""
echo "=== Starting DeepSets training (streaming mode) ==="
cd \$WORK

TRAIN_CMD="python training/train.py \\
  --model deepsets \\
  --train-file data/$TRAIN_BASENAME \\
  --val-file data/$VAL_BASENAME \\
  --property-table training/property_table.json \\
  --output-dir models \\
  --streaming \\
  --epochs \$EPOCHS \\
  --batch-size \$BATCH_SIZE \\
  --lr \$LR \\
  --patience \$PATIENCE \\
  --num-workers 0 \\
  --seed \$SEED \\
  --device cuda"

if [ \$MAX_RECORDS -gt 0 ]; then
  TRAIN_CMD="\$TRAIN_CMD --max-records \$MAX_RECORDS"
fi

echo "Command: \$TRAIN_CMD"
echo ""

# Background checkpoint sync every 5 min
(
  while true; do
    sleep 300
    if [ -d models ]; then
      aws s3 sync models/ s3://\$BUCKET/\$S3_PREFIX/models/ --region \$REGION --quiet 2>/dev/null
    fi
    aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$REGION --quiet 2>/dev/null
    echo "[sync] Checkpoints uploaded to S3 at \$(date)"
  done
) &
SYNC_PID=\$!
echo "Background S3 sync started (PID \$SYNC_PID, every 5 min)"

eval \$TRAIN_CMD 2>&1 | tee training_output.log
TRAIN_EXIT=\$?

kill \$SYNC_PID 2>/dev/null || true

echo ""
echo "Training exited with code: \$TRAIN_EXIT"

# Upload final results
echo "Uploading final results to S3..."
aws s3 sync models/ s3://\$BUCKET/\$S3_PREFIX/models/ --region \$REGION

# Export weights to DSN2 binary format
echo "Exporting DeepSets weights to DSN2 format..."
if [ -f models/best_model.pt ]; then
  python training/export_weights_v2.py models/best_model.pt models/neural_weights.bin \\
    --property-table training/property_table.json
  aws s3 cp models/neural_weights.bin s3://\$BUCKET/\$S3_PREFIX/neural_weights.bin --region \$REGION
  echo "Weights exported and uploaded."
else
  echo "WARNING: No best_model.pt found!"
fi

aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$REGION
aws s3 cp \$LOG s3://\$BUCKET/\$S3_PREFIX/training_boot.log --region \$REGION

echo ""
echo "=== DeepSets Training complete (HUMAN REPLAYS) ==="
echo "Results at: s3://\$BUCKET/\$S3_PREFIX/"
echo "Download weights: aws s3 cp s3://\$BUCKET/\$S3_PREFIX/neural_weights.bin bin/asset/config/neural_weights.bin --region \$REGION"
echo "Download model: aws s3 cp s3://\$BUCKET/\$S3_PREFIX/models/best_model.pt training/models/ --region \$REGION"
date

echo "Training script complete. Exiting..."
ENDSCRIPT
)

if [ "$DRY_RUN" = "true" ]; then
  echo "=== DRY RUN - Userdata script: ==="
  echo "$USERDATA"
  exit 0
fi

# Write userdata to temp file
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_human_tmp.sh"
echo "$USERDATA" > "$USERDATA_FILE"

# Base64 encode userdata
USERDATA_B64=$(base64 -w0 "$USERDATA_FILE")

echo "Launching instance..."

if [ "$USE_SPOT" = "true" ]; then
  echo "(Using SPOT pricing — request will queue until capacity available)"

  SPEC_FILE="c:/libraries/PrismataAI/aws/.spot_spec_human_tmp.json"
  cat > "$SPEC_FILE" <<SPECEOF
{
  "ImageId": "$AMI",
  "InstanceType": "$INSTANCE_TYPE",
  "KeyName": "$KEY_NAME",
  "SecurityGroupIds": ["$SG_ID"],
  "IamInstanceProfile": {"Name": "$PROFILE"},
  "UserData": "$USERDATA_B64",
  "BlockDeviceMappings": [{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 50, "VolumeType": "gp3"}}]
}
SPECEOF

  SPOT_REQ_ID=$(MSYS_NO_PATHCONV=1 aws ec2 request-spot-instances \
    --instance-count 1 \
    --type "one-time" \
    --instance-interruption-behavior terminate \
    --launch-specification "file://$SPEC_FILE" \
    --query 'SpotInstanceRequests[0].SpotInstanceRequestId' \
    --output text \
    --region "$REGION" 2>&1)
  rm -f "$SPEC_FILE"

  if [[ "$SPOT_REQ_ID" != sir-* ]]; then
    echo "ERROR: Spot request failed: $SPOT_REQ_ID"
    rm -f "$USERDATA_FILE"
    exit 1
  fi

  echo "  Spot request: $SPOT_REQ_ID"
  echo "  Waiting for fulfillment (up to 5 min)..."

  for i in $(seq 1 30); do
    sleep 10
    STATUS=$(aws ec2 describe-spot-instance-requests \
      --spot-instance-request-ids "$SPOT_REQ_ID" \
      --query 'SpotInstanceRequests[0].[State,Status.Code,InstanceId]' \
      --output text --region "$REGION" 2>&1)
    STATE=$(echo "$STATUS" | awk '{print $1}')
    CODE=$(echo "$STATUS" | awk '{print $2}')
    INSTANCE_ID=$(echo "$STATUS" | awk '{print $3}')

    if [ "$STATE" = "active" ] && [[ "$INSTANCE_ID" == i-* ]]; then
      echo "  Fulfilled! Instance: $INSTANCE_ID"
      aws ec2 create-tags --resources "$INSTANCE_ID" \
        --tags "Key=Name,Value=PrismataDeepSets-${LABEL}" \
        --region "$REGION" 2>/dev/null
      break
    elif [ "$STATE" = "closed" ] || [ "$STATE" = "cancelled" ] || [ "$STATE" = "failed" ]; then
      echo "  Spot request $STATE: $CODE"
      INSTANCE_ID=""
      break
    fi
    echo "  [$i/30] Status: $STATE ($CODE)..."
  done

  if [[ "$INSTANCE_ID" != i-* ]]; then
    echo "ERROR: Spot request not fulfilled within 5 min."
    echo "  Cancel with: aws ec2 cancel-spot-instance-requests --spot-instance-request-ids $SPOT_REQ_ID --region $REGION"
    rm -f "$USERDATA_FILE"
    exit 1
  fi
else
  echo "(Using ON-DEMAND pricing)"
  INSTANCE_ID=$(MSYS_NO_PATHCONV=1 aws ec2 run-instances \
    --image-id "$AMI" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile Name="$PROFILE" \
    --user-data "file://$USERDATA_FILE" \
    --instance-initiated-shutdown-behavior terminate \
    --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=50,VolumeType=gp3}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataDeepSets-${LABEL}}]" \
    --query 'Instances[0].InstanceId' \
    --output text \
    --region "$REGION" 2>&1)

  if [[ "$INSTANCE_ID" != i-* ]]; then
    echo "ERROR: Launch failed: $INSTANCE_ID"
    rm -f "$USERDATA_FILE"
    exit 1
  fi
fi

rm -f "$USERDATA_FILE"

echo ""
echo "=== DeepSets Training Instance Launched (HUMAN REPLAYS) ==="
echo "  Instance ID: $INSTANCE_ID"
echo "  Type:        $INSTANCE_TYPE"
echo "  Label:       $LABEL"
echo "  Data:        human_1500_no6s_v2.h5 (~2.5M records, 97K games)"
echo ""
echo "The instance will:"
echo "  1. Boot Amazon Linux 2023 + PyTorch 2.6 (~2 min)"
echo "  2. Download human replay HDF5 from S3 (~1 min)"
echo "  3. Train DeepSets on NVIDIA L4 GPU (streaming, lr=$LR)"
echo "  4. Export weights to DSN2 binary format"
echo "  5. Upload model + metrics to s3://$BUCKET/training-runs/$LABEL/"
echo "  6. Auto-terminate (no ongoing charges)"
echo ""
echo "Monitor:"
echo "  aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].State.Name' --region $REGION"
echo ""
echo "SSH (if needed):"
echo "  aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --region $REGION"
echo "  ssh -i ~/.ssh/prismata-selfplay.pem ec2-user@<IP>"
echo ""
echo "Download results when done:"
echo "  aws s3 sync s3://$BUCKET/training-runs/$LABEL/ training/cloud-runs/$LABEL/ --region $REGION"
