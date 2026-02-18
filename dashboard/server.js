const express = require('express');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawn } = require('child_process');

const app = express();
const PORT = process.env.PORT || 3000;
const BASE = process.env.DASHBOARD_BASE || 'c:/libraries/PrismataAI';
const BIND_LAN = process.env.BIND_LAN === '1' || process.argv.includes('--lan');
const BIND_HOST = BIND_LAN ? '0.0.0.0' : '127.0.0.1';
const DASHBOARD_TOKEN = process.env.DASHBOARD_TOKEN || (BIND_LAN ? crypto.randomBytes(16).toString('hex') : null);

// Selfplay binary shard format constants
const HEADER_SIZE = 64;
const FOOTER_SIZE = 4;
const OVERHEAD_SIZE = HEADER_SIZE + FOOTER_SIZE; // 68 bytes
const RECORD_SIZE = 7152;

// --- Helpers ---

function readJsonWithBom(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(raw.replace(/^\uFEFF/, ''));
  } catch (e) {
    return null;
  }
}

function readLastLines(filePath, count) {
  try {
    const fd = fs.openSync(filePath, 'r');
    const stat = fs.fstatSync(fd);
    if (stat.size === 0) { fs.closeSync(fd); return []; }

    // Read from the end in chunks to find enough lines
    const chunkSize = Math.min(stat.size, 8192);
    let collected = [];
    let pos = stat.size;

    while (collected.length <= count && pos > 0) {
      const readSize = Math.min(chunkSize, pos);
      pos -= readSize;
      const buf = Buffer.alloc(readSize);
      fs.readSync(fd, buf, 0, readSize, pos);
      let text = buf.toString('utf8');
      if (pos === 0) text = text.replace(/^\uFEFF/, ''); // strip BOM
      const chunk = text.split(/\r?\n/).filter(l => l.trim());
      collected = chunk.concat(collected);
    }

    fs.closeSync(fd);
    return collected.slice(-count);
  } catch (e) {
    return [];
  }
}

function parseLogLine(line) {
  const match = line.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.*)$/);
  if (!match) return { time: null, message: line, type: 'unknown' };
  const [, time, message] = match;
  let type = 'check';
  if (/CHANGE:/i.test(message)) type = 'change';
  else if (/WARNING:/i.test(message)) type = 'warning';
  else if (/scale-up/i.test(message)) type = 'scale';
  else if (/S3 sync/i.test(message)) type = 'sync';
  else if (/relaunch/i.test(message)) type = 'relaunch';
  else if (/Check/i.test(message)) type = 'check';
  return { time, message, type };
}

// --- SSE ---

const sseClients = new Set();

function broadcast(event, data) {
  const msg = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const res of sseClients) {
    try { res.write(msg); } catch (e) { sseClients.delete(res); }
  }
}

// S9: SSE heartbeat — keep connections alive, prune dead clients
const heartbeatInterval = setInterval(() => {
  for (const res of sseClients) {
    if (res.socket?.destroyed) {
      sseClients.delete(res);
    } else {
      try { res.write(': heartbeat\n\n'); } catch (e) { sseClients.delete(res); }
    }
  }
}, 30000);

// S10: Simple rate limiter — per-key cooldown (no external deps)
const rateLimits = new Map();
function rateLimit(key, cooldownMs) {
  const now = Date.now();
  const last = rateLimits.get(key) || 0;
  if (now - last < cooldownMs) return false;
  rateLimits.set(key, now);
  return true;
}

// S22: File watchers — only active when SSE clients are connected
const statusPath = path.join(BASE, 'aws/watcher_status.json');
const logPath = path.join(BASE, 'aws/watcher_log.txt');
let lastLogSize = 0;
try { lastLogSize = fs.statSync(logPath).size; } catch (e) {}
let watchersActive = false;

function statusWatcher(curr, prev) {
  if (curr.mtimeMs !== prev.mtimeMs) {
    setTimeout(() => {
      const status = readJsonWithBom(statusPath);
      if (status) broadcast('status', status);
    }, 200);
  }
}

function logWatcher(curr) {
  if (curr.size < lastLogSize) lastLogSize = 0;
  if (curr.size > lastLogSize) {
    const buf = Buffer.alloc(curr.size - lastLogSize);
    const fd = fs.openSync(logPath, 'r');
    fs.readSync(fd, buf, 0, buf.length, lastLogSize);
    fs.closeSync(fd);
    const newLines = buf.toString('utf8').split(/\r?\n/).filter(l => l.trim());
    for (const line of newLines) {
      broadcast('log', parseLogLine(line));
    }
    lastLogSize = curr.size;
  }
}

