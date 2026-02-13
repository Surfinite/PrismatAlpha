#!/usr/bin/env python3
"""
Opening Book Extraction from Expert Replays

Parses 12,957 expert replay games from training_data.jsonl to extract
opening patterns at multiple aggregation levels:
- Universal: cross-set buy patterns by round and seat
- Per-unit: early-buy win rate impact for all 105 non-base units
- Tech timing: when experts first buy Conduit/Blastforge/Animus
- Per-pair: Spyrfyr's base+2 synergy analysis (all 5,460 pairs)
- Per-triple: extended triple analysis (33,219+ triples with 10+ games)

Pure Python, stdlib only. All output to training/data/.
"""

import json
import math
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

JSONL_PATH = r"c:\libraries\prismata-replay-parser\training_data.jsonl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def elo_expected(self_rating, opp_rating):
    """Expected win probability based on Elo ratings."""
    return 1.0 / (1.0 + 10.0 ** ((opp_rating - self_rating) / 400.0))


def wilson_lower(wins, n, z=1.96):
    """Wilson score lower bound (95% CI) for win rate ranking."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (center - spread) / denom


def percentile(sorted_values, pct):
    """Compute percentile from a pre-sorted list. pct in [0, 100]."""
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[f]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def median(values):
    """Compute median of an unsorted list."""
    s = sorted(values)
    return percentile(s, 50)


def r4(v):
    """Round a float to 4 decimal places, or return None."""
    if v is None:
        return None
    return round(v, 4)


def compute_bucket_stats(entries):
    """Compute win rate, Wilson, and Elo-residual stats for a list of
    (won: bool, self_rating: float, opp_rating: float) entries.
    Returns a dict with all stats, or None if empty."""
    if not entries:
        return None
    count = len(entries)
    wins = sum(1 for w, _, _ in entries if w)
    win_rate = wins / count if count else 0
    sum_expected = sum(elo_expected(sr, opr) for _, sr, opr in entries)
    residual_wins = wins - sum_expected
    residual_wr = residual_wins / count if count else 0
    avg_self = sum(sr for _, sr, _ in entries) / count
    avg_opp = sum(opr for _, _, opr in entries) / count
    avg_diff = sum(sr - opr for _, sr, opr in entries) / count
    return {
        "count": count,
        "wins": wins,
        "win_rate": r4(win_rate),
        "wilson_lower": r4(wilson_lower(wins, count)),
        "avg_self_rating": r4(avg_self),
        "avg_opponent_rating": r4(avg_opp),
        "avg_rating_diff": r4(avg_diff),
        "sum_expected_wins": r4(sum_expected),
        "residual_win_rate": r4(residual_wr),
    }


def compute_bucket_stats_slim(entries):
    """Like compute_bucket_stats but with fewer fields (for triples)."""
    if not entries:
        return None
    count = len(entries)
    wins = sum(1 for w, _, _ in entries if w)
    win_rate = wins / count if count else 0
    sum_expected = sum(elo_expected(sr, opr) for _, sr, opr in entries)
    residual_wr = (wins - sum_expected) / count if count else 0
    return {
        "count": count,
        "wins": wins,
        "win_rate": r4(win_rate),
        "wilson_lower": r4(wilson_lower(wins, count)),
        "residual_win_rate": r4(residual_wr),
    }


def compute_bucket_stats_minimal(entries):
    """Minimal stats (for none-bought buckets with potentially small n)."""
    if not entries:
        return None
    count = len(entries)
    wins = sum(1 for w, _, _ in entries if w)
    win_rate = wins / count if count else 0
    result = {
        "count": count,
        "wins": wins,
        "win_rate": r4(win_rate),
    }
    if count >= 5:
        result["wilson_lower"] = r4(wilson_lower(wins, count))
        sum_expected = sum(elo_expected(sr, opr) for _, sr, opr in entries)
        result["residual_win_rate"] = r4((wins - sum_expected) / count)
    return result


# ---------------------------------------------------------------------------
# Step 1: Load and Group
# ---------------------------------------------------------------------------

def load_games():
    """Load JSONL and build per-game structure with per-player openings."""
    games = {}
    total_lines = 0

    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            d = json.loads(line)
            code = d["replay_code"]
            player = d["active_player"]
            rnd = d["turn"]
            bought = sorted(d["action"]["bought"])

            if code not in games:
                games[code] = {
                    "card_set": d["state"]["card_set"],
                    "result": d["result"],
                    "p0_rating": d["p0_rating"],
                    "p1_rating": d["p1_rating"],
                    "players": defaultdict(list),
                }
            games[code]["players"][player].append({
                "round": rnd,
                "bought": bought,
            })

    # Sort each player's turns by round and extract first-4 openings
    openings = []  # list of (code, player, opening_seq, won, self_rating, opp_rating, card_set)
    skipped = 0
    for code, game in games.items():
        for player, turns in game["players"].items():
            turns.sort(key=lambda t: t["round"])
            if len(turns) < 4:
                skipped += 1
                continue
            opening = [t["bought"] for t in turns[:4]]
            won = (game["result"] == 0 and player == 0) or \
                  (game["result"] == 1 and player == 1)
            if player == 0:
                self_r = game["p0_rating"]
                opp_r = game["p1_rating"]
            else:
                self_r = game["p1_rating"]
                opp_r = game["p0_rating"]
            openings.append((code, player, opening, won, self_r, opp_r, game["card_set"]))

    print(f"Total JSONL lines:       {total_lines:,}", file=sys.stderr)
    print(f"Total unique games:      {len(games):,}", file=sys.stderr)
    print(f"Player-openings used:    {len(openings):,}  (skipped {skipped} with <4 turns)", file=sys.stderr)

    return games, openings, total_lines, skipped


# ---------------------------------------------------------------------------
# Step 2: Detect Base Set
# ---------------------------------------------------------------------------

def detect_base_set(games):
    card_freq = Counter()
    for game in games.values():
        for card in game["card_set"]:
            card_freq[card] += 1
    n_games = len(games)
    base_set = {card for card, count in card_freq.items() if count == n_games}
    expected = {"Drone", "Engineer", "Conduit", "Blastforge", "Animus",
                "Forcefield", "Gauss Cannon", "Wall", "Steelsplitter", "Tarsier", "Rhino"}
    assert base_set == expected, f"Base set mismatch! Detected: {base_set}, Expected: {expected}"
    print(f"Base set auto-detected:  {len(base_set)} cards (matches expected)", file=sys.stderr)
    return base_set


# ---------------------------------------------------------------------------
# Step 5a: Universal Openings
# ---------------------------------------------------------------------------

def generate_universal_openings(games, openings, base_set):
    """Cross-set buy patterns by round and seat, with deck-size breakdown."""

    def build_round_data(filtered_openings):
        """Build per-round stats for a list of openings."""
        result = {}
        for rnd_idx in range(4):
            rnd_num = rnd_idx + 1
            buy_counter = Counter()
            empty_count = 0
            for _, _, opening, _, _, _, _ in filtered_openings:
                buy = tuple(opening[rnd_idx])
                buy_counter[buy] += 1
                if not buy:
                    empty_count += 1
            total = len(filtered_openings)
            top_buys = []
            for buy, count in buy_counter.most_common(30):
                top_buys.append({
                    "buy": list(buy),
                    "count": count,
                    "pct": r4(count / total) if total else 0,
                })
            result[f"round_{rnd_num}"] = {
                "top_buys": top_buys,
                "empty_buy_count": empty_count,
                "unique_buy_combos": len(buy_counter),
            }
        return result

    # Split by seat
    p0_openings = [o for o in openings if o[1] == 0]
    p1_openings = [o for o in openings if o[1] == 1]

    by_seat = {
        "p0": build_round_data(p0_openings),
        "p1": build_round_data(p1_openings),
    }

    # Split by deck size
    def deck_size_key(card_set):
        dom = set(card_set) - base_set
        return f"base_plus_{len(dom)}"

    deck_groups = defaultdict(list)
    deck_game_counts = Counter()
    for o in openings:
        dk = deck_size_key(o[6])
        deck_groups[dk].append(o)
    for game in games.values():
        dk = deck_size_key(game["card_set"])
        deck_game_counts[dk] += 1

    by_deck_size = {}
    for dk in sorted(deck_groups.keys()):
        group = deck_groups[dk]
        p0_group = [o for o in group if o[1] == 0]
        p1_group = [o for o in group if o[1] == 1]
        by_deck_size[dk] = {
            "game_count": deck_game_counts[dk],
            "p0": build_round_data(p0_group),
            "p1": build_round_data(p1_group),
        }

    return {
        "metadata": {
            "total_games": len(games),
            "total_p0_openings": len(p0_openings),
            "total_p1_openings": len(p1_openings),
            "description": "Expert buy patterns across all games, aggregated by round and seat",
        },
        "by_seat": by_seat,
        "by_deck_size": by_deck_size,
    }


# ---------------------------------------------------------------------------
# Step 5b: Unit Opening Impact
# ---------------------------------------------------------------------------

def generate_unit_opening_impact(games, openings, base_set):
    """Per non-base-set unit: early-buy win rate impact."""

    # Collect all non-base units
    all_units = set()
    for game in games.values():
        for card in game["card_set"]:
            if card not in base_set:
                all_units.add(card)

    # For each unit, collect stats from openings where the unit is in the card set
    unit_stats = {}
    for unit in sorted(all_units):
        in_set_count = 0
        bought_entries = []     # (won, self_r, opp_r)
        not_bought_entries = [] # (won, self_r, opp_r)
        first_bought_rounds = []

        for code, player, opening, won, self_r, opp_r, card_set in openings:
            if unit not in card_set:
                continue
            in_set_count += 1

            # Check if unit was bought in the opening (first 4 rounds)
            bought_round = None
            for rnd_idx, buys in enumerate(opening):
                if unit in buys:
                    bought_round = rnd_idx + 1  # 1-indexed
                    break

            entry = (won, self_r, opp_r)
            if bought_round is not None:
                bought_entries.append(entry)
                first_bought_rounds.append(bought_round)
            else:
                not_bought_entries.append(entry)

        # Also count how many games have this unit (not just openings)
        game_count = sum(1 for g in games.values() if unit in g["card_set"])

        bought_stats = compute_bucket_stats(bought_entries)
        not_bought_stats = compute_bucket_stats(not_bought_entries)

        # First-bought-round distribution stats
        fbr_sorted = sorted(first_bought_rounds)
        fbr_avg = sum(fbr_sorted) / len(fbr_sorted) if fbr_sorted else None
        fbr_med = percentile(fbr_sorted, 50) if fbr_sorted else None
        fbr_p25 = percentile(fbr_sorted, 25) if fbr_sorted else None
        fbr_p75 = percentile(fbr_sorted, 75) if fbr_sorted else None

        # Impact deltas
        bought_wr = bought_stats["win_rate"] if bought_stats else 0
        not_bought_wr = not_bought_stats["win_rate"] if not_bought_stats else 0
        bought_res = bought_stats["residual_win_rate"] if bought_stats else 0
        not_bought_res = not_bought_stats["residual_win_rate"] if not_bought_stats else 0

        unit_stats[unit] = {
            "in_card_set_count": game_count,
            "openings_analyzed": in_set_count,
            "first_bought_round_avg": r4(fbr_avg),
            "first_bought_round_median": r4(fbr_med),
            "first_bought_round_p25": r4(fbr_p25),
            "first_bought_round_p75": r4(fbr_p75),
            "bought_in_opening": bought_stats,
            "not_bought_in_opening": not_bought_stats,
            "impact_delta": r4(bought_wr - not_bought_wr),
            "residual_impact_delta": r4(bought_res - not_bought_res),
        }

    # Sort by residual_impact_delta descending
    sorted_units = sorted(unit_stats.keys(),
                          key=lambda u: unit_stats[u]["residual_impact_delta"] or 0,
                          reverse=True)
    ordered = {}
    for u in sorted_units:
        ordered[u] = unit_stats[u]

    return {
        "metadata": {
            "total_units_analyzed": len(all_units),
            "min_games_threshold": 50,
            "early_cutoff_round": 4,
            "description": "Per-unit impact of early purchasing on win rate",
        },
        "units": ordered,
    }


# ---------------------------------------------------------------------------
# Step 5c: Tech Timing
# ---------------------------------------------------------------------------

def generate_tech_timing(openings):
    """When experts first buy tech buildings."""

    tech_names = ["Conduit", "Blastforge", "Animus"]
    tech_results = {}

    for tech in tech_names:
        all_first_rounds = []
        by_seat_data = {"p0": [], "p1": []}
        openings_with = 0
        openings_without = 0

        for code, player, opening, won, self_r, opp_r, card_set in openings:
            first_round = None
            for rnd_idx, buys in enumerate(opening):
                if tech in buys:
                    first_round = rnd_idx + 1
                    break
            seat = f"p{player}"
            if first_round is not None:
                openings_with += 1
                all_first_rounds.append(first_round)
                by_seat_data[seat].append(first_round)
            else:
                openings_without += 1

        # Distribution
        dist = Counter(all_first_rounds)
        dist_dict = {str(k): v for k, v in sorted(dist.items())}

        # Aggregate stats
        fbr_sorted = sorted(all_first_rounds)
        fbr_avg = sum(fbr_sorted) / len(fbr_sorted) if fbr_sorted else None
        fbr_med = percentile(fbr_sorted, 50) if fbr_sorted else None
        fbr_p25 = percentile(fbr_sorted, 25) if fbr_sorted else None
        fbr_p75 = percentile(fbr_sorted, 75) if fbr_sorted else None

        # Per-seat stats
        seat_stats = {}
        for seat in ["p0", "p1"]:
            rounds = sorted(by_seat_data[seat])
            if rounds:
                seat_stats[seat] = {
                    "openings_with_purchase": len(rounds),
                    "first_buy_round_avg": r4(sum(rounds) / len(rounds)),
                    "first_buy_round_median": r4(percentile(rounds, 50)),
                    "first_buy_round_p25": r4(percentile(rounds, 25)),
                    "first_buy_round_p75": r4(percentile(rounds, 75)),
                }
            else:
                seat_stats[seat] = {
                    "openings_with_purchase": 0,
                    "first_buy_round_avg": None,
                    "first_buy_round_median": None,
                    "first_buy_round_p25": None,
                    "first_buy_round_p75": None,
                }

        tech_results[tech] = {
            "games_in_card_set": len(openings),  # tech is base-set, always present
            "openings_with_purchase": openings_with,
            "openings_without_purchase": openings_without,
            "first_buy_round_distribution": dist_dict,
            "first_buy_round_avg": r4(fbr_avg),
            "first_buy_round_median": r4(fbr_med),
            "first_buy_round_p25": r4(fbr_p25),
            "first_buy_round_p75": r4(fbr_p75),
            "by_seat": seat_stats,
        }

    return {
        "metadata": {
            "description": "When experts first purchase tech buildings. Round numbers are 1-indexed game rounds.",
            "note": "P0 starts with 6 Drones (6 gold round 1). P1 starts with 7 Drones (7 gold round 1). Tech costs: Conduit=4G, Blastforge=5GG, Animus=6GR.",
            "ai_thresholds": {
                "legacy": {"Conduit": "10 gold", "Blastforge": "11 gold", "Animus": "9 gold"},
                "improved": {"Conduit": "7 gold", "Blastforge": "8 gold", "Animus": "6 gold"},
            },
        },
        "tech_buildings": tech_results,
    }


# ---------------------------------------------------------------------------
# Step 5d: Pair Opening Analysis
# ---------------------------------------------------------------------------

def generate_pair_analysis(games, openings, base_set):
    """Per-pair synergy analysis for all non-base-set unit pairs."""

    # Build per-game dominion set and index openings by game code
    game_dominions = {}
    for code, game in games.items():
        dom = tuple(sorted(set(game["card_set"]) - base_set))
        game_dominions[code] = dom

    # Index openings by code for quick lookup
    openings_by_code = defaultdict(list)
    for o in openings:
        openings_by_code[o[0]].append(o)

    # Count pair occurrences and collect per-pair openings
    pair_games = Counter()       # pair -> game count
    pair_openings = defaultdict(list)  # pair -> list of openings

    for code, dom in game_dominions.items():
        for pair in combinations(dom, 2):
            pair_games[pair] += 1

        # Add openings for this game to all pairs in its dominion
        for o in openings_by_code.get(code, []):
            for pair in combinations(dom, 2):
                pair_openings[pair].append(o)

    # Analyze each pair
    pairs_result = {}
    for pair in sorted(pair_games.keys()):
        if pair_games[pair] < 10:
            continue

        olist = pair_openings[pair]
        unit_a, unit_b = pair

        either_entries = []
        both_entries = []
        neither_entries = []
        opening_when_either = Counter()

        for code, player, opening, won, self_r, opp_r, card_set in olist:
            flat_buys = set()
            for buys in opening:
                flat_buys.update(buys)
            bought_a = unit_a in flat_buys
            bought_b = unit_b in flat_buys

            entry = (won, self_r, opp_r)
            if bought_a or bought_b:
                either_entries.append(entry)
                # Track most common opening sequence
                key = tuple(tuple(b) for b in opening)
                opening_when_either[key] += 1
            if bought_a and bought_b:
                both_entries.append(entry)
            if not bought_a and not bought_b:
                neither_entries.append(entry)

        # Most common opening when either bought
        most_common_opening = None
        if opening_when_either:
            best_key = opening_when_either.most_common(1)[0][0]
            most_common_opening = [list(rnd) for rnd in best_key]

        pair_key = f"{unit_a}+{unit_b}"
        pairs_result[pair_key] = {
            "game_count": pair_games[pair],
            "openings_analyzed": len(olist),
            "either_bought_early": compute_bucket_stats(either_entries),
            "both_bought_early": compute_bucket_stats(both_entries),
            "neither_bought_early": compute_bucket_stats(neither_entries),
            "most_common_opening_when_either": most_common_opening,
        }

    # Sort: by both_bought_early.residual_win_rate desc if count >= 5,
    # else by either_bought_early.residual_win_rate desc
    def sort_key(pair_key):
        data = pairs_result[pair_key]
        both = data.get("both_bought_early")
        either = data.get("either_bought_early")
        if both and both["count"] >= 5 and both["residual_win_rate"] is not None:
            return (1, both["residual_win_rate"])
        if either and either["residual_win_rate"] is not None:
            return (0, either["residual_win_rate"])
        return (-1, 0)

    sorted_keys = sorted(pairs_result.keys(), key=sort_key, reverse=True)
    ordered = {}
    for k in sorted_keys:
        ordered[k] = pairs_result[k]

    pairs_50 = sum(1 for p in pair_games.values() if p >= 50)
    return {
        "metadata": {
            "total_pairs": len(ordered),
            "pairs_with_50_plus_games": pairs_50,
            "description": "Per-pair opening analysis. 'early' = purchased in first 4 rounds.",
        },
        "pairs": ordered,
    }


# ---------------------------------------------------------------------------
# Step 5e: Triple Opening Analysis
# ---------------------------------------------------------------------------

def generate_triple_analysis(games, openings, base_set):
    """Per-triple analysis for triples with 10+ games."""

    game_dominions = {}
    for code, game in games.items():
        dom = tuple(sorted(set(game["card_set"]) - base_set))
        game_dominions[code] = dom

    openings_by_code = defaultdict(list)
    for o in openings:
        openings_by_code[o[0]].append(o)

    # Count triple occurrences
    triple_games = Counter()
    for code, dom in game_dominions.items():
        for triple in combinations(dom, 3):
            triple_games[triple] += 1

    # Filter to triples with 10+ games
    qualifying = {t for t, c in triple_games.items() if c >= 10}
    print(f"Triple analysis: {len(qualifying):,} triples with 10+ games (of {len(triple_games):,} total)", file=sys.stderr)

    # Collect openings for qualifying triples
    # Process game by game to avoid massive memory usage
    triple_any = defaultdict(list)     # triple -> list of (won, self_r, opp_r) for any-bought
    triple_none = defaultdict(list)    # triple -> list of (won, self_r, opp_r) for none-bought
    triple_opening_count = Counter()   # triple -> number of openings analyzed

    for code, dom in game_dominions.items():
        game_openings = openings_by_code.get(code, [])
        if not game_openings:
            continue

        # Get qualifying triples for this game
        game_triples = [t for t in combinations(dom, 3) if t in qualifying]
        if not game_triples:
            continue

        for o in game_openings:
            _, player, opening, won, self_r, opp_r, card_set = o
            flat_buys = set()
            for buys in opening:
                flat_buys.update(buys)
            entry = (won, self_r, opp_r)

            for triple in game_triples:
                triple_opening_count[triple] += 1
                bought_any = any(u in flat_buys for u in triple)
                if bought_any:
                    triple_any[triple].append(entry)
                else:
                    triple_none[triple].append(entry)

    # Build output
    triples_result = {}
    for triple in qualifying:
        key = "+".join(triple)
        any_entries = triple_any.get(triple, [])
        none_entries = triple_none.get(triple, [])

        triples_result[key] = {
            "game_count": triple_games[triple],
            "openings_analyzed": triple_opening_count.get(triple, 0),
            "any_bought_early": compute_bucket_stats_slim(any_entries),
            "none_bought_early": compute_bucket_stats_minimal(none_entries),
        }

    # Sort by any_bought_early.residual_win_rate descending
    def sort_key(k):
        data = triples_result[k]
        any_stats = data.get("any_bought_early")
        if any_stats and any_stats.get("residual_win_rate") is not None:
            return any_stats["residual_win_rate"]
        return -999

    sorted_keys = sorted(triples_result.keys(), key=sort_key, reverse=True)
    ordered = {}
    for k in sorted_keys:
        ordered[k] = triples_result[k]

    return {
        "metadata": {
            "total_triples_with_10_plus": len(ordered),
            "min_games_threshold": 10,
            "description": "Per-triple opening analysis. Only triples with 10+ games included.",
        },
        "triples": ordered,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_json(data, filename):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
    size = os.path.getsize(path)
    print(f"  {filename} ({size:,} bytes)", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Step 1: Load
    games, openings, total_lines, skipped = load_games()

    # Step 2: Detect base set
    base_set = detect_base_set(games)

    # Deck size distribution
    deck_sizes = Counter()
    unique_doms = set()
    for game in games.values():
        dom = tuple(sorted(set(game["card_set"]) - base_set))
        deck_sizes[f"Base+{len(dom)}"] += 1
        unique_doms.add(dom)

    print(f"\nDeck size distribution:", file=sys.stderr)
    for k in sorted(deck_sizes.keys()):
        print(f"  {k}:  {deck_sizes[k]:,} games", file=sys.stderr)

    print(f"\nAggregation density:", file=sys.stderr)
    print(f"  Unique dominion sets:    {len(unique_doms):,} (all unique — per-set books impossible)", file=sys.stderr)

    # Step 5a: Universal openings
    print(f"\nGenerating universal_openings.json...", file=sys.stderr)
    universal = generate_universal_openings(games, openings, base_set)

    # Step 5b: Unit opening impact
    print(f"Generating unit_opening_impact.json...", file=sys.stderr)
    unit_impact = generate_unit_opening_impact(games, openings, base_set)

    # Step 5c: Tech timing
    print(f"Generating tech_timing.json...", file=sys.stderr)
    tech_timing = generate_tech_timing(openings)

    # Step 5d: Pair analysis
    print(f"Generating pair_opening_analysis.json...", file=sys.stderr)
    pair_analysis = generate_pair_analysis(games, openings, base_set)

    # Step 5e: Triple analysis
    print(f"Generating triple_opening_analysis.json...", file=sys.stderr)
    triple_analysis = generate_triple_analysis(games, openings, base_set)

    # Write outputs
    print(f"\nFiles written:", file=sys.stderr)
    write_json(universal, "universal_openings.json")
    write_json(unit_impact, "unit_opening_impact.json")
    write_json(tech_timing, "tech_timing.json")
    write_json(pair_analysis, "pair_opening_analysis.json")
    write_json(triple_analysis, "triple_opening_analysis.json")

    # Summary
    print(f"\n=== Opening Book Extraction Summary ===", file=sys.stderr)
    print(f"Total JSONL lines:       {total_lines:,}", file=sys.stderr)
    print(f"Total unique games:      {len(games):,}", file=sys.stderr)
    print(f"Player-openings used:    {len(openings):,}  (skipped {skipped} with <4 turns)", file=sys.stderr)

    # Tech timing summary
    print(f"\nTech timing (median first purchase round):", file=sys.stderr)
    for tech in ["Conduit", "Blastforge", "Animus"]:
        td = tech_timing["tech_buildings"][tech]
        med = td["first_buy_round_median"]
        p0_med = td["by_seat"]["p0"]["first_buy_round_median"]
        p1_med = td["by_seat"]["p1"]["first_buy_round_median"]
        print(f"  {tech:12s}: round {med} (P0: {p0_med}, P1: {p1_med})", file=sys.stderr)

    # Top 5 early-buy impact units
    units = unit_impact["units"]
    sorted_units = sorted(units.keys(),
                          key=lambda u: units[u]["residual_impact_delta"] or 0,
                          reverse=True)
    print(f"\nTop 5 early-buy impact units (by residual):", file=sys.stderr)
    for i, u in enumerate(sorted_units[:5]):
        delta = units[u]["residual_impact_delta"]
        print(f"  {i+1}. {u:25s}  {delta:+.4f} residual WR delta", file=sys.stderr)

    # Pair/triple density
    print(f"\nPair analysis: {len(pair_analysis['pairs']):,} pairs", file=sys.stderr)
    print(f"Triple analysis: {len(triple_analysis['triples']):,} triples", file=sys.stderr)


if __name__ == "__main__":
    main()
