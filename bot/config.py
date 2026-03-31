"""DeadGameBot configuration."""

import os

# PrismataAI.exe — Steam's Master Bot binary
PRISMATA_AI_EXE = os.environ.get(
    "PRISMATA_AI_EXE",
    r"C:\libraries\Prismata\AI\PrismataAI.exe"
)

# Think time in milliseconds
THINK_TIME_MS = 7000

# SteamAI subprocess timeout (think time + overhead)
STEAM_AI_TIMEOUT_S = 15

# Trigger site
TRIGGER_SITE_URL = os.environ.get(
    "TRIGGER_SITE_URL",
    "https://deadgame.prismata.live"
)
TRIGGER_POLL_INTERVAL_S = 5
HEARTBEAT_INTERVAL_S = 10

# Bot API key for authenticated endpoints
BOT_API_KEY = os.environ.get("BOT_API_KEY", "")

# Prismata server
PRISMATA_SERVER_HOST = "3.229.49.48"
PRISMATA_MAIN_PORT = 11600
PRISMATA_TLS_PORT = 11601
PRISMATA_CLIENT_VERSION = "3433"

# Bot account credentials (set via environment)
BOT_USERNAME = os.environ.get("BOT_USERNAME", "DeadGameBot")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "")

# Ranked queue timeout
QUEUE_TIMEOUT_S = 60

# Resignation threshold
RESIGN_EVAL_PCT_THRESHOLD = 5.0  # resign if eval_pct < 5% for N consecutive turns
RESIGN_CONSECUTIVE_TURNS = 3
