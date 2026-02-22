#!/usr/bin/env python
"""Discord Knowledge Extractor for Prismata AI.

Phase 1: Pre-filter, thread grouping, quality scoring, and chunking of Discord
export JSON files. Produces numbered chunk files ready for LLM extraction.

Phase 2: LLM extraction via Anthropic Batch API (or synchronous --no-batch mode).
Sends chunks to Claude Haiku, validates response schema, routes insights by
confidence level, supports checkpoint/resume.

Phase 3: Consolidation & dedup. Merges all extraction JSONs, deduplicates via
sentence-transformers embeddings (cosine similarity >= 0.85), cross-references
with existing knowledge base, and writes discord_knowledge_consolidated.json.

Phase 3.5: Human review gate. Generates a preview markdown document with
statistics, contradictions, top insights, and category samples for manual review.

Phase 4: Integration. Writes insights to docs/commentary-knowledge/discord/
mirror directory, updates sources.md and README.md, creates replay code index.
Does NOT modify existing canonical KB files.

Usage:
    # Dry-run: stats only, no files written
    python tools/discord_knowledge_extractor.py --dry-run

    # Dry-run for a single channel (calibration)
    python tools/discord_knowledge_extractor.py --dry-run --channel strategy_advice

    # Full Phase 1: produce chunk files
    python tools/discord_knowledge_extractor.py

    # Single channel chunk generation
    python tools/discord_knowledge_extractor.py --channel strategy_advice

    # Phase 2: submit batch extraction (default: Batch API)
    python tools/discord_knowledge_extractor.py --extract

    # Phase 2: synchronous extraction (calibration, single channel)
    python tools/discord_knowledge_extractor.py --extract --no-batch --channel strategy_advice

    # Phase 2: resume a previously submitted batch
    python tools/discord_knowledge_extractor.py --batch-id msgbatch_abc123

    # Phase 3: consolidate and deduplicate extractions
    python tools/discord_knowledge_extractor.py --consolidate

    # Phase 3.5: generate preview for human review
    python tools/discord_knowledge_extractor.py --preview

    # Phase 4: integrate into commentary knowledge base
    python tools/discord_knowledge_extractor.py --integrate
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tiktoken

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

DISCORD_EXPORTS_DIR = "c:/libraries/prismata-replay-parser/discord_exports_full/"

# Per-channel thread grouping windows (seconds)
CHANNEL_WINDOWS = {
    "strategy_advice": 600,        # 10 min
    "unit_and_game_design": 600,
    "ask_a_dev": 600,
    "alpha_player_lounge": 600,
    "questions_and_help": 300,     # 5 min
    "dev_seeking_feedback": 300,
    "general": 300,                # League general
    "prismata_chat": 180,          # 3 min
}

# Channels to skip entirely (zero strategic ROI)
SKIP_CHANNELS = {"general_chat", "off_topic"}

# Processing priority order
CHANNEL_PRIORITY = [
    "strategy_advice", "unit_and_game_design", "ask_a_dev",
    "alpha_player_lounge", "dev_seeking_feedback",
    "questions_and_help", "general",
    "prismata_chat",
]

# Known expert handles (match on author.name, which is stable lowercase)
EXPERTS = {
    "amalloy", "mrguy888", "velizar_", "masn6811", "awaclus", "apooche", "elyot",
    "liadahlia", ".holyfire", "307th", "spiritfryer", ".bky_1556", "p0lari",
    "mtanzer", "steel0229e", "shadourow", "extratricky", "crash_overlord", "mqp",
    "silentslayers", "namington",
}

# Replay code regex
REPLAY_CODE_RE = r'[A-Za-z0-9+@]{5}-[A-Za-z0-9+@]{5}'

# Quality scoring thresholds
MIN_THREAD_SCORE = 3
MAX_THREAD_MESSAGES = 50
MAX_THREAD_TOKENS = 5000
TARGET_CHUNK_TOKENS = 15000
MAX_CHUNK_TOKENS = 18000
MIN_MESSAGE_LENGTH = 20

# Haiku pricing (per million tokens)
HAIKU_INPUT_PRICE = 0.25     # $/MTok synchronous
HAIKU_OUTPUT_PRICE = 1.25    # $/MTok synchronous
BATCH_DISCOUNT = 0.50        # 50% off for Batch API

# Estimated output/input ratio for extraction
OUTPUT_INPUT_RATIO = 0.10    # ~10% of input tokens as output

# All 161 unit display names from cardLibrary.jso
UNIT_NAMES = [
    "A.R. Groans", "Aegis", "Amporilla", "Animus", "Antima Comet", "Apollo",
    "Arcflare", "Arka Sodara", "Arms Race", "Asteri Cannon", "Aurb Magnifier",
    "Auric Impulse", "Auride Core", "Barrier", "Basilica", "Behemoth",
    "Blastforge", "Blasto", "Blood Pact", "Blood Phage", "Bloodrager",
    "Bombarder", "Borehole Patroller", "Cauterizer", "Centrifuge", "Centurion",
    "Charged Drone", "Chieftain", "Chrono Filter", "Cluster Bolt", "Colossus",
    "Conduit", "Corpus", "Corracks", "Cryo Cell", "Cryo Ray", "Cursed Wall",
    "Cyclic Drone", "Cynestra", "Deadeye Operative", "Deep Impact", "Defense Grid",
    "Doomed Drone", "Doomed Mech", "Doomed Ship", "Doomed Wall", "Drake", "Drone",
    "EMP", "Ebb Turbine", "Electrovore", "Elephant Graveyard", "Endotherm Kit",
    "Energy Matrix", "Engineer", "Evaporoid", "Farmer", "Feral Warden",
    "Ferritin Sac", "Fire Spinner", "Fireflower", "Fission Turret", "Flame Animus",
    "Flying Drone", "Forcefield", "Forcefield2", "Fragilant", "Frost Brooder",
    "Frost Tarsier", "Frostbite", "Fusion", "Galvani Drone", "Gas Packet",
    "Gauss Cannon", "Gauss Charge", "Gauss Fabricator", "Gaussite Symbiote",
    "Glaciator", "Grenade Mech", "Grimbotch", "Hannibull", "Harm Maker",
    "Hellhound", "Husk", "Iceblade Golem", "Immaculon", "Immolite", "Infestor",
    "Infusion Grid", "Innervi Field", "Ionic Welder", "Iso Kronus",
    "Kinetic Driver", "Lancetooth", "Living Blastforge", "Lucina Spinos",
    "Mahar Rectifier", "Manticore", "Mega Drone", "Militia", "Mobile Animus",
    "Moment's Peace", "Monk", "Need for Speed", "Nightmare Vortex", "Nitrocybe",
    "Nivo Charge", "Odin", "Omega Splitter", "Ossified Drone", "Overwork",
    "Oxide Mixer", "Perforator", "Photonic Fibroid", "Pixie", "Plasmafier",
    "Plexo Cell", "Polywall", "Protoplasm", "Redeemer", "Resophore", "Rhino",
    "Savior", "Scorchilla", "Sentinel", "Shadowfang", "Shiver Yeti", "Shredder",
    "Sound Plan", "Steelforge", "Steelsplitter", "Summon Fusion", "Superservant",
    "Synthesizer", "Tantalum Ray", "Tarsier", "Tatsu Nullifier", "Tesla Coil",
    "The Gift", "The Wincer", "Thermite Core", "Thorium Dynamo", "Thunderhead",
    "Tia Thurnax", "Tough Drone", "Transtower", "Transwall", "Trinity Drone",
    "Twin-Barrel Mech", "Tyranno Smorcus", "Urban Sentry", "Vai Mauronax",
    "Valkyrion", "Venge Cannon", "Vivid Drone", "Wall", "Warp Rift",
    "Wild Drone", "Xaetron", "Xeno Guardian", "Zemora Voidbringer",
]

# Pre-compile unit name set (case-insensitive matching)
_UNIT_NAMES_LOWER = {name.lower(): name for name in UNIT_NAMES}

# ---------------------------------------------------------------------------
# Phase 2 constants
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "UNIT_INTERACTION", "STRATEGY_RULE", "OPENING_THEORY", "GAME_MECHANIC",
    "BALANCE_OPINION", "EXPERT_ASSESSMENT", "COMMUNITY_JARGON",
}

VALID_CONFIDENCE = {"high", "medium", "low"}

VALID_TEMPORAL = {"timeless", "patch_dependent", "historical"}

REQUIRED_FIELDS = {
    "category", "insight", "units", "confidence", "author", "date",
    "replay_code", "context", "temporal_validity", "source_message_ids",
}

MAX_INSIGHT_LENGTH = 400

EXTRACTION_MODEL = "claude-haiku-4-5-20251001"
EXTRACTION_MAX_TOKENS = 4096
BATCH_POLL_INTERVAL = 60  # seconds
SYNC_RETRY_ATTEMPTS = 3
SYNC_RETRY_BASE_DELAY = 2  # seconds (exponential: 2, 4, 8)

EXTRACTION_PROMPT_TEMPLATE = """\
You are analyzing Prismata Discord conversations for strategic game knowledge.
Prismata is a deterministic turn-based strategy card game (no RNG, perfect information).
Two players build economies, armies, and defenses from a random set of units each game.

=== PATCH HISTORY (for temporal_validity tagging) ===
Pre-2018: Early beta, many units and mechanics different from final game.
2018-2019: Active balance patches. Major rebalance Dec 2017. Venge rework Aug 2018.
           Final major balance patch Jul 2019.
2020+: Game development ended. No further balance changes. All post-2020 advice is current.
If discussing unit strength/weakness that may have changed: tag patch_dependent.
If discussing timeless mechanics or principles: tag timeless.
If discussing pre-2020 meta that may no longer apply: tag historical.
======================

=== KNOWN EXPERTS (high-confidence by default) ===
amalloy, mrguy888, velizar_, masn6811, awaclus, apooche, elyot, liadahlia,
.holyfire, 307th, spiritfryer, .bky_1556, p0lari, mtanzer, steel0229e,
shadourow, extratricky, crash_overlord, mqp, silentslayers, namington
Authors with "Developers" role are authoritative on game mechanics.
======================

=== UNIT NAMES (for entity recognition) ===
Base set: Drone, Engineer, Conduit, Blastforge, Animus, Tarsier, Rhino, Wall,
          Steelsplitter, Gauss Cannon, Forcefield.
