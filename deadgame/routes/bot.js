'use strict';
const express = require('express');
const router = express.Router();
router.get('/status', (req, res) => res.json({ state: 'offline', online: false }));
module.exports = router;
