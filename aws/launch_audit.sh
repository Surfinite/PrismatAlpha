#!/bin/bash
# Launch c5.xlarge EC2 spot instance for self-play data integrity audit
# Usage: bash aws/launch_audit.sh
#
# Options (via env vars):
#   DRY_RUN=true    Print userdata script without launching (default: false)
#   INSTANCE_TYPE=c5.xlarge  Instance type (default: c5.xlarge, 4 vCPU, 8GB RAM)
#
# Prerequisites:
#   - Deploy audit script: aws s3 cp tools/audit_selfplay_s3.py s3://$CLOUD_BUCKET/deploy/tools/audit_selfplay_s3.py --region $AWS_REGION

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

# Infrastructure
INSTANCE_TYPE="${INSTANCE_TYPE:-c5.xlarge}"
DRY_RUN="${DRY_RUN:-false}"
REGION="${AWS_REGION:-eu-north-1}"
AMI="${AWS_AMI_DL_PYTORCH:?Set AWS_AMI_DL_PYTORCH in cloud-config.env}"
KEY_NAME="${AWS_KEY_NAME:?Set AWS_KEY_NAME in cloud-config.env}"
SG_ID="${AWS_SG_ID:?Set AWS_SG_ID in cloud-config.env}"
PROFILE="${AWS_IAM_PROFILE:?Set AWS_IAM_PROFILE in cloud-config.env}"
BUCKET="${CLOUD_BUCKET:?Set CLOUD_BUCKET in cloud-config.env}"

echo "=== Prismata Self-Play Data Audit Launch ==="
echo "  Instance:  $INSTANCE_TYPE"
echo "  Region:    $REGION"
echo "  Spot:      yes (one-time, terminate)"
echo "  Disk:      20 GB gp3 (default)"
echo "  Est. cost: <\$0.10 (~30 min)"
echo ""

# Build userdata script
USERDATA=$(cat <<'ENDSCRIPT'
#!/bin/bash
set -eo pipefail

BUCKET="__CLOUD_BUCKET__"
REGION="__AWS_REGION__"
LOG="/tmp/audit_boot.log"

exec > >(tee -a "$LOG") 2>&1

echo "=== Prismata Self-Play Audit Worker Starting ==="
IMDS_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300" 2>/dev/null || true)
echo "Instance: $(curl -s -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo unknown)"
date

# Setup Python environment (DL AMI has venv at /opt/pytorch/)
echo "Setting up Python..."
export PATH="/opt/pytorch/bin:$PATH"
pip install boto3 tqdm --quiet 2>/dev/null || true

# Download audit script
echo "Downloading audit script from S3..."
aws s3 cp s3://$BUCKET/deploy/tools/audit_selfplay_s3.py /tmp/audit.py --region $REGION

# Run audit
echo "Starting audit..."
cd /tmp
python audit.py --output /tmp/audit_report.json 2>&1 | tee audit_output.log
AUDIT_EXIT=$?

echo "Audit exited with code: $AUDIT_EXIT"

# Upload results
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
echo "Uploading results to S3..."
aws s3 cp /tmp/audit_report.json s3://$BUCKET/audit-results/audit_${TIMESTAMP}.json --region $REGION
aws s3 cp /tmp/audit_output.log s3://$BUCKET/audit-results/audit_${TIMESTAMP}.log --region $REGION
aws s3 cp $LOG s3://$BUCKET/audit-results/audit_${TIMESTAMP}_boot.log --region $REGION

echo ""
echo "=== Audit complete ==="
echo "Results at: s3://$BUCKET/audit-results/audit_${TIMESTAMP}.*"
date

# Self-terminate
echo "Shutting down..."
sudo shutdown -h now
ENDSCRIPT
)

# Inject sourced config values into userdata (heredoc is single-quoted to protect shell syntax)
USERDATA="${USERDATA/__CLOUD_BUCKET__/$BUCKET}"
USERDATA="${USERDATA/__AWS_REGION__/$REGION}"

if [ "$DRY_RUN" = "true" ]; then
  echo "=== DRY RUN - Userdata script: ==="
  echo "$USERDATA"
  exit 0
fi

