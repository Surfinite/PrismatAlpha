"""GamePlayer -- manages a single Prismata game session.

Handles the full game lifecycle from BeginGame through turns to GameOver.
Receives server messages (via PrismataClient.on_message callback), tracks
game state, calls SteamAIBridge for AI moves, and sends clicks back.

Protocol flow per turn:
  Server: StartTurn
  Client: EndSwoosh -> [Click ...] -> EndTurn
  (repeat until GameOver)
"""

import logging
import time

from bot.config import RESIGN_EVAL_PCT_THRESHOLD, RESIGN_CONSECUTIVE_TURNS

log = logging.getLogger(__name__)


class GamePlayer:
    """Manages one game session from BeginGame to GameOver."""

    def __init__(self, bridge, client):
        """
        Args:
            bridge: SteamAIBridge instance (or None for testing).
            client: PrismataClient instance (or None for testing).
        """
        self.bridge = bridge
        self.client = client

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

        # Resignation tracking
        self._consecutive_low_evals = 0

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

        log.info(
            "BeginGame: game_id=%s format=%s player_index=%s opponent=%s",
            self.game_id, self.format, self.our_player_index, self.opponent_name,
        )

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
        """Handle Loading message -- send loading complete."""
        if self.client and self.game_id:
            self.client.send_loading_complete(self.game_id)
            log.debug("Sent loading complete for %s", self.game_id)

    def _handle_start_grace(self, msg):
        """Handle StartGrace -- send Endgrace to skip countdown."""
        if self.client and self.game_id:
            self.client.send_endgrace(self.game_id)
            log.debug("Sent Endgrace for %s", self.game_id)

    def _handle_grace_over(self, msg):
        """Handle GraceOver -- grace period ended."""
        log.debug("Grace period over for %s", self.game_id)

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

    def _is_our_turn(self):
        """Check if the current turn belongs to us.

        Turn 0 = P0, turn 1 = P1, turn 2 = P0, etc.
        """
        if self.our_player_index is None:
            return False
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

        # 3. Get AI move
        clicks = self._get_ai_move()
        if clicks is None:
            log.error("Failed to get AI move at turn %d, sending empty turn",
                      self.current_turn)
            clicks = []

        # 4. Send clicks
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

        TODO: This is the v1 approach -- pass the init_info with accumulated
        commandInfo. If PrismataAI.exe can't handle this format, we'll need
        to build a proper gameState snapshot (as matchup_clean.js does).

        Returns:
            dict suitable for SteamAIBridge.get_move(), or None on failure.
        """
        if not self.init_info:
            log.error("No init_info available for AI request")
            return None

        # Update commandInfo with accumulated clicks
        request = dict(self.init_info)
        request["commandInfo"] = {
            "commandList": self.command_list,
            "clicksPerTurn": self.clicks_per_turn,
        }

        return request

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
            log.debug("Opponent click: %s", click_data)

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

    _HANDLERS = {
        "BeginGame": _handle_begin_game,
        "Loading": _handle_loading,
        "StartGrace": _handle_start_grace,
        "GraceOver": _handle_grace_over,
        "StartTurn": _handle_start_turn,
        "Click": _handle_click,
        "EndTurn": _handle_end_turn,
        "GameOver": _handle_game_over,
    }
