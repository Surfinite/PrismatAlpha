#!/usr/bin/env python3
"""Audit all self-play shards in S3 (or local dir) for integrity and statistical anomalies.

Streams each shard, validates structure, accumulates statistics, outputs JSON report.
Memory-efficient: only metadata is held in RAM, not record data.

Usage:
  # S3 mode (run on EC2 in eu-north-1 for free/fast transfer):
  python audit_selfplay_s3.py

  # Local mode (test on small subset):
  python audit_selfplay_s3.py --local-dir bin/training/data/selfplay/2026-02-15_11-31-33/

  # Options:
  --sample-every N    Only inspect every Nth record for feature checks (default: 1 = all)
  --output FILE       Output JSON report path (default: audit_report.json)
  --skip-crc          Skip CRC32 verification (faster, less thorough)
"""

import argparse
import glob
import hashlib
import json
import os
import struct
import sys
import time
import zlib
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

# ── Binary format constants (must match SelfPlayDataSink.cpp / load_selfplay.py) ──
MAGIC = 0x50534450        # "PSDP"
VERSION = 1
HEADER_SIZE = 64
FOOTER_SIZE = 4           # CRC32
ENDIAN_CHECK = 0x01020304
RECORD_COUNT_SENTINEL = 0xFFFFFFFFFFFFFFFF
FEATURE_DIM = 1785
RECORD_SIZE = FEATURE_DIM * 4 + 4 + 4 + 2 + 1 + 1  # 7152

# S3 defaults
BUCKET = 'prismata-selfplay-data'
PREFIX = 'results/'
REGION = 'eu-north-1'


