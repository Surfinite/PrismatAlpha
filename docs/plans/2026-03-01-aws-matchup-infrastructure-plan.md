# AWS MCDSAI Matchup Infrastructure Plan

> **Status**: DRAFT — awaiting approval
> **Created**: 2026-03-01
> **Branch**: `feature/as3-js-transpilation`
> **Estimated cost**: ~$17 for 1000 games, ~$29 for 2000 games (Windows OD)

## Goal

Enable running 1000+ MCDSAI vs C++ AI matchup games on AWS, parallelized across
multiple instances, with results collected to S3. This complements the existing
C++ tournament infrastructure (`launch_tournament.sh`) which handles PrismatAI vs
OriginalHardestAI/LiveHardestAI matchups.

## Key Constraint: Windows Required

`matchup_main.js` spawns `Prismata_Testing.exe --suggest` (x86 Windows) as a
subprocess every turn. **Linux instances cannot run the exe.** The infrastructure
must use Windows Server AMIs with Node.js installed — a hybrid of:

- `aws/launch_tournament.sh` (Windows PowerShell userdata, VC++ install)
- `aws/launch_js_selfplay.sh` (Node.js, JS engine deploy, multi-worker pattern)

## Phase 0: Documentation Discovery (Consolidated Findings)

### Existing Infrastructure

| Script | Platform | Purpose | S3 Output |
|--------|----------|---------|-----------|
| `aws/deploy_for_eval.sh` | Bash | Upload exe + config + weights | `deploy/` |
| `aws/deploy_js_selfplay.sh` | Bash | Upload JS engine + MCDSAI + AI params | `deploy/` |
| `aws/launch_tournament.sh` | Win PS | C++ tournament (AB vs Original) | `eval-results/` |
| `aws/launch_js_selfplay.sh` | Linux | JS MCDSAI vs MCDSAI selfplay | `js_results/` |

**Both deploy scripts upload to the same `deploy/` prefix** — no conflicts.

### matchup_main.js Architecture

- **Sequential games** (no parallel within one process)
- **Per game**: ~40 turns, MCDSAI (~1s/turn via IPC) + C++ (~7s/turn via execFile)
- **~5.5 min per game** at 7s C++ think time
- **CPU per game**: ~1 core average (MCDSAI and C++ alternate, never overlap)
- **28 JS files** (~440KB), no npm deps, Node.js >=16
- **Temp files**: `/tmp/prismata_suggest_<pid>_<turn>.json` (unique per PID, auto-cleaned)
- **Output**: stderr (stats) + `--jsonl` (training data) + `--replay-dir` (replay JSON)
- **Retry logic**: 3 retries per game on failure, ~5% random card sets cause AI exceptions

### File Dependencies for Deployment

| Component | S3 Key | Size | Source Deploy Script |
|-----------|--------|------|---------------------|
| JS engine (28 .js files) | `deploy/js_engine/*.js` | 440KB | `deploy_js_selfplay.sh` |
| MCDSAI3441.js | `deploy/tmp_browser_client/MCDSAI3441.js` | 1.8MB | `deploy_js_selfplay.sh` |
| AI params (full) | `deploy/tmp_swf_extract/148_*.bin` | 201KB | `deploy_js_selfplay.sh` |
| AI params (short) | `deploy/tmp_swf_extract/93_*.bin` | ~50KB | `deploy_js_selfplay.sh` |
| cardLibrary.jso | `deploy/asset/config/cardLibrary.jso` | 43KB | Both |
| Prismata_Testing.exe | `deploy/Prismata_Testing.exe` | ~5MB | `deploy_for_eval.sh` |
| config.txt | `deploy/asset/config/config.txt` | ~30KB | `deploy_for_eval.sh` |
| neural_weights.bin | `deploy/asset/config/neural_weights.bin` | 3.6MB | `deploy_for_eval.sh` |

### Parallelism Model

Each matchup_main.js process uses ~1 core average (alternating MCDSAI/C++ think).
On c5.2xlarge (8 vCPU, 16 GB RAM):

- **4 parallel processes** = safe, headroom for Node.js overhead
- Each process: 1 persistent MCDSAI worker + intermittent C++ exe
- Memory: ~300MB per process (MCDSAI Emscripten module + Node.js)
- Total: ~1.2GB for 4 processes, well within 16GB

