'use strict';

const Database = require('better-sqlite3');
const path = require('path');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'deadgame.db');
const LADDER_DB_PATH = process.env.LADDER_DB_PATH || '/opt/prismata/<ladder>.db';
const RATING_THRESHOLD = parseInt(process.env.RATING_THRESHOLD, 10) || 1600;
const DAILY_CAP = parseInt(process.env.DAILY_CAP, 10) || 5;

// Main deadgame database
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    rating_snapshot REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'pending',
    deny_reason TEXT,
    matched_opponent TEXT,
    replay_code TEXT,
    result TEXT,
    bot_rating_before REAL,
    bot_rating_after REAL,
    completed_at TEXT
  );

  CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
`);

// --- Bot state ---

const stmtGetAllState = db.prepare('SELECT key, value FROM bot_state');
const stmtUpsertState = db.prepare(`
  INSERT INTO bot_state (key, value, updated_at) VALUES (?, ?, datetime('now'))
  ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
`);
const stmtGetState = db.prepare('SELECT value FROM bot_state WHERE key = ?');

function getBotState() {
  const rows = stmtGetAllState.all();
  const state = {};
  for (const row of rows) {
    state[row.key] = row.value;
  }
  return state;
}

function setBotState(key, value) {
  stmtUpsertState.run(key, String(value));
}

function isBotOnline() {
  const row = stmtGetState.get('last_heartbeat');
  if (!row) return false;
  const lastBeat = new Date(row.value + 'Z').getTime();
  const now = Date.now();
  if (now - lastBeat > 30000) return false;
  const killed = stmtGetState.get('killed');
  if (killed && killed.value === 'true') return false;
  return true;
}

function isBotAvailable() {
  if (!isBotOnline()) return false;
  const row = stmtGetState.get('state');
  return row && row.value === 'idle';
}

// --- Requests ---

const stmtCreateRequest = db.prepare(`
  INSERT INTO requests (username, rating_snapshot, status) VALUES (?, ?, 'pending')
`);
const stmtCreateDenied = db.prepare(`
  INSERT INTO requests (username, rating_snapshot, status, deny_reason) VALUES (?, ?, 'denied', ?)
`);
const stmtGetPending = db.prepare(`
  SELECT * FROM requests WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1
`);
const stmtConsume = db.prepare(`
  UPDATE requests SET status = 'consumed', matched_opponent = ? WHERE id = ?
`);
const stmtComplete = db.prepare(`
  UPDATE requests SET replay_code = ?, result = ?, bot_rating_before = ?, bot_rating_after = ?, completed_at = datetime('now') WHERE id = ?
`);
const stmtExpire = db.prepare(`
  UPDATE requests SET status = 'expired' WHERE status = 'pending' AND created_at < datetime('now', '-2 minutes')
`);
const stmtDailyCount = db.prepare(`
  SELECT COUNT(*) AS cnt FROM requests WHERE username = ? AND status = 'consumed' AND created_at >= date('now')
`);
const stmtLastRequestTime = db.prepare(`
  SELECT created_at FROM requests WHERE username = ? ORDER BY created_at DESC LIMIT 1
`);
const stmtLastGame = db.prepare(`
  SELECT * FROM requests WHERE replay_code IS NOT NULL ORDER BY completed_at DESC LIMIT 1
`);

function createRequest(username, ratingSnapshot) {
  const info = stmtCreateRequest.run(username, ratingSnapshot);
  return info.lastInsertRowid;
}

function createDeniedRequest(username, ratingSnapshot, reason) {
  const info = stmtCreateDenied.run(username, ratingSnapshot, reason);
  return info.lastInsertRowid;
}

function getPendingRequest() {
  return stmtGetPending.get() || null;
}

function consumeRequest(id, opponent) {
  stmtConsume.run(opponent, id);
}

function completeRequest(id, replayCode, result, botRatingBefore, botRatingAfter) {
  stmtComplete.run(replayCode, result, botRatingBefore, botRatingAfter, id);
}

function expirePendingRequests() {
  const info = stmtExpire.run();
  return info.changes;
}

function getDailyCount(username) {
  const row = stmtDailyCount.get(username);
  return row ? row.cnt : 0;
}

function getLastRequestTime(username) {
  const row = stmtLastRequestTime.get(username);
  return row ? row.created_at : null;
}

function getLastGame() {
  return stmtLastGame.get() || null;
}

// --- Ladder DB (separate, read-only) ---

let ladderDb = null;

function getLadderDb() {
  if (ladderDb) return ladderDb;
  try {
    ladderDb = new Database(LADDER_DB_PATH, { readonly: true });
    return ladderDb;
  } catch {
    return null;
  }
}

function getPlayerRating(prismataUsername) {
  const ldb = getLadderDb();
  if (!ldb) return null;
  try {
    // Check as p1
    const asP1 = ldb.prepare(`
      SELECT p1_elo AS rating FROM games WHERE p1_name = ? ORDER BY played_at DESC LIMIT 1
    `).get(prismataUsername);
    const asP2 = ldb.prepare(`
      SELECT p2_elo AS rating FROM games WHERE p2_name = ? ORDER BY played_at DESC LIMIT 1
    `).get(prismataUsername);

    if (!asP1 && !asP2) return null;
    if (!asP1) return asP2.rating;
    if (!asP2) return asP1.rating;

    // Return whichever is more recent — but we don't have the timestamp easily
    // compared across queries, so just take the max of two queries with played_at
    const best = ldb.prepare(`
      SELECT rating, played_at FROM (
        SELECT p1_elo AS rating, played_at FROM games WHERE p1_name = ?
        UNION ALL
        SELECT p2_elo AS rating, played_at FROM games WHERE p2_name = ?
      ) ORDER BY played_at DESC LIMIT 1
    `).get(prismataUsername, prismataUsername);
    return best ? best.rating : null;
  } catch {
    return null;
  }
}

function hasRecentLowRatedActivity() {
  const ldb = getLadderDb();
  if (!ldb) return false;
  try {
    const row = ldb.prepare(`
      SELECT COUNT(*) AS cnt FROM games
      WHERE played_at > datetime('now', '-30 minutes')
        AND (p1_elo < ? OR p2_elo < ?)
    `).get(RATING_THRESHOLD, RATING_THRESHOLD);
    return row && row.cnt > 0;
  } catch {
    return false;
  }
}

module.exports = {
  db,
  getBotState,
  setBotState,
  isBotOnline,
  isBotAvailable,
  createRequest,
  createDeniedRequest,
  getPendingRequest,
  consumeRequest,
  completeRequest,
  expirePendingRequests,
  getDailyCount,
  getLastRequestTime,
  getLastGame,
  getPlayerRating,
  hasRecentLowRatedActivity,
  RATING_THRESHOLD,
  DAILY_CAP,
};
