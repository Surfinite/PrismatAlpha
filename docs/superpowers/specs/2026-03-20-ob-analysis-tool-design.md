# Design Spec: Opening Book Analysis Tool

> **Date**: 2026-03-20
> **Goal**: Build a Python CLI tool that analyzes 102k parsed expert replays to generate data-driven opening book entries, producing both a human-readable analysis report and config-ready OB JSON
> **Data source**: `replays.db` — 101,879 parsed replays with ground-truth turn data from JS engine extraction (2.5M turns, 7.5M action records)
> **OB format reference**: `bin/asset/config/config.txt` — existing 63 entries across 4 book variants

---

## 1. Architecture Overview

```
replays.db (read-only)
    |
    v
+-----------------------------------+
|  ob_analysis.py                   |
|  * Query Dominion unit frequency  |
|  * Per-unit consensus (P1/P2)     |
|  * Pair analysis for contested    |
|  * Turn 2 analysis for DD states  |
+-----------------------------------+
    |
    v
+-----------------------------------+
|  ob_format.py                     |
|  * Format analysis report (JSON)  |
|  * Generate config.txt OB entries |
|  * Validate against existing OB   |
|  * Human-readable summary         |
+-----------------------------------+
    |
    +---> report.json (evidence)
    +---> ob_entries.json (config-ready)
    +---> stdout summary
```

### Design Principles

1. **Read-only** — No DB writes. All analysis is SQL queries against existing tables
2. **Evidence-based** — Every generated OB entry is backed by consensus data (frequency, sample size, win rate)
3. **Configurable threshold** — Rating filter is a CLI flag, not hardcoded. Default 2000+ both players
4. **Targeted pair analysis** — Only contested single-unit results trigger pair exploration (avoids combinatorial explosion)
5. **Validation** — Compare generated entries against existing LiveOpeningBook2 to surface confirmations, contradictions, and gaps

---

## 2. CLI Interface

```bash
# Full analysis with defaults (2000+ rating, 30 min samples)
python -m replay_parser.ob_analysis --db c:/libraries/prismata-replay-parser/replays.db

# Custom thresholds
python -m replay_parser.ob_analysis --db replays.db --min-rating 1800 --min-samples 50

# Output to files
python -m replay_parser.ob_analysis --db replays.db \
    --report ob_report.json --config ob_entries.json

# Analyze specific unit(s) only
python -m replay_parser.ob_analysis --db replays.db --units "Wild Drone,Tarsier"
```

### Parameters

| Flag | Default | Description |
|---|---|---|
| `--db` | required | Path to replays.db |
| `--min-rating` | 2000 | Minimum rating for both players |
| `--min-samples` | 30 | Minimum games for a unit to be analyzed |
| `--report` | stdout | Path for analysis report JSON |
| `--config` | stdout | Path for config-ready OB entries JSON |
| `--units` | all | Comma-separated unit names to analyze (skip others) |
| `--pair-threshold` | 0.40 | Consensus below this triggers pair analysis |
| `--strong-threshold` | 0.60 | Consensus above this = strong (auto-include) |

---

## 3. Analysis Pipeline

### 3.1 Step 1: Identify Dominion Units

Query all non-base-set units appearing in enough games at the rating threshold.

```sql
SELECT ru.unit_name, COUNT(DISTINCT ru.code) as games
FROM replay_units ru
JOIN replays r ON ru.code = r.code
WHERE r.p1_rating >= :min_rating AND r.p2_rating >= :min_rating
GROUP BY ru.unit_name
HAVING games >= :min_samples
ORDER BY games DESC
```

**Base set exclusion list** (11 units — always available, not conditional):
Drone, Engineer, Conduit, Blastforge, Animus, Wall, Steelsplitter, Forcefield, Gauss Cannon, Tarsier, Rhino

### 3.2 Step 2: Per-Unit Turn 1 Consensus

For each Dominion unit, for each player position (P1=0, P2=1):