### Cost Model

```
Per game: ~5.5 min at 7s C++ think
Total sequential compute for 1000 games: 5500 min
With 4 parallel processes per instance: 1375 instance-minutes needed
Windows c5.2xlarge OD (eu-north-1): $0.732/hr ($0.0122/min)
Base compute cost: 1375 × $0.0122 = $16.78
+ boot overhead (~5 min × N instances): ~$0.50-2.00
```

| Instances | Procs/inst | Total procs | Games/proc | Wall time | Cost |
|-----------|------------|-------------|------------|-----------|------|
| 4 | 4 | 16 | 63 | ~5.8 hr | ~$17 |
| 6 | 4 | 24 | 42 | ~3.9 hr | ~$17 |
| **12** | **4** | **48** | **21** | **~2.0 hr** | **~$18** |
| 24 | 4 | 96 | 11 | ~1.1 hr | ~$19 |

**Sweet spot: 12 instances** (~2 hr wall time, ~$18).

For 2000 games (1000 C++ tournament + 1000 JS matchup) running in parallel:
- C++ fleet: 12 × c5.2xlarge = 96 vCPU → ~$12, ~82 min
- JS fleet: 12 × c5.2xlarge = 96 vCPU → ~$18, ~2 hr
- Total: 192 vCPU (full quota), **~$30, ~2 hr wall time**

### Anti-Patterns to Avoid

- Do NOT use Linux instances — exe is Windows-only
- Do NOT use `dnf install nodejs` — that's AL2023, not Windows Server
- Do NOT run more than 6 processes per c5.2xlarge — diminishing returns
- Do NOT modify matchup_main.js game loop for parallelism — use multi-process
- Do NOT use `$var` in single-quoted heredocs — use `__PLACEHOLDER__` pattern
- Do NOT use `Set-Content` for config patching — use `Get-Content -Raw` + regex

---

## Phase 1: Deploy Script

**Create `aws/deploy_for_matchup.sh`**

This combines uploads from both `deploy_for_eval.sh` (exe + config + weights) and
`deploy_js_selfplay.sh` (JS engine + MCDSAI + AI params) into a single script.

### What to implement

Copy the cloud-config loading pattern from `deploy_for_eval.sh:1-18`.
Combine the S3 upload commands from both existing deploy scripts.

### Files to upload

```bash
# From deploy_for_eval.sh pattern (lines 22-32):
aws s3 cp "$BIN_DIR/Prismata_Testing.exe" "s3://$BUCKET/deploy/Prismata_Testing.exe"
aws s3 cp "$BIN_DIR/asset/config/config.txt" "s3://$BUCKET/deploy/asset/config/config.txt"
aws s3 cp "$BIN_DIR/asset/config/cardLibrary.jso" "s3://$BUCKET/deploy/asset/config/cardLibrary.jso"
aws s3 cp "$BIN_DIR/asset/config/neural_weights.bin" "s3://$BUCKET/deploy/asset/config/neural_weights.bin"

# From deploy_js_selfplay.sh pattern (lines 25-56):
aws s3 sync "$BASE/js_engine/" "s3://$BUCKET/deploy/js_engine/" \
    --exclude "*" --include "*.js" --exclude "test_*.js" \
    --exclude "*.jsonl" --exclude "*.json" --exclude "*.txt" --exclude "*.log" --delete
aws s3 cp "$BASE/tmp_browser_client/MCDSAI3441.js" "s3://$BUCKET/deploy/tmp_browser_client/MCDSAI3441.js"
aws s3 cp "$BASE/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" \
    "s3://$BUCKET/deploy/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin"
aws s3 cp "$BASE/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" \
    "s3://$BUCKET/deploy/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin"
```

### Verification

```bash
# After running deploy_for_matchup.sh:
aws s3 ls s3://$BUCKET/deploy/js_engine/ --region $REGION | wc -l    # ~28 .js files
aws s3 ls s3://$BUCKET/deploy/Prismata_Testing.exe --region $REGION  # exists
aws s3 ls s3://$BUCKET/deploy/tmp_browser_client/ --region $REGION   # MCDSAI3441.js
```

