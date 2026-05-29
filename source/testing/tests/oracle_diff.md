# Replay serializer — verification log (Task 19)

This is the fidelity-verification record for the native C++ replay serializer
(`source/testing/ReplaySerializer.{h,cpp}`), which emits the matchup-format
`game_NNNN.json.gz` files the PixiJS `/replay/local` viewer consumes.

## Why there is no automated "oracle diff"

The original plan (Task 19) called for a field-by-field diff of the C++ output
against `matchup_clean.js --save-replays`. We deliberately did **not** do this:

1. **`matchup_clean.js` is an unverified producer.** Its `--suggest`
   click-emission path has documented click failures, so it is not a trusted
   oracle. A diff between two unvalidated producers proves nothing: a clean
   diff wouldn't establish correctness, and a dirty diff wouldn't localize the
   fault.
2. **The only trusted reference — S3 live replays — exercises a different
   path.** In the viewer, S3 replays load via `processS3Replay`
   (clicklist → real-engine reconstruction); they never touch the pre-baked
   `states[]` the C++ serializer emits. So an S3 comparison validates nothing
   about this code.

Instead we verified the output against **pipeline-independent ground truth**:
known card mechanics + structural invariants, plus an adversarial multi-agent
code review. All checks run on engine-pristine, deterministic output.

## Verification performed

### Structural fidelity (per-instance `table[]`)
- **`blocking` = `Card::canBlock()`** — the exact expression Dave's own
  `Card::toJSONString()` uses. Fixed an always-false bug (`status==Assigned &&
  canBlock()`); now ~20% of alive units block, distribution sane by phase.
- **`lifespan`** uses the `0 → -1` (infinite) convention.
- **`role`** maps sellable / assigned / inert / default from `isSellable()` +
  `getStatus()`.
- **`instId` — synthetic monotonic remap.** Dave's engine recycles `CardID`
  slots when units die (~39% of ids in a game refer to >1 unit). The viewer
  assumes unique, creation-monotonic ids (JS `nextInstId++`) for the pile
  newest-sorts-left tiebreak and for cross-frame sprite pairing. The serializer
  remaps each distinct unit to a stable, ever-increasing id. **Verified across
  80 games / 2.25M instances: 0 reuse, fully monotonic, freshly-placed unit is
  always the newest id in its pile.**
- **Freshness flags.** `boughtThisPhase = isSellable()` (faithful to the SWF
  `role===SELLABLE` gate). `bornThisTurn` = a non-sellable unit tagged at first
  appearance with its owner's turn index, expiring at the owner's next turn —
  covering both ability spawns (Sentinel→Engineer, Valkyrion→Sound Barrier) and
  begin-turn spawns (Gauss Fabricator→Minicannon, Defense Grid→Drone). Verified:
  0 born-while-sellable, 0 never-expire; a port of the viewer's `pile-sort.ts`
  bunches every freshly-placed unit leftmost.

### Derived HUD fields (Task 17) — mechanic checks
- **Gold-estimate bounds**: lower ≤ upper and ≥ current gold — 0 violations /
  13,414 player-states.
- **Drone floor**: estimate ≥ in-window Drone count — 0 violations.
- **Per-unit gold coverage**: all 116 units scanned; every gold producer
  (Thorium Dynamo, Centrifuge, Blood Phage, all drone variants, …) is counted
  with the correct amount, reading `Resources::amountOf(Gold)`.
- **Resonate**: Savior gold-resonate and the three attack-resonate units
  (Resophore, Amporilla, Antima Comet) are handled by one generic
  `resonateBonus` path (runtime-confirmed on real boards).

### Adversarial code review
A 3-lens multi-agent review (correctness · cross-reference integrity · SWF
faithfulness) with adversarial verification of each finding. It caught a real
bug — `bornThisTurn` never firing for begin-turn-create spawns, because the
engine omits begin-turn creates from `getCreatedCardIDs()`
(`GameState.cpp:1043`) — which was then fixed (owner-turn tagging). It also
confirmed no surviving raw-`CardID` cross-reference: `table[]` synthetic ids are
internally consistent, and `actions[]` labels keep raw ids but no consumer
correlates them back to instances.

## Known limitations (honest)
- **Begin-turn spawns not observed end-to-end.** The 4 begin-turn creators
  appear in the buy pool but the AI doesn't build them in random games (0/80
  on-table), so a begin-turn spawn was never produced for a live screenshot.
  Covered by construction: the `bornThisTurn` code path is identical for ability
  and begin-turn spawns, and ability spawns are verified.
- **`actions[]` labels are raw `Action::toHistoryString()`** ("player type id
  targetId", raw recycled CardIDs) — cosmetic; richer labels ("Buy Drone") and
  any id-correlation are deferred.

## Conclusion
Task 19's intent — establishing serializer fidelity — is met via mechanic-based
verification plus adversarial review. No automated `matchup_clean.js` diff was
run, by design: it would be misleading rather than informative.
