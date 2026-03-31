"""StateBridge — manages a Node.js state tracker subprocess.

Spawns js_engine/state_tracker.js as a long-running child process.
Communicates via JSON lines on stdin/stdout.
"""

import json
import logging
import os
import subprocess
import threading

log = logging.getLogger(__name__)

_STATE_TRACKER_JS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'js_engine', 'state_tracker.js'
))

_SEND_TIMEOUT_S = 30


class StateBridge:
    """Manage a Node.js state tracker subprocess."""

    def __init__(self, node_path='node'):
        self.node_path = node_path
        self.proc = None
        self._stderr_thread = None
        self._stderr_lines = []

    def start(self, merged_deck):
        """Spawn the state tracker and initialize with merged_deck.
        Idempotent: closes any existing process before starting a new one.
        Returns dict with 'ok' key.
        """
        self.close()  # idempotent
        try:
            self.proc = subprocess.Popen(
                [self.node_path, _STATE_TRACKER_JS],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=os.path.dirname(_STATE_TRACKER_JS),
            )
        except (FileNotFoundError, OSError) as e:
            return {'ok': False, 'error': f'Failed to start state tracker: {e}'}

        # Drain stderr in background thread to prevent pipe buffer fill-up
        self._stderr_lines = []
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        return self._send({'cmd': 'INIT', 'mergedDeck': merged_deck})

    def _drain_stderr(self):
        """Read stderr lines in background (prevents pipe buffer fill)."""
        try:
            for line in self.proc.stderr:
                line = line.rstrip('\n')
                if line:
                    self._stderr_lines.append(line)
                    if len(self._stderr_lines) > 100:
                        self._stderr_lines.pop(0)
                    log.debug("state_tracker: %s", line)
        except (ValueError, OSError):
            pass

    def reinit_from_clicks(self, merged_deck, command_info):
        """Re-initialize the state tracker with full click history (both players).

        Used after ObserveTopGame to rebuild state from authoritative commandInfo.

        Args:
            merged_deck: list, the mergedDeck from BeginGame.
            command_info: dict with 'commandList' and 'clicksPerTurn' arrays.

        Returns:
            dict with 'ok', 'turn', 'phase' keys.
        """
        return self._send({
            'cmd': 'REINIT',
            'mergedDeck': merged_deck,
            'commandInfo': command_info,
        })

    def export_state(self):
        """Export current game state. Returns dict with 'ok' and 'state' keys."""
        return self._send({'cmd': 'EXPORT'})

    def apply_clicks(self, clicks):
        """Apply clicks to advance the game state. Returns dict with 'ok', 'applied', 'failed'."""
        return self._send({'cmd': 'CLICKS', 'clicks': clicks})

    def close(self):
        """Shut down the Node.js subprocess."""
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None

    def _send(self, msg, timeout=None):
        """Send a JSON command and read the JSON response.
        Uses a background thread + timeout to avoid hanging forever.
        """
        timeout = timeout or _SEND_TIMEOUT_S
        if not self.proc or self.proc.poll() is not None:
            return {'ok': False, 'error': 'State tracker process not running'}

        line = json.dumps(msg, separators=(',', ':')) + '\n'
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            return {'ok': False, 'error': f'Pipe error writing: {e}'}

        # Read with timeout via a thread
        result = [None]

        def read_response():
            try:
                result[0] = self.proc.stdout.readline()
            except Exception:
                pass

        reader = threading.Thread(target=read_response, daemon=True)
        reader.start()
        reader.join(timeout=timeout)

        if reader.is_alive():
            stderr_tail = '\n'.join(self._stderr_lines[-5:])
            return {'ok': False, 'error': f'Timeout ({timeout}s) waiting for state tracker. stderr: {stderr_tail}'}

        response_line = result[0]
        if not response_line:
            stderr_tail = '\n'.join(self._stderr_lines[-5:])
            return {'ok': False, 'error': f'No response from state tracker. stderr: {stderr_tail}'}

        try:
            return json.loads(response_line)
        except json.JSONDecodeError as e:
            return {'ok': False, 'error': f'Invalid JSON response: {e}'}