Advanced (80+ exist, common abbreviations in chat):
Shadowfang, Pixie, Cauterizer, Cynestra, Drake, Doomed Mech, Borehole Patroller,
Corpus, Husk, Galvani Drone, Zemora Voidbringer, Venge Cannon, Plasmafier,
Wincer, Infestor, Centurion, Grimbotch, Scorchilla, Gaussite Symbiote,
Iso Kronus, Tia Threnody, Plexo Cell, Vai Mauronax, Tatsu Nullifier,
Shiver Yeti, Omega Splitter, Thorium Dynamo, Lucent Hellion, Cryo Ray,
Fission Turret, Grenade Mech, Blood Pact, Apollo, Phase Tiger, Endotherm Kit,
Barrager, Savior, Tantalum Ray, Militia, Cluster Bolt, Manticore, Wild Drone,
Chrono Filter, Tera Sentinel, Research Net, Bloodrager, Thunderhead,
Antima Comet, Vivid Drone, Deadeye Operative, Cataclysm, Colossus.
(Do not hallucinate unit names. Use names as-is if ambiguous.)
======================

=== EXTRACTION TASK ===
Extract game knowledge from these conversations. Apply HIGH quality standards:

Only extract insights that meet ALL of:
  (1) Specific to named units or named strategic concepts -- not generic
  (2) Not obvious to any player who has read the basic game rules
  (3) Backed by reasoning, examples, or community agreement in the conversation

Do NOT extract:
  - "Buy drones early" or similar obvious economy advice
  - Pure social chat, jokes without game content
  - Speculation without reasoning or support
  - Balance complaints without citing why or what changed

For each insight, provide:
- category: UNIT_INTERACTION | STRATEGY_RULE | OPENING_THEORY | GAME_MECHANIC |
            BALANCE_OPINION | EXPERT_ASSESSMENT | COMMUNITY_JARGON
- insight: the knowledge (1-3 sentences, precise, name specific units)
- units: array of unit display names mentioned ([] if none)
- confidence: "high" (expert/dev, or strong consensus) /
              "medium" (reasonable player, some agreement) /
              "low" (single unverified claim)
- author: who said it, or "consensus" if multiple agree
- date: approximate date (YYYY-MM)
- replay_code: cited replay code, or null
- context: one sentence on the discussion context
- temporal_validity: "timeless" | "patch_dependent" | "historical"
- source_message_ids: array of Discord message IDs that support this insight (for traceability)

Return ONLY valid JSON. No markdown fences. No commentary outside the array.
Output: JSON array of insight objects. If no qualifying knowledge: [].

--- CONVERSATIONS ---
{chunk_content}
"""

# ---------------------------------------------------------------------------
# Tiktoken encoder (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_encoder = None


def get_encoder():
    """Return the cached tiktoken cl100k_base encoder."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text):
    """Count tokens using tiktoken cl100k_base encoding."""
    return len(get_encoder().encode(text))


# ---------------------------------------------------------------------------
# Phase 1A: Channel discovery
# ---------------------------------------------------------------------------

def discover_channel_files(exports_dir):
    """Scan Discord export JSON files and map channel names to file paths.

    Reads the ``channel.name`` field from each JSON file in *exports_dir*.
    Channels listed in SKIP_CHANNELS are excluded from the result.

    Returns:
        dict: Mapping of channel_name (str) -> filepath (str).
    """
    exports_path = Path(exports_dir)
    if not exports_path.is_dir():
        print(f"ERROR: exports directory not found: {exports_dir}", file=sys.stderr)
        sys.exit(1)

    channel_files = {}
    for fp in sorted(exports_path.glob("*.json")):
        try:
            # Extract channel name from early bytes without loading full file.
            # DiscordChatExporter puts the channel object near the top of the
            # JSON, so a 4KB head read is sufficient.
            with open(fp, encoding="utf-8") as f:
                head = f.read(4096)
            match = re.search(r'"channel"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', head)
            if not match:
                # Fallback: load the full file (shouldn't happen with standard exports)
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                channel_name = data["channel"]["name"]
            else:
                channel_name = match.group(1)
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            print(f"WARNING: skipping {fp.name} ({exc})", file=sys.stderr)
            continue

        if channel_name in SKIP_CHANNELS:
            continue

        channel_files[channel_name] = str(fp)

    return channel_files


# ---------------------------------------------------------------------------
# Phase 1B: Message loading and filtering
# ---------------------------------------------------------------------------

def load_messages(filepath):
    """Load all messages from a Discord export JSON file.

    Messages are returned in chronological order (as exported).

    Returns:
        list[dict]: List of message dicts.
    """
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    return data["messages"]


def _extract_embed_text(embeds):
    """Extract readable text from a list of embed objects.

    Concatenates embed title, description, and field name+value pairs.

    Returns:
        str: Combined embed text (may be empty).
    """
    parts = []
    for embed in embeds:
        if embed.get("title"):
            parts.append(embed["title"])
        if embed.get("description"):
            parts.append(embed["description"])
        for field in embed.get("fields", []):
            name = field.get("name", "")
            value = field.get("value", "")
            if name and value:
                parts.append(f"{name}: {value}")
    return "\n".join(parts)


def filter_messages(messages):
    """Filter messages per Phase 1B rules.

    Removes:
    - Bot messages (author.isBot == True)
    - Empty/whitespace-only content with no embeds
    - Messages shorter than MIN_MESSAGE_LENGTH with no embeds

    Adds ``_embed_text`` field to messages that have embeds.
    Adds ``_full_text`` field combining content + embed text.

    Returns:
        list[dict]: Filtered messages (originals are not mutated; shallow copies
        are returned with extra fields).
    """
    filtered = []
    for msg in messages:
        # Skip bots
        if msg.get("author", {}).get("isBot", False):
            continue

        content = (msg.get("content") or "").strip()
        embeds = msg.get("embeds", [])
        embed_text = _extract_embed_text(embeds) if embeds else ""

        # Skip empty messages with no embeds
        if not content and not embed_text:
            continue

        # Skip short messages without embeds
        if len(content) < MIN_MESSAGE_LENGTH and not embed_text:
            continue

        # Build enriched copy (shallow — we only add string fields)
        enriched = dict(msg)
        enriched["_embed_text"] = embed_text
        enriched["_full_text"] = (content + "\n" + embed_text).strip() if embed_text else content
        filtered.append(enriched)

    return filtered


# ---------------------------------------------------------------------------
# Phase 1C: Thread grouping
# ---------------------------------------------------------------------------

def _parse_timestamp(ts_str):
    """Parse an ISO-8601 timestamp string to a datetime object.

    Handles timezone-aware strings (``+00:00``, ``Z``, etc.) as produced by
    DiscordChatExporter.
    """
    # Python 3.7+ fromisoformat handles most formats; normalize trailing Z
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


def _thread_tokens(thread_messages):
    """Estimate the total token count for a thread's formatted text."""
    text = _format_thread_messages(thread_messages)
    return count_tokens(text)


def _format_thread_messages(messages):
    """Format a list of messages as readable text for token counting.

    Format: ``[YYYY-MM-DD HH:MM] author: content``
    """
    lines = []
    for msg in messages:
        ts = _parse_timestamp(msg["timestamp"])
        ts_str = ts.strftime("%Y-%m-%d %H:%M")
        author = msg.get("author", {}).get("name", "unknown")
        text = msg.get("_full_text", msg.get("content", ""))
        lines.append(f"[{ts_str}] {author}: {text}")
    return "\n".join(lines)


def group_threads(messages, window_seconds):
    """Group messages into conversation threads.

    Two consecutive messages belong to the same thread if their timestamps
    differ by at most *window_seconds*. Explicit Reply references
    (``reference.messageId``) extend threads across arbitrary time gaps.

    Oversized threads (> MAX_THREAD_MESSAGES or > MAX_THREAD_TOKENS) are
    split at the boundary point.

    Args:
        messages: Filtered messages (chronological order).
        window_seconds: Maximum gap in seconds between consecutive messages
            within a thread.

    Returns:
        list[dict]: Each thread dict contains:
            - messages: list of message dicts
            - participants: set of author names
            - start_ts: ISO string of first message
            - end_ts: ISO string of last message
            - replay_codes: list of replay code strings found
    """
    if not messages:
        return []

    # Build reply lookup: message_id -> thread_index (populated incrementally)
    msg_id_to_thread = {}

    threads = []
    current_thread_msgs = []
    current_thread_idx = 0

    window = timedelta(seconds=window_seconds)

    for msg in messages:
        ts = _parse_timestamp(msg["timestamp"])
        assigned = False

        # Check if this message is a reply to a message in an existing thread.
        # Reply references extend threads across arbitrary time gaps (plan 1C).
        ref = msg.get("reference")
        if ref and ref.get("messageId"):
            ref_id = ref["messageId"]
            if ref_id in msg_id_to_thread:
                target_thread_idx = msg_id_to_thread[ref_id]
                if target_thread_idx == current_thread_idx:
                    # Reply to current thread — stays in same thread
                    assigned = True
                elif not current_thread_msgs:
                    # No current thread open — inherit the referenced thread index
                    # so this message starts a continuation of that conversation
                    current_thread_idx = target_thread_idx
                    assigned = True
                else:
                    # Reply to a past thread while current thread is open.
                    # Finalize the current thread, then start a continuation
                    # of the referenced thread.
                    threads.append(_finalize_thread(current_thread_msgs))
                    current_thread_msgs = []
                    current_thread_idx = len(threads)
                    assigned = True

        # Check time proximity to previous message in current thread
        if not assigned and current_thread_msgs:
            prev_ts = _parse_timestamp(current_thread_msgs[-1]["timestamp"])
            if ts - prev_ts <= window:
                assigned = True

        if not assigned and current_thread_msgs:
            # Finalize current thread
            threads.append(_finalize_thread(current_thread_msgs))
            current_thread_idx = len(threads)
            current_thread_msgs = []

        current_thread_msgs.append(msg)
        msg_id_to_thread[msg["id"]] = current_thread_idx

        # Check if thread is oversized and needs splitting
        if len(current_thread_msgs) >= MAX_THREAD_MESSAGES:
            threads.append(_finalize_thread(current_thread_msgs))
            current_thread_idx = len(threads)
            current_thread_msgs = []
        elif len(current_thread_msgs) % 10 == 0 and len(current_thread_msgs) >= 10:
            # Periodic token check (every 10 messages to avoid O(n^2) counting)
            if _thread_tokens(current_thread_msgs) > MAX_THREAD_TOKENS:
                # Split: keep all but last message, start new thread with last
                last_msg = current_thread_msgs.pop()
                threads.append(_finalize_thread(current_thread_msgs))
                current_thread_idx = len(threads)
                current_thread_msgs = [last_msg]
                msg_id_to_thread[last_msg["id"]] = current_thread_idx

    # Finalize last thread
    if current_thread_msgs:
        threads.append(_finalize_thread(current_thread_msgs))

    # Final token-check pass: split any thread that still exceeds MAX_THREAD_TOKENS
    threads = _split_oversized_threads(threads)

    return threads