def parse_header(data):
    """Parse the 64-byte header. Returns dict or raises ValueError."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Header too short: {len(data)} bytes")
    magic = struct.unpack_from('<I', data, 0)[0]
    version = struct.unpack_from('<I', data, 4)[0]
    feature_dim = struct.unpack_from('<I', data, 8)[0]
    record_size = struct.unpack_from('<I', data, 12)[0]
    record_count = struct.unpack_from('<Q', data, 16)[0]
    endian_check = struct.unpack_from('<I', data, 24)[0]
    return {
        'magic': magic,
        'version': version,
        'feature_dim': feature_dim,
        'record_size': record_size,
        'record_count': record_count,
        'endian_check': endian_check,
    }


def make_record_dtype(feature_dim):
    """Numpy structured dtype for one record."""
    return np.dtype([
        ('features', np.float32, (feature_dim,)),
        ('outcome', np.float32),
        ('game_id', np.uint32),
        ('turn_number', np.uint16),
        ('player_index', np.uint8),
        ('flags', np.uint8),
    ])


# ── Accumulators ──

class AuditState:
    """Holds all cross-shard accumulated state."""

    def __init__(self):
        self.total_games = 0              # accumulated per-shard game count
        self.game_first_hashes = {}       # (shard_idx, game_id) -> md5 hex
        self.shard_index = 0              # incremented per shard
        self.game_lengths = []            # records per game (all shards)
        self.outcome_issues = 0           # total outcome inconsistencies
        # Win/loss/draw counters per player_index
        self.p0_wins = 0
        self.p0_losses = 0
        self.p1_wins = 0
        self.p1_losses = 0
        self.draws = 0
        # Feature stats
        self.feature_min = np.full(FEATURE_DIM, np.inf, dtype=np.float64)
        self.feature_max = np.full(FEATURE_DIM, -np.inf, dtype=np.float64)
        self.dims_always_zero = np.ones(FEATURE_DIM, dtype=bool)
        # Errors / warnings
        self.errors = []
        self.warnings = []
        # Per-shard stats list
        self.shard_stats = []
        # Totals
        self.total_shards = 0
        self.total_records = 0
        self.total_bytes = 0
        self.crc_ok = 0
        self.crc_fail = 0
        self.crc_skip = 0
        self.nan_records = 0
        self.inf_records = 0

    def add_error(self, shard, err_type, msg):
        self.errors.append({'shard': shard, 'type': err_type, 'msg': msg})

    def add_warning(self, shard, warn_type, msg):
        self.warnings.append({'shard': shard, 'type': warn_type, 'msg': msg})


def outcome_sign(val):
    """Quantize outcome float to +1/0/-1 for consistency checks."""
    if val > 0.5:
        return 1
    elif val < -0.5:
        return -1
    return 0


def audit_shard(data, key, file_size, state, sample_every=1, skip_crc=False):
    """Audit a single shard's data. Updates state in-place."""
    shard_info = {'key': key, 'size': file_size, 'records': 0, 'status': 'ok'}
    state.total_shards += 1
    state.total_bytes += file_size

    # ── Check 1: Header validation ──
    try:
        header = parse_header(data)
    except ValueError as e:
        state.add_error(key, 'header_parse', str(e))
        shard_info['status'] = 'error'
        state.shard_stats.append(shard_info)
        return

    if header['magic'] != MAGIC:
        state.add_error(key, 'bad_magic', f"0x{header['magic']:08X}")
        shard_info['status'] = 'error'
        state.shard_stats.append(shard_info)
        return

    if header['version'] != VERSION:
        state.add_error(key, 'bad_version', str(header['version']))

    if header['endian_check'] != ENDIAN_CHECK:
        state.add_error(key, 'bad_endian', f"0x{header['endian_check']:08X}")
        shard_info['status'] = 'error'
        state.shard_stats.append(shard_info)
        return

    if header['feature_dim'] != FEATURE_DIM:
        state.add_error(key, 'bad_feature_dim', str(header['feature_dim']))
        shard_info['status'] = 'error'
        state.shard_stats.append(shard_info)
        return

    expected_rs = header['feature_dim'] * 4 + 4 + 4 + 2 + 1 + 1
    if header['record_size'] != expected_rs:
        state.add_error(key, 'bad_record_size',
                        f"header={header['record_size']} expected={expected_rs}")
        shard_info['status'] = 'error'
        state.shard_stats.append(shard_info)
        return

    # ── Check 2: File size alignment ──
    payload = file_size - HEADER_SIZE - FOOTER_SIZE
    if payload < 0:
        state.add_error(key, 'too_small', f"size={file_size}")
        shard_info['status'] = 'error'
        state.shard_stats.append(shard_info)
        return

    inferred_count = payload // RECORD_SIZE
    remainder = payload % RECORD_SIZE
    if remainder != 0:
        state.add_warning(key, 'size_misalign',
                          f"payload={payload} remainder={remainder}")

    header_count = header['record_count']
    is_sentinel = header_count == RECORD_COUNT_SENTINEL
    if is_sentinel:
        record_count = inferred_count
        state.add_warning(key, 'sentinel_record_count',
                          f"Header has sentinel count, inferred {inferred_count}")
    else:
        record_count = header_count
        if header_count != inferred_count:
            state.add_warning(key, 'count_mismatch',
                              f"header={header_count} inferred={inferred_count}")

    if record_count == 0:
        state.add_warning(key, 'empty_shard', 'Zero records')
        shard_info['records'] = 0
        state.shard_stats.append(shard_info)
        return

    shard_info['records'] = record_count

    # ── Check 3: CRC32 verification ──
    record_data = data[HEADER_SIZE: HEADER_SIZE + record_count * RECORD_SIZE]
    if not skip_crc:
        footer_offset = HEADER_SIZE + record_count * RECORD_SIZE
        # In-progress shards (sentinel count + trailing bytes) don't have a real
        # CRC footer — the bytes after the last complete record are part of an
        # incomplete record being written when the process was killed.
        if is_sentinel and remainder != 0:
            state.crc_skip += 1
            state.add_warning(key, 'in_progress_shard',
                              f"Sentinel count + {remainder} trailing bytes (no CRC footer)")
            shard_info['status'] = 'in_progress'
        elif footer_offset + FOOTER_SIZE <= len(data):
            stored_crc = struct.unpack_from('<I', data, footer_offset)[0]
            computed_crc = zlib.crc32(record_data) & 0xFFFFFFFF
            if computed_crc == stored_crc:
                state.crc_ok += 1
            else:
                state.crc_fail += 1
                state.add_warning(key, 'crc_mismatch',
                                  f"stored=0x{stored_crc:08X} computed=0x{computed_crc:08X}")
                shard_info['status'] = 'crc_fail'
        else:
            state.crc_skip += 1
            state.add_warning(key, 'no_footer', 'File too short for CRC footer')
    else:
        state.crc_skip += 1

    # ── Check 4+: Record-level scanning ──
    dt = make_record_dtype(FEATURE_DIM)
    # Validate buffer has enough data for the expected record count
    expected_data_len = record_count * RECORD_SIZE
    actual_data_len = len(record_data)
    if actual_data_len < expected_data_len:
        state.add_error(key, 'buffer_too_small',
                        f"need {expected_data_len} bytes for {record_count} records, "
                        f"got {actual_data_len} (file len={len(data)})")
        record_count = actual_data_len // RECORD_SIZE
        if record_count == 0:
            shard_info['records'] = 0
            shard_info['status'] = 'error'
            state.shard_stats.append(shard_info)
            return
        record_data = record_data[:record_count * RECORD_SIZE]
        shard_info['records'] = record_count
    records = np.frombuffer(record_data, dtype=dt, count=record_count)

    features = records['features']
    outcomes = records['outcome']
    game_ids = records['game_id']
    player_indices = records['player_index']
    flags = records['flags']

    # Sample indices for expensive checks
    if sample_every > 1:
        sample_idx = np.arange(0, record_count, sample_every)
    else:
        sample_idx = np.arange(record_count)

    # Check 4a: NaN/Inf in features (sampled)
    sampled_feats = features[sample_idx]
    nan_mask = np.isnan(sampled_feats).any(axis=1)
    inf_mask = np.isinf(sampled_feats).any(axis=1)
    n_nan = int(nan_mask.sum())
    n_inf = int(inf_mask.sum())
    if n_nan > 0:
        state.nan_records += n_nan
        state.add_warning(key, 'nan_features', f"{n_nan} records with NaN")
    if n_inf > 0:
        state.inf_records += n_inf
        state.add_warning(key, 'inf_features', f"{n_inf} records with Inf")

    # Check 4b: Outcome values
    unique_outcomes = np.unique(outcomes)
    valid_outcomes = {-1.0, 0.0, 1.0}
    for ov in unique_outcomes:
        if float(ov) not in valid_outcomes:
            state.add_warning(key, 'unexpected_outcome', f"outcome={ov}")
            break

    # Check 4c: player_index values
    unique_players = np.unique(player_indices)
    for pv in unique_players:
        if int(pv) not in (0, 1):
            state.add_error(key, 'bad_player_index', f"player_index={pv}")

    # Check 4d: flags values
    if np.any(flags > 0x01):
        bad_flags = int(flags.max())
        state.add_warning(key, 'unexpected_flags', f"max_flags=0x{bad_flags:02X}")

    # ── Check 5-8: Per-shard game analysis (vectorized) ──
    # Game IDs are only unique within a shard (each process starts from 0),
    # so all game-level analysis is scoped per-shard.
    shard_idx = state.shard_index

    # Vectorized game counting and length computation
    unique_gids, _, gid_counts = np.unique(
        game_ids, return_inverse=True, return_counts=True)
    shard_game_count = len(unique_gids)
    state.total_games += shard_game_count
    shard_info['games'] = shard_game_count

    # Game lengths (records per game) — already computed by np.unique
    shard_game_lengths = gid_counts.tolist()

    # Check 6: Duplicate game detection — hash first record per game
    # Sort by game_id (stable to preserve record order), take first of each group
    sort_idx = np.argsort(game_ids, kind='stable')
    sorted_gids = game_ids[sort_idx]
    first_mask = np.concatenate([[True], np.diff(sorted_gids) != 0])
    first_indices = sort_idx[first_mask]
    for fi in first_indices:
        composite_key = (shard_idx, int(game_ids[fi]))
        feat_bytes = features[fi].tobytes()
        state.game_first_hashes[composite_key] = hashlib.md5(feat_bytes).hexdigest()

    # Check 7: Outcome consistency — vectorized
    # Compute outcome sign for all records
    outcome_signs = np.zeros(record_count, dtype=np.int8)
    outcome_signs[outcomes > 0.5] = 1
    outcome_signs[outcomes < -0.5] = -1

    # Group by (game_id, player_index), check min==max within each group
    group_keys = game_ids.astype(np.int64) * 2 + player_indices.astype(np.int64)
    gsort = np.argsort(group_keys)
    sorted_gkeys = group_keys[gsort]
    sorted_signs = outcome_signs[gsort]
    # Find group boundaries
    gbound = np.concatenate([[0], np.where(np.diff(sorted_gkeys) != 0)[0] + 1])
    group_mins = np.minimum.reduceat(sorted_signs, gbound)
    group_maxs = np.maximum.reduceat(sorted_signs, gbound)
    outcome_issues = int(np.sum(group_mins != group_maxs))

    # Check 8: Turn monotonicity — vectorized
    sorted_turns = records['turn_number'][sort_idx].astype(np.int32)
    sorted_gids_i32 = sorted_gids.astype(np.int64)
    turn_diffs = np.diff(sorted_turns)
    gid_diffs = np.diff(sorted_gids_i32)
    # Violation = turn decreased within the same game
    mono_violation_mask = (turn_diffs < 0) & (gid_diffs == 0)
    # Count unique games with violations
    if np.any(mono_violation_mask):
        violation_positions = np.where(mono_violation_mask)[0]
        violation_gids = sorted_gids[violation_positions]
        mono_violations = len(np.unique(violation_gids))
    else:
        mono_violations = 0

    if outcome_issues > 0:
        state.add_warning(key, 'outcome_inconsistency',
                          f"{outcome_issues} (game,player) pairs with inconsistent outcomes")
    if mono_violations > 0:
        state.add_warning(key, 'turn_monotonicity',
                          f"{mono_violations} games with non-monotonic turns")
    shard_info['outcome_issues'] = outcome_issues

    # Accumulate game lengths for global stats
    state.game_lengths.extend(shard_game_lengths)

    # Check 9: Win rate counting (per-record, not per-game — unaffected by game_id scoping)
    p0_mask = player_indices == 0
    p1_mask = player_indices == 1
    p0_outcomes = outcomes[p0_mask]
    p1_outcomes = outcomes[p1_mask]
    state.p0_wins += int(np.sum(p0_outcomes > 0.5))
    state.p0_losses += int(np.sum(p0_outcomes < -0.5))
    state.p1_wins += int(np.sum(p1_outcomes > 0.5))
    state.p1_losses += int(np.sum(p1_outcomes < -0.5))
    state.draws += int(np.sum(np.abs(outcomes) <= 0.5))

    # Check 11: Feature min/max (sampled, update global)
    if len(sample_idx) > 0:
        smin = np.min(sampled_feats, axis=0).astype(np.float64)
        smax = np.max(sampled_feats, axis=0).astype(np.float64)
        np.minimum(state.feature_min, smin, out=state.feature_min)
        np.maximum(state.feature_max, smax, out=state.feature_max)
        state.dims_always_zero &= (smin == 0) & (smax == 0)

    state.total_records += record_count
    state.outcome_issues += shard_info.get('outcome_issues', 0)
    state.shard_index += 1
    state.shard_stats.append(shard_info)


