#!/bin/bash
# Launch GPU EC2 instance for neural network training (default: g6.2xlarge)
# Usage: bash aws/launch_training.sh [OPTIONS]
#
# Options (via env vars):
#   HIDDEN_DIM=256       Hidden layer size (default: 256)
#   LR=1e-5              Learning rate (default: 1e-5)
#   EPOCHS=40            Max epochs (default: 40)
#   BATCH_SIZE=512       Batch size (default: 512)
#   PATIENCE=15          Early stopping patience (default: 15)
#   NUM_LAYERS=2         Residual blocks in trunk (default: 2)
#   WARMUP_EPOCHS=2      LR warmup epochs (default: 2)
#   DROPOUT=0.1          Dropout rate (default: 0.1)
#   WEIGHT_DECAY=1e-4    AdamW weight decay (default: 1e-4)
#   LABEL_SMOOTH=0.95    Label smoothing (default: 0.95)
#   LOSS_FN=mse          Loss function: mse or bce (default: mse)
#   EVAL_STEPS=5000      Eval every N steps (default: 5000)
#   MAX_RECORDS=0        Max records to load, 0=all (default: 0)
#   LABEL=256h_400k      Run label for S3 output dir (default: auto)
#   INSTANCE_TYPE=g6.2xlarge   Instance type (default: g6.2xlarge, L4 GPU + 32GB RAM)
#   USE_SPOT=true        Use spot pricing (default: true)
#   DRY_RUN=true         Print userdata script without launching (default: false)
#
# Examples:
#   bash aws/launch_training.sh                              # 256h default
#   HIDDEN_DIM=512 bash aws/launch_training.sh               # 512h model
#   HIDDEN_DIM=256 LR=3e-5 bash aws/launch_training.sh      # LR sweep
#   DRY_RUN=true bash aws/launch_training.sh                 # Preview userdata
#
# Parallel sweep example:
#   for lr in 1e-5 3e-5 1e-4; do
#     HIDDEN_DIM=256 LR=$lr LABEL="sweep_256h_lr${lr}" bash aws/launch_training.sh
#     sleep 2
#   done

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

# Hyperparameters
HIDDEN_DIM="${HIDDEN_DIM:-256}"
LR="${LR:-1e-5}"
EPOCHS="${EPOCHS:-40}"
BATCH_SIZE="${BATCH_SIZE:-512}"
PATIENCE="${PATIENCE:-15}"
NUM_LAYERS="${NUM_LAYERS:-2}"
WARMUP_EPOCHS="${WARMUP_EPOCHS:-2}"
DROPOUT="${DROPOUT:-0.1}"
WEIGHT_DECAY="${WEIGHT_DECAY:-1e-4}"
LABEL_SMOOTH="${LABEL_SMOOTH:-0.95}"
LOSS_FN="${LOSS_FN:-mse}"
EVAL_STEPS="${EVAL_STEPS:-5000}"
MAX_RECORDS="${MAX_RECORDS:-0}"
SEED="${SEED:-42}"

# Infrastructure
INSTANCE_TYPE="${INSTANCE_TYPE:-g6.2xlarge}"
USE_SPOT="${USE_SPOT:-true}"
DRY_RUN="${DRY_RUN:-false}"
REGION="${AWS_REGION:-eu-north-1}"
AMI="${AWS_AMI_DL_PYTORCH:?Set AWS_AMI_DL_PYTORCH in cloud-config.env}"
KEY_NAME="${AWS_KEY_NAME:?Set AWS_KEY_NAME in cloud-config.env}"
SG_ID="${AWS_SG_ID:?Set AWS_SG_ID in cloud-config.env}"
PROFILE="${AWS_IAM_PROFILE:?Set AWS_IAM_PROFILE in cloud-config.env}"
BUCKET="${CLOUD_BUCKET:?Set CLOUD_BUCKET in cloud-config.env}"

# Auto-generate label if not provided
if [ -z "$LABEL" ]; then
  LABEL="h${HIDDEN_DIM}_lr${LR}"
fi

