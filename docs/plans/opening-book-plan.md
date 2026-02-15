# Task: Opening Book Extraction from Expert Replays

## Context

You are working on **PrismataAI**, a C++ game engine and AI for the card game Prismata. Full project status is in `CLAUDE.md` at the repo root — read it for background on file locations, data formats, naming conventions, and the AI architecture.

Competitive player **Spyrfyr** suggested an opening book approach. This task is **pure Python** — no C++ changes, no builds, no interference with anything running.

## Goal

Parse 12,957 expert replay games (already extracted to `training_data.jsonl`) to identify expert opening patterns. Since every game has a unique card set (verified: 0 exact set repeats in 12,957 games), **per-exact-set opening books are impossible**. Instead, extract opening intelligence at levels that DO have statistical power: universal patterns, per-unit impact, per-pair synergies, and tech timing.

All output goes to `training/data/`.

## Input

**File:** `c:\libraries\prismata-replay-parser\training_data.jsonl`
- ~251,000 JSON Lines, one per expert player-turn
- 12,957 unique games, 19,597 player-game entries (6,640 games have both players; 6,317 have one)

### Key fields per line

| Field | Type | Description |
|---|---|---|
| `replay_code` | string | Groups lines into games |
| `turn` | int | **Round number** (1-indexed, per-round NOT per-player). Both P0 and P1 share the same turn number for the same round. Starts at 1. |
| `active_player` | int | 0 or 1 |
| `result` | int | 0 = P0 won, 1 = P1 won, 2 = draw |
| `action.bought` | list[str] | Display names of units purchased. Can be empty `[]` (player saved gold — meaningful, track it). |
| `state.card_set` | list[str] | All buyable unit display names for this game |
| `p0_rating` | float | Player 0's rating |
| `p1_rating` | float | Player 1's rating |

### Critical data properties (verified empirically)

1. **Turn numbering is per-round, 1-indexed.** Both P0 and P1 have entries at turn=1, then turn=2, etc. P0's first 4 rounds are turns 1,2,3,4. P1's first 4 rounds are turns 1,2,3,4.

2. **Only the 2000+ rated player's turns are present.** In 6,317 games only one player's turns appear; in 6,640 games both appear (both rated 2000+). The missing player's turns cannot be reconstructed.

3. **Every game has a unique dominion set.** With 105 non-base-set units and sets of 5-11 random picks, the combinatorial space is enormous (C(105,10) ≈ 1.7 trillion for Base+10). Per-exact-set opening books are impossible with this dataset size.

4. **Pair-level aggregation is dense.** All 5,460 possible unit pairs have 10+ games. 5,393 pairs (98.8%) have 50+ games. This is the right granularity for opening analysis.

5. **Triple-level aggregation is usable.** 33,219 triples have 10+ games.

6. **Base set cards appear in 100% of games.** The 11 base-set names in the JSONL are exactly: `Animus, Blastforge, Conduit, Drone, Engineer, Forcefield, Gauss Cannon, Rhino, Steelsplitter, Tarsier, Wall`. No aliases, no naming drift.

7. **99.1% of player-games have >=4 turns.** Only 168 player-games (0.9%) have <4 turns — these are resignations/disconnects.

8. **Card set sizes:** Base+5 (436 games), Base+8 (1,968), Base+9 (4,426), Base+10 (4,550), Base+11 (1,577).

9. **Unit frequencies are uniform:** range 626-1,285 appearances across 12,957 games (~5-10% each).

## Output

**Location:** `training/data/` (create the directory if needed)

**Reference files (read-only, do not modify):**
- `c:\libraries\prismata-replay-parser\training_data.jsonl`
- `training/data/unit_index.json` (for reference only — output uses display names)

## Implementation: `training/opening_book.py`

Single Python script. **No external dependencies** — use only `json`, `collections`, `math`, `sys`, `os`. Output all files as formatted JSON (`indent=2`).

