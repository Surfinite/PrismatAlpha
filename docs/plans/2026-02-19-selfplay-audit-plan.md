# Self-Play Data Integrity Audit — Implementation Plan

**Goal:** Build `tools/audit_selfplay_s3.py` that streams all 7,756 shards from S3, performs comprehensive integrity checks, and outputs a JSON report. Run it on a cheap AWS spot instance in eu-north-1 (same region as data — free transfer, fast reads).

**Estimated cost:** <$0.10 (c5.xlarge spot ~$0.07/hr, ~30 min runtime)

---

## Phase 1: Build `tools/audit_selfplay_s3.py`

### Overview
A self-contained Python script (only needs `boto3`, `numpy`, `zlib` stdlib) that:
1. Lists all `.bin` files under `s3://$CLOUD_BUCKET/results/`
2. Streams each shard, validates structure, accumulates statistics
3. Outputs a JSON report + human-readable summary

### Checks to Implement

**Per-Shard Checks:**
1. **Header validation** — magic=0x50534450, version=1, endian=0x01020304, feature_dim=1785, record_size=7152
2. **File size alignment** — `(size - 64 - 4) % 7152 == 0`, inferred count matches header count
3. **CRC32 verification** — `zlib.crc32(record_bytes) & 0xFFFFFFFF` vs stored footer
4. **Record-level sampling** (every Nth record, or all if fast enough):
   - Outcome ∈ {-1.0, 0.0, +1.0}
   - player_index ∈ {0, 1}
   - flags ≤ 0x01
   - No NaN/Inf in features (sample first 100 floats per record for speed)

**Cross-Shard Checks (accumulated in memory):**
5. **Game ID uniqueness** — set of all game_ids seen (705K entries × ~50 bytes ≈ 35MB)
6. **Duplicate game detection** — hash first position's features per game → detect collisions
   - For each game_id, store hash of first record's feature vector (xxhash or md5)
   - 705K hashes × ~24 bytes ≈ 17MB
7. **Outcome consistency** — for each game_id, all records for player P must have same outcome
   - Store `{game_id: {(player, outcome)}}` — only flag mismatches
8. **Turn monotonicity** — within each shard, verify turn_numbers increase per game_id
9. **P0/P1 win rate balance** — aggregate win/loss/draw counts per player_index
10. **Game length distribution** — records per game_id, compute mean/median/max/min/std
11. **Feature value ranges** — track global min/max of each feature dimension (or sampled subset)

### Memory Budget (c5.xlarge = 8GB RAM)
| Data Structure | Size | Purpose |
|---|---|---|
| game_id set | ~35 MB | Uniqueness check |
| game_hash dict | ~50 MB | Duplicate game detection |
| game_outcome dict | ~50 MB | Outcome consistency (sparse, only store on first encounter) |
| game_record_counts | ~30 MB | Game length distribution |
| Feature min/max arrays | ~14 KB | 1785 × 2 × float32 |
| Current shard buffer | ~200 MB | Largest shard is ~107 MB, buffer 2x |
| **Total** | **~365 MB** | Well within 8GB |

### Implementation Pattern

```python
#!/usr/bin/env python3
"""Audit all self-play shards in S3 for integrity and statistical anomalies."""

import boto3, struct, zlib, json, sys, hashlib, time
import numpy as np
from collections import defaultdict

BUCKET = '$CLOUD_BUCKET'
PREFIX = 'results/'
REGION = 'eu-north-1'
MAGIC = 0x50534450
VERSION = 1
HEADER_SIZE = 64
FOOTER_SIZE = 4
ENDIAN_CHECK = 0x01020304
FEATURE_DIM = 1785
RECORD_SIZE = FEATURE_DIM * 4 + 4 + 4 + 2 + 1 + 1  # 7152

# Accumulate across shards
all_game_ids = set()
game_first_hash = {}        # game_id -> hash of first position features
game_outcomes = {}           # game_id -> set of (player, outcome) tuples
game_record_counts = defaultdict(int)  # game_id -> count
p0_wins, p0_losses, p1_wins, p1_losses, draws = 0, 0, 0, 0, 0
feature_min = np.full(FEATURE_DIM, np.inf, dtype=np.float32)
feature_max = np.full(FEATURE_DIM, -np.inf, dtype=np.float32)

errors = []  # list of error dicts
warnings = []  # list of warning dicts

def audit_shard(s3_client, key, file_size):
    """Download and audit a single shard. Returns dict of per-shard stats."""
    # ... download, parse header, validate CRC, scan records ...

def main():
    s3 = boto3.client('s3', region_name=REGION)
    # List all .bin files
    # Process each shard
    # Cross-shard checks
    # Output report
```

