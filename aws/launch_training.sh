#!/bin/bash
# Launch g4dn.xlarge EC2 GPU instance for neural network training
# Usage: bash aws/launch_training.sh [OPTIONS]
#
# Options (via env vars):
#   HIDDEN_DIM=256       Hidden layer size (default: 256)
#   LR=1e-5              Learning rate (default: 1e-5)
#   EPOCHS=100           Max epochs (default: 100)
#   BATCH_SIZE=512       Batch size (default: 512)
#   PATIENCE=15          Early stopping patience (default: 15)
#   LOSS_FN=mse          Loss function: mse or bce (default: mse)
#   EVAL_STEPS=5000      Eval every N steps (default: 5000)
#   MAX_RECORDS=0        Max records to load, 0=all (default: 0)
#   LABEL=256h_400k      Run label for S3 output dir (default: auto)
#   INSTANCE_TYPE=g4dn.xlarge  Instance type (default: g4dn.xlarge)
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

# Hyperparameters
HIDDEN_DIM="${HIDDEN_DIM:-256}"
LR="${LR:-1e-5}"
EPOCHS="${EPOCHS:-100}"
BATCH_SIZE="${BATCH_SIZE:-512}"
PATIENCE="${PATIENCE:-15}"
LOSS_FN="${LOSS_FN:-mse}"
EVAL_STEPS="${EVAL_STEPS:-5000}"
MAX_RECORDS="${MAX_RECORDS:-0}"
SEED="${SEED:-42}"

# Infrastructure
INSTANCE_TYPE="${INSTANCE_TYPE:-g4dn.xlarge}"
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
  LABEL="h${HIDDEN_DIM}_lr${LR}"
fi

echo "=== Prismata Training GPU Launch ==="
echo "  Instance:   $INSTANCE_TYPE"
echo "  GPU:        NVIDIA T4 (16GB)"
echo "  Label:      $LABEL"
echo "  Hidden dim: $HIDDEN_DIM"
echo "  LR:         $LR"
echo "  Epochs:     $EPOCHS"
echo "  Batch size: $BATCH_SIZE"
echo "  Patience:   $PATIENCE"
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
set -euo pipefail

# ============================================================
# Prismata Training Worker (g4dn.xlarge, NVIDIA T4)
# ============================================================
BUCKET="$BUCKET"
REGION="$REGION"
LABEL="$LABEL"
HIDDEN_DIM=$HIDDEN_DIM
LR=$LR
EPOCHS=$EPOCHS
BATCH_SIZE=$BATCH_SIZE
PATIENCE=$PATIENCE
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
echo "Instance: \$(curl -s http://169.254.169.254/latest/meta-data/instance-type)"
date

# ============================================================
# Setup environment
# ============================================================
echo "Activating PyTorch environment..."
source /opt/conda/etc/profile.d/conda.sh
conda activate pytorch

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

echo "Downloading selfplay data from S3..."
aws s3 sync s3://\$BUCKET/results/ \$WORK/selfplay_data/ --region \$REGION --quiet
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
  "records": \$RECORD_COUNT,
  "instance_type": "\$(curl -s http://169.254.169.254/latest/meta-data/instance-type)"
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
echo "  LR: \$LR"
echo "  Records: \$RECORD_COUNT"
echo ""

cd \$WORK

# Build training command
TRAIN_CMD="python training/train.py training/data training/models \\
  --selfplay-dir selfplay_data/ \\
  --value-only \\
  --hidden-dim \$HIDDEN_DIM \\
  --epochs \$EPOCHS \\
  --batch-size \$BATCH_SIZE \\
  --lr \$LR \\
  --tanh-in-training \\
  --loss-fn \$LOSS_FN \\
  --patience \$PATIENCE \\
  --num-workers 4 \\
  --eval-every-steps \$EVAL_STEPS \\
  --seed \$SEED \\
  --device cuda"

# Add --max-records if set
if [ \$MAX_RECORDS -gt 0 ]; then
  TRAIN_CMD="\$TRAIN_CMD --max-records \$MAX_RECORDS"
fi

echo "Command: \$TRAIN_CMD"
echo ""

eval \$TRAIN_CMD 2>&1 | tee training_output.log
TRAIN_EXIT=\$?

echo ""
echo "Training exited with code: \$TRAIN_EXIT"

# ============================================================
# Upload results
# ============================================================
echo "Uploading results to S3..."
S3_PREFIX="training-runs/\$LABEL/\$RUN_ID"

# Upload model checkpoints
aws s3 sync training/models/ s3://\$BUCKET/\$S3_PREFIX/models/ --region \$REGION

# Upload run JSONs (metrics)
if [ -d training/runs ]; then
  aws s3 sync training/runs/ s3://\$BUCKET/\$S3_PREFIX/runs/ --region \$REGION
fi

# Upload training output log
aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$REGION

# Export weights to binary format
echo "Exporting weights..."
if [ -f training/models/best_model.pt ]; then
  python training/export_weights.py training/models/best_model.pt training/models/neural_weights.bin
  aws s3 cp training/models/neural_weights.bin s3://\$BUCKET/\$S3_PREFIX/neural_weights.bin --region \$REGION
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

# Self-terminate
echo "Shutting down..."
sudo shutdown -h now
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

echo "Launching instance..."

SPOT_OPTS=""
if [ "$USE_SPOT" = "true" ]; then
  SPOT_OPTS="--instance-market-options MarketType=spot"
  echo "(Using SPOT pricing)"
fi

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name="$PROFILE" \
  --user-data "file://$USERDATA_FILE" \
  --instance-initiated-shutdown-behavior terminate \
  --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=100,VolumeType=gp3}" \
  $SPOT_OPTS \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=PrismataTraining-${LABEL}}]" \
  --query 'Instances[0].InstanceId' \
  --output text \
  --region "$REGION" 2>&1)

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
