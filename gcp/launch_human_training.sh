#!/bin/bash
# Launch GCP GPU instance for DeepSets training on HUMAN REPLAY data only
# Usage: bash gcp/launch_human_training.sh [OPTIONS]
#
# Trains on human_1500_no6s_v2.h5 (2.5M records from 97,317 expert replays,
# both players ≥1500 rated, 6s bullet excluded, balance-validated).
#
# Options (via env vars):
#   LR=3e-4              Learning rate (default: 3e-4)
#   EPOCHS=100           Max epochs (default: 100)
#   BATCH_SIZE=512       Batch size (default: 512)
#   PATIENCE=15          Early stopping patience (default: 15)
#   MAX_RECORDS=0        Max records to load, 0=all (default: 0)
#   LABEL=human_1500     Run label for GCS output dir (default: human_1500)
#   MACHINE_TYPE=g2-standard-8   Machine type (default: g2-standard-8, 1xL4 32GB RAM)
#   ZONE=us-central1-a   Zone (default: us-central1-a)
#   DRY_RUN=true         Print startup script without launching (default: false)
#
# Data files (must exist locally):
#   training/data/human_1500_no6s_v2.h5   — Human expert replays (~2.5M records)
#   training/data/local_mbvmb.h5          — Validation set (~414K records)
#   training/property_table.json

GCLOUD="C:/google-cloud-sdk/bin/gcloud.cmd"

# Hyperparameters
LR="${LR:-3e-4}"
EPOCHS="${EPOCHS:-100}"
BATCH_SIZE="${BATCH_SIZE:-512}"
PATIENCE="${PATIENCE:-15}"
MAX_RECORDS="${MAX_RECORDS:-0}"
SEED="${SEED:-42}"

# Infrastructure
MACHINE_TYPE="${MACHINE_TYPE:-g2-standard-8}"
ZONE="${ZONE:-us-central1-a}"
DRY_RUN="${DRY_RUN:-false}"
PROJECT="prismata-selfplay"
BUCKET="prismata-selfplay-data"
IMAGE_FAMILY="pytorch-2-7-cu128-ubuntu-2204-nvidia-570"
IMAGE_PROJECT="deeplearning-platform-release"

# Auto-generate label if not provided
LABEL="${LABEL:-human_1500}"

# Training data files
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

echo "=== Prismata DeepSets Training — HUMAN REPLAYS ONLY (GCP) ==="
echo "  Machine:    $MACHINE_TYPE"
echo "  GPU:        NVIDIA L4 (24GB)"
echo "  Label:      $LABEL"
echo "  LR:         $LR"
echo "  Epochs:     $EPOCHS"
echo "  Batch size: $BATCH_SIZE"
echo "  Patience:   $PATIENCE"
echo "  Max records: $MAX_RECORDS (0=all)"
echo "  Seed:       $SEED"
echo "  Zone:       $ZONE"
echo "  Spot:       yes (preemptible)"
echo "  Mode:       streaming (chunk-buffered, minimal RAM)"
echo ""
echo "  Training data:"
echo "    $TRAIN_FILE ($(du -h "$TRAIN_FILE" | cut -f1))"
echo "  Val data:   $VAL_FILE ($(du -h "$VAL_FILE" | cut -f1))"
echo ""

# ============================================================
# Step 1: Upload data and code to GCS
# ============================================================
if [ "${SKIP_UPLOAD:-false}" = "true" ]; then
  echo "=== Skipping upload (SKIP_UPLOAD=true, data already in GCS) ==="
else
  echo "=== Uploading training code and data to GCS ==="

  echo "  Uploading training code..."
  $GCLOUD storage cp training/train.py gs://$BUCKET/deploy/deepsets/train.py
  $GCLOUD storage cp training/model_deepsets.py gs://$BUCKET/deploy/deepsets/model_deepsets.py
  $GCLOUD storage cp training/export_weights_v2.py gs://$BUCKET/deploy/deepsets/export_weights_v2.py
  $GCLOUD storage cp "$PROP_TABLE" gs://$BUCKET/deploy/deepsets/property_table.json

  echo "  Uploading HDF5 data files..."
  TRAIN_BASENAME=$(basename "$TRAIN_FILE")
  echo "    $TRAIN_BASENAME..."
  $GCLOUD storage cp "$TRAIN_FILE" "gs://$BUCKET/deploy/deepsets/$TRAIN_BASENAME"

  VAL_BASENAME=$(basename "$VAL_FILE")
  echo "    $VAL_BASENAME..."
  $GCLOUD storage cp "$VAL_FILE" "gs://$BUCKET/deploy/deepsets/$VAL_BASENAME"

  echo "  Upload complete."
