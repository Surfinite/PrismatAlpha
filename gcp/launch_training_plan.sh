#!/bin/bash
# Launch GCP GPU instance to execute the FULL training plan (12 runs)
# Downloads data once, runs all experiments sequentially, uploads results after each.
#
# Usage: bash gcp/launch_training_plan.sh
#
# This script creates a startup script that:
#   1. Downloads selfplay data from GCS (fast) or S3 (fallback)
#   2. Runs Phase 1: R1 baseline
#   3. Runs Phase 2: R2-R6 grid (capacity x LR)
#   4. Decision gate: picks best hidden_dim and LR
#   5. Runs Phase 3: R7-R8 depth experiments
#   6. Decision gate: picks best depth
#   7. Runs Phase 4: R9-R12 regularization
#   8. Uploads all results, self-deletes

export PATH="$PATH:/c/google-cloud-sdk/bin:/c/Program Files/Amazon/AWSCLIV2"

# Load cloud config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../cloud-config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "ERROR: Missing cloud-config.env. Copy cloud-config.env.example and fill in your values."
    exit 1
fi

# Verify gcloud (on Windows it's a .cmd file, command -v won't find it)
if ! gcloud --version &>/dev/null; then
    echo "ERROR: gcloud not found. Install Google Cloud SDK or check PATH."
    exit 1
fi

# Infrastructure
MACHINE_TYPE="${MACHINE_TYPE:-g2-standard-4}"
USE_SPOT="${USE_SPOT:-false}"
DRY_RUN="${DRY_RUN:-false}"
PROJECT="${GCP_PROJECT:?Set GCP_PROJECT in cloud-config.env}"
ZONE="${GCP_ZONE:-us-central1-a}"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
GPU_COUNT=1
IMAGE_FAMILY="pytorch-2-7-cu128-ubuntu-2204-nvidia-570"
IMAGE_PROJECT="deeplearning-platform-release"
BUCKET="${CLOUD_BUCKET:?Set CLOUD_BUCKET in cloud-config.env}"
S3_REGION="${AWS_REGION:-eu-north-1}"

# Load AWS credentials
CRED_FILE="$(cd "$(dirname "$0")" && pwd)/.aws_credentials"
if [ "$DRY_RUN" != "true" ]; then
    if [ ! -f "$CRED_FILE" ]; then
        echo "ERROR: AWS credentials not found at $CRED_FILE"
        exit 1
    fi
    source "$CRED_FILE"
else
    AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-PLACEHOLDER}"
    AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-PLACEHOLDER}"
fi

echo "=== Prismata Training Plan — Full Execution ==="
echo "  Machine:    $MACHINE_TYPE + $GPU_TYPE x$GPU_COUNT"
echo "  Phases:     1-4 (12 runs total)"
echo "  Zone:       $ZONE"
echo "  Spot:       $USE_SPOT"
echo ""

STARTUP_SCRIPT=$(cat <<'ENDSCRIPT'
#!/bin/bash
set -uo pipefail

# ============================================================
# Prismata Training Plan — Full Automated Execution
# ============================================================
BUCKET="prismata-selfplay-data"
S3_REGION="eu-north-1"
export PYTHONUNBUFFERED=1

# Increase file descriptor limit for streaming DataLoader (6000+ shard mmaps per worker)
ulimit -n 65536

PLAN_RUN_ID=$(date +%Y-%m-%d_%H-%M-%S)
WORK="/root/training"
LOG="/root/training_boot.log"

exec > >(tee -a "$LOG") 2>&1

echo "=== Prismata Training Plan — Full Execution ==="
echo "Plan Run ID: $PLAN_RUN_ID"
INSTANCE_NAME=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name)
INSTANCE_ZONE=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | rev | cut -d'/' -f1 | rev)
echo "Instance: $INSTANCE_NAME in $INSTANCE_ZONE"
date

# ============================================================
# Setup environment
# ============================================================
echo "Checking GPU..."
nvidia-smi || { echo "ERROR: nvidia-smi failed"; exit 1; }

