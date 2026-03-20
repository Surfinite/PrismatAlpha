"""Opening book output formatting — report JSON, config entries, validation, summary.

Converts analysis dicts from ob_analysis into:
  - Config-ready OB entries for config.txt
  - Validation against existing LiveOpeningBook2 entries
  - Human-readable stdout summary
  - Full report JSON
"""
import json

from replay_parser.ob_analysis import DD_FOLLOWUP_STATES, STARTING_STATES

# Abbreviations for compact summary display
UNIT_ABBREVS = {
    "Drone": "D",
    "Engineer": "E",
    "Conduit": "C",
    "Blastforge": "B",
    "Animus": "A",
    "Wall": "W",
    "Tarsier": "T",
    "Rhino": "R",
    "Steelsplitter": "SS",
    "Forcefield": "FF",
    "Gauss Cannon": "GC",
}


def _abbrev_buy(buy_list):
    """Abbreviate a buy list for display.  Dominion units use first 3 chars."""
    parts = [UNIT_ABBREVS.get(name, name[:3]) for name in buy_list]
    return "+".join(parts)


def _buy_hash_to_set(buy_hash):
    """Convert a comma-separated buy_hash to a frozenset for order-independent comparison."""
    if not buy_hash:
        return frozenset()
    return frozenset(buy_hash.split(","))


def _buy_hash_to_list(buy_hash):
    """Convert a comma-separated buy_hash to a sorted list."""
    if not buy_hash:
        return []
    return buy_hash.split(",")


def _self_state_to_drone_count(self_state):
    """Extract drone count from a self state list like [["Drone", 6], ["Engineer", 2]]."""
    for name, count in self_state:
        if name == "Drone":
            return count
    return 0


def _player_and_turn_from_self(self_state):
    """Determine player (0 or 1) and turn (1 or 2) from the self state drone count.

    6D = P0 turn 1, 7D = P1 turn 1, 8D = P0 turn 2, 9D = P1 turn 2.
    Returns (player, turn) or (None, None) if unrecognized.
    """
    drone_count = _self_state_to_drone_count(self_state)
    mapping = {6: (0, 1), 7: (1, 1), 8: (0, 2), 9: (1, 2)}
    return mapping.get(drone_count, (None, None))


# ---------------------------------------------------------------------------
# 1. generate_ob_entries
# ---------------------------------------------------------------------------

def generate_ob_entries(analysis):
    """Generate config.txt-ready OB entries from analysis results.

    Produces entries for each strong/moderate consensus result in turn1, turn2,
    and pair analysis.

    Returns a list of dicts, each with keys:
        _comment, self, enemy, buyable, buy, _source (metadata for tracking)
    """
    entries = []

    # Turn 1 entries
    for unit_name, sides in analysis.get("turn1_analysis", {}).items():
        for pkey in ("p0", "p1"):
            result = sides.get(pkey)
            if not result:
                continue
            consensus = result.get("consensus", "contested")
            if consensus not in ("strong", "moderate"):
                continue
            player = int(pkey[1])
            self_state = [list(pair) for pair in STARTING_STATES[player]]
            buy_list = result["top_5"][0]["buy_sequence"] if result.get("top_5") else []
            if not buy_list:
                continue
            freq_pct = round(result["frequency"] * 100, 1)
            entry = {
                "_comment": f"{unit_name} (P{player + 1} T1) -- "
                            f"{freq_pct}% consensus, "
                            f"{result['total_games']} games, {consensus}",
                "self": self_state,
                "enemy": [],
                "buyable": [unit_name],
                "buy": buy_list,
            }
            entries.append({
                **entry,
                "_source": {
                    "type": "turn1",
                    "unit": unit_name,
                    "player": player,
                    "consensus": consensus,
                    "frequency": result["frequency"],
                    "win_rate": result["win_rate"],
                    "sample_size": result["sample_size"],
                },
            })

    # Turn 2 entries
    for unit_name, sides in analysis.get("turn2_analysis", {}).items():
        for pkey in ("p0", "p1"):
            result = sides.get(pkey)
            if not result:
                continue
            consensus = result.get("consensus", "contested")
            if consensus not in ("strong", "moderate"):
                continue
            player = int(pkey[1])
            self_state = [list(pair) for pair in DD_FOLLOWUP_STATES[player]]
            buy_list = result["top_5"][0]["buy_sequence"] if result.get("top_5") else []
            if not buy_list:
                continue
            freq_pct = round(result["frequency"] * 100, 1)
            entry = {
                "_comment": f"{unit_name} (P{player + 1} T2 post-DD) -- "
                            f"{freq_pct}% consensus, "
                            f"{result['total_games']} games, {consensus}",
                "self": self_state,
                "enemy": [],
                "buyable": [unit_name],
                "buy": buy_list,
            }
            entries.append({
                **entry,
                "_source": {
                    "type": "turn2",
                    "unit": unit_name,
                    "player": player,
                    "consensus": consensus,
                    "frequency": result["frequency"],
                    "win_rate": result["win_rate"],
                    "sample_size": result["sample_size"],
                },
            })

    # Pair entries
    for unit_name, pairs in analysis.get("pair_analysis", {}).items():
        for pair_result in pairs:
            consensus = pair_result.get("consensus", "contested")
            if consensus not in ("strong", "moderate"):
                continue
            player = pair_result["player"]
            partner = pair_result["partner"]
            self_state = [list(pair) for pair in STARTING_STATES[player]]
            # Pair results don't carry top_5; parse from top_buy hash
            buy_list = _buy_hash_to_list(pair_result.get("top_buy", ""))
            if not buy_list:
                continue
            freq_pct = round(pair_result["frequency"] * 100, 1)
            buyable = sorted([unit_name, partner])
            entry = {
                "_comment": f"{unit_name}+{partner} (P{player + 1} T1) -- "
                            f"{freq_pct}% consensus, "
                            f"{pair_result['total_games']} games, {consensus}",
                "self": self_state,
                "enemy": [],
                "buyable": buyable,
                "buy": buy_list,
            }
            entries.append({
                **entry,
                "_source": {
                    "type": "pair",
                    "unit": unit_name,
                    "partner": partner,
                    "player": player,
                    "consensus": consensus,
                    "frequency": pair_result["frequency"],
                    "win_rate": pair_result["win_rate"],
                    "sample_size": pair_result["sample_size"],
                },
            })

    return entries


