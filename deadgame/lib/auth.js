'use strict';

const { jwtVerify } = require('jose');

const SESSION_COOKIE = 'prismata_session';
const SESSION_SECRET = new TextEncoder().encode(
  process.env.SESSION_SECRET || 'dev-secret-change-in-production'
);
const BOT_API_KEY = process.env.BOT_API_KEY || '';

async function getSessionFromRequest(req) {
  const token = req.cookies?.[SESSION_COOKIE];
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, SESSION_SECRET);
    return payload.user || null;
  } catch {
    return null;
  }
}

function requireLogin(req, res, next) {
  getSessionFromRequest(req).then(user => {
    if (!user) return res.status(401).json({ error: 'Not logged in' });
    if (!user.prismata_username) return res.status(403).json({ error: 'No Prismata account linked' });
    req.user = user;
    next();
  }).catch(() => res.status(401).json({ error: 'Invalid session' }));
}

function requireBotKey(req, res, next) {
  if (!BOT_API_KEY) return res.status(500).json({ error: 'Bot API key not configured' });
  const key = req.headers['authorization']?.replace('Bearer ', '');
  if (key !== BOT_API_KEY) return res.status(401).json({ error: 'Invalid bot API key' });
  next();
}

module.exports = { getSessionFromRequest, requireLogin, requireBotKey };
