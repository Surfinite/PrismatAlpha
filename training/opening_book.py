#!/usr/bin/env python3
"""
Opening Book Extraction from Expert Prismata Replays.

Reads training_data.jsonl (expert replay turns) and produces 5 JSON analysis files:
  1. universal_openings.json      - Cross-set buy patterns by round and seat
  2. unit_opening_impact.json     - Per-unit early-buy win rate impact
  3. tech_timing.json             - When experts first buy Conduit/Blastforge/Animus
  4. pair_opening_analysis.json   - Per-pair synergy analysis (all 5,460 pairs)
  5. triple_opening_analysis.json - Per-triple analysis (33,219+ triples with 10+ games)

Usage:
    python training/opening_book.py

All output written to training/data/. Summary stats printed to stderr.
No external dependencies -- stdlib only (json, collections, math, sys, os).
"""

import json
import math
import os
import sys
from collections import Counter, defaultdict


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

JSONL_PATH = r"c:\libraries\prismata-replay-parser\training_data.jsonl"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

EXPECTED_BASE = {
    "Drone", "Engineer", "Conduit", "Blastforge", "Animus",
    "Forcefield", "Gauss Cannon", "Wall", "Steelsplitter", "Tarsier", "Rhino",
}

OPENING_ROUNDS = 4
MIN_PAIR_GAMES = 10
MIN_TRIPLE_GAMES = 10
TOP_BUYS_LIMIT = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def eprint(*args, **kwargs):
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