echo "=== Prismata Training GPU Launch ==="
echo "  Instance:   $INSTANCE_TYPE"
echo "  GPU:        $(if [[ $INSTANCE_TYPE == g6* ]]; then echo 'NVIDIA L4 (24GB)'; else echo 'NVIDIA T4 (16GB)'; fi)"
echo "  Label:      $LABEL"
echo "  Hidden dim: $HIDDEN_DIM"
echo "  LR:         $LR"
echo "  Epochs:     $EPOCHS"
echo "  Batch size: $BATCH_SIZE"
echo "  Patience:   $PATIENCE"
echo "  Layers:     $NUM_LAYERS"
echo "  Warmup:     $WARMUP_EPOCHS epochs"
echo "  Dropout:    $DROPOUT"
echo "  Wt decay:   $WEIGHT_DECAY"
echo "  Label smooth: $LABEL_SMOOTH"
echo "  Loss fn:    $LOSS_FN"
echo "  Eval steps: $EVAL_STEPS"
echo "  Max records: $MAX_RECORDS (0=all)"
echo "  Seed:       $SEED"
echo "  Region:     $REGION"
echo "  Spot:       $USE_SPOT"
echo ""

# Build the userdata script (bash for Linux AMI)
USERDATA=$(cat <<ENDSCRIPT
#!/bin/bash
set -eo pipefail

# Ensure instance self-terminates on ANY exit (crash, signal, pipefail)
cleanup_and_shutdown() {
    echo "[trap] Script exiting (code \$?) — uploading logs and shutting down..."
    # Best-effort final log upload
    if [ -f training_output.log ] && [ -n "\${BUCKET:-}" ] && [ -n "\${S3_PREFIX:-}" ]; then
        aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$REGION 2>/dev/null || true
    fi
    # Kill background sync if running
    kill \$SYNC_PID 2>/dev/null || true
    sudo shutdown -h now
}
trap cleanup_and_shutdown EXIT

# ============================================================
# Prismata Training Worker (GPU instance)
# ============================================================
BUCKET="$BUCKET"
REGION="$REGION"
LABEL="$LABEL"
HIDDEN_DIM=$HIDDEN_DIM
LR=$LR
EPOCHS=$EPOCHS
BATCH_SIZE=$BATCH_SIZE
PATIENCE=$PATIENCE
NUM_LAYERS=$NUM_LAYERS
WARMUP_EPOCHS=$WARMUP_EPOCHS
DROPOUT=$DROPOUT
WEIGHT_DECAY=$WEIGHT_DECAY
LABEL_SMOOTH=$LABEL_SMOOTH
LOSS_FN="$LOSS_FN"
EVAL_STEPS=$EVAL_STEPS
MAX_RECORDS=$MAX_RECORDS
SEED=$SEED

RUN_ID=\$(date +%Y-%m-%d_%H-%M-%S)
WORK="/home/ec2-user/training"
LOG="/home/ec2-user/training_boot.log"

exec > >(tee -a "\$LOG") 2>&1

echo "=== Prismata Training Worker Starting ==="
echo "Run ID: \$RUN_ID"
echo "Label: \$LABEL"
IMDS_TOKEN=\$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300" 2>/dev/null || true)
echo "Instance: \$(curl -s -H "X-aws-ec2-metadata-token: \$IMDS_TOKEN" http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo unknown)"
date

# ============================================================
# Setup environment (DL AMI uses venv at /opt/pytorch/)
# ============================================================
echo "Activating PyTorch venv..."
export PATH="/opt/pytorch/bin:\$PATH"

# Verify GPU
echo "GPU check:"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}'); print(f'PyTorch: {torch.__version__}')"

# Install any missing deps
pip install tqdm --quiet 2>/dev/null || true

# ============================================================
# Download training code and data
# ============================================================
echo "Downloading training code from S3..."
mkdir -p \$WORK/training \$WORK/data \$WORK/models

aws s3 cp s3://\$BUCKET/deploy/training/train.py \$WORK/training/train.py --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/training/load_selfplay.py \$WORK/training/load_selfplay.py --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/training/schema.json \$WORK/training/schema.json --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/training/export_weights.py \$WORK/training/export_weights.py --region \$REGION
aws s3 cp s3://\$BUCKET/deploy/training/unit_index.json \$WORK/data/unit_index.json --region \$REGION

echo "Downloading selfplay data from S3 (shards only, skipping dumps/logs)..."
aws s3 sync s3://\$BUCKET/results/ \$WORK/selfplay_data/ --region \$REGION --quiet \
  --exclude "*.dmp" --exclude "*.log" --exclude "*.txt" --exclude "*.jsonl" || {
  echo "WARNING: S3 sync exited with non-zero code (partial transfer warnings). Continuing..."
}
echo "Download complete."