---

### Step 1: Load and Group

Read `training_data.jsonl` line by line. Build a per-game structure:

```python
games = {
    replay_code: {
        "card_set": [...],           # from first line seen
        "result": int,               # 0=P0 won, 1=P1 won, 2=draw
        "p0_rating": float,
        "p1_rating": float,
        "players": {
            0: [                     # P0's turns, sorted by round
                {"round": 1, "bought": ["Drone", "Drone"]},
                {"round": 2, "bought": ["Drone", "Conduit"]},
                ...
            ],
            1: [...]                 # P1's turns (may be absent)
        }
    }
}
```

**Per-player opening extraction:**
- For each player present in the game, sort their turns by `round` number
- Take the **first 4 entries** as the opening
- If a player has fewer than 4 turns, **skip that player's opening entirely** — do not pad
- Represent each turn's buys as a **sorted list** of display names (removes buy-order noise: `["Drone", "Wall"]` not `["Wall", "Drone"]`)
- An empty buy `[]` is valid and distinct (player saved gold)

The opening sequence for a player is: `[sorted_buy_turn_1, sorted_buy_turn_2, sorted_buy_turn_3, sorted_buy_turn_4]`

**No game-level filtering.** Do not filter out "short games" at the game level. The per-player >=4 turn requirement is sufficient — a game where P0 has 2 turns (skipped) but P1 has 8 turns (used) is still valuable for P1's opening.

Print to stderr: total lines read, total games, total player-openings extracted, players skipped (<4 turns).

### Step 2: Detect Base Set

**Auto-detect from data** rather than hardcoding. Count card frequency across all games. Base set = cards appearing in 100% of games.

```python
# After loading all games:
card_freq = Counter()
for game in games.values():
    for card in game["card_set"]:
        card_freq[card] += 1

n_games = len(games)
BASE_SET = {card for card, count in card_freq.items() if count == n_games}
```

**Then assert** it matches the expected set:

```python
EXPECTED_BASE = {"Drone", "Engineer", "Conduit", "Blastforge", "Animus",
                 "Forcefield", "Gauss Cannon", "Wall", "Steelsplitter", "Tarsier", "Rhino"}
assert BASE_SET == EXPECTED_BASE, f"Base set mismatch! Detected: {BASE_SET}, Expected: {EXPECTED_BASE}"
```

This protects against naming drift while being self-validating.

**Dominion key** = `tuple(sorted(set(card_set) - BASE_SET))` — used only for deck-size grouping, NOT for per-set lookup (since every set is unique).

### Step 3: Rating Bias Helpers

Because the dataset includes games where a 2200-rated player faces a 1400-rated opponent, raw win rates overstate the quality of openings that happen to be played in mismatched games.

Compute per-opening:
- `avg_self_rating` — average rating of the player using this opening
- `avg_opponent_rating` — average rating of the opponent
- `avg_rating_diff` = mean(self - opponent)
- **Elo-expected residual**: how much better than expected this opening performs

```python
def elo_expected(self_rating, opp_rating):
    """Expected win probability based on Elo ratings."""
    return 1.0 / (1.0 + 10.0 ** ((opp_rating - self_rating) / 400.0))
```

For each opening occurrence, compute `E = elo_expected(self, opp)`. Track `sum_expected = sum(E)` alongside `wins`. Then:
- `residual_wins = wins - sum_expected` — how many more wins than Elo predicts
- `residual_win_rate = residual_wins / count` — positive = opening outperforms Elo expectation

This lets you distinguish "this opening wins 80% because it's good" from "this opening wins 80% because it's played against weak opponents."

### Step 4: Statistical Helpers

```python
import math

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
```

### Step 5: Generate Outputs

All outputs to `training/data/`. Use `json.dump()` with `indent=2` and `sort_keys=True`. Round all floats to 4 decimal places in output.

---

#### 5a. `universal_openings.json`

