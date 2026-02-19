#!/bin/bash
# Launch GCP Compute Engine GPU instance for neural network training
# Usage: bash gcp/launch_training.sh [OPTIONS]
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
#   MACHINE_TYPE=g2-standard-4   Machine type (default: g2-standard-4)
#   GPU_TYPE=nvidia-l4   GPU accelerator type (default: nvidia-l4)
#   USE_SPOT=false       Use spot/preemptible pricing (default: false)
#   RESUME_FROM=""       S3 path to checkpoint to resume from (default: none)
#   DRY_RUN=true         Print startup script without launching (default: false)
#
# Examples:
#   bash gcp/launch_training.sh                              # 256h default
#   HIDDEN_DIM=512 bash gcp/launch_training.sh               # 512h model
#   HIDDEN_DIM=256 LR=3e-5 bash gcp/launch_training.sh      # LR sweep
#   DRY_RUN=true bash gcp/launch_training.sh                 # Preview startup
#   USE_SPOT=false bash gcp/launch_training.sh               # On-demand (if spot unavailable)
#
# Parallel sweep example:
#   for lr in 1e-5 3e-5 1e-4; do
#     HIDDEN_DIM=256 LR=$lr LABEL="sweep_256h_lr${lr}" bash gcp/launch_training.sh
#     sleep 5
#   done

export PATH="$PATH:/c/google-cloud-sdk/bin:/c/Program Files/Amazon/AWSCLIV2"

# Verify tools
if ! command -v gcloud &>/dev/null; then
    echo "ERROR: gcloud not found. Install Google Cloud SDK or check PATH."
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
RESUME_FROM="${RESUME_FROM:-}"

# Infrastructure
MACHINE_TYPE="${MACHINE_TYPE:-g2-standard-4}"
USE_SPOT="${USE_SPOT:-false}"
DRY_RUN="${DRY_RUN:-false}"
PROJECT="prismata-selfplay"
ZONE="us-central1-a"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
GPU_COUNT=1
IMAGE_FAMILY="pytorch-2-7-cu128-ubuntu-2204-nvidia-570"
IMAGE_PROJECT="deeplearning-platform-release"
BUCKET="prismata-selfplay-data"
S3_REGION="eu-north-1"

# Load AWS credentials for S3 access (skip in DRY_RUN mode)
CRED_FILE="$(cd "$(dirname "$0")" && pwd)/.aws_credentials"
if [ "$DRY_RUN" != "true" ]; then
    if [ ! -f "$CRED_FILE" ]; then
        echo "ERROR: AWS credentials not found at $CRED_FILE"
        echo "Create it with:"
        echo "  AWS_ACCESS_KEY_ID=..."
        echo "  AWS_SECRET_ACCESS_KEY=..."
        exit 1
    fi
    source "$CRED_FILE"
else
    AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-PLACEHOLDER}"
    AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-PLACEHOLDER}"
fi

# Auto-generate label if not provided
if [ -z "$LABEL" ]; then
    LABEL="h${HIDDEN_DIM}_lr${LR}"
fi

echo "=== Prismata Training GCP GPU Launch ==="
echo "  Machine:    $MACHINE_TYPE + $GPU_TYPE x$GPU_COUNT"
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
echo "  Resume:     ${RESUME_FROM:-none}"
echo "  Zone:       $ZONE"
echo "  Spot:       $USE_SPOT"
echo "  Image:      $IMAGE_FAMILY"
echo ""

# Build the startup script (bash for Linux DL VM)
STARTUP_SCRIPT=$(cat <<ENDSCRIPT
#!/bin/bash
set -uo pipefail

# ============================================================
# Prismata Training Worker (GCP GPU)
# ============================================================
BUCKET="$BUCKET"
S3_REGION="$S3_REGION"
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
RESUME_FROM="$RESUME_FROM"

RUN_ID=\$(date +%Y-%m-%d_%H-%M-%S)
WORK="/root/training"
LOG="/root/training_boot.log"
export PYTHONUNBUFFERED=1

# Increase file descriptor limit for streaming DataLoader (6000+ shard mmaps per worker)
ulimit -n 65536

exec > >(tee -a "\$LOG") 2>&1

echo "=== Prismata Training GCP Worker Starting ==="
echo "Run ID: \$RUN_ID"
echo "Label: \$LABEL"
INSTANCE_NAME=\$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name)
INSTANCE_ZONE=\$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | rev | cut -d'/' -f1 | rev)
echo "Instance: \$INSTANCE_NAME in \$INSTANCE_ZONE"
date

# ============================================================
# Setup environment
# ============================================================
echo "Checking GPU..."
nvidia-smi || { echo "ERROR: nvidia-smi failed"; exit 1; }

# The DL VM image comes with conda + pytorch pre-installed
echo "Activating PyTorch environment..."
# DL VM images put conda at /opt/conda
if [ -f /opt/conda/etc/profile.d/conda.sh ]; then
    source /opt/conda/etc/profile.d/conda.sh
    # Try pytorch env first, fall back to base
    conda activate pytorch 2>/dev/null || conda activate base
fi

