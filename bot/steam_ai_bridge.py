"""SteamAI Bridge — spawn PrismataAI.exe and get AI moves.

PrismataAI.exe is Steam's Master Bot binary. It's a one-shot process:
- Receives game state JSON via stdin (newline-terminated)
- Returns click response JSON via stdout (newline-terminated)
- Process exits after each response

Input format:
  {"mergedDeck": [...], "gameState": {...}, "aiParameters": {...}, "aiPlayerName": "HardestAI"}

Output format:
  {"aiclicks": [{_type, _id}, ...], "aithinktime": N, "eval": 0.5, "eval_pct": "50%"}
"""

import json
import re
import subprocess
from bot.config import PRISMATA_AI_EXE, STEAM_AI_TIMEOUT_S


class SteamAIBridge:
    def __init__(self, exe_path=None, timeout_s=None):
        self.exe_path = exe_path or PRISMATA_AI_EXE
        self.timeout_s = timeout_s or STEAM_AI_TIMEOUT_S

    def get_move(self, request_json):
        """Send game state to PrismataAI.exe and return parsed response.

        Args:
            request_json: JSON string or dict with mergedDeck, gameState,
                          aiParameters, aiPlayerName

        Returns:
            dict with keys: aiclicks, aithinktime, eval, eval_pct

        Raises:
            TimeoutError: if process doesn't respond within timeout
            RuntimeError: if process exits with error or returns invalid JSON
        """
        if isinstance(request_json, dict):
            request_json = json.dumps(request_json)

        payload = request_json if request_json.endswith('\n') else request_json + '\n'

        try:
            result = subprocess.run(
                [self.exe_path],
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"PrismataAI.exe did not respond within {self.timeout_s}s"
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"PrismataAI.exe exited with code {result.returncode}: "
                f"{result.stderr[:200] if result.stderr else 'no stderr'}"
            )

        stdout = result.stdout
        if not stdout.strip():
            raise RuntimeError("PrismataAI.exe returned empty output")

        clean = self._clean_response(stdout)

        try:
            response = json.loads(clean)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Invalid JSON from PrismataAI.exe: {e}\nRaw: {stdout[:200]}"
            )

        return response

    def _clean_response(self, raw):
        """Strip control characters from stdout before JSON parsing.

        PrismataAI.exe may emit control characters or debug output before
        the JSON response. Find the first '{' and strip control chars.
        """
        idx = raw.find('{')
        if idx == -1:
            return raw
        raw = raw[idx:]
        return re.sub(r'[\x00-\x1f]', ' ', raw).strip()

    def parse_eval_pct(self, response):
        """Extract numeric eval percentage from response.

        PrismataAI.exe returns eval_pct as a string like "70%".
        Returns float (e.g., 70.0) or None if not present.
        """
        eval_pct = response.get('eval_pct', '')
        if isinstance(eval_pct, str) and eval_pct.endswith('%'):
            try:
                return float(eval_pct[:-1])
            except ValueError:
                return None
        return None
