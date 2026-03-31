'use strict';

const express = require('express');
const db = require('../lib/db');
const { requireLogin, requireBotKey } = require('../lib/auth');

const router = express.Router();

const COOLDOWN_MS = 10 * 60 * 1000; // 10 minutes

// GET /api/bot/status — public, returns bot state
router.get('/status', (req, res) => {
  db.expirePendingRequests();

  const state = db.getBotState();
  const online = db.isBotOnline();
  const available = db.isBotAvailable();
  const pending = db.getPendingRequest();
  const lastGame = db.getLastGame();
  const activityDetected = db.hasRecentLowRatedActivity();

  res.json({
    state: online ? state.state : 'offline',
    online,
    available,
    pending_request: !!pending,
    activity_detected: activityDetected,
    last_game: lastGame ? {
      opponent: lastGame.matched_opponent,
      result: lastGame.result,
      replay_code: lastGame.replay_code,
      completed_at: lastGame.completed_at,
    } : null,
  });
});

// POST /api/bot/queue — requires login, creates a queue request
router.post('/queue', requireLogin, (req, res) => {
  const username = req.user.prismata_username;

  // Check kill switch
  const state = db.getBotState();
  if (state.killed === 'true') {
    return res.status(503).json({ error: 'Bot has been disabled' });
  }

  // Check bot online and available
  if (!db.isBotOnline()) {
    return res.status(503).json({ error: 'Bot is offline' });
  }
  if (!db.isBotAvailable()) {
    db.createDeniedRequest(username, null, 'bot_busy');
    return res.status(409).json({ error: 'Bot is busy — if multiple people want to play, try queuing ranked normally!' });
  }

  // Activity detection
  if (db.hasRecentLowRatedActivity()) {
    db.createDeniedRequest(username, null, 'activity_detected');
    return res.status(503).json({ error: 'Players are active right now — try queuing normally first!' });
  }

  // Rating check
  const rating = db.getPlayerRating(username);
  if (rating !== null && rating >= db.RATING_THRESHOLD) {
    db.createDeniedRequest(username, rating, 'rating_too_high');
    return res.status(403).json({
      error: `Your rating (${Math.round(rating)}) is high enough to find human opponents!`,
    });
  }

  // Daily cap
  const dailyCount = db.getDailyCount(username);
  if (dailyCount >= db.DAILY_CAP) {
    db.createDeniedRequest(username, rating, 'daily_cap');
    return res.status(429).json({
      error: `Daily limit reached (${db.DAILY_CAP} games per day)`,
      uses_today: dailyCount,
      daily_cap: db.DAILY_CAP,
    });
  }

  // Cooldown
  const lastReq = db.getLastRequestTime(username);
  if (lastReq) {
    const elapsed = Date.now() - new Date(lastReq + 'Z').getTime();
    if (elapsed < COOLDOWN_MS) {
      const remaining = Math.ceil((COOLDOWN_MS - elapsed) / 1000);
      return res.status(429).json({
        error: `Cooldown active — try again in ${remaining}s`,
        cooldown_remaining_s: remaining,
      });
    }
  }

  // Create request
  db.createRequest(username, rating);
  const usesRemaining = db.DAILY_CAP - dailyCount - 1;

  console.log(`[bot] Queue request from ${username} (rating: ${rating || 'new'}, remaining: ${usesRemaining})`);

  res.json({
    ok: true,
    message: 'Bot will queue for ranked shortly',
    disclaimer: 'You are not guaranteed to be matched against the bot — another player may get the match.',
    uses_remaining: usesRemaining,
    daily_cap: db.DAILY_CAP,
  });
});

// POST /api/bot/heartbeat — bot reports it's alive (requires API key)
router.post('/heartbeat', requireBotKey, (req, res) => {
  db.setBotState('last_heartbeat', new Date().toISOString());
  res.json({ ok: true });
});

// POST /api/bot/update-status — bot reports state change (requires API key)
router.post('/update-status', requireBotKey, (req, res) => {
  const { state, matched_opponent, replay_code, result, request_id } = req.body;

  if (state) {
    db.setBotState('state', state);
  }

  // If matched, mark request as consumed
  if (request_id && matched_opponent) {
    db.consumeRequest(request_id, matched_opponent);
  }

  // If game completed, update the request record
  if (request_id && (replay_code || result)) {
    db.completeRequest(request_id, replay_code, result, null, null);
  }

  res.json({ ok: true });
});

// POST /api/bot/kill — remote kill switch (requires API key)
router.post('/kill', requireBotKey, (req, res) => {
  db.setBotState('killed', 'true');
  db.setBotState('state', 'killed');
  console.log('[bot] KILL SWITCH ACTIVATED');
  res.json({ ok: true, message: 'Bot killed' });
});

// POST /api/bot/unkill — re-enable bot (requires API key)
router.post('/unkill', requireBotKey, (req, res) => {
  db.setBotState('killed', 'false');
  console.log('[bot] Kill switch deactivated');
  res.json({ ok: true });
});

module.exports = router;