function startWatchers() {
  if (watchersActive) return;
  watchersActive = true;
  fs.watchFile(statusPath, { interval: 5000 }, statusWatcher);
  fs.watchFile(logPath, { interval: 5000 }, logWatcher);
}

function stopWatchers() {
  if (!watchersActive) return;
  watchersActive = false;
  fs.unwatchFile(statusPath, statusWatcher);
  fs.unwatchFile(logPath, logWatcher);
}

// --- Data stats cache ---

let dataStatsCache = null;
let dataStatsCacheTime = 0;
let dataStatsInFlight = null;

async function getDataStats() {
  const now = Date.now();
  if (dataStatsCache && now - dataStatsCacheTime < 60000) return dataStatsCache;
  // Coalesce concurrent requests
  if (dataStatsInFlight) return dataStatsInFlight;

  dataStatsInFlight = (async () => {
    const selfplayDir = path.join(BASE, 'bin/training/data/selfplay');
    let totalRecords = 0;
    let shardCount = 0;

    async function walkDir(dir) {
      try {
        const entries = await fs.promises.readdir(dir, { withFileTypes: true });
        for (const entry of entries) {
          const full = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            await walkDir(full);
          } else if (entry.name.endsWith('.bin')) {
            try {
              const stat = await fs.promises.stat(full);
              if (stat.size > OVERHEAD_SIZE) {
                shardCount++;
                totalRecords += Math.floor((stat.size - OVERHEAD_SIZE) / RECORD_SIZE);
              }
            } catch (e) {}
          }
        }
      } catch (e) {}
    }
    await walkDir(selfplayDir);

    dataStatsCache = {
      records: totalRecords,
      games: Math.floor(totalRecords / 37),
      shards: shardCount,
      target: 500000
    };
    dataStatsCacheTime = Date.now();
    dataStatsInFlight = null;
    return dataStatsCache;
  })();

  return dataStatsInFlight;
}

// --- Action system ---

const activeOps = new Map();

// S14: Load action registry from config file
function loadActionRegistry() {
  try {
    const raw = fs.readFileSync(path.join(__dirname, 'actions.json'), 'utf8');
    return JSON.parse(raw);
  } catch (e) {
    console.error('Failed to load actions.json:', e.message);
    return {};
  }
}
let ACTION_REGISTRY = loadActionRegistry();

// --- Logs directory for action output (S3) ---
const logsDir = path.join(__dirname, 'logs');
try { fs.mkdirSync(logsDir, { recursive: true }); } catch (e) {}

// --- Auth middleware (S1) ---
function authMiddleware(req, res, next) {
  // CSRF protection: reject POSTs with foreign Origin header
  const origin = req.headers.origin;
  if (origin) {
    try {
      const host = new URL(origin).hostname;
      if (host !== 'localhost' && host !== '127.0.0.1' &&
          !host.startsWith('192.168.') && !host.startsWith('10.')) {
        return res.status(403).json({ error: 'Cross-origin request blocked' });
      }
    } catch (e) {
      return res.status(403).json({ error: 'Invalid origin' });
    }
  }
  // Token auth (required when LAN mode is active)
  if (DASHBOARD_TOKEN) {
    const token = req.headers['x-dashboard-token'];
    if (token !== DASHBOARD_TOKEN) {
      return res.status(401).json({ error: 'Unauthorized — include X-Dashboard-Token header' });
    }
  }
  next();
}

// --- API Routes ---

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// SSE endpoint
app.get('/api/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  sseClients.add(res);
  if (sseClients.size === 1) startWatchers(); // S22: start watching when first client connects
  req.on('close', () => {
    sseClients.delete(res);
    if (sseClients.size === 0) stopWatchers(); // S22: stop watching when last client disconnects
  });

  // Send initial data
  const status = readJsonWithBom(statusPath);
  if (status) res.write(`event: status\ndata: ${JSON.stringify(status)}\n\n`);
});

// Watcher status
app.get('/api/status', (req, res) => {
  const data = readJsonWithBom(path.join(BASE, 'aws/watcher_status.json'));
  if (!data) return res.status(500).json({ error: 'Could not read watcher_status.json' });
  res.json(data);
});