# ---------------------------------------------------------------------------
# 2. load_existing_ob
# ---------------------------------------------------------------------------

def load_existing_ob(config_path):
    """Load LiveOpeningBook2 entries from config.txt.

    Config structure: {"Opening Books": {"LiveOpeningBook2": [...]}}.
    Returns the list of OB entry dicts, or [] if not found.
    """
    with open(config_path, "r") as f:
        config = json.load(f)
    ob = config.get("Opening Books", {})
    return ob.get("LiveOpeningBook2", [])


# ---------------------------------------------------------------------------
# 3. validate_against_existing
# ---------------------------------------------------------------------------

def validate_against_existing(analysis, existing_entries):
    """Compare analysis results against existing LiveOpeningBook2 entries.

    For each existing entry, determines whether the analysis confirms,
    contradicts, or has insufficient data for the entry.

    Returns a dict with lists:
        confirmed    — existing entries that match analysis top buy
        contradicted — existing entries where analysis disagrees
        new          — analysis entries not present in existing OB
        unmatched    — existing entries we can't map to analysis
        insufficient — existing entries where analysis has no data
    """
    result = {
        "confirmed": [],
        "contradicted": [],
        "new": [],
        "unmatched": [],
        "insufficient": [],
    }

    # Index existing entries by (player, turn, buyable_set) for matching
    existing_indexed = []
    for entry in existing_entries:
        self_state = entry.get("self", [])
        player, turn = _player_and_turn_from_self(self_state)
        buyable = frozenset(entry.get("buyable", []))
        buy_set = frozenset(entry.get("buy", []))
        existing_indexed.append({
            "entry": entry,
            "player": player,
            "turn": turn,
            "buyable": buyable,
            "buy_set": buy_set,
        })

    # Track which analysis entries are matched
    matched_analysis_keys = set()

    for ei in existing_indexed:
        player = ei["player"]
        turn = ei["turn"]
        buyable = ei["buyable"]

        if player is None:
            result["unmatched"].append(ei["entry"])
            continue

        pkey = f"p{player}"

        # Determine which analysis section to look in
        analysis_result = None
        match_key = None

        if turn == 1 and len(buyable) == 1:
            # Single unit turn 1
            unit_name = next(iter(buyable))
            unit_data = analysis.get("turn1_analysis", {}).get(unit_name, {})
            analysis_result = unit_data.get(pkey)
            match_key = ("turn1", unit_name, player)

        elif turn == 1 and len(buyable) == 2:
            # Pair turn 1 — find in pair_analysis
            for unit_name in buyable:
                pairs = analysis.get("pair_analysis", {}).get(unit_name, [])
                partner = next(iter(buyable - {unit_name}))
                for pr in pairs:
                    if pr["partner"] == partner and pr["player"] == player:
                        # Build a pseudo analysis_result for comparison
                        analysis_result = pr
                        match_key = ("pair", unit_name, partner, player)
                        break
                if analysis_result:
                    break

        elif turn == 2 and len(buyable) == 1:
            # Single unit turn 2
            unit_name = next(iter(buyable))
            unit_data = analysis.get("turn2_analysis", {}).get(unit_name, {})
            analysis_result = unit_data.get(pkey)
            match_key = ("turn2", unit_name, player)

        elif turn == 1 and len(buyable) == 0:
            # Generic DD entry (no specific unit) — can't validate
            result["unmatched"].append(ei["entry"])
            continue

        else:
            result["unmatched"].append(ei["entry"])
            continue

        if analysis_result is None:
            result["unmatched"].append(ei["entry"])
            continue

        if match_key:
            matched_analysis_keys.add(match_key)

        # Check data sufficiency
        if analysis_result.get("status") == "insufficient" or \
                analysis_result.get("total_games", 0) == 0:
            result["insufficient"].append(ei["entry"])
            continue

        # Compare buy hashes (order-independent)
        analysis_buy_hash = analysis_result.get("top_buy", "")
        analysis_buy_set = _buy_hash_to_set(analysis_buy_hash)
        existing_buy_set = ei["buy_set"]

        if analysis_buy_set == existing_buy_set:
            result["confirmed"].append(ei["entry"])
        else:
            result["contradicted"].append({
                "existing": ei["entry"],
                "analysis_top_buy": sorted(analysis_buy_set) if analysis_buy_set else [],
                "analysis_frequency": analysis_result.get("frequency", 0.0),
                "analysis_consensus": analysis_result.get("consensus", "unknown"),
            })

    # Find new entries: strong/moderate results not in existing OB
    for unit_name, sides in analysis.get("turn1_analysis", {}).items():
        for pkey in ("p0", "p1"):
            r = sides.get(pkey)
            if not r:
                continue
            player = int(pkey[1])
            if r.get("consensus") not in ("strong", "moderate"):
                continue
            key = ("turn1", unit_name, player)
            if key not in matched_analysis_keys:
                result["new"].append({
                    "type": "turn1",
                    "unit": unit_name,
                    "player": player,
                    "consensus": r["consensus"],
                    "top_buy": r["top_buy"],
                    "frequency": r["frequency"],
                })

    for unit_name, sides in analysis.get("turn2_analysis", {}).items():
        for pkey in ("p0", "p1"):
            r = sides.get(pkey)
            if not r:
                continue
            player = int(pkey[1])
            if r.get("consensus") not in ("strong", "moderate"):
                continue
            key = ("turn2", unit_name, player)
            if key not in matched_analysis_keys:
                result["new"].append({
                    "type": "turn2",
                    "unit": unit_name,
                    "player": player,
                    "consensus": r["consensus"],
                    "top_buy": r["top_buy"],
                    "frequency": r["frequency"],
                })

    for unit_name, pairs in analysis.get("pair_analysis", {}).items():
        for pr in pairs:
            if pr.get("consensus") not in ("strong", "moderate"):
                continue
            partner = pr["partner"]
            player = pr["player"]
            key = ("pair", unit_name, partner, player)
            key_rev = ("pair", partner, unit_name, player)
            if key not in matched_analysis_keys and \
                    key_rev not in matched_analysis_keys:
                result["new"].append({
                    "type": "pair",
                    "unit": unit_name,
                    "partner": partner,
                    "player": player,
                    "consensus": pr["consensus"],
                    "top_buy": pr["top_buy"],
                    "frequency": pr["frequency"],
                })

    return result