# Count data
RECORD_COUNT=\$(python -c "
import os
base = '\$WORK/selfplay_data'
total = sum(
    (os.path.getsize(os.path.join(r, f)) - 68) // 7152
    for r, _, fs in os.walk(base)
    for f in fs
    if f.endswith('.bin') and os.path.getsize(os.path.join(r, f)) > 68
)
print(total)
")
echo "Dataset: \$RECORD_COUNT records (~\$((RECORD_COUNT / 37)) games)"

# Upload run config to S3 for tracking
cat > /tmp/run_config.json <<CONFIGEOF
{
  "run_id": "\$RUN_ID",
  "label": "\$LABEL",
  "hidden_dim": \$HIDDEN_DIM,
  "lr": \$LR,
  "epochs": \$EPOCHS,
  "batch_size": \$BATCH_SIZE,
  "patience": \$PATIENCE,
  "loss_fn": "\$LOSS_FN",
  "eval_steps": \$EVAL_STEPS,
  "max_records": \$MAX_RECORDS,
  "seed": \$SEED,
  "num_layers": \$NUM_LAYERS,
  "warmup_epochs": \$WARMUP_EPOCHS,
  "dropout": \$DROPOUT,
  "weight_decay": \$WEIGHT_DECAY,
  "label_smooth": \$LABEL_SMOOTH,
  "records": \$RECORD_COUNT,
  "instance_type": "\$(curl -s -H \"X-aws-ec2-metadata-token: \$IMDS_TOKEN\" http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo unknown)"
}
CONFIGEOF
aws s3 cp /tmp/run_config.json s3://\$BUCKET/training-runs/\$LABEL/\$RUN_ID/run_config.json --region \$REGION

# ============================================================
# Run training
# ============================================================
echo ""
echo "=== Starting training ==="
echo "  Device: cuda (T4)"
echo "  Hidden dim: \$HIDDEN_DIM"
echo "  Layers: \$NUM_LAYERS"
echo "  LR: \$LR"
echo "  Records: \$RECORD_COUNT"
echo ""

cd \$WORK

# Build training command
TRAIN_CMD="python training/train.py data models \\
  --selfplay-dir selfplay_data/ \\
  --value-only \\
  --hidden-dim \$HIDDEN_DIM \\
  --num-layers \$NUM_LAYERS \\
  --epochs \$EPOCHS \\
  --batch-size \$BATCH_SIZE \\
  --lr \$LR \\
  --warmup-epochs \$WARMUP_EPOCHS \\
  --dropout \$DROPOUT \\
  --weight-decay \$WEIGHT_DECAY \\
  --label-smooth \$LABEL_SMOOTH \\
  --tanh-in-training \\
  --loss-fn \$LOSS_FN \\
  --patience \$PATIENCE \\
  --num-workers 2 \\
  --eval-every-steps \$EVAL_STEPS \\
  --seed \$SEED \\
  --streaming \\
  --device cuda"

# Add --max-records if set
if [ \$MAX_RECORDS -gt 0 ]; then
  TRAIN_CMD="\$TRAIN_CMD --max-records \$MAX_RECORDS"
fi

echo "Command: \$TRAIN_CMD"
echo ""

# Background checkpoint sync — uploads to S3 every 5 min so spot termination doesn't lose progress
S3_PREFIX="training-runs/\$LABEL/\$RUN_ID"
(
  while true; do
    sleep 300
    if [ -d models ]; then
      aws s3 sync models/ s3://\$BUCKET/\$S3_PREFIX/models/ --region \$REGION --quiet 2>/dev/null
    fi
    if [ -d runs ]; then
      aws s3 sync runs/ s3://\$BUCKET/\$S3_PREFIX/runs/ --region \$REGION --quiet 2>/dev/null
    fi
    aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$REGION --quiet 2>/dev/null
    echo "[sync] Checkpoints uploaded to S3 at \$(date)"
  done
) &
SYNC_PID=\$!
echo "Background S3 sync started (PID \$SYNC_PID, every 5 min)"

eval \$TRAIN_CMD 2>&1 | tee training_output.log
TRAIN_EXIT=\$?

# Stop background sync
kill \$SYNC_PID 2>/dev/null || true

echo ""
echo "Training exited with code: \$TRAIN_EXIT"

# ============================================================
# Upload results (final)
# ============================================================
echo "Uploading final results to S3..."

# Upload model checkpoints
aws s3 sync models/ s3://\$BUCKET/\$S3_PREFIX/models/ --region \$REGION

# Upload run JSONs (metrics)
if [ -d runs ]; then
  aws s3 sync runs/ s3://\$BUCKET/\$S3_PREFIX/runs/ --region \$REGION
fi

# Upload training output log
aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$REGION

# Export weights to binary format
echo "Exporting weights..."
if [ -f models/best_model.pt ]; then
  python training/export_weights.py models/best_model.pt models/neural_weights.bin
  aws s3 cp models/neural_weights.bin s3://\$BUCKET/\$S3_PREFIX/neural_weights.bin --region \$REGION
  echo "Weights exported and uploaded."
else
  echo "WARNING: No best_model.pt found!"
fi

# Upload boot log
aws s3 cp \$LOG s3://\$BUCKET/\$S3_PREFIX/training_boot.log --region \$REGION

echo ""
echo "=== Training complete ==="
echo "Results at: s3://\$BUCKET/\$S3_PREFIX/"
echo "Download model: aws s3 cp s3://\$BUCKET/\$S3_PREFIX/neural_weights.bin bin/asset/config/neural_weights.bin --region \$REGION"
echo "Download checkpoint: aws s3 cp s3://\$BUCKET/\$S3_PREFIX/models/best_model.pt training/models/ --region \$REGION"
date

# Self-terminate (trap EXIT handler will run shutdown)
echo "Training script complete. Exiting..."
ENDSCRIPT
)

