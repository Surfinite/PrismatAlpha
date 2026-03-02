#!/bin/bash
# Download and aggregate MCDSAI matchup results from S3
# Usage: bash aws/aggregate_matchup_results.sh [RUN_PREFIX]
#
# Examples:
#   bash aws/aggregate_matchup_results.sh                                    # all matchup results
#   bash aws/aggregate_matchup_results.sh matchup-results/matchup_2026-03-01  # specific run prefix

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
PREFIX="${1:-matchup-results/}"
LOCAL_DIR="matchup_results_tmp"

echo "=== Downloading Matchup Results ==="
echo "  Bucket:  s3://$BUCKET/$PREFIX"
echo "  Region:  $REGION"
echo ""

# Download all summary files
mkdir -p "$LOCAL_DIR"
aws s3 sync "s3://$BUCKET/$PREFIX" "$LOCAL_DIR/" \
    --region "$REGION" --exclude "*" --include "*/summary_*.json"

# Count what we got
SUMMARY_COUNT=$(find "$LOCAL_DIR" -name "summary_*.json" 2>/dev/null | wc -l)
if [ "$SUMMARY_COUNT" -eq 0 ]; then
    echo ""
    echo "No summary_*.json files found under s3://$BUCKET/$PREFIX"
    echo "Check that matchup workers have completed and synced results."
    rm -rf "$LOCAL_DIR"
    exit 1
fi

echo ""
echo "Found $SUMMARY_COUNT summary files."
echo ""

# Aggregate with Python (Wilson 95% CI)
python -c "
import json, glob, os, math

summaries = sorted(glob.glob('$LOCAL_DIR/**/summary_*.json', recursive=True))

total = {'mcdsai_wins': 0, 'cpp_wins': 0, 'draws': 0, 'total': 0, 'failed': 0}
cpp_player = None
mcdsai_diff = None
think_time = None

print('Per-worker results:')
for f in summaries:
    with open(f) as fh:
        d = json.load(fh)
    for k in total:
        total[k] += d.get(k, 0)
    # Track config from first file
    if cpp_player is None:
        cpp_player = d.get('cpp_player', 'unknown')
        mcdsai_diff = d.get('mcdsai_difficulty', 'unknown')
        think_time = d.get('think_time_ms', 'unknown')
    run_dir = os.path.basename(os.path.dirname(f))
    worker = os.path.basename(f)
    print(f'  {run_dir}/{worker}: MCDSAI {d[\"mcdsai_wins\"]}, C++ {d[\"cpp_wins\"]}, draws {d[\"draws\"]}, total {d[\"total\"]}')

completed = total['total']
if completed == 0:
    print()
    print('No completed games found.')
    exit(0)

wr = total['mcdsai_wins'] / completed * 100
cpp_wr = total['cpp_wins'] / completed * 100

# Wilson 95% CI for MCDSAI win rate
z = 1.96
p = total['mcdsai_wins'] / completed
n = completed
denom = 1 + z*z/n
center = (p + z*z/(2*n)) / denom
margin = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n) / denom
lo = max(0, center - margin) * 100
hi = min(1, center + margin) * 100

# Wilson 95% CI for C++ win rate
p2 = total['cpp_wins'] / completed
center2 = (p2 + z*z/(2*n)) / denom
margin2 = z * math.sqrt((p2*(1-p2) + z*z/(4*n)) / n) / denom
lo2 = max(0, center2 - margin2) * 100
hi2 = min(1, center2 + margin2) * 100

print()
print('=== Aggregate Matchup Results ===')
print(f'MCDSAI ({mcdsai_diff}) vs C++ ({cpp_player}), {think_time}ms think')
print(f'')
print(f'MCDSAI wins:  {total[\"mcdsai_wins\"]:>5}  ({wr:.1f}%)  Wilson 95% CI: [{lo:.1f}%, {hi:.1f}%]')
print(f'C++ wins:     {total[\"cpp_wins\"]:>5}  ({cpp_wr:.1f}%)  Wilson 95% CI: [{lo2:.1f}%, {hi2:.1f}%]')
print(f'Draws:        {total[\"draws\"]:>5}')
print(f'Total:        {completed:>5}  ({total[\"failed\"]} failed)')
"

# Cleanup
rm -rf "$LOCAL_DIR"
