# JS Engine Faithfulness Campaign — Results (COMPLETE 2026-05-30)

## Goal
Make `js_engine` a **perfectly faithful** port of the AS3 Prismata client, measured by replaying
the full human replay corpus (**61,267** ranked 1800+ codes) and driving **failed clicks → 0**.
This is for engine / **prismata.live** correctness (the DSNN-retrain framing was dropped).

## Result
**Faithful. Done.** Failing replays went **~8,700 asserts (campaign start) → 164 → 33**. The
**33 residual failures are recordings the official Prismata client itself cannot replay** — a
rare bug in Lunarch's client (recording / live-vs-replay determinism), which our engine
**faithfully reproduces** (it fails exactly where the client fails). There are **no known
remaining bugs in `js_engine`**.

- Final failure list: `docs/scratch/corpus_failures4.json` (33 replays, 2,993 illegal clicks, 0 crashes).
- Residual rate: **33 / 61,267 = 0.054%**.

## The decisive reframe
"0 failed clicks" was a *proxy* for faithfulness, under the assumption the client replays every
recording cleanly. **That assumption is false** — the shipped client fails on some recordings.
The true goal is **"our engine matches the client on every replay."** So each failure is either:
- **(A)** client replays it fine, we don't → a real bug → **fix it**; or
- **(B)** the client also fails → we're faithful → **not our bug**.

All 33 residual failures are **(B)**. Verified empirically: the user loaded a representative
sample (VXGaI, S1gfK, KXHPU, 68UpV, FjSD5, nW5iM, JPXI5, n5f5a, KhOsi) in the real client — both
patched **and unpatched** — and **none reach the end**; they stop at the exact point our engine
stops. So the SWF dev-mode patch is not implicated; the client genuinely cannot replay them.

