# bot/ranked_bot.py
"""DeadGameBot -- on-demand ranked bot for Prismata.

Main entry point. Connects to Prismata server, authenticates, and waits
for queue triggers.

State machine:
  IDLE -> QUEUING -> PLAYING -> IDLE

Usage:
  python -m bot.ranked_bot

Environment variables:
  BOT_USERNAME -- Prismata account username (default: DeadGameBot)
  BOT_PASSWORD -- Prismata account password (required)
  BOT_API_KEY -- API key for deadgame.prismata.live (optional until Phase 4)
  PRISMATA_AI_EXE -- Path to PrismataAI.exe
"""

import sys
import time
import signal
import logging

from bot.config import BOT_USERNAME, BOT_PASSWORD, QUEUE_TIMEOUT_S
from bot.client import PrismataClient
from bot.steam_ai_bridge import SteamAIBridge
from bot.game_player import GamePlayer
from bot.state_bridge import StateBridge
from bot.trigger_poller import TriggerPoller

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('bot')


class DeadGameBot:
    """Main bot orchestrator."""

    IDLE = "idle"
    QUEUING = "queuing"
    PLAYING = "playing"

    def __init__(self):
        self.state = self.IDLE
        self.running = True
        self.client = PrismataClient()
        self.bridge = SteamAIBridge()
        self.state_bridge = StateBridge()
        self.player = GamePlayer(self.bridge, self.client, state_bridge=self.state_bridge)
        self.poller = TriggerPoller()
        self._queue_start = 0
        self._pending_requeue = False

        # Wire up message handling
        self.client.on_message = self._on_message

    def start(self):
        """Connect, authenticate, and enter main loop."""
        if not BOT_PASSWORD:
            log.error("BOT_PASSWORD environment variable not set")
            sys.exit(1)

        log.info(f"Starting DeadGameBot as {BOT_USERNAME}")

        self.client.connect()
        self.client.login(BOT_USERNAME, BOT_PASSWORD)

        if not self._wait_for_lobby(timeout=30):
            log.warning("Did not receive SplashToLobby within 30s")

        log.info(f"Ready. State: {self.state}")
        self._main_loop()

    def _main_loop(self):
        """Main event loop."""
        while self.running:
            try:
                self.client.pump_messages(timeout=1)

                if self.state == self.IDLE:
                    if self.poller.poll():
                        log.info("Queue request received from trigger site!")
                        self.queue_for_ranked()

                elif self.state == self.QUEUING:
                    if time.time() - self._queue_start > QUEUE_TIMEOUT_S:
                        log.info("Queue timed out, returning to IDLE")
                        self.client.cancel_queue()
                        self._set_state(self.IDLE)

                elif self.state == self.PLAYING:
                    if self.player.game_over:
                        replay = getattr(self.player, 'replay_code', None)
                        log.info(f"Game over: {self.player.result}"
                                 + (f", replay: {replay}" if replay else ""))
                        self.player.reset()
                        # Wait for SplashToLobby
                        self._wait_for_lobby(timeout=10)
                        self._set_state(self.IDLE)

            except KeyboardInterrupt:
                log.info("Interrupted, shutting down...")
                self.running = False
            except Exception as e:
                log.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(1)

        self.client.disconnect()
        log.info("Shut down.")

    def _on_message(self, inner):
        """Handle messages from the Prismata server."""
        if not inner:
            return

        msg_type = inner[0]

        if msg_type == "BeginGame":
            if self.state == self.IDLE:
                # Resumed game from a previous crash — resign it
                self._abandon_resumed_game(inner)
            else:
                self._set_state(self.PLAYING)
                self.player.handle_message(inner)
        elif msg_type == "ReconnectGame":
            # Server sent full game state after AttemptReconnect.
            log.info("ReconnectGame received — resuming game")
            if self.state in (self.IDLE, self.QUEUING):
                # Stale game from previous session — resign it
                log.info("Abandoning stale reconnected game")
                self._abandon_resumed_game(["BeginGame", inner[1]])
            else:
                self._set_state(self.PLAYING)
                self.player.handle_message(["BeginGame", inner[1]])
        elif msg_type == "QuitGame" and self._pending_requeue:
            # Stale game fully cleared — re-send the original StartBotGame
            log.info("Stale game cleared, re-queuing for bot game")
            self._pending_requeue = False
            self.queue_for_bot_game()
        elif self.state == self.PLAYING:
            self.player.handle_message(inner)
        elif msg_type == "SplashToLobby":
            # Already handled by client, but note it
            pass

    def _abandon_resumed_game(self, begin_game_msg):
        """Resign a game resumed from a previous session."""
        info = begin_game_msg[1] if len(begin_game_msg) > 1 else {}
        game_id = info.get("liveGameID", "")
        log.warning("Abandoning resumed game %s from previous session", game_id)

        # Determine our player index to resign properly
        lane_info = info.get("laneInfo", [{}])
        players = lane_info[0].get("players", []) if lane_info else []
        our_idx = 0
        username = self.client.username
        for i, p in enumerate(players):
            if p.get("displayName") == username or p.get("name") == username:
                our_idx = i
                break

        # Resign: finishGame with opponent as winner
        winner = 1 - our_idx
        self.client.send_finish_game(game_id, winner_index=winner,
                                     player_index=our_idx, duration=0, resigned=True)
        self.client.send_standup_game(game_id)
        self._pending_requeue = True
        log.info("Resigned abandoned game, will re-queue after QuitGame")

    def _wait_for_lobby(self, timeout=30):
        """Poll messages until lobby_ready or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.client.pump_messages(timeout=1)
            if self.client.lobby_ready:
                return True
        return False

    def _set_state(self, new_state):
        """Transition to a new state."""
        old = self.state
        self.state = new_state
        log.info(f"State: {old} -> {new_state}")
        self.poller.update_status(new_state)

    # --- Manual triggers (for testing) ---

    def queue_for_bot_game(self):
        """Start a game vs the in-game Master Bot."""
        log.info("Starting bot game...")
        self.player.reset()
        self.player.client_username = self.client.username
        self.client.start_bot_game()
        self._set_state(self.QUEUING)
        self._queue_start = time.time()

    def queue_for_ranked(self):
        """Queue for ranked play."""
        log.info("Queuing for ranked...")
        self.player.reset()
        self.player.client_username = self.client.username
        self.client.queue_ranked()
        self._set_state(self.QUEUING)
        self._queue_start = time.time()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='DeadGameBot')
    parser.add_argument('--bot-game', action='store_true',
                        help='Immediately start a game vs Master Bot (for testing)')
    parser.add_argument('--ranked', action='store_true',
                        help='Immediately queue for ranked (for testing)')
    args = parser.parse_args()

    bot = DeadGameBot()

    def handle_sigint(sig, frame):
        bot.running = False
    signal.signal(signal.SIGINT, handle_sigint)

    if args.bot_game or args.ranked:
        # Connect, login, then trigger immediately
        if not BOT_PASSWORD:
            log.error("BOT_PASSWORD environment variable not set")
            sys.exit(1)
        log.info(f"Starting DeadGameBot as {BOT_USERNAME}")
        bot.client.connect()
        bot.client.login(BOT_USERNAME, BOT_PASSWORD)
        if not bot._wait_for_lobby(timeout=30):
            log.warning("Did not receive SplashToLobby within 30s")
        log.info(f"Ready. State: {bot.state}")
        if args.bot_game:
            bot.queue_for_bot_game()
        else:
            bot.queue_for_ranked()
        bot._main_loop()
    else:
        bot.start()


if __name__ == "__main__":
    main()
