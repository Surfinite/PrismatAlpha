"""Parse BlendSweep_vsMedium tournament results from replay JSON files.

Reads game_NNNN.json files, extracts matchup results, and prints
a formatted summary table with per-matchup win counts.
"""

import json
import os
from collections import defaultdict

REPLAY_DIR = r"c:\libraries\PrismataAI\bin\asset\replays\BlendSweep_vsMedium_2026-02-13_17-02-28"

# Expected players in canonical order
PLAYERS = [
    "BlendUCT_50",
    "BlendUCT_25",
    "BlendUCT_10",
    "BlendAB_50",
    "BlendAB_25",
    "MediumAI",
]


def main():
    # matchup_wins[(playerA, playerB)] = number of wins for playerA
    matchup_wins = defaultdict(int)
    matchup_games = defaultdict(int)
    total_games = 0
    draws = 0

    # Scan all game files
    files = sorted(f for f in os.listdir(REPLAY_DIR) if f.startswith("game_") and f.endswith(".json"))
    print(f"Found {len(files)} game files in {REPLAY_DIR}\n")

    for fname in files:
        fpath = os.path.join(REPLAY_DIR, fname)
        with open(fpath, "r") as f:
            data = json.load(f)

        p0 = data["p0"]
        p1 = data["p1"]
        winner_idx = data["winner"]
        winner_name = data["winnerName"]
        turns = data.get("turns", "?")

        total_games += 1

        if winner_idx == 2:
            # Draw
            draws += 1
            pair = tuple(sorted([p0, p1]))
            matchup_games[pair] += 1
        else:
            winner = p0 if winner_idx == 0 else p1
            loser = p1 if winner_idx == 0 else p0
            pair = tuple(sorted([p0, p1]))
            matchup_games[pair] += 1
            matchup_wins[(pair, winner)] += 1

    # Print per-game log
    print("=" * 80)
    print("GAME-BY-GAME LOG")
    print("=" * 80)
    for fname in files:
        fpath = os.path.join(REPLAY_DIR, fname)
        with open(fpath, "r") as f:
            data = json.load(f)
        p0 = data["p0"]
        p1 = data["p1"]
        winner_name = data["winnerName"]
        turns = data.get("turns", "?")
        print(f"  {fname}: {p0} vs {p1} -> {winner_name} wins ({turns} turns)")

    # Print matchup matrix
    print()
    print("=" * 80)
    print("MATCHUP RESULTS")
    print("=" * 80)
    print()

    # Collect all players that actually appeared
    seen_players = set()
    for fname in files:
        fpath = os.path.join(REPLAY_DIR, fname)
        with open(fpath, "r") as f:
            data = json.load(f)
        seen_players.add(data["p0"])
        seen_players.add(data["p1"])

    # Use canonical order, filtering to players that appeared
    ordered_players = [p for p in PLAYERS if p in seen_players]
    # Add any unexpected players at the end
    for p in sorted(seen_players):
        if p not in ordered_players:
            ordered_players.append(p)

    for i, pa in enumerate(ordered_players):
        for j, pb in enumerate(ordered_players):
            if j <= i:
                continue
            pair = tuple(sorted([pa, pb]))
            games = matchup_games.get(pair, 0)
            if games == 0:
                continue
            wins_a = matchup_wins.get((pair, pa), 0)
            wins_b = matchup_wins.get((pair, pb), 0)
            draw_count = games - wins_a - wins_b
            pct_a = (wins_a / games * 100) if games > 0 else 0
            pct_b = (wins_b / games * 100) if games > 0 else 0

            print(f"  {pa} vs {pb}")
            print(f"    Games: {games}   |   {pa}: {wins_a} ({pct_a:.1f}%)   |   {pb}: {wins_b} ({pct_b:.1f}%)", end="")
            if draw_count > 0:
                print(f"   |   Draws: {draw_count}", end="")
            print()
            print()

    # Print overall win/loss record per player
    print("=" * 80)
    print("OVERALL PLAYER RECORDS")
    print("=" * 80)
    print()

    player_wins = defaultdict(int)
    player_losses = defaultdict(int)
    player_draws = defaultdict(int)
    player_games = defaultdict(int)

    for fname in files:
        fpath = os.path.join(REPLAY_DIR, fname)
        with open(fpath, "r") as f:
            data = json.load(f)
        p0 = data["p0"]
        p1 = data["p1"]
        winner_idx = data["winner"]
        player_games[p0] += 1
        player_games[p1] += 1
        if winner_idx == 2:
            player_draws[p0] += 1
            player_draws[p1] += 1
        elif winner_idx == 0:
            player_wins[p0] += 1
            player_losses[p1] += 1
        else:
            player_wins[p1] += 1
            player_losses[p0] += 1

    # Header
    print(f"  {'Player':<20} {'Games':>6} {'Wins':>6} {'Losses':>6} {'Draws':>6} {'Win%':>8}")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*8}")

    for p in ordered_players:
        g = player_games.get(p, 0)
        w = player_wins.get(p, 0)
        l = player_losses.get(p, 0)
        d = player_draws.get(p, 0)
        pct = (w / g * 100) if g > 0 else 0
        print(f"  {p:<20} {g:>6} {w:>6} {l:>6} {d:>6} {pct:>7.1f}%")

    print()
    print(f"  Total games: {total_games}   Draws: {draws}")
    print()

    # Print note about expected vs completed
    expected = len(ordered_players) * (len(ordered_players) - 1) // 2 * 16  # 15 matchups * 16 rounds
    print(f"  Expected games (6-player round-robin, 16 rounds): ~{expected}")
    print(f"  Completed: {total_games} ({total_games/expected*100:.1f}%)")


if __name__ == "__main__":
    main()