**The most important output.** Cross-set patterns — what do experts buy on each round regardless of card set?

```json
{
  "metadata": {
    "total_games": 12957,
    "total_p0_openings": 9500,
    "total_p1_openings": 9200,
    "description": "Expert buy patterns across all games, aggregated by round and seat"
  },
  "by_seat": {
    "p0": {
      "round_1": {
        "top_buys": [
          {"buy": ["Drone", "Drone"], "count": 5000, "pct": 0.526},
          {"buy": ["Drone", "Drone", "Drone"], "count": 1200, "pct": 0.126}
        ],
        "empty_buy_count": 50,
        "unique_buy_combos": 120
      },
      "round_2": {},
      "round_3": {},
      "round_4": {}
    },
    "p1": {}
  },
  "by_deck_size": {
    "base_plus_8": {
      "game_count": 1968,
      "p0": {
        "round_1": {
          "top_buys": [],
          "empty_buy_count": 0,
          "unique_buy_combos": 0
        }
      },
      "p1": {}
    },
    "base_plus_9": {},
    "base_plus_10": {},
    "base_plus_11": {}
  }
}
```

**Details:**
- Aggregate across ALL games (the `by_seat` section)
- Also break down by deck size (`by_deck_size`) — this is the fallback tier when no per-unit data applies
- Show **top 30 buy combinations** per round per seat (there will be many unique combos; show enough to capture the long tail)
- Include `empty_buy_count` — how often experts buy nothing on that round
- Include `unique_buy_combos` — total distinct buy multisets observed
- Sort `top_buys` by `count` descending

---

#### 5b. `unit_opening_impact.json`

Per non-base-set unit: when it's in the card set, how does buying it early affect win rate?

```json
{
  "metadata": {
    "total_units_analyzed": 105,
    "min_games_threshold": 50,
    "early_cutoff_round": 4,
    "description": "Per-unit impact of early purchasing on win rate"
  },
  "units": {
    "Apollo": {
      "in_card_set_count": 750,
      "openings_analyzed": 680,
      "first_bought_round_avg": 3.2,
      "first_bought_round_median": 3,
      "first_bought_round_p25": 2,
      "first_bought_round_p75": 4,
      "bought_in_opening": {
        "count": 220,
        "wins": 132,
        "win_rate": 0.600,
        "wilson_lower": 0.534,
        "avg_self_rating": 2105.3,
        "avg_opponent_rating": 1985.2,
        "avg_rating_diff": 120.1,
        "sum_expected_wins": 128.5,
        "residual_win_rate": 0.016
      },
      "not_bought_in_opening": {
        "count": 460,
        "wins": 237,
        "win_rate": 0.515,
        "wilson_lower": 0.469,
        "avg_self_rating": 2088.1,
        "avg_opponent_rating": 2001.4,
        "avg_rating_diff": 86.7,
        "sum_expected_wins": 240.2,
        "residual_win_rate": -0.007
      },
      "impact_delta": 0.085,
      "residual_impact_delta": 0.023
    }
  }
}
```

**Details:**
- Include all 105 non-base-set units (all have 626+ games — well above any reasonable threshold)
- `openings_analyzed` = number of player-openings from games containing this unit (may be less than `in_card_set_count` because some players have <4 turns)
- "bought in opening" = expert purchased at least one copy in their first 4 rounds
- `first_bought_round_*` stats computed only from openings where the unit WAS bought
- `impact_delta` = `bought_in_opening.win_rate - not_bought_in_opening.win_rate` — quick comparison
- `residual_impact_delta` = `bought_in_opening.residual_win_rate - not_bought_in_opening.residual_win_rate` — Elo-adjusted comparison (more trustworthy)
- Sort output by `residual_impact_delta` descending (units with strongest early-buy advantage first)

---

#### 5c. `tech_timing.json`

