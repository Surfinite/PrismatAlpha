"""Search Discord exports for AI/bot-related strategic feedback.

Scans exported Discord JSON files for messages discussing Master Bot behavior,
unit valuation issues, AI mistakes, and strategic insights relevant to
improving the heuristic move generation system.

Usage:
    python tools/search_discord_ai_feedback.py [export_dir] [--output results.json]

Default export_dir: c:/libraries/prismata-replay-parser/discord_exports_full/
Falls back to: discord_exports_all/, discord_exports/
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

# Keywords grouped by category
KEYWORD_GROUPS = {
    "bot_behavior": [
        r"\bmaster\s*bot\b", r"\bMB\b", r"\bbot\s+(does|doesn'?t|won'?t|can'?t|always|never)",
        r"\bbot\s+(buy|attack|block|breach|snipe|chill|target|kill|sacrifice)",
        r"\bAI\s+(does|doesn'?t|won'?t|can'?t|always|never|bug|mistake|wrong|bad|dumb|stupid)",
    ],
    "valuation_issues": [
        r"\bovervalue[sd]?\b", r"\bundervalue[sd]?\b", r"\bmisvalue[sd]?\b",
        r"\bwrong\s+value\b", r"\bbad\s+value\b",
        r"\bcost.*wrong\b", r"\bworth\s+(more|less)\b",
        r"\bshould\s+(buy|not\s+buy|block|not\s+block|target|snipe|breach|kill)",
    ],
    "targeting_issues": [
        r"\btarget(s|ed|ing)?\s+(wrong|bad|dumb|stupid|weird)",
        r"\bsnipe(s|d)?\s+(wrong|bad|dumb|instead)",
        r"\bbreach(es|ed|ing)?\s+(wrong|bad|instead)",
        r"\bchill(s|ed|ing)?\s+(wrong|bad|instead)",
        r"\bkill(s|ed|ing)?\s+(wrong|instead|galvani|drone|wall)",
        r"\babsorb\s+on\s+(empty|corpus)",
    ],
    "unit_specific": [
        r"\bcorpus\b.*\b(bot|AI|MB|absorb|husk|wrong|bad)\b",
        r"\b(bot|AI|MB)\b.*\bcorpus\b",
        r"\bborehole\b.*\b(bot|AI|MB|pixie|overvalue|wrong)\b",
        r"\b(bot|AI|MB)\b.*\bborehole\b",
        r"\bgalvani\b.*\b(bot|AI|MB|target|kill|snipe|wrong)\b",
        r"\b(bot|AI|MB)\b.*\bgalvani\b",
        r"\bforcefield\b.*\b(bot|AI|MB|block|wrong)\b",
        r"\b(bot|AI|MB)\b.*\bforcefield\b",
        r"\btantalum\b.*\b(bot|AI|MB|target|health|wrong)\b",
        r"\b(bot|AI|MB)\b.*\btantalum\b",
    ],
    "strategic_insight": [
        r"\bopening\s+(is|should|always|never|best|worst|wrong)",
        r"\bturn\s*\d+\s+(buy|should|always|never)",
        r"\b(rush|timing|econ|economy|greed|greedy|tempo|pressure)\b.*\b(better|worse|wrong|right|correct)\b",
    ],
    "commentary_feedback": [
        r"\bcommentar(y|ies|ator)\b",
        r"\banalysis\b.*\b(game|replay|match)\b",
        r"\b(game|replay|match)\b.*\banalysis\b",
        r"\bSurfinite\b.*\b(bot|AI|cool|nice|awesome|amazing|great|love|neat)\b",
        r"\b(bot|AI)\b.*\b(commentat|analys|narrat|post|recap)\b",
        r"\b(cool|nice|awesome|amazing|neat)\b.*\b(bot|AI|analysis|commentary)\b",
        r"\bPrismatAI\b",
        r"\bPrismatAlpha\b",
        r"\bneural\s*(net|network|AI|eval)\b",
    ],
}


def compile_patterns():
    compiled = {}
    for group, patterns in KEYWORD_GROUPS.items():
        compiled[group] = [re.compile(p, re.IGNORECASE) for p in patterns]
    return compiled


def search_message(content, compiled_patterns):
    """Return list of (group, pattern) matches for a message."""
    matches = []
    for group, patterns in compiled_patterns.items():
        for pattern in patterns:
            if pattern.search(content):
                matches.append((group, pattern.pattern))
                break  # one match per group is enough
    return matches


def get_context_messages(messages, idx, window=2):
    """Get surrounding messages for context."""
    start = max(0, idx - window)
    end = min(len(messages), idx + window + 1)
    context = []
    for i in range(start, end):
        msg = messages[i]
        author = msg.get("author", {}).get("name", "Unknown")
        content = msg.get("content", "")
        if content:
            prefix = ">>>" if i == idx else "   "
            context.append(f"{prefix} {author}: {content[:200]}")
    return context


def scan_file(filepath, compiled_patterns):
    """Scan a single Discord export JSON file."""
    results = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  WARNING: Could not parse {os.path.basename(filepath)}: {e}")
        return results

    channel_name = data.get("channel", {}).get("name", "unknown")
    guild_name = data.get("guild", {}).get("name", "unknown")
    messages = data.get("messages", [])

    for idx, msg in enumerate(messages):
        content = msg.get("content", "")
        if not content or len(content) < 10:
            continue

        # Also check embeds
        embed_text = ""
        for embed in msg.get("embeds", []):
            embed_text += " " + embed.get("description", "")
            embed_text += " " + embed.get("title", "")
            for field in embed.get("fields", []):
                embed_text += " " + field.get("name", "") + " " + field.get("value", "")

        full_text = content + embed_text
        matches = search_message(full_text, compiled_patterns)

        if matches:
            author = msg.get("author", {}).get("name", "Unknown")
            timestamp = msg.get("timestamp", "")[:19]
            is_bot = msg.get("author", {}).get("isBot", False)

            results.append({
                "guild": guild_name,
                "channel": channel_name,
                "author": author,
                "is_bot": is_bot,
                "timestamp": timestamp,
                "content": content[:500],
                "categories": [m[0] for m in matches],
                "matched_patterns": [m[1] for m in matches],
                "context": get_context_messages(messages, idx),
            })

    return results


def main():
    # Find export directory
    default_dirs = [
        "c:/libraries/prismata-replay-parser/discord_exports_full",
        "c:/libraries/prismata-replay-parser/discord_exports_all",
        "c:/libraries/prismata-replay-parser/discord_exports",
    ]

    export_dir = None
    output_file = "discord_ai_feedback.json"

    args = sys.argv[1:]
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--output" and i + 1 < len(args):
            output_file = args[i + 1]
            skip_next = True
        elif not arg.startswith("--"):
            export_dir = arg

    if not export_dir:
        for d in default_dirs:
            if os.path.isdir(d):
                export_dir = d
                break

    if not export_dir or not os.path.isdir(export_dir):
        print(f"ERROR: No export directory found. Tried: {default_dirs}")
        print("Run tools/export_discord_full.sh first, or pass directory as argument.")
        sys.exit(1)

    print(f"Scanning: {export_dir}")
    compiled = compile_patterns()

    all_results = []
    json_files = [f for f in os.listdir(export_dir) if f.endswith(".json")]
    print(f"Found {len(json_files)} JSON files")

    for filename in sorted(json_files):
        filepath = os.path.join(export_dir, filename)
        results = scan_file(filepath, compiled)
        if results:
            print(f"  {filename}: {len(results)} matches")
        all_results.extend(results)

    # Sort by timestamp
    all_results.sort(key=lambda r: r.get("timestamp", ""))

    # Summary statistics
    category_counts = defaultdict(int)
    author_counts = defaultdict(int)
    for r in all_results:
        for cat in r["categories"]:
            category_counts[cat] += 1
        author_counts[r["author"]] += 1

    summary = {
        "scan_date": datetime.now().isoformat()[:19],
        "export_dir": export_dir,
        "files_scanned": len(json_files),
        "total_matches": len(all_results),
        "by_category": dict(category_counts),
        "top_contributors": dict(sorted(author_counts.items(), key=lambda x: -x[1])[:20]),
    }

    output = {"summary": summary, "results": all_results}

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n=== Summary ===")
    print(f"Total matches: {len(all_results)}")
    print(f"By category:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print(f"Top contributors:")
    for author, count in sorted(author_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {author}: {count}")
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
