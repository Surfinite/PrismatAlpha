"""
Generate synthetic self-play binary data for testing the loader and training pipeline.

Creates fake .bin files matching the SelfPlayDataSink binary format:
  - 64-byte header
  - N records of 7152 bytes each
  - 4-byte CRC32 footer

Usage:
  python generate_synthetic_selfplay.py [output_dir] [--games N] [--min-turns T] [--max-turns T]
"""

import os
import struct
import sys
import zlib

import numpy as np

# Format constants (must match SelfPlayDataSink)
MAGIC = 0x50534450
VERSION = 1
HEADER_SIZE = 64
ENDIAN_CHECK = 0x01020304
FEATURE_DIM = 1785
RECORD_SIZE = FEATURE_DIM * 4 + 4 + 4 + 2 + 1 + 1  # 7152


def write_header(f, record_count):
    """Write the 64-byte header."""
    buf = bytearray(HEADER_SIZE)
    struct.pack_into('<I', buf, 0, MAGIC)
    struct.pack_into('<I', buf, 4, VERSION)
    struct.pack_into('<I', buf, 8, FEATURE_DIM)
    struct.pack_into('<I', buf, 12, RECORD_SIZE)
    struct.pack_into('<Q', buf, 16, record_count)
    struct.pack_into('<I', buf, 24, ENDIAN_CHECK)
    # bytes 28-63 reserved (zeros)
    f.write(buf)


def write_record(f, features, outcome, game_id, turn_number, player_index, flags):
    """Write a single record. Returns the raw bytes written (for CRC)."""
    buf = bytearray(RECORD_SIZE)
    # Features: float32[1785]
    feat_bytes = np.asarray(features, dtype=np.float32).tobytes()
    buf[0:len(feat_bytes)] = feat_bytes
    offset = len(feat_bytes)
    struct.pack_into('<f', buf, offset, outcome)
    offset += 4
    struct.pack_into('<I', buf, offset, game_id)
    offset += 4
    struct.pack_into('<H', buf, offset, turn_number)
    offset += 2
    buf[offset] = player_index
    offset += 1
    buf[offset] = flags
    f.write(buf)
    return bytes(buf)