### Output Format (JSON)

```json
{
  "timestamp": "2026-02-19T20:00:00Z",
  "bucket": "$CLOUD_BUCKET",
  "prefix": "results/",
  "summary": {
    "total_shards": 7756,
    "total_records": 26000000,
    "total_games": 705000,
    "total_bytes": 196000000000,
    "shards_with_errors": 0,
    "shards_with_warnings": 12,
    "duplicate_game_ids": 0,
    "duplicate_games_by_features": 0,
    "outcome_inconsistencies": 0,
    "crc_failures": 0,
    "nan_inf_records": 0
  },
  "win_rates": {
    "p0_wins": 345000, "p0_losses": 348000, "p0_draws": 12000,
    "p1_wins": 348000, "p1_losses": 345000, "p1_draws": 12000,
    "p0_win_pct": 49.6, "p1_win_pct": 50.0
  },
  "game_length_stats": {
    "mean": 37.2, "median": 35, "std": 12.1,
    "min": 4, "max": 312, "p95": 65, "p99": 98
  },
  "feature_ranges": {
    "global_min": -1.0, "global_max": 45.0,
    "dims_always_zero": 42, "dims_negative": 14
  },
  "errors": [],
  "warnings": [
    {"shard": "results/.../selfplay_t00_s000.bin", "type": "sentinel_record_count", "msg": "..."}
  ],
  "per_shard_stats": [...]
}
```

### Documentation References
- Header parsing: `training/load_selfplay.py:43-69` (parse_header function)
- CRC validation: `training/load_selfplay.py:119-126` (zlib.crc32 pattern)
- Record dtype: `training/load_selfplay.py:31-40` (make_record_dtype)
- Verify patterns: `tools/verify_selfplay.py` (6-check structure)
- C++ CRC: `source/testing/SelfPlayDataSink.cpp:12-28,257-266` (IEEE 802.3)

### Anti-Patterns to Avoid
- Do NOT download all 182GB to disk — stream via boto3 `get_object` per shard
- Do NOT hold all records in memory — process per-shard, accumulate only metadata
- Do NOT use `aws s3 ls --recursive` (times out on 8000+ objects) — use `list_objects_v2` paginator
- Do NOT assume record_count in header is valid — crashed shards have sentinel 0xFFFFFFFFFFFFFFFF, infer from file size instead
- CRC check will FAIL on crashed/in-progress shards (no footer) — report as warning, not error

### Verification
- Run locally on a single small run dir first (e.g., `bin/training/data/selfplay/2026-02-15_11-31-33/`, 4 shards) to verify logic
- Compare CRC results with existing `tools/verify_selfplay.py` on same shards

---

## Phase 2: Build `aws/launch_audit.sh`

### Overview
Minimal launch script based on `aws/launch_training.sh` pattern but much simpler:
- c5.xlarge spot (~$0.07/hr) in eu-north-1
- Amazon Linux 2023 AMI (same training AMI works: `$AWS_AMI_DL_PYTORCH`)
- Install boto3+numpy, download audit script from S3, run, upload results, terminate
- No GPU needed, small disk (20GB default is fine)

