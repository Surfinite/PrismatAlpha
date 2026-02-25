#!/usr/bin/env python
"""Compare F6 ground-truth states against C++ --dump-states output.

Usage:
    python tools/compare_engine_states.py \
        --f6 f6_ground_truth.json \
        --cpp state_dump.jsonl \
        [--card-library bin/asset/config/cardLibrary.jso] \
        [--output comparison_report.json]

Phase 3 of the Replay State Verification plan.

F6 states come from capture_replay_states.py (Phase 2).
C++ states come from Prismata_Testing.exe --dump-states (Phase 1).

Key differences handled:
  - C++ card names are internal (e.g. "Tesla Tower"), F6 uses display names ("Tarsier")
  - Lifespan encoding: C++ outputs -1 for no-limit, F6 may output 0 or -1
  - F6 has instId per card; C++ does not -- instId is not compared
  - F6 'blocking' field can be stale -- not compared
"""

import argparse
import json
import os

import sys
from collections import Counter


# ---------------------------------------------------------------------------
# Name mapping: internal <-> display
# ---------------------------------------------------------------------------

def load_name_mapping(card_library_path):
    """Parse cardLibrary.jso and return internal<->display name mappings.

    cardLibrary.jso is a non-standard JSON file where the top-level keys are
    the internal card names. Cards with a different display name have a
    "UIName" field.

    Returns:
        (internal_to_display, display_to_internal) dicts.
        Cards without UIName map to themselves in both directions.
    """
    with open(card_library_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # The file is valid JSON with top-level keys being card names
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse card library: {e}", file=sys.stderr)
        sys.exit(1)

    internal_to_display = {}
    display_to_internal = {}

    for internal_name, card_def in data.items():
        if not isinstance(card_def, dict):
            continue

        # Check for UIName (case-insensitive key check)
        ui_name = None
        for key in card_def:
            if key.lower() == "uiname":
                ui_name = card_def[key]
                break

        display_name = ui_name if ui_name else internal_name
        internal_to_display[internal_name] = display_name
        display_to_internal[display_name] = internal_name

    return internal_to_display, display_to_internal


# ---------------------------------------------------------------------------
# State normalization
# ---------------------------------------------------------------------------

def _parse_mana(mana_str):
    """Parse a mana string like '6BGGG' into a canonical sorted form.

    Returns the original string -- we compare mana strings directly since
    both engines should produce the same format.
    """
    if not mana_str:
        return ""
    return str(mana_str)


def _normalize_lifespan(val):
    """Normalize lifespan encoding differences.

    C++ outputs: -1 when lifespan==0 (no limit), else the actual countdown.
    F6 outputs:  -1 for no limit (most cases), sometimes 0.
    Normalize: values <= 0 become 0 (meaning 'no limit').
    """
    if val is None:
        return 0
    val = int(val)
    if val <= 0:
        return 0
    return val


def _normalize_role(role_str):
    """Normalize role/status string to lowercase."""
    if not role_str:
        return "default"
    return str(role_str).lower().strip()


def _normalize_deadness(val):
    """Normalize deadness value."""
    if not val:
        return "alive"
    return str(val).lower().strip()


def _normalize_unit(unit, name_map=None):
    """Normalize a single unit entry to a comparable dict.

    Args:
        unit: dict from table entry
        name_map: if provided, maps internal->display names for the cardName

    Returns:
        Normalized dict with canonical field names and values.
    """
    card_name = unit.get("cardName", "")
    if name_map and card_name in name_map:
        card_name = name_map[card_name]

    return {
        "cardName": card_name,
        "owner": int(unit.get("owner", -1)),
        "health": int(unit.get("health", 0)),
        "chill": int(unit.get("disruptDamage", 0)),
        "role": _normalize_role(unit.get("role", "default")),
        "charge": int(unit.get("charge", 0)),
        "constructionTime": int(unit.get("constructionTime", 0)),
        "delay": int(unit.get("delay", 0)),
        "lifespan": _normalize_lifespan(unit.get("lifespan", -1)),
        "deadness": _normalize_deadness(unit.get("deadness", "alive")),
    }


def _unit_sort_key(unit):
    """Sort key for order-independent unit comparison.

    Sort by (owner, cardName, constructionTime, health, role, charge, delay).
    This should uniquely identify most units even when there are duplicates.
    """
    return (
        unit["owner"],
        unit["cardName"],
        unit["constructionTime"],
        unit["health"],
        unit["role"],
        unit["charge"],
        unit["delay"],
        unit["lifespan"],
        unit["chill"],
        unit["deadness"],
    )


def normalize_f6_state(f6_data):
    """Extract comparable fields from F6 JSON.

    F6 structure: {"CurrentInfo": {"gameState": {...}, "mergedDeck": [...]}}
    or bare: {"gameState": {...}}
    or directly: {"whiteMana": ..., "table": [...]}
    """
    # Navigate to gameState
    inner = f6_data
    if "CurrentInfo" in inner:
        inner = inner["CurrentInfo"]
    if "gameState" in inner:
        inner = inner["gameState"]

    # Extract scalar fields
    result = {
        "numTurns": int(inner.get("numTurns", -1)),
        "activePlayer": int(inner.get("turn", -1)),
        "phase": str(inner.get("phase", "unknown")).lower(),
        "whiteMana": _parse_mana(inner.get("whiteMana", "")),
        "blackMana": _parse_mana(inner.get("blackMana", "")),
    }

    # Extract and normalize units
    table = inner.get("table", [])
    units = [_normalize_unit(u) for u in table]
    units.sort(key=_unit_sort_key)
    result["units"] = units
    result["unit_count"] = len(units)

    # Extract supply info (for reference, compared as arrays)
    result["cards"] = inner.get("cards", [])
    result["whiteTotalSupply"] = inner.get("whiteTotalSupply", [])
    result["blackTotalSupply"] = inner.get("blackTotalSupply", [])
    result["whiteSupplySpent"] = inner.get("whiteSupplySpent", [])
    result["blackSupplySpent"] = inner.get("blackSupplySpent", [])

    return result


def normalize_cpp_state(cpp_entry, internal_to_display):
    """Extract comparable fields from a C++ dump state entry.

    cpp_entry is a parsed JSON dict with {"turn": N, "player": P, "state": {...}}.
    The state.table[].cardName uses internal names that need mapping.
    The state.cards[] uses UINames (display names) already.
    """
    state = cpp_entry.get("state", cpp_entry)

    result = {
        "numTurns": int(state.get("numTurns", -1)),
        "activePlayer": int(state.get("turn", -1)),
        "phase": str(state.get("phase", "unknown")).lower(),
        "whiteMana": _parse_mana(state.get("whiteMana", "")),
        "blackMana": _parse_mana(state.get("blackMana", "")),
    }

    # Extract and normalize units -- map internal names to display names
    table = state.get("table", [])
    units = [_normalize_unit(u, name_map=internal_to_display) for u in table]
    units.sort(key=_unit_sort_key)
    result["units"] = units
    result["unit_count"] = len(units)

    # Extract supply info
    result["cards"] = state.get("cards", [])
    result["whiteTotalSupply"] = state.get("whiteTotalSupply", [])
    result["blackTotalSupply"] = state.get("blackTotalSupply", [])
    result["whiteSupplySpent"] = state.get("whiteSupplySpent", [])
    result["blackSupplySpent"] = state.get("blackSupplySpent", [])

    return result


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

_SCALAR_FIELDS = ["activePlayer", "phase", "whiteMana", "blackMana"]
_SUPPLY_FIELDS = ["cards", "whiteTotalSupply", "blackTotalSupply",
                  "whiteSupplySpent", "blackSupplySpent"]
_UNIT_FIELDS = ["cardName", "owner", "health", "chill", "role", "charge",
                "constructionTime", "delay", "lifespan", "deadness"]


def compare_states(f6_norm, cpp_norm, turn):
    """Compare two normalized states and return a list of mismatch dicts.

    Each mismatch: {"turn": N, "field": "description", "f6": val, "cpp": val}

    Returns empty list if states match.
    """
    mismatches = []

    # Compare scalar fields
    for field in _SCALAR_FIELDS:
        f6_val = f6_norm.get(field)
        cpp_val = cpp_norm.get(field)
        if f6_val != cpp_val:
            mismatches.append({
                "turn": turn,
                "field": field,
                "f6": f6_val,
                "cpp": cpp_val,
            })

    # Compare supply arrays
    for field in _SUPPLY_FIELDS:
        f6_val = f6_norm.get(field, [])
        cpp_val = cpp_norm.get(field, [])
        if f6_val != cpp_val:
            mismatches.append({
                "turn": turn,
                "field": field,
                "f6": f6_val,
                "cpp": cpp_val,
            })

    # Compare unit counts
    f6_count = f6_norm["unit_count"]
    cpp_count = cpp_norm["unit_count"]
    if f6_count != cpp_count:
        mismatches.append({
            "turn": turn,
            "field": "unit_count",
            "f6": f6_count,
            "cpp": cpp_count,
        })
        # Also report which units are extra/missing
        f6_names = Counter(u["cardName"] for u in f6_norm["units"])
        cpp_names = Counter(u["cardName"] for u in cpp_norm["units"])
        extra_in_f6 = f6_names - cpp_names
        extra_in_cpp = cpp_names - f6_names
        if extra_in_f6:
            mismatches.append({
                "turn": turn,
                "field": "units_extra_in_f6",
                "f6": dict(extra_in_f6),
                "cpp": None,
            })
        if extra_in_cpp:
            mismatches.append({
                "turn": turn,
                "field": "units_extra_in_cpp",
                "f6": None,
                "cpp": dict(extra_in_cpp),
            })

    # Compare individual units if counts match
    if f6_count == cpp_count:
        f6_units = f6_norm["units"]
        cpp_units = cpp_norm["units"]
        for idx in range(f6_count):
            f6_u = f6_units[idx]
            cpp_u = cpp_units[idx]
            for field in _UNIT_FIELDS:
                f6_val = f6_u.get(field)
                cpp_val = cpp_u.get(field)
                if f6_val != cpp_val:
                    # Build a descriptive field name
                    unit_desc = f"unit[{idx}].{field}"
                    # Add card name context for clarity
                    name_hint = f6_u.get("cardName", "?")
                    owner_hint = f6_u.get("owner", "?")
                    mismatches.append({
                        "turn": turn,
                        "field": unit_desc,
                        "unit": f"P{owner_hint} {name_hint}",
                        "f6": f6_val,
                        "cpp": cpp_val,
                    })

    return mismatches


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_f6_states(filepath):
    """Load F6 ground truth states from capture_replay_states.py output.

    Expected format: {"states": [{"turn": N, "f6_json": {...}}, ...]}
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    states = data.get("states", [])
    result = {}
    for entry in states:
        turn = entry.get("turn", -999)
        f6_json = entry.get("f6_json", {})
        result[turn] = f6_json

    return result


def load_cpp_states(filepath):
    """Load C++ state dump from --dump-states JSONL output.

    Each line is a JSON object. Last line may be a summary (skip it).
    """
    result = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"WARNING: Skipping malformed JSONL line {line_num}: {e}",
                      file=sys.stderr)
                continue

            # Skip summary line
            if entry.get("summary", False):
                continue

            turn = entry.get("turn", -999)
            result[turn] = entry

    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(f6_states, cpp_states, internal_to_display):
    """Compare all aligned turns and produce a full report.

    Returns:
        (summary_text, detailed_report_dict)
    """
    f6_turns = set(f6_states.keys())
    cpp_turns = set(cpp_states.keys())
    aligned_turns = sorted(f6_turns & cpp_turns)
    f6_only = sorted(f6_turns - cpp_turns)
    cpp_only = sorted(cpp_turns - f6_turns)

    per_turn_results = []
    all_mismatches = []
    match_count = 0
    mismatch_count = 0
    first_mismatch_turn = None
    category_counts = Counter()

    for turn in aligned_turns:
        f6_norm = normalize_f6_state(f6_states[turn])
        cpp_norm = normalize_cpp_state(cpp_states[turn], internal_to_display)
        mismatches = compare_states(f6_norm, cpp_norm, turn)

        if mismatches:
            mismatch_count += 1
            if first_mismatch_turn is None:
                first_mismatch_turn = turn
            per_turn_results.append({
                "turn": turn,
                "status": "MISMATCH",
                "mismatches": mismatches,
            })
            all_mismatches.extend(mismatches)
            for m in mismatches:
                # Categorize: scalar field or unit.field
                field = m["field"]
                if field.startswith("unit["):
                    # Extract the unit field part after the dot
                    dot_pos = field.find(".")
                    if dot_pos >= 0:
                        cat = "unit." + field[dot_pos + 1:]
                    else:
                        cat = field
                else:
                    cat = field
                category_counts[cat] += 1
        else:
            match_count += 1
            per_turn_results.append({
                "turn": turn,
                "status": "MATCH",
            })

    # Build human-readable summary
    lines = []
    lines.append("Replay State Comparison")
    lines.append("=======================")
    lines.append(f"F6 states: {len(f6_turns)} turns")
    lines.append(f"C++ states: {len(cpp_turns)} turns")
    lines.append(f"Aligned turns: {len(aligned_turns)}")
    if f6_only:
        lines.append(f"F6-only turns (not in C++): {f6_only}")
    if cpp_only:
        lines.append(f"C++-only turns (not in F6): {cpp_only}")
    lines.append("")

    for entry in per_turn_results:
        turn = entry["turn"]
        turn_label = "init" if turn == -1 else str(turn).rjust(4)
        if entry["status"] == "MATCH":
            lines.append(f"Turn {turn_label}: MATCH")
        else:
            # Show first mismatch for this turn
            first_m = entry["mismatches"][0]
            field = first_m["field"]
            f6_val = first_m["f6"]
            cpp_val = first_m["cpp"]
            extra = ""
            if len(entry["mismatches"]) > 1:
                extra = f" (+{len(entry['mismatches']) - 1} more)"
            lines.append(
                f"Turn {turn_label}: MISMATCH - {field} "
                f"(F6: {_fmt_val(f6_val)}, C++: {_fmt_val(cpp_val)}){extra}"
            )

    lines.append("")
    total_aligned = len(aligned_turns)
    if total_aligned > 0:
        pct = 100.0 * match_count / total_aligned
        lines.append(f"Summary: {match_count}/{total_aligned} turns match ({pct:.1f}%)")
    else:
        lines.append("Summary: No aligned turns to compare")

    if first_mismatch_turn is not None:
        lines.append(f"First mismatch: Turn {first_mismatch_turn}")

    if category_counts:
        cats_str = ", ".join(
            f"{cat}: {count}" for cat, count in category_counts.most_common()
        )
        lines.append(f"Categories: {cats_str}")

    summary_text = "\n".join(lines)

    # Build detailed JSON report
    detailed_report = {
        "f6_turn_count": len(f6_turns),
        "cpp_turn_count": len(cpp_turns),
        "aligned_turn_count": len(aligned_turns),
        "match_count": match_count,
        "mismatch_count": mismatch_count,
        "match_rate": round(100.0 * match_count / total_aligned, 2) if total_aligned > 0 else 0,
        "first_mismatch_turn": first_mismatch_turn,
        "f6_only_turns": f6_only,
        "cpp_only_turns": cpp_only,
        "category_counts": dict(category_counts.most_common()),
        "per_turn": per_turn_results,
        "all_mismatches": all_mismatches,
    }

    return summary_text, detailed_report


def _fmt_val(val):
    """Format a value for human-readable display."""
    if isinstance(val, str):
        return f'"{val}"'
    if isinstance(val, dict):
        return json.dumps(val, separators=(",", ":"))
    if isinstance(val, list) and len(val) > 6:
        return f"[{len(val)} items]"
    return str(val)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compare F6 ground-truth states against C++ --dump-states output."
    )
    parser.add_argument(
        "--f6",
        required=True,
        help="F6 ground truth JSON file (from capture_replay_states.py)",
    )
    parser.add_argument(
        "--cpp",
        required=True,
        help="C++ state dump JSONL file (from --dump-states)",
    )
    parser.add_argument(
        "--card-library",
        default="bin/asset/config/cardLibrary.jso",
        help="Path to cardLibrary.jso (default: bin/asset/config/cardLibrary.jso)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Write detailed JSON report to this file",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed mismatches for each turn",
    )
    args = parser.parse_args()

    # Validate inputs
    for label, path in [("F6", args.f6), ("C++", args.cpp),
                        ("Card library", args.card_library)]:
        if not os.path.isfile(path):
            print(f"ERROR: {label} file not found: {path}", file=sys.stderr)
            sys.exit(1)

    # Load name mapping
    internal_to_display = load_name_mapping(args.card_library)[0]
    print(f"Loaded {len(internal_to_display)} card name mappings", file=sys.stderr)

    # Load states
    f6_states = load_f6_states(args.f6)
    cpp_states = load_cpp_states(args.cpp)
    print(f"Loaded {len(f6_states)} F6 states, {len(cpp_states)} C++ states",
          file=sys.stderr)

    # Generate comparison report
    summary_text, detailed_report = generate_report(
        f6_states, cpp_states, internal_to_display
    )

    # Print summary to stdout
    print(summary_text)

    # Print verbose detail if requested
    if args.verbose and detailed_report["all_mismatches"]:
        print("\n\nDetailed Mismatches")
        print("===================")
        current_turn = None
        for m in detailed_report["all_mismatches"]:
            if m["turn"] != current_turn:
                current_turn = m["turn"]
                turn_label = "init" if current_turn == -1 else str(current_turn)
                print(f"\n--- Turn {turn_label} ---")
            unit_ctx = f" [{m['unit']}]" if "unit" in m else ""
            print(f"  {m['field']}{unit_ctx}: F6={_fmt_val(m['f6'])}  C++={_fmt_val(m['cpp'])}")

    # Write detailed JSON report if requested
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(detailed_report, f, indent=2, ensure_ascii=False)
        print(f"\nDetailed report written to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