def _finalize_thread(messages):
    """Build a thread dict from a list of messages."""
    participants = set()
    replay_codes = []

    for msg in messages:
        author = msg.get("author", {}).get("name", "unknown")
        participants.add(author)
        text = msg.get("_full_text", msg.get("content", ""))
        codes = re.findall(REPLAY_CODE_RE, text)
        replay_codes.extend(codes)

    return {
        "messages": list(messages),
        "participants": participants,
        "start_ts": messages[0]["timestamp"],
        "end_ts": messages[-1]["timestamp"],
        "replay_codes": replay_codes,
    }


def _split_oversized_threads(threads):
    """Split threads that exceed MAX_THREAD_TOKENS into sub-threads."""
    result = []
    for thread in threads:
        msgs = thread["messages"]
        tokens = _thread_tokens(msgs)
        if tokens <= MAX_THREAD_TOKENS:
            result.append(thread)
            continue

        # Binary-search-style split: find midpoint and split
        mid = len(msgs) // 2
        first_half = msgs[:mid]
        second_half = msgs[mid:]
        if first_half:
            result.append(_finalize_thread(first_half))
        if second_half:
            # Recursively check the second half
            sub = _split_oversized_threads([_finalize_thread(second_half)])
            result.extend(sub)

    return result


# ---------------------------------------------------------------------------
# Phase 1D: Orphan handling
# ---------------------------------------------------------------------------

def _has_role(msg, role_name):
    """Check if a message's author has a specific role by name."""
    roles = msg.get("author", {}).get("roles", [])
    return any(r.get("name") == role_name for r in roles)


def handle_orphans(threads, channel_name):
    """Filter orphan threads (single-message threads) per Phase 1D rules.

    Keep orphans if ANY of:
    - author.name is in EXPERTS
    - author has "Alpha Player" or "Developers" role
    - content >= 100 characters
    - channel is ask_a_dev or alpha_player_lounge

    Args:
        threads: List of thread dicts.
        channel_name: Name of the channel being processed.

    Returns:
        list[dict]: Threads with unqualified orphans removed.
    """
    result = []
    for thread in threads:
        if len(thread["messages"]) > 1:
            # Multi-message thread: always keep
            result.append(thread)
            continue

        msg = thread["messages"][0]
        author = msg.get("author", {}).get("name", "")
        content = msg.get("_full_text", msg.get("content", ""))

        keep = False
        if author in EXPERTS:
            keep = True
        elif _has_role(msg, "Alpha Player") or _has_role(msg, "Developers"):
            keep = True
        elif len(content) >= 100:
            keep = True
        elif channel_name in ("ask_a_dev", "alpha_player_lounge"):
            keep = True

        if keep:
            result.append(thread)

    return result


# ---------------------------------------------------------------------------
# Phase 1E: Quality scoring
# ---------------------------------------------------------------------------

def _find_unit_mentions(text):
    """Find all Prismata unit names mentioned in text (case-insensitive).

    Returns:
        set: Display names of mentioned units.
    """
    text_lower = text.lower()
    found = set()
    for name_lower, name in _UNIT_NAMES_LOWER.items():
        # Word boundary check to avoid false positives (e.g., "Wall" in "wallet")
        # Use simple substring for multi-word names, word boundary for single-word
        if " " in name_lower:
            if name_lower in text_lower:
                found.add(name)
        else:
            # Use regex word boundary for single-word names
            if re.search(r'\b' + re.escape(name_lower) + r'\b', text_lower):
                found.add(name)
    return found


def score_threads(threads):
    """Score each thread per Phase 1E quality rules and filter low-scoring ones.

    Scoring:
    - +2 per expert message
    - +2 per Developers-role message
    - +1 per Alpha Player-role message
    - +1 per message > 100 chars, +2 per message > 200 chars
    - +1 per replay code found
    - +1 per unit name mentioned (across all messages in thread)
    - -1 per Deleted User message

    Threads scoring below MIN_THREAD_SCORE are discarded.

    Returns:
        list[dict]: Scored threads (with ``_score`` field added), filtered.
    """
    result = []
    for thread in threads:
        score = 0
        all_text = []

        for msg in thread["messages"]:
            author = msg.get("author", {}).get("name", "")
            content = msg.get("_full_text", msg.get("content", ""))
            all_text.append(content)

            # Expert bonus
            if author in EXPERTS:
                score += 2

            # Role bonuses
            if _has_role(msg, "Developers"):
                score += 2
            if _has_role(msg, "Alpha Player"):
                score += 1

            # Length bonuses
            content_len = len(content)
            if content_len > 200:
                score += 2
            elif content_len > 100:
                score += 1

            # Deleted User penalty
            if "Deleted User" in (msg.get("author", {}).get("nickname", "") or ""):
                score -= 1
            if author.startswith("deleted_user") or author == "Deleted User":
                score -= 1

        # Replay code bonus
        score += len(thread.get("replay_codes", []))

        # Unit name mentions (deduplicated across thread)
        combined_text = "\n".join(all_text)
        units_mentioned = _find_unit_mentions(combined_text)
        score += len(units_mentioned)

        if score >= MIN_THREAD_SCORE:
            thread["_score"] = score
            thread["_units_mentioned"] = units_mentioned
            result.append(thread)

    return result


# ---------------------------------------------------------------------------
# Phase 1F: Chunking
# ---------------------------------------------------------------------------

def format_thread_text(thread):
    """Convert a thread to readable text for LLM consumption.

    Format::

        --- Thread (3 messages, 2020-03-15 to 2020-03-15) ---
        [2020-03-15 14:32] amalloy: The key thing about Tarsier is...
        [2020-03-15 14:33] mrguy888: I agree, but you also need to consider...

    Returns:
        str: Formatted thread text.
    """
    start = _parse_timestamp(thread["start_ts"]).strftime("%Y-%m-%d")
    end = _parse_timestamp(thread["end_ts"]).strftime("%Y-%m-%d")
    n = len(thread["messages"])
    date_range = start if start == end else f"{start} to {end}"

    lines = [f"--- Thread ({n} messages, {date_range}) ---"]
    for msg in thread["messages"]:
        ts = _parse_timestamp(msg["timestamp"])
        ts_str = ts.strftime("%Y-%m-%d %H:%M")
        author = msg.get("author", {}).get("name", "unknown")
        nickname = msg.get("author", {}).get("nickname", "")
        # Show nickname in parens if different from handle
        author_display = f"{author} ({nickname})" if nickname and nickname.lower() != author else author

        text = msg.get("_full_text", msg.get("content", ""))
        lines.append(f"[{ts_str}] {author_display}: {text}")

    return "\n".join(lines)


def chunk_threads(threads, channel_name):
    """Assemble scored threads into chunks of ~TARGET_CHUNK_TOKENS each.

    Never splits a thread across chunks. Each chunk includes metadata:
    channel, date_range, thread_count, token_count.

    Args:
        threads: Scored and filtered threads.
        channel_name: Channel name for metadata.

    Returns:
        list[dict]: Chunk dicts with keys: channel, date_range, thread_count,
        token_count, threads (list of formatted thread dicts).
    """
    chunks = []
    current_threads = []
    current_tokens = 0
    current_start = None
    current_end = None

    for thread in threads:
        thread_text = format_thread_text(thread)
        thread_tok = count_tokens(thread_text)

        # If a single thread exceeds MAX_CHUNK_TOKENS, it goes in its own chunk
        if thread_tok > MAX_CHUNK_TOKENS:
            # Flush current chunk first
            if current_threads:
                chunks.append(_build_chunk(
                    current_threads, channel_name, current_start, current_end, current_tokens
                ))
                current_threads = []
                current_tokens = 0
                current_start = None
                current_end = None

            # Oversized thread as its own chunk (will exceed MAX but we can't split threads)
            chunks.append(_build_chunk(
                [thread], channel_name, thread["start_ts"], thread["end_ts"], thread_tok
            ))
            continue

        # Would adding this thread exceed target?
        if current_tokens + thread_tok > TARGET_CHUNK_TOKENS and current_threads:
            # Flush
            chunks.append(_build_chunk(
                current_threads, channel_name, current_start, current_end, current_tokens
            ))
            current_threads = []
            current_tokens = 0
            current_start = None
            current_end = None

        # Add thread to current chunk
        current_threads.append(thread)
        current_tokens += thread_tok
        if current_start is None:
            current_start = thread["start_ts"]
        current_end = thread["end_ts"]

    # Flush remaining
    if current_threads:
        chunks.append(_build_chunk(
            current_threads, channel_name, current_start, current_end, current_tokens
        ))

    return chunks


def _build_chunk(threads, channel_name, start_ts, end_ts, token_count):
    """Build a chunk metadata dict."""
    start_date = _parse_timestamp(start_ts).strftime("%Y-%m-%d")
    end_date = _parse_timestamp(end_ts).strftime("%Y-%m-%d")
    date_range = start_date if start_date == end_date else f"{start_date} to {end_date}"

    return {
        "channel": channel_name,
        "date_range": date_range,
        "thread_count": len(threads),
        "token_count": token_count,
        "threads": [
            {
                "start_ts": t["start_ts"],
                "end_ts": t["end_ts"],
                "participants": sorted(t["participants"]),
                "replay_codes": t["replay_codes"],
                "score": t.get("_score", 0),
                "formatted_text": format_thread_text(t),
                "messages": [
                    {
                        "id": m["id"],
                        "author": m.get("author", {}).get("name", "unknown"),
                        "nickname": m.get("author", {}).get("nickname", ""),
                        "timestamp": m["timestamp"],
                        "content": m.get("_full_text", m.get("content", "")),
                    }
                    for m in t["messages"]
                ],
            }
            for t in threads
        ],
    }