def cross_shard_checks(state):
    """Run checks that require data from all shards."""
    # Check 6: Duplicate games by feature hash (cross-shard)
    # Two games in different shards with identical first-record features are suspect.
    hash_to_keys = defaultdict(list)
    for composite_key, h in state.game_first_hashes.items():
        hash_to_keys[h].append(composite_key)
    dup_groups = {h: keys for h, keys in hash_to_keys.items() if len(keys) > 1}
    n_dup_games = sum(len(keys) - 1 for keys in dup_groups.values())
    if n_dup_games > 0:
        for h, keys in list(dup_groups.items())[:5]:
            state.add_warning('cross-shard', 'duplicate_game_features',
                              f"hash={h[:12]}... in {len(keys)} shard/game pairs")

    # Outcome inconsistencies already accumulated per-shard
    return n_dup_games, state.outcome_issues


def _count_warnings_by_type(warnings):
    """Count warnings grouped by type."""
    counts = defaultdict(int)
    for w in warnings:
        counts[w['type']] += 1
    return dict(counts)


def _cap_warnings_by_type(warnings, max_per_type=50):
    """Keep up to max_per_type warnings per type, prioritizing critical types."""
    by_type = defaultdict(list)
    for w in warnings:
        by_type[w['type']].append(w)
    result = []
    for wtype, items in by_type.items():
        result.extend(items[:max_per_type])
    return result


