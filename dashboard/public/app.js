// ============================================
// PrismataAI Command Center — Client
// ============================================

(function() {
  'use strict';

  // --- Auth token (for LAN mode) ---
  const urlParams = new URLSearchParams(window.location.search);
  const urlToken = urlParams.get('token');
  if (urlToken) {
    sessionStorage.setItem('dashboard-token', urlToken);
    window.history.replaceState({}, '', window.location.pathname);
  }
  const authToken = sessionStorage.getItem('dashboard-token');

  function authFetch(url, opts = {}) {
    if (authToken) {
      opts.headers = Object.assign({}, opts.headers || {}, { 'X-Dashboard-Token': authToken });
    }
    return fetch(url, opts);
  }

  // --- State ---
  let currentStatus = null;
  let experiments = [];
  let selectedExp = null;
  let selectedExps = []; // multi-select for chart overlay (Ctrl+click)
  let lossChart = null;
  let brierChart = null;
  let logFilter = 'all';
  let activeActions = {};
  let sortCol = 'best_brier';
  let sortAsc = true;
  let gamesPerShard = 0; // estimated ratio for converting shard rate → game rate
  let currentGames = 0;
  let targetGames = 500000;
  const USD_TO_GBP = 0.79; // approximate conversion rate

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

  // S19: Convert "20260217_143022" timestamp to readable date
  function fmtTimestamp(ts) {
    if (!ts || ts.length < 8) return '';
    const y = ts.slice(0, 4), m = ts.slice(4, 6), d = ts.slice(6, 8);
    const parts = [y, m, d].join('-');
    if (ts.length >= 15) {
      const hh = ts.slice(9, 11), mm = ts.slice(11, 13), ss = ts.slice(13, 15);
      return parts + ' ' + [hh, mm, ss].join(':');
    }
    return parts;
  }

  function setDot(el, ok) {
    el.className = 'status-dot ' + (ok === true ? 'dot-ok' : ok === false ? 'dot-error' : 'dot-stale');
  }

  function fmtEta(hours) {
    if (hours <= 0 || !isFinite(hours)) return '--';
    if (hours < 1) return '<1h';
    if (hours < 24) return '~' + Math.round(hours) + 'h';
    const days = Math.floor(hours / 24);
    const remainHrs = Math.round(hours % 24);
    if (remainHrs === 0) return '~' + days + 'd';
    return '~' + days + 'd ' + remainHrs + 'h';
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
    const ev = data.eval || {};
    const gcp = data.gcp || {};
    const az = data.azure || {};
    const q = data.quotas || {};
    const api = data.api_health || {};
    const shard = data.shard_activity || {};

    // Per-provider vCPU calculation (8 vCPU per instance)
    // ec2_alive tracks ALL running EC2 instances (selfplay + eval combined)
    const awsEval = ev.ec2_alive || 0;
    const awsInstances = sp.ec2_alive || ((sp.ec2_on_demand || 0) + (sp.ec2_spot || 0) + awsEval);
    const awsSelfplay = Math.max(0, awsInstances - awsEval);
    const awsVcpu = awsInstances * 8;
    const awsQuota = (q.aws_on_demand_vcpus || 0) + (q.aws_spot_vcpus || 0);

    const gcpInstances = gcp.alive || 0;
    const gcpVcpu = gcpInstances * 8;
    const gcpN2 = q.gcp_n2_vcpus || 0;
    const gcpGlobal = q.gcp_global_cpus || 0;
    const gcpQuota = (gcpN2 > 0 && gcpGlobal > 0) ? Math.min(gcpN2, gcpGlobal) : (gcpN2 || gcpGlobal);

    const azInstances = az.alive || 0;
    const azVcpu = azInstances * 8;
    const azQuota = q.azure_vcpus || 0;

    const localProcs = sp.local_processes || 0;
    const localVcpu = localProcs * 4;

    const totalUsed = awsVcpu + gcpVcpu + azVcpu + localVcpu;
    const localQuota = 12; // max threads we'll use on this PC
    const totalQuota = awsQuota + gcpQuota + azQuota + localQuota;
    const totalInstances = awsInstances + gcpInstances + azInstances + localProcs;

    // Primary utilization bar
    $('fleet-vcpu-used').textContent = totalUsed;
    $('fleet-vcpu-total').textContent = totalQuota;
    const utilPct = totalQuota > 0 ? Math.min(100, (totalUsed / totalQuota) * 100) : 0;
    $('fleet-util-fill').style.width = utilPct + '%';
    $('fleet-total').textContent = totalInstances + ' active';

    // --- Job type rows ---
    // SELFPLAY
    const selfplayParts = [];
    if (sp.ec2_spot > 0) selfplayParts.push(sp.ec2_spot + ' AWS spot');
    const awsOdSelfplay = Math.max(0, awsSelfplay - (sp.ec2_spot || 0));
    if (awsOdSelfplay > 0) selfplayParts.push(awsOdSelfplay + ' AWS OD');
    if (gcpInstances > 0) selfplayParts.push(gcpInstances + ' GCP');
    if (azInstances > 0) selfplayParts.push(azInstances + ' Azure');
    if (localProcs > 0) selfplayParts.push(localProcs + ' Local');
    const selfplayVcpu = (awsSelfplay * 8) + gcpVcpu + azVcpu + localVcpu;

    const selfplayRow = $('job-selfplay');
    if (selfplayParts.length > 0) {
      $('selfplay-detail').textContent = selfplayParts.join(' \u00b7 ');
      $('selfplay-vcpu').textContent = selfplayVcpu + ' vCPU';
      selfplayRow.classList.add('job-active');
      selfplayRow.classList.remove('job-idle');
    } else {
      $('selfplay-detail').textContent = 'idle';
      $('selfplay-vcpu').textContent = '';
      selfplayRow.classList.remove('job-active');
      selfplayRow.classList.add('job-idle');
    }

    // EVAL
    const evalVcpu = awsEval * 8;
    const evalRow = $('job-eval');
    if (awsEval > 0) {
      $('eval-detail').textContent = awsEval + ' AWS on-demand';
      $('eval-vcpu').textContent = evalVcpu + ' vCPU';
      evalRow.classList.add('job-active');
      evalRow.classList.remove('job-idle');
      evalRow.style.display = '';
    } else {
      $('eval-detail').textContent = 'idle';
      $('eval-vcpu').textContent = '';
      evalRow.classList.remove('job-active');
      evalRow.classList.add('job-idle');
    }

    // --- Provider rows (simplified — detail + quota) ---
    setDot($('aws-dot'), api.aws_api_success);
    setDot($('gcp-dot'), api.gcp_api_success);
    setDot($('azure-dot'), api.azure_api_success);

    const awsDetail = $('aws-detail');
    if (awsInstances > 0) {
      awsDetail.textContent = awsInstances + ' running';
      awsDetail.classList.remove('idle');
    } else {
      awsDetail.textContent = 'idle';
      awsDetail.classList.add('idle');
    }
    $('aws-quota').innerHTML = '<span class="fleet-row-quota-used">' + awsVcpu + '</span> / ' + awsQuota + ' vCPU';

    const gcpDetail = $('gcp-detail');
    if (gcpInstances > 0) {
      gcpDetail.textContent = gcpInstances + ' running';
      gcpDetail.classList.remove('idle');
    } else {
      gcpDetail.textContent = 'idle';
      gcpDetail.classList.add('idle');
    }
    $('gcp-quota').innerHTML = '<span class="fleet-row-quota-used">' + gcpVcpu + '</span> / ' + gcpQuota + ' vCPU';

    const azDetail = $('azure-detail');
    if (azInstances > 0) {
      azDetail.textContent = az.running + ' running';
      if (az.stopped > 0) azDetail.textContent += ', ' + az.stopped + ' stopped';
      azDetail.classList.remove('idle');
    } else {
      azDetail.textContent = 'idle';
      azDetail.classList.add('idle');
    }
    $('azure-quota').innerHTML = '<span class="fleet-row-quota-used">' + azVcpu + '</span> / ' + azQuota + ' vCPU';

    const localDetail = $('local-detail');
    if (localProcs > 0) {
      localDetail.textContent = localProcs + ' process' + (localProcs > 1 ? 'es' : '');
      localDetail.classList.remove('idle');
    } else {
      localDetail.textContent = 'idle';
      localDetail.classList.add('idle');
    }
    $('local-quota').innerHTML = localVcpu > 0 ? '<span class="fleet-row-quota-used">' + localVcpu + '</span> vCPU' : '';

    // Game rate (estimated from shards × avg games/shard)
    const shardsHr = shard.shards_last_hour;
    let gamesHr = 0;
    if (shardsHr != null && gamesPerShard > 0) {
      gamesHr = Math.round(shardsHr * gamesPerShard);
      if (gamesHr >= 120) {
        $('data-rate').textContent = Math.round(gamesHr / 60) + '/min';
        $('data-rate-label').textContent = 'GAMES/MIN';
      } else {
        $('data-rate').textContent = fmt(gamesHr) + '/hr';
        $('data-rate-label').textContent = 'GAMES/HR';
      }
    } else if (shardsHr != null) {
      $('data-rate').textContent = shardsHr + ' shards/hr';
      $('data-rate-label').textContent = 'RATE';
    } else {
      $('data-rate').textContent = '--';
    }

    // ETA to 500K target
    const etaEl = $('data-eta');
    if (currentGames >= targetGames) {
      etaEl.textContent = 'DONE';
      etaEl.style.color = 'var(--green)';
    } else if (gamesHr > 0) {
      const remaining = targetGames - currentGames;
      const etaHrs = remaining / gamesHr;
      etaEl.textContent = fmtEta(etaHrs);
      etaEl.style.color = etaHrs < 24 ? 'var(--green)' : '';
    } else {
      etaEl.textContent = '--';
      etaEl.style.color = '';
    }

    // Last S3 sync (reliable, unlike last_new_shard)
    const syncData = data.s3_sync || {};
    $('data-last-sync').textContent = timeAgo(syncData.last_sync);

    // Watcher health
    const checkAge = data.last_check ? (Date.now() - new Date(data.last_check).getTime()) / 60000 : 999;
    $('watcher-ago').textContent = timeAgo(data.last_check);
    setDot($('watcher-dot'), checkAge < 10 ? true : checkAge < 30 ? null : false);

    // Fleet cost estimation — prefer watcher's computed costs (knows actual VM sizes)
    const cost = data.cost_estimate || {};
    const totalCostUsd = cost.total_per_hour != null ? cost.total_per_hour : 0;
    const totalCostGbp = totalCostUsd * USD_TO_GBP;
    $('fleet-cost').textContent = '\u00a3' + totalCostGbp.toFixed(2) + '/hr';
    $('fleet-cost').style.color = totalCostGbp > 4 ? 'var(--red)' : totalCostGbp > 0 ? 'var(--amber)' : '';
  }

  // --- Data stats ---
  function updateDataStats(data) {
    currentGames = data.games || 0;
    targetGames = data.target || 500000;
    $('data-games').textContent = fmt(data.games);
    $('data-records-inline').textContent = fmtCompact(data.records);
    $('data-shards-inline').textContent = fmt(data.shards);
    const pct = Math.min(100, (data.games / data.target) * 100);
    $('data-progress-fill').style.width = pct + '%';
    $('data-pct').textContent = pct.toFixed(1) + '%';
    // Update ratio for shard→game rate conversion
    if (data.shards > 0) gamesPerShard = data.games / data.shards;
  }

  // --- Cloud costs ---
  function updateCloudCosts(data) {
    if (!data) return;
    const aws = data.aws || {};
    const azure = data.azure || {};
    const gcp = data.gcp || {};

    // AWS (API returns USD — convert to GBP)
    let awsNetGbp = 0;
    if (aws.gross != null) {
      const grossGbp = aws.gross * USD_TO_GBP;
      const creditsGbp = (aws.credits || 0) * USD_TO_GBP;
      const netGbp = aws.net != null ? aws.net * USD_TO_GBP : grossGbp;
      awsNetGbp = netGbp;
      $('cost-aws-gross').textContent = '\u00a3' + Math.round(grossGbp) + ' gross';
      $('cost-aws-credit').textContent = aws.credits ? '(' + aws.credit_label + ' credit)' : '';
      $('cost-aws-net').textContent = '\u00a3' + Math.round(netGbp);
      $('cost-aws-net').style.color = netGbp > 0 ? 'var(--amber)' : 'var(--green)';
    } else if (aws.error) {
      $('cost-aws-gross').textContent = 'error';
    }

    // Azure (API returns GBP — already in £)
    let azNetGbp = 0;
    if (azure.gross != null) {
      const azGross = azure.gross;
      // Credit: $200 ≈ £158 GBP
      const creditGbp = Math.round((azure.credit_allowance_usd || 200) * USD_TO_GBP);
      azNetGbp = Math.max(0, azGross - creditGbp);
      $('cost-azure-gross').textContent = '\u00a3' + Math.round(azGross) + ' gross';
      $('cost-azure-credit').textContent = azure.credit_label ? '(' + azure.credit_label + ' credit)' : '';
      $('cost-azure-net').textContent = '\u00a3' + Math.round(azNetGbp);
      $('cost-azure-net').style.color = azNetGbp > 0 ? 'var(--amber)' : 'var(--green)';
    } else if (azure.error) {
      $('cost-azure-gross').textContent = 'error';
    }

    // GCP (minimal usage — convert any USD to GBP)
    if (gcp.note) {
      $('cost-gcp-gross').textContent = '\u00a30';
      $('cost-gcp-credit').textContent = '(' + gcp.credit_label + ' credit)';
      $('cost-gcp-net').textContent = '\u00a30';
      $('cost-gcp-net').style.color = 'var(--green)';
    }

    // Total net in GBP
    const totalNetGbp = awsNetGbp + azNetGbp;
    const netEl = $('cost-net');
    if (totalNetGbp <= 0) {
      netEl.textContent = '\u00a30 due';
      netEl.style.color = 'var(--green)';
    } else {
      netEl.textContent = '~\u00a3' + Math.round(totalNetGbp) + ' due';
      netEl.style.color = 'var(--amber)';
    }
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
      const isSelected = selectedExps.some(s => s.timestamp === exp.timestamp) ||
        (selectedExp && selectedExp.timestamp === exp.timestamp);
      if (isSelected) tr.classList.add('exp-selected');

      // S19: parse timestamp into human-readable date for tooltip
      const dateTitle = fmtTimestamp(exp.timestamp);
      tr.innerHTML = `
        <td title="${dateTitle}">${exp.timestamp}</td>
        <td>${exp.hidden_dim}</td>
        <td>${exp.lr}</td>
        <td>${exp.loss_fn}</td>
        <td>${exp.tanh ? 'Y' : 'N'}</td>
        <td style="font-weight:600;color:${isBest ? 'var(--amber)' : 'var(--text-bright)'}">${exp.best_brier != null ? exp.best_brier.toFixed(4) : '--'}</td>
        <td>${exp.best_val_acc != null ? (exp.best_val_acc * 100).toFixed(1) + '%' : '--'}</td>
        <td>${exp.best_step || '--'}</td>
      `;
      tr.addEventListener('click', (e) => {
        if (e.ctrlKey || e.metaKey) {
          // Multi-select: toggle this experiment in overlay (max 3)
          const idx = selectedExps.findIndex(s => s.timestamp === exp.timestamp);
          if (idx >= 0) {
            selectedExps.splice(idx, 1);
          } else if (selectedExps.length < 3) {
            selectedExps.push(exp);
          } else {
            toast('Max 3 experiments for overlay', 'info');
            return;
          }
          if (selectedExps.length > 0) {
            loadMultiExperimentChart(selectedExps);
          } else {
            $('chart-area').classList.remove('visible');
            renderExperiments();
          }
        } else {
          selectedExps = [];
          loadExperimentChart(exp);
        }
      });
      tbody.appendChild(tr);
    }

    // Header sort indicators + S18: aria-sort
    document.querySelectorAll('.exp-table th').forEach(th => {
      th.classList.remove('sorted-asc', 'sorted-desc');
      if (th.dataset.sort === sortCol) {
        th.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
        th.setAttribute('aria-sort', sortAsc ? 'ascending' : 'descending');
      } else {
        th.setAttribute('aria-sort', 'none');
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
    // S12: hide hint when chart is open
    const hint = $('exp-hint');
    if (hint) hint.style.display = 'none';
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

  // Multi-experiment overlay chart
  async function loadMultiExperimentChart(expList) {
    selectedExp = null;
    renderExperiments();

    const chartArea = $('chart-area');
    chartArea.classList.add('visible');
    const hint = $('exp-hint');
    if (hint) hint.style.display = 'none';
    $('chart-title').textContent = 'Comparing ' + expList.map(e => e.hidden_dim + 'h').join(' vs ');

    if (lossChart) lossChart.destroy();
    if (brierChart) brierChart.destroy();

    const lossDatasets = [];
    const brierDatasets = [];
    const accDatasets = [];
    let maxLabels = [];

    for (let i = 0; i < expList.length; i++) {
      try {
        const resp = await fetch('/api/experiment/' + expList[i].timestamp);
        const data = await resp.json();
        const series = data.step_evals && data.step_evals.length > 0 ? data.step_evals : data.epochs || [];
        const useSteps = data.step_evals && data.step_evals.length > 0;
        const labels = series.map(s => useSteps ? s.step : s.epoch);
        if (labels.length > maxLabels.length) maxLabels = labels;

        const color = chartColors[i % chartColors.length];
        const tag = expList[i].hidden_dim + 'h LR=' + expList[i].lr;

        lossDatasets.push({
          label: tag + ' Val Loss',
          data: series.map(e => e.val_value_loss),
          borderColor: color.border,
          backgroundColor: color.bg,
          tension: 0.3, pointRadius: 2, borderWidth: 1.5
        });

        brierDatasets.push({
          label: tag + ' Brier',
          data: series.map(e => e.brier_score),
          borderColor: color.border,
          backgroundColor: color.bg,
          tension: 0.3, pointRadius: 2, borderWidth: 1.5
        });

        accDatasets.push({
          label: tag + ' Acc',
          data: series.map(e => e.val_value_acc),
          borderColor: color.border,
          backgroundColor: 'transparent',
          tension: 0.3, pointRadius: 1, borderWidth: 1, borderDash: [4, 2],
          yAxisID: 'y1'
        });
      } catch (e) {
        toast('Failed to load ' + expList[i].timestamp, 'error');
      }
    }

    lossChart = new Chart($('chart-loss'), {
      type: 'line',
      data: { labels: maxLabels, datasets: lossDatasets },
      options: {
        ...chartDefaults,
        plugins: {
          ...chartDefaults.plugins,
          title: { display: true, text: 'Val Loss Comparison', color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 11 } }
        }
      }
    });

    brierChart = new Chart($('chart-brier'), {
      type: 'line',
      data: { labels: maxLabels, datasets: [...brierDatasets, ...accDatasets] },
      options: {
        ...chartDefaults,
        plugins: {
          ...chartDefaults.plugins,
          title: { display: true, text: 'Brier & Accuracy Comparison', color: '#6878a0', font: { family: "'IBM Plex Mono'", size: 11 } }
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
  }

  $('chart-close').addEventListener('click', () => {
    $('chart-area').classList.remove('visible');
    selectedExp = null;
    selectedExps = [];
    renderExperiments();
    // S12: show hint again
    const hint = $('exp-hint');
    if (hint) hint.style.display = '';
  });

  // --- Actions ---
  let pendingAction = null;

  document.querySelectorAll('.action-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.action;
      if (btn.disabled || activeActions[name]) return;

      // S10: client-side debounce — disable during fetch round-trip
      btn.disabled = true;
      try {
        const resp = await fetch('/api/action/' + name);
        const action = await resp.json();

        if (resp.status === 409) {
          toast(action.error + ' — started ' + timeAgo(action.startTime), 'error');
          btn.disabled = false;
          return;
        }

        if (action.tier === 'safe') {
          // Execute immediately
          const execResp = await authFetch('/api/action/' + name + '/confirm', { method: 'POST' });
          const result = await execResp.json();
          if (result.completed) {
            toast(action.label + ' complete', 'success');
            refreshAll();
          } else if (result.started) {
            setActionRunning(name, true);
            toast(action.label + ' started', 'info');
          }
          if (!activeActions[name]) btn.disabled = false;
        } else {
          // Show confirmation modal
          pendingAction = name;
          $('modal-title').textContent = 'Confirm: ' + action.label;
          $('modal-desc').textContent = action.description;
          $('modal-overlay').classList.add('visible');
          btn.disabled = false;
        }
      } catch (e) {
        toast('Action failed: ' + e.message, 'error');
        btn.disabled = false;
      }
    });
  });

  $('modal-confirm').addEventListener('click', async () => {
    $('modal-overlay').classList.remove('visible');
    if (!pendingAction) return;
    const name = pendingAction;
    pendingAction = null;

    try {
      const resp = await authFetch('/api/action/' + name + '/confirm', { method: 'POST' });
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
      // S13: add cancel overlay (visible on hover)
      if (!btn.querySelector('.cancel-overlay')) {
        const cancel = document.createElement('span');
        cancel.className = 'cancel-overlay';
        cancel.textContent = 'CANCEL';
        cancel.addEventListener('click', async (e) => {
          e.stopPropagation();
          cancel.textContent = '...';
          try {
            const resp = await authFetch('/api/action/' + name + '/cancel', { method: 'POST' });
            const result = await resp.json();
            if (result.cancelled) {
              toast('Cancelling ' + name + '...', 'info');
            } else if (result.error) {
              toast(result.error, 'error');
              cancel.textContent = 'CANCEL';
            }
          } catch (err) {
            toast('Cancel failed: ' + err.message, 'error');
            cancel.textContent = 'CANCEL';
          }
        });
        btn.appendChild(cancel);
      }
      btn.disabled = false; // keep enabled so cancel overlay is clickable
    } else {
      delete activeActions[name];
      btn.classList.remove('running');
      btn.disabled = false;
      // Remove cancel overlay
      const cancel = btn.querySelector('.cancel-overlay');
      if (cancel) cancel.remove();
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
      const [statusResp, dataResp, logResp, expResp, actResp, diskResp, costResp] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/data-stats'),
        fetch('/api/log?lines=200'),
        fetch('/api/experiments'),
        fetch('/api/actions/status'),
        fetch('/api/disk'),
        fetch('/api/cloud-costs')
      ]);

      // Data stats first — sets gamesPerShard needed by updateStatus for game rate
      if (dataResp.ok) updateDataStats(await dataResp.json());
      if (statusResp.ok) updateStatus(await statusResp.json());
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
      if (costResp.ok) updateCloudCosts(await costResp.json());
    } catch (e) {
      toast('Failed to load data', 'error');
    }
  }

  // --- Boot ---
  refreshAll();
  connectSSE();

  // Refresh status + data stats + experiments every 30s
  setInterval(async () => {
    try {
      const [statusResp, dataResp, expResp, costResp] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/data-stats'),
        fetch('/api/experiments'),
        fetch('/api/cloud-costs')
      ]);
      if (dataResp.ok) updateDataStats(await dataResp.json());
      if (statusResp.ok) updateStatus(await statusResp.json());
      if (expResp.ok) {
        experiments = await expResp.json();
        renderExperiments();
      }
      if (costResp.ok) updateCloudCosts(await costResp.json());
    } catch (e) {}
  }, 30000);

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