# Ensure python3 is aliased as python (some DL VMs only have python3)
which python 2>/dev/null || ln -s \$(which python3) /usr/local/bin/python

python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}'); print(f'PyTorch: {torch.__version__}')"

# Install deps
pip install tqdm --quiet 2>/dev/null || pip3 install tqdm --quiet 2>/dev/null || true

# ============================================================
# Install AWS CLI for S3 access
# ============================================================
echo "Installing AWS CLI..."
if ! command -v aws &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq unzip > /dev/null 2>&1
    curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    cd /tmp && unzip -q awscliv2.zip && sudo ./aws/install --update
    cd -
fi

# Get AWS credentials from instance metadata
AWS_KEY_ID=\$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/aws-key-id)
AWS_SECRET=\$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/aws-secret-key)
export AWS_ACCESS_KEY_ID="\$AWS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="\$AWS_SECRET"
export AWS_DEFAULT_REGION="\$S3_REGION"

# Verify S3 access
aws s3 ls s3://\$BUCKET/ --region \$S3_REGION 2>&1 | head -3
echo "AWS S3 access verified"

# ============================================================
# Download training code and data
# ============================================================
echo "Downloading training code from S3..."
mkdir -p \$WORK/training/data \$WORK/models

aws s3 cp s3://\$BUCKET/deploy/training/train.py \$WORK/training/train.py --region \$S3_REGION
aws s3 cp s3://\$BUCKET/deploy/training/load_selfplay.py \$WORK/training/load_selfplay.py --region \$S3_REGION
aws s3 cp s3://\$BUCKET/deploy/training/schema.json \$WORK/training/schema.json --region \$S3_REGION
aws s3 cp s3://\$BUCKET/deploy/training/export_weights.py \$WORK/training/export_weights.py --region \$S3_REGION
aws s3 cp s3://\$BUCKET/deploy/training/unit_index.json \$WORK/training/data/unit_index.json --region \$S3_REGION

echo "Downloading selfplay data from S3..."
aws s3 sync s3://\$BUCKET/results/ \$WORK/selfplay_data/ --region \$S3_REGION --quiet || echo "WARNING: s3 sync exited non-zero (partial transfer errors are normal for large syncs)"
echo "Download complete."

