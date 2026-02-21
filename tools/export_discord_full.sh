#!/bin/bash
# Export full Discord conversation history from Prismata servers
# Usage: bash tools/export_discord_full.sh <discord_token>
#
# Exports strategy-relevant channels from both Prismata and Prismata League servers.
# Output: c:\libraries\prismata-replay-parser\discord_exports_full\

set -euo pipefail

TOKEN="${1:?Usage: bash tools/export_discord_full.sh <discord_token>}"
EXPORTER="c:/libraries/DiscordChatExporter/cli/DiscordChatExporter.Cli.exe"
OUTPUT_DIR="c:/libraries/prismata-replay-parser/discord_exports_full"

if [ ! -f "$EXPORTER" ]; then
    echo "ERROR: DiscordChatExporter not found at $EXPORTER"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

# Prismata server (112616041175089152) - strategy-relevant channels
PRISMATA_CHANNELS=(
    "119275839652102145"   # prismata_chat
    "400825103367012357"   # strategy_advice
    "406260513312604160"   # unit_and_game_design
    "391209894671548416"   # questions_and_help
    "391209800911814656"   # ask_a_dev
    "400883404935135253"   # alpha_player_lounge
    "415958165020999691"   # dev_seeking_feedback
    "112616041175089152"   # general_chat (off-topic, but has game discussion)
)

# Prismata League server (412991183355248640) - strategy-relevant channels
LEAGUE_CHANNELS=(
    "412991183355248643"   # general
    "454644856590172180"   # prismatic-league
    "454644987746058240"   # prismatic-league-results
    "454645032444493824"   # meteoric-league
    "454645078174990347"   # meteoric-league-results
    "454645171246858240"   # cosmic-league-a
    "454645210194903041"   # cosmic-league-a-results
    "454645265283153940"   # cosmic-league-b
    "454645306089275393"   # cosmic-league-b-results
)

echo "=== Exporting Prismata server channels ==="
for CHANNEL in "${PRISMATA_CHANNELS[@]}"; do
    echo "  Exporting channel $CHANNEL..."
    "$EXPORTER" export --channel "$CHANNEL" --token "$TOKEN" -f Json -o "$OUTPUT_DIR" || {
        echo "  WARNING: Failed to export channel $CHANNEL, continuing..."
    }
done

echo ""
echo "=== Exporting Prismata League server channels ==="
for CHANNEL in "${LEAGUE_CHANNELS[@]}"; do
    echo "  Exporting channel $CHANNEL..."
    "$EXPORTER" export --channel "$CHANNEL" --token "$TOKEN" -f Json -o "$OUTPUT_DIR" || {
        echo "  WARNING: Failed to export channel $CHANNEL, continuing..."
    }
done

echo ""
echo "=== Export complete ==="
echo "Output directory: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR"/*.json 2>/dev/null | wc -l | xargs -I{} echo "  {} JSON files exported"