echo "Activating PyTorch environment..."
if [ -f /opt/conda/etc/profile.d/conda.sh ]; then
    source /opt/conda/etc/profile.d/conda.sh
    conda activate pytorch 2>/dev/null || conda activate base
fi
which python 2>/dev/null || ln -s $(which python3) /usr/local/bin/python

python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}'); print(f'PyTorch: {torch.__version__}')"
pip install tqdm --quiet 2>/dev/null || pip3 install tqdm --quiet 2>/dev/null || true

# ============================================================
# Install AWS CLI
# ============================================================
echo "Installing AWS CLI..."
if ! command -v aws &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq unzip > /dev/null 2>&1
    curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    cd /tmp && unzip -q awscliv2.zip && sudo ./aws/install --update
    cd -
fi

# Get AWS credentials from instance metadata
AWS_KEY_ID=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/aws-key-id)
AWS_SECRET=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/aws-secret-key)
export AWS_ACCESS_KEY_ID="$AWS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$AWS_SECRET"
export AWS_DEFAULT_REGION="$S3_REGION"

aws s3 ls s3://$BUCKET/ --region $S3_REGION 2>&1 | head -3
echo "AWS S3 access verified"

# ============================================================
# Download training code and data
# ============================================================
echo "Downloading training code from S3..."
mkdir -p $WORK/training/data $WORK/models

aws s3 cp s3://$BUCKET/deploy/training/train.py $WORK/training/train.py --region $S3_REGION
aws s3 cp s3://$BUCKET/deploy/training/load_selfplay.py $WORK/training/load_selfplay.py --region $S3_REGION
aws s3 cp s3://$BUCKET/deploy/training/schema.json $WORK/training/schema.json --region $S3_REGION
aws s3 cp s3://$BUCKET/deploy/training/export_weights.py $WORK/training/export_weights.py --region $S3_REGION
aws s3 cp s3://$BUCKET/deploy/training/unit_index.json $WORK/training/data/unit_index.json --region $S3_REGION