# Stage selfplay data to GCS for future runs (avoids S3 egress on subsequent launches)
echo "Staging selfplay data to GCS (background)..."
(gsutil -m rsync -r \$WORK/selfplay_data/ gs://prismata-selfplay-data/selfplay_data/ 2>&1 | tail -5 && echo "[gcs] Selfplay data staged to GCS") &
GCS_STAGE_PID=\$!

# Download resume checkpoint if specified
if [ -n "\$RESUME_FROM" ]; then
    echo "Downloading resume checkpoint: \$RESUME_FROM"
    mkdir -p \$WORK/resume
    aws s3 cp "s3://\$BUCKET/\$RESUME_FROM" \$WORK/resume/checkpoint.pt --region \$S3_REGION
    echo "Resume checkpoint downloaded."
fi

# Count data
RECORD_COUNT=\$(python3 -c "
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
  "provider": "gcp",
  "machine_type": "\$(curl -sf -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/machine-type | rev | cut -d'/' -f1 | rev)",
  "gpu": "$GPU_TYPE",
  "num_layers": $NUM_LAYERS,
  "warmup_epochs": $WARMUP_EPOCHS,
  "dropout": $DROPOUT,
  "weight_decay": $WEIGHT_DECAY,
  "label_smooth": $LABEL_SMOOTH,
  "resume_from": "\$RESUME_FROM"
}
CONFIGEOF
aws s3 cp /tmp/run_config.json s3://\$BUCKET/training-runs/\$LABEL/\$RUN_ID/run_config.json --region \$S3_REGION

# ============================================================
# Run training
# ============================================================
echo ""
echo "=== Starting training ==="
echo "  Device: cuda"
echo "  Hidden dim: \$HIDDEN_DIM"
echo "  Layers: \$NUM_LAYERS"
echo "  LR: \$LR"
echo "  Records: \$RECORD_COUNT"
echo ""

cd \$WORK

# Build training command
TRAIN_CMD="python3 training/train.py training/data training/models \\
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
  --num-workers 4 \\
  --eval-every-steps \$EVAL_STEPS \\
  --seed \$SEED \\
  --streaming \\
  --device cuda"

# Add --max-records if set
if [ \$MAX_RECORDS -gt 0 ]; then
  TRAIN_CMD="\$TRAIN_CMD --max-records \$MAX_RECORDS"
fi

# Add --resume if checkpoint available
if [ -n "\$RESUME_FROM" ] && [ -f \$WORK/resume/checkpoint.pt ]; then
  TRAIN_CMD="\$TRAIN_CMD --resume \$WORK/resume/checkpoint.pt"
fi

echo "Command: \$TRAIN_CMD"
echo ""

# Background checkpoint sync — uploads to S3 every 5 min so preemption doesn't lose progress
S3_PREFIX="training-runs/\$LABEL/\$RUN_ID"
(
  while true; do
    sleep 300
    if [ -d training/models ]; then
      aws s3 sync training/models/ s3://\$BUCKET/\$S3_PREFIX/models/ --region \$S3_REGION --quiet 2>/dev/null
    fi
    if [ -d training/runs ]; then
      aws s3 sync training/runs/ s3://\$BUCKET/\$S3_PREFIX/runs/ --region \$S3_REGION --quiet 2>/dev/null
    fi
    aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$S3_REGION --quiet 2>/dev/null
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
aws s3 sync training/models/ s3://\$BUCKET/\$S3_PREFIX/models/ --region \$S3_REGION

# Upload run JSONs (metrics)
if [ -d training/runs ]; then
  aws s3 sync training/runs/ s3://\$BUCKET/\$S3_PREFIX/runs/ --region \$S3_REGION
fi

# Upload training output log
aws s3 cp training_output.log s3://\$BUCKET/\$S3_PREFIX/training_output.log --region \$S3_REGION

# Export weights to binary format
echo "Exporting weights..."
if [ -f training/models/best_model.pt ]; then
  python3 training/export_weights.py training/models/best_model.pt training/models/neural_weights.bin
  aws s3 cp training/models/neural_weights.bin s3://\$BUCKET/\$S3_PREFIX/neural_weights.bin --region \$S3_REGION
  echo "Weights exported and uploaded."
else
  echo "WARNING: No best_model.pt found!"
fi

# Upload boot log
aws s3 cp \$LOG s3://\$BUCKET/\$S3_PREFIX/training_boot.log --region \$S3_REGION

echo ""
echo "=== Training complete ==="
echo "Results at: s3://\$BUCKET/\$S3_PREFIX/"
echo "Download model: aws s3 cp s3://\$BUCKET/\$S3_PREFIX/neural_weights.bin bin/asset/config/neural_weights.bin --region \$S3_REGION"
echo "Download checkpoint: aws s3 cp s3://\$BUCKET/\$S3_PREFIX/models/best_model.pt training/models/ --region \$S3_REGION"
date

# Self-delete the instance
echo "Self-deleting instance..."
gcloud compute instances delete \$INSTANCE_NAME --zone=\$INSTANCE_ZONE --quiet 2>&1 || true
# Fallback
sudo shutdown -h now
ENDSCRIPT
)

if [ "$DRY_RUN" = "true" ]; then
    echo "=== DRY RUN - Startup script: ==="
    echo "$STARTUP_SCRIPT"
    exit 0
fi

# Write startup script to temp file
STARTUP_FILE="c:/libraries/PrismataAI/gcp/.startup_training_tmp.sh"
echo "$STARTUP_SCRIPT" > "$STARTUP_FILE"

echo "Launching instance..."

SPOT_OPTS=""
if [ "$USE_SPOT" = "true" ]; then
    SPOT_OPTS="--provisioning-model=SPOT --instance-termination-action=DELETE"
    echo "(Using SPOT/Preemptible pricing)"
fi

INSTANCE_NAME="prismata-training-$(date +%H%M%S)"

gcloud compute instances create "$INSTANCE_NAME" \
    --project="$PROJECT" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --accelerator="type=$GPU_TYPE,count=$GPU_COUNT" \
    --maintenance-policy=TERMINATE \
    --image-family="$IMAGE_FAMILY" \
    --image-project="$IMAGE_PROJECT" \
    --boot-disk-size=250GB \
    --boot-disk-type=pd-standard \
    --metadata="aws-key-id=$AWS_ACCESS_KEY_ID,aws-secret-key=$AWS_SECRET_ACCESS_KEY,install-nvidia-driver=True" \
    --metadata-from-file="startup-script=$STARTUP_FILE" \
    --scopes=compute-rw,storage-ro \
    $SPOT_OPTS \
    --no-restart-on-failure \
    2>&1

rm -f "$STARTUP_FILE"

echo ""
echo "=== Training Instance Launched ==="
echo "  Instance:   $INSTANCE_NAME"
echo "  Machine:    $MACHINE_TYPE + $GPU_TYPE"
echo "  Label:      $LABEL"
echo "  Zone:       $ZONE"
echo "  Spot:       $USE_SPOT"
echo ""
echo "The instance will:"
echo "  1. Boot Ubuntu 22.04 + PyTorch 2.7 + CUDA 12.8 (~3 min)"
echo "  2. Install AWS CLI, download training code + data (~5 min)"
echo "  3. Train on $GPU_TYPE GPU (hidden=$HIDDEN_DIM, layers=$NUM_LAYERS, lr=$LR)"
echo "  4. Upload model + metrics to s3://$BUCKET/training-runs/$LABEL/"
echo "  5. Self-delete (no ongoing charges)"
echo ""
echo "Monitor:"
echo "  gcloud compute instances list --project=$PROJECT"
echo ""
echo "SSH (check progress):"
echo "  gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --project=$PROJECT"
echo ""
echo "Serial console (boot logs):"
echo "  gcloud compute instances get-serial-port-output $INSTANCE_NAME --zone=$ZONE --project=$PROJECT"
echo ""
echo "Download results when done:"
echo "  aws s3 sync s3://$BUCKET/training-runs/$LABEL/ training/cloud-runs/$LABEL/ --region $S3_REGION"
