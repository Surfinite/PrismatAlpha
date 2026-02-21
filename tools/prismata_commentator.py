"""
Live AI commentary engine for Prismata games.
Phase 1: text output to console + in-game chat injection.

Registers @on_message handlers in the sniffer's dispatcher,
aggregates game events via GameNarrative, generates commentary
via Claude Haiku on a dedicated worker thread.

Import this module from prismata_sniffer.py to activate.
"""

import os
import sys
import queue
import threading
import time

# Add tools/ to path for sibling imports
_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from prismata_game_state import GameNarrative, GameContext, TurnRecord

# Import sniffer globals for handler registration and chat injection
from prismata_sniffer import on_message, session

# ============================================================
# Configuration
# ============================================================

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS_FAST = 40       # Quick turns — ~15 words, 1 punchy sentence
MAX_TOKENS_THINK = 120     # Long thinks — more colour, analysis, predictions
THINK_TIME_THRESHOLD = 15  # Seconds: above this = "thinking", expand commentary
MAX_TOKENS_GAME_END = 100
COMMENTARY_PREFIX = "[AI] "  # prefix for chat messages

# ============================================================
# System Prompt Construction
# ============================================================

_KNOWLEDGE_PATH = os.path.join(_tools_dir, "commentary_prompt.md")


def _load_knowledge():
    """Load condensed knowledge base from file."""
    try:
        with open(_KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are a Prismata game commentator. Prismata is a turn-based strategy game."


_INSTRUCTIONS = """You are an expert Prismata game commentator casting a live match for an expert audience.

Rules:
- Generate 1-2 sentences of strategic commentary for this turn.
- Be analytical and insightful, not play-by-play. The audience are expert players.
- Focus on: strategic decisions, economy vs attack timing, key purchases, threats, absorb efficiency.
- Reference specific units and resource costs when relevant.
- If the turn is routine (just Drones), be brief or note what phase the game is in.
- Keep output under 20 words unless told otherwise. No markdown formatting. No emojis.
- Do NOT list every purchase. Highlight the ONE thing that matters most.
- Use game terminology naturally: absorb, breach, tech, float, granularity.
- You can be witty or dramatic at key moments (first tech, breach threat, big purchase).
"""


def _build_system_prompt(game: GameContext):
    """Build system prompt with cached knowledge + dynamic set info."""
    knowledge = _load_knowledge()

    # Build per-game set info from mergedDeck
    set_lines = []
    if game.randomizer:
        set_lines.append("\n## This Game's Random Set")
        for unit_name in game.randomizer:
            # Find in mergedDeck
            for card in game.merged_deck:
                ui_name = card.get("UIName") or card.get("name", "")
                if ui_name == unit_name:
                    cost = card.get("buyCost", "?")
                    hp = card.get("toughness", "?")
                    fragile = " fragile" if card.get("fragile") else ""
                    bt = card.get("buildTime", 0)
                    abilities = []
                    if card.get("beginOwnTurnScript", {}).get("receive"):
                        abilities.append(f"produces {card['beginOwnTurnScript']['receive']}")
                    if card.get("beginOwnTurnScript", {}).get("create"):
                        abilities.append("creates units")
                    if card.get("abilityScript"):
                        abilities.append("click ability")
                    if card.get("targetAction"):
                        abilities.append(card["targetAction"])
                    if card.get("lifespan"):
                        abilities.append(f"lifespan {card['lifespan']}")
                    ability_str = f" — {', '.join(abilities)}" if abilities else ""
                    set_lines.append(f"- {ui_name} ({cost}, {hp}HP{fragile}, BT{bt}){ability_str}")
                    break

    set_info = "\n".join(set_lines) if set_lines else ""

    # Use prompt caching: knowledge+instructions are static, set info is dynamic
    return [
        {
            "type": "text",
            "text": knowledge + "\n\n" + _INSTRUCTIONS,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": set_info,
        },
    ]


# ============================================================
# Commentary Worker Thread
# ============================================================

class CommentaryWorker:
    """Dedicated thread that consumes turn events and calls Claude API."""

    def __init__(self, narrative: GameNarrative):
        self._queue = queue.Queue(maxsize=5)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._client = None
        self._system_prompt = None
        self._last_commentary = ""
        self._running = False
        self._narrative = narrative

    def start(self):
        self._running = True
        self._thread.start()

    def enqueue(self, event_type, game, payload=None):
        """Non-blocking enqueue. Drops oldest if full."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self._queue.put_nowait((event_type, game, payload))
        except queue.Full:
            pass

    def _run(self):
        while self._running:
            try:
                event_type, game, payload = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                if event_type == "start":
                    self._on_game_start(game)
                elif event_type == "turn":
                    self._on_turn_end(game, payload)
                elif event_type == "end":
                    self._on_game_end(game, payload)
            except Exception as e:
                print(f"  [commentary] Worker error: {e}")

    def _ensure_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()

    def _on_game_start(self, game: GameContext):
        """Reset state, build system prompt, print game intro."""
        self._last_commentary = ""
        self._system_prompt = _build_system_prompt(game)

        players = " vs ".join(game.players) if game.players else "Unknown"
        rand_set = ", ".join(game.randomizer) if game.randomizer else "base set only"

        intro = f"{COMMENTARY_PREFIX}Live commentary active: {players} | Set: {rand_set}"
        print(f"\n  >>> {intro}\n")
        _inject_chat(game, intro)

    def _on_turn_end(self, game: GameContext, turn: TurnRecord):
        """Generate commentary for a completed turn."""
        self._ensure_client()

        if not self._system_prompt:
            self._system_prompt = _build_system_prompt(game)

        long_think = turn.time_used >= THINK_TIME_THRESHOLD
        max_tokens = MAX_TOKENS_THINK if long_think else MAX_TOKENS_FAST

        user_content = game.summary_for_llm(window=5, last_commentary=self._last_commentary)
        if long_think:
            user_content += (
                "\nThe player took a long time thinking. "
                "Add colour: predictions, historical comparisons, "
                "strategic narratives, or witty observations. 2-3 sentences OK."
            )

        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            commentary = response.content[0].text.strip()
        except Exception as e:
            print(f"  [commentary] API error: {e}")
            return

        self._last_commentary = commentary

        # Print to console
        print(f"\n  >>> T{turn.turn_number} {turn.player_name}: {commentary}\n")

        # Inject into game chat
        chat_text = f"{COMMENTARY_PREFIX}T{turn.turn_number}: {commentary}"
        _inject_chat(game, chat_text)

    def _on_game_end(self, game: GameContext, payload):
        """Generate game-end commentary."""
        self._ensure_client()

        winner_idx, replay_code = payload
        turn_count = len(game.turns)

        if winner_idx is not None and winner_idx < len(game.players):
            winner = game.players[winner_idx]
            result = f"{winner} wins"
        else:
            result = "Draw" if winner_idx is None else "Game over"

        user_content = (
            f"GAME OVER after {turn_count} turns. {result}.\n"
            f"Replay: {replay_code}\n"
            f"Generate a brief 1-2 sentence wrap-up of the game."
        )

        if not self._system_prompt:
            self._system_prompt = _build_system_prompt(game)

        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS_GAME_END,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            commentary = response.content[0].text.strip()
        except Exception as e:
            print(f"  [commentary] API error (game end): {e}")
            commentary = f"{result} after {turn_count} turns."

        print(f"\n  >>> GAME OVER: {commentary}\n")

        chat_text = f"{COMMENTARY_PREFIX}{commentary} | Replay: {replay_code}"
        _inject_chat(game, chat_text)

        self._last_commentary = ""
        self._system_prompt = None


# ============================================================
# Chat Injection Helper
# ============================================================

def _inject_chat(game: GameContext, text):
    """Inject commentary as a PM to the configured target player."""
    try:
        target = getattr(session, '_chat_target_id', None)
        if not target:
            return
        session.inject_chat(target, text)
    except Exception as e:
        print(f"  [commentary] Chat injection error: {e}")


# ============================================================
# Module initialization — wire up narrative + worker
# ============================================================

_narrative = GameNarrative()
_worker = CommentaryWorker(_narrative)

_narrative.on_game_start(lambda game: _worker.enqueue("start", game))
_narrative.on_turn_end(lambda game, turn: _worker.enqueue("turn", game, turn))
_narrative.on_game_end(lambda game, winner, code: _worker.enqueue("end", game, (winner, code)))


# ============================================================
# Sniffer message handlers (registered at import time)
# ============================================================

@on_message("BeginGame", direction="S->C")
def _commentary_begin_game(msg_type, direction, params, raw_msg):
    if not params or not isinstance(params[0], dict):
        return
    info = params[0]

    players = []
    player_ids = []
    lane_info = info.get("laneInfo", [])
    if lane_info and isinstance(lane_info[0], dict):
        for p in lane_info[0].get("players", []):
            players.append(p.get("displayName") or p.get("name", "?"))
            player_ids.append(str(p.get("id", "")))

    randomizer = []
    if lane_info and isinstance(lane_info[0], dict):
        rand_sets = lane_info[0].get("randomizer", [])
        if rand_sets and isinstance(rand_sets[0], list):
            randomizer = rand_sets[0]

    merged_deck = info.get("mergedDeck", [])
    _narrative.begin_game(players, player_ids, randomizer, merged_deck)


@on_message("EndTurn", direction="S->C")
def _commentary_end_turn(msg_type, direction, params, raw_msg):
    if not session.merged_deck:
        return

    with session._lock:
        buys = list(session.turn_buys)
        turn = session.turn_number
        players = list(getattr(session, 'players', []))
        f6_state = session.last_f6_state

    active_player = (turn - 1) % 2
    player_name = players[active_player] if active_player < len(players) else f"P{active_player + 1}"
    time_used = float(params[0]) if params else 0.0
    time_bank = float(params[2]) if len(params) > 2 else 0.0

    _narrative.end_turn(
        turn_number=turn,
        active_player=active_player,
        player_name=player_name,
        buys=buys,
        time_used=time_used,
        time_bank=time_bank,
        board_state=f6_state,
    )


@on_message("GameOver")
def _commentary_game_over(msg_type, direction, params, raw_msg):
    winner_idx = None
    replay_code = ""
    if len(params) >= 3:
        winner_idx = params[0] if isinstance(params[0], int) else None
        replay_code = params[2] if isinstance(params[2], str) else ""
    _narrative.end_game(winner_idx, replay_code)


# ============================================================
# Public API
# ============================================================

def start():
    """Start the commentary worker thread. Called from sniffer."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [commentary] WARNING: ANTHROPIC_API_KEY not set. Commentary disabled.")
        return False
    _worker.start()
    print("  [commentary] Live commentary engine active (Phase 1: text + chat)")
    return True
