"""GamePlayer -- manages a single Prismata game session.

Handles the full game lifecycle from BeginGame through turns to GameOver.
Receives server messages (via PrismataClient.on_message callback), tracks
game state, calls SteamAIBridge for AI moves, and sends clicks back.

Protocol flow per turn:
  Server: StartTurn
  Client: EndSwoosh -> [Click ...] -> EndTurn
  (repeat until GameOver)
"""

import json
import logging
import time

from bot.ai_params import load_params, select_params
from bot.config import (
    RESIGN_EVAL_PCT_THRESHOLD, RESIGN_CONSECUTIVE_TURNS,
    AI_FULL_PARAMS_PATH, AI_SHORT_PARAMS_PATH,
)

log = logging.getLogger(__name__)


class GamePlayer:
    """Manages one game session from BeginGame to GameOver."""

    def __init__(self, bridge, client, state_bridge=None):
        """
        Args:
            bridge: SteamAIBridge instance (or None for testing).
            client: PrismataClient instance (or None for testing).
            state_bridge: StateBridge instance (or None to disable state tracking).
        """
        self.bridge = bridge
        self.client = client
        self.state_bridge = state_bridge

        # Game identity
        self.game_id = None
        self.format = None  # 201 = bot game, 202 = PvP
        self.our_player_index = None
        self.opponent_name = None
        self.client_username = None  # set externally before handle_message

        # Game state tracking
        self.init_info = None
        self.merged_deck = None
        self.lane_info = None
        self.command_list = []  # accumulated clicks (ours + opponent)
        self.clicks_per_turn = []  # click count per turn
        self.current_turn = -1
        self.game_start_time = None
        self.game_over = False
        self.result = None  # "win", "loss", "draw", or None

        # Opponent click buffer for state bridge
        self._pending_opponent_clicks = []

        # Loading state — deferred to survive disconnect/reconnect cycle
        self._loading_sent = False
        self._begin_game_time = None
        self._saw_disconnect = False

        # Resignation tracking
        self._consecutive_low_evals = 0

        # Load AI params once at construction
        self._load_ai_params()

    def _load_ai_params(self):
        """Load and parse AI parameter files once at construction."""
        try:
            full_str = load_params(AI_FULL_PARAMS_PATH)
            short_str = load_params(AI_SHORT_PARAMS_PATH)
            self._full_params = json.loads(full_str)
            self._short_params = json.loads(short_str)
        except FileNotFoundError:
            log.warning("AI param files not found — _build_ai_request will fail")
            self._full_params = None
            self._short_params = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self):
        """Reset all state for a new game."""
        self.game_id = None
        self.format = None
        self.our_player_index = None
        self.opponent_name = None
        self.init_info = None
        self.merged_deck = None
        self.lane_info = None
        self.command_list = []
        self.clicks_per_turn = []
        self.current_turn = -1
        self.game_start_time = None
        self.game_over = False
        self.result = None
        self._consecutive_low_evals = 0
        self._pending_opponent_clicks = []
        self._loading_sent = False
        self._begin_game_time = None
        self._saw_disconnect = False
        if self.state_bridge:
            self.state_bridge.close()

    def record_eval(self, eval_pct):
        """Record an eval percentage from the AI response.

        Args:
            eval_pct: float, the AI's evaluation percentage (0-100).
        """
        if eval_pct is not None and eval_pct < RESIGN_EVAL_PCT_THRESHOLD:
            self._consecutive_low_evals += 1
        else:
            self._consecutive_low_evals = 0

    def should_resign(self):
        """Return True if the bot should resign based on consecutive low evals."""
        return self._consecutive_low_evals >= RESIGN_CONSECUTIVE_TURNS

    def handle_message(self, msg):
        """Route a server message to the appropriate handler.

        Args:
            msg: list, the inner message from PrismataClient (already unwrapped
                 from the Msg envelope).
        """
        if not isinstance(msg, list) or not msg:
            return

        msg_type = msg[0]
        handler = self._HANDLERS.get(msg_type)
        if handler:
            handler(self, msg)
        else:
            log.debug("Unhandled game message: %s", msg_type)

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def _handle_begin_game(self, msg):
        """Process BeginGame -- extract game identity and state."""
        if len(msg) < 2:
            log.warning("BeginGame missing init_info")
            return

        info = msg[1]
        self.init_info = info
        self.game_id = info.get("liveGameID")
        self.format = info.get("format")
        self.merged_deck = info.get("mergedDeck", [])
        self.game_start_time = time.time()

        # Extract lane info
        lane_info_list = info.get("laneInfo", [])
        if lane_info_list:
            self.lane_info = lane_info_list[0]

        # Replay state from commandInfo
        cmd_info = info.get("commandInfo", {})
        self.command_list = list(cmd_info.get("commandList", []))
        self.clicks_per_turn = list(cmd_info.get("clicksPerTurn", []))

        # Determine our player index from display names
        self._identify_player()

        # Initialize state tracker
        if self.state_bridge and self.merged_deck:
            result = self.state_bridge.start(self.merged_deck)
            if result.get("ok"):
                log.info("State tracker initialized")
            else:
                log.error("State tracker init failed: %s", result.get("error"))

        log.info(
            "BeginGame: game_id=%s format=%s player_index=%s opponent=%s",
            self.game_id, self.format, self.our_player_index, self.opponent_name,
        )

        # Defer loading — the node switch causes a PlayerDisconnected/Reconnected
        # cycle that drops any messages sent during the disconnect window.
        # We'll send loading from check_deferred_loading() once the cycle settles.
        self._begin_game_time = time.time()
        self._loading_sent = False
        self._saw_disconnect = False

    def _identify_player(self):
        """Determine which player index (0 or 1) we are."""
        if not self.lane_info:
            log.warning("No laneInfo -- cannot identify player")
            return

        players = self.lane_info.get("players", [])
        username = self.client_username or (self.client.username if self.client else None)

        for i, player in enumerate(players):
            display_name = player.get("displayName", "")
            name = player.get("name", "")
            is_bot = bool(player.get("bot", ""))
            # In bot games, Master Bot has name=our username but bot="HardestAI".
            # Skip players with a non-empty bot field — that's the server bot, not us.
            if is_bot:
                continue
            if display_name == username or name == username:
                self.our_player_index = i
                # Opponent is the other player
                opp_idx = 1 - i
                if opp_idx < len(players):
                    self.opponent_name = players[opp_idx].get("displayName", "Unknown")
                return

        log.warning(
            "Could not identify player index for username=%s in players=%s",
            username, [p.get("displayName") for p in players],
        )

    def _handle_loading(self, msg):
        """Handle Loading message -- trigger deferred loading."""
        if not self._loading_sent:
            self._send_loading()

    def _handle_start_grace(self, msg):
        """Handle StartGrace -- send Endgrace to skip countdown."""
        if self.client and self.game_id:
            self.client.send_endgrace(self.game_id)
            log.info("Sent Endgrace for %s", self.game_id)

    def _handle_grace_over(self, msg):
        """Handle GraceOver -- grace period ended."""
        log.info("Grace period over for %s", self.game_id)

    def _handle_start_turn(self, msg):
        """Handle StartTurn -- determine if it's our turn and play."""
        # StartTurn contains turn number info
        # Turn numbers are 0-based: P0 plays turn 0, P1 plays turn 1, etc.
        # Even turns = P0, odd turns = P1
        if len(msg) > 1 and isinstance(msg[1], dict):
            time_info = msg[1]
            self.current_turn = time_info.get("turnNumber", self.current_turn + 1)
        else:
            self.current_turn += 1

        is_our_turn = self._is_our_turn()
        log.info(
            "StartTurn: turn=%d our_turn=%s (player_index=%s)",
            self.current_turn, is_our_turn, self.our_player_index,
        )

        if is_our_turn:
            self._play_turn()
        else:
            # PvP only — wait for opponent. In bot games this never happens
            # because every StartTurn is ours (Master Bot plays server-side).
            log.info("Waiting for opponent turn %d", self.current_turn)

    def _is_our_turn(self):
        """Check if the current turn belongs to us.

        In bot games (format 201), every StartTurn is ours — Master Bot
        plays silently server-side between EndTurn and the next StartTurn.
        In PvP (format 202): turn 0 = P0, turn 1 = P1, etc.
        """
        if self.our_player_index is None:
            return False
        if self.format == 201:
            return True  # bot games: every StartTurn is ours
        return (self.current_turn % 2) == self.our_player_index

    def _play_turn(self):
        """Execute our turn: EndSwoosh -> get AI move -> send clicks -> EndTurn."""
        if not self.client or not self.game_id:
            log.warning("Cannot play turn: no client or game_id")
            return

        turn_start = time.time()

        # 1. Send EndSwoosh (required before any clicks)
        self.client.send_end_swoosh(self.game_id, self.current_turn)

        # 2. Check resignation before requesting AI move
        if self.should_resign():
            log.info("Resigning at turn %d (eval below %.1f%% for %d turns)",
                     self.current_turn, RESIGN_EVAL_PCT_THRESHOLD,
                     RESIGN_CONSECUTIVE_TURNS)
            self._resign()
            return

        # 3. Get AI move (in background thread so we can keep pumping messages)
        import threading
        ai_result = [None]
        ai_done = threading.Event()

        def run_ai():
            ai_result[0] = self._get_ai_move()
            ai_done.set()

        ai_thread = threading.Thread(target=run_ai, daemon=True)
        ai_thread.start()

        # Keep connection alive (respond to Pings) while AI thinks
        while not ai_done.is_set():
            if self.client:
                self.client.pump_messages(timeout=1)
            ai_done.wait(timeout=0.1)

        clicks = ai_result[0]
        if clicks is None:
            log.error("Failed to get AI move at turn %d, sending empty turn",
                      self.current_turn)
            clicks = []

        # 4. Apply clicks to state tracker first to get resolved {_type, _id} format.
        # PrismataAI.exe returns raw {type, args} format — the state tracker
        # converts them via StateUtil.convertToClicks and returns resolvedClicks.
        if self.state_bridge and clicks:
            result = self.state_bridge.apply_clicks(clicks)
            if not result.get("ok") or result.get("failed", 0):
                log.error("Click application failed: %s", result)
                self._dump_debug_state("our_clicks_failed")
            # Use resolved clicks for server (converted from raw SteamAI format).
            # Strip to only {_type, _id} and remove trailing space clicks beyond
            # the first — the server handles confirm→commit on EndTurn, so we
            # only send one space click (action→confirm).
            resolved = result.get("resolvedClicks")
            if resolved:
                server_clicks = []
                space_count = 0
                for c in resolved:
                    if "_type" not in c:
                        continue
                    if c["_type"] == "space clicked":
                        space_count += 1
                        if space_count > 1:
                            continue  # skip extra space clicks
                    server_clicks.append({"_type": c["_type"], "_id": c["_id"]})
                clicks = server_clicks

        # 5. Send clicks to server
        log.info("Sending %d clicks to server: %s", len(clicks),
                 [f"{c.get('_type')}:{c.get('_id')}" for c in clicks])
        for click in clicks:
            self.client.send_click(self.game_id, click, self.current_turn)
            self.command_list.append(click)

        # Track clicks per turn
        self.clicks_per_turn.append(len(clicks))

        # 5. Send EndTurn
        duration = time.time() - turn_start
        last_click = clicks[-1] if clicks else {"_type": "space clicked", "_id": -1}
        self.client.send_end_turn(
            self.game_id, duration, self.current_turn, last_click
        )

        log.info("Played turn %d: %d clicks in %.1fs",
                 self.current_turn, len(clicks), duration)

    def _get_ai_move(self):
        """Request a move from PrismataAI.exe via the bridge.

        Returns:
            list of click dicts, or None on failure.
        """
        if not self.bridge:
            log.warning("No bridge configured -- cannot get AI move")
            return None

        # Build the request for PrismataAI.exe
        # TODO: For v1, pass the raw init_info with accumulated commandInfo.
        # PrismataAI.exe expects {mergedDeck, gameState, aiParameters, aiPlayerName}.
        # This may need iteration to build the proper state format.
        request = self._build_ai_request()
        if request is None:
            return None

        try:
            response = self.bridge.get_move(request)
        except (TimeoutError, RuntimeError) as e:
            log.error("AI bridge error: %s", e)
            return None

        # Record eval for resignation tracking
        eval_pct = self.bridge.parse_eval_pct(response)
        self.record_eval(eval_pct)

        return response.get("aiclicks", [])

    def _build_ai_request(self):
        """Build the JSON request for PrismataAI.exe.

        Exports current game state from the Node.js state tracker and
        combines with AI parameters.

        Returns:
            dict suitable for SteamAIBridge.get_move(), or None on failure.
        """
        if not self.state_bridge:
            log.error("No state bridge configured")
            return None
        if not self._short_params:
            log.error("AI parameters not loaded")
            return None

        self._flush_opponent_clicks()

        export = self.state_bridge.export_state()
        if not export.get("ok"):
            log.error("State export failed: %s", export.get("error"))
            return None

        game_state = export["state"]
        # HardestAI always gets short params (index 6 in AI_NO_OPENINGS)
        ai_params = self._short_params  # pre-parsed at construction

        return {
            "mergedDeck": self.merged_deck,
            "gameState": game_state,
            "aiParameters": ai_params,
            "aiPlayerName": "HardestAI",
        }

    def _flush_opponent_clicks(self):
        """Send buffered opponent clicks to the state bridge."""
        if not self._pending_opponent_clicks or not self.state_bridge:
            return
        result = self.state_bridge.apply_clicks(self._pending_opponent_clicks)
        if not result.get("ok"):
            log.error("Failed to apply opponent clicks: %s", result.get("error"))
        elif result.get("failed", 0):
            log.warning("Opponent clicks: %d applied, %d failed",
                        result.get("applied", 0), result.get("failed", 0))
        self._pending_opponent_clicks = []

    def _dump_debug_state(self, label):
        """Dump current state to disk for debugging."""
        ts = int(time.time())
        path = f"bot_debug_{label}_{ts}.json"
        try:
            export = self.state_bridge.export_state() if self.state_bridge else {}
            data = {
                "label": label,
                "game_id": self.game_id,
                "current_turn": self.current_turn,
                "our_player_index": self.our_player_index,
                "state": export.get("state") if export.get("ok") else None,
                "command_list_tail": self.command_list[-20:],
            }
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            log.info("Debug state dumped to %s", path)
        except Exception as e:
            log.warning("Failed to dump debug state: %s", e)

    def _resign(self):
        """Send resignation to the server."""
        if not self.client or not self.game_id:
            return

        duration = time.time() - (self.game_start_time or time.time())
        winner_index = 1 - self.our_player_index
        self.client.send_finish_game(
            self.game_id,
            winner_index=winner_index,
            player_index=self.our_player_index,
            duration=duration,
            resigned=True,
        )
        self.client.send_standup_game(self.game_id)
        self.result = "loss"
        self.game_over = True
        log.info("Resigned game %s", self.game_id)

    def _handle_click(self, msg):
        """Handle Click from server -- opponent's click (PvP only)."""
        if len(msg) >= 3:
            click_data = msg[2]
            self.command_list.append(click_data)
            self._pending_opponent_clicks.append(click_data)
            log.debug("Opponent click: %s", click_data)

    def _handle_many_clicks(self, msg):
        """Handle ManyClicks -- batch of opponent clicks in one message."""
        if len(msg) >= 3 and isinstance(msg[2], list):
            for click_data in msg[2]:
                self.command_list.append(click_data)
                self._pending_opponent_clicks.append(click_data)
            log.debug("ManyClicks: %d opponent clicks", len(msg[2]))

    def _handle_end_turn(self, msg):
        """Handle EndTurn from server -- opponent's turn ended."""
        log.debug("EndTurn received at turn %d", self.current_turn)

    def _handle_game_over(self, msg):
        """Handle GameOver -- record result and clean up."""
        self.game_over = True

        # GameOver payload varies; try to extract winner
        winner_index = None
        if len(msg) > 1 and isinstance(msg[1], dict):
            winner_index = msg[1].get("winner")
        elif len(msg) > 1:
            winner_index = msg[1]

        if winner_index is not None and self.our_player_index is not None:
            if winner_index == self.our_player_index:
                self.result = "win"
            elif winner_index == (1 - self.our_player_index):
                self.result = "loss"
            else:
                self.result = "draw"
        else:
            self.result = "unknown"

        duration = time.time() - (self.game_start_time or time.time())

        log.info("GameOver: result=%s winner=%s duration=%.0fs",
                 self.result, winner_index, duration)

        # Send acknowledgments
        if self.client and self.game_id and self.our_player_index is not None:
            self.client.send_finish_game(
                self.game_id,
                winner_index=winner_index if winner_index is not None else 0,
                player_index=self.our_player_index,
                duration=duration,
            )
            self.client.send_standup_game(self.game_id)

    # ------------------------------------------------------------------
    # Handler dispatch table
    # ------------------------------------------------------------------

    def _handle_player_disconnected(self, msg):
        """Handle PlayerDisconnected — track disconnect for deferred loading."""
        player_idx = msg[1] if len(msg) > 1 else None
        is_us = player_idx == self.our_player_index
        log.warning("PlayerDisconnected: player=%s (us=%s)", player_idx, is_us)
        if is_us:
            self._saw_disconnect = True

    def _handle_player_reconnected(self, msg):
        """Handle PlayerReconnected — send deferred loading now."""
        player_idx = msg[1] if len(msg) > 1 else None
        is_us = player_idx == self.our_player_index
        log.info("PlayerReconnected: player=%s (us=%s)", player_idx, is_us)
        if is_us and not self._loading_sent:
            self._send_loading()

    def _send_loading(self):
        """Send loading progress to the server."""
        if self._loading_sent or not self.client or not self.game_id:
            return
        self.client.send_loading_complete(self.game_id)
        self._loading_sent = True
        log.info("Sent loading complete")

    def check_deferred_loading(self):
        """Called from main loop — send loading if no disconnect occurred.

        If there was no PlayerDisconnected within 3s of BeginGame, send
        loading now (the node switch didn't happen this time).
        """
        if self._loading_sent or not self._begin_game_time:
            return
        if not self._saw_disconnect and time.time() - self._begin_game_time > 3.0:
            log.info("No PlayerDisconnected after 3s — sending loading now")
            self._send_loading()

    _HANDLERS = {
        "BeginGame": _handle_begin_game,
        "Loading": _handle_loading,
        "StartGrace": _handle_start_grace,
        "GraceOver": _handle_grace_over,
        "StartTurn": _handle_start_turn,
        "Click": _handle_click,
        "ManyClicks": _handle_many_clicks,
        "EndTurn": _handle_end_turn,
        "GameOver": _handle_game_over,
        "PlayerDisconnected": _handle_player_disconnected,
        "PlayerReconnected": _handle_player_reconnected,
    }
