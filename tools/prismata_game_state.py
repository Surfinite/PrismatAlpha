"""
Shared game state model for Prismata tool consumers.
Aggregates per-turn events from the sniffer into a structured narrative.
No external dependencies beyond stdlib. Thread-safe.

Consumers: prismata_commentator.py (live commentary), future player agent.
"""

import threading
from dataclasses import dataclass, field
from typing import List, Optional, Callable


@dataclass
class TurnRecord:
    """Immutable snapshot of a single completed turn."""
    turn_number: int
    active_player: int          # 0 or 1
    player_name: str
    buys: List[str]             # display names of purchased units
    time_used: float            # seconds
    time_bank: float            # seconds remaining
    board_state: Optional[dict] = None  # parsed F6 state if available


@dataclass
class GameContext:
    """Accumulated game-level context. Reset on each BeginGame."""
    players: List[str] = field(default_factory=list)
    player_ids: List[str] = field(default_factory=list)  # numeric IDs as strings
    randomizer: List[str] = field(default_factory=list)
    merged_deck: list = field(default_factory=list)
    turns: List[TurnRecord] = field(default_factory=list)
    game_active: bool = False

    def summary_for_llm(self, window=5, last_commentary="") -> str:
        """Compact text summary for LLM context. ~200-400 tokens."""
        lines = []

        if self.players:
            lines.append(f"Game: {self.players[0]} (P1) vs {self.players[1]} (P2)")

        if self.randomizer:
            lines.append(f"Set: {', '.join(self.randomizer)}")

        current = self.turns[-1] if self.turns else None
        if not current:
            return "\n".join(lines)

        lines.append(f"\nTurn {current.turn_number} just ended ({current.player_name}'s turn)")

        # Buys
        if current.buys:
            buy_counts = {}
            for b in current.buys:
                buy_counts[b] = buy_counts.get(b, 0) + 1
            buy_str = ", ".join(
                f"{name} x{c}" if c > 1 else name
                for name, c in buy_counts.items()
            )
            lines.append(f"Bought: {buy_str}")
        else:
            lines.append("Bought: nothing")

        lines.append(f"Time: {current.time_used:.1f}s (bank: {current.time_bank:.1f}s)")

        # Board state if available (from F6)
        if current.board_state:
            bs = current.board_state
            for i, player in enumerate(self.players):
                key = f"p{i + 1}_units"
                units = bs.get(key, {})
                if units:
                    unit_str = ", ".join(
                        f"{name} x{c}" if c > 1 else name
                        for name, c in units.items()
                    )
                    lines.append(f"{player}: {unit_str}")

        # Recent turn history
        recent = self.turns[-(window + 1):-1] if len(self.turns) > 1 else []
        if recent:
            lines.append("\nRecent turns:")
            for t in recent:
                if t.buys:
                    buy_counts = {}
                    for b in t.buys:
                        buy_counts[b] = buy_counts.get(b, 0) + 1
                    buy_str = ", ".join(
                        f"{name} x{c}" if c > 1 else name
                        for name, c in buy_counts.items()
                    )
                else:
                    buy_str = "(nothing)"
                lines.append(f"  T{t.turn_number} {t.player_name}: {buy_str}")

        if last_commentary:
            lines.append(f"\nYour last commentary: \"{last_commentary}\"")

        lines.append("\nGenerate 1-2 sentences of expert commentary for this turn.")
        return "\n".join(lines)


class GameNarrative:
    """Thread-safe game state accumulator with callback registration.

    Consumers register on_turn_end / on_game_start / on_game_end callbacks.
    The sniffer's @on_message handlers push events; consumers react.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._game = GameContext()
        self._callbacks_turn_end: List[Callable] = []
        self._callbacks_game_start: List[Callable] = []
        self._callbacks_game_end: List[Callable] = []

    @property
    def game(self):
        return self._game

    def on_turn_end(self, fn):
        self._callbacks_turn_end.append(fn)

    def on_game_start(self, fn):
        self._callbacks_game_start.append(fn)

    def on_game_end(self, fn):
        self._callbacks_game_end.append(fn)

    def begin_game(self, players, player_ids, randomizer, merged_deck):
        with self._lock:
            self._game = GameContext(
                players=list(players),
                player_ids=[str(pid) for pid in player_ids],
                randomizer=list(randomizer),
                merged_deck=list(merged_deck),
                game_active=True,
            )
            game = self._game
        for fn in self._callbacks_game_start:
            try:
                fn(game)
            except Exception as e:
                print(f"  [narrative] game_start callback error: {e}")

    def end_turn(self, turn_number, active_player, player_name, buys,
                 time_used, time_bank, board_state=None):
        record = TurnRecord(
            turn_number=turn_number,
            active_player=active_player,
            player_name=player_name,
            buys=list(buys),
            time_used=time_used,
            time_bank=time_bank,
            board_state=board_state,
        )
        with self._lock:
            self._game.turns.append(record)
            game = self._game
        for fn in self._callbacks_turn_end:
            try:
                fn(game, record)
            except Exception as e:
                print(f"  [narrative] turn_end callback error: {e}")

    def end_game(self, winner_idx, replay_code):
        with self._lock:
            self._game.game_active = False
            game = self._game
        for fn in self._callbacks_game_end:
            try:
                fn(game, winner_idx, replay_code)
            except Exception as e:
                print(f"  [narrative] game_end callback error: {e}")