# ---------------------------------------------------------------------------
# Phase 1 pipeline: process one channel
# ---------------------------------------------------------------------------

def process_channel(channel_name, filepath, window_seconds):
    """Run the full Phase 1 pipeline for a single channel.

    Returns:
        dict: Channel processing results with keys: channel, filepath,
        raw_count, filtered_count, thread_count, orphans_removed,
        scored_count, chunks, expert_counts, total_tokens.
    """
    print(f"  Loading {channel_name}...", end="", flush=True)
    messages = load_messages(filepath)
    raw_count = len(messages)
    print(f" {raw_count} raw messages", flush=True)

    print(f"  Filtering...", end="", flush=True)
    filtered = filter_messages(messages)
    filtered_count = len(filtered)
    print(f" {filtered_count} after filter ({raw_count - filtered_count} removed)", flush=True)

    print(f"  Grouping threads (window={window_seconds}s)...", end="", flush=True)
    threads = group_threads(filtered, window_seconds)
    pre_orphan_count = len(threads)
    print(f" {pre_orphan_count} threads", flush=True)

    print(f"  Handling orphans...", end="", flush=True)
    threads = handle_orphans(threads, channel_name)
    orphans_removed = pre_orphan_count - len(threads)
    print(f" {orphans_removed} orphans removed, {len(threads)} remaining", flush=True)

    print(f"  Scoring...", end="", flush=True)
    threads = score_threads(threads)
    scored_count = len(threads)
    print(f" {scored_count} threads pass quality threshold (>={MIN_THREAD_SCORE})", flush=True)

    print(f"  Chunking...", end="", flush=True)
    chunks = chunk_threads(threads, channel_name)
    total_tokens = sum(c["token_count"] for c in chunks)
    print(f" {len(chunks)} chunks, {total_tokens:,} tokens", flush=True)

    # Count expert messages
    expert_counts = defaultdict(int)
    for msg in filtered:
        author = msg.get("author", {}).get("name", "")
        if author in EXPERTS:
            expert_counts[author] += 1

    return {
        "channel": channel_name,
        "filepath": filepath,
        "raw_count": raw_count,
        "filtered_count": filtered_count,
        "thread_count": pre_orphan_count,
        "orphans_removed": orphans_removed,
        "scored_count": scored_count,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "expert_counts": dict(expert_counts),
        "total_tokens": total_tokens,
    }


# ---------------------------------------------------------------------------
# Dry-run output
# ---------------------------------------------------------------------------

def print_dry_run(results):
    """Print dry-run statistics tables.

    Displays:
    1. Per-channel stats table
    2. Expert frequency by channel
    3. Total estimated API cost
    """
    # 1. Per-channel stats
    print("\n" + "=" * 90)
    print("PHASE 1 DRY-RUN RESULTS")
    print("=" * 90)

    header = f"{'Channel':<25} {'Raw':>7} {'Filtered':>9} {'Threads':>8} {'Scored':>7} {'Chunks':>7} {'Tokens':>10}"
    print(f"\n{header}")
    print("-" * len(header))

    totals = {
        "raw": 0, "filtered": 0, "threads": 0,
        "scored": 0, "chunks": 0, "tokens": 0,
    }

    for r in results:
        print(f"{r['channel']:<25} {r['raw_count']:>7,} {r['filtered_count']:>9,} "
              f"{r['thread_count']:>8,} {r['scored_count']:>7,} {r['chunk_count']:>7,} "
              f"{r['total_tokens']:>10,}")
        totals["raw"] += r["raw_count"]
        totals["filtered"] += r["filtered_count"]
        totals["threads"] += r["thread_count"]
        totals["scored"] += r["scored_count"]
        totals["chunks"] += r["chunk_count"]
        totals["tokens"] += r["total_tokens"]

    print("-" * len(header))
    print(f"{'TOTAL':<25} {totals['raw']:>7,} {totals['filtered']:>9,} "
          f"{totals['threads']:>8,} {totals['scored']:>7,} {totals['chunks']:>7,} "
          f"{totals['tokens']:>10,}")

    # 2. Expert frequency by channel
    # Collect all experts that appear
    all_expert_names = set()
    for r in results:
        all_expert_names.update(r["expert_counts"].keys())
    all_expert_names = sorted(all_expert_names)

    if all_expert_names:
        print(f"\nExpert Message Frequency by Channel:")
        # Truncate expert names for display
        name_width = 10
        expert_header = f"{'Channel':<25}"
        for name in all_expert_names:
            display = name[:name_width]
            expert_header += f" {display:>{name_width}}"
        expert_header += f" {'TOTAL':>7}"
        print(expert_header)
        print("-" * len(expert_header))

        grand_totals = defaultdict(int)
        for r in results:
            row = f"{r['channel']:<25}"
            ch_total = 0
            for name in all_expert_names:
                count = r["expert_counts"].get(name, 0)
                grand_totals[name] += count
                ch_total += count
                row += f" {count:>{name_width}}"
            row += f" {ch_total:>7}"
            print(row)

        # Grand total row
        print("-" * len(expert_header))
        row = f"{'TOTAL':<25}"
        for name in all_expert_names:
            row += f" {grand_totals[name]:>{name_width}}"
        row += f" {sum(grand_totals.values()):>7}"
        print(row)

    # 3. Cost estimate
    total_input_tokens = totals["tokens"]
    total_output_tokens = int(total_input_tokens * OUTPUT_INPUT_RATIO)

    sync_cost = (total_input_tokens / 1_000_000 * HAIKU_INPUT_PRICE +
                 total_output_tokens / 1_000_000 * HAIKU_OUTPUT_PRICE)
    batch_cost = sync_cost * BATCH_DISCOUNT

    print(f"\nEstimated API Cost:")
    print(f"  Input tokens:  {total_input_tokens:>12,}")
    print(f"  Output tokens: {total_output_tokens:>12,} (est. {OUTPUT_INPUT_RATIO:.0%} of input)")
    print(f"  Synchronous:   ${sync_cost:>8.4f}")
    print(f"  Batch API:     ${batch_cost:>8.4f} (50% discount)")
    print(f"\nFilter rate:     {(1 - totals['filtered'] / totals['raw']) * 100:.1f}% of raw messages removed")
    print(f"Thread yield:    {totals['scored'] / totals['threads'] * 100:.1f}% of threads pass quality scoring"
          if totals["threads"] > 0 else "")


# ---------------------------------------------------------------------------
# Write chunks to disk
# ---------------------------------------------------------------------------

def write_chunks(all_results, work_dir):
    """Write chunk files to the work directory.

    Creates ``work_dir/chunks/`` and writes numbered JSON files. Also writes
    a manifest file ``work_dir/chunk_manifest.json``.

    Returns:
        int: Total number of chunk files written.
    """
    chunks_dir = Path(work_dir) / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    chunk_num = 0

    for result in all_results:
        for chunk in result["chunks"]:
            chunk_num += 1
            filename = f"chunk_{chunk_num:04d}.json"
            filepath = chunks_dir / filename

            # Write chunk file (without the raw messages to save space; keep formatted_text)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(chunk, f, indent=2, ensure_ascii=False, default=str)

            manifest.append({
                "filename": filename,
                "channel": chunk["channel"],
                "date_range": chunk["date_range"],
                "thread_count": chunk["thread_count"],
                "token_count": chunk["token_count"],
            })

    # Write manifest
    manifest_path = Path(work_dir) / "chunk_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_chunks": chunk_num,
            "total_tokens": sum(m["token_count"] for m in manifest),
            "generated": datetime.now(timezone.utc).isoformat(),
            "chunks": manifest,
        }, f, indent=2, ensure_ascii=False)

    return chunk_num


# ---------------------------------------------------------------------------
# Phase 2: LLM extraction
# ---------------------------------------------------------------------------

def build_extraction_prompt(chunk):
    """Build the full extraction prompt for a chunk.

    Takes a chunk dict (as written by Phase 1) and formats the extraction
    prompt template with the chunk's formatted thread text.

    Args:
        chunk: A chunk dict with 'threads' list, each having 'formatted_text'.

    Returns:
        str: The complete prompt string ready for the LLM.
    """
    # Concatenate all thread formatted texts within this chunk
    thread_texts = []
    for thread in chunk.get("threads", []):
        thread_texts.append(thread.get("formatted_text", ""))

    chunk_content = "\n\n".join(thread_texts)
    return EXTRACTION_PROMPT_TEMPLATE.format(chunk_content=chunk_content)


def validate_insight(insight):
    """Validate a single insight dict against the extraction schema.

    Checks:
    - All REQUIRED_FIELDS are present
    - category is in VALID_CATEGORIES
    - confidence is in VALID_CONFIDENCE
    - temporal_validity is in VALID_TEMPORAL
    - replay_code (if not null) matches the replay code regex
    - source_message_ids is a list of strings
    - insight text length flagging (> MAX_INSIGHT_LENGTH)

    Args:
        insight: A dict representing one extracted insight.

    Returns:
        tuple: (is_valid, insight_with_flags) where is_valid is True if all
        required fields are present and typed correctly, and
        insight_with_flags has '_flagged' markers added for any issues.
    """
    if not isinstance(insight, dict):
        return False, insight

    result = dict(insight)
    is_valid = True
    flags = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in result:
            flags.append(f"missing_{field}")
            is_valid = False

    # Validate category
    if result.get("category") not in VALID_CATEGORIES:
        flags.append("invalid_category")

    # Validate confidence
    if result.get("confidence") not in VALID_CONFIDENCE:
        flags.append("invalid_confidence")

    # Validate temporal_validity
    if result.get("temporal_validity") not in VALID_TEMPORAL:
        flags.append("invalid_temporal_validity")

    # Validate replay_code format (if not null)
    replay_code = result.get("replay_code")
    if replay_code is not None and replay_code != "null":
        if not isinstance(replay_code, str) or not re.match(
            r'^' + REPLAY_CODE_RE + r'$', replay_code
        ):
            flags.append("invalid_replay_code")

    # Validate source_message_ids is a list of strings
    msg_ids = result.get("source_message_ids")
    if msg_ids is not None:
        if not isinstance(msg_ids, list):
            flags.append("source_message_ids_not_list")
        elif not all(isinstance(mid, str) for mid in msg_ids):
            flags.append("source_message_ids_not_strings")
    else:
        flags.append("missing_source_message_ids")
        is_valid = False

    # Validate units is a list
    units = result.get("units")
    if units is not None and not isinstance(units, list):
        flags.append("units_not_list")

    # Flag long insights
    insight_text = result.get("insight", "")
    if isinstance(insight_text, str) and len(insight_text) > MAX_INSIGHT_LENGTH:
        flags.append("insight_too_long")

    if flags:
        result["_flagged"] = flags

    return is_valid, result