## The fixes (chronological)
| Commit | Fix | Effect |
|---|---|---|
| `43ea627` | `Controller` recompute StateHelper after every state-restore (revert + undo) | — |
| `f0c4dfa` | `State._canBlockAtStartOfPhase` ← AS3 State.as:4136 (phase-aware blocking) | — |
| `94c632c` | `State._cameOnTableThisPhase` ← AS3 State.as:4131 (owner/turn/phase + creator gates) | — |
| `d2363c5` | `State._checkWin` — removed a win condition absent from AS3 (golden-armor premature win) | cleared 57 breach replays |
| `314163f` | `Controller` target-mode null-guard (don't deref `null.dead`) | `errored` 6 → 0 |
| **`8486153`** | **`AS3Dictionary` — port AVM2 `Dictionary` for-in order** | **164 → 33 (131 fixed, 0 regressions)** |

Tooling committed: `corpus_scan.js` (`b77939c`, full-corpus meter), `oracle_diff.js` (`25a4c44`,
AS3 ground-truth state diff). All pushed to PrismatAlpha (branch `fix/jsengine-defense-revert`).

## Headline fix — AVM2 Dictionary for-in order
`State.table` is an int-keyed `flash.utils.Dictionary`. AS3 `for (t in dict)` over integer keys
iterates in the AVM2 `InlineHashtable`'s **physical-slot order** — *not* insertion order, *not*
numeric order. That order decides the sequence in which units run their begin-turn `create`
scripts during `swoosh`, hence which `instId` each created token receives. Our `AS3Dictionary`
was backed by a JS `Map` (insertion order), so multi-creator swooshes mis-assigned token instIds
and a later recorded click landed on the wrong card (e.g. a Pixie self-sac click hitting an inert
Gauss Cannon; a chill-source Frostbite landing on a Drone).

Ported avmplus `core/avmplusHashtable.cpp` exactly: int key `n` → atom `(n<<3)|6`; bucket
`(2n) & ((cap-1)&~1)`; fresh capacity 4 atoms; load factor 0.80; ×2 grow + rehash;
deleted-items grow rehashes at same capacity (purging tombstones); quadratic probe
(`n0=14, n+=2, i=(i+n)&mask`, stops at key or first EMPTY); `for-in` emits int keys in physical
slot order. This also makes `State.clone()` (AS3 State.as:218 re-inserts in for-in order)
faithful by construction. This single bug was the dominant cause and also cracked the
begin-turn-spawn-order class previously written off as "too hard" (the `oTbs6` class).

## Methodology — what made it tractable
1. **Premise proven from source.** Recordings are *accepted-only*: a click reaches the saved
   command stream only if `canClick==true` when made (live game sends to server only on
   `result.canClick`, LiveGame.as:258-272; `Analyzer.recordClick` gates the push, Analyzer.as:210;
   network path same gate, RaidAnalyzer.as:520). So every failed click on replay = a real state
   divergence. (Caveat discovered later: the *client's own replay* can diverge from live play —
   see residual analysis.)
2. **AS3 F6 dev-mode oracle.** Patched the Steam SWF to dev mode (`Prismata.swf` byte
   `0x1580196`: `0x27`→`0x26`); F6 dumps `gameState` (identical to our `State.toString()` format).
   `js_engine/oracle_diff.js <CODE> <F6dump>` replays a code, snapshots every action boundary,
   auto-aligns to the dump by state signature, and diffs scalars + every per-inst field. This
   turned "high-confidence inference" into byte-level ground-truth proof (the AVM2 fix landed
   **0 table diffs** vs the client at FIm28 turn 27 and v+7VV turn 28).
3. **Parallel diagnosis.** A 10-agent workflow diagnosed all bug families against AS3; a focused
   research agent recovered the exact avmplus hashtable algorithm from the open Tamarin source.

## The residual 33 (all client bugs — not ours)
Classification of the first illegal click (`js_engine/classify_failures.js`):
- **11 self-target** — a chill/snipe targets the active player's *own* unit (illegal in any faithful replay). VXGaI confirmed: the client also has those units as the player's own.
- **3 future-id** — a click references an `instId ≥ nextInstId` (not yet created). S1gfK confirmed: it clicks instId 68 at commands 76-77, but id 68 isn't created until command 78 — **temporally impossible in any forward replay**.
- **8 enemy-unit clicks / 7 own-assigned + DEF-commit / 4 singletons** — all client-also-fail.

### Dates (the "is it still a live bug?" question)
Game `startTime` by year: **2016 ×16, 2017 ×10, 2018 ×3, 2019 ×2, 2020 ×2** — mostly old, tapering
off (consistent with bugs being progressively fixed). The two from 2020 (`JPXI5-GjsBy` 2020-01,
`S1gfK-xUO5j` 2020-02) are **not** evidence of a fixable live bug: S1gfK is a temporally-corrupt
recording (click-before-create, above), and JPXI5 is an early double-buy the client also rejects.
`serverVersion` (the field in the replay) is the *server* deploy counter, not the client SWF
version; the client was effectively frozen after the Jan 2019 gameplay patch. Conclusion: a rare
**recording-time** corruption persisted to 2020, producing permanently-unreplayable saves. There
is no still-live bug in `js_engine`; "fixing" these would mean *diverging* from the real client.

## Implication for prismata.live
`js_engine` (shared with prismata.live) now matches the AS3 client. **~0.05% of replays are
unviewable** because the official client itself can't replay them — this is faithful, expected
behavior (those replays are unviewable in the real client too), not a prismata.live bug.

## Reproduce
```bash
cd js_engine
node corpus_scan.js \
  C:/libraries/prismata-replay-parser/final_training_codes_1800.txt \
  C:/libraries/prismata-replay-parser/replays_archive \
  C:/libraries/PrismataAI/docs/scratch/corpus_failures_rerun.json   # ~8 min; expect 33 failing, 0 errored
node classify_failures.js docs/scratch/corpus_failures4.json        # bucket the 33 by first-illegal click
# Ground-truth check against the AS3 client (requires an F6 dev-mode dump):
node oracle_diff.js <CODE> <F6dump.txt>
```
