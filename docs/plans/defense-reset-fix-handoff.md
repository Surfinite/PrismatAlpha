# Defense Reset Bug Fix — Handoff Prompt for New Context

> **Instructions**: Paste this entire document into a new Claude Code context before starting
> any work on the PrismataAI codebase. This establishes what has been investigated, what the
> fix is, and critically — what you CAN and CANNOT modify or run.

---

## Background (already investigated — do NOT re-investigate)

A critical engine bug was discovered and fully investigated. The investigation is complete.
You are being brought in to **apply the fix and verify it**, not to re-investigate.

### The Bug (confirmed, root cause identified)

`source/engine/GameState.cpp`, function `beginPhase()`, lines 1289-1307.

A 19-line block of code resets ALL cards' statuses from `Assigned` (tapped) to `Default`/`Inert`
(untapped) at the start of the Defense phase. This defeats the engine's existing
`assignedBlocking`/`defaultBlocking` mechanism in `cardLibrary.jso`, allowing tapped Drones
(and all other tapped units) to incorrectly block during Defense.

In real Prismata: tapping a Drone for gold (ability use) means it CANNOT block that turn.
With this bug: tapping is free — you can tap AND block.

### Impact (already assessed — severity: DEGRADED)

- **All 722K self-play games** were generated with this bug (introduced Feb 13, self-play started Feb 15)
- **Bug is symmetric** — both self-play sides equally affected
- **~40-60% extra defense** per Defense phase from tapped cards incorrectly blocking
- **Feature vectors are NOT corrupted** — captured at Action phase start after proper reset
- **Game outcomes ARE distorted** — extra defense changes who wins/loses
- **Model learned variant Prismata** — general strategic knowledge is valid but defense
  evaluation is wrong (model doesn't know tap-or-block tradeoff)
- **Relative WR progression (3.6% → 51.9%) still valid** — symmetric bug doesn't invalidate
  relative comparisons
- **Only 2 units should block when tapped**: Fusion (`assignedBlocking: 1`) and Infestor
  (`assignedBlocking: 1`). All others have `assignedBlocking: 0`.

---

## The Fix (approved for implementation)

**Remove lines 1289-1307** from `source/engine/GameState.cpp` — the entire for-loop that
resets card statuses at the start of the Defense phase. Keep the attack check at lines 1309-1312.

The code to DELETE (everything between `case Phases::Defense: {` and the attack check):
```cpp
// Reset card statuses for the defending player before defense.
// Cards that used abilities in the previous action phase still have
// Assigned status (beginTurn hasn't run yet). In the live Prismata
// game, units can block during defense regardless of prior ability use.
for (const auto & cardID : getCardIDs(player))
{
    Card & card = _getCardByID(cardID);
    if (!card.isDead() && !card.isUnderConstruction() && !card.isDelayed())
    {
        if (card.getType().hasAbility() || card.getType().hasTargetAbility())
        {
            card.setStatus(CardStatus::Default);
        }
        else
        {
            card.setStatus(CardStatus::Inert);
        }
    }
}
```

The result should be:
```cpp
case Phases::Defense:
{
    if (getAttack(getEnemy(player)) == 0)
    {
        endPhase();
    }
    break;
}
```

### Why this is safe (already verified)

1. **The existing mechanism handles everything**: `Card::canBlock()` → `CardType::canBlock(assigned)` →
   checks `assignedBlocking` (from `cardLibrary.jso`). Drone has `assignedBlocking: 0`. This
   mechanism was always correct but was being bypassed by the buggy reset.

2. **Wipeout logic is unaffected**: `canWipeout()` and `blockWithAllBlockers()` are called
   BEFORE the buggy reset (during Action→Breach transition), so they already see the correct
   lower defense. Removing the reset doesn't change their behavior.

3. **The Confirm assert is safe**: `getAttack(player) < getTotalAvailableDefense(enemy)` at
   line 1404 holds because `!canWipeout` at Action end guarantees attack < defense, and nothing
   changes defense between Action end and Confirm.

4. **AI Defense players are safe**: `PartialPlayer_Defense_Default` checks `isLegal(ASSIGN_BLOCKER)`
   per card — tapped cards will correctly be skipped.

5. **Frozen cards unaffected**: `isFrozen()` checks `currentChill >= currentHealth`, independent
   of card status.

---

## What You CAN Do

1. **Apply the fix**: Remove lines 1289-1307 from `source/engine/GameState.cpp`
2. **Build the solution**: MSBuild the full solution `visualstudio/Prismata.sln`
   - Debug build: `//p:Configuration=Debug //p:Platform=x86`
   - Release build: `//p:Configuration=Release //p:Platform=x86`
   - Use `/t:Rebuild` (not `/t:Build`)
3. **Run a local tournament** (100-game minimum) to verify the fix:
   - Fixed `PrismatAlpha_AB` vs `OriginalHardestAI`
   - Compare WR against known baseline (51.9% with buggy engine)
   - Check that games complete without asserts/crashes
4. **Run the GUI** (`Prismata_GUI.exe`) to visually verify:
   - Tapped Drones should NOT have green borders during Defense
   - Untapped Drones should still show as legal blockers
5. **Read any file** in the codebase for verification
6. **Update CLAUDE.md** with bug documentation (under "Known Issues" or "Gotchas")

## What You CANNOT Do

1. **DO NOT modify `OriginalHardestAI` or any legacy player behavior** — these are the stable baseline
2. **DO NOT modify `cardLibrary.jso`** — the blocking config is correct as-is
3. **DO NOT modify the feature schema** (state_dim=1785 contract in `training/schema.json`)
4. **DO NOT modify the binary shard format** (`SelfPlayDataSink.h/cpp`)
5. **DO NOT deploy to S3** — do not run `aws/deploy_for_eval.sh` or upload anything to S3
   without explicit user approval
6. **DO NOT launch any cloud instances** (EC2, GCP, Azure) — no fleet changes
7. **DO NOT push to any git remote** without explicit user approval
8. **DO NOT delete or regenerate any self-play data**
9. **DO NOT modify `aws/watcher_config.json`** or any watcher files
10. **DO NOT modify any training code** (`training/*.py`) — the training pipeline is correct
11. **DO NOT run any cloud commands** (`aws`, `gcloud`, `az`) that create/modify resources
12. **DO NOT stop/unregister TheWatcher Task Scheduler job**

## Verification Checklist

After applying the fix:

- [ ] Build succeeds (Debug and/or Release x86)
- [ ] Run a 100-game tournament: note the WR (may go up, down, or stay similar)
- [ ] Visually verify in GUI that tapped Drones cannot block during Defense
- [ ] Check that no PRISMATA_ASSERT fires during the tournament
- [ ] Report: WR result, any crashes, any unexpected behavior

## Key Files Reference

| File | Role |
|------|------|
| `source/engine/GameState.cpp:1289-1307` | **THE BUG** — delete these lines |
| `source/engine/Card.cpp:484-512` | `canBlock()` — the correct mechanism |
| `source/engine/CardType.cpp:337-347` | `canBlock(assigned)` — checks `assignedBlocking` |
| `source/engine/CardType.h:12` | `CardStatus` enum: Default, Assigned, Inert |
| `bin/asset/config/cardLibrary.jso:3-11` | Drone: `assignedBlocking: 0` |
| `bin/asset/config/config.txt` | Tournament configs (check which ones have `"run":true`) |
| `source/ai/PartialPlayer_Defense_Default.cpp` | AI defense logic (uses `isLegal`) |

## Build Command

```bash
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI/visualstudio/Prismata.sln" \
  //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m
```

## Tournament Config

In `bin/asset/config/config.txt`, find the `NeuralAB_vs_Original` tournament (or similar)
and set `"run": true`. Ensure it uses:
- Player 1: `PrismatAlpha_AB` (neural net + Alpha-Beta)
- Player 2: `OriginalHardestAI` (baseline, legacy)
- Rounds: 100 minimum
- Run from `bin/` directory: `./Prismata_Testing.exe > log.txt 2>&1`

## Current Branch

The repo is on `feature/postgame-commentary`. The bug exists on ALL branches including `master`.
You can either:
- Apply the fix on the current branch (for quick testing)
- Create a new branch from master: `git checkout -b fix/defense-reset master`

The user prefers explicit branch management — ask before creating branches or switching.