---

## Phase 2: matchup_main.js Enhancement (Minimal)

**Add `--summary-json <path>` flag** for structured result collection.

### Why

Currently results are only in stderr text output. Parsing "MCDSAI wins: 48 (49.0%)"
across 48+ worker logs is fragile. A structured JSON summary per worker enables
trivial aggregation.

### What to implement

Add to CLI arg parsing (near line 417 of `matchup_main.js`):
```javascript
let summaryJsonPath = null;
// In arg parsing loop:
case '--summary-json': summaryJsonPath = args[++i]; break;
```

Add at end of main() (after line 614, before process cleanup):
```javascript
if (summaryJsonPath) {
    const summary = {
        mcdsai_wins: mcdsaiWins,
        cpp_wins: cppWins,
        draws: draws,
        total: completed,
        failed: failed,
        avg_turns: avgTurns,
        avg_mcdsai_think_ms: avgMcdsaiThink,
        avg_cpp_think_ms: avgCppThink,
        mcdsai_difficulty: difficulty,
        cpp_player: playerName,
        think_time_ms: thinkTime,
        games_requested: numGames
    };
    fs.writeFileSync(summaryJsonPath, JSON.stringify(summary, null, 2));
}
```

### References

- Arg parsing pattern: `matchup_main.js:400-440` (existing --games, --jsonl, etc.)
- Stats variables: `matchup_main.js:460-465` (mcdsaiWins, cppWins, etc.)
- Final report: `matchup_main.js:596-615` (existing text output to replicate as JSON)

### Verification

```bash
cd js_engine
node matchup_main.js --games 2 --think-time 1000 --summary-json /tmp/test_summary.json
cat /tmp/test_summary.json  # Should have mcdsai_wins, cpp_wins, etc.
```

---

## Phase 3: Launch Script (Main Deliverable)

**Create `aws/launch_matchup.sh`**

### Script Signature

```bash
bash aws/launch_matchup.sh [INSTANCE_TYPE] [NUM_GAMES] [NUM_INSTANCES] [THINK_TIME_MS]
```

| Arg | Default | Description |
|-----|---------|-------------|
| `$1` INSTANCE_TYPE | `c5.2xlarge` | EC2 instance type |
| `$2` NUM_GAMES | `1000` | Total games across all instances |
| `$3` NUM_INSTANCES | `1` | Number of EC2 instances |
| `$4` THINK_TIME_MS | `7000` | C++ AI think time in ms |

| Env Var | Default | Description |
|---------|---------|-------------|
| `WEIGHTS_KEY` | `deploy/asset/config/neural_weights.bin` | S3 key for weights |
| `MODEL_LABEL` | `default` | Instance tag label |
| `USE_SPOT` | `false` | Use spot instances |
| `CPP_PLAYER` | `OriginalHardestAI` | C++ player name |
| `MCDSAI_DIFFICULTY` | `HardestAI` | MCDSAI difficulty |

### Process Count Mapping

```bash
# Each matchup game uses ~1 core average (alternating MCDSAI/C++ think)
case "$INSTANCE_TYPE" in
  c5.xlarge)   WORKERS=3 ;;   # 4 vCPU
  c5.2xlarge)  WORKERS=4 ;;   # 8 vCPU
  c5.4xlarge)  WORKERS=8 ;;   # 16 vCPU
  c5.9xlarge)  WORKERS=16 ;;  # 36 vCPU
  *)           WORKERS=2 ;;
esac
```

### PowerShell UserData Structure

Copy the heredoc pattern from `launch_tournament.sh:90-252`. Key sections:

#### Section 1: Static heredoc (single-quoted to protect PS syntax)