def r4(v):
    """Round a float to 4 decimal places, or return None if None."""
    if v is None:
        return None
    return round(v, 4)


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def wilson_lower(wins, n, z=1.96):
    """Wilson score lower bound (95% CI) for win rate ranking."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (center - spread) / denom


def elo_expected(self_rating, opp_rating):
    """Expected win probability based on Elo ratings."""
    return 1.0 / (1.0 + 10.0 ** ((opp_rating - self_rating) / 400.0))


def percentile(sorted_values, pct):
    """Compute percentile from a pre-sorted list.  pct in [0, 100]."""
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


# ---------------------------------------------------------------------------
# Step 1: Load and Group
# ---------------------------------------------------------------------------

def load_and_group():
    """Read training_data.jsonl, build per-game structure, extract openings.

    Returns (games, openings, total_lines, skipped).

    games: dict mapping replay_code -> {card_set, result, p0_rating, p1_rating,
                                         players: {0: [...], 1: [...]}}
    openings: list of dicts, one per valid player-opening:
        {replay_code, player, card_set (set), rounds (list of 4 sorted buy lists),
         win (float: 1.0/0.5/0.0), self_rating, opp_rating}
    """

    games = {}
    total_lines = 0

    eprint("Loading", JSONL_PATH, "...")

    with open(JSONL_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            total_lines += 1
            rec = json.loads(line)

            code = rec["replay_code"]
            turn = rec["turn"]                  # 1-indexed round number
            player = rec["active_player"]       # 0 or 1
            bought = sorted(rec["action"]["bought"])  # alphabetical sort
            result = rec["result"]
            card_set = rec["state"]["card_set"]
            p0_rating = rec["p0_rating"]
            p1_rating = rec["p1_rating"]

            if code not in games:
                games[code] = {
                    "card_set": card_set,
                    "result": result,
                    "p0_rating": p0_rating,
                    "p1_rating": p1_rating,
                    "players": {0: [], 1: []},
                }

            games[code]["players"][player].append({
                "round": turn,
                "bought": bought,
            })

    # Sort each player's turns by round
    for g in games.values():
        for pid in (0, 1):
            g["players"][pid].sort(key=lambda t: t["round"])

    # Extract openings
    openings = []
    skipped = 0

    for code, g in games.items():
        for pid in (0, 1):
            turns = g["players"][pid]
            if len(turns) == 0:
                # Player's turns not in the data (not 2000+ rated) -- not a skip
                continue
            if len(turns) < OPENING_ROUNDS:
                skipped += 1
                continue

            if pid == 0:
                self_rating = g["p0_rating"]
                opp_rating = g["p1_rating"]
            else:
                self_rating = g["p1_rating"]
                opp_rating = g["p0_rating"]

            # Win value: 1.0 if this player won, 0.5 for draw, 0.0 if lost
            if g["result"] == 2:
                win = 0.5
            elif g["result"] == pid:
                win = 1.0
            else:
                win = 0.0

            rounds = [turns[i]["bought"] for i in range(OPENING_ROUNDS)]

            openings.append({
                "replay_code": code,
                "player": pid,
                "card_set": set(g["card_set"]),
                "card_set_list": g["card_set"],
                "win": win,
                "self_rating": self_rating,
                "opp_rating": opp_rating,
                "rounds": rounds,
            })

    eprint("  Lines read:       %s" % "{:,}".format(total_lines))
    eprint("  Unique games:     %s" % "{:,}".format(len(games)))
    eprint("  Player-openings:  %s  (skipped %d with <%d turns)"
           % ("{:,}".format(len(openings)), skipped, OPENING_ROUNDS))
    return games, openings, total_lines, skipped


# ---------------------------------------------------------------------------
# Step 2: Detect Base Set
# ---------------------------------------------------------------------------

def detect_base_set(games):
    """Auto-detect base set from data and assert it matches expected."""
    card_freq = Counter()
    for game in games.values():
        for card in game["card_set"]:
            card_freq[card] += 1

    n_games = len(games)
    base_set = {card for card, count in card_freq.items() if count == n_games}

    assert base_set == EXPECTED_BASE, (
        "Base set mismatch! Detected: %s, Expected: %s"
        % (sorted(base_set), sorted(EXPECTED_BASE))
    )

    eprint("  Base set auto-detected: %d cards (matches expected)" % len(base_set))
    return base_set


# ---------------------------------------------------------------------------
# Dominion / deck-size helpers
# ---------------------------------------------------------------------------

def get_dominion(card_set_collection, base_set):
    """Return the sorted tuple of non-base-set cards."""
    return tuple(sorted(set(card_set_collection) - base_set))


def deck_size_label(dom_count):
    return "base_plus_%d" % dom_count


# ---------------------------------------------------------------------------
# 5a. universal_openings.json
# ---------------------------------------------------------------------------

def generate_universal_openings(games, openings, base_set):
    eprint("\nGenerating universal_openings.json ...")

    p0_openings = [o for o in openings if o["player"] == 0]
    p1_openings = [o for o in openings if o["player"] == 1]

    # Attach dominion size to each opening for deck-size breakdown
    game_dom_size = {}
    for code, g in games.items():
        game_dom_size[code] = len(get_dominion(g["card_set"], base_set))

    def compute_round_stats(subset):
        """Compute per-round buy stats for a list of openings."""
        result = {}
        for r_idx in range(OPENING_ROUNDS):
            round_num = r_idx + 1
            buy_counter = Counter()
            empty_count = 0
            for o in subset:
                buy_key = tuple(o["rounds"][r_idx])
                buy_counter[buy_key] += 1
                if len(o["rounds"][r_idx]) == 0:
                    empty_count += 1

            total = len(subset)
            top_buys = []
            for buy_tup, cnt in buy_counter.most_common(TOP_BUYS_LIMIT):
                top_buys.append({
                    "buy": list(buy_tup),
                    "count": cnt,
                    "pct": r4(cnt / total) if total > 0 else 0,
                })

            result["round_%d" % round_num] = {
                "top_buys": top_buys,
                "empty_buy_count": empty_count,
                "unique_buy_combos": len(buy_counter),
            }
        return result

    by_seat = {
        "p0": compute_round_stats(p0_openings),
        "p1": compute_round_stats(p1_openings),
    }

    # By deck size
    by_deck_size = {}
    deck_groups = defaultdict(list)
    for o in openings:
        ds = game_dom_size[o["replay_code"]]
        deck_groups[ds].append(o)

    deck_game_counts = Counter()
    for code, g in games.items():
        ds = len(get_dominion(g["card_set"], base_set))
        deck_game_counts[ds] += 1

    for ds in sorted(deck_groups.keys()):
        ds_openings = deck_groups[ds]
        ds_p0 = [o for o in ds_openings if o["player"] == 0]
        ds_p1 = [o for o in ds_openings if o["player"] == 1]
        by_deck_size[deck_size_label(ds)] = {
            "game_count": deck_game_counts[ds],
            "p0": compute_round_stats(ds_p0),
            "p1": compute_round_stats(ds_p1),
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
# 5b. unit_opening_impact.json
# ---------------------------------------------------------------------------

def generate_unit_opening_impact(games, openings, base_set):
    eprint("Generating unit_opening_impact.json ...")

    # Collect all non-base-set units
    all_units = set()
    for g in games.values():
        for card in g["card_set"]:
            if card not in base_set:
                all_units.add(card)

    units_result = {}

    for unit in sorted(all_units):
        # Count how many GAMES have this unit (not just openings)
        in_card_set_count = sum(1 for g in games.values() if unit in g["card_set"])

        # Openings from games containing this unit
        unit_openings = [o for o in openings if unit in o["card_set"]]
        openings_analyzed = len(unit_openings)

        bought_list = []      # openings where unit was bought in first 4 rounds
        not_bought_list = []  # openings where unit was NOT bought
        first_bought_rounds = []

        for o in unit_openings:
            first_round = None
            for r_idx in range(OPENING_ROUNDS):
                if unit in o["rounds"][r_idx]:
                    first_round = r_idx + 1  # 1-indexed
                    break

            if first_round is not None:
                bought_list.append(o)
                first_bought_rounds.append(first_round)
            else:
                not_bought_list.append(o)

        def bucket_stats_full(bucket):
            """Full stats for a bucket: count, wins, win_rate, wilson_lower,
            avg_self_rating, avg_opponent_rating, avg_rating_diff,
            sum_expected_wins, residual_win_rate."""
            count = len(bucket)
            if count == 0:
                return {
                    "count": 0,
                    "wins": 0,
                    "win_rate": 0.0,
                    "wilson_lower": 0.0,
                    "avg_self_rating": 0.0,
                    "avg_opponent_rating": 0.0,
                    "avg_rating_diff": 0.0,
                    "sum_expected_wins": 0.0,
                    "residual_win_rate": 0.0,
                }
            wins = sum(o["win"] for o in bucket)
            sum_exp = sum(elo_expected(o["self_rating"], o["opp_rating"]) for o in bucket)
            avg_self = sum(o["self_rating"] for o in bucket) / count
            avg_opp = sum(o["opp_rating"] for o in bucket) / count
            return {
                "count": count,
                "wins": r4(wins),
                "win_rate": r4(wins / count),
                "wilson_lower": r4(wilson_lower(wins, count)),
                "avg_self_rating": r4(avg_self),
                "avg_opponent_rating": r4(avg_opp),
                "avg_rating_diff": r4(avg_self - avg_opp),
                "sum_expected_wins": r4(sum_exp),
                "residual_win_rate": r4((wins - sum_exp) / count),
            }

        bought_stats = bucket_stats_full(bought_list)
        not_bought_stats = bucket_stats_full(not_bought_list)

        # First-bought-round stats (only from openings where the unit WAS bought)
        sorted_fbr = sorted(first_bought_rounds)
        fbr_avg = r4(sum(sorted_fbr) / len(sorted_fbr)) if sorted_fbr else None
        fbr_median = r4(percentile(sorted_fbr, 50)) if sorted_fbr else None
        fbr_p25 = r4(percentile(sorted_fbr, 25)) if sorted_fbr else None
        fbr_p75 = r4(percentile(sorted_fbr, 75)) if sorted_fbr else None

        impact_delta = r4(bought_stats["win_rate"] - not_bought_stats["win_rate"])
        residual_impact_delta = r4(
            bought_stats["residual_win_rate"] - not_bought_stats["residual_win_rate"]
        )

        units_result[unit] = {
            "in_card_set_count": in_card_set_count,
            "openings_analyzed": openings_analyzed,
            "first_bought_round_avg": fbr_avg,
            "first_bought_round_median": fbr_median,
            "first_bought_round_p25": fbr_p25,
            "first_bought_round_p75": fbr_p75,
            "bought_in_opening": bought_stats,
            "not_bought_in_opening": not_bought_stats,
            "impact_delta": impact_delta,
            "residual_impact_delta": residual_impact_delta,
        }

    # Sort by residual_impact_delta descending
    sorted_units = dict(
        sorted(units_result.items(),
               key=lambda kv: kv[1]["residual_impact_delta"] or 0,
               reverse=True)
    )

    return {
        "metadata": {
            "total_units_analyzed": len(sorted_units),
            "min_games_threshold": 50,
            "early_cutoff_round": OPENING_ROUNDS,
            "description": "Per-unit impact of early purchasing on win rate",
        },
        "units": sorted_units,
    }


# ---------------------------------------------------------------------------
# 5c. tech_timing.json
# ---------------------------------------------------------------------------

def generate_tech_timing(openings):
    eprint("Generating tech_timing.json ...")

    tech_buildings = {}

    for tech in ("Conduit", "Blastforge", "Animus"):
        all_first_rounds = []
        seat_data = {0: [], 1: []}
        with_purchase = 0
        without_purchase = 0

        for o in openings:
            first_round = None
            for r_idx in range(OPENING_ROUNDS):
                if tech in o["rounds"][r_idx]:
                    first_round = r_idx + 1
                    break

            if first_round is not None:
                with_purchase += 1
                all_first_rounds.append(first_round)
                seat_data[o["player"]].append(first_round)
            else:
                without_purchase += 1

        # Distribution
        dist = Counter(all_first_rounds)
        dist_dict = {}
        for r in sorted(dist.keys()):
            dist_dict[str(r)] = dist[r]

        sorted_all = sorted(all_first_rounds)

        def seat_stats(rounds_list):
            if not rounds_list:
                return {
                    "openings_with_purchase": 0,
                    "first_buy_round_avg": None,
                    "first_buy_round_median": None,
                    "first_buy_round_p25": None,
                    "first_buy_round_p75": None,
                }
            s = sorted(rounds_list)
            return {
                "openings_with_purchase": len(s),
                "first_buy_round_avg": r4(sum(s) / len(s)),
                "first_buy_round_median": r4(percentile(s, 50)),
                "first_buy_round_p25": r4(percentile(s, 25)),
                "first_buy_round_p75": r4(percentile(s, 75)),
            }

        tech_buildings[tech] = {
            "games_in_card_set": len(openings),   # base set, always present
            "openings_with_purchase": with_purchase,
            "openings_without_purchase": without_purchase,
            "first_buy_round_distribution": dist_dict,
            "first_buy_round_avg": r4(sum(sorted_all) / len(sorted_all)) if sorted_all else None,
            "first_buy_round_median": r4(percentile(sorted_all, 50)) if sorted_all else None,
            "first_buy_round_p25": r4(percentile(sorted_all, 25)) if sorted_all else None,
            "first_buy_round_p75": r4(percentile(sorted_all, 75)) if sorted_all else None,
            "by_seat": {
                "p0": seat_stats(seat_data[0]),
                "p1": seat_stats(seat_data[1]),
            },
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
        "tech_buildings": tech_buildings,
    }


# ---------------------------------------------------------------------------
# 5d. pair_opening_analysis.json
# ---------------------------------------------------------------------------

def generate_pair_analysis(games, openings, base_set):
    eprint("Generating pair_opening_analysis.json ...")

    # Collect all non-base units sorted
    all_units = sorted({
        card
        for g in games.values()
        for card in g["card_set"]
        if card not in base_set
    })

    # Pre-compute: for each opening, the set of non-base units bought in opening
    # and the set of non-base units in card set
    for o in openings:
        bought_set = set()
        for r_idx in range(OPENING_ROUNDS):
            for u in o["rounds"][r_idx]:
                if u not in base_set:
                    bought_set.add(u)
        o["_nonbase_bought"] = bought_set
        o["_nonbase_in_set"] = o["card_set"] - base_set

    # Build inverted index: unit -> list of opening indices
    unit_to_oidx = defaultdict(list)
    for idx, o in enumerate(openings):
        for u in o["_nonbase_in_set"]:
            unit_to_oidx[u].append(idx)

    # Also build unit -> set of opening indices for fast intersection
    unit_to_oidx_set = {}
    for u in all_units:
        unit_to_oidx_set[u] = set(unit_to_oidx[u])

    pairs_result = {}
    n_units = len(all_units)
    pair_count = 0
    total_possible = n_units * (n_units - 1) // 2

    for i in range(n_units):
        u1 = all_units[i]
        s1 = unit_to_oidx_set[u1]

        for j in range(i + 1, n_units):
            u2 = all_units[j]
            common_indices = s1 & unit_to_oidx_set[u2]

            # Count unique games
            game_codes = set()
            for idx in common_indices:
                game_codes.add(openings[idx]["replay_code"])
            game_count = len(game_codes)

            if game_count < MIN_PAIR_GAMES:
                continue

            pair_openings = [openings[idx] for idx in common_indices]
            openings_analyzed = len(pair_openings)

            # Buckets
            either_list = []
            both_list = []
            neither_list = []
            opening_when_either = Counter()

            for o in pair_openings:
                b1 = u1 in o["_nonbase_bought"]
                b2 = u2 in o["_nonbase_bought"]

                if b1 or b2:
                    either_list.append(o)
                    # Track most common opening sequence
                    seq_key = tuple(tuple(r) for r in o["rounds"])
                    opening_when_either[seq_key] += 1
                if b1 and b2:
                    both_list.append(o)
                if not b1 and not b2:
                    neither_list.append(o)

            def pair_bucket_stats(bucket):
                """Stats for pair buckets: count, wins, win_rate, wilson_lower,
                avg_rating_diff, residual_win_rate."""
                count = len(bucket)
                if count == 0:
                    return {
                        "count": 0,
                        "wins": 0,
                        "win_rate": 0.0,
                        "wilson_lower": 0.0,
                        "avg_rating_diff": 0.0,
                        "residual_win_rate": 0.0,
                    }
                wins = sum(o["win"] for o in bucket)
                sum_exp = sum(elo_expected(o["self_rating"], o["opp_rating"]) for o in bucket)
                avg_diff = sum(o["self_rating"] - o["opp_rating"] for o in bucket) / count
                return {
                    "count": count,
                    "wins": r4(wins),
                    "win_rate": r4(wins / count),
                    "wilson_lower": r4(wilson_lower(wins, count)),
                    "avg_rating_diff": r4(avg_diff),
                    "residual_win_rate": r4((wins - sum_exp) / count),
                }

            either_stats = pair_bucket_stats(either_list)
            both_stats = pair_bucket_stats(both_list)
            neither_stats = pair_bucket_stats(neither_list)

            # Most common opening when either bought
            if opening_when_either:
                best_key = opening_when_either.most_common(1)[0][0]
                most_common_opening = [list(rnd) for rnd in best_key]
            else:
                most_common_opening = []

            pair_key = "%s+%s" % (u1, u2)
            pairs_result[pair_key] = {
                "game_count": game_count,
                "openings_analyzed": openings_analyzed,
                "either_bought_early": either_stats,
                "both_bought_early": both_stats,
                "neither_bought_early": neither_stats,
                "most_common_opening_when_either": most_common_opening,
            }

            pair_count += 1
            if pair_count % 1000 == 0:
                eprint("  Processed %d/%d pairs ..." % (pair_count, total_possible))

    eprint("  Total pairs with >=%d games: %d" % (MIN_PAIR_GAMES, len(pairs_result)))

    # Sort: by both_bought_early.residual_win_rate desc if count >= 5,
    # else by either_bought_early.residual_win_rate desc
    def pair_sort_key(kv):
        p = kv[1]
        if p["both_bought_early"]["count"] >= 5:
            return p["both_bought_early"]["residual_win_rate"] or 0
        return p["either_bought_early"]["residual_win_rate"] or 0

    sorted_pairs = dict(sorted(pairs_result.items(), key=pair_sort_key, reverse=True))

    pairs_with_50_plus = sum(
        1 for p in pairs_result.values() if p["game_count"] >= 50
    )

    return {
        "metadata": {
            "total_pairs": len(sorted_pairs),
            "pairs_with_50_plus_games": pairs_with_50_plus,
            "description": "Per-pair opening analysis. 'early' = purchased in first 4 rounds.",
        },
        "pairs": sorted_pairs,
    }


# ---------------------------------------------------------------------------
# 5e. triple_opening_analysis.json
# ---------------------------------------------------------------------------

def generate_triple_analysis(games, openings, base_set):
    eprint("Generating triple_opening_analysis.json ...")

    # Collect all non-base units sorted
    all_units = sorted({
        card
        for g in games.values()
        for card in g["card_set"]
        if card not in base_set
    })

    # Reuse _nonbase_bought and _nonbase_in_set from pair analysis (already attached)

    # Build inverted index: unit -> set of opening indices
    unit_to_oidx_set = defaultdict(set)
    for idx, o in enumerate(openings):
        for u in o["_nonbase_in_set"]:
            unit_to_oidx_set[u].add(idx)

    triples_result = {}
    triple_count = 0
    n_units = len(all_units)

    eprint("  Computing triples across %d units ..." % n_units)

    for i in range(n_units):
        u1 = all_units[i]
        s1 = unit_to_oidx_set[u1]

        for j in range(i + 1, n_units):
            u2 = all_units[j]
            s12 = s1 & unit_to_oidx_set[u2]

            # Early exit: if the pair has fewer openings than threshold,
            # no triple (i,j,k) can meet the threshold either
            if len(s12) < MIN_TRIPLE_GAMES:
                continue

            for k in range(j + 1, n_units):
                u3 = all_units[k]
                common_indices = s12 & unit_to_oidx_set[u3]

                # Count unique games
                game_codes = set()
                for idx in common_indices:
                    game_codes.add(openings[idx]["replay_code"])
                game_count = len(game_codes)

                if game_count < MIN_TRIPLE_GAMES:
                    continue

                triple_openings = [openings[idx] for idx in common_indices]
                openings_analyzed = len(triple_openings)

                # Buckets: any bought early vs none bought early
                any_bought = []
                none_bought = []

                for o in triple_openings:
                    nb = o["_nonbase_bought"]
                    if u1 in nb or u2 in nb or u3 in nb:
                        any_bought.append(o)
                    else:
                        none_bought.append(o)

                # any_bought_early stats (with Wilson + residual)
                any_count = len(any_bought)
                if any_count > 0:
                    any_wins = sum(o["win"] for o in any_bought)
                    any_sum_exp = sum(
                        elo_expected(o["self_rating"], o["opp_rating"])
                        for o in any_bought
                    )
                    any_stats = {
                        "count": any_count,
                        "wins": r4(any_wins),
                        "win_rate": r4(any_wins / any_count),
                        "wilson_lower": r4(wilson_lower(any_wins, any_count)),
                        "residual_win_rate": r4((any_wins - any_sum_exp) / any_count),
                    }
                else:
                    any_stats = {
                        "count": 0,
                        "wins": 0,
                        "win_rate": 0.0,
                        "wilson_lower": 0.0,
                        "residual_win_rate": 0.0,
                    }

                # none_bought_early stats (skip residual if count < 5)
                none_count = len(none_bought)
                if none_count > 0:
                    none_wins = sum(o["win"] for o in none_bought)
                    none_stats = {
                        "count": none_count,
                        "wins": r4(none_wins),
                        "win_rate": r4(none_wins / none_count),
                    }
                    if none_count >= 5:
                        none_sum_exp = sum(
                            elo_expected(o["self_rating"], o["opp_rating"])
                            for o in none_bought
                        )
                        none_stats["residual_win_rate"] = r4(
                            (none_wins - none_sum_exp) / none_count
                        )
                else:
                    none_stats = {
                        "count": 0,
                        "wins": 0,
                        "win_rate": 0.0,
                    }

                triple_key = "%s+%s+%s" % (u1, u2, u3)
                triples_result[triple_key] = {
                    "game_count": game_count,
                    "openings_analyzed": openings_analyzed,
                    "any_bought_early": any_stats,
                    "none_bought_early": none_stats,
                }

                triple_count += 1

        if (i + 1) % 10 == 0:
            eprint("  Unit %d/%d done, %d triples so far ..."
                   % (i + 1, n_units, triple_count))

    eprint("  Total triples with >=%d games: %d" % (MIN_TRIPLE_GAMES, len(triples_result)))

    # Sort by any_bought_early.residual_win_rate descending
    def triple_sort_key(kv):
        return kv[1]["any_bought_early"]["residual_win_rate"] or 0

    sorted_triples = dict(
        sorted(triples_result.items(), key=triple_sort_key, reverse=True)
    )

    return {
        "metadata": {
            "total_triples_with_10_plus": len(sorted_triples),
            "min_games_threshold": MIN_TRIPLE_GAMES,
            "description": "Per-triple opening analysis. Only triples with 10+ games included.",
        },
        "triples": sorted_triples,
    }


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def write_json(data, filename):
    """Write data as JSON with indent=2, sort_keys=True."""
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    size = os.path.getsize(path)
    eprint("  %s (%s bytes)" % (filename, "{:,}".format(size)))


# ---------------------------------------------------------------------------
# Step 6: Summary Stats
# ---------------------------------------------------------------------------

def print_summary(total_lines, games, openings, skipped, base_set,
                  tech_output, unit_output, pair_output, triple_output):
    eprint("")
    eprint("=== Opening Book Extraction Summary ===")
    eprint("Total JSONL lines:       %s" % "{:,}".format(total_lines))
    eprint("Total unique games:      %s" % "{:,}".format(len(games)))

    p0_count = sum(1 for o in openings if o["player"] == 0)
    p1_count = sum(1 for o in openings if o["player"] == 1)
    eprint("Player-openings used:    %s  (skipped %d with <%d turns)"
           % ("{:,}".format(len(openings)), skipped, OPENING_ROUNDS))
    eprint("Base set auto-detected:  %d cards (matches expected)" % len(base_set))

    # Deck size distribution
    eprint("")
    eprint("Deck size distribution:")
    deck_sizes = Counter()
    for g in games.values():
        dom = get_dominion(g["card_set"], base_set)
        deck_sizes[len(dom)] += 1
    for ds in sorted(deck_sizes.keys()):
        eprint("  Base+%d:  %s games" % (ds, "{:,}".format(deck_sizes[ds])))

    # Aggregation density
    eprint("")
    eprint("Aggregation density:")
    unique_sets = set()
    for g in games.values():
        dom = get_dominion(g["card_set"], base_set)
        unique_sets.add(dom)
    eprint("  Unique dominion sets:    %s (all unique -- per-set books impossible)"
           % "{:,}".format(len(unique_sets)))
    eprint("  Unit pairs (>=%d games):  %s / 5,460"
           % (MIN_PAIR_GAMES, "{:,}".format(pair_output["metadata"]["total_pairs"])))
    eprint("  Unit triples (>=%d games): %s"
           % (MIN_TRIPLE_GAMES,
              "{:,}".format(triple_output["metadata"]["total_triples_with_10_plus"])))

    # Tech timing
    eprint("")
    eprint("Tech timing (median first purchase round):")
    for tech in ("Conduit", "Blastforge", "Animus"):
        tb = tech_output["tech_buildings"][tech]
        med = tb["first_buy_round_median"]
        p0_med = tb["by_seat"]["p0"]["first_buy_round_median"]
        p1_med = tb["by_seat"]["p1"]["first_buy_round_median"]
        eprint("  %-12s: round %s (P0: %s, P1: %s)" % (tech, med, p0_med, p1_med))

    # Top 5 early-buy impact units
    eprint("")
    eprint("Top 5 early-buy impact units (by residual):")
    sorted_units = list(unit_output["units"].items())
    for rank, (name, data) in enumerate(sorted_units[:5], 1):
        delta = data["residual_impact_delta"]
        sign = "+" if delta >= 0 else ""
        eprint("  %d. %-25s %s%.4f residual WR delta" % (rank, name, sign, delta))

    eprint("")
    eprint("Files written: 5")
    eprint("  training/data/universal_openings.json")
    eprint("  training/data/unit_opening_impact.json")
    eprint("  training/data/tech_timing.json")
    eprint("  training/data/pair_opening_analysis.json")
    eprint("  training/data/triple_opening_analysis.json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Step 1: Load and group
    games, openings, total_lines, skipped = load_and_group()

    # Step 2: Detect base set
    base_set = detect_base_set(games)

    # Step 5a: Universal openings
    universal = generate_universal_openings(games, openings, base_set)

    # Step 5b: Unit opening impact
    unit_impact = generate_unit_opening_impact(games, openings, base_set)

    # Step 5c: Tech timing
    tech = generate_tech_timing(openings)

    # Step 5d: Pair analysis
    pair = generate_pair_analysis(games, openings, base_set)

    # Step 5e: Triple analysis
    triple = generate_triple_analysis(games, openings, base_set)

    # Write all 5 files
    eprint("")
    write_json(universal, "universal_openings.json")
    write_json(unit_impact, "unit_opening_impact.json")
    write_json(tech, "tech_timing.json")
    write_json(pair, "pair_opening_analysis.json")
    write_json(triple, "triple_opening_analysis.json")

    # Print summary to stderr
    print_summary(total_lines, games, openings, skipped, base_set,
                  tech, unit_impact, pair, triple)


if __name__ == "__main__":
    main()
