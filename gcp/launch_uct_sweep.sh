#!/bin/bash
# Launch GCP CPU instances for wide UCT unit sweep
# One instance per unit, embarrassingly parallel — finds winning lines for
# units the standard AI misplays by using deep search with relaxed limits.
#
# Usage:
#   bash gcp/launch_uct_sweep.sh --units "Blood Phage,Barrier,Electrovore"
#   bash gcp/launch_uct_sweep.sh --file gcp/sweep_units.txt
#   DRY_RUN=true bash gcp/launch_uct_sweep.sh --file gcp/sweep_units.txt
#   SKIP_UPLOAD=true bash gcp/launch_uct_sweep.sh --file gcp/sweep_units.txt
#
# Results land in:
#   gs://BUCKET/uct-sweep/LABEL/UNIT_NAME/results.jsonl
#   gs://BUCKET/uct-sweep/LABEL/UNIT_NAME/game.log
#
# Options (via env vars):
#   THINK_TIME=60000         Think time per turn in ms (default: 60000 = 60s)
#   MAX_TRAVERSALS=10000000  UCT max traversals (default: 10M)
#   MAX_CHILDREN=100         UCT max children per node (default: 100)
#   GAMES=12                 Games per unit (default: 12, with --player-switch)
#   PLAYER_WHITE=LiveHardestAI_UCT_Wide  White player (default: wide UCT)
#   PLAYER_BLACK=LiveHardestAI           Black player (default: standard AB)
#   MACHINE_TYPE=e2-standard-8  GCP machine type (default: e2-standard-8)
#   ZONE=us-central1-a       GCP zone (default: us-central1-a)
#   LABEL=uct-sweep          Run label for GCS output dir
#   DRY_RUN=false            Print commands without launching
#   SKIP_UPLOAD=false        Skip uploading files to GCS (already there)

GCLOUD="C:/google-cloud-sdk/bin/gcloud.cmd"

# Infrastructure
MACHINE_TYPE="${MACHINE_TYPE:-e2-standard-8}"
ZONE="${ZONE:-us-central1-a}"
PROJECT="prismata-selfplay"
BUCKET="prismata-selfplay-data"
DRY_RUN="${DRY_RUN:-false}"
SKIP_UPLOAD="${SKIP_UPLOAD:-false}"

# UCT settings
THINK_TIME="${THINK_TIME:-60000}"
MAX_TRAVERSALS="${MAX_TRAVERSALS:-10000000}"
MAX_CHILDREN="${MAX_CHILDREN:-100}"
GAMES="${GAMES:-12}"

# Players
PLAYER_WHITE="${PLAYER_WHITE:-LiveHardestAI_UCT_Wide}"
PLAYER_BLACK="${PLAYER_BLACK:-LiveHardestAI}"

# Label
LABEL="${LABEL:-uct-sweep-$(date +%m%d)}"

# ============================================================
# Parse --units or --file argument
# ============================================================
UNITS_CSV=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --units)
            UNITS_CSV="$2"
            shift 2
            ;;
        --file)
            if [ ! -f "$2" ]; then
                echo "ERROR: Units file not found: $2"
                exit 1
            fi
            # Read lines, strip comments and blanks, join with comma
            UNITS_CSV=$(grep -v '^\s*#' "$2" | grep -v '^\s*$' | paste -sd ',')
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: bash gcp/launch_uct_sweep.sh --units \"Unit1,Unit2\" | --file units.txt"
            exit 1
            ;;
    esac
done

if [ -z "$UNITS_CSV" ]; then
    echo "ERROR: No units specified. Use --units or --file."
    echo "Usage: bash gcp/launch_uct_sweep.sh --units \"Blood Phage,Barrier\" | --file gcp/sweep_units.txt"
    exit 1
fi

