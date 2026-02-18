#!/bin/bash
# Tournament harness: run N games between two AI players.
#
# This script modifies config.txt to enable a tournament benchmark,
# runs the testing executable, and parses results into CSV.
#
# Usage:
#   bash scripts/tournament.sh [OPTIONS]
#
# Options:
#   --p1 NAME       Player 1 name (default: HardestAI)
#   --p2 NAME       Player 2 name (default: OriginalHardestAI)
#   --games N       Number of rounds (default: 200)
#   --cards N       Random cards per game (default: 8)
#   --output FILE   CSV output path (default: scripts/tournament_results.csv)
#
# Requires: Prismata_Testing.exe built and in bin/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$PROJECT_DIR/bin"
CONFIG="$BIN_DIR/asset/config/config.txt"

# Defaults
P1="HardestAI"
P2="OriginalHardestAI"
GAMES=200
CARDS=8
OUTPUT="$SCRIPT_DIR/tournament_results.csv"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --p1) P1="$2"; shift 2;;
        --p2) P2="$2"; shift 2;;
        --games) GAMES="$2"; shift 2;;
        --cards) CARDS="$2"; shift 2;;
        --output) OUTPUT="$2"; shift 2;;
        *) echo "Unknown option: $1"; exit 1;;
    esac
done

# Find testing executable
EXE=""
for candidate in "$BIN_DIR/Prismata_Testing.exe" "$BIN_DIR/Prismata_Testing_d.exe" "$BIN_DIR/Prismata_Testing"; do
    if [ -f "$candidate" ]; then
        EXE="$candidate"
        break
    fi
done

if [ -z "$EXE" ]; then
    echo "ERROR: Cannot find Prismata_Testing executable in $BIN_DIR"
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: Config file not found: $CONFIG"
    exit 1
fi

echo "=== Tournament Harness ==="
echo "  Player 1:    $P1"
echo "  Player 2:    $P2"
echo "  Games:       $GAMES"
echo "  Random cards: $CARDS"
echo "  Output:      $OUTPUT"
echo "  Executable:  $EXE"
echo ""

# Backup config
cp "$CONFIG" "$CONFIG.bak"

# Create a temporary tournament entry by modifying config
# We replace the NeuralTest tournament entry (or append if not found)
TOURNAMENT_JSON="{ \"run\":true, \"type\":\"Tournament\", \"name\":\"ScriptTournament\", \"rounds\":$GAMES, \"UpdateIntervalSec\":5, \"RandomCards\":$CARDS, \"players\":[ {\"name\":\"$P1\",\"group\":1}, {\"name\":\"$P2\",\"group\":2}] }"

# Disable all existing benchmarks and enable ours
# We use python for reliable JSON manipulation
python -c "
import json, sys, re

with open('$CONFIG', 'r') as f:
    content = f.read()

# Find the Benchmarks array and disable all entries, then add ours
# Simple approach: replace all '\"run\":true' with '\"run\":false' in the Benchmarks section
content = re.sub(r'\"run\"\s*:\s*true', '\"run\":false', content)

# Insert our tournament before the last ] in the Benchmarks array
# Find the last benchmark entry
last_bracket = content.rfind(']')
if last_bracket > 0:
    # Insert before the closing bracket
    content = content[:last_bracket] + ',\n    $TOURNAMENT_JSON\n  ' + content[last_bracket:]

with open('$CONFIG', 'w') as f:
    f.write(content)

print('Config updated with tournament entry')
" 2>&1 || {
    echo "ERROR: Failed to modify config"
    cp "$CONFIG.bak" "$CONFIG"
    exit 1
}

# Run tournament
echo "Running tournament ($GAMES games)..."
cd "$BIN_DIR"
TOURNAMENT_OUTPUT=$("$EXE" 2>&1) || {
    echo "WARNING: Executable returned non-zero exit code"
}

# Restore config
cp "$CONFIG.bak" "$CONFIG"
rm -f "$CONFIG.bak"

echo "$TOURNAMENT_OUTPUT"

# Parse results
echo ""
echo "--- Results ---"

# Extract win counts from tournament output
# The tournament output typically looks like:
# Tournament Results:
#   PlayerName wins: X / N
P1_WINS=$(echo "$TOURNAMENT_OUTPUT" | grep -oP "$P1.*?(\d+)\s*/\s*(\d+)" | grep -oP '\d+\s*/\s*\d+' | head -1 | cut -d/ -f1 | tr -d ' ' || echo "0")
TOTAL=$(echo "$TOURNAMENT_OUTPUT" | grep -oP "$P1.*?(\d+)\s*/\s*(\d+)" | grep -oP '\d+\s*/\s*\d+' | head -1 | cut -d/ -f2 | tr -d ' ' || echo "$GAMES")

if [ -z "$P1_WINS" ] || [ "$P1_WINS" = "0" ] && [ "$TOTAL" = "$GAMES" ]; then
    echo "Could not parse detailed results from output."
    echo "Check the raw output above for tournament results."
    echo ""
    echo "Tournament output saved to: $SCRIPT_DIR/tournament_output.txt"
    echo "$TOURNAMENT_OUTPUT" > "$SCRIPT_DIR/tournament_output.txt"
else
    P2_WINS=$((TOTAL - P1_WINS))
    WIN_RATE=$(python -c "print(f'{$P1_WINS/$TOTAL:.1%}')" 2>/dev/null || echo "N/A")

    # Wilson confidence interval (95%)
    WILSON=$(python -c "
import math
n = $TOTAL
p = $P1_WINS / n if n > 0 else 0.5
z = 1.96  # 95% CI
denom = 1 + z**2/n
center = (p + z**2/(2*n)) / denom
margin = z * math.sqrt((p*(1-p) + z**2/(4*n)) / n) / denom
print(f'{center:.1%} [{center-margin:.1%}, {center+margin:.1%}]')
" 2>/dev/null || echo "N/A")

    echo "  $P1 wins: $P1_WINS / $TOTAL ($WIN_RATE)"
    echo "  $P2 wins: $P2_WINS / $TOTAL"
    echo "  95% Wilson CI: $WILSON"

    # Write CSV header + result
    echo "game_id,p1_type,p2_type,winner,num_turns" > "$OUTPUT"
    echo "summary,$P1,$P2,$P1_WINS/$TOTAL,-" >> "$OUTPUT"

    echo ""
    echo "Results saved to: $OUTPUT"
fi

echo "$TOURNAMENT_OUTPUT" > "$SCRIPT_DIR/tournament_output.txt"
echo "Full output saved to: $SCRIPT_DIR/tournament_output.txt"
