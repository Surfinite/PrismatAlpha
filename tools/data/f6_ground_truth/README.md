# F6 Ground Truth Captures

This directory contains F6 state captures from the Prismata client's replay viewer.
These are the AS3 engine's ground truth states for regression testing.

## How to capture ground truth for a new replay

1. Open Prismata client (with SWF dev mode patch)
2. Load the replay in the replay viewer
3. Run: `python tools/capture_replay_states.py --output tools/data/f6_ground_truth/CODE.json`

Files are named by replay code (e.g., `xhzg6-ncYpY.json`).
Once captured, these files serve as permanent regression baselines.

## Usage

The `--regression` flag on `validate_engine_states.py` automatically checks this
directory for ground truth. If no `.json` files exist here, it falls back to
C++-only validation (equivalent to `--skip-f6`).

## File format

Each JSON file contains an array of per-turn state snapshots captured via the
F6 clipboard export mechanism (Shift+F6 for compact format). The state includes
`mergedDeck`, `gameState`, and `aiParameters` as exported by the Prismata client.