fi
echo ""

# ============================================================
# Step 2: Build startup script
# ============================================================
TRAIN_BASENAME=$(basename "$TRAIN_FILE")
VAL_BASENAME=$(basename "$VAL_FILE")
INSTANCE_NAME="prismata-human-${LABEL//[_.]/-}-$(date +%m%d-%H%M)"

STARTUP_SCRIPT=$(cat <<'ENDSCRIPT'
#!/bin/bash

# Log everything to boot.log from the start
exec > >(tee -a /tmp/startup_boot.log) 2>&1
echo "=== Startup script began at $(date) ==="

# Upload logs to GCS on any exit, then shutdown
cleanup_and_shutdown() {
    echo "[trap] Script exiting (code $?) at $(date)"
    gcloud storage cp /tmp/startup_boot.log gs://${BUCKET:-prismata-selfplay-data}/debug/startup_boot_$(date +%s).log 2>/dev/null || true
    if [ -f /home/training/training_output.log ] && [ -n "${GCS_PREFIX:-}" ]; then
        gcloud storage cp /home/training/training_output.log gs://$BUCKET/$GCS_PREFIX/training_output.log 2>/dev/null || true
    fi
    kill $SYNC_PID 2>/dev/null || true
    sudo shutdown -h now
}
trap cleanup_and_shutdown EXIT

BUCKET="PLACEHOLDER_BUCKET"
LABEL="PLACEHOLDER_LABEL"
LR=PLACEHOLDER_LR
EPOCHS=PLACEHOLDER_EPOCHS
BATCH_SIZE=PLACEHOLDER_BATCH_SIZE
PATIENCE=PLACEHOLDER_PATIENCE
MAX_RECORDS=PLACEHOLDER_MAX_RECORDS
SEED=PLACEHOLDER_SEED
TRAIN_BASENAME="PLACEHOLDER_TRAIN_BASENAME"
VAL_BASENAME="PLACEHOLDER_VAL_BASENAME"

RUN_ID=$(date +%Y-%m-%d_%H-%M-%S)
WORK="/home/training"
LOG="/home/training/boot.log"

mkdir -p $WORK

echo "=== Prismata DeepSets Training — HUMAN REPLAYS ONLY (GCP) ==="
echo "Run ID: $RUN_ID"
echo "Label: $LABEL"
echo "Instance: $(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/machine-type | awk -F/ '{print $NF}')"
date

# Setup environment — find Python with PyTorch
echo "Setting up Python environment..."
echo "Looking for Python installations..."
which python3 || true
which python || true
ls /opt/conda/bin/python* 2>/dev/null || true
ls /opt/pytorch/bin/python* 2>/dev/null || true

# Try common DL VM paths
for p in /opt/conda/bin /opt/pytorch/bin /usr/local/bin /usr/bin; do
  if [ -x "$p/python3" ] || [ -x "$p/python" ]; then
    export PATH="$p:$PATH"
    echo "Using Python from $p"
    break
  fi
done

echo "Python: $(which python3 2>/dev/null || which python)"
echo "Version: $(python3 --version 2>/dev/null || python --version)"

echo "GPU check:"
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"none\"}'); print(f'PyTorch: {torch.__version__}')" || echo "WARNING: PyTorch GPU check failed"

pip install tqdm h5py --quiet 2>/dev/null || pip3 install tqdm h5py --quiet 2>/dev/null || true

export HDF5_USE_FILE_LOCKING=FALSE
export PYTHONUNBUFFERED=1

# Download code and data from GCS
echo "Downloading training code and data from GCS..."
mkdir -p $WORK/training $WORK/data $WORK/models

gcloud storage cp gs://$BUCKET/deploy/deepsets/train.py $WORK/training/train.py
gcloud storage cp gs://$BUCKET/deploy/deepsets/model_deepsets.py $WORK/training/model_deepsets.py
gcloud storage cp gs://$BUCKET/deploy/deepsets/export_weights_v2.py $WORK/training/export_weights_v2.py
gcloud storage cp gs://$BUCKET/deploy/deepsets/property_table.json $WORK/training/property_table.json

echo "Downloading HDF5 data..."
gcloud storage cp gs://$BUCKET/deploy/deepsets/$TRAIN_BASENAME $WORK/data/$TRAIN_BASENAME
gcloud storage cp gs://$BUCKET/deploy/deepsets/$VAL_BASENAME $WORK/data/$VAL_BASENAME

echo "Download complete."

# Count records
TOTAL_N=$(python3 -c "
import h5py
with h5py.File('$WORK/data/$TRAIN_BASENAME', 'r') as h:
    print(h['label_A'].shape[0])
")
echo "Dataset: $TOTAL_N training records (human replays, 1500+ rated, no 6s bullet)"

# Upload run config
GCS_PREFIX="training-runs/$LABEL/$RUN_ID"
cat > /tmp/run_config.json <<CONFIGEOF
{
  "run_id": "$RUN_ID",
  "label": "$LABEL",
  "model": "deepsets",
  "mode": "streaming",
  "platform": "gcp",
  "data": "human_1500_no6s (97,317 games, both players 1500+, no 6s bullet)",
  "lr": $LR,
  "epochs": $EPOCHS,
  "batch_size": $BATCH_SIZE,
  "patience": $PATIENCE,
  "max_records": $MAX_RECORDS,
  "seed": $SEED,
  "total_records": $TOTAL_N,
  "machine_type": "$(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/machine-type | awk -F/ '{print $NF}')"
}
CONFIGEOF
gcloud storage cp /tmp/run_config.json gs://$BUCKET/$GCS_PREFIX/run_config.json

# Build training command
echo ""
echo "=== Starting DeepSets training (streaming mode) ==="
cd $WORK

TRAIN_CMD="python3 training/train.py \
  --model deepsets \
  --train-file data/$TRAIN_BASENAME \
  --val-file data/$VAL_BASENAME \
  --property-table training/property_table.json \
  --output-dir models \
  --streaming \
  --epochs $EPOCHS \
  --batch-size $BATCH_SIZE \
  --lr $LR \
  --patience $PATIENCE \
  --num-workers 0 \
  --seed $SEED \
  --device cuda"

if [ $MAX_RECORDS -gt 0 ]; then
  TRAIN_CMD="$TRAIN_CMD --max-records $MAX_RECORDS"
fi

echo "Command: $TRAIN_CMD"
echo ""

# Background checkpoint sync every 5 min
(
  while true; do
    sleep 300
    if [ -d models ]; then
      gcloud storage rsync models/ gs://$BUCKET/$GCS_PREFIX/models/ --quiet 2>/dev/null
    fi
    gcloud storage cp training_output.log gs://$BUCKET/$GCS_PREFIX/training_output.log --quiet 2>/dev/null
    echo "[sync] Checkpoints uploaded to GCS at $(date)"
  done
) &
SYNC_PID=$!
echo "Background GCS sync started (PID $SYNC_PID, every 5 min)"

eval $TRAIN_CMD 2>&1 | tee training_output.log
TRAIN_EXIT=$?

kill $SYNC_PID 2>/dev/null || true

echo ""
echo "Training exited with code: $TRAIN_EXIT"

# Upload final results
echo "Uploading final results to GCS..."
gcloud storage rsync models/ gs://$BUCKET/$GCS_PREFIX/models/

# Export weights to DSN2 binary format
echo "Exporting DeepSets weights to DSN2 format..."
if [ -f models/best_model.pt ]; then
  python3 training/export_weights_v2.py models/best_model.pt models/neural_weights.bin \
    --property-table training/property_table.json
  gcloud storage cp models/neural_weights.bin gs://$BUCKET/$GCS_PREFIX/neural_weights.bin
  echo "Weights exported and uploaded."
else
  echo "WARNING: No best_model.pt found!"
fi

gcloud storage cp training_output.log gs://$BUCKET/$GCS_PREFIX/training_output.log
gcloud storage cp $LOG gs://$BUCKET/$GCS_PREFIX/boot.log

echo ""
echo "=== DeepSets Training complete (HUMAN REPLAYS, GCP) ==="
echo "Results at: gs://$BUCKET/$GCS_PREFIX/"
date

echo "Training script complete. Exiting..."
ENDSCRIPT
)

# Do placeholder substitution
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_BUCKET/$BUCKET}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_LABEL/$LABEL}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_LR/$LR}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_EPOCHS/$EPOCHS}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_BATCH_SIZE/$BATCH_SIZE}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_PATIENCE/$PATIENCE}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_MAX_RECORDS/$MAX_RECORDS}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_SEED/$SEED}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_TRAIN_BASENAME/$TRAIN_BASENAME}"
STARTUP_SCRIPT="${STARTUP_SCRIPT//PLACEHOLDER_VAL_BASENAME/$VAL_BASENAME}"