def _parse_llm_json(raw_text):
    """Parse JSON from LLM response, stripping markdown fences if present.

    Args:
        raw_text: Raw text from the LLM response.

    Returns:
        list or None: Parsed JSON array, or None if parsing failed.
    """
    text = raw_text.strip()

    # Strip markdown fences: ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].rstrip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        # If it's a single object, wrap it
        if isinstance(parsed, dict):
            return [parsed]
        return None
    except json.JSONDecodeError:
        return None


def _route_insights(insights, chunk_filename, high_dir, low_dir):
    """Route validated insights by confidence level to output directories.

    High and medium confidence insights go to high_dir.
    Low confidence insights go to low_dir.

    Args:
        insights: List of validated insight dicts.
        chunk_filename: The source chunk filename (e.g., 'chunk_0001.json').
        high_dir: Path to high-confidence output directory.
        low_dir: Path to low-confidence output directory.

    Returns:
        tuple: (high_count, low_count) number of insights routed.
    """
    high_insights = []
    low_insights = []

    for insight in insights:
        confidence = insight.get("confidence", "low")
        if confidence in ("high", "medium"):
            high_insights.append(insight)
        else:
            low_insights.append(insight)

    high_count = 0
    low_count = 0

    if high_insights:
        high_dir.mkdir(parents=True, exist_ok=True)
        outpath = high_dir / chunk_filename
        with open(outpath, "w", encoding="utf-8") as f:
            json.dump(high_insights, f, indent=2, ensure_ascii=False)
        high_count = len(high_insights)

    if low_insights:
        low_dir.mkdir(parents=True, exist_ok=True)
        outpath = low_dir / chunk_filename
        with open(outpath, "w", encoding="utf-8") as f:
            json.dump(low_insights, f, indent=2, ensure_ascii=False)
        low_count = len(low_insights)

    return high_count, low_count


def _load_processed_chunks(work_dir):
    """Load the processed chunks checkpoint file.

    Returns:
        dict: Checkpoint data with 'processed' list, 'last_updated', 'batch_ids'.
    """
    checkpoint_path = Path(work_dir) / "processed_chunks.json"
    if checkpoint_path.exists():
        with open(checkpoint_path, encoding="utf-8") as f:
            return json.load(f)
    return {"processed": [], "last_updated": None, "batch_ids": []}


def _save_processed_chunks(work_dir, checkpoint):
    """Save the processed chunks checkpoint file."""
    checkpoint["last_updated"] = datetime.now(timezone.utc).isoformat()
    checkpoint_path = Path(work_dir) / "processed_chunks.json"
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