# ---------------------------------------------------------------------------
# 4. build_summary
# ---------------------------------------------------------------------------

def build_summary(analysis, entries, validation):
    """Build a human-readable summary string for stdout.

    Sections: strong consensus, turn 2, pair analysis, validation results.
    """
    lines = []
    params = analysis.get("parameters", {})

    lines.append("=" * 60)
    lines.append("OPENING BOOK ANALYSIS SUMMARY")
    lines.append(f"  min_rating={params.get('min_rating', '?')}, "
                 f"min_samples={params.get('min_samples', '?')}, "
                 f"strong>={params.get('strong_threshold', '?')}, "
                 f"moderate>={params.get('pair_threshold', '?')}")
    lines.append("=" * 60)

    # --- Turn 1 strong/moderate consensus ---
    lines.append("")
    lines.append("--- TURN 1 CONSENSUS ---")

    turn1 = analysis.get("turn1_analysis", {})
    t1_count = 0
    for unit_name in sorted(turn1.keys()):
        sides = turn1[unit_name]
        for pkey in ("p0", "p1"):
            r = sides.get(pkey)
            if not r:
                continue
            consensus = r.get("consensus", "contested")
            if consensus not in ("strong", "moderate"):
                continue
            t1_count += 1
            player = int(pkey[1])
            buy_list = r["top_5"][0]["buy_sequence"] if r.get("top_5") else []
            buy_str = _abbrev_buy(buy_list) if buy_list else "?"
            wr_pct = round(r["win_rate"] * 100, 1)
            freq_pct = round(r["frequency"] * 100, 1)
            lines.append(
                f"  P{player + 1} {unit_name:<22s} "
                f"{buy_str:<20s} "
                f"{freq_pct:5.1f}% freq  "
                f"{wr_pct:5.1f}% WR  "
                f"n={r['sample_size']}/{r['total_games']}  "
                f"[{consensus}]"
            )

    if t1_count == 0:
        lines.append("  (none)")
    lines.append(f"  Total: {t1_count} entries")

    # --- Turn 2 ---
    lines.append("")
    lines.append("--- TURN 2 (POST-DD) CONSENSUS ---")

    turn2 = analysis.get("turn2_analysis", {})
    t2_count = 0
    for unit_name in sorted(turn2.keys()):
        sides = turn2[unit_name]
        for pkey in ("p0", "p1"):
            r = sides.get(pkey)
            if not r:
                continue
            consensus = r.get("consensus", "contested")
            if consensus not in ("strong", "moderate"):
                continue
            t2_count += 1
            player = int(pkey[1])
            buy_list = r["top_5"][0]["buy_sequence"] if r.get("top_5") else []
            buy_str = _abbrev_buy(buy_list) if buy_list else "?"
            freq_pct = round(r["frequency"] * 100, 1)
            wr_pct = round(r["win_rate"] * 100, 1)
            state = r.get("state", "?")
            lines.append(
                f"  P{player + 1} {unit_name:<22s} "
                f"{buy_str:<20s} "
                f"{freq_pct:5.1f}% freq  "
                f"{wr_pct:5.1f}% WR  "
                f"n={r['sample_size']}/{r['total_games']}  "
                f"[{consensus}] ({state})"
            )

    if t2_count == 0:
        lines.append("  (none)")
    lines.append(f"  Total: {t2_count} entries")

    # --- Pair analysis ---
    lines.append("")
    lines.append("--- PAIR ANALYSIS (CONTESTED UNITS) ---")

    pair_analysis = analysis.get("pair_analysis", {})
    pair_count = 0
    for unit_name in sorted(pair_analysis.keys()):
        pairs = pair_analysis[unit_name]
        for pr in pairs:
            consensus = pr.get("consensus", "contested")
            if consensus not in ("strong", "moderate"):
                continue
            pair_count += 1
            player = pr["player"]
            partner = pr["partner"]
            buy_list = _buy_hash_to_list(pr.get("top_buy", ""))
            buy_str = _abbrev_buy(buy_list) if buy_list else "?"
            freq_pct = round(pr["frequency"] * 100, 1)
            wr_pct = round(pr["win_rate"] * 100, 1)
            lines.append(
                f"  P{player + 1} {unit_name:<16s}+{partner:<16s} "
                f"{buy_str:<20s} "
                f"{freq_pct:5.1f}% freq  "
                f"{wr_pct:5.1f}% WR  "
                f"n={pr['sample_size']}/{pr['total_games']}  "
                f"[{consensus}]"
            )

    if pair_count == 0:
        lines.append("  (none)")
    lines.append(f"  Total: {pair_count} pair entries")

    # --- Validation ---
    lines.append("")
    lines.append("--- VALIDATION vs LiveOpeningBook2 ---")
    lines.append(f"  Confirmed:    {len(validation.get('confirmed', []))}")
    lines.append(f"  Contradicted: {len(validation.get('contradicted', []))}")
    lines.append(f"  New:          {len(validation.get('new', []))}")
    lines.append(f"  Unmatched:    {len(validation.get('unmatched', []))}")
    lines.append(f"  Insufficient: {len(validation.get('insufficient', []))}")

    contradicted = validation.get("contradicted", [])
    if contradicted:
        lines.append("")
        lines.append("  Contradicted entries:")
        for c in contradicted:
            existing = c["existing"]
            existing_buy = existing.get("buy", [])
            analysis_buy = c.get("analysis_top_buy", [])
            freq_pct = round(c.get("analysis_frequency", 0.0) * 100, 1)
            buyable = existing.get("buyable", [])
            unit_str = ",".join(buyable) if buyable else "generic"
            lines.append(
                f"    {unit_str}: "
                f"existing={_abbrev_buy(existing_buy)}, "
                f"analysis={_abbrev_buy(analysis_buy)} "
                f"({freq_pct}% freq, {c.get('analysis_consensus', '?')})"
            )

    new_entries = validation.get("new", [])
    if new_entries:
        lines.append("")
        lines.append("  New entries (not in existing OB):")
        for n in new_entries:
            buy_list = _buy_hash_to_list(n.get("top_buy", ""))
            buy_str = _abbrev_buy(buy_list) if buy_list else "?"
            freq_pct = round(n.get("frequency", 0.0) * 100, 1)
            unit = n.get("unit", "?")
            partner = n.get("partner")
            player = n.get("player", 0)
            entry_type = n.get("type", "?")
            if partner:
                lines.append(
                    f"    P{player + 1} {unit}+{partner} ({entry_type}): "
                    f"{buy_str} ({freq_pct}% freq, {n.get('consensus', '?')})"
                )
            else:
                lines.append(
                    f"    P{player + 1} {unit} ({entry_type}): "
                    f"{buy_str} ({freq_pct}% freq, {n.get('consensus', '?')})"
                )

    # --- Generated entries count ---
    lines.append("")
    lines.append(f"--- GENERATED: {len(entries)} config-ready OB entries ---")
    lines.append("=" * 60)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. build_report