# Write userdata to temp file
USERDATA_FILE="c:/libraries/PrismataAI/aws/.userdata_audit_tmp.sh"
echo "$USERDATA" > "$USERDATA_FILE"

# Base64 encode for spot request API
USERDATA_B64=$(base64 -w0 "$USERDATA_FILE")

echo "Launching spot instance..."

# Write launch spec JSON
SPEC_FILE="c:/libraries/PrismataAI/aws/.spot_spec_audit_tmp.json"
cat > "$SPEC_FILE" <<SPECEOF
{
  "ImageId": "$AMI",
  "InstanceType": "$INSTANCE_TYPE",
  "KeyName": "$KEY_NAME",
  "SecurityGroupIds": ["$SG_ID"],
  "IamInstanceProfile": {"Name": "$PROFILE"},
  "UserData": "$USERDATA_B64"
}
SPECEOF

SPOT_REQ_ID=$(MSYS_NO_PATHCONV=1 aws ec2 request-spot-instances \
  --instance-count 1 \
  --type "one-time" \
  --instance-interruption-behavior terminate \
  --launch-specification "file://$SPEC_FILE" \
  --query 'SpotInstanceRequests[0].SpotInstanceRequestId' \
  --output text \
  --region "$REGION" 2>&1)
rm -f "$SPEC_FILE"

if [[ "$SPOT_REQ_ID" != sir-* ]]; then
  echo "ERROR: Spot request failed: $SPOT_REQ_ID"
  rm -f "$USERDATA_FILE"
  exit 1
fi

echo "  Spot request: $SPOT_REQ_ID"
echo "  Waiting for fulfillment (up to 5 min)..."

# Poll for fulfillment
for i in $(seq 1 30); do
  sleep 10
  STATUS=$(aws ec2 describe-spot-instance-requests \
    --spot-instance-request-ids "$SPOT_REQ_ID" \
    --query 'SpotInstanceRequests[0].[State,Status.Code,InstanceId]' \
    --output text --region "$REGION" 2>&1)
  STATE=$(echo "$STATUS" | awk '{print $1}')
  CODE=$(echo "$STATUS" | awk '{print $2}')
  INSTANCE_ID=$(echo "$STATUS" | awk '{print $3}')

  if [ "$STATE" = "active" ] && [[ "$INSTANCE_ID" == i-* ]]; then
    echo "  Fulfilled! Instance: $INSTANCE_ID"
    aws ec2 create-tags --resources "$INSTANCE_ID" \
      --tags "Key=Name,Value=PrismataAudit" \
      --region "$REGION" 2>/dev/null
    break
  elif [ "$STATE" = "closed" ] || [ "$STATE" = "cancelled" ] || [ "$STATE" = "failed" ]; then
    echo "  Spot request $STATE: $CODE"
    INSTANCE_ID=""
    break
  fi
  echo "  [$i/30] Status: $STATE ($CODE)..."
done

rm -f "$USERDATA_FILE"

if [[ "$INSTANCE_ID" != i-* ]]; then
  echo "ERROR: Spot request not fulfilled within 5 min."
  echo "  Cancel with: aws ec2 cancel-spot-instance-requests --spot-instance-request-ids $SPOT_REQ_ID --region $REGION"
  exit 1
fi

echo ""
echo "=== Audit Instance Launched ==="
echo "  Instance ID: $INSTANCE_ID"
echo "  Type:        $INSTANCE_TYPE"
echo ""
echo "The instance will:"
echo "  1. Boot Amazon Linux 2023 + Python (~2 min)"
echo "  2. Download audit script from S3"
echo "  3. Stream and validate all ~7,756 shards (~30 min)"
echo "  4. Upload JSON report to s3://$BUCKET/audit-results/"
echo "  5. Auto-terminate (cost: <\$0.10)"
echo ""
echo "Monitor:"
echo "  aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].State.Name' --region $REGION"
echo ""
echo "SSH (if needed):"
echo "  aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --region $REGION"
echo "  ssh -i ~/.ssh/prismata-selfplay.pem ec2-user@<IP>"
echo ""
echo "Download results when done:"
echo "  aws s3 ls s3://$BUCKET/audit-results/ --region $REGION"
echo "  aws s3 cp s3://$BUCKET/audit-results/audit_LATEST.json . --region $REGION"