```sql
SELECT tb.buy_sequence, COUNT(*) as freq,
       SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) as wins,
       SUM(CASE WHEN r.result = 2 THEN 1 ELSE 0 END) as draws
FROM turn_buys tb
JOIN replays r ON tb.code = r.code
WHERE tb.player = :player AND tb.player_turn = 1
  AND r.p1_rating >= :min_rating AND r.p2_rating >= :min_rating
  AND r.result IN (0, 1, 2)
  AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = :unit)
GROUP BY tb.buy_sequence
ORDER BY freq DESC
```

**Computed metrics per unit per player:**
- `top_buy`: Most frequent buy sequence
- `frequency`: `top_count / total_games` — consensus percentage
- `win_rate`: `wins / (total - draws)` — win rate when using the top buy (draws excluded)
- `runner_up`: Second most frequent buy
- `runner_up_freq`: Runner-up's frequency
- `total_games`: Sample size

**Consensus classification:**

| Frequency | Label | Action |
|---|---|---|
| >= `strong_threshold` (0.60) | `strong` | Generate OB entry |
| >= `pair_threshold` (0.40) | `moderate` | Generate OB entry, flag for review |
| < `pair_threshold` (0.40) | `contested` | No entry; trigger pair analysis |

### 3.3 Step 3: Turn 2 Analysis for DD Follow-Up States

After turn 1 analysis, analyze turn 2 for the common case where both players opened with DD (Drone, Drone). These are deterministic states:
- P1 after DD: `{"Drone": 8, "Engineer": 2}` — same as existing `BlueTurnTwoOpeningBook` entry
- P2 after DD: `{"Drone": 9, "Engineer": 2}`

```sql
SELECT tb.buy_sequence, COUNT(*) as freq,
       SUM(CASE WHEN tb.player = r.result THEN 1 ELSE 0 END) as wins
FROM turn_buys tb
JOIN replays r ON tb.code = r.code
JOIN turn_state ts ON tb.code = ts.code AND tb.global_turn = ts.global_turn
WHERE tb.player = :player AND tb.player_turn = 2
  AND r.p1_rating >= :min_rating AND r.p2_rating >= :min_rating
  AND json_extract(ts.units_owned, '$.Drone') = :expected_drones
  AND json_extract(ts.units_owned, '$.Engineer') = 2
  AND tb.code IN (SELECT code FROM replay_units WHERE unit_name = :unit)
GROUP BY tb.buy_sequence
ORDER BY freq DESC
```

Where `expected_drones` is 8 for P1, 9 for P2 (standard DD follow-up).

This captures the "what do experts buy on turn 2 after DD when unit X is in the set?" signal — the same pattern the existing `BlueTurnTwoOpeningBook` uses for Blastforge.

Turn 2 entries use the post-DD `self` condition:
```json
{"self": [["Drone", 8], ["Engineer", 2]], "buyable": ["Tarsier"], "buy": [...]}
```

### 3.4 Step 4: Pair Analysis for Contested Units

For any unit where **both** P1 and P2 turn 1 consensus is below `pair_threshold`:

1. Find top co-occurring Dominion units:

```sql
SELECT ru2.unit_name, COUNT(*) as co_count
FROM replay_units ru1
JOIN replay_units ru2 ON ru1.code = ru2.code AND ru1.unit_name != ru2.unit_name
JOIN replays r ON ru1.code = r.code
WHERE ru1.unit_name = :contested_unit
  AND r.p1_rating >= :min_rating AND r.p2_rating >= :min_rating
  AND ru2.unit_name NOT IN (:base_set_list)
GROUP BY ru2.unit_name
ORDER BY co_count DESC LIMIT 10
```

2. For each top co-occurring unit, re-run the Step 2 consensus query but conditioned on BOTH units being present (INTERSECT on replay_units).

3. If a pair resolves to >= `pair_threshold`, generate a pair-conditional OB entry with `buyable: ["Unit1", "Unit2"]`.

### 3.5 Step 5: Validate Against Existing OB

Compare generated entries against the 50 entries in LiveOpeningBook2:

