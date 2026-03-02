#!/bin/bash
set -eo pipefail
export PATH="/opt/pytorch/bin:$PATH"
export PYTHONUNBUFFERED=1
cd /home/ec2-user/training

echo "=== Quick CUDA Training Test ==="
echo "Using subset of data to avoid long shard indexing..."

# Use a single subdirectory to limit shard count
SUBSET_DIR=$(find selfplay_data/ -maxdepth 1 -type d | head -2 | tail -1)
echo "Using data from: $SUBSET_DIR"
SHARD_COUNT=$(find "$SUBSET_DIR" -name "*.bin" | wc -l)
echo "Shards in subset: $SHARD_COUNT"

echo ""
echo "=== Starting training (3 epochs, 5K records, CUDA) ==="
python -u training/train.py data models \
  --selfplay-dir "$SUBSET_DIR" \
  --value-only \
  --hidden-dim 256 \
  --lr 1e-5 \
  --epochs 3 \
  --batch-size 512 \
  --max-records 5000 \
  --num-workers 2 \
  --streaming \
  --device cuda 2>&1

echo ""
echo "=== Training complete ==="
ls -la models/

if [ -f models/best_model.pt ]; then
  echo "=== Exporting weights ==="
  python training/export_weights.py models/best_model.pt models/neural_weights.bin
  ls -la models/neural_weights.bin
  echo "PIPELINE TEST: SUCCESS"
else
  echo "PIPELINE TEST: FAILED - no best_model.pt"
fi
