const express = require('express');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const app = express();
const PORT = 3000;
const BASE = 'c:/libraries/PrismataAI';

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
    const content = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
    const lines = content.split(/\r?\n/).filter(l => l.trim());
    return lines.slice(-count);
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

// Watch watcher_status.json for changes
const statusPath = path.join(BASE, 'aws/watcher_status.json');
let lastStatusMtime = 0;
fs.watchFile(statusPath, { interval: 5000 }, (curr, prev) => {
  if (curr.mtimeMs !== prev.mtimeMs) {
    setTimeout(() => {
      const status = readJsonWithBom(statusPath);
      if (status) broadcast('status', status);
    }, 200); // debounce for half-written file
  }
});

// Watch log file for new lines
const logPath = path.join(BASE, 'aws/watcher_log.txt');
let lastLogSize = 0;
try { lastLogSize = fs.statSync(logPath).size; } catch (e) {}
fs.watchFile(logPath, { interval: 5000 }, (curr, prev) => {
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
});

// --- Data stats cache ---

let dataStatsCache = null;
let dataStatsCacheTime = 0;

function getDataStats() {
  const now = Date.now();
  if (dataStatsCache && now - dataStatsCacheTime < 60000) return dataStatsCache;

  const selfplayDir = path.join(BASE, 'bin/training/data/selfplay');
  let totalRecords = 0;
  let shardCount = 0;

  function walkDir(dir) {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walkDir(full);
        } else if (entry.name.endsWith('.bin')) {
          try {
            const size = fs.statSync(full).size;
            if (size > 16) {
              shardCount++;
              totalRecords += Math.floor((size - 16) / 7152);
            }
          } catch (e) {}
        }
      }
    } catch (e) {}
  }
  walkDir(selfplayDir);

  dataStatsCache = {
    records: totalRecords,
    games: Math.floor(totalRecords / 37),
    shards: shardCount,
    target: 500000
  };
  dataStatsCacheTime = now;
  return dataStatsCache;
}

// --- Action system ---

const activeOps = new Map();

const ACTION_REGISTRY = {
  'refresh': {
    tier: 'safe',
    label: 'Refresh Status',
    description: 'Re-read all data files',
    command: null
  },
  'sync-s3': {
    tier: 'safe',
    label: 'Sync S3',
    description: 'Download latest self-play results from S3',
    command: ['bash', ['aws/download_results.sh']],
    cwd: BASE
  },
  'launch-aws': {
    tier: 'cautious',
    label: 'Launch AWS Fleet',
    description: 'Launch 8x c5.2xlarge on-demand instances for self-play generation',
    command: ['bash', ['aws/launch_selfplay.sh', 'c5.2xlarge', '2000', '1', '2']],
    cwd: BASE
  },
  'train-e2b': {
    tier: 'cautious',
    label: 'Train E2b',
    description: 'Train 256h model with winning E2b recipe (LR=1e-5, tanh+MSE)',
    command: ['python', ['training/train.py', '--selfplay-dir', 'bin/training/data/selfplay/', '--value-only', '--hidden-dim', '256', '--lr', '1e-5', '--epochs', '100', '--batch-size', '512', '--patience', '5', '--max-records', '1000000', '--num-workers', '0', '--tanh-in-training', '--loss-fn', 'mse']],
    cwd: BASE
  }
};

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
  req.on('close', () => sseClients.delete(res));

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

// All experiments summary
app.get('/api/experiments', (req, res) => {
  const runsDir = path.join(BASE, 'training/runs');
  try {
    const files = fs.readdirSync(runsDir).filter(f => f.endsWith('.json')).sort();
    const experiments = files.map(f => {
      try {
        const data = JSON.parse(fs.readFileSync(path.join(runsDir, f), 'utf8'));
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
    }).filter(Boolean);

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
app.get('/api/data-stats', (req, res) => {
  res.json(getDataStats());
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
app.post('/api/action/:name/confirm', (req, res) => {
  const name = req.params.name;
  const action = ACTION_REGISTRY[name];
  if (!action) return res.status(404).json({ error: 'Unknown action' });
  if (activeOps.has(name)) {
    return res.status(409).json({ error: 'already_running' });
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
  activeOps.set(name, { child, startTime });

  broadcast('op-started', { op: name, label: action.label, startTime });

  child.stdout.on('data', (chunk) => {
    broadcast('op-progress', { op: name, stream: 'stdout', text: chunk.toString() });
  });
  child.stderr.on('data', (chunk) => {
    broadcast('op-progress', { op: name, stream: 'stderr', text: chunk.toString() });
  });
  child.on('close', (code) => {
    activeOps.delete(name);
    broadcast('op-complete', { op: name, label: action.label, code, startTime });
  });
  child.on('error', (err) => {
    activeOps.delete(name);
    broadcast('op-complete', { op: name, label: action.label, code: -1, error: err.message, startTime });
  });

  res.json({ started: true, pid: child.pid });
});

// Disk space (Windows)
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
  res.json({ free: null, total: null, freeGB: null });
});

// --- Start ---

app.listen(PORT, '0.0.0.0', () => {
  console.log(`PrismataAI Command Center running at http://localhost:${PORT}`);
  const nets = require('os').networkInterfaces();
  for (const iface of Object.values(nets)) {
    for (const info of iface) {
      if (info.family === 'IPv4' && !info.internal) {
        console.log(`  LAN: http://${info.address}:${PORT}`);
      }
    }
  }
});
