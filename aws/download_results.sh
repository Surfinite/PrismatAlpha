#!/bin/bash
# Download self-play results from S3 to local training data directory
export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

BUCKET="prismata-selfplay-data"
REGION="eu-north-1"
LOCAL_DIR="c:/libraries/PrismataAI/bin/training/data/selfplay"

echo "Downloading from s3://$BUCKET/results/ ..."
aws s3 sync "s3://$BUCKET/results/" "$LOCAL_DIR/" --region "$REGION"
echo ""
echo "Done. Files saved to: $LOCAL_DIR"
echo ""

# Show what we got
for d in "$LOCAL_DIR"/run_*/; do
  if [ -d "$d" ]; then
    count=$(ls "$d"*.bin 2>/dev/null | wc -l)
    total=$(python -c "import os,glob; print(sum(os.path.getsize(f) for f in glob.glob('${d}*.bin')))" 2>/dev/null)
    echo "  $(basename $d): $count shards, $total bytes"
  fi
done
