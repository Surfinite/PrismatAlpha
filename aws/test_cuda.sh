#!/bin/bash
set -eo pipefail
export PATH="/opt/pytorch/bin:$PATH"
export PYTHONUNBUFFERED=1
cd /home/ec2-user/training

echo "=== CUDA Training Pipeline Test ==="
date

# Use two larger data directories (each should have many shards)
SUBSET1="selfplay_data/2026-02-15_12-09-27"
SUBSET2="selfplay_data/2026-02-15_12-09-28"
echo "Data dirs: $SUBSET1, $SUBSET2"

# Clean models from previous failed runs
rm -rf models/*

echo ""
echo "=== Starting training (2 epochs, batch=32, CUDA) ==="
python -u training/train.py data models \
  --selfplay-dir "$SUBSET1" \
  --value-only \
  --hidden-dim 256 \
  --lr 1e-5 \
  --epochs 2 \
  --batch-size 32 \
  --max-records 5000 \
  --streaming \
  --device cuda 2>&1

echo ""
echo "=== Models ==="
ls -la models/

if [ -f models/best_model.pt ]; then
  echo "=== Exporting weights ==="
  python -u training/export_weights.py models/best_model.pt models/neural_weights.bin
  ls -la models/neural_weights.bin
  echo ""
  echo "FULL PIPELINE TEST: SUCCESS"
  date
else
  echo "FULL PIPELINE TEST: FAILED - no best_model.pt"
fi