```powershell
<powershell>
$ErrorActionPreference = "Continue"
$bucket = "__CLOUD_BUCKET__"
$runId = "matchup_" + (Get-Date -Format "yyyy-MM-dd_HH-mm-ss") + "_" + $env:COMPUTERNAME

Start-Transcript -Path "C:\matchup_boot.log" -Append

# Install VC++ Redistributable (for Prismata_Testing.exe)
# Copy pattern from launch_tournament.sh:102-106
$vcUrl = "https://aka.ms/vs/17/release/vc_redist.x86.exe"
Invoke-WebRequest -Uri $vcUrl -OutFile "C:\vc_redist.x86.exe"
Start-Process -Wait -FilePath "C:\vc_redist.x86.exe" -ArgumentList "/install /quiet /norestart"

# Install Node.js (portable zip — no MSI, no admin prompts)
$nodeVer = "v20.11.0"
$nodeUrl = "https://nodejs.org/dist/$nodeVer/node-$nodeVer-win-x64.zip"
Invoke-WebRequest -Uri $nodeUrl -OutFile "C:\node.zip"
Expand-Archive -Path "C:\node.zip" -DestinationPath "C:\"
$env:PATH = "C:\node-$nodeVer-win-x64;$env:PATH"
[Environment]::SetEnvironmentVariable("PATH", $env:PATH, "Process")

# Create directory structure matching local project layout
# CRITICAL: matchup_main.js uses relative paths:
#   ../bin/Prismata_Testing.exe (from js_engine/)
#   ../bin/asset/config/cardLibrary.jso (from card_library.js)
#   ../tmp_browser_client/MCDSAI3441.js (from mcdsai_wrapper.js)
#   ../tmp_swf_extract/*.bin (from ai_params.js)
New-Item -ItemType Directory -Force -Path "C:\matchup\js_engine" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\bin\asset\config" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\tmp_browser_client" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\tmp_swf_extract" | Out-Null
New-Item -ItemType Directory -Force -Path "C:\matchup\output" | Out-Null

# Download from S3
Write-Host "Downloading JS engine..."
# aws s3 sync for js_engine/ (Read-S3Object doesn't support sync)
$jsFiles = Get-S3Object -BucketName $bucket -KeyPrefix "deploy/js_engine/" -Region __AWS_REGION__
foreach ($f in $jsFiles) {
    if ($f.Key -match '\.js$') {
        $localPath = "C:\matchup\js_engine\" + ($f.Key -replace '^deploy/js_engine/', '')
        Read-S3Object -BucketName $bucket -Key $f.Key -File $localPath -Region __AWS_REGION__
    }
}

Write-Host "Downloading MCDSAI + AI params..."
Read-S3Object -BucketName $bucket -Key "deploy/tmp_browser_client/MCDSAI3441.js" `
    -File "C:\matchup\tmp_browser_client\MCDSAI3441.js" -Region __AWS_REGION__
Read-S3Object -BucketName $bucket -Key "deploy/tmp_swf_extract/148_AI.AIThreadHandler_aiParamTextLoad.bin" `
    -File "C:\matchup\tmp_swf_extract\148_AI.AIThreadHandler_aiParamTextLoad.bin" -Region __AWS_REGION__
Read-S3Object -BucketName $bucket -Key "deploy/tmp_swf_extract/93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" `
    -File "C:\matchup\tmp_swf_extract\93_AI.AIThreadHandler_aiParam_shortTextLoad.bin" -Region __AWS_REGION__

Write-Host "Downloading C++ exe + config..."
Read-S3Object -BucketName $bucket -Key "deploy/Prismata_Testing.exe" `
    -File "C:\matchup\bin\Prismata_Testing.exe" -Region __AWS_REGION__
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/config.txt" `
    -File "C:\matchup\bin\asset\config\config.txt" -Region __AWS_REGION__
Read-S3Object -BucketName $bucket -Key "deploy/asset/config/cardLibrary.jso" `
    -File "C:\matchup\bin\asset\config\cardLibrary.jso" -Region __AWS_REGION__
Read-S3Object -BucketName $bucket -Key "__WEIGHTS_KEY__" `
    -File "C:\matchup\bin\asset\config\neural_weights.bin" -Region __AWS_REGION__

Write-Host "Download complete. Verifying Node.js..."
node --version
</powershell>
```

#### Section 2: Placeholder injection (after heredoc)

```bash
USERDATA="${USERDATA/__CLOUD_BUCKET__/$BUCKET}"
USERDATA="${USERDATA//__AWS_REGION__/$REGION}"
USERDATA="${USERDATA/__WEIGHTS_KEY__/$WEIGHTS_KEY}"
```

#### Section 3: Dynamic variable injection + worker launch

```powershell
$numWorkers = __NUM_WORKERS__
$gamesPerWorker = __GAMES_PER_WORKER__
$thinkTime = __THINK_TIME__
$cppPlayer = "__CPP_PLAYER__"
$mcdsaiDifficulty = "__MCDSAI_DIFFICULTY__"