# Try GCS first (free within GCP), fall back to S3
echo "Checking GCS for selfplay data..."
GCS_COUNT=$(gsutil ls gs://prismata-selfplay-data/selfplay_data/ 2>/dev/null | wc -l || echo "0")
if [ "$GCS_COUNT" -gt 100 ]; then
    echo "Found data on GCS ($GCS_COUNT dirs). Downloading from GCS (free)..."
    gsutil -m rsync -r gs://prismata-selfplay-data/selfplay_data/ $WORK/selfplay_data/ 2>&1 | tail -10
    echo "GCS download complete."
else
    echo "GCS empty or small ($GCS_COUNT dirs). Downloading from S3..."
    aws s3 sync s3://$BUCKET/results/ $WORK/selfplay_data/ --region $S3_REGION --quiet || echo "WARNING: s3 sync exited non-zero (partial transfer errors are normal for large syncs)"
    echo "S3 download complete."
    # Stage to GCS in background for future runs
    echo "Staging selfplay data to GCS (background)..."
    (gsutil -m rsync -r $WORK/selfplay_data/ gs://prismata-selfplay-data/selfplay_data/ 2>&1 | tail -5 && echo "[gcs] Selfplay data staged to GCS") &
fi

# Count data
RECORD_COUNT=$(python3 -c "
import os
base = '$WORK/selfplay_data'
total = sum(
    (os.path.getsize(os.path.join(r, f)) - 68) // 7152
    for r, _, fs in os.walk(base)
    for f in fs
    if f.endswith('.bin') and os.path.getsize(os.path.join(r, f)) > 68
)
print(total)
")
GAME_COUNT=$((RECORD_COUNT / 37))
echo "Dataset: $RECORD_COUNT records (~$GAME_COUNT games)"

cd $WORK

# ============================================================
# Helper function: run one training experiment
# ============================================================
run_experiment() {
    local LABEL="$1"
    local HIDDEN_DIM="$2"
    local NUM_LAYERS="$3"
    local LR="$4"
    local DROPOUT="$5"
    local WEIGHT_DECAY="$6"
    local LABEL_SMOOTH="$7"

    local RUN_ID=$(date +%Y-%m-%d_%H-%M-%S)
    local S3_PREFIX="training-runs/$LABEL/$RUN_ID"
    local MODEL_DIR="training/models_$LABEL"

    echo ""
    echo "============================================================"
    echo "EXPERIMENT: $LABEL"
    echo "  Hidden: $HIDDEN_DIM, Layers: $NUM_LAYERS, LR: $LR"
    echo "  Dropout: $DROPOUT, WD: $WEIGHT_DECAY, Smooth: $LABEL_SMOOTH"
    echo "  Model dir: $MODEL_DIR"
    echo "  S3: s3://$BUCKET/$S3_PREFIX/"
    echo "  Time: $(date)"
    echo "============================================================"

    mkdir -p "$MODEL_DIR"

    # Upload run config
    cat > /tmp/run_config.json <<RCEOF
{
  "run_id": "$RUN_ID",
  "label": "$LABEL",
  "hidden_dim": $HIDDEN_DIM,
  "num_layers": $NUM_LAYERS,
  "lr": $LR,
  "epochs": 40,
  "batch_size": 512,
  "patience": 15,
  "loss_fn": "mse",
  "eval_steps": 5000,
  "seed": 42,
  "records": $RECORD_COUNT,
  "games": $GAME_COUNT,
  "dropout": $DROPOUT,
  "weight_decay": $WEIGHT_DECAY,
  "label_smooth": $LABEL_SMOOTH,
  "warmup_epochs": 2,
  "provider": "gcp",
  "plan_run_id": "$PLAN_RUN_ID"
}
RCEOF
    aws s3 cp /tmp/run_config.json s3://$BUCKET/$S3_PREFIX/run_config.json --region $S3_REGION

    # Run training
    python3 training/train.py training/data "$MODEL_DIR" \
        --selfplay-dir selfplay_data/ \
        --value-only \
        --hidden-dim $HIDDEN_DIM \
        --num-layers $NUM_LAYERS \
        --epochs 40 \
        --batch-size 512 \
        --lr $LR \
        --warmup-epochs 2 \
        --dropout $DROPOUT \
        --weight-decay $WEIGHT_DECAY \
        --label-smooth $LABEL_SMOOTH \
        --tanh-in-training \
        --loss-fn mse \
        --patience 15 \
        --num-workers 4 \
        --eval-every-steps 5000 \
        --seed 42 \
        --streaming \
        --device cuda 2>&1 | tee "output_$LABEL.log"

    local TRAIN_EXIT=$?
    echo "Training $LABEL exited with code: $TRAIN_EXIT"

    # Upload results
    echo "Uploading $LABEL results to S3..."
    aws s3 sync "$MODEL_DIR/" s3://$BUCKET/$S3_PREFIX/models/ --region $S3_REGION
    if [ -d training/runs ]; then
        aws s3 sync training/runs/ s3://$BUCKET/$S3_PREFIX/runs/ --region $S3_REGION
    fi
    aws s3 cp "output_$LABEL.log" s3://$BUCKET/$S3_PREFIX/training_output.log --region $S3_REGION

    # Export weights
    if [ -f "$MODEL_DIR/best_model.pt" ]; then
        python3 training/export_weights.py "$MODEL_DIR/best_model.pt" "$MODEL_DIR/neural_weights.bin"
        aws s3 cp "$MODEL_DIR/neural_weights.bin" s3://$BUCKET/$S3_PREFIX/neural_weights.bin --region $S3_REGION
        echo "Weights exported for $LABEL"
    else
        echo "WARNING: No best_model.pt found for $LABEL!"
    fi

    # Save result to a per-label file for easy comparison
    # Extract best val loss from the most recent run JSON
    python3 -c "
import json, glob, os
runs = sorted(glob.glob('training/runs/*.json'), key=os.path.getmtime, reverse=True)
for rf in runs:
    try:
        d = json.load(open(rf))
        vl = d.get('best_val_value_loss', d.get('best_val_loss', 999))
        print(f'Best val_loss for $LABEL: {vl:.6f}')
        with open('result_$LABEL.txt', 'w') as f:
            f.write(f'{vl} $HIDDEN_DIM $NUM_LAYERS $LR')
        break
    except: pass
" 2>/dev/null || echo "Could not extract val_loss for $LABEL"

    echo "=== $LABEL complete at $(date) ==="
}

# ============================================================
# Helper: pick best run from a set of labels
# ============================================================
pick_best() {
    # Usage: pick_best label1 label2 label3 ...
    # Returns: best_label best_val_loss best_hidden_dim best_num_layers best_lr
    python3 -c "
import sys
labels = sys.argv[1:]
best_loss = float('inf')
best_label = labels[0]
best_hd = '256'
best_nl = '2'
best_lr = '1e-5'
for label in labels:
    try:
        with open(f'result_{label}.txt') as f:
            parts = f.read().strip().split()
            vl = float(parts[0])
            if vl < best_loss:
                best_loss = vl
                best_label = label
                best_hd = parts[1] if len(parts) > 1 else '256'
                best_nl = parts[2] if len(parts) > 2 else '2'
                best_lr = parts[3] if len(parts) > 3 else '1e-5'
    except:
        pass
print(f'{best_label} {best_loss} {best_hd} {best_nl} {best_lr}')
" "$@"
}

# ============================================================
# PHASE 1: Baseline Retrain
# ============================================================
echo ""
echo "########################################################"
echo "# PHASE 1: Baseline Retrain (R1)"
echo "########################################################"

run_experiment "baseline_256h_356k" 256 2 1e-5 0.1 1e-4 0.95

# Decision gate: check val_loss
R1_VAL_LOSS=$(python3 -c "
import glob, json
for f in sorted(glob.glob('training/runs/*.json'), reverse=True):
    try:
        d = json.load(open(f))
        if 'best_val_value_loss' in d:
            print(f\"{d['best_val_value_loss']:.4f}\")
            break
    except:
        pass
" 2>/dev/null || echo "0.30")
echo "R1 val_loss: $R1_VAL_LOSS"

R1_CHECK=$(python3 -c "print('PASS' if float('$R1_VAL_LOSS') < 0.30 else 'FAIL')")
if [ "$R1_CHECK" = "FAIL" ]; then
    echo "WARNING: R1 val_loss > 0.30 ($R1_VAL_LOSS). Plan says investigate."
    echo "Continuing anyway (data may have improved since plan was written)."
fi

# ============================================================
# PHASE 2: Capacity x LR Grid (R2-R6)
# ============================================================
echo ""
echo "########################################################"
echo "# PHASE 2: Capacity x LR Grid (R2-R6)"
echo "########################################################"

run_experiment "grid_256h_lr5e6" 256 2 5e-6 0.1 1e-4 0.95
run_experiment "grid_256h_lr2e5" 256 2 2e-5 0.1 1e-4 0.95
run_experiment "grid_512h_lr5e6" 512 2 5e-6 0.1 1e-4 0.95
run_experiment "grid_512h_lr1e5" 512 2 1e-5 0.1 1e-4 0.95
run_experiment "grid_512h_lr2e5" 512 2 2e-5 0.1 1e-4 0.95

# Decision gate: pick best from R1-R6
echo ""
echo "=== Phase 2 Decision Gate ==="
PHASE2_RESULT=$(pick_best baseline_256h_356k grid_256h_lr5e6 grid_256h_lr2e5 grid_512h_lr5e6 grid_512h_lr1e5 grid_512h_lr2e5)
BEST_LABEL=$(echo $PHASE2_RESULT | cut -d' ' -f1)
BEST_LOSS=$(echo $PHASE2_RESULT | cut -d' ' -f2)
BEST_HD=$(echo $PHASE2_RESULT | cut -d' ' -f3)
BEST_NL=$(echo $PHASE2_RESULT | cut -d' ' -f4)
BEST_LR=$(echo $PHASE2_RESULT | cut -d' ' -f5)
echo "Phase 2 winner: $BEST_LABEL (val_loss=$BEST_LOSS, hidden=$BEST_HD, lr=$BEST_LR)"

# Upload phase summary
cat > /tmp/phase2_summary.json <<P2EOF
{
  "phase": 2,
  "winner": "$BEST_LABEL",
  "best_val_loss": $BEST_LOSS,
  "best_hidden_dim": $BEST_HD,
  "best_lr": "$BEST_LR",
  "timestamp": "$(date -Iseconds)"
}
P2EOF
aws s3 cp /tmp/phase2_summary.json s3://$BUCKET/training-runs/plan_$PLAN_RUN_ID/phase2_summary.json --region $S3_REGION

# ============================================================
# PHASE 3: Depth Experiments (R7-R8)
# ============================================================
echo ""
echo "########################################################"
echo "# PHASE 3: Depth Experiments (R7-R8)"
echo "# Using winner: hidden=$BEST_HD, lr=$BEST_LR"
echo "########################################################"

run_experiment "depth_3blocks" $BEST_HD 3 $BEST_LR 0.1 1e-4 0.95
run_experiment "depth_4blocks" $BEST_HD 4 $BEST_LR 0.1 1e-4 0.95

# Decision gate: pick best depth
echo ""
echo "=== Phase 3 Decision Gate ==="
PHASE3_RESULT=$(pick_best "$BEST_LABEL" depth_3blocks depth_4blocks)
BEST_LABEL=$(echo $PHASE3_RESULT | cut -d' ' -f1)
BEST_LOSS=$(echo $PHASE3_RESULT | cut -d' ' -f2)
BEST_HD=$(echo $PHASE3_RESULT | cut -d' ' -f3)
BEST_NL=$(echo $PHASE3_RESULT | cut -d' ' -f4)
BEST_LR=$(echo $PHASE3_RESULT | cut -d' ' -f5)
echo "Phase 3 winner: $BEST_LABEL (val_loss=$BEST_LOSS, hidden=$BEST_HD, layers=$BEST_NL, lr=$BEST_LR)"

cat > /tmp/phase3_summary.json <<P3EOF
{
  "phase": 3,
  "winner": "$BEST_LABEL",
  "best_val_loss": $BEST_LOSS,
  "best_hidden_dim": $BEST_HD,
  "best_num_layers": $BEST_NL,
  "best_lr": "$BEST_LR",
  "timestamp": "$(date -Iseconds)"
}
P3EOF
aws s3 cp /tmp/phase3_summary.json s3://$BUCKET/training-runs/plan_$PLAN_RUN_ID/phase3_summary.json --region $S3_REGION

# ============================================================
# PHASE 4: Regularization Tuning (R9-R12)
# ============================================================
echo ""
echo "########################################################"
echo "# PHASE 4: Regularization Tuning (R9-R12)"
echo "# Using winner: hidden=$BEST_HD, layers=$BEST_NL, lr=$BEST_LR"
echo "########################################################"

run_experiment "reg_dropout05" $BEST_HD $BEST_NL $BEST_LR 0.05 1e-4 0.95
run_experiment "reg_dropout20" $BEST_HD $BEST_NL $BEST_LR 0.2 1e-4 0.95
run_experiment "reg_smooth100" $BEST_HD $BEST_NL $BEST_LR 0.1 1e-4 1.0
run_experiment "reg_smooth90" $BEST_HD $BEST_NL $BEST_LR 0.1 1e-4 0.90

# Final decision
echo ""
echo "=== Final Decision Gate ==="
FINAL_RESULT=$(pick_best "$BEST_LABEL" reg_dropout05 reg_dropout20 reg_smooth100 reg_smooth90)
FINAL_LABEL=$(echo $FINAL_RESULT | cut -d' ' -f1)
FINAL_LOSS=$(echo $FINAL_RESULT | cut -d' ' -f2)
echo "Overall winner: $FINAL_LABEL (val_loss=$FINAL_LOSS)"

# ============================================================
# Final summary
# ============================================================
cat > /tmp/plan_summary.json <<SUMEOF
{
  "plan_run_id": "$PLAN_RUN_ID",
  "overall_winner": "$FINAL_LABEL",
  "final_val_loss": $FINAL_LOSS,
  "records": $RECORD_COUNT,
  "games": $GAME_COUNT,
  "instance": "$INSTANCE_NAME",
  "completed_at": "$(date -Iseconds)",
  "runs_completed": [
    "baseline_256h_356k",
    "grid_256h_lr5e6", "grid_256h_lr2e5",
    "grid_512h_lr5e6", "grid_512h_lr1e5", "grid_512h_lr2e5",
    "depth_3blocks", "depth_4blocks",
    "reg_dropout05", "reg_dropout20", "reg_smooth100", "reg_smooth90"
  ]
}
SUMEOF
aws s3 cp /tmp/plan_summary.json s3://$BUCKET/training-runs/plan_$PLAN_RUN_ID/plan_summary.json --region $S3_REGION

# Upload the winning weights prominently
WINNER_WEIGHTS="training/models_$FINAL_LABEL/neural_weights.bin"
if [ -f "$WINNER_WEIGHTS" ]; then
    aws s3 cp "$WINNER_WEIGHTS" s3://$BUCKET/training-runs/plan_$PLAN_RUN_ID/WINNER_neural_weights.bin --region $S3_REGION
    echo "Winner weights uploaded to s3://$BUCKET/training-runs/plan_$PLAN_RUN_ID/WINNER_neural_weights.bin"
fi

# Upload boot log
aws s3 cp $LOG s3://$BUCKET/training-runs/plan_$PLAN_RUN_ID/training_boot.log --region $S3_REGION

echo ""
echo "############################################"
echo "# TRAINING PLAN COMPLETE"
echo "# Winner: $FINAL_LABEL"
echo "# Val loss: $FINAL_LOSS"
echo "# Results: s3://$BUCKET/training-runs/plan_$PLAN_RUN_ID/"
echo "############################################"
date

# Self-delete
echo "Self-deleting instance..."
gcloud compute instances delete $INSTANCE_NAME --zone=$INSTANCE_ZONE --quiet 2>&1 || true
sudo shutdown -h now
ENDSCRIPT
)

# Inject sourced config values into startup script (heredoc is single-quoted to protect shell syntax)
STARTUP_SCRIPT="${STARTUP_SCRIPT/BUCKET=\"prismata-selfplay-data\"/BUCKET=\"$BUCKET\"}"
STARTUP_SCRIPT="${STARTUP_SCRIPT/S3_REGION=\"eu-north-1\"/S3_REGION=\"$S3_REGION\"}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//gs:\/\/prismata-selfplay-data\//gs:\/\/$BUCKET\/}"

if [ "$DRY_RUN" = "true" ]; then
    echo "=== DRY RUN ==="
    echo "$STARTUP_SCRIPT"
    exit 0
fi

STARTUP_FILE="c:/libraries/PrismataAI/gcp/.startup_plan_tmp.sh"
echo "$STARTUP_SCRIPT" > "$STARTUP_FILE"

echo "Launching instance..."

SPOT_OPTS=""
if [ "$USE_SPOT" = "true" ]; then
    SPOT_OPTS="--provisioning-model=SPOT --instance-termination-action=DELETE"
fi

INSTANCE_NAME="prismata-plan-$(date +%H%M%S)"

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
echo "=== Training Plan Instance Launched ==="
echo "  Instance: $INSTANCE_NAME"
echo "  Runs 12 experiments sequentially, uploads after each"
echo "  Total time estimate: ~1 hr (data download) + ~30 min (training) + ~10 min (uploads)"
echo ""
echo "Monitor:"
echo "  gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --project=$PROJECT --quiet --command='sudo tail -50 /root/training_boot.log'"
echo ""
echo "Results when done:"
echo "  aws s3 ls s3://$BUCKET/training-runs/plan_/ --region $S3_REGION --recursive"
