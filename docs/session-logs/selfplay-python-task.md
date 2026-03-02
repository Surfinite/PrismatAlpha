# Self-Play Python Pipeline — Task Instructions

**Context:** You are implementing the Python side of self-play data generation. Another context is writing the C++ side in parallel. Read `CLAUDE_selfplay_worker_instructions.md` for the full spec — this file is your quick-start.

**Tracking file:** Update `CLAUDE_selfplay_python_progress.md` as you work. Create it immediately with a checklist. Another context or the user will check this file for status.

---

## What to do (in order)

### 1. Create your tracking file `CLAUDE_selfplay_python_progress.md`
Mark each item as you go: DONE / IN PROGRESS / BLOCKED.

### 2. Create `training/load_selfplay.py` — Binary shard loader

Reads the binary format produced by C++ `SelfPlayDataSink`:

**Header (64 bytes):**
```
uint32 magic=0x50534450, uint32 version=1, uint32 feature_dim=1785,
uint32 record_size=7152, uint64 record_count (or 0xFFFFFFFFFFFFFFFF sentinel),
uint32 endian_check=0x01020304, uint8[36] reserved
```

**Per record (7152 bytes):**
```
float32[1785] features, float32 outcome (+1/-1/0), uint32 game_id,
uint16 turn_number, uint8 player_index, uint8 flags (bit 0 = draw)
```

**Footer:** uint32 CRC32 over all record bytes.

Requirements:
- Parse header, validate magic/version/endianness
- If record_count is sentinel, infer from file size: `(filesize - 64 - 4) / record_size`
- Validate CRC32 via `zlib.crc32()`
- Parse records using numpy `np.frombuffer` with structured dtype
- `load_all_shards(directory)` — loads + concatenates all `selfplay_t*_s*.bin` files
- Print summary: total records, games, draws, outcome distribution

### 3. Create a synthetic test binary

Don't wait for C++ output. Write a small Python script that generates a fake .bin file matching the format spec (e.g., 10 games, 30 turns each, random features, known outcomes). Use this to validate your loader works before real data exists.

### 4. Modify `training/train.py`

Add CLI arguments:
- `--selfplay-dir PATH` — directory with binary shards
- `--expert-weight FLOAT` (default 0.5) — fraction from expert replays

When `--selfplay-dir` is provided:
1. Load via `load_selfplay.load_all_shards()`
2. Split train/val **by game_id** (`game_id % 10 == 0` for val) — CRITICAL, do NOT split by record (causes data leakage, see CLAUDE.md section 23)
3. If `--expert-weight > 0`, also load `training/data/train.pt` and mix
4. Train as normal (both value + policy heads)

### 5. Test the full pipeline with synthetic data

- Generate synthetic .bin
- Load with `load_selfplay.py` — verify CRC, record counts, outcomes
- Run `train.py --selfplay-dir <synthetic_dir> --epochs 50 --lr 1e-3 --dropout 0.0`
- Verify it overfits (train loss → ~0, accuracy → 95%+)

---

## Key gotchas
- **Split by game_id, NOT by record.** All records from same game share same outcome. Per-record split = massive leakage.
- **tanh is NOT in the PyTorch model.** Raw logits during training. `tanhf()` at C++ inference time only.
- **Outcome values:** +1.0 (active player won), -1.0 (lost), 0.0 (draw). Same convention as existing `vectorize.py`.
- **feature_dim = 1785** (161 units x 11 features + 14 global). Schema in `training/schema.json`.
- **Existing training data:** `training/data/train.pt` and `val.pt` (expert replays, 226K + 25K examples).
- **Python 3.13, PyTorch 2.10.0+cpu** — already installed and working.

## Environment
```bash
cd c:/libraries/PrismataAI
python training/load_selfplay.py <dir>       # test loader
python training/train.py --selfplay-dir <dir> # train with self-play data
```