# Launch parallel matchup workers
$jobs = @()
for ($i = 0; $i -lt $numWorkers; $i++) {
    Write-Host "Launching matchup worker $i ($gamesPerWorker games)..."

    $nodeArgs = "matchup_main.js" +
        " --games $gamesPerWorker" +
        " --think-time $thinkTime" +
        " --player $cppPlayer" +
        " --difficulty $mcdsaiDifficulty" +
        " --exe ..\bin\Prismata_Testing.exe" +
        " --jsonl ..\output\matchup_worker_${i}.jsonl" +
        " --summary-json ..\output\summary_${i}.json"

    $job = Start-Process -FilePath "node" `
        -ArgumentList $nodeArgs `
        -WorkingDirectory "C:\matchup\js_engine" `
        -RedirectStandardOutput "C:\matchup\output\stdout_worker_$i.txt" `
        -RedirectStandardError "C:\matchup\output\log_worker_$i.txt" `
        -PassThru

    $jobs += $job
    Start-Sleep -Seconds 2   # stagger for unique PIDs (temp file naming)
}
```

#### Section 4: Periodic S3 sync (copy pattern from launch_tournament.sh:191-225)

```powershell
function Sync-MatchupToS3 {
    param($bucket, $runId, $region, $numWorkers)
    $syncCount = 0
    $tempBase = "C:\matchup\sync_temp"
    New-Item -ItemType Directory -Force -Path $tempBase | Out-Null

    # Summary JSONs (structured results)
    $summaryFiles = Get-ChildItem "C:\matchup\output\summary_*.json" -ErrorAction SilentlyContinue
    foreach ($f in $summaryFiles) {
        try {
            Copy-Item $f.FullName "$tempBase\$($f.Name)" -Force
            Write-S3Object -BucketName $bucket -Key "matchup-results/$runId/$($f.Name)" `
                -File "$tempBase\$($f.Name)" -Region $region
            $syncCount++
        } catch { Write-Host "[Sync] Warning: $($f.Name): $_" }
    }

    # Worker logs
    for ($i = 0; $i -lt $numWorkers; $i++) {
        foreach ($prefix in @("log_worker", "stdout_worker")) {
            $logFile = "C:\matchup\output\${prefix}_$i.txt"
            if (Test-Path $logFile) {
                try {
                    Copy-Item $logFile "$tempBase\${prefix}_$i.txt" -Force
                    Write-S3Object -BucketName $bucket `
                        -Key "matchup-results/$runId/${prefix}_$i.txt" `
                        -File "$tempBase\${prefix}_$i.txt" -Region $region
                    $syncCount++
                } catch { }
            }
        }
    }

    # JSONL training data (may be large, upload periodically)
    $jsonlFiles = Get-ChildItem "C:\matchup\output\matchup_worker_*.jsonl" -ErrorAction SilentlyContinue
    foreach ($f in $jsonlFiles) {
        try {
            Copy-Item $f.FullName "$tempBase\$($f.Name)" -Force
            Write-S3Object -BucketName $bucket -Key "matchup-results/$runId/$($f.Name)" `
                -File "$tempBase\$($f.Name)" -Region $region
            $syncCount++
        } catch { }
    }

    Remove-Item $tempBase -Recurse -Force -ErrorAction SilentlyContinue
    return $syncCount
}

# Wait for workers with periodic sync every 5 minutes
$syncIntervalSec = 300
while ($true) {
    $running = @($jobs | Where-Object { -not $_.HasExited })
    if ($running.Count -eq 0) { break }
    Start-Sleep -Seconds $syncIntervalSec
    $count = Sync-MatchupToS3 $bucket $runId $region $numWorkers
    $running = @($jobs | Where-Object { -not $_.HasExited })
    Write-Host "[Sync] Uploaded $count files. Workers running: $($running.Count)/$numWorkers"
}

# Final sync + shutdown
foreach ($job in $jobs) {
    Write-Host "Worker PID $($job.Id) exit code: $($job.ExitCode)"
}
$count = Sync-MatchupToS3 $bucket $runId $region $numWorkers
Write-Host "[Sync] Final upload: $count files"

Stop-Transcript
Write-S3Object -BucketName $bucket -Key "matchup-results/$runId/matchup_boot.log" `
    -File "C:\matchup_boot.log" -Region $region
Stop-Computer -Force
```

#### Section 5: EC2 launch loop

Copy from `launch_tournament.sh:259-292`, changing:
- Tag name: `PrismataMatchup-{MODEL_LABEL}-{NUM_GAMES}g`
- Use `$AMI` (Windows AMI from cloud-config.env)

### S3 Output Structure

```
s3://$BUCKET/matchup-results/
└── matchup_YYYY-MM-DD_HH-MM-SS_HOSTNAME/
    ├── summary_0.json              # Structured results (per worker)
    ├── summary_1.json
    ├── summary_2.json
    ├── summary_3.json
    ├── matchup_worker_0.jsonl      # Training data
    ├── matchup_worker_1.jsonl
    ├── log_worker_0.txt            # stderr (progress + stats)
    ├── log_worker_1.txt
    ├── stdout_worker_0.txt         # stdout
    ├── stdout_worker_1.txt
    └── matchup_boot.log            # Boot transcript
```

### Verification

```bash
# Dry run (prints config, doesn't launch)
DRY_RUN=true bash aws/launch_matchup.sh c5.2xlarge 100 1 3000

# Single instance smoke test
bash aws/launch_matchup.sh c5.2xlarge 8 1 3000
# (8 games, 1 instance, 3s think = ~3 min per game × 2 games/worker = ~6 min)

# Monitor
aws ec2 describe-instances --region $REGION \
    --filters "Name=tag:Name,Values=PrismataMatchup-*" "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`].Value|[0],State.Name]' \
    --output table
```

---

## Phase 4: Result Aggregation

**Create `aws/aggregate_matchup_results.sh`** (or Python script)

### What to implement

Download all `summary_*.json` files from `matchup-results/`, aggregate wins/losses:

```bash
#!/bin/bash
# Usage: bash aws/aggregate_matchup_results.sh [RUN_PREFIX]
# Downloads and aggregates matchup results from S3

BUCKET="${CLOUD_BUCKET:?}"
REGION="${AWS_REGION:-eu-north-1}"
PREFIX="${1:-matchup-results/}"

# Download all summary files
mkdir -p matchup_results_tmp
aws s3 sync "s3://$BUCKET/$PREFIX" matchup_results_tmp/ \
    --region "$REGION" --exclude "*" --include "*/summary_*.json"

# Aggregate with Python
python -c "
import json, glob, os
summaries = glob.glob('matchup_results_tmp/**/summary_*.json', recursive=True)
total = {'mcdsai_wins': 0, 'cpp_wins': 0, 'draws': 0, 'total': 0, 'failed': 0}
for f in sorted(summaries):
    with open(f) as fh:
        d = json.load(fh)
    for k in total:
        total[k] += d.get(k, 0)
    print(f'  {os.path.basename(os.path.dirname(f))}/{os.path.basename(f)}: '
          f'MCDSAI {d[\"mcdsai_wins\"]}, C++ {d[\"cpp_wins\"]}, draws {d[\"draws\"]}')

completed = total['total']
wr = total['mcdsai_wins'] / completed * 100 if completed else 0
# Wilson 95% CI
import math
z = 1.96
p = total['mcdsai_wins'] / completed if completed else 0
n = completed
denom = 1 + z*z/n
center = (p + z*z/(2*n)) / denom
margin = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n) / denom
lo, hi = max(0, center - margin) * 100, min(1, center + margin) * 100

print()
print(f'=== Aggregate Results ===')
print(f'MCDSAI wins:  {total[\"mcdsai_wins\"]} ({wr:.1f}%)')
print(f'C++ wins:     {total[\"cpp_wins\"]} ({100-wr:.1f}%)')
print(f'Draws:        {total[\"draws\"]}')
print(f'Total:        {completed} ({total[\"failed\"]} failed)')
print(f'Wilson 95% CI: [{lo:.1f}%, {hi:.1f}%]')
"
```

### Verification

Run against a local smoke test first (2 workers, 4 games each).

---

## Phase 5: Verification & Smoke Test

### Step 1: Local Smoke Test

```bash
# Test matchup_main.js locally with --summary-json
cd js_engine
node matchup_main.js --games 2 --think-time 1000 --summary-json ../test_summary.json 2> ../test_log.txt
cat ../test_summary.json
cat ../test_log.txt
```

### Step 2: Deploy Test

```bash
# Deploy all files to S3
bash aws/deploy_for_matchup.sh

# Verify S3 contents
aws s3 ls s3://$BUCKET/deploy/js_engine/ --region $REGION | wc -l          # ~28 files
aws s3 ls s3://$BUCKET/deploy/Prismata_Testing.exe --region $REGION        # exists
aws s3 ls s3://$BUCKET/deploy/tmp_browser_client/ --region $REGION         # MCDSAI
```

### Step 3: Single Instance Cloud Test

```bash
# 8 games, 1 instance, 3s think time = ~3 min per game
# With 4 workers: 2 games per worker = ~6 min total + 5 min boot
bash aws/launch_matchup.sh c5.2xlarge 8 1 3000
# Expected cost: ~$0.12 (1 instance × 11 min × $0.732/hr)
```

Wait ~15 min, then check results:

```bash
aws s3 ls s3://$BUCKET/matchup-results/ --region $REGION --recursive
# Should see summary_0.json through summary_3.json, log files, JSONL files
bash aws/aggregate_matchup_results.sh
```

### Step 4: Anti-Pattern Checks

```bash
# Verify no hardcoded paths in launch script
grep -n 'c:\\libraries' aws/launch_matchup.sh       # Should be 0 matches
grep -n 'Surfinite' aws/launch_matchup.sh            # Should be 0 matches

# Verify Node.js URL uses HTTPS
grep -n 'nodejs.org' aws/launch_matchup.sh           # Should show https://

# Verify auto-terminate is present
grep -n 'Stop-Computer' aws/launch_matchup.sh        # Should be present

# Verify placeholder pattern (not raw $var in heredocs)
grep -n '__CLOUD_BUCKET__' aws/launch_matchup.sh     # Should be present
```

---

## Launch Commands (For Production Run)

### 1000 games vs MCDSAI (OriginalHardestAI as C++ player)

```bash
# Deploy
bash aws/deploy_for_matchup.sh

# Launch 12 instances (192/2=96 vCPU if sharing with C++ tournament)
bash aws/launch_matchup.sh c5.2xlarge 1000 12 7000
```

### 2000 games (combined with C++ tournament)

```bash
# Deploy everything once
bash aws/deploy_for_matchup.sh

# Fleet A: 1000 games C++ tournament (PrismatAI_AB_Legacy vs OriginalHardestAI)
bash aws/launch_tournament.sh c5.2xlarge 21 1.3 12

# Fleet B: 1000 games JS matchup (MCDSAI vs OriginalHardestAI via --suggest)
bash aws/launch_matchup.sh c5.2xlarge 1000 12 7000

# Monitor both fleets
aws ec2 describe-instances --region $REGION \
    --filters "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`].Value|[0],LaunchTime]' \
    --output table

# Aggregate results when done
aws s3 sync s3://$BUCKET/eval-results/ eval-results/ --region $REGION
bash aws/aggregate_matchup_results.sh
```

### Cost comparison

| Run | Instances | Wall Time | Cost |
|-----|-----------|-----------|------|
| 1000 C++ tournament only | 12 × c5.2xlarge Win OD | ~82 min | ~$12 |
| 1000 JS matchup only | 12 × c5.2xlarge Win OD | ~2 hr | ~$18 |
| **Both (parallel)** | **24 × c5.2xlarge Win OD** | **~2 hr** | **~$30** |

---

## Implementation Order

1. **Phase 2** first (matchup_main.js --summary-json) — small, testable locally
2. **Phase 1** (deploy script) — straightforward combination of existing scripts
3. **Phase 3** (launch script) — main deliverable, most complex
4. **Phase 4** (aggregation) — simple post-processing
5. **Phase 5** (verification) — local then cloud smoke tests

Each phase is independently verifiable before proceeding to the next.