// Watcher config
app.get('/api/config', (req, res) => {
  const data = readJsonWithBom(path.join(BASE, 'aws/watcher_config.json'));
  if (!data) return res.status(500).json({ error: 'Could not read watcher_config.json' });
  res.json(data);
});

// S16: All experiments summary (async)
app.get('/api/experiments', async (req, res) => {
  const runsDir = path.join(BASE, 'training/runs');
  try {
    const files = (await fs.promises.readdir(runsDir)).filter(f => f.endsWith('.json')).sort();
    const experiments = (await Promise.all(files.map(async f => {
      try {
        const raw = await fs.promises.readFile(path.join(runsDir, f), 'utf8');
        const data = JSON.parse(raw);
        const hp = data.hyperparameters || {};
        const epochs = data.epochs || [];
        const stepEvals = data.step_evals || [];

        let bestBrier = Infinity;
        let bestAcc = 0;
        for (const e of epochs) {
          if (e.brier_score != null && e.brier_score < bestBrier) bestBrier = e.brier_score;
          if (e.val_value_acc != null && e.val_value_acc > bestAcc) bestAcc = e.val_value_acc;
        }
        for (const s of stepEvals) {
          if (s.brier_score != null && s.brier_score < bestBrier) bestBrier = s.brier_score;
          if (s.val_value_acc != null && s.val_value_acc > bestAcc) bestAcc = s.val_value_acc;
        }

        return {
          timestamp: data.timestamp || f.replace('.json', ''),
          hidden_dim: hp.hidden_dim || 512,
          lr: hp.lr || 0.0003,
          loss_fn: hp.loss_fn || 'mse',
          tanh: hp.tanh_in_training || hp.use_tanh || false,
          subsample_every: hp.subsample_every || 1,
          model_params: data.model_params || 0,
          train_examples: (data.data || {}).train_examples || 0,
          best_brier: bestBrier === Infinity ? null : Math.round(bestBrier * 10000) / 10000,
          best_val_acc: Math.round(bestAcc * 10000) / 10000,
          best_epoch: data.best_epoch || null,
          best_step: data.best_step || null,
          total_time_s: data.total_wall_time_s || null,
          num_epochs: epochs.length
        };
      } catch (e) {
        return null;
      }
    }))).filter(Boolean);

    res.json(experiments);
  } catch (e) {
    res.status(500).json({ error: 'Could not read training runs' });
  }
});

// Single experiment detail
app.get('/api/experiment/:timestamp', (req, res) => {
  const ts = req.params.timestamp.replace(/[^0-9_]/g, ''); // sanitize
  const filePath = path.join(BASE, 'training/runs', `${ts}.json`);
  try {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    res.json(data);
  } catch (e) {
    res.status(404).json({ error: 'Experiment not found' });
  }
});

// Watcher log
app.get('/api/log', (req, res) => {
  const lines = parseInt(req.query.lines) || 100;
  const clamped = Math.min(Math.max(lines, 10), 500);
  const rawLines = readLastLines(path.join(BASE, 'aws/watcher_log.txt'), clamped);
  const parsed = rawLines.map(parseLogLine).reverse(); // newest first
  res.json(parsed);
});

// Data generation stats
app.get('/api/data-stats', async (req, res) => {
  res.json(await getDataStats());
});

// Tournament logs
app.get('/api/tournaments', (req, res) => {
  const tournaments = [];
  try {
    const dirs = fs.readdirSync(BASE).filter(d => d.startsWith('bin_eval_'));
    for (const dir of dirs) {
      const dirPath = path.join(BASE, dir);
      try {
        const logs = fs.readdirSync(dirPath).filter(f => f.startsWith('tournament_') && f.endsWith('.log'));
        for (const log of logs) {
          const content = fs.readFileSync(path.join(dirPath, log), 'utf8');
          const lines = content.split(/\r?\n/);
          // Try to find tournament name and stats
          const nameLine = lines.find(l => /Tournament '/.test(l));
          const name = nameLine ? nameLine.match(/Tournament '([^']+)'/)?.[1] : log;
          const hiddenMatch = content.match(/hidden=(\d+)/);
          tournaments.push({
            dir: dir,
            file: log,
            name: name || log,
            hidden_dim: hiddenMatch ? parseInt(hiddenMatch[1]) : null,
            lines: lines.length
          });
        }
      } catch (e) {}
    }
  } catch (e) {}
  res.json(tournaments);
});