if [ "$DRY_RUN" = "true" ]; then
  echo "=== DRY RUN - Startup script: ==="
  echo "$STARTUP_SCRIPT"
  exit 0
fi

# Write startup script to temp file
STARTUP_FILE="c:/libraries/PrismataAI/gcp/.startup_human_tmp.sh"
mkdir -p "$(dirname "$STARTUP_FILE")"
echo "$STARTUP_SCRIPT" > "$STARTUP_FILE"

echo "Launching GCP instance: $INSTANCE_NAME"
echo ""

$GCLOUD compute instances create "$INSTANCE_NAME" \
  --project="$PROJECT" \
  --zone="$ZONE" \
  --machine-type="$MACHINE_TYPE" \
  --accelerator="type=nvidia-l4,count=1" \
  --image-family="$IMAGE_FAMILY" \
  --image-project="$IMAGE_PROJECT" \
  --boot-disk-size=100GB \
  --boot-disk-type=pd-balanced \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --maintenance-policy=TERMINATE \
  --scopes=storage-full \
  --metadata=install-nvidia-driver=True \
  --metadata-from-file=startup-script="$STARTUP_FILE" \
  --no-restart-on-failure

LAUNCH_EXIT=$?
rm -f "$STARTUP_FILE"

if [ $LAUNCH_EXIT -ne 0 ]; then
  echo "ERROR: Instance launch failed!"
  exit 1
