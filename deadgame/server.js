'use strict';

const express = require('express');
const path = require('path');
const cookieParser = require('cookie-parser');

const app = express();
app.use(express.json());
app.use(cookieParser());
app.set('trust proxy', 'loopback');

const PORT = process.env.PORT || 3101;

// Routes
const botRoutes = require('./routes/bot');
app.use('/api/bot', botRoutes);

// Health check
app.get('/healthz', (req, res) => res.json({ ok: true }));

// API 404
app.use('/api', (req, res) => res.status(404).json({ error: 'Not found' }));

// Static files
app.use(express.static(path.join(__dirname, 'public')));

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start
app.listen(PORT, () => {
  console.log(`[deadgame] Server listening on port ${PORT}`);
});