When experts buy their first tech building. **Directly informs the AI's TechHeuristic threshold parameters** (legacy: 11/10/9 gold thresholds ≈ round 4-5; improved: 8/7/6 ≈ round 2-3).

```json
{
  "metadata": {
    "description": "When experts first purchase tech buildings. Round numbers are 1-indexed game rounds.",
    "note": "P0 starts with 6 Drones (6 gold round 1). P1 starts with 7 Drones (7 gold round 1). Tech costs: Conduit=4G, Blastforge=5GG, Animus=6GR.",
    "ai_thresholds": {
      "legacy": {"Conduit": "10 gold", "Blastforge": "11 gold", "Animus": "9 gold"},
      "improved": {"Conduit": "7 gold", "Blastforge": "8 gold", "Animus": "6 gold"}
    }
  },
  "tech_buildings": {
    "Conduit": {
      "games_in_card_set": 12957,
      "openings_with_purchase": 8000,
      "openings_without_purchase": 4000,
      "first_buy_round_distribution": {"1": 500, "2": 2500, "3": 2000, "4": 1500},
      "first_buy_round_avg": 2.1,
      "first_buy_round_median": 2,
      "first_buy_round_p25": 1,
      "first_buy_round_p75": 3,
      "by_seat": {
        "p0": {
          "openings_with_purchase": 3800,
          "first_buy_round_avg": 2.3,
          "first_buy_round_median": 2,
          "first_buy_round_p25": 2,
          "first_buy_round_p75": 3
        },
        "p1": {
          "openings_with_purchase": 4200,
          "first_buy_round_avg": 1.9,
          "first_buy_round_median": 2,
          "first_buy_round_p25": 1,
          "first_buy_round_p75": 2
        }
      }
    },
    "Blastforge": {},
    "Animus": {}
  }
}
```