def generate_synthetic_features(rng, turn, player, feature_dim=FEATURE_DIM):
    """Generate somewhat realistic synthetic features.

    Most features are 0 (sparse). A few unit slots get small counts.
    Global features (last 14) get normalized values.
    """
    features = np.zeros(feature_dim, dtype=np.float32)

    # Simulate some units: first few slots (Drone=0, Engineer=1, etc.)
    # Each unit has 11 features: p0_ready, p0_exhausted, p0_constructing, p0_blocking,
    #                            p1_ready, p1_exhausted, p1_constructing, p1_blocking,
    #                            p0_supply, p1_supply, in_card_set
    for u in range(min(20, feature_dim // 11)):  # first 20 unit types
        base = u * 11
        if base + 10 >= feature_dim:
            break
        # Random small counts for ready/exhausted
        features[base + 0] = rng.integers(0, 4)  # p0_ready
        features[base + 4] = rng.integers(0, 4)  # p1_ready
        # Supply (e.g., 10 for normal, 4 for rare)
        features[base + 8] = rng.integers(0, 11)  # p0_supply
        features[base + 9] = rng.integers(0, 11)  # p1_supply
        # In card set
        features[base + 10] = 1.0 if u < 11 else float(rng.random() > 0.5)

    # Global features (last 14 slots): clamp-divide normalized
    global_base = feature_dim - 14
    features[global_base + 0] = min(rng.integers(0, 20) / 20.0, 1.0)   # p0_gold
    features[global_base + 1] = min(rng.integers(0, 5) / 5.0, 1.0)     # p0_blue
    features[global_base + 2] = min(rng.integers(0, 5) / 5.0, 1.0)     # p0_red
    features[global_base + 3] = min(rng.integers(0, 15) / 15.0, 1.0)   # p0_green
    features[global_base + 4] = min(rng.integers(0, 10) / 10.0, 1.0)   # p0_energy
    features[global_base + 5] = min(rng.integers(0, 25) / 25.0, 1.0)   # p0_attack
    features[global_base + 6] = min(rng.integers(0, 20) / 20.0, 1.0)   # p1_gold
    features[global_base + 7] = min(rng.integers(0, 5) / 5.0, 1.0)     # p1_blue
    features[global_base + 8] = min(rng.integers(0, 5) / 5.0, 1.0)     # p1_red
    features[global_base + 9] = min(rng.integers(0, 15) / 15.0, 1.0)   # p1_green
    features[global_base + 10] = min(rng.integers(0, 10) / 10.0, 1.0)  # p1_energy
    features[global_base + 11] = min(rng.integers(0, 25) / 25.0, 1.0)  # p1_attack
    features[global_base + 12] = min(turn / 30.0, 1.0)                 # turn_number
    features[global_base + 13] = float(player)                          # active_player

    return features


def generate_shard(output_dir, thread_index, shard_index, num_games, min_turns, max_turns, seed=42):
    """Generate a single binary shard with synthetic data."""
    rng = np.random.default_rng(seed + thread_index * 1000 + shard_index)

    filename = f"selfplay_t{thread_index:02d}_s{shard_index:03d}.bin"
    filepath = os.path.join(output_dir, filename)

    # Pre-generate all records to know the count
    all_records = []
    game_id = thread_index * 100000  # offset by thread to ensure unique IDs

    for g in range(num_games):
        turns = rng.integers(min_turns, max_turns + 1)
        # Decide winner: P0 or P1, or rarely draw
        r = rng.random()
        if r < 0.48:
            winner = 0
        elif r < 0.96:
            winner = 1
        else:
            winner = 3  # draw (Player_None)

        for t in range(turns):
            player = t % 2  # alternating
            features = generate_synthetic_features(rng, t, player)

            if winner == 3:
                outcome = 0.0
                flags = 0x01
            elif winner == player:
                outcome = 1.0
                flags = 0x00
            else:
                outcome = -1.0
                flags = 0x00

            all_records.append((features, outcome, game_id, t, player, flags))

        game_id += 1

    record_count = len(all_records)

    with open(filepath, 'wb') as f:
        write_header(f, record_count)

        crc = 0
        for features, outcome, gid, turn, player, flags in all_records:
            raw = write_record(f, features, outcome, gid, turn, player, flags)
            crc = zlib.crc32(raw, crc) & 0xFFFFFFFF

        # Write CRC32 footer
        f.write(struct.pack('<I', crc))

    expected_size = HEADER_SIZE + record_count * RECORD_SIZE + 4
    actual_size = os.path.getsize(filepath)
    assert actual_size == expected_size, f"Size mismatch: {actual_size} != {expected_size}"

    return filepath, record_count, num_games


def main():
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "c:/libraries/PrismataAI/training/data/selfplay_synthetic"
    num_games = 10
    min_turns = 20
    max_turns = 60

    # Parse optional args
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--games' and i + 1 < len(args):
            num_games = int(args[i + 1])
            i += 2
        elif args[i] == '--min-turns' and i + 1 < len(args):
            min_turns = int(args[i + 1])
            i += 2
        elif args[i] == '--max-turns' and i + 1 < len(args):
            max_turns = int(args[i + 1])
            i += 2
        else:
            i += 1

    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating synthetic self-play data:")
    print(f"  Output:    {output_dir}")
    print(f"  Games:     {num_games}")
    print(f"  Turns:     {min_turns}-{max_turns}")
    print(f"  Features:  {FEATURE_DIM}")
    print(f"  Record:    {RECORD_SIZE} bytes")

    # Generate one shard (thread 0, shard 0)
    filepath, n_records, n_games = generate_shard(
        output_dir, thread_index=0, shard_index=0,
        num_games=num_games, min_turns=min_turns, max_turns=max_turns
    )

    file_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"\n  Created: {filepath}")
    print(f"  Records: {n_records}")
    print(f"  Games:   {n_games}")
    print(f"  Size:    {file_mb:.2f} MB")
    print(f"\nDone. Test with: python training/load_selfplay.py {output_dir}")


if __name__ == '__main__':
    main()