// Action status
app.get('/api/actions/status', (req, res) => {
  const statuses = {};
  for (const [name, info] of activeOps) {
    statuses[name] = { running: true, startTime: info.startTime, pid: info.child.pid };
  }
  res.json({ actions: ACTION_REGISTRY, active: statuses });
});

// Action info (for confirmation)
app.get('/api/action/:name', (req, res) => {
  const action = ACTION_REGISTRY[req.params.name];
  if (!action) return res.status(404).json({ error: 'Unknown action' });
  if (activeOps.has(req.params.name)) {
    return res.status(409).json({ error: 'already_running', startTime: activeOps.get(req.params.name).startTime });
  }
  res.json(action);
});

// Execute action
app.post('/api/action/:name/confirm', authMiddleware, (req, res) => {
  const name = req.params.name;
  const action = ACTION_REGISTRY[name];
  if (!action) return res.status(404).json({ error: 'Unknown action' });
  if (activeOps.has(name)) {
    return res.status(409).json({ error: 'already_running' });
  }

  // S10: rate limit actions
  const cooldown = name === 'refresh' ? 5000 : 2000;
  if (!rateLimit('action-' + name, cooldown)) {
    return res.status(429).json({ error: 'Too soon — try again in a few seconds' });
  }

  // S20: check action conflicts
  const conflicts = action.conflicts || [];
  for (const dep of conflicts) {
    if (activeOps.has(dep)) {
      return res.status(409).json({ error: `Blocked — "${ACTION_REGISTRY[dep]?.label || dep}" is still running` });
    }
  }
  // Also check if any running action conflicts with this one
  for (const [runName, runInfo] of activeOps) {
    const runConflicts = ACTION_REGISTRY[runName]?.conflicts || [];
    if (runConflicts.includes(name)) {
      return res.status(409).json({ error: `Blocked — "${ACTION_REGISTRY[runName]?.label || runName}" conflicts` });
    }
  }

  // Refresh is special — no shell
  if (name === 'refresh') {
    dataStatsCache = null; // bust cache
    const status = readJsonWithBom(statusPath);
    if (status) broadcast('status', status);
    return res.json({ started: true, completed: true });
  }

  const [cmd, args] = action.command;
  const isWindows = process.platform === 'win32';
  const spawnOpts = {
    cwd: action.cwd || BASE,
    windowsHide: true,
    env: { ...process.env }
  };

  // For bash scripts on Windows, use Git Bash
  if (cmd === 'bash' && isWindows) {
    spawnOpts.shell = 'C:/Program Files/Git/bin/bash.exe';
  }
  // For python, ensure unbuffered output
  if (cmd === 'python') {
    spawnOpts.env.PYTHONUNBUFFERED = '1';
    spawnOpts.env.PYTHONIOENCODING = 'utf-8';
  }

  const child = spawn(cmd, args, spawnOpts);
  const startTime = new Date().toISOString();
  const logFile = path.join(logsDir, `${name}-${startTime.replace(/[:.]/g, '-')}.log`);
  const logStream = fs.createWriteStream(logFile, { flags: 'a' });
  logStream.write(`[${startTime}] Action: ${action.label}\n`);
  activeOps.set(name, { child, startTime, logFile });

  broadcast('op-started', { op: name, label: action.label, startTime });

  child.stdout.on('data', (chunk) => {
    const text = chunk.toString();
    logStream.write(text);
    broadcast('op-progress', { op: name, stream: 'stdout', text });
  });
  child.stderr.on('data', (chunk) => {
    const text = chunk.toString();
    logStream.write(text);
    broadcast('op-progress', { op: name, stream: 'stderr', text });
  });
  child.on('close', (code) => {
    logStream.write(`\n[${new Date().toISOString()}] Exit code: ${code}\n`);
    logStream.end();
    activeOps.delete(name);
    broadcast('op-complete', { op: name, label: action.label, code, startTime });
  });
  child.on('error', (err) => {
    logStream.write(`\n[${new Date().toISOString()}] Error: ${err.message}\n`);
    logStream.end();
    activeOps.delete(name);
    broadcast('op-complete', { op: name, label: action.label, code: -1, error: err.message, startTime });
  });

  res.json({ started: true, pid: child.pid });
});