fi

echo ""
echo "=== DeepSets Training Instance Launched (HUMAN REPLAYS, GCP) ==="
echo "  Instance:   $INSTANCE_NAME"
echo "  Type:       $MACHINE_TYPE (1x NVIDIA L4, 32GB RAM)"
echo "  Zone:       $ZONE"
echo "  Label:      $LABEL"
echo "  Data:       human_1500_no6s_v2.h5 (~2.5M records, 97K games)"
echo "  Pricing:    Spot (~\$0.35/hr)"
echo ""
echo "The instance will:"
echo "  1. Boot Ubuntu 22.04 + PyTorch 2.7 + CUDA 12.8 (~2 min)"
echo "  2. Download human replay HDF5 from GCS (~30s, same region)"
echo "  3. Train DeepSets on NVIDIA L4 GPU (streaming, lr=$LR)"
echo "  4. Export weights to DSN2 binary format"
echo "  5. Upload model + metrics to gs://$BUCKET/training-runs/$LABEL/"
echo "  6. Auto-delete instance (no ongoing charges)"
echo ""
echo "Monitor:"
echo "  $GCLOUD compute instances describe $INSTANCE_NAME --zone=$ZONE --format='value(status)'"
echo ""
echo "Console output:"
echo "  $GCLOUD compute instances get-serial-port-output $INSTANCE_NAME --zone=$ZONE"
echo ""
echo "SSH (if needed):"
echo "  $GCLOUD compute ssh $INSTANCE_NAME --zone=$ZONE"
echo ""
echo "Download results when done:"
echo "  $GCLOUD storage rsync gs://$BUCKET/training-runs/$LABEL/ training/cloud-runs/$LABEL/"
