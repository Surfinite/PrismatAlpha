#!/bin/bash
# Smoke test: run 10 heuristic-vs-heuristic games via the fixed set test.
# Verifies: no crash (exit code 0), reasonable output.
#
# Usage: bash scripts/smoke_test.sh [--legacy]
#
# Requires: Prismata_Testing.exe built and in bin/

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BIN_DIR="$PROJECT_DIR/bin"

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
    echo "Build the solution first: MSBuild visualstudio/Prismata.sln"
    exit 1
fi

echo "=== Smoke Test ==="
echo "Executable: $EXE"
echo "Working dir: $BIN_DIR"

# Determine which flag to use
FLAG="--fixedset"
if [ "$1" = "--legacy" ]; then
    FLAG="--fixedset-legacy"
    echo "Mode: Legacy (OriginalHardestAI)"
else
    echo "Mode: Improved (HardestAI)"
fi

# Run the fixed set test (10 games of AI vs itself)
echo ""
echo "Running 10 fixed-set games..."
cd "$BIN_DIR"
OUTPUT=$("$EXE" "$FLAG" 2>&1) || {
    echo "FAIL: Executable crashed (exit code $?)"
    echo "Output:"
    echo "$OUTPUT"
    exit 1
}

echo "$OUTPUT"

# Basic sanity checks on output
echo ""
echo "--- Sanity Checks ---"

# Check that some games were played (look for turn/buy output)
TURN_LINES=$(echo "$OUTPUT" | grep -c "Turn" || true)
if [ "$TURN_LINES" -lt 5 ]; then
    echo "WARNING: Only $TURN_LINES turn lines found (expected >= 5)"
fi

# Check no assertion failures
ASSERT_COUNT=$(echo "$OUTPUT" | grep -ci "assert\|abort\|segfault\|exception" || true)
if [ "$ASSERT_COUNT" -gt 0 ]; then
    echo "FAIL: Found assertion/crash indicators in output"
    exit 1
fi

echo "Smoke test PASSED"
echo "  Games ran without crashes"
echo "  Turn lines found: $TURN_LINES"