// S13: Cancel running action
app.post('/api/action/:name/cancel', authMiddleware, (req, res) => {
  const name = req.params.name;
  if (!rateLimit('cancel-' + name, 2000)) {
    return res.status(429).json({ error: 'Too soon — try again in a few seconds' });
  }
  const op = activeOps.get(name);
  if (!op) return res.status(404).json({ error: 'No running action with that name' });
  try {
    op.child.kill('SIGTERM');
  } catch (e) {
    return res.status(500).json({ error: 'Failed to kill process: ' + e.message });
  }
  res.json({ cancelled: true, pid: op.child.pid });
});

// --- Cloud costs cache ---

let cloudCostsCache = null;
let cloudCostsCacheTime = 0;
let cloudCostsInFlight = null;

function execCmd(command, args, timeout = 15000, useCmd = false) {
  return new Promise((resolve) => {
    const { execFile } = require('child_process');
    const opts = { timeout, windowsHide: true };
    if (useCmd && process.platform === 'win32') {
      // Use cmd.exe for Windows-only CLIs (az, gcloud)
      opts.shell = 'cmd.exe';
    } else {
      opts.shell = true;
    }
    execFile(command, args, opts, (err, stdout, stderr) => {
      if (err) resolve({ error: err.message, stdout: stdout || '', stderr: stderr || '' });
      else resolve({ stdout: stdout.trim(), stderr: stderr.trim() });
    });
  });
}

async function getCloudCosts() {
  const now = Date.now();
  if (cloudCostsCache && now - cloudCostsCacheTime < 300000) return cloudCostsCache; // 5 min cache
  if (cloudCostsInFlight) return cloudCostsInFlight;

  cloudCostsInFlight = (async () => {
    const today = new Date();
    const endDate = new Date(today);
    endDate.setDate(endDate.getDate() + 1);
    const startStr = today.toISOString().slice(0, 8) + '01';
    const endStr = endDate.toISOString().slice(0, 10);

    const result = { aws: null, azure: null, gcp: null, fetched_at: new Date().toISOString() };

    // AWS Cost Explorer — grouped by record type
    // Write Azure request body to temp file to avoid shell escaping issues
    const azBody = JSON.stringify({
      type: 'ActualCost',
      timeframe: 'Custom',
      timePeriod: { from: startStr + 'T00:00:00Z', to: endStr + 'T00:00:00Z' },
      dataset: {
        granularity: 'None',
        aggregation: { totalCost: { name: 'Cost', function: 'Sum' } },
        grouping: [{ type: 'Dimension', name: 'ChargeType' }]
      }
    });
    const azBodyFile = path.join(require('os').tmpdir(), 'az_cost_body.json');
    fs.writeFileSync(azBodyFile, azBody, 'utf8');

    const subId = process.env.AZURE_SUBSCRIPTION_ID || 'e8b7ff8a-f6ce-4ae3-bb1e-6da11607cdbe';
    const [awsRes, azureRes] = await Promise.all([
      execCmd('aws', [
        'ce', 'get-cost-and-usage',
        '--time-period', `Start=${startStr},End=${endStr}`,
        '--granularity', 'MONTHLY',
        '--metrics', 'BlendedCost',
        '--group-by', 'Type=DIMENSION,Key=RECORD_TYPE'
      ]),
      execCmd('az', [
        'rest', '--method', 'post',
        '--url', `https://management.azure.com/subscriptions/${subId}/providers/Microsoft.CostManagement/query?api-version=2023-11-01`,
        '--body', `@${azBodyFile}`
      ], 15000, true)
    ]);

    // Parse AWS
    try {
      const awsData = JSON.parse(awsRes.stdout);
      const groups = awsData.ResultsByTime?.[0]?.Groups || [];
      let usage = 0, credits = 0, tax = 0;
      for (const g of groups) {
        const type = g.Keys[0];
        const amount = parseFloat(g.Metrics.BlendedCost.Amount) || 0;
        if (type === 'Usage') usage = amount;
        else if (type === 'Credit') credits = amount; // negative
        else if (type === 'Tax') tax = amount;
      }
      result.aws = {
        gross: Math.round(usage * 100) / 100,
        credits: Math.round(credits * 100) / 100,
        tax: Math.round(tax * 100) / 100,
        net: Math.round((usage + credits + tax) * 100) / 100,
        currency: 'USD',
        credit_allowance: 200,
        credit_label: '$200/12mo'
      };
    } catch (e) {
      result.aws = { error: 'Failed to query AWS costs' };
    }

    // Parse Azure
    try {
      const azData = JSON.parse(azureRes.stdout);
      const rows = azData.properties?.rows || [];
      let usage = 0;
      let currency = 'GBP';
      for (const row of rows) {
        if (row[1] === 'Usage') {
          usage = row[0];
          currency = row[2] || 'GBP';
        }
      }
      result.azure = {
        gross: Math.round(usage * 100) / 100,
        currency: currency,
        credit_allowance_usd: 200,
        credit_label: '$200/30d'
      };
    } catch (e) {
      result.azure = { error: 'Failed to query Azure costs' };
    }

    // GCP — not installed locally
    result.gcp = {
      gross: 0,
      currency: 'USD',
      credit_allowance: 300,
      credit_label: '$300/90d',
      note: 'gcloud not installed'
    };

    cloudCostsCache = result;
    cloudCostsCacheTime = Date.now();
    cloudCostsInFlight = null;
    return result;
  })();

  return cloudCostsInFlight;
}

