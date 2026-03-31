# bot/trigger_poller.py
"""Trigger poller — polls deadgame.prismata.live for queue requests.

Sends heartbeats so the site knows the bot is online.
Reports state changes back to the site.
"""

import time
import json
import logging
import urllib.request
import urllib.error
from bot.config import (
    TRIGGER_SITE_URL, TRIGGER_POLL_INTERVAL_S,
    HEARTBEAT_INTERVAL_S, BOT_API_KEY,
)

log = logging.getLogger('poller')


class TriggerPoller:
    """Polls the trigger site for queue requests."""

    def __init__(self):
        self.base_url = TRIGGER_SITE_URL.rstrip('/')
        self.last_heartbeat = 0
        self.last_poll = 0

    def poll(self):
        """Check for pending queue requests.

        Returns True if a queue request is pending.
        Also sends heartbeat if enough time has elapsed.
        """
        now = time.time()

        # Send heartbeat if due
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL_S:
            self._send_heartbeat()
            self.last_heartbeat = now

        # Poll for status
        if now - self.last_poll < TRIGGER_POLL_INTERVAL_S:
            return False
        self.last_poll = now

        try:
            data = self._get('/api/bot/status')
            return data.get('pending_request', False)
        except Exception as e:
            log.warning(f"Poll failed: {e}")
            return False

    def update_status(self, state, **kwargs):
        """Report state change to the trigger site.

        Args:
            state: 'idle', 'queuing', 'playing'
            **kwargs: optional fields: matched_opponent, replay_code, result, request_id
        """
        body = {'state': state, **kwargs}
        try:
            self._post('/api/bot/update-status', body)
        except Exception as e:
            log.warning(f"Status update failed: {e}")

    def _send_heartbeat(self):
        try:
            self._post('/api/bot/heartbeat', {})
        except Exception as e:
            log.warning(f"Heartbeat failed: {e}")

    def _get(self, path):
        url = self.base_url + path
        req = urllib.request.Request(url)
        if BOT_API_KEY:
            req.add_header('Authorization', f'Bearer {BOT_API_KEY}')
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def _post(self, path, body):
        url = self.base_url + path
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/json')
        if BOT_API_KEY:
            req.add_header('Authorization', f'Bearer {BOT_API_KEY}')
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