def build_report(state, n_dup_games, outcome_issues, elapsed_sec):
    """Build the final JSON report."""
    n_games = state.total_games
    total_recs = state.total_records

    # Game length distribution
    counts = np.array(state.game_lengths, dtype=np.int64) if state.game_lengths else np.array([], dtype=np.int64)
    if len(counts) > 0:
        game_len_stats = {
            'mean': round(float(counts.mean()), 1),
            'median': int(np.median(counts)),
            'std': round(float(counts.std()), 1),
            'min': int(counts.min()),
            'max': int(counts.max()),
            'p95': int(np.percentile(counts, 95)),
            'p99': int(np.percentile(counts, 99)),
        }
    else:
        game_len_stats = {}

    # Win rate percentages
    p0_total = state.p0_wins + state.p0_losses
    p1_total = state.p1_wins + state.p1_losses

    # Feature ranges
    dims_negative = int(np.sum(state.feature_min < 0))
    dims_zero = int(np.sum(state.dims_always_zero))
    global_min = float(state.feature_min.min()) if not np.all(np.isinf(state.feature_min)) else 0.0
    global_max = float(state.feature_max.max()) if not np.all(np.isinf(state.feature_max)) else 0.0

    # Shards with errors
    error_shards = set(e['shard'] for e in state.errors)
    warning_shards = set(w['shard'] for w in state.warnings)

    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'bucket': BUCKET,
        'prefix': PREFIX,
        'elapsed_seconds': round(elapsed_sec, 1),
        'summary': {
            'total_shards': state.total_shards,
            'total_records': total_recs,
            'total_games': n_games,
            'total_bytes': state.total_bytes,
            'shards_with_errors': len(error_shards),
            'shards_with_warnings': len(warning_shards),
            'duplicate_games_by_features': n_dup_games,
            'outcome_inconsistencies': outcome_issues,
            'crc_ok': state.crc_ok,
            'crc_fail': state.crc_fail,
            'crc_skip': state.crc_skip,
            'nan_records': state.nan_records,
            'inf_records': state.inf_records,
        },
        'win_rates': {
            'p0_wins': state.p0_wins,
            'p0_losses': state.p0_losses,
            'p1_wins': state.p1_wins,
            'p1_losses': state.p1_losses,
            'draws': state.draws,
            'p0_win_pct': round(100.0 * state.p0_wins / max(p0_total, 1), 2),
            'p1_win_pct': round(100.0 * state.p1_wins / max(p1_total, 1), 2),
        },
        'game_length_stats': game_len_stats,
        'feature_ranges': {
            'global_min': round(global_min, 4),
            'global_max': round(global_max, 4),
            'dims_always_zero': dims_zero,
            'dims_negative': dims_negative,
        },
        'errors': state.errors,
        'warnings': _cap_warnings_by_type(state.warnings, max_per_type=50),
        'warning_count': len(state.warnings),
        'warning_counts_by_type': _count_warnings_by_type(state.warnings),
    }
    return report