def _save_batch_status(work_dir, batch_id, status, extra=None):
    """Save batch status to work_dir/batch_status.json."""
    data = {
        "batch_id": batch_id,
        "status": status,
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        data.update(extra)
    status_path = Path(work_dir) / "batch_status.json"
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_sync(chunk, client):
    """Synchronous extraction for a single chunk (--no-batch mode).

    Sends the extraction prompt to Claude Haiku via the Messages API,
    parses the JSON response, validates each insight, and returns them.

    Retries on API errors up to SYNC_RETRY_ATTEMPTS times with
    exponential backoff.

    Args:
        chunk: A chunk dict (from Phase 1 output).
        client: An Anthropic client instance.

    Returns:
        list: Validated insight dicts (may include _flagged markers).
        Returns empty list if extraction fails after all retries.
    """
    import time as _time

    prompt = build_extraction_prompt(chunk)

    raw_text = None
    for attempt in range(SYNC_RETRY_ATTEMPTS):
        try:
            response = client.messages.create(
                model=EXTRACTION_MODEL,
                max_tokens=EXTRACTION_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text
            break
        except Exception as exc:
            delay = SYNC_RETRY_BASE_DELAY * (2 ** attempt)
            if attempt < SYNC_RETRY_ATTEMPTS - 1:
                print(f"    API error (attempt {attempt + 1}/{SYNC_RETRY_ATTEMPTS}): "
                      f"{exc}. Retrying in {delay}s...", flush=True)
                _time.sleep(delay)
            else:
                print(f"    API error (attempt {attempt + 1}/{SYNC_RETRY_ATTEMPTS}): "
                      f"{exc}. Giving up.", flush=True)
                return []

    if raw_text is None:
        return []

    # Parse JSON response
    insights = _parse_llm_json(raw_text)
    if insights is None:
        print(f"    WARNING: JSON parse failed for chunk", flush=True)
        return []

    # Validate each insight
    validated = []
    for insight in insights:
        _, flagged = validate_insight(insight)
        validated.append(flagged)

    return validated


def extract_batch(chunks_dir, work_dir, client):
    """Submit a batch extraction job for all unprocessed chunks.

    Builds requests from unprocessed chunks, submits to the Anthropic
    Batch API, polls for completion, downloads results, validates and
    routes insights.

    Args:
        chunks_dir: Path to the chunks directory.
        work_dir: Path to the working directory.
        client: An Anthropic client instance.

    Returns:
        dict: Summary with keys: submitted, succeeded, failed, total_insights.
    """
    import time as _time

    work_path = Path(work_dir)
    chunks_path = Path(chunks_dir)

    # Load manifest
    manifest_path = work_path / "chunk_manifest.json"
    if not manifest_path.exists():
        print("ERROR: chunk_manifest.json not found. Run Phase 1 first.", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # Load checkpoint
    checkpoint = _load_processed_chunks(work_dir)
    processed_set = set(checkpoint["processed"])

    # Build batch requests from unprocessed chunks
    requests = []
    chunk_filenames = []
    for entry in manifest["chunks"]:
        filename = entry["filename"]
        if filename in processed_set:
            continue

        chunk_path = chunks_path / filename
        if not chunk_path.exists():
            print(f"  WARNING: chunk file missing: {filename}", flush=True)
            continue

        with open(chunk_path, encoding="utf-8") as f:
            chunk = json.load(f)

        prompt = build_extraction_prompt(chunk)
        custom_id = filename.replace(".json", "")

        requests.append({
            "custom_id": custom_id,
            "params": {
                "model": EXTRACTION_MODEL,
                "max_tokens": EXTRACTION_MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            },
        })
        chunk_filenames.append(filename)

    if not requests:
        print("All chunks already processed. Nothing to submit.", flush=True)
        return {"submitted": 0, "succeeded": 0, "failed": 0, "total_insights": 0}

    print(f"Submitting batch with {len(requests)} requests...", flush=True)

    # Submit batch
    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id
    print(f"Batch submitted: {batch_id}", flush=True)

    # Save batch status
    _save_batch_status(work_dir, batch_id, "submitted", {
        "total_requests": len(requests),
    })

    # Track batch_id in checkpoint
    if batch_id not in checkpoint["batch_ids"]:
        checkpoint["batch_ids"].append(batch_id)
        _save_processed_chunks(work_dir, checkpoint)

    # Poll for completion
    print("Polling for completion...", flush=True)
    while batch.processing_status == "in_progress":
        _time.sleep(BATCH_POLL_INTERVAL)
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        total = counts.processing + counts.succeeded + counts.errored + counts.canceled + counts.expired
        print(f"  Status: {batch.processing_status} "
              f"(succeeded={counts.succeeded}, errored={counts.errored}, "
              f"processing={counts.processing}/{total})", flush=True)
        _save_batch_status(work_dir, batch_id, batch.processing_status, {
            "total_requests": total,
            "succeeded": counts.succeeded,
            "errored": counts.errored,
        })

    print(f"Batch complete: {batch.processing_status}", flush=True)

    # Process results
    return _process_batch_results(batch_id, work_dir, client, checkpoint)


def _process_batch_results(batch_id, work_dir, client, checkpoint):
    """Download and process results from a completed batch.

    Args:
        batch_id: The batch ID to download results from.
        work_dir: Path to the working directory.
        client: An Anthropic client instance.
        checkpoint: The current processed_chunks checkpoint dict.

    Returns:
        dict: Summary with keys: submitted, succeeded, failed, total_insights.
    """
    work_path = Path(work_dir)
    high_dir = work_path / "extractions" / "high"
    low_dir = work_path / "extractions" / "low"
    errors_dir = work_path / "extraction_errors"

    succeeded = 0
    failed = 0
    total_insights = 0
    total_high = 0
    total_low = 0

    for entry in client.messages.batches.results(batch_id):
        # Map custom_id back to chunk filename
        chunk_filename = entry.custom_id + ".json"

        if entry.result.type == "succeeded":
            raw_text = entry.result.message.content[0].text
            insights = _parse_llm_json(raw_text)

            if insights is None:
                # JSON parse failure — save raw text for debugging
                errors_dir.mkdir(parents=True, exist_ok=True)
                error_path = errors_dir / chunk_filename
                with open(error_path, "w", encoding="utf-8") as f:
                    f.write(raw_text)
                print(f"  WARNING: JSON parse failed for {chunk_filename}, "
                      f"raw saved to extraction_errors/", flush=True)
                failed += 1
            else:
                # Validate each insight
                validated = []
                for insight in insights:
                    _, flagged = validate_insight(insight)
                    validated.append(flagged)

                # Route by confidence
                high_count, low_count = _route_insights(
                    validated, chunk_filename, high_dir, low_dir
                )
                total_high += high_count
                total_low += low_count
                total_insights += len(validated)
                succeeded += 1

                if validated:
                    print(f"  {chunk_filename}: {len(validated)} insights "
                          f"({high_count} high/med, {low_count} low)", flush=True)
                else:
                    print(f"  {chunk_filename}: 0 insights (empty)", flush=True)

        elif entry.result.type == "errored":
            error_msg = getattr(entry.result.error, "message", str(entry.result.error))
            print(f"  ERROR: {chunk_filename} - {error_msg}", flush=True)
            failed += 1
        else:
            # canceled, expired, etc.
            print(f"  SKIPPED: {chunk_filename} - result type: {entry.result.type}", flush=True)
            failed += 1

        # Mark chunk as processed regardless of outcome
        if chunk_filename not in checkpoint["processed"]:
            checkpoint["processed"].append(chunk_filename)
            _save_processed_chunks(work_dir, checkpoint)

    # Final status update
    _save_batch_status(work_dir, batch_id, "results_processed", {
        "succeeded": succeeded,
        "failed": failed,
        "total_insights": total_insights,
        "high_confidence": total_high,
        "low_confidence": total_low,
    })

    print(f"\nResults: {succeeded} succeeded, {failed} failed", flush=True)
    print(f"Insights: {total_insights} total ({total_high} high/medium, "
          f"{total_low} low)", flush=True)

    return {
        "submitted": succeeded + failed,
        "succeeded": succeeded,
        "failed": failed,
        "total_insights": total_insights,
    }


def resume_batch(batch_id, work_dir, client):
    """Resume polling and processing a previously submitted batch.

    If the batch is still in progress, polls until completion.
    If already complete, downloads and processes results.

    Args:
        batch_id: The batch ID to resume.
        work_dir: Path to the working directory.
        client: An Anthropic client instance.

    Returns:
        dict: Summary with keys: submitted, succeeded, failed, total_insights.
    """
    import time as _time

    print(f"Resuming batch: {batch_id}", flush=True)
    batch = client.messages.batches.retrieve(batch_id)
    print(f"Current status: {batch.processing_status}", flush=True)

    # Poll if still in progress
    while batch.processing_status == "in_progress":
        counts = batch.request_counts
        total = counts.processing + counts.succeeded + counts.errored + counts.canceled + counts.expired
        print(f"  Status: {batch.processing_status} "
              f"(succeeded={counts.succeeded}, errored={counts.errored}, "
              f"processing={counts.processing}/{total})", flush=True)
        _save_batch_status(work_dir, batch_id, batch.processing_status, {
            "total_requests": total,
            "succeeded": counts.succeeded,
            "errored": counts.errored,
        })
        _time.sleep(BATCH_POLL_INTERVAL)
        batch = client.messages.batches.retrieve(batch_id)

    if batch.processing_status == "ended":
        print("Batch complete. Processing results...", flush=True)
        checkpoint = _load_processed_chunks(work_dir)
        return _process_batch_results(batch_id, work_dir, client, checkpoint)
    else:
        print(f"Batch in unexpected state: {batch.processing_status}", flush=True)
        _save_batch_status(work_dir, batch_id, batch.processing_status)
        return {"submitted": 0, "succeeded": 0, "failed": 0, "total_insights": 0}


def run_extraction(args):
    """Main entry point for Phase 2 extraction.

    Handles three modes:
    - --no-batch: synchronous extraction of all chunks
    - --batch-id: resume an existing batch
    - (default): submit new batch and poll for results

    Args:
        args: Parsed argparse namespace with work_dir, channel, no_batch,
              batch_id attributes.
    """
    # Import anthropic inside the function so Phase 1 works without API key
    from anthropic import Anthropic

    # Resolve work directory
    if args.work_dir:
        work_dir = args.work_dir
    else:
        script_dir = Path(__file__).resolve().parent
        work_dir = str(script_dir / "discord_extraction")

    work_path = Path(work_dir)
    chunks_dir = work_path / "chunks"

    # Verify chunks exist
    if not chunks_dir.is_dir():
        print(f"ERROR: chunks directory not found: {chunks_dir}", file=sys.stderr)
        print("Run Phase 1 first (without --extract) to generate chunks.", file=sys.stderr)
        sys.exit(1)

    manifest_path = work_path / "chunk_manifest.json"
    if not manifest_path.exists():
        print("ERROR: chunk_manifest.json not found. Run Phase 1 first.", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"Work directory: {work_dir}", flush=True)
    print(f"Total chunks:   {manifest['total_chunks']}", flush=True)
    print(f"Total tokens:   {manifest['total_tokens']:,}", flush=True)

    # Initialize Anthropic client
    client = Anthropic()

    if args.batch_id:
        # Resume existing batch
        resume_batch(args.batch_id, work_dir, client)

    elif args.no_batch:
        # Synchronous extraction
        checkpoint = _load_processed_chunks(work_dir)
        processed_set = set(checkpoint["processed"])

        high_dir = work_path / "extractions" / "high"
        low_dir = work_path / "extractions" / "low"

        # Determine which chunks to process
        chunks_to_process = []
        for entry in manifest["chunks"]:
            filename = entry["filename"]
            if filename in processed_set:
                continue
            # Filter by channel if specified
            if args.channel and entry.get("channel") != args.channel:
                continue
            chunks_to_process.append(entry)

        if not chunks_to_process:
            print("All matching chunks already processed.", flush=True)
            return

        print(f"\nProcessing {len(chunks_to_process)} chunks synchronously...", flush=True)

        total_insights = 0
        total_high = 0
        total_low = 0
        succeeded = 0
        failed = 0

        for i, entry in enumerate(chunks_to_process, 1):
            filename = entry["filename"]
            chunk_path = chunks_dir / filename

            print(f"\n[{i}/{len(chunks_to_process)}] {filename} "
                  f"({entry.get('channel', '?')}, {entry.get('token_count', 0)} tokens)...",
                  flush=True)

            if not chunk_path.exists():
                print(f"  WARNING: chunk file missing, skipping", flush=True)
                failed += 1
                continue

            with open(chunk_path, encoding="utf-8") as f:
                chunk = json.load(f)

            insights = extract_sync(chunk, client)

            if insights:
                high_count, low_count = _route_insights(
                    insights, filename, high_dir, low_dir
                )
                total_high += high_count
                total_low += low_count
                total_insights += len(insights)
                succeeded += 1
                print(f"  {len(insights)} insights "
                      f"({high_count} high/med, {low_count} low)", flush=True)
            else:
                # Check if we got a raw text failure vs genuinely empty
                succeeded += 1
                print(f"  0 insights", flush=True)

            # Mark as processed
            if filename not in checkpoint["processed"]:
                checkpoint["processed"].append(filename)
                _save_processed_chunks(work_dir, checkpoint)

        print(f"\n{'=' * 60}", flush=True)
        print(f"Sync extraction complete:", flush=True)
        print(f"  Chunks processed: {succeeded + failed} "
              f"({succeeded} succeeded, {failed} failed)", flush=True)
        print(f"  Total insights:   {total_insights} "
              f"({total_high} high/medium, {total_low} low)", flush=True)

    else:
        # Default: submit new batch
        extract_batch(str(chunks_dir), work_dir, client)

    # Print output locations
    high_dir = work_path / "extractions" / "high"
    low_dir = work_path / "extractions" / "low"
    if high_dir.exists():
        high_files = list(high_dir.glob("*.json"))
        print(f"\nHigh/medium confidence: {len(high_files)} files in {high_dir}", flush=True)
    if low_dir.exists():
        low_files = list(low_dir.glob("*.json"))
        print(f"Low confidence:        {len(low_files)} files in {low_dir}", flush=True)


# ---------------------------------------------------------------------------
# Phase 3: Consolidation & Dedup
# ---------------------------------------------------------------------------

def merge_extractions(work_dir):
    """Load all high/medium extraction JSONs, merge into single list sorted by category then confidence."""
    high_dir = Path(work_dir) / "extractions" / "high"
    all_insights = []
    for fp in sorted(high_dir.glob("*.json")):
        with open(fp, encoding="utf-8") as f:
            insights = json.load(f)
        all_insights.extend(insights)

    # Sort by category, then confidence (high first)
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    all_insights.sort(key=lambda x: (x.get("category", ""), confidence_order.get(x.get("confidence", ""), 9)))
    return all_insights


def dedup_insights(insights):
    """Deduplicate insights using sentence-transformers embeddings.

    Groups by (category, primary_unit) for efficiency.
    Uses cosine similarity >= 0.85 to detect duplicates.
    Keeps higher-confidence version, combines authors, keeps earliest date,
    unions replay codes and source_message_ids.

    Assigns stable import_id = sha256(category + insight[:50]).hexdigest()[:12]
    """
    from sentence_transformers import SentenceTransformer
    import numpy as np
    from hashlib import sha256

    model = SentenceTransformer('all-MiniLM-L6-v2')

    # Group by (category, primary_unit)
    groups = defaultdict(list)
    for ins in insights:
        primary_unit = ins.get("units", ["__none__"])[0] if ins.get("units") else "__none__"
        groups[(ins.get("category", ""), primary_unit)].append(ins)

    deduped = []
    duplicates_removed = 0

    for (cat, _unit), group in groups.items():
        if len(group) <= 1:
            for ins in group:
                ins["import_id"] = sha256((cat + ins.get("insight", "")[:50]).encode()).hexdigest()[:12]
            deduped.extend(group)
            continue

        texts = [i["insight"] for i in group]
        embeddings = model.encode(texts, normalize_embeddings=True)

        # Compute cosine similarity matrix
        sim_matrix = np.dot(embeddings, embeddings.T)

        # Find duplicates (greedy: mark later items as duplicates of earlier ones)
        merged_into = {}  # index -> index it was merged into
        for i in range(len(group)):
            if i in merged_into:
                continue
            for j in range(i + 1, len(group)):
                if j in merged_into:
                    continue
                if sim_matrix[i][j] >= 0.85:
                    # Merge j into i
                    _merge_insight(group[i], group[j])
                    merged_into[j] = i
                    duplicates_removed += 1

        for idx, ins in enumerate(group):
            if idx not in merged_into:
                ins["import_id"] = sha256((cat + ins.get("insight", "")[:50]).encode()).hexdigest()[:12]
                deduped.append(ins)

    return deduped, duplicates_removed


def _merge_insight(keep, discard):
    """Merge discard insight into keep insight."""
    confidence_order = {"high": 0, "medium": 1, "low": 2}

    # Keep higher confidence
    if confidence_order.get(discard.get("confidence"), 9) < confidence_order.get(keep.get("confidence"), 9):
        keep["confidence"] = discard["confidence"]
        keep["insight"] = discard["insight"]  # Use the higher-confidence text

    # Combine authors
    keep_author = keep.get("author", "")
    discard_author = discard.get("author", "")
    if discard_author and discard_author not in keep_author:
        keep["author"] = f"{keep_author}, {discard_author}" if keep_author else discard_author

    # Keep earliest date
    if discard.get("date", "9999") < keep.get("date", "9999"):
        keep["date"] = discard["date"]

    # Union replay codes
    keep_codes = keep.get("replay_code")
    discard_codes = discard.get("replay_code")
    if discard_codes and not keep_codes:
        keep["replay_code"] = discard_codes

    # Union source_message_ids
    keep_ids = set(keep.get("source_message_ids", []))
    keep_ids.update(discard.get("source_message_ids", []))
    keep["source_message_ids"] = sorted(keep_ids)


def cross_reference_kb(insights, kb_dir="docs/commentary-knowledge"):
    """Check each insight against existing knowledge base files.

    Sets insight["kb_status"] to: "new", "confirms_existing", or "contradicts_existing".
    Simple approach: search for matching unit names + key terms in existing .md files.
    """
    kb_path = Path(kb_dir)
    kb_text = ""
    for md_file in kb_path.glob("*.md"):
        if md_file.name.startswith("RESEARCH"):
            continue
        with open(md_file, encoding="utf-8") as f:
            kb_text += f.read().lower() + "\n"

    for ins in insights:
        units = [u.lower() for u in ins.get("units", [])]
        insight_lower = ins.get("insight", "").lower()

        # Extract key terms (words > 4 chars that aren't common)
        words = set(re.findall(r'\b[a-z]{5,}\b', insight_lower))

        # Check if any unit + key term combination exists in KB
        matched_units = [u for u in units if u in kb_text]
        matched_terms = [w for w in words if w in kb_text]

        if matched_units and len(matched_terms) >= 2:
            # Likely already covered
            ins["kb_status"] = "confirms_existing"
        else:
            ins["kb_status"] = "new"

        # Note: "contradicts_existing" requires manual review; we flag it
        # in Phase 3.5 by looking for opposing sentiment, not automated here.


def write_consolidated(insights, work_dir, duplicates_removed):
    """Write discord_knowledge_consolidated.json with summary stats."""
    # Build summary
    by_category = defaultdict(int)
    by_confidence = defaultdict(int)
    by_temporal = defaultdict(int)
    by_kb_status = defaultdict(int)

    for ins in insights:
        by_category[ins.get("category", "UNKNOWN")] += 1
        by_confidence[ins.get("confidence", "unknown")] += 1
        by_temporal[ins.get("temporal_validity", "unknown")] += 1
        by_kb_status[ins.get("kb_status", "unknown")] += 1

    output = {
        "summary": {
            "total_after_dedup": len(insights),
            "duplicates_removed": duplicates_removed,
            "by_category": dict(by_category),
            "by_confidence": dict(by_confidence),
            "by_temporal_validity": dict(by_temporal),
            "kb_status": dict(by_kb_status),
        },
        "insights": insights,
    }

    out_path = Path(work_dir) / "discord_knowledge_consolidated.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output["summary"]


def run_consolidation(args):
    """Main entry point for Phase 3: Consolidation & Dedup."""
    work_dir = args.work_dir or str(Path(__file__).resolve().parent / "discord_extraction")
    work_path = Path(work_dir)

    high_dir = work_path / "extractions" / "high"
    if not high_dir.exists():
        print("ERROR: No extractions found. Run --extract first.", file=sys.stderr)
        sys.exit(1)

    print("Phase 3: Consolidation & Dedup", flush=True)
    print("=" * 60, flush=True)

    # 3A: Merge
    print("\n3A. Merging extractions...", flush=True)
    all_insights = merge_extractions(work_dir)
    print(f"  Loaded {len(all_insights)} insights", flush=True)

    # 3B: Dedup
    print("\n3B. Deduplicating with sentence-transformers...", flush=True)
    deduped, dups = dedup_insights(all_insights)
    print(f"  {len(all_insights)} -> {len(deduped)} ({dups} duplicates removed)", flush=True)

    # 3C: Cross-reference
    print("\n3C. Cross-referencing with existing KB...", flush=True)
    cross_reference_kb(deduped)
    new_count = sum(1 for i in deduped if i.get("kb_status") == "new")
    confirms = sum(1 for i in deduped if i.get("kb_status") == "confirms_existing")
    print(f"  New: {new_count}, Confirms existing: {confirms}", flush=True)

    # 3D: Write output
    print("\n3D. Writing consolidated output...", flush=True)
    summary = write_consolidated(deduped, work_dir, dups)

    print(f"\nConsolidation complete.", flush=True)
    print(f"  Output: {work_path / 'discord_knowledge_consolidated.json'}", flush=True)
    print(f"\nCategory distribution:", flush=True)
    for cat, count in sorted(summary["by_category"].items()):
        print(f"  {cat}: {count}", flush=True)


# ---------------------------------------------------------------------------
# Phase 3.5: Human Review Gate (--preview)
# ---------------------------------------------------------------------------

def generate_preview(args):
    """Generate a preview document for human review before Phase 4."""
    work_dir = args.work_dir or str(Path(__file__).resolve().parent / "discord_extraction")
    work_path = Path(work_dir)

    consolidated_path = work_path / "discord_knowledge_consolidated.json"
    if not consolidated_path.exists():
        print("ERROR: No consolidated data. Run --consolidate first.", file=sys.stderr)
        sys.exit(1)

    with open(consolidated_path, encoding="utf-8") as f:
        data = json.load(f)

    summary = data["summary"]
    insights = data["insights"]

    # Build preview markdown
    lines = []
    lines.append("# Discord Knowledge Extraction Preview")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("")

    # Statistics
    lines.append("## Statistics")
    lines.append(f"- After dedup: {summary['total_after_dedup']}")
    lines.append(f"- Duplicates removed: {summary['duplicates_removed']}")
    lines.append(f"- New insights: {summary['kb_status'].get('new', 0)}")
    lines.append(f"- Confirms existing: {summary['kb_status'].get('confirms_existing', 0)}")
    lines.append("")

    # Category distribution table
    lines.append("### Category Distribution")
    lines.append("| Category | Count |")
    lines.append("|---|---|")
    for cat, count in sorted(summary["by_category"].items()):
        lines.append(f"| {cat} | {count} |")
    lines.append("")

    # Temporal validity table
    lines.append("### Temporal Validity")
    lines.append("| Validity | Count |")
    lines.append("|---|---|")
    for val, count in sorted(summary.get("by_temporal_validity", {}).items()):
        lines.append(f"| {val} | {count} |")
    lines.append("")

    # Contradictions (all kb_status == "contradicts_existing")
    contradictions = [i for i in insights if i.get("kb_status") == "contradicts_existing"]
    lines.append(f"## Contradictions ({len(contradictions)} -- ALL require review)")
    if contradictions:
        for i, ins in enumerate(contradictions, 1):
            lines.append(f"\n### Contradiction {i}")
            lines.append(f"- **Insight:** {ins['insight']}")
            lines.append(f"- **Author:** {ins.get('author', '?')} ({ins.get('date', '?')})")
            lines.append(f"- **Category:** {ins.get('category', '?')}")
            lines.append(f"- **Temporal:** {ins.get('temporal_validity', '?')}")
    else:
        lines.append("None detected (automated check only -- manual spot-check recommended).")
    lines.append("")

    # Top 50 high-confidence new insights
    new_high = [i for i in insights if i.get("kb_status") == "new" and i.get("confidence") == "high"]
    new_high.sort(key=lambda x: x.get("category", ""))
    top50 = new_high[:50]
    lines.append(f"## Top {len(top50)} High-Confidence New Insights")
    for i, ins in enumerate(top50, 1):
        lines.append(f"\n{i}. **[{ins.get('category', '?')}]** {ins['insight']}")
        lines.append(f"   - Author: {ins.get('author', '?')} | Date: {ins.get('date', '?')} | Temporal: {ins.get('temporal_validity', '?')}")
        if ins.get("units"):
            lines.append(f"   - Units: {', '.join(ins['units'])}")
    lines.append("")

    # Category samples (5 random per category)
    import random
    lines.append("## Category Samples (up to 5 per category)")
    categories = sorted(set(i.get("category", "UNKNOWN") for i in insights))
    for cat in categories:
        cat_insights = [i for i in insights if i.get("category") == cat]
        sample = random.sample(cat_insights, min(5, len(cat_insights)))
        lines.append(f"\n### {cat} ({len(cat_insights)} total)")
        for ins in sample:
            lines.append(f"- [{ins.get('confidence', '?')}] {ins['insight']}")
            lines.append(f"  _{ins.get('author', '?')}, {ins.get('date', '?')}_")
    lines.append("")

    # Developer checklist
    lines.append("## Developer Checklist")
    lines.append("- [ ] Top 50 insights look genuinely useful to a Prismata player")
    lines.append("- [ ] No category is producing systematically bad extractions")
    lines.append("- [ ] Contradictions reviewed (decide: keep Discord version or KB version)")
    lines.append("- [ ] Confidence levels feel appropriately calibrated")
    lines.append("- [ ] COMMUNITY_JARGON samples look tone-appropriate")
    lines.append("- [ ] Spot-check 5 insights against original Discord messages")
    lines.append("")
    lines.append("**If review fails:** Return to Phase 1.5 and recalibrate. Do NOT proceed with bad extractions.")

    # Write preview
    preview_path = Path("docs/discord-knowledge-extraction-preview.md")
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Preview written to: {preview_path}", flush=True)
    print(f"Review this document before proceeding to --integrate.", flush=True)


# ---------------------------------------------------------------------------
# Phase 4: Integration (--integrate)
# ---------------------------------------------------------------------------

def run_integration(args):
    """Phase 4: Write insights to discord mirror directory."""
    work_dir = args.work_dir or str(Path(__file__).resolve().parent / "discord_extraction")
    work_path = Path(work_dir)

    consolidated_path = work_path / "discord_knowledge_consolidated.json"
    if not consolidated_path.exists():
        print("ERROR: No consolidated data. Run --consolidate first.", file=sys.stderr)
        sys.exit(1)

    with open(consolidated_path, encoding="utf-8") as f:
        data = json.load(f)

    insights = data["insights"]

    # 4A: Create discord mirror directory
    discord_dir = Path("docs/commentary-knowledge/discord")
    discord_dir.mkdir(parents=True, exist_ok=True)

    # Category -> filename mapping
    CATEGORY_FILES = {
        "GAME_MECHANIC": "01-game-fundamentals-discord.md",
        "UNIT_INTERACTION": "03-advanced-units-discord.md",
        "STRATEGY_RULE": "04-strategy-concepts-discord.md",
        "OPENING_THEORY": "05-openings-builds-discord.md",
        "EXPERT_ASSESSMENT": "06-meta-expert-discord.md",
        "BALANCE_OPINION": "08-balance-history-discord.md",
        "COMMUNITY_JARGON": "discord_jargon_review.md",
    }

    # Group insights by category
    by_category = defaultdict(list)
    for ins in insights:
        cat = ins.get("category", "UNKNOWN")
        by_category[cat].append(ins)

    # Write category files
    for cat, cat_insights in sorted(by_category.items()):
        filename = CATEGORY_FILES.get(cat)
        if not filename:
            continue

        filepath = discord_dir / filename
        lines = []

        if cat == "COMMUNITY_JARGON":
            lines.append("# Community Jargon (Manual Review Required)")
            lines.append("")
            lines.append("These items need manual review for tone before any integration.")
            lines.append("")
        else:
            display_cat = cat.replace("_", " ").title()
            lines.append(f"# {display_cat} (Discord)")
            lines.append("")
            lines.append(f"Extracted from Prismata Discord ({len(cat_insights)} insights).")
            lines.append("")

        for ins in cat_insights:
            lines.append(f"### {ins.get('insight', 'No insight text')}")
            if ins.get("units"):
                lines.append(f"**Units:** {', '.join(ins['units'])}")
            lines.append(f"**Confidence:** {ins.get('confidence', '?')} | "
                         f"**Temporal:** {ins.get('temporal_validity', '?')}")
            lines.append(f"> Source: Discord #{ins.get('_channel', 'unknown')} -- "
                         f"{ins.get('author', '?')} ({ins.get('date', '?')})")
            lines.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  Written: {filepath} ({len(cat_insights)} insights)", flush=True)

    # Write low-confidence insights to separate file
    low_dir = work_path / "extractions" / "low"
    if low_dir.exists():
        all_low = []
        for fp in sorted(low_dir.glob("*.json")):
            with open(fp, encoding="utf-8") as f:
                all_low.extend(json.load(f))

        low_path = discord_dir / "discord_low_confidence.json"
        with open(low_path, "w", encoding="utf-8") as f:
            json.dump(all_low, f, indent=2, ensure_ascii=False)
        print(f"  Written: {low_path} ({len(all_low)} low-confidence insights)", flush=True)

    # 4B: Update sources.md
    sources_path = Path("docs/commentary-knowledge/sources.md")
    if sources_path.exists():
        with open(sources_path, encoding="utf-8") as f:
            sources_text = f.read()

        if "Tier 4: Discord" not in sources_text:
            tier4_block = (
                "\n\n### Tier 4: Discord Community Discussion\n"
                "~222,854 messages from Prismata Discord (2015-2026) -- general_chat excluded.\n"
                "Channels: strategy_advice, unit_and_game_design, ask_a_dev, alpha_player_lounge,\n"
                "prismata_chat, questions_and_help, dev_seeking_feedback, Prismata League general.\n"
            )
            with open(sources_path, "a", encoding="utf-8") as f:
                f.write(tier4_block)
            print(f"  Updated: {sources_path} (added Tier 4)", flush=True)

    # 4C: Replay code index
    replay_insights = [i for i in insights if i.get("replay_code")]
    if replay_insights:
        replay_index = []
        for ins in replay_insights:
            replay_index.append({
                "code": ins["replay_code"],
                "channel": ins.get("_channel", "unknown"),
                "author": ins.get("author", "unknown"),
                "date": ins.get("date", "unknown"),
                "discussion_topic": ins.get("context", ""),
                "units_mentioned": ins.get("units", []),
            })

        replay_path = Path("docs/discord-replay-codes.json")
        with open(replay_path, "w", encoding="utf-8") as f:
            json.dump(replay_index, f, indent=2, ensure_ascii=False)
        print(f"  Written: {replay_path} ({len(replay_index)} replay codes)", flush=True)

    # 4D: Update README.md index
    readme_path = Path("docs/commentary-knowledge/README.md")
    if readme_path.exists():
        with open(readme_path, encoding="utf-8") as f:
            readme_text = f.read()

        if "discord/" not in readme_text:
            discord_section = (
                "\n\n### Discord Extractions\n"
                "- `discord/` -- Extracted insights from Prismata Discord (mirror directory, not yet promoted)\n"
                "  - Requires manual review and promotion to main KB files\n"
            )
            with open(readme_path, "a", encoding="utf-8") as f:
                f.write(discord_section)
            print(f"  Updated: {readme_path} (added discord/ section)", flush=True)

    # Write processing stats
    stats = {
        "total_insights": len(insights),
        "by_category": dict(data["summary"]["by_category"]),
        "by_confidence": dict(data["summary"]["by_confidence"]),
        "by_temporal_validity": dict(data["summary"].get("by_temporal_validity", {})),
        "kb_status": dict(data["summary"].get("kb_status", {})),
        "files_created": [str(discord_dir / CATEGORY_FILES[cat]) for cat in by_category if cat in CATEGORY_FILES],
    }
    stats_path = Path("docs/discord-knowledge-extraction-stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"  Written: {stats_path}", flush=True)

    print(f"\n{'=' * 60}", flush=True)
    print(f"Phase 4 complete. Files in: {discord_dir}", flush=True)
    print(f"IMPORTANT: No existing KB files were modified.", flush=True)
    print(f"Promotion to main files is manual (Phase 4D).", flush=True)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Discord Knowledge Extractor for Prismata AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Phases:\n"
            "  (default)    Phase 1: filter, thread, chunk\n"
            "  --dry-run    Phase 1 stats only (no files written)\n"
            "  --extract    Phase 2: Claude Haiku extraction via Batch API\n"
            "  --consolidate Phase 3: dedup and consolidation\n"
            "  --preview    Phase 3.5: generate review preview doc\n"
            "  --integrate  Phase 4: write to commentary KB\n"
        ),
    )

    # Phase 1 flags
    parser.add_argument("--dry-run", action="store_true",
                        help="Phase 1 only: print stats, no API calls, no chunk files")
    parser.add_argument("--channel", type=str, default=None,
                        help="Process single channel only (e.g., strategy_advice)")
    parser.add_argument("--work-dir", type=str, default=None,
                        help="Working directory (default: discord_extraction/ relative to script)")
    parser.add_argument("--exports-dir", type=str, default=DISCORD_EXPORTS_DIR,
                        help=f"Discord exports directory (default: {DISCORD_EXPORTS_DIR})")

    # Phase 2 flags
    parser.add_argument("--extract", action="store_true",
                        help="Phase 2: run Claude Haiku extraction on chunks")
    parser.add_argument("--no-batch", action="store_true",
                        help="Phase 2: use synchronous API instead of Batch API")
    parser.add_argument("--batch-id", type=str, default=None,
                        help="Phase 2: resume/check status of an existing batch")

    # Phase 3 flags
    parser.add_argument("--consolidate", action="store_true",
                        help="Phase 3: consolidate and deduplicate extractions")

    # Phase 3.5 flag
    parser.add_argument("--preview", action="store_true",
                        help="Phase 3.5: generate preview doc for human review")

    # Phase 4 flags
    parser.add_argument("--integrate", action="store_true",
                        help="Phase 4: integrate into commentary knowledge base")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # Phase 2: LLM extraction
    if args.extract or args.batch_id:
        run_extraction(args)
        return

    # Phase 3: Consolidation & Dedup
    if args.consolidate:
        run_consolidation(args)
        return

    # Phase 3.5: Human review gate
    if args.preview:
        generate_preview(args)
        return

    # Phase 4: Integration
    if args.integrate:
        run_integration(args)
        return

    # -----------------------------------------------------------------------
    # Phase 1: Pre-filter, thread grouping, scoring, chunking
    # -----------------------------------------------------------------------

    # Resolve work directory
    if args.work_dir:
        work_dir = args.work_dir
    else:
        script_dir = Path(__file__).resolve().parent
        work_dir = str(script_dir / "discord_extraction")

    print(f"Exports directory: {args.exports_dir}")
    print(f"Work directory:    {work_dir}")
    if args.dry_run:
        print("Mode:              DRY-RUN (stats only, no files written)")
    print()

    # Discover channel files
    print("Discovering channel files...")
    channel_files = discover_channel_files(args.exports_dir)

    if not channel_files:
        print("ERROR: no channel files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(channel_files)} channels: {', '.join(sorted(channel_files.keys()))}")
    print()

    # Determine processing order
    if args.channel:
        if args.channel not in channel_files:
            available = ", ".join(sorted(channel_files.keys()))
            print(f"ERROR: channel '{args.channel}' not found. Available: {available}",
                  file=sys.stderr)
            sys.exit(1)
        channels_to_process = [args.channel]
    else:
        # Use priority order, then append any discovered channels not in the priority list
        channels_to_process = [ch for ch in CHANNEL_PRIORITY if ch in channel_files]
        for ch in sorted(channel_files.keys()):
            if ch not in channels_to_process:
                channels_to_process.append(ch)

    # Process each channel
    all_results = []
    for channel_name in channels_to_process:
        filepath = channel_files[channel_name]
        window = CHANNEL_WINDOWS.get(channel_name, 300)  # default 5 min

        print(f"\n--- Processing: {channel_name} ---")
        result = process_channel(channel_name, filepath, window)
        all_results.append(result)

    # Output
    if args.dry_run:
        print_dry_run(all_results)
    else:
        print(f"\nWriting chunks to {work_dir}/chunks/...")
        total_written = write_chunks(all_results, work_dir)
        print(f"Wrote {total_written} chunk files.")
        print(f"Manifest: {work_dir}/chunk_manifest.json")

        # Print summary
        total_tokens = sum(r["total_tokens"] for r in all_results)
        total_threads = sum(r["scored_count"] for r in all_results)
        print(f"\nSummary: {total_written} chunks, {total_threads} threads, {total_tokens:,} tokens")

    print("\nDone.")


if __name__ == "__main__":
    main()