# Split CSV into array
IFS=',' read -ra UNITS <<< "$UNITS_CSV"
NUM_UNITS=${#UNITS[@]}

echo "=== Prismata UCT Wide Sweep (GCP) ==="
echo "  Units:          $NUM_UNITS"
echo "  Player white:   $PLAYER_WHITE"
echo "  Player black:   $PLAYER_BLACK"
echo "  Think time:     ${THINK_TIME}ms"
echo "  Max traversals: $MAX_TRAVERSALS"
echo "  Max children:   $MAX_CHILDREN"
echo "  Games per unit: $GAMES (with player-switch)"
echo "  Machine:        $MACHINE_TYPE"
echo "  Zone:           $ZONE"
echo "  Label:          $LABEL"
echo "  Spot:           yes (preemptible)"
echo ""
echo "  Units:"
for u in "${UNITS[@]}"; do
    echo "    - $u"
done
echo ""

# ============================================================
# Step 1: Upload engine files and JS engine to GCS
# ============================================================
if [ "$SKIP_UPLOAD" = "true" ]; then
    echo "=== Skipping upload (SKIP_UPLOAD=true) ==="
else
    echo "=== Uploading engine files to GCS ==="

    echo "  Uploading Prismata_Testing.exe (x64)..."
    $GCLOUD storage cp bin/Prismata_Testing.exe gs://$BUCKET/deploy/uct-sweep/Prismata_Testing.exe

    echo "  Uploading config and card library..."
    $GCLOUD storage cp bin/asset/config/config.txt gs://$BUCKET/deploy/uct-sweep/config/config.txt
    $GCLOUD storage cp bin/asset/config/cardLibrary.jso gs://$BUCKET/deploy/uct-sweep/config/cardLibrary.jso

    echo "  Uploading neural weight files..."
    for wf in bin/asset/config/neural_weights*.bin; do
        [ -f "$wf" ] && $GCLOUD storage cp "$wf" gs://$BUCKET/deploy/uct-sweep/config/$(basename "$wf")
    done

    echo "  Uploading unit index..."
    $GCLOUD storage cp training/data/unit_index.json gs://$BUCKET/deploy/uct-sweep/unit_index.json

    echo "  Uploading JS engine..."
    $GCLOUD storage cp js_engine/matchup_clean.js   gs://$BUCKET/deploy/uct-sweep/js/matchup_clean.js
    $GCLOUD storage cp js_engine/matchup_worker.js  gs://$BUCKET/deploy/uct-sweep/js/matchup_worker.js
    $GCLOUD storage cp js_engine/steam_ai.js        gs://$BUCKET/deploy/uct-sweep/js/steam_ai.js

    # Upload the full JS engine directory (transpiled game logic)
    $GCLOUD storage rsync js_engine/ gs://$BUCKET/deploy/uct-sweep/js/ \
        --exclude "*.log" --exclude "*.json.gz" --exclude "test_replays/*" --quiet

    echo "  Upload complete."
fi
echo ""

# ============================================================
# Step 2: Add LiveHardestAI_UCT_Wide to config if not present
# ============================================================
if ! grep -q "LiveHardestAI_UCT_Wide" bin/asset/config/config.txt; then
    echo "WARNING: LiveHardestAI_UCT_Wide not found in config.txt"
    echo "Add this entry to config.txt before running:"
    echo '  "LiveHardestAI_UCT_Wide": { "type":"Player_UCT", "TimeLimit":60000, "MaxChildren":100, "MaxTraversals":10000000, "RootMoveIterator":"LiveHardestAI_Root", "MoveIterator":"LiveHardestAI_Iterator", "Eval":"Playout", "PlayoutPlayer":"Live_Playout" }'
    echo ""
fi

# ============================================================
# Step 3: Launch one instance per unit
# ============================================================
LAUNCHED=0
FAILED=0

for UNIT in "${UNITS[@]}"; do
    # Sanitise unit name for use in instance name and paths
    SAFE_NAME=$(echo "$UNIT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-\|-$//g')
    INSTANCE_NAME="prismata-sweep-${SAFE_NAME}-$(date +%m%d-%H%M%S)"
    GCS_PREFIX="uct-sweep/$LABEL/$SAFE_NAME"

    echo "[$((LAUNCHED + FAILED + 1))/$NUM_UNITS] Launching: $UNIT → $INSTANCE_NAME"

    STARTUP_SCRIPT=$(cat <<ENDSCRIPT
#!/bin/bash
exec > >(tee -a /tmp/boot.log) 2>&1
echo "=== UCT Sweep startup: $UNIT at \$(date) ==="

cleanup_and_shutdown() {
    echo "[trap] Exiting at \$(date)"
    gcloud storage cp /tmp/boot.log gs://$BUCKET/$GCS_PREFIX/boot.log 2>/dev/null || true
    [ -f /home/sweep/game.log ] && gcloud storage cp /home/sweep/game.log gs://$BUCKET/$GCS_PREFIX/game.log 2>/dev/null || true
    [ -f /home/sweep/results.jsonl ] && gcloud storage cp /home/sweep/results.jsonl gs://$BUCKET/$GCS_PREFIX/results.jsonl 2>/dev/null || true
    sudo shutdown -h now
}
trap cleanup_and_shutdown EXIT

WORK="/home/sweep"
mkdir -p \$WORK/bin/asset/config \$WORK/js_engine \$WORK/training/data

# Install Node.js
echo "Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null
sudo apt-get install -y nodejs 2>/dev/null
echo "Node: \$(node --version)"

# Download engine files
echo "Downloading engine files from GCS..."
gcloud storage cp gs://$BUCKET/deploy/uct-sweep/Prismata_Testing.exe \$WORK/bin/Prismata_Testing.exe
chmod +x \$WORK/bin/Prismata_Testing.exe
gcloud storage cp gs://$BUCKET/deploy/uct-sweep/config/config.txt       \$WORK/bin/asset/config/config.txt
gcloud storage cp gs://$BUCKET/deploy/uct-sweep/config/cardLibrary.jso  \$WORK/bin/asset/config/cardLibrary.jso
gcloud storage cp gs://$BUCKET/deploy/uct-sweep/unit_index.json         \$WORK/training/data/unit_index.json

# Download weight files (needed by NeuralNet loader at startup)
for wname in neural_weights.bin neural_weights_mbonly.bin neural_weights_human.bin neural_weights_mbonly_swa.bin; do
    gcloud storage cp gs://$BUCKET/deploy/uct-sweep/config/\$wname \$WORK/bin/asset/config/\$wname 2>/dev/null || true
done

# Download JS engine
echo "Downloading JS engine..."
gcloud storage rsync gs://$BUCKET/deploy/uct-sweep/js/ \$WORK/js_engine/ --quiet

echo "Download complete."

# Run matchup
echo ""
echo "=== Running UCT sweep for unit: $UNIT ==="
cd \$WORK/js_engine

node matchup_clean.js \\
    --games $GAMES \\
    --player-switch \\
    --player-white $PLAYER_WHITE \\
    --player-black $PLAYER_BLACK \\
    --think-time-white $THINK_TIME \\
    --think-time-black 7000 \\
    --cards "$UNIT" \\
    --save-replays sweep_replays_${SAFE_NAME} \\
    2>\$WORK/game.log
MATCHUP_EXIT=\$?

echo ""
echo "Matchup exited with code: \$MATCHUP_EXIT"

# Copy results.jsonl if it exists (written to stdout by matchup_clean.js)
# Re-run to capture stdout
node matchup_clean.js \\
    --games $GAMES \\
    --player-switch \\
    --player-white $PLAYER_WHITE \\
    --player-black $PLAYER_BLACK \\
    --think-time-white $THINK_TIME \\
    --think-time-black 7000 \\
    --cards "$UNIT" \\
    > \$WORK/results.jsonl \\
    2>>\$WORK/game.log

echo "Done. Uploading results..."
ENDSCRIPT
)

    if [ "$DRY_RUN" = "true" ]; then
        echo "  DRY RUN — would launch: $INSTANCE_NAME"
        echo "  GCS output: gs://$BUCKET/$GCS_PREFIX/"
        LAUNCHED=$((LAUNCHED + 1))
        continue
    fi

    STARTUP_FILE="/tmp/startup_sweep_${SAFE_NAME}.sh"
    echo "$STARTUP_SCRIPT" > "$STARTUP_FILE"

    $GCLOUD compute instances create "$INSTANCE_NAME" \
        --project="$PROJECT" \
        --zone="$ZONE" \
        --machine-type="$MACHINE_TYPE" \
        --image-family="ubuntu-2204-lts" \
        --image-project="ubuntu-os-cloud" \
        --boot-disk-size=20GB \
        --boot-disk-type=pd-standard \
        --provisioning-model=SPOT \
        --instance-termination-action=STOP \
        --maintenance-policy=TERMINATE \
        --scopes=storage-full \
        --metadata-from-file=startup-script="$STARTUP_FILE" \
        --no-restart-on-failure \
        --quiet

    LAUNCH_EXIT=$?
    rm -f "$STARTUP_FILE"

    if [ $LAUNCH_EXIT -ne 0 ]; then
        echo "  ERROR: Failed to launch $INSTANCE_NAME"
        FAILED=$((FAILED + 1))
    else
        echo "  Launched OK → gs://$BUCKET/$GCS_PREFIX/"
        LAUNCHED=$((LAUNCHED + 1))
    fi

    # Small delay to avoid GCP API rate limiting
    sleep 1
done

echo ""
echo "=== UCT Sweep Launch Complete ==="
echo "  Launched: $LAUNCHED / $NUM_UNITS"
echo "  Failed:   $FAILED"
echo ""
echo "Monitor instances:"
echo "  $GCLOUD compute instances list --project=$PROJECT --filter='name~prismata-sweep'"
echo ""
echo "Check results as they arrive:"
echo "  $GCLOUD storage ls gs://$BUCKET/uct-sweep/$LABEL/"
echo ""
echo "Download all results when done:"
echo "  $GCLOUD storage rsync gs://$BUCKET/uct-sweep/$LABEL/ gcp/sweep-results/$LABEL/ --recursive"
echo ""
echo "Delete all sweep instances when done:"
echo "  $GCLOUD compute instances list --project=$PROJECT --filter='name~prismata-sweep' --format='value(name,zone)' | while read name zone; do $GCLOUD compute instances delete \$name --zone=\$zone --quiet; done"
