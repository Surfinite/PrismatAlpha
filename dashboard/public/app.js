// ============================================
// PrismataAI Command Center — Client
// ============================================

(function() {
  'use strict';

  // --- State ---
  let currentStatus = null;
  let experiments = [];
  let selectedExp = null;
  let lossChart = null;
  let brierChart = null;
  let logFilter = 'all';
  let activeActions = {};
  let sortCol = 'best_brier';
  let sortAsc = true;

  // --- DOM refs ---
  const $ = id => document.getElementById(id);

  // --- Helpers ---
  function fmt(n) {
    if (n == null || isNaN(n)) return '--';
    return n.toLocaleString();
  }

  function fmtCompact(n) {
    if (n == null) return '--';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toString();
  }

  function timeAgo(isoStr) {
    if (!isoStr) return '--';
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + 'm ago';
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + 'h ' + (mins % 60) + 'm ago';
    return Math.floor(hrs / 24) + 'd ago';
  }

  function setDot(el, ok) {
    el.className = 'status-dot ' + (ok === true ? 'dot-ok' : ok === false ? 'dot-error' : 'dot-stale');
  }

  function toast(msg, type) {
    const container = $('toast-container');
    const el = document.createElement('div');
    el.className = 'toast toast-' + (type || 'info');
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 4000);
  }

  // --- Fleet status ---
  function updateStatus(data) {
    currentStatus = data;
    const sp = data.selfplay || {};
    const gcp = data.gcp || {};
    const az = data.azure || {};
    const q = data.quotas || {};
    const api = data.api_health || {};
    const shard = data.shard_activity || {};

    // Fleet counts
    $('aws-count').textContent = sp.ec2_alive || 0;
    $('aws-od').textContent = sp.ec2_on_demand || 0;
    $('aws-spot').textContent = sp.ec2_spot || 0;
    $('gcp-count').textContent = gcp.alive || 0;
    $('gcp-std').textContent = gcp.standard || 0;
    $('gcp-spot').textContent = gcp.spot || 0;
    $('azure-count').textContent = az.alive || 0;
    $('azure-run').textContent = az.running || 0;
    $('azure-stop').textContent = az.stopped || 0;
    $('local-count').textContent = sp.local_processes || 0;

    const total = (sp.ec2_alive || 0) + (gcp.alive || 0) + (az.alive || 0) + (sp.local_processes || 0);
    $('fleet-total').textContent = total + ' active';

    // Active highlighting
    $('fleet-aws').classList.toggle('fleet-active', (sp.ec2_alive || 0) > 0);
    $('fleet-gcp').classList.toggle('fleet-active', (gcp.alive || 0) > 0);
    $('fleet-azure').classList.toggle('fleet-active', (az.alive || 0) > 0);
    $('fleet-local').classList.toggle('fleet-active', (sp.local_processes || 0) > 0);

    // API health dots
    setDot($('aws-dot'), api.aws_api_success);
    setDot($('gcp-dot'), api.gcp_api_success);
    setDot($('azure-dot'), api.azure_api_success);

    // Quota bars — AWS uses vCPU count * 8 for instances (c5.2xlarge = 8 vCPU)
    const awsUsed = ((sp.ec2_on_demand || 0) * 8) + ((sp.ec2_spot || 0) * 8);
    const awsTotal = (q.aws_on_demand_vcpus || 1) + (q.aws_spot_vcpus || 1);
    $('aws-quota-fill').style.width = Math.min(100, (awsUsed / awsTotal) * 100) + '%';
    $('aws-quota-text').textContent = awsUsed + ' / ' + awsTotal + ' vCPU';

    const gcpUsed = (gcp.alive || 0) * 8;
    const gcpTotal = q.gcp_global_cpus || q.gcp_n2_vcpus || 1;
    $('gcp-quota-fill').style.width = Math.min(100, (gcpUsed / gcpTotal) * 100) + '%';
    $('gcp-quota-text').textContent = gcpUsed + ' / ' + gcpTotal + ' vCPU';

    const azUsed = (az.alive || 0) * 8;
    const azTotal = q.azure_vcpus || 1;
    $('azure-quota-fill').style.width = Math.min(100, (azUsed / azTotal) * 100) + '%';
    $('azure-quota-text').textContent = azUsed + ' / ' + azTotal + ' vCPU';

    // Shard activity
    $('data-rate').textContent = shard.shards_last_hour != null ? shard.shards_last_hour : '--';
    const lastShard = shard.last_new_shard;
    $('data-last-shard').textContent = timeAgo(lastShard);
    // Staleness warning
    if (lastShard) {
      const staleMin = (Date.now() - new Date(lastShard).getTime()) / 60000;
      $('data-last-shard').style.color = staleMin > 60 ? 'var(--red)' : '';
    }

    // Watcher health
    const checkAge = data.last_check ? (Date.now() - new Date(data.last_check).getTime()) / 60000 : 999;
    $('watcher-ago').textContent = timeAgo(data.last_check);
    setDot($('watcher-dot'), checkAge < 10 ? true : checkAge < 30 ? null : false);

    // Fleet cost estimation
    const awsOdCost = (sp.ec2_on_demand || 0) * 0.34;
    const awsSpotCost = (sp.ec2_spot || 0) * 0.10;
    const gcpCost = (gcp.alive || 0) * 0.39;
    const azCost = (az.alive || 0) * 0.32;
    const totalCost = awsOdCost + awsSpotCost + gcpCost + azCost;
    $('fleet-cost').textContent = '$' + totalCost.toFixed(2) + '/hr';
    $('fleet-cost').style.color = totalCost > 5 ? 'var(--red)' : totalCost > 0 ? 'var(--amber)' : '';
  }

  // --- Data stats ---
  function updateDataStats(data) {
    $('data-games').textContent = fmt(data.games);
    $('data-records').textContent = fmtCompact(data.records);
    $('data-shards').textContent = fmt(data.shards);
    const pct = Math.min(100, (data.games / data.target) * 100);
    $('data-progress-fill').style.width = pct + '%';
    $('data-pct').textContent = pct.toFixed(1) + '%';
  }

  // --- Log viewer ---
  function renderLogLine(entry) {
    const div = document.createElement('div');
    div.className = 'log-line';
    div.dataset.type = entry.type || 'check';

    const time = document.createElement('span');
    time.className = 'log-time';
    time.textContent = entry.time || '';

    const msg = document.createElement('span');
    msg.className = 'log-msg';
    msg.textContent = entry.message || '';

    div.appendChild(time);
    div.appendChild(msg);
    return div;
  }

  function renderLog(entries) {
    const body = $('log-body');
    body.innerHTML = '';
    for (const entry of entries) {
      const el = renderLogLine(entry);
      if (logFilter !== 'all' && entry.type !== logFilter) {
        el.style.display = 'none';
      }
      body.appendChild(el);
    }
  }

  function addLogLine(entry) {
    const body = $('log-body');
    const el = renderLogLine(entry);
    if (logFilter !== 'all' && entry.type !== logFilter) {
      el.style.display = 'none';
    }
    body.insertBefore(el, body.firstChild);
    // Trim to 500 lines
    while (body.children.length > 500) body.removeChild(body.lastChild);
  }

  // Log filter buttons
  document.querySelectorAll('.log-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.log-filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      logFilter = btn.dataset.filter;
      document.querySelectorAll('.log-line').forEach(line => {
        if (logFilter === 'all' || line.dataset.type === logFilter) {
          line.style.display = '';
        } else {
          line.style.display = 'none';
        }
      });
    });
  });

  // --- Experiments table ---
  function renderExperiments() {
    const tbody = $('exp-tbody');
    tbody.innerHTML = '';
    $('exp-count').textContent = experiments.length + ' runs';

    // Sort
    const sorted = [...experiments].sort((a, b) => {
      let va = a[sortCol], vb = b[sortCol];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      return sortAsc ? va - vb : vb - va;
    });

    // Find best brier
    let bestBrier = Infinity;
    for (const exp of experiments) {
      if (exp.best_brier != null && exp.best_brier < bestBrier) bestBrier = exp.best_brier;
    }

    for (const exp of sorted) {
      const tr = document.createElement('tr');
      const isBest = exp.best_brier != null && exp.best_brier === bestBrier;
      if (isBest) tr.classList.add('exp-best');
      if (selectedExp && selectedExp.timestamp === exp.timestamp) tr.classList.add('exp-selected');

      tr.innerHTML = `
        <td>${exp.timestamp}</td>
        <td>${exp.hidden_dim}</td>
        <td>${exp.lr}</td>
        <td>${exp.loss_fn}</td>
        <td>${exp.tanh ? 'Y' : 'N'}</td>
        <td style="font-weight:600;color:${isBest ? 'var(--amber)' : 'var(--text-bright)'}">${exp.best_brier != null ? exp.best_brier.toFixed(4) : '--'}</td>
        <td>${exp.best_val_acc != null ? (exp.best_val_acc * 100).toFixed(1) + '%' : '--'}</td>
        <td>${exp.best_step || '--'}</td>
      `;
      tr.addEventListener('click', () => loadExperimentChart(exp));
      tbody.appendChild(tr);
    }

    // Header sort indicators
    document.querySelectorAll('.exp-table th').forEach(th => {
      th.classList.remove('sorted-asc', 'sorted-desc');
      if (th.dataset.sort === sortCol) {
        th.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
      }
    });
  }

  // Table sort
  document.querySelectorAll('.exp-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (sortCol === col) sortAsc = !sortAsc;
      else { sortCol = col; sortAsc = true; }
      renderExperiments();
    });
  });

  // --- Charts ---
  const chartColors = [
    { border: '#40d8f0', bg: 'rgba(64,216,240,0.1)' },
    { border: '#f04040', bg: 'rgba(240,64,64,0.1)' },
    { border: '#f0a830', bg: 'rgba(240,168,48,0.1)' },
    { border: '#30e060', bg: 'rgba(48,224,96,0.1)' },
  ];

  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: true,
    animation: { duration: 400 },
    plugins: {
      legend: { labels: { color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 10 } } }
    },
    scales: {
      x: {
        ticks: { color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 9 } },
        grid: { color: 'rgba(30,42,58,0.6)' }
      },
      y: {
        ticks: { color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 9 } },
        grid: { color: 'rgba(30,42,58,0.6)' },
        beginAtZero: false
      }
    }
  };

  async function loadExperimentChart(expSummary) {
    selectedExp = expSummary;
    renderExperiments(); // highlight row

    const chartArea = $('chart-area');
    chartArea.classList.add('visible');
    $('chart-title').textContent = 'Run ' + expSummary.timestamp + ' (' + expSummary.hidden_dim + 'h, LR=' + expSummary.lr + ')';

    try {
      const resp = await fetch('/api/experiment/' + expSummary.timestamp);
      const data = await resp.json();

      // Prefer step_evals if available, else epochs
      const series = data.step_evals && data.step_evals.length > 0 ? data.step_evals : data.epochs || [];
      const useSteps = data.step_evals && data.step_evals.length > 0;
      const labels = series.map(s => useSteps ? s.step : s.epoch);

      // Destroy old charts
      if (lossChart) lossChart.destroy();
      if (brierChart) brierChart.destroy();

      // Loss chart
      const lossDatasets = [];
      if (data.epochs && data.epochs.length > 0) {
        lossDatasets.push({
          label: 'Train Loss',
          data: data.epochs.map(e => e.train_value_loss),
          borderColor: chartColors[0].border,
          backgroundColor: chartColors[0].bg,
          tension: 0.3, pointRadius: 2, borderWidth: 1.5
        });
      }
      lossDatasets.push({
        label: 'Val Loss',
        data: series.map(e => e.val_value_loss),
        borderColor: chartColors[1].border,
        backgroundColor: chartColors[1].bg,
        tension: 0.3, pointRadius: 2, borderWidth: 1.5
      });

      lossChart = new Chart($('chart-loss'), {
        type: 'line',
        data: {
          labels: useSteps ? labels : data.epochs.map(e => e.epoch),
          datasets: lossDatasets
        },
        options: {
          ...chartDefaults,
          plugins: {
            ...chartDefaults.plugins,
            title: { display: true, text: 'Loss', color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 11 } }
          }
        }
      });

      // Brier chart
      brierChart = new Chart($('chart-brier'), {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'Brier Score',
            data: series.map(e => e.brier_score),
            borderColor: chartColors[2].border,
            backgroundColor: chartColors[2].bg,
            tension: 0.3, pointRadius: 2, borderWidth: 1.5
          }, {
            label: 'Val Accuracy',
            data: series.map(e => e.val_value_acc),
            borderColor: chartColors[3].border,
            backgroundColor: chartColors[3].bg,
            tension: 0.3, pointRadius: 2, borderWidth: 1.5,
            yAxisID: 'y1'
          }]
        },
        options: {
          ...chartDefaults,
          plugins: {
            ...chartDefaults.plugins,
            title: { display: true, text: 'Brier & Accuracy', color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 11 } }
          },
          scales: {
            ...chartDefaults.scales,
            y1: {
              position: 'right',
              ticks: { color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 9 } },
              grid: { display: false }
            }
          }
        }
      });
    } catch (e) {
      toast('Failed to load experiment data', 'error');
    }
  }

  $('chart-close').addEventListener('click', () => {
    $('chart-area').classList.remove('visible');
    selectedExp = null;
    renderExperiments();
  });

  // --- Actions ---
  let pendingAction = null;

  document.querySelectorAll('.action-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.action;
      if (btn.disabled || activeActions[name]) return;

      try {
        const resp = await fetch('/api/action/' + name);
        const action = await resp.json();

        if (resp.status === 409) {
          toast(action.error + ' — started ' + timeAgo(action.startTime), 'error');
          return;
        }

        if (action.tier === 'safe') {
          // Execute immediately
          const execResp = await fetch('/api/action/' + name + '/confirm', { method: 'POST' });
          const result = await execResp.json();
          if (result.completed) {
            toast(action.label + ' complete', 'success');
            refreshAll();
          } else if (result.started) {
            setActionRunning(name, true);
            toast(action.label + ' started', 'info');
          }
        } else {
          // Show confirmation modal
          pendingAction = name;
          $('modal-title').textContent = 'Confirm: ' + action.label;
          $('modal-desc').textContent = action.description;
          $('modal-overlay').classList.add('visible');
        }
      } catch (e) {
        toast('Action failed: ' + e.message, 'error');
      }
    });
  });

  $('modal-confirm').addEventListener('click', async () => {
    $('modal-overlay').classList.remove('visible');
    if (!pendingAction) return;
    const name = pendingAction;
    pendingAction = null;

    try {
      const resp = await fetch('/api/action/' + name + '/confirm', { method: 'POST' });
      const result = await resp.json();
      if (result.started) {
        setActionRunning(name, true);
        toast('Started', 'info');
      } else if (result.error) {
        toast(result.error, 'error');
      }
    } catch (e) {
      toast('Failed: ' + e.message, 'error');
    }
  });

  $('modal-cancel').addEventListener('click', () => {
    $('modal-overlay').classList.remove('visible');
    pendingAction = null;
  });

  function setActionRunning(name, running) {
    const btn = document.querySelector(`[data-action="${name}"]`);
    if (!btn) return;
    if (running) {
      activeActions[name] = true;
      btn.classList.add('running');
      btn.disabled = true;
    } else {
      delete activeActions[name];
      btn.classList.remove('running');
      btn.disabled = false;
    }
  }

  // Console output
  $('console-clear').addEventListener('click', () => {
    $('action-console-body').textContent = '';
  });

  function appendConsole(text) {
    const body = $('action-console-body');
    body.textContent += text;
    body.scrollTop = body.scrollHeight;
  }

  // --- SSE ---
  function connectSSE() {
    const es = new EventSource('/api/events');

    es.addEventListener('status', e => {
      try {
        updateStatus(JSON.parse(e.data));
      } catch (err) {}
    });

    es.addEventListener('log', e => {
      try {
        addLogLine(JSON.parse(e.data));
      } catch (err) {}
    });

    es.addEventListener('op-started', e => {
      try {
        const data = JSON.parse(e.data);
        setActionRunning(data.op, true);
        appendConsole('\n--- ' + data.label + ' started ---\n');
      } catch (err) {}
    });

    es.addEventListener('op-progress', e => {
      try {
        const data = JSON.parse(e.data);
        appendConsole(data.text);
      } catch (err) {}
    });

    es.addEventListener('op-complete', e => {
      try {
        const data = JSON.parse(e.data);
        setActionRunning(data.op, false);
        const success = data.code === 0;
        appendConsole('\n--- ' + data.label + (success ? ' COMPLETE' : ' FAILED (code ' + data.code + ')') + ' ---\n');
        toast(data.label + (success ? ' complete' : ' failed'), success ? 'success' : 'error');
        if (success) refreshAll();
      } catch (err) {}
    });

    es.onopen = () => {
      setDot($('sse-dot'), true);
    };

    es.onerror = () => {
      setDot($('sse-dot'), false);
      // EventSource auto-reconnects
    };
  }

  // --- Initial data load ---
  async function refreshAll() {
    try {
      const [statusResp, dataResp, logResp, expResp, actResp, diskResp] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/data-stats'),
        fetch('/api/log?lines=200'),
        fetch('/api/experiments'),
        fetch('/api/actions/status'),
        fetch('/api/disk')
      ]);

      if (statusResp.ok) updateStatus(await statusResp.json());
      if (dataResp.ok) updateDataStats(await dataResp.json());
      if (logResp.ok) renderLog(await logResp.json());
      if (expResp.ok) {
        experiments = await expResp.json();
        renderExperiments();
      }
      if (actResp.ok) {
        const actData = await actResp.json();
        for (const name of Object.keys(actData.active || {})) {
          setActionRunning(name, true);
        }
      }
      if (diskResp.ok) {
        const disk = await diskResp.json();
        if (disk.freeGB != null) {
          $('disk-free').textContent = disk.freeGB + ' GB';
          $('disk-free').style.color = disk.freeGB < 50 ? 'var(--red)' : '';
        }
      }
    } catch (e) {
      toast('Failed to load data', 'error');
    }
  }

  // --- Boot ---
  refreshAll();
  connectSSE();

  // Refresh data stats every 60s (cached server-side anyway)
  setInterval(async () => {
    try {
      const resp = await fetch('/api/data-stats');
      if (resp.ok) updateDataStats(await resp.json());
    } catch (e) {}
  }, 60000);

  // Refresh disk every 5 min
  setInterval(async () => {
    try {
      const resp = await fetch('/api/disk');
      if (resp.ok) {
        const disk = await resp.json();
        if (disk.freeGB != null) {
          $('disk-free').textContent = disk.freeGB + ' GB';
          $('disk-free').style.color = disk.freeGB < 50 ? 'var(--red)' : '';
        }
      }
    } catch (e) {}
  }, 300000);
})();