# ---------------------------------------------------------------------------

def build_report(analysis, entries, validation):
    """Build the full report dict combining all outputs.

    Returns a JSON-serializable dict with:
        parameters, turn1_analysis, turn2_analysis, pair_analysis,
        generated_entries, validation, summary_stats
    """
    # Strip _source from entries for the config-ready list
    config_entries = []
    for e in entries:
        clean = {k: v for k, v in e.items() if k != "_source"}
        config_entries.append(clean)

    pairs_resolved = sum(
        1 for pairs in analysis.get("pair_analysis", {}).values()
        for p in pairs
        if p.get("consensus") in ("strong", "moderate")
    )

    # Count consensus categories across turn1
    t1_strong = 0
    t1_moderate = 0
    t1_contested = 0
    for sides in analysis.get("turn1_analysis", {}).values():
        for pkey in ("p0", "p1"):
            r = sides.get(pkey)
            if not r:
                continue
            c = r.get("consensus", "contested")
            if c == "strong":
                t1_strong += 1
            elif c == "moderate":
                t1_moderate += 1
            else:
                t1_contested += 1

    return {
        "parameters": analysis.get("parameters", {}),
        "turn1_analysis": analysis.get("turn1_analysis", {}),
        "turn2_analysis": analysis.get("turn2_analysis", {}),
        "pair_analysis": analysis.get("pair_analysis", {}),
        "generated_entries": config_entries,
        "validation": validation,
        "summary_stats": {
            "units_analyzed": len(analysis.get("turn1_analysis", {})),
            "turn1_strong": t1_strong,
            "turn1_moderate": t1_moderate,
            "turn1_contested": t1_contested,
            "turn2_entries": sum(
                1 for sides in analysis.get("turn2_analysis", {}).values()
                for pkey in ("p0", "p1")
                if sides.get(pkey) and
                sides[pkey].get("consensus") in ("strong", "moderate")
            ),
            "pairs_resolved": pairs_resolved,
            "total_generated": len(entries),
            "validation_confirmed": len(validation.get("confirmed", [])),
            "validation_contradicted": len(validation.get("contradicted", [])),
            "validation_new": len(validation.get("new", [])),
        },
    }