app.get('/api/cloud-costs', async (req, res) => {
  try {
    const costs = await getCloudCosts();
    res.json(costs);
  } catch (e) {
    res.status(500).json({ error: 'Failed to fetch cloud costs' });
  }
});

// S21: Disk space with PowerShell fallback
app.get('/api/disk', (req, res) => {
  try {
    const { statfsSync } = fs;
    if (statfsSync) {
      const stats = statfsSync('c:/');
      const free = stats.bfree * stats.bsize;
      const total = stats.blocks * stats.bsize;
      return res.json({ free, total, freeGB: Math.round(free / 1073741824 * 10) / 10 });
    }
  } catch (e) {}
  // Fallback: PowerShell Get-PSDrive on Windows
  if (process.platform === 'win32') {
    const { execFile } = require('child_process');
    return execFile('powershell', ['-NoProfile', '-Command',
      "(Get-PSDrive C).Free, (Get-PSDrive C).Used" ],
      { timeout: 5000, windowsHide: true }, (err, stdout) => {
        if (err) return res.json({ free: null, total: null, freeGB: null });
        const [freeStr, usedStr] = stdout.trim().split(/\r?\n/);
        const free = parseInt(freeStr) || 0;
        const used = parseInt(usedStr) || 0;
        const total = free + used;
        res.json({ free, total, freeGB: Math.round(free / 1073741824 * 10) / 10 });
      });
  }
  res.json({ free: null, total: null, freeGB: null });
});

// Action output log retrieval (S3)
app.get('/api/action/:name/log', (req, res) => {
  const name = req.params.name;
  if (!ACTION_REGISTRY[name]) return res.status(404).json({ error: 'Unknown action' });
  try {
    const files = fs.readdirSync(logsDir)
      .filter(f => f.startsWith(name + '-') && f.endsWith('.log'))
      .sort()
      .reverse();
    if (files.length === 0) return res.json({ log: null, message: 'No log history' });
    const latest = fs.readFileSync(path.join(logsDir, files[0]), 'utf8');
    res.json({ log: latest, file: files[0], available: files.length });
  } catch (e) {
    res.json({ log: null, message: 'Could not read log' });
  }
});

// --- Graceful shutdown (S8) ---

function shutdown() {
  console.log('\nShutting down...');
  clearInterval(heartbeatInterval);
  // Close SSE connections
  for (const res of sseClients) {
    try { res.end(); } catch (e) {}
  }
  sseClients.clear();
  // Kill running action child processes
  for (const [name, info] of activeOps) {
    try { info.child.kill(); } catch (e) {}
  }
  activeOps.clear();
  // Stop file watchers
  stopWatchers();
  // Close HTTP server
  if (server) server.close();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// --- Start ---

let server;
server = app.listen(PORT, BIND_HOST, () => {
  console.log(`PrismataAI Command Center running at http://localhost:${PORT}`);
  if (BIND_LAN) {
    const nets = require('os').networkInterfaces();
    for (const iface of Object.values(nets)) {
      for (const info of iface) {
        if (info.family === 'IPv4' && !info.internal) {
          const tokenParam = DASHBOARD_TOKEN ? `?token=${DASHBOARD_TOKEN}` : '';
          console.log(`  LAN: http://${info.address}:${PORT}${tokenParam}`);
        }
      }
    }
    if (DASHBOARD_TOKEN) {
      console.log(`  Auth token: ${DASHBOARD_TOKEN}`);
    }
  } else {
    console.log('  Bound to localhost only. Use --lan or BIND_LAN=1 for network access.');
  }
});