For each existing entry, check if the analysis agrees:
- **Confirmed**: Generated entry has same `buyable` condition and matching `buy` sequence
- **Contradicted**: Generated entry exists for same `buyable` but has a different `buy` sequence (expert consensus disagrees with the hand-crafted entry)
- **New**: Generated entry for a unit/pair with no existing LiveOpeningBook2 coverage
- **Insufficient**: Existing entry for a unit that has < `min_samples` games at the rating threshold

This validation section appears in the report but does NOT modify the existing config.

---

## 4. Output Formats

### 4.1 Analysis Report (JSON)

```json
{
  "parameters": {
    "min_rating": 2000,
    "min_samples": 30,
    "strong_threshold": 0.60,
    "pair_threshold": 0.40,
    "total_replays_at_threshold": 24440,
    "turn_depth": 2
  },
  "summary": {
    "units_analyzed": 87,
    "units_strong_consensus": 25,
    "units_moderate_consensus": 9,
    "units_contested": 45,
    "units_insufficient_data": 8,
    "pairs_analyzed": 12,
    "pairs_resolved": 4,
    "turn1_entries_generated": 52,
    "turn2_entries_generated": 18,
    "total_entries_generated": 70
  },
  "turn1_analysis": [
    {
      "unit": "Wild Drone",
      "games": 3241,
      "p1": {
        "top_buy": ["Drone", "Engineer", "Wild Drone"],
        "frequency": 0.72,
        "win_rate": 0.54,
        "consensus": "strong",
        "sample_size": 1620,
        "runner_up": ["Drone", "Drone"],
        "runner_up_freq": 0.18,
        "top_5": [
          {"buy": ["Drone", "Engineer", "Wild Drone"], "freq": 0.72, "wins": 0.54},
          {"buy": ["Drone", "Drone"], "freq": 0.18, "wins": 0.48}
        ]
      },
      "p2": {
        "top_buy": ["Drone", "Engineer", "Wild Drone"],
        "frequency": 0.68,
        "consensus": "strong"
      }
    }
  ],
  "turn2_analysis": [
    {
      "unit": "Tarsier",
      "state": "8D+2E (P1 after DD)",
      "games": 1205,
      "top_buy": ["Drone", "Tarsier"],
      "frequency": 0.55,
      "consensus": "moderate"
    }
  ],
  "pair_analysis": [
    {
      "units": ["Synthesizer", "Blastforge"],
      "reason": "Synthesizer single-unit consensus 0.31 (contested)",
      "games": 412,
      "p1": {
        "top_buy": ["Conduit", "Drone"],
        "frequency": 0.52,
        "consensus": "moderate"
      }
    }
  ],
  "validation": {
    "confirmed": 28,
    "contradicted": 3,
    "new": 22,
    "insufficient": 7,
    "contradictions": [
      {
        "existing_buyable": ["Centurion"],
        "existing_buy": ["Drone", "Drone", "Engineer"],
        "expert_buy": ["Drone", "Drone"],
        "expert_freq": 0.71,
        "existing_freq": 0.15
      }
    ]
  }
}
```

### 4.2 Config-Ready OB Entries (JSON)

Array of OB entry objects, directly pasteable into config.txt:

```json
[
  {
    "_comment": "Wild Drone (P1 T1) — 72% consensus, 3241 games, strong",
    "self": [["Drone", 6], ["Engineer", 2]],
    "enemy": [],
    "buyable": ["Wild Drone"],
    "buy": ["Drone", "Engineer", "Wild Drone"]
  },
  {
    "_comment": "Wild Drone (P2 T1) — 68% consensus, 3241 games, strong",
    "self": [["Drone", 7], ["Engineer", 2]],
    "enemy": [],
    "buyable": ["Wild Drone"],
    "buy": ["Drone", "Engineer", "Wild Drone"]
  },
  {
    "_comment": "Tarsier (P1 T2 after DD) — 55% consensus, 1205 games, moderate",
    "self": [["Drone", 8], ["Engineer", 2]],
    "enemy": [],
    "buyable": ["Tarsier"],
    "buy": ["Drone", "Tarsier"]
  }
]
```

The `_comment` field is for human review — the C++ JSON parser ignores unknown keys, so these are safe to include in config.txt.

