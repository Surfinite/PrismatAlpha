# Handoff → prismata-ladder: update the site engine bundle with the faithfulness fixes

**From:** PrismataAI repo (`c:\libraries\PrismataAI`), branch `fix/jsengine-defense-revert`, 2026-05-30.
**For:** a prismata-ladder workspace session that will update the site's engine bundle.
**TL;DR:** 6 faithfulness fixes landed in `js_engine` (3 core engine files changed). They make the
engine match the real AS3 client (fixed ~131 mis-replayed games across the human corpus). The site
needs them — but the deployed bundle was hand-edited in place, so **do NOT blindly rebuild**;
reconcile carefully and re-verify Puzzle + Live before shipping.

---

## 0. Critical constraint (read first)
The site's engine bundle (`prismata-engine.js`) was historically **edited in place** on the site,
and only **mostly backfilled** into `js_engine` here. Just before this work we diffed the two:
divergences were **small but non-zero**, so the **"don't rebuild the engine bundle from scratch"
rule is still in effect** — a clean rebuild from `js_engine` would clobber the site-only edits
(the bits that make Puzzle/Live work) that were never backfilled.

So this is a **reconcile**, not a rebuild: get the 3 changed files' fixes into the bundle while
preserving the site-only edits.

---

## 1. What changed in the engine (the delta to port)
Branch `fix/jsengine-defense-revert`, commits not in `master`:

| Commit | File | What | Lines |
|---|---|---|---|
| `43ea627` | `Controller.js` | recompute StateHelper after every state-restore (revert/undo/end-defense/enter-confirm) | part of +28 |
| `314163f` | `Controller.js` | null-guard the target-mode click path (don't deref `null.dead` → no crash) | part of +28 |
| `f0c4dfa` | `State.js` | `_canBlockAtStartOfPhase` — phase-aware "is currently blocking" (was a wrong rewrite) | part of +33 |
| `94c632c` | `State.js` | `_cameOnTableThisPhase` — owner/turn/phase + creatorId gates (was `role===SELLABLE`) | part of +33 |
| `d2363c5` | `State.js` | `_checkWin` — removed a bogus "opponent has only under-construction units → win" | part of +33 |
| **`8486153`** | **`AS3Dictionary.js`** | **port AVM2 `Dictionary` for-in order** (begin-turn token instIds) — the big one | +194 / −74 |

Tools also added (`corpus_scan.js`, `oracle_diff.js`, `classify_failures.js`) — **NOT part of the
bundle**, ignore them for the site update.

**Only 3 bundle files changed: `AS3Dictionary.js`, `Controller.js`, `State.js`.** Everything else
in the bundle is untouched.

Full background: `docs/jsengine-faithfulness-results.md`.

---

## 2. How the bundle is built (so you know what maps where)
`js_engine/build_viewer_bundle.js` concatenates these files, in this order, into the site:
```
C.js, Mana.js, Rndm.js, SacDescription.js, CreateDescription.js, Script.js, Card.js, Inst.js,
AS3Dictionary.js, Click.js, ClickResult.js, EndTurnObject.js, Order.js, StateHelper.js,
State.js, Controller.js, Analyzer.js, replay_exporter.js
   → <ladder>/<ladder>-site/public/js/prismata-engine.js
```
So in the deployed `prismata-engine.js`, the `AS3Dictionary` / `State` / `Controller` sections are
where these fixes go.

---

## 3. The headline change & its risk — read before touching `AS3Dictionary`
`State.table` is an int-keyed `flash.utils.Dictionary`. AS3 `for (t in dict)` over integer keys
iterates in the **AVM2 hashtable's physical-slot order** — *not* insertion order, *not* numeric
order. That order decides which `instId` each begin-turn-created token gets. The old `AS3Dictionary`
used a JS `Map` (**insertion order**), so multi-creator begin-turn swooshes mis-assigned token
instIds and the wrong unit ended up at a given id (e.g. a Pixie and a Gauss Cannon swapped ids).
The new file ports the avmplus hashtable exactly.

**Why this matters for the site:** the change alters **iteration order everywhere the unit table is
walked** (begin-turn creates, and any `table.forIn/forEach/keys/values`). Consequences:
- **Replay viewer / spectating:** strictly *more* faithful — token instIds now match the real
  client, so replays that previously rendered a wrong/desynced unit now match. This is the win.
- **Puzzle & Live:** these are the regression risk. Any Puzzle/Live logic that **relies on the old
  insertion (≈ascending) iteration order** — e.g. assuming `table.keys()`/`forEach` yields units
  in ascending-instId order, or pinning to a specific token id — could behave differently. The new
  order is the *correct* (client-matching) one, but if site code was written against the old order,
  verify it.

**API compat note:** `keys()` / `values()` / `entries()` now return **arrays** (were Map
iterators). `for...of` and spread are unaffected; but flag any site code that calls `.next()` on
them or relies on single-use-iterator semantics.

The new `AS3Dictionary` public API is otherwise identical: `set/get/has/delete`, `length` getter,
`keys/values/entries/forIn/forEach/toObject`, static `fromObject/fromEntries`.

---

## 4. Per-file porting instructions

### 4a. `AS3Dictionary.js` — replace wholesale (verify no site edits first)
This is a near-total rewrite and the class is pure low-level infra (no game/UI/site logic), so the
site bundle almost certainly has **no** site-specific edits here. **Verify** (diff the bundle's
`AS3Dictionary` section against the *pre-fix* `js_engine/AS3Dictionary.js`); if it's clean (== old
Map-based version), **replace the whole class** with the new `js_engine/AS3Dictionary.js` (commit
`8486153`). If the site *did* edit it, port those edits onto the new file (unlikely, but check).

