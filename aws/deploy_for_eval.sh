#!/bin/bash
# Upload exe, config, and neural weights to S3 for tournament evaluation
# Run this after rebuilding Prismata_Testing.exe with the latest code + weights
export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"

BUCKET="prismata-selfplay-data"
REGION="eu-north-1"
BIN_DIR="c:/libraries/PrismataAI/bin"

echo "=== Deploying to S3 for Tournament Evaluation ==="

echo "Uploading Prismata_Testing.exe..."
aws s3 cp "$BIN_DIR/Prismata_Testing.exe" "s3://$BUCKET/deploy/Prismata_Testing.exe" --region "$REGION"

echo "Uploading config.txt..."
aws s3 cp "$BIN_DIR/asset/config/config.txt" "s3://$BUCKET/deploy/asset/config/config.txt" --region "$REGION"

echo "Uploading cardLibrary.jso..."
aws s3 cp "$BIN_DIR/asset/config/cardLibrary.jso" "s3://$BUCKET/deploy/asset/config/cardLibrary.jso" --region "$REGION"

echo "Uploading neural_weights.bin..."
aws s3 cp "$BIN_DIR/asset/config/neural_weights.bin" "s3://$BUCKET/deploy/asset/config/neural_weights.bin" --region "$REGION"

echo ""
echo "=== Deploy complete ==="
echo "Now launch with: bash aws/launch_tournament.sh [INSTANCE_TYPE] [NUM_ROUNDS] [VM_MULTIPLIER]"