def list_s3_shards(s3_client):
    """List all .bin files under PREFIX using paginator."""
    paginator = s3_client.get_paginator('list_objects_v2')
    shards = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith('.bin'):
                shards.append({'key': key, 'size': obj['Size']})
    return shards


def list_local_shards(directory):
    """List all .bin shard files in a local directory."""
    files = sorted(set(glob.glob(
        os.path.join(directory, '**', 'selfplay_t*_s*.bin'), recursive=True)))
    # Also grab any .bin files that don't follow the naming pattern
    others = sorted(set(glob.glob(
        os.path.join(directory, '**', '*.bin'), recursive=True)))
    all_files = sorted(set(files + others))
    shards = []
    for fp in all_files:
        size = os.path.getsize(fp)
        shards.append({'key': fp, 'size': size, 'local_path': fp})
    return shards


def main():
    parser = argparse.ArgumentParser(description='Audit self-play data integrity')
    parser.add_argument('--local-dir', type=str, default=None,
                        help='Audit local directory instead of S3')
    parser.add_argument('--sample-every', type=int, default=1,
                        help='Sample every Nth record for feature checks (1=all)')
    parser.add_argument('--output', type=str, default='audit_report.json',
                        help='Output JSON report path')
    parser.add_argument('--skip-crc', action='store_true',
                        help='Skip CRC32 verification')
    args = parser.parse_args()

    state = AuditState()
    t0 = time.time()

    if args.local_dir:
        # Local mode
        print(f"Auditing local directory: {args.local_dir}")
        shards = list_local_shards(args.local_dir)
        print(f"Found {len(shards)} .bin files")

        for i, shard in enumerate(shards):
            key = shard['key']
            size = shard['size']
            if size < HEADER_SIZE:
                state.add_warning(key, 'too_small', f"size={size}")
                state.total_shards += 1
                continue
            with open(shard['local_path'], 'rb') as f:
                data = f.read()
            print(f"  [{i+1}/{len(shards)}] {os.path.basename(key)} "
                  f"({size:,} bytes)...", end='', flush=True)
            audit_shard(data, key, size, state,
                        sample_every=args.sample_every,
                        skip_crc=args.skip_crc)
            print(f" {state.shard_stats[-1].get('records', 0)} records")
            del data
    else:
        # S3 mode
        try:
            import boto3
        except ImportError:
            print("ERROR: boto3 required for S3 mode. Install: pip install boto3")
            sys.exit(1)

        print(f"Auditing s3://{BUCKET}/{PREFIX}")
        s3 = boto3.client('s3', region_name=REGION)

        print("Listing shards...")
        shards = list_s3_shards(s3)
        print(f"Found {len(shards)} .bin files")

        total_size = sum(s['size'] for s in shards)
        print(f"Total data: {total_size / (1024**3):.1f} GB")

        for i, shard in enumerate(shards):
            key = shard['key']
            size = shard['size']
            if size < HEADER_SIZE:
                state.add_warning(key, 'too_small', f"size={size}")
                state.total_shards += 1
                continue

            # Stream the entire shard into memory (largest ~107MB, well within budget)
            resp = s3.get_object(Bucket=BUCKET, Key=key)
            data = resp['Body'].read()

            # Validate S3 read completeness
            if len(data) != size:
                state.add_error(key, 'truncated_s3_read',
                                f"S3 size={size} but read {len(data)} bytes")
                state.total_shards += 1
                del data
                continue

            basename = key.split('/')[-1]
            if (i + 1) % 500 == 0 or i == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(shards) - i - 1) / rate if rate > 0 else 0
                print(f"  [{i+1}/{len(shards)}] {basename} "
                      f"({size:,} bytes) "
                      f"games={state.total_games:,} records={state.total_records:,} "
                      f"[{elapsed:.0f}s elapsed, ~{eta:.0f}s remaining]",
                      flush=True)

            audit_shard(data, key, size, state,
                        sample_every=args.sample_every,
                        skip_crc=args.skip_crc)
            del data

    elapsed = time.time() - t0

    # Cross-shard checks
    print("\nRunning cross-shard checks...")
    n_dup_games, outcome_issues = cross_shard_checks(state)

    # Build and write report
    report = build_report(state, n_dup_games, outcome_issues, elapsed)

    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {args.output}")

    # Print human-readable summary
    s = report['summary']
    w = report['win_rates']
    g = report['game_length_stats']
    fr = report['feature_ranges']

    print("\n" + "=" * 60)
    print("SELF-PLAY DATA INTEGRITY AUDIT REPORT")
    print("=" * 60)
    print(f"  Timestamp:        {report['timestamp']}")
    print(f"  Elapsed:          {elapsed:.1f}s")
    print(f"  Shards:           {s['total_shards']:,}")
    print(f"  Records:          {s['total_records']:,}")
    print(f"  Games:            {s['total_games']:,}")
    print(f"  Data size:        {s['total_bytes'] / (1024**3):.1f} GB")
    print()
    print("  INTEGRITY:")
    print(f"    CRC OK:         {s['crc_ok']:,}")
    print(f"    CRC FAIL:       {s['crc_fail']:,}")
    print(f"    CRC skipped:    {s['crc_skip']:,}")
    print(f"    NaN records:    {s['nan_records']:,}")
    print(f"    Inf records:    {s['inf_records']:,}")
    print(f"    Dup games:      {s['duplicate_games_by_features']}")
    print(f"    Outcome issues: {s['outcome_inconsistencies']}")
    print(f"    Error shards:   {s['shards_with_errors']}")
    print(f"    Warning shards: {s['shards_with_warnings']}")
    if report.get('warning_counts_by_type'):
        print("    Warnings by type:")
        for wtype, wcount in sorted(report['warning_counts_by_type'].items(),
                                     key=lambda x: -x[1]):
            print(f"      {wtype}: {wcount:,}")
    print()
    print("  WIN RATES:")
    print(f"    P0 wins:  {w['p0_wins']:,}  losses: {w['p0_losses']:,}  "
          f"({w['p0_win_pct']:.1f}%)")
    print(f"    P1 wins:  {w['p1_wins']:,}  losses: {w['p1_losses']:,}  "
          f"({w['p1_win_pct']:.1f}%)")
    print(f"    Draws:    {w['draws']:,}")
    print()
    if g:
        print("  GAME LENGTH (records/game):")
        print(f"    Mean: {g['mean']}  Median: {g['median']}  "
              f"Std: {g['std']}  Min: {g['min']}  Max: {g['max']}")
        print(f"    P95: {g['p95']}  P99: {g['p99']}")
        print()
    print("  FEATURE RANGES:")
    print(f"    Global min: {fr['global_min']}  max: {fr['global_max']}")
    print(f"    Dims always zero: {fr['dims_always_zero']}/{FEATURE_DIM}")
    print(f"    Dims with negatives: {fr['dims_negative']}")
    print()

    # Overall verdict
    if s['crc_fail'] == 0 and s['nan_records'] == 0 and s['inf_records'] == 0 \
            and s['shards_with_errors'] == 0 and s['outcome_inconsistencies'] == 0:
        print("  VERDICT: PASS — Data integrity confirmed.")
    else:
        problems = []
        if s['crc_fail'] > 0:
            problems.append(f"{s['crc_fail']} CRC failures")
        if s['nan_records'] > 0:
            problems.append(f"{s['nan_records']} NaN records")
        if s['inf_records'] > 0:
            problems.append(f"{s['inf_records']} Inf records")
        if s['shards_with_errors'] > 0:
            problems.append(f"{s['shards_with_errors']} error shards")
        if s['outcome_inconsistencies'] > 0:
            problems.append(f"{s['outcome_inconsistencies']} outcome issues")
        print(f"  VERDICT: ISSUES FOUND — {', '.join(problems)}")

    print("=" * 60)


if __name__ == '__main__':
    main()
