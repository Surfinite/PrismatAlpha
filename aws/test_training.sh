#!/bin/bash
set -eo pipefail
export PATH="/opt/pytorch/bin:$PATH"
cd /home/ec2-user/training

# Get unit_index.json
echo "=== Downloading unit_index.json ==="
aws s3 cp s3://$BUCKET/deploy/training/unit_index.json /home/ec2-user/training/data/unit_index.json --region $REGION
ls -la data/unit_index.json

# Count records
echo "=== Counting records ==="
RECORD_COUNT=$(python -c "
import os
base = '/home/ec2-user/training/selfplay_data'
total = sum(
    (os.path.getsize(os.path.join(r, f)) - 68) // 7152
    for r, _, fs in os.walk(base)
    for f in fs
    if f.endswith('.bin') and os.path.getsize(os.path.join(r, f)) > 68
)
print(total)
")
echo "Records: $RECORD_COUNT (~$((RECORD_COUNT / 37)) games)"

# Start training with small max-records for quick test
echo "=== Starting training (3 epochs, 10K records, CUDA) ==="
python training/train.py data models \
  --selfplay-dir selfplay_data \
  --value-only \
  --hidden-dim 256 \
  --lr 1e-5 \
  --epochs 3 \
  --batch-size 512 \
  --max-records 10000 \
  --num-workers 4 \
  --streaming \
  --device cuda 2>&1

echo "=== Training complete ==="
echo "Checking model output..."
ls -la models/
echo "=== Exporting weights ==="
if [ -f models/best_model.pt ]; then
  python training/export_weights.py models/best_model.pt models/neural_weights.bin
  ls -la models/neural_weights.bin
  echo "Export SUCCESS"
else
  echo "WARNING: No best_model.pt found!"
fi