### 4.3 Human-Readable Summary (stdout)

```
Opening Book Analysis Report
Rating threshold: 2000+ (24,440 replays)
Units analyzed: 87 (8 insufficient data)

=== Turn 1 Strong Consensus (>60%) — 25 units ===
  Wild Drone      P1: DEW (72%)  P2: DEW (68%)  3241 games
  Doomed Drone    P1: DD  (85%)  P2: DDE (64%)  2891 games
  Vivid Drone     P1: EEV (61%)  P2: EEV (58%)  4102 games
  ...

=== Turn 2 After DD — 18 entries ===
  Tarsier (P1 8D+2E): DT (55%)  1205 games  moderate
  Blastforge (P1 8D+2E): DB (78%)  2340 games  strong
  ...

=== Contested (pair analysis triggered) — 12 units ===
  Synthesizer: P1=31% P2=28% → pair with Blastforge resolves to 52%
  ...

=== Validation vs LiveOpeningBook2 ===
  Confirmed: 28/50  Contradicted: 3  New candidates: 22  Insufficient data: 7

  Contradictions:
    Centurion: existing=DDE, expert=DD (71%)

Generated 70 OB entries (52 turn 1, 18 turn 2)
Saved report to ob_report.json
Saved config entries to ob_entries.json
```

---

## 5. File Structure

### New Files

| File | Responsibility |
|---|---|
| `replay_parser/ob_analysis.py` | Analysis logic: SQL queries, consensus computation, pair analysis, CLI entry point |
| `replay_parser/ob_format.py` | Output formatting: report JSON, config JSON, stdout summary, validation comparison |
| `replay_parser/tests/test_ob_analysis.py` | Unit tests for consensus computation with mock data |

### No Changes to Existing Files

All analysis is read-only against existing DB tables. No schema changes, no pipeline changes.

### Constants

**Base set units** (excluded from Dominion analysis):
```python
BASE_SET_UNITS = frozenset([
    "Drone", "Engineer", "Conduit", "Blastforge", "Animus",
    "Wall", "Steelsplitter", "Forcefield", "Gauss Cannon",
    "Tarsier", "Rhino"
])
```

**Starting states** (for `self` condition generation):
```python
STARTING_STATES = {
    0: [("Drone", 6), ("Engineer", 2)],   # P1 turn 1
    1: [("Drone", 7), ("Engineer", 2)],   # P2 turn 1
}
DD_FOLLOWUP_STATES = {
    0: [("Drone", 8), ("Engineer", 2)],   # P1 turn 2 after DD
    1: [("Drone", 9), ("Engineer", 2)],   # P2 turn 2 after DD
}
```

---

## 6. Existing OB Comparison Reference

The validation step compares against LiveOpeningBook2 (50 entries). These entries are loaded by parsing `config.txt` at analysis time — no hardcoded copy.

### Existing book structure:
- **LiveOpeningBook2**: 50 entries, all turn 1, all single-unit `buyable` conditions
- **BlueTurnTwoOpeningBook**: 4 entries covering turn 1 DD fallback + turn 2 Blastforge
- **LiveOpeningBook**: 4 generic entries (P1/P2 starting states)
- **DefaultOpeningBook**: 5 entries (Vivid Drone conditional)

The generated entries are designed to be compatible with the existing format and could extend or replace LiveOpeningBook2.

---

## 7. Future Extensions (Not in V1)

- **Turn 3+ depth**: Extend to turn 3 for specific high-consensus paths (e.g., DD → DB → ?)
- **All-pairs analysis**: Analyze every Dominion unit pair (C flag from brainstorming)
- **Interactive mode**: Query tool for ad-hoc exploration ("show me Tarsier + Animus at 1800+")
- **Action-aware entries**: Use `turn_actions` data to account for ability sequencing (Synthesizer lines)
- **Tournament validation**: Automatically run matchups with/without generated OB entries to measure win rate impact
- **Rating-stratified analysis**: Compare openings at 1800 vs 2000 vs 2200 to detect rating-dependent strategies