### 4b. `Controller.js` — apply 2 surgical hunks
These are small and localized; apply into the bundle's `Controller` section (preserving any
surrounding site edits):

**(i) target-mode null-guard** — in `processClick`, right after `inst = this.state.instIdToInst(id);`
in the `inTargetMode` branch, before the `instSatisfiesConditionWhy(...)` call:
```js
                inst = this.state.instIdToInst(id);
+               if (inst === null || inst === undefined) {
+                   return new ClickResult(actuallyDoClick, false);
+               }
                tempReason = this.instSatisfiesConditionWhy(inst, this.targetSources[0].card.condition);
```

**(ii) StateHelper recompute after state-restore** — there are **4 sites** where the old code had
`/* STUB: UI-only — state.dispatch(SEND_LOADSTATE) */` after restoring `this.state` (the
`MOVE_END_DEFENSE`, `MOVE_ENTER_CONFIRM`, `ORDER_REVERT` cases, and the revert branch in
`processMoveOrRevert`). Each must now recompute the helper:
```js
                this.state = <the restored state>;
-               /* STUB: UI-only — state.dispatch(SEND_LOADSTATE) */
+               this.state.helper.update(this.state);
```
(AS3 dispatched `SEND_LOADSTATE` which recomputed the StateHelper; the headless port dropped it as
"UI-only", leaving `partiallyDamagedInst` stale → undo/revert mis-allocated defense damage.)

### 4c. `State.js` — apply 3 surgical hunks
Replace the bodies of these three methods in the bundle's `State` section with the corrected
versions (commits `f0c4dfa`, `94c632c`, `d2363c5`):

**`_cameOnTableThisPhase`** →
```js
        return (inst.owner === this.turn && this.phase === C.PHASE_ACTION && inst.role === C.ROLE_SELLABLE)
            || inst.creatorIdFromBuyOrAbility >= 0
            || inst.creatorIdFromBeginTurn >= 0;
```

**`_canBlockAtStartOfPhase`** →
```js
        if (this.phase === C.PHASE_DEFENSE || this.phase === C.PHASE_CONFIRM) {
            return inst.blocking;
        }
        return inst.blocking || inst.disruptDamage > 0;
```

**`_checkWin`** — remove the bogus win condition (delete this block; do NOT replace it with a return
`this.turn`):
```js
-           // Opponent has only under-construction units — cannot defend or attack
-           if (this.helper.oppAllUnitsTotal > 0 && this.helper.oppNonInvTotal === 0) {
-               return this.turn;
-           }
```
(leave the surrounding `allOppUnitsDoomed → return this.turn` and the final `return C.COLOR_NONE`.)

For the exact diffs: `git show <commit>` for each, or `git diff master..HEAD -- js_engine/State.js
js_engine/Controller.js` on this branch.

---

## 5. Recommended procedure for the site update
Two viable paths — pick based on how confident you are in cataloguing the site-only edits:

**Path A — surgical patch (lowest regression risk; recommended for the immediate ship).**
1. In the deployed `prismata-engine.js`, diff the `AS3Dictionary` / `State` / `Controller` sections
   against the *pre-fix* `js_engine` versions to confirm the site-only edits (the "small but
   non-zero" delta) live elsewhere / don't collide with these methods.
2. Apply §4 changes directly into the bundle, preserving everything else.
3. Verify (§6). Ship.

**Path B — backfill then rebuild (cleaner long-term; kills the divergence).**
1. Catalogue the site-only bundle edits and **backfill them into `js_engine`** so `js_engine`
   == bundle behavior. (This is the "don't rebuild" rule's actual fix — once the divergence is 0,
   rebuilds are safe.)
2. Rebuild via `node js_engine/build_viewer_bundle.js` (now includes both the site edits and the 6
   fixes).
3. Verify (§6). Ship. Going forward, the bundle can be rebuilt from `js_engine` cleanly.

---

## 6. Verification checklist (don't ship without this)
- **Puzzle:** run the puzzle features end-to-end. They exercise interactive solving + the table /
  begin-turn logic — the most likely place an iteration-order assumption hides.
- **Live spectating:** confirm live games still track/render correctly (the engine drives the
  state used by the viewer).
- **Replay viewer:** spot-check a few replays render correctly; the AVM2 order change should make
  previously-desynced ones *better*, not worse.
- **Faithfulness (optional but decisive):** point `js_engine/corpus_scan.js` at the corpus — the
  current engine yields **33 failing / 61,267** (down from 164). If the site bundle yields the same
  33 (and 0 crashes), it has the fixes and matches `js_engine`. The 33 residual are recordings the
  **real client can't replay either** (a client bug we faithfully reproduce — do NOT try to "fix"
  them; ~0.05% of replays, unviewable in the official client too). See
  `docs/jsengine-faithfulness-results.md`.
- **Ground-truth diff (if a specific replay looks off):** `node js_engine/oracle_diff.js <CODE>
  <F6dump>` against an AS3 F6 dev-mode dump pinpoints any per-unit divergence.

---

## 7. Pointers
- Engine repo: `c:\libraries\PrismataAI`, branch `fix/jsengine-defense-revert` (pushed to PrismatAlpha).
- Results / full write-up: `docs/jsengine-faithfulness-results.md`.
- Fix commits: `43ea627`, `f0c4dfa`, `94c632c`, `d2363c5`, `314163f`, **`8486153`**.
- Bundle builder + file list: `js_engine/build_viewer_bundle.js`.
- Tools (not bundled): `js_engine/corpus_scan.js`, `js_engine/oracle_diff.js`, `js_engine/classify_failures.js`.