**Details:**
- All three are base-set and appear in 100% of games, so data is maximally dense
- Track full distribution (`first_buy_round_distribution`), not just averages — shows the shape
- Seat-specific stats are critical: P1 with 7 gold can afford Conduit (4G) or Animus (6G) on round 1; P0 with 6 gold can afford Conduit (4G) or Animus (6G) on round 1 too, but with different remaining gold
- "openings_without_purchase" = expert had 4+ turns but never bought this tech in the opening — also meaningful (some games don't need certain tech)
- The AI threshold comparison in metadata gives the reader immediate context

---

#### 5d. `pair_opening_analysis.json`

**Spyrfyr's base+2 idea.** For every pair of non-base-set units that appear together, analyze opening behavior. All 5,460 pairs have 10+ games; 5,393 have 50+.

```json
{
  "metadata": {
    "total_pairs": 5460,
    "pairs_with_50_plus_games": 5393,
    "description": "Per-pair opening analysis. 'early' = purchased in first 4 rounds."
  },
  "pairs": {
    "Apollo+Centrifuge": {
      "game_count": 85,
      "openings_analyzed": 78,
      "either_bought_early": {
        "count": 55,
        "wins": 33,
        "win_rate": 0.600,
        "wilson_lower": 0.468,
        "avg_rating_diff": 95.2,
        "residual_win_rate": 0.024
      },
      "both_bought_early": {
        "count": 12,
        "wins": 9,
        "win_rate": 0.750,
        "wilson_lower": 0.467,
        "avg_rating_diff": 110.3,
        "residual_win_rate": 0.081
      },
      "neither_bought_early": {
        "count": 23,
        "wins": 10,
        "win_rate": 0.435,
        "wilson_lower": 0.253,
        "avg_rating_diff": 82.1,
        "residual_win_rate": -0.031
      },
      "most_common_opening_when_either": [
        ["Drone", "Drone"],
        ["Conduit", "Drone"],
        ["Apollo"],
        ["Drone", "Wall"]
      ]
    }
  }
}
```

**Details:**
- Include all pairs with >= 10 games (should be all 5,460)
- Three buckets: `either_bought_early` (at least one of the pair), `both_bought_early`, `neither_bought_early`
- `most_common_opening_when_either` = the single most frequent 4-round opening sequence among player-openings that bought at least one unit from the pair
- Include Elo-residual stats for all buckets
- Sort pairs by `both_bought_early.residual_win_rate` descending (strongest synergy pairs first) — but only if `both_bought_early.count >= 5`, otherwise sort by `either_bought_early.residual_win_rate`

---

#### 5e. `triple_opening_analysis.json`

Extend Spyrfyr's idea to triples. 33,219 triples have 10+ games — worth capturing.

```json
{
  "metadata": {
    "total_triples_with_10_plus": 33219,
    "min_games_threshold": 10,
    "description": "Per-triple opening analysis. Only triples with 10+ games included."
  },
  "triples": {
    "Apollo+Centrifuge+Tesla Coil": {
      "game_count": 15,
      "openings_analyzed": 14,
      "any_bought_early": {
        "count": 11,
        "wins": 7,
        "win_rate": 0.636,
        "wilson_lower": 0.354,
        "residual_win_rate": 0.042
      },
      "none_bought_early": {
        "count": 3,
        "wins": 1,
        "win_rate": 0.333
      }
    }
  }
}
```

**Details:**
- Only include triples with >= 10 games (33,219 triples — file will be large but manageable)
- Simpler schema than pairs: just `any_bought_early` vs `none_bought_early` (tracking "all three bought early" would have very sparse counts)
- Include Wilson lower and Elo-residual for `any_bought_early`
- Skip Elo-residual for `none_bought_early` if count < 5
- Sort by `any_bought_early.residual_win_rate` descending

**Note:** This file will be several MB. That's fine — it's a data artifact, not a config file.

---

### Step 6: Summary Stats to stderr

```
=== Opening Book Extraction Summary ===
Total JSONL lines:       251,106
Total unique games:      12,957
Player-openings used:    19,200  (skipped 397 with <4 turns)
Base set auto-detected:  11 cards (matches expected)

Deck size distribution:
  Base+5:  436 games
  Base+8:  1,968 games
  Base+9:  4,426 games
  Base+10: 4,550 games
  Base+11: 1,577 games

Aggregation density:
  Unique dominion sets:    12,957 (all unique — per-set books impossible)
  Unit pairs (10+ games):  5,460 / 5,460 (100%)
  Unit triples (10+ games): 33,219

Tech timing (median first purchase round):
  Conduit:    round X (P0: X, P1: X)
  Blastforge: round X (P0: X, P1: X)
  Animus:     round X (P0: X, P1: X)

Top 5 early-buy impact units (by residual):
  1. UnitName  +0.XXX residual WR delta
  2. ...

Files written: 5
  training/data/universal_openings.json
  training/data/unit_opening_impact.json
  training/data/tech_timing.json
  training/data/pair_opening_analysis.json
  training/data/triple_opening_analysis.json
```

---

## Constraints

- **Pure Python, stdlib only.** No pandas, numpy, or any pip install.
- **Read-only** on `training_data.jsonl` — do not modify it.
- **All output to `training/data/`** — create the directory if it doesn't exist.
- **Do not modify any C++ files, config files, or anything under `source/`, `bin/`, or `visualstudio/`.**
- **Display names only** — all unit names in the JSONL are display names (e.g., "Tarsier" not "Tesla Tower"). Keep them as-is. Internal name mapping is only needed for C++ integration (out of scope).
- **Sorted buy lists** in JSON output (JSON has no tuple type).
- **Round all floats to 4 decimal places** in JSON output.
- **Wilson lower bound** for any ranking. Always include both `win_rate` and `wilson_lower`.
- **Elo-expected residual** for any win rate comparison. Always include `residual_win_rate` alongside raw `win_rate` so a reader can distinguish "genuinely good" from "played against weak opponents."

## Success Criteria

1. Script runs end-to-end without errors: `python training/opening_book.py`
2. All 5 JSON files produced in `training/data/`
3. Base set auto-detected and matches expected 11 cards
4. `tech_timing.json` shows when experts buy Conduit/Blastforge/Animus — directly comparable to the AI's thresholds
5. `universal_openings.json` answers "what do experts buy on rounds 1-4?" with deck-size breakdown
6. `unit_opening_impact.json` ranks all 105 non-base units by early-buy impact
7. `pair_opening_analysis.json` covers all 5,460 pairs with 10+ games each
8. `triple_opening_analysis.json` covers 33,000+ triples with 10+ games each
9. Elo-expected residuals computed for all win rate comparisons
10. Summary stats printed to stderr confirm reasonable numbers

## Not In Scope

- C++ opening book integration (future task, separate context)
- Per-exact-dominion-set opening books (impossible — every set is unique)
- Modifying the training pipeline or neural net
- Running any builds or tournaments
- Fetching new replays from S3 or the API
- Raw buy order preservation (the raw data is already in the JSONL if ever needed)

## Why This Changed From the Original Plan

The original plan in `CLAUDE.md` proposed `opening_frequency.json` and `opening_winrates.json` as the primary outputs — per-exact-dominion-set opening books ranked by Wilson lower bound. **Empirical verification revealed this is impossible**: all 12,957 games have unique dominion sets (0 repeats). With C(105,10) ≈ 1.7 trillion possible Base+10 sets, this was inevitable but wasn't checked until now.

The plan pivoted to aggregation levels that DO have statistical power:
- **Universal** (all games): maximally dense, answers "what do experts do in general?"
- **Per-unit** (105 units, 626-1,285 games each): dense enough for reliable stats
- **Per-pair** (5,460 pairs, all with 10+ games, 98.8% with 50+): Spyrfyr's base+2 idea, now the primary mechanism for set-specific guidance
- **Per-triple** (33,219 triples with 10+ games): extends pair analysis for richer set-specific patterns
- **By deck size** (Base+5/8/9/10/11): fallback tier in universal_openings.json

The `opening_frequency.json` / `opening_winrates.json` files were dropped entirely. The tech_timing analysis was kept unchanged — it's the most directly actionable output for AI improvement.

## Potential Future Step: Small-Set MasterBot Self-Play

**Status:** Not started — potential extension, not a definite follow-up.

**Idea:** Run OriginalHardestAI (or HardestAIUCT for randomness) vs itself on **controlled small card sets** (Base+1, Base+2, Base+3) to get per-exact-set opening data with statistical repetition.

| Set Size | Possible Sets | Games @ 5/set | Time (8 cores) | Coverage |
|---|---|---|---|---|
| Base+1 | 105 | 525 | ~1 hour | Exhaustive |
| Base+2 | 5,460 | 27,300 | ~19 hours | Exhaustive (every Spyrfyr pair) |
| Base+3 | 187,460 | too many | ~6 days for 1/set | Sample only |

**Why this is complementary (not a replacement):**
- Expert replay data tells us what **GOOD** openings look like (2000+ ELO players)
- MasterBot self-play tells us what the **AI currently does** per-set (~1200 ELO)
- The **delta** between them identifies where MasterBot diverges from expert play — directly actionable improvement targets
- For Base+1 and Base+2, we get **exhaustive per-exact-set coverage** — impossible with expert data

**Caveats:**
- HardestAI (Alpha-Beta) is **deterministic** — same card set produces identical games. Must use UCT-based players for varied games per set.
- MasterBot's openings encode the current (bad) tech threshold behavior — the self-play data shows the problem, not the solution.
- Requires either new config entries per card set, or a testing binary modification to enumerate sets programmatically.

**Recommendation:** Start with Base+1 only (~1 hour) as a low-cost probe. If the comparison with expert data reveals useful patterns, proceed to Base+2 overnight.
