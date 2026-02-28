#!/bin/bash
# Deploy JS self-play engine files to S3
# Run this before launching JS self-play instances.

export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

BUCKET="prismata-selfplay-data"
REGION="eu-north-1"
BASE="c:/libraries/PrismataAI"

echo "=== Deploying JS Self-Play Engine to S3 ==="

# JS engine files (all .js in js_engine/)
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

# MCDSAI module (1.8 MB)
echo "Uploading MCDSAI3441.js ..."
aws s3 cp "$BASE/tmp_browser_client/MCDSAI3441.js" \
    "s3://$BUCKET/deploy/tmp_browser_client/MCDSAI3441.js" \
    --region "$REGION"

# AI params (SWF-extracted)
echo "Uploading AI params ..."
aws s3 cp "$BASE/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" \
    "s3://$BUCKET/deploy/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" \
    --region "$REGION"
aws s3 cp "$BASE/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" \
    "s3://$BUCKET/deploy/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" \
    --region "$REGION"

# Card library
echo "Uploading cardLibrary.jso ..."
aws s3 cp "$BASE/bin/asset/config/cardLibrary.jso" \
    "s3://$BUCKET/deploy/asset/config/cardLibrary.jso" \
    --region "$REGION"

echo ""
echo "=== Deploy Complete ==="
echo "Verify:"
echo "  aws s3 ls s3://$BUCKET/deploy/js_engine/ --region $REGION | wc -l"
echo "  aws s3 ls s3://$BUCKET/deploy/tmp_browser_client/ --region $REGION"
