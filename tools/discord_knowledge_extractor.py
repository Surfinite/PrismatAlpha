#!/usr/bin/env python
"""Discord Knowledge Extractor for Prismata AI.

Phase 1: Pre-filter, thread grouping, quality scoring, and chunking of Discord
export JSON files. Produces numbered chunk files ready for LLM extraction.

Phases 2-4 (extraction, consolidation, integration) are stubbed for later.

Usage:
    # Dry-run: stats only, no files written
    python tools/discord_knowledge_extractor.py --dry-run

    # Dry-run for a single channel (calibration)
    python tools/discord_knowledge_extractor.py --dry-run --channel strategy_advice

    # Full Phase 1: produce chunk files
    python tools/discord_knowledge_extractor.py

    # Single channel chunk generation
    python tools/discord_knowledge_extractor.py --channel strategy_advice
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
            "  --extract    Phase 2: Claude Haiku extraction (TODO)\n"
            "  --consolidate Phase 3: dedup and consolidation (TODO)\n"
            "  --integrate  Phase 4: write to commentary KB (TODO)\n"
            "  --preview    Phase 3.5: generate review preview doc (TODO)\n"
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

    # Phase 2 flags (stub)
    parser.add_argument("--extract", action="store_true",
                        help="Phase 2: run Claude Haiku extraction on chunks (TODO)")
    parser.add_argument("--no-batch", action="store_true",
                        help="Phase 2: use synchronous API instead of Batch API (TODO)")
    parser.add_argument("--batch-id", type=str, default=None,
                        help="Phase 2: resume/check status of an existing batch (TODO)")

    # Phase 3 flags (stub)
    parser.add_argument("--consolidate", action="store_true",
                        help="Phase 3: consolidate and deduplicate extractions (TODO)")

    # Phase 4 flags (stub)
    parser.add_argument("--integrate", action="store_true",
                        help="Phase 4: integrate into commentary knowledge base (TODO)")

    # Phase 3.5 flag (stub)
    parser.add_argument("--preview", action="store_true",
                        help="Phase 3.5: generate preview doc for human review (TODO)")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # Phase 2 stub
    if args.extract:
        # TODO: Phase 2 — Claude Haiku extraction via Batch API
        # - Load chunks from work_dir/chunks/
        # - Build extraction prompt with chunk content
        # - Submit to Anthropic Batch API (or synchronous with --no-batch)
        # - Validate JSON schema on responses
        # - Route high/medium confidence to extractions/high/
        # - Route low confidence to extractions/low/
        # - Update processed_chunks.json for checkpoint/resume
        print("ERROR: Phase 2 (extraction) not yet implemented.", file=sys.stderr)
        sys.exit(1)

    # Phase 3 stub
    if args.consolidate:
        # TODO: Phase 3 — Consolidation & deduplication
        # - Merge all extraction JSONs
        # - Embedding-based dedup with sentence-transformers (all-MiniLM-L6-v2)
        # - Cross-reference with existing docs/commentary-knowledge/*.md
        # - Flag contradictions for manual review
        # - Generate discord_knowledge_consolidated.json
        print("ERROR: Phase 3 (consolidation) not yet implemented.", file=sys.stderr)
        sys.exit(1)

    # Phase 3.5 stub
    if args.preview:
        # TODO: Phase 3.5 — Generate preview doc
        # - Load consolidated JSON
        # - Generate docs/discord-knowledge-extraction-preview.md
        # - Include: statistics, contradictions, top 50, category samples
        print("ERROR: Phase 3.5 (preview) not yet implemented.", file=sys.stderr)
        sys.exit(1)

    # Phase 4 stub
    if args.integrate:
        # TODO: Phase 4 — Integration into commentary knowledge base
        # - Create docs/commentary-knowledge/discord/ mirror directory
        # - Write category-specific files (01-game-fundamentals-discord.md, etc.)
        # - Route COMMUNITY_JARGON to discord_jargon_review.md
        # - Route low-confidence to discord_low_confidence.json
        # - Create docs/discord-replay-codes.json index
        # - Update docs/commentary-knowledge/sources.md
        # - DO NOT modify existing canonical KB files
        print("ERROR: Phase 4 (integration) not yet implemented.", file=sys.stderr)
        sys.exit(1)

    # Batch ID check stub
    if args.batch_id:
        # TODO: Phase 2 — Check batch status / download results
        # - client.batches.retrieve(batch_id)
        # - If complete: download and process results
        # - If pending: print progress and exit
        print("ERROR: Batch status check not yet implemented.", file=sys.stderr)
        sys.exit(1)

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
