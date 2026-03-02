#!/bin/bash
# Deploy both C++ tournament files AND JS engine files to S3.
# Combines deploy_for_eval.sh + deploy_js_selfplay.sh for matchup runs
# that need both engines available.

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

BUCKET="${CLOUD_BUCKET:?Set CLOUD_BUCKET in cloud-config.env}"
REGION="${AWS_REGION:-eu-north-1}"
BASE="c:/libraries/PrismataAI"

echo "=== Deploying C++ + JS Engine to S3 for Matchup ==="

# --- C++ tournament files (from deploy_for_eval.sh) ---

echo "Uploading Prismata_Testing.exe..."
aws s3 cp "$BASE/bin/Prismata_Testing.exe" "s3://$BUCKET/deploy/Prismata_Testing.exe" --region "$REGION"

echo "Uploading config.txt..."
aws s3 cp "$BASE/bin/asset/config/config.txt" "s3://$BUCKET/deploy/asset/config/config.txt" --region "$REGION"

echo "Uploading cardLibrary.jso..."
aws s3 cp "$BASE/bin/asset/config/cardLibrary.jso" "s3://$BUCKET/deploy/asset/config/cardLibrary.jso" --region "$REGION"

echo "Uploading neural_weights.bin..."
aws s3 cp "$BASE/bin/asset/config/neural_weights.bin" "s3://$BUCKET/deploy/asset/config/neural_weights.bin" --region "$REGION"

# --- JS engine files (from deploy_js_selfplay.sh) ---

echo "Uploading js_engine/ ..."
aws s3 sync "$BASE/js_engine/" "s3://$BUCKET/deploy/js_engine/" \
    --region "$REGION" \
    --exclude "*" \
    --include "*.js" \
    --exclude "test_*.js" \
    --exclude "benchmark_*.jsonl" \
    --exclude "*.jsonl" \
    --exclude "*.json" \
    --exclude "*.txt" \
    --exclude "*.log" \
    --delete

echo "Uploading MCDSAI3441.js ..."
aws s3 cp "$BASE/tmp_browser_client/MCDSAI3441.js" \
    "s3://$BUCKET/deploy/tmp_browser_client/MCDSAI3441.js" \
    --region "$REGION"

echo "Uploading AI params ..."
aws s3 cp "$BASE/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" \
    "s3://$BUCKET/deploy/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" \
    --region "$REGION"
aws s3 cp "$BASE/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" \
    "s3://$BUCKET/deploy/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" \
    --region "$REGION"

echo ""
echo "=== Deploy Complete ==="
echo "Verify:"
echo "  aws s3 ls s3://$BUCKET/deploy/Prismata_Testing.exe --region $REGION"
echo "  aws s3 ls s3://$BUCKET/deploy/asset/config/ --region $REGION"
echo "  aws s3 ls s3://$BUCKET/deploy/js_engine/ --region $REGION | wc -l"
echo "  aws s3 ls s3://$BUCKET/deploy/tmp_browser_client/ --region $REGION"
echo "  aws s3 ls s3://$BUCKET/deploy/tmp_swf_extract/ --region $REGION"
