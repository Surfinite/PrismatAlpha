"""
Binary shard loader for self-play training data.

Reads .bin files produced by C++ SelfPlayDataSink:
  - 64-byte header (magic, version, feature_dim, record_size, record_count, endian_check)
  - N x record_size bytes (features + outcome + game_id + turn_number + player_index + flags)
  - 4-byte CRC32 footer over all record bytes

Usage:
  python load_selfplay.py <directory>         # Print summary
  python load_selfplay.py <directory> --dump   # Print per-game details
"""

import glob
import os
import struct
import sys
import zlib

import numpy as np

# Binary format constants
MAGIC = 0x50534450  # "PSDP"
VERSION = 1
HEADER_SIZE = 64
FOOTER_SIZE = 4  # CRC32
ENDIAN_CHECK = 0x01020304
RECORD_COUNT_SENTINEL = 0xFFFFFFFFFFFFFFFF


def make_record_dtype(feature_dim):
    """Create numpy structured dtype for a single record."""
    return np.dtype([
        ('features', np.float32, (feature_dim,)),
        ('outcome', np.float32),
        ('game_id', np.uint32),
        ('turn_number', np.uint16),
        ('player_index', np.uint8),
        ('flags', np.uint8),
    ])


def parse_header(data):
    """Parse the 64-byte header. Returns dict of header fields."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Header too short: {len(data)} bytes (need {HEADER_SIZE})")

    # Unpack field by field (Q at offset 16 needs careful offset handling)
    magic = struct.unpack_from('<I', data, 0)[0]
    version = struct.unpack_from('<I', data, 4)[0]
    feature_dim = struct.unpack_from('<I', data, 8)[0]
    record_size = struct.unpack_from('<I', data, 12)[0]
    record_count = struct.unpack_from('<Q', data, 16)[0]
    endian_check = struct.unpack_from('<I', data, 24)[0]

    if magic != MAGIC:
        raise ValueError(f"Bad magic: 0x{magic:08X} (expected 0x{MAGIC:08X})")
    if version != VERSION:
        raise ValueError(f"Bad version: {version} (expected {VERSION})")
    if endian_check != ENDIAN_CHECK:
        raise ValueError(f"Bad endian check: 0x{endian_check:08X} (expected 0x{ENDIAN_CHECK:08X})")

    return {
        'magic': magic,
        'version': version,
        'feature_dim': feature_dim,
        'record_size': record_size,
        'record_count': record_count,
    }


def load_shard(filepath, validate_crc=True):
    """Load a single binary shard file.

    Returns:
        numpy structured array of records, or None if empty.
    """
    filesize = os.path.getsize(filepath)
    if filesize < HEADER_SIZE + FOOTER_SIZE:
        print(f"  WARNING: {os.path.basename(filepath)} too small ({filesize} bytes), skipping")
        return None

    with open(filepath, 'rb') as f:
        data = f.read()

    header = parse_header(data)
    feature_dim = header['feature_dim']
    record_size = header['record_size']
    record_count = header['record_count']

    # Validate record_size matches feature_dim
    expected_record_size = feature_dim * 4 + 4 + 4 + 2 + 1 + 1  # features + outcome + game_id + turn + player + flags
    if record_size != expected_record_size:
        raise ValueError(
            f"record_size mismatch: header says {record_size}, "
            f"computed {expected_record_size} from feature_dim={feature_dim}"
        )

    # Infer record count from file size if sentinel
    record_bytes_available = filesize - HEADER_SIZE - FOOTER_SIZE
    inferred_count = record_bytes_available // record_size

    if record_count == RECORD_COUNT_SENTINEL:
        record_count = inferred_count
    else:
        if record_count != inferred_count:
            print(f"  WARNING: {os.path.basename(filepath)}: header record_count={record_count} "
                  f"but file has space for {inferred_count}. Using header value.")

    if record_count == 0:
        print(f"  WARNING: {os.path.basename(filepath)} has 0 records, skipping")
        return None

    # Extract record bytes and footer
    record_data = data[HEADER_SIZE : HEADER_SIZE + record_count * record_size]
    footer_offset = HEADER_SIZE + record_count * record_size
    stored_crc = struct.unpack_from('<I', data, footer_offset)[0]

    # CRC32 validation
    if validate_crc:
        computed_crc = zlib.crc32(record_data) & 0xFFFFFFFF
        if computed_crc != stored_crc:
            raise ValueError(
                f"CRC32 mismatch in {os.path.basename(filepath)}: "
                f"stored=0x{stored_crc:08X}, computed=0x{computed_crc:08X}"
            )

    # Parse records via numpy
    dt = make_record_dtype(feature_dim)
    records = np.frombuffer(record_data, dtype=dt, count=record_count)

    return records


def load_all_shards(directory, validate_crc=True, max_records=0):
    """Load and concatenate all selfplay_t*_s*.bin files from a directory.

    Args:
        max_records: Stop loading after this many records (0=unlimited).

    Returns:
        numpy structured array of all records, or None if no data found.
    """
    # Search for shards recursively (handles AWS-downloaded dirs like 2026-*/run_*/)
    files = sorted(set(glob.glob(os.path.join(directory, '**', 'selfplay_t*_s*.bin'), recursive=True)))

    if not files:
        print(f"No selfplay shard files found in {directory}")
        return None

    # Report which run directories are being loaded
    run_dirs = sorted(set(os.path.basename(os.path.dirname(f)) for f in files))
    if any(d.startswith('run_') for d in run_dirs):
        print(f"  Found {len(files)} shards across {len(run_dirs)} run(s): {', '.join(run_dirs)}")

    # Assign each source directory a unique game_id block to prevent collisions
    # across runs (each C++ process starts game_id at 0)
    dir_to_offset = {}
    for fp in files:
        d = os.path.dirname(fp)
        if d not in dir_to_offset:
            dir_to_offset[d] = len(dir_to_offset) * (1 << 20)  # 1M IDs per directory

    all_records = []
    total_loaded = 0
    for fp in files:
        print(f"  Loading {os.path.basename(fp)}...")
        records = load_shard(fp, validate_crc=validate_crc)
        if records is not None:
            # Namespace game_ids by source directory
            offset = dir_to_offset[os.path.dirname(fp)]
            if offset > 0:
                records = records.copy()  # avoid modifying read-only buffer
                records['game_id'] = records['game_id'] + offset
            all_records.append(records)
            total_loaded += len(records)
            if max_records > 0 and total_loaded >= max_records:
                print(f"  Reached max_records limit ({max_records}), stopping load.")
                break

    if not all_records:
        print("No valid records found in any shard.")
        return None

    combined = np.concatenate(all_records)
    return combined


class MemmapShardIndex:
    """Pre-scan all shards to build an index of records for memory-mapped access.

    Reads only headers and game_ids (not full features) to build train/val split
    indices without loading the entire dataset into RAM.
    """

    def __init__(self, directory, subsample_every=1):
        files = sorted(set(glob.glob(
            os.path.join(directory, '**', 'selfplay_t*_s*.bin'), recursive=True)))
        if not files:
            raise FileNotFoundError(f"No selfplay shard files found in {directory}")

        # Assign each source directory a unique game_id block (same as load_all_shards)
        dir_to_offset = {}
        for fp in files:
            d = os.path.dirname(fp)
            if d not in dir_to_offset:
                dir_to_offset[d] = len(dir_to_offset) * (1 << 20)

        self.shards = []       # list of shard info dicts
        self.total_records = 0

        # Per-record lookup: (shard_idx, local_record_idx)
        shard_indices = []
        local_indices = []
        all_game_ids = []

        for fp in files:
            filesize = os.path.getsize(fp)
            if filesize < HEADER_SIZE + FOOTER_SIZE:
                continue

            with open(fp, 'rb') as f:
                header_data = f.read(HEADER_SIZE)
            header = parse_header(header_data)

            feature_dim = header['feature_dim']
            record_size = header['record_size']
            record_count = header['record_count']

            record_bytes_available = filesize - HEADER_SIZE - FOOTER_SIZE
            inferred_count = record_bytes_available // record_size
            if record_count == RECORD_COUNT_SENTINEL:
                record_count = inferred_count
            if record_count == 0:
                continue

            shard_idx = len(self.shards)
            self.shards.append({
                'path': fp,
                'feature_dim': feature_dim,
                'record_size': record_size,
                'record_count': record_count,
            })

            # Read only game_id field efficiently via strided dtype
            # game_id is at byte offset (feature_dim*4 + 4) within each record
            game_id_offset = feature_dim * 4 + 4  # after features + outcome
            gid_dtype = np.dtype({'names': ['game_id'],
                                  'formats': [np.uint32],
                                  'offsets': [game_id_offset],
                                  'itemsize': record_size})
            mm = np.memmap(fp, dtype=gid_dtype, mode='r',
                           offset=HEADER_SIZE, shape=(record_count,))
            gids = mm['game_id'].copy()
            del mm

            # Apply directory-based game_id offset
            offset = dir_to_offset[os.path.dirname(fp)]
            if offset > 0:
                gids = gids + offset

            n = len(gids)
            shard_indices.append(np.full(n, shard_idx, dtype=np.int32))
            local_indices.append(np.arange(n, dtype=np.int32))
            all_game_ids.append(gids)
            self.total_records += n

        if self.total_records == 0:
            raise FileNotFoundError(f"No valid records found in {directory}")

        self._shard_indices = np.concatenate(shard_indices)
        self._local_indices = np.concatenate(local_indices)
        self._game_ids = np.concatenate(all_game_ids)

        # Position subsampling
        if subsample_every > 1:
            original = self.total_records
            _, inverse = np.unique(self._game_ids, return_inverse=True)
            counts = np.zeros(inverse.max() + 1, dtype=np.int32)
            position_in_game = np.empty(len(self._game_ids), dtype=np.int32)
            for i in range(len(self._game_ids)):
                position_in_game[i] = counts[inverse[i]]
                counts[inverse[i]] += 1
            keep = (position_in_game % subsample_every) == 0
            self._shard_indices = self._shard_indices[keep]
            self._local_indices = self._local_indices[keep]
            self._game_ids = self._game_ids[keep]
            self.total_records = len(self._game_ids)
            print(f"  Subsampled: {original:,} -> {self.total_records:,} records "
                  f"(every {subsample_every}th position)")

        n_games = len(np.unique(self._game_ids))
        print(f"  Indexed {self.total_records:,} records from {n_games:,} games "
              f"across {len(self.shards)} shards")

    def resolve(self, global_idx):
        """Map a global record index to (shard_idx, local_record_idx)."""
        return int(self._shard_indices[global_idx]), int(self._local_indices[global_idx])

    def get_train_val_indices(self):
        """Split by game_id % 10 == 0 for val (same rule as existing code)."""
        val_mask = (self._game_ids % 10) == 0
        train_indices = np.where(~val_mask)[0]
        val_indices = np.where(val_mask)[0]
        return train_indices, val_indices

    def get_feature_dim(self):
        """Return feature dimension (consistent across all shards)."""
        return self.shards[0]['feature_dim']


class MemmapSelfPlayDataset:
    """PyTorch-compatible Dataset backed by memory-mapped shard files.

    Supports random access without loading all data into RAM.
    The OS pages data in/out as needed.

    Implements __len__ and __getitem__ for use with DataLoader.
    """

    def __init__(self, index, record_indices, label_smooth=0.95, num_units=161,
                 bce_mode=False):
        import torch  # lazy import
        self._torch = torch

        self.index = index
        self.record_indices = record_indices
        self.label_smooth = label_smooth
        self.num_units = num_units
        self.bce_mode = bce_mode

        # Open persistent memmap handles (OS manages actual memory)
        self._mmaps = []
        for shard in index.shards:
            mm = np.memmap(shard['path'], dtype=np.uint8, mode='r')
            self._mmaps.append(mm)

        # Pre-compute dtypes per shard
        self._dtypes = [make_record_dtype(s['feature_dim']) for s in index.shards]

    def __len__(self):
        return len(self.record_indices)

    def __getitem__(self, idx):
        torch = self._torch
        global_idx = self.record_indices[idx]
        shard_idx, local_idx = self.index.resolve(global_idx)

        shard = self.index.shards[shard_idx]
        offset = HEADER_SIZE + local_idx * shard['record_size']
        end = offset + shard['record_size']

        record_bytes = self._mmaps[shard_idx][offset:end]
        record = np.frombuffer(bytes(record_bytes), dtype=self._dtypes[shard_idx])

        features = torch.from_numpy(record['features'][0].copy())
        outcome = float(record['outcome'][0])

        # Apply label smoothing
        value = outcome * self.label_smooth

        # BCE mode: remap from [-smooth, +smooth] to [0, 1]
        if self.bce_mode:
            value = (value + 1.0) / 2.0

        buy_targets = torch.zeros(self.num_units)
        turn = float(record['turn_number'][0])
        has_policy = 0.0

        return (features,
                buy_targets,
                torch.tensor(value, dtype=torch.float32),
                torch.tensor(turn, dtype=torch.float32),
                torch.tensor(has_policy, dtype=torch.float32))


def print_summary(records):
    """Print a human-readable summary of the loaded records."""
    n = len(records)
    outcomes = records['outcome']
    game_ids = records['game_id']
    player_indices = records['player_index']
    features = records['features']

    unique_games = np.unique(game_ids)
    n_games = len(unique_games)
    n_wins = np.sum(outcomes > 0.5)
    n_losses = np.sum(outcomes < -0.5)
    n_draws = np.sum(np.abs(outcomes) < 0.5)
    n_p0 = np.sum(player_indices == 0)
    n_p1 = np.sum(player_indices == 1)

    print(f"\n=== Self-Play Data Summary ===")
    print(f"  Total records:   {n:,}")
    print(f"  Total games:     {n_games:,}")
    print(f"  Avg turns/game:  {n / max(n_games, 1):.1f}")
    print(f"  Outcomes:        +1: {n_wins:,} ({100*n_wins/n:.1f}%)  "
          f"-1: {n_losses:,} ({100*n_losses/n:.1f}%)  "
          f"0: {n_draws:,} ({100*n_draws/n:.1f}%)")
    print(f"  Player records:  P0: {n_p0:,}  P1: {n_p1:,}")
    print(f"  Game ID range:   [{game_ids.min()}, {game_ids.max()}]")

    # Feature stats
    feat_nonzero = np.count_nonzero(features, axis=1)
    has_nan = np.any(np.isnan(features))
    has_inf = np.any(np.isinf(features))
    print(f"  Feature dim:     {features.shape[1]}")
    print(f"  Avg non-zero features/record: {feat_nonzero.mean():.1f}")
    print(f"  NaN in features: {has_nan}")
    print(f"  Inf in features: {has_inf}")

    # Per-game outcome consistency check
    n_inconsistent = 0
    for gid in unique_games[:100]:  # check first 100 games
        mask = game_ids == gid
        game_outcomes = outcomes[mask]
        game_players = player_indices[mask]
        # All records for same player should have same outcome
        for p in [0, 1]:
            p_mask = game_players == p
            if p_mask.any():
                p_outcomes = game_outcomes[p_mask]
                if not np.all(p_outcomes == p_outcomes[0]):
                    n_inconsistent += 1

    if n_inconsistent > 0:
        print(f"  WARNING: {n_inconsistent} player-game groups with inconsistent outcomes!")
    else:
        print(f"  Outcome consistency: OK (checked {min(100, n_games)} games)")

    print()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <directory> [--dump] [--no-crc]")
        sys.exit(1)

    directory = sys.argv[1]
    dump = '--dump' in sys.argv
    validate_crc = '--no-crc' not in sys.argv

    records = load_all_shards(directory, validate_crc=validate_crc)
    if records is None:
        print("No data loaded.")
        sys.exit(1)

    print_summary(records)

    if dump:
        game_ids = records['game_id']
        unique_games = np.unique(game_ids)
        for gid in unique_games[:10]:  # first 10 games
            mask = game_ids == gid
            game_recs = records[mask]
            winner_str = "draw"
            if game_recs['outcome'][0] > 0.5:
                winner_str = f"P{game_recs['player_index'][0]} won"
            elif game_recs['outcome'][0] < -0.5:
                other = 1 - game_recs['player_index'][0]
                winner_str = f"P{other} won"
            print(f"  Game {gid}: {len(game_recs)} turns, {winner_str}")
            for r in game_recs:
                nz = np.count_nonzero(r['features'])
                print(f"    turn={r['turn_number']:3d} player={r['player_index']} "
                      f"outcome={r['outcome']:+.1f} flags={r['flags']:02x} "
                      f"nonzero_features={nz}")


if __name__ == '__main__':
    main()