if [ "$DRY_RUN" = "true" ]; then
  echo "=== DRY RUN - Userdata script: ==="
  echo "$USERDATA"
  exit 0
fi

# Write userdata to temp file
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_training_tmp.sh"
echo "$USERDATA" > "$USERDATA_FILE"

# Base64 encode userdata for spot request API
USERDATA_B64=$(base64 -w0 "$USERDATA_FILE")

echo "Launching instance..."

if [ "$USE_SPOT" = "true" ]; then
  echo "(Using SPOT pricing — request will queue until capacity available)"

  # Write launch spec JSON (request-spot-instances queues instead of instant-fail)
  SPEC_FILE="c:/libraries/PrismataAI/aws/.spot_spec_tmp.json"
  cat > "$SPEC_FILE" <<SPECEOF
{
  "ImageId": "$AMI",
  "InstanceType": "$INSTANCE_TYPE",
  "KeyName": "$KEY_NAME",
  "SecurityGroupIds": ["$SG_ID"],
  "IamInstanceProfile": {"Name": "$PROFILE"},
  "UserData": "$USERDATA_B64",
  "BlockDeviceMappings": [{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 350, "VolumeType": "gp3"}}]
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

  # Poll for fulfillment
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
      # Tag the instance
      aws ec2 create-tags --resources "$INSTANCE_ID" \
        --tags "Key=Name,Value=PrismataTraining-${LABEL}" \
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
  # On-demand launch
  echo "(Using ON-DEMAND pricing)"
  INSTANCE_ID=$(MSYS_NO_PATHCONV=1 aws ec2 run-instances \
    --image-id "$AMI" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile Name="$PROFILE" \
    --user-data "file://$USERDATA_FILE" \
    --instance-initiated-shutdown-behavior terminate \
    --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=350,VolumeType=gp3}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataTraining-${LABEL}}]" \
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
echo "=== Training Instance Launched ==="
echo "  Instance ID: $INSTANCE_ID"
echo "  Type:        $INSTANCE_TYPE"
echo "  Label:       $LABEL"
echo ""
echo "The instance will:"
echo "  1. Boot Amazon Linux 2023 + PyTorch 2.6 (~2 min)"
echo "  2. Download training code + selfplay data from S3 (~5 min)"
echo "  3. Train on NVIDIA T4 GPU (hidden=$HIDDEN_DIM, lr=$LR)"
echo "  4. Upload model + metrics to s3://$BUCKET/training-runs/$LABEL/"
echo "  5. Auto-terminate (no ongoing charges)"
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