### Userdata Script (bash)
```bash
#!/bin/bash
set -e
exec > /tmp/audit_boot.log 2>&1

# Setup Python
source /opt/pytorch/bin/activate 2>/dev/null || {
    yum install -y python3-pip
    pip3 install boto3 numpy
}

# Download audit script
aws s3 cp s3://$CLOUD_BUCKET/deploy/tools/audit_selfplay_s3.py /tmp/audit.py --region eu-north-1

# Run audit
cd /tmp
python3 audit.py 2>&1 | tee audit_output.log

# Upload results
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
aws s3 cp /tmp/audit_report.json s3://$CLOUD_BUCKET/audit-results/audit_${TIMESTAMP}.json --region eu-north-1
aws s3 cp /tmp/audit_output.log s3://$CLOUD_BUCKET/audit-results/audit_${TIMESTAMP}.log --region eu-north-1
aws s3 cp /tmp/audit_boot.log s3://$CLOUD_BUCKET/audit-results/audit_${TIMESTAMP}_boot.log --region eu-north-1

# Self-terminate
sudo shutdown -h now
```

### Launch Command
```bash
# Deploy audit script to S3 first
aws s3 cp tools/audit_selfplay_s3.py s3://$CLOUD_BUCKET/deploy/tools/audit_selfplay_s3.py --region eu-north-1

# Launch
bash aws/launch_audit.sh
```

### Infrastructure Details
- **AMI:** `$AWS_AMI_DL_PYTORCH` (Deep Learning AMI, has Python+boto3 preinstalled)
- **Instance type:** c5.xlarge (4 vCPU, 8GB RAM) — no GPU needed
- **Disk:** 20GB gp3 (default, plenty for a script that streams)
- **Spot:** Always (one-time, terminate on interruption)
- **Region:** eu-north-1 (same as S3 — free, fast transfers)
- **Auto-terminate:** `--instance-initiated-shutdown-behavior terminate` + `shutdown -h now`
- **IAM:** Same `PrismataSelfPlayEC2` profile (already has S3 read/write)
- **Results:** Uploaded to `s3://$CLOUD_BUCKET/audit-results/`

### Documentation References
- Spot request pattern: `aws/launch_training.sh:330-397`
- Userdata structure: `aws/launch_training.sh:93-313`
- Auto-terminate: `aws/launch_training.sh:408` (`--instance-initiated-shutdown-behavior terminate`)
- IAM profile: `PrismataSelfPlayEC2` (used in all launch scripts)
- AMI ID: `aws/launch_training.sh:59`

---

## Phase 3: Local Dry Run + Deploy + Launch

### Steps
1. **Test locally** on a small subset:
   ```bash
   python tools/audit_selfplay_s3.py --local-dir bin/training/data/selfplay/2026-02-15_11-31-33/
   ```
   Verify output matches `tools/verify_selfplay.py` results on same dir.

2. **Deploy to S3:**
   ```bash
   aws s3 cp tools/audit_selfplay_s3.py s3://$CLOUD_BUCKET/deploy/tools/audit_selfplay_s3.py --region eu-north-1
   ```

3. **Launch on spot:**
   ```bash
   bash aws/launch_audit.sh
   ```

4. **Monitor:**
   - Check spot request fulfillment
   - Wait ~30 min
   - Download results:
     ```bash
     aws s3 ls s3://$CLOUD_BUCKET/audit-results/ --region eu-north-1
     aws s3 cp s3://$CLOUD_BUCKET/audit-results/audit_LATEST.json . --region eu-north-1
     ```

### Verification Checklist
- [ ] Local test passes on small subset (4 shards, known-good data)
- [ ] CRC results match verify_selfplay.py
- [ ] Game ID uniqueness confirmed
- [ ] No duplicate games detected (or flagged with details)
- [ ] Outcome consistency holds for all games
- [ ] P0/P1 win rate is roughly balanced (~50/50)
- [ ] Game length distribution looks reasonable (mean ~37 records)
- [ ] No NaN/Inf in features
- [ ] Report JSON is well-formed and complete
- [ ] Instance auto-terminated after completion

---

## Summary

| Phase | What | Output |
|---|---|---|
| 1 | Build `tools/audit_selfplay_s3.py` | Python script with 11 checks |
| 2 | Build `aws/launch_audit.sh` | Minimal spot launcher |
| 3 | Test locally, deploy, launch on spot | JSON audit report in S3 |

**Total estimated cost:** <$0.10 (one c5.xlarge spot for ~30 min)
**Total estimated runtime:** ~30 min on AWS (I/O bound reading 7,756 shards from S3)
