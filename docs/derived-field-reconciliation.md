# Derived-Field Reconciliation — site-bundle authority

Per spec [2026-05-28-cpp-replay-export-pixijs-viewer-design.md](superpowers/specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md).

**Authority:** the shipped `prismata-ladder-site/public/js/prismata-engine.js`, hand-divergent from `js_engine/build_viewer_bundle.js`. Where local and shipped disagree, **shipped wins**.

**Date built:** 2026-05-28 against shipped-bundle blob sha `182b737eb8fa3dc54a881649cfe4b72ebbe77450` and PrismataAI master `0f837e0e86094264bf9daed2fed46eb45038b2f6`.

## Ranked-play scope (2026-05-28)

DSNN is trained on the canonical ranked-play card list at
`c:/libraries/PrismataAI-dave-master/bin/asset/config/cardLibrary.jso`. Two non-ranked
units come up in this reconciliation doc — implications for C++ implementation:

- **Cryo Kronus** (the `+999` `oppDisruptPotential` hardcode at bundle line 2914 / local
  StateHelper.js:423) is **NOT in ranked**. The hardcode is keyed on a literal
  `cardName === 'Cryo Kronus'` match; no other ranked disrupt unit triggers it
  (the seven ranked disrupt units are Cryo Ray, Nivo Charge, Vai Mauronax, Tatsu
  Nullifier, Shiver Yeti, Frostbite, Iceblade Golem — none name-match). **C++ may
  safely skip the +999 path; it is dead code for any DSNN-relevant replay.**
- **Robo Santa** (the example for `bornThisTurn`) is **NOT in ranked**, but the
  `bornThisTurn` mechanic itself IS load-bearing — four ranked units use
  `beginOwnTurnScript: {create: ...}`: Gauss Fabricator (Minicannon), Defense Grid
  (Drone), Oxide Mixer (Pixie), Frost Brooder (Screech Blast). **The DISAGREE-material
  finding for `bornThisTurn` must be implemented in C++; Robo Santa was just an
  illustrative example.**

If other Phase 3 special cases turn out to be keyed on non-ranked unit names, the same
rule applies: verify against `cardLibrary.jso` first; skip if dead.

---

## Summary

| Field | Status | C++ source-of-truth |
|---|---|---|
| `incomingAttack` | AGREE | port from `local StateHelper.js` / `replay_exporter.js:227`; read `oppMana.attack` integer directly |
| `maxAttack` | AGREE | port from `local StateHelper.js:148,161,195,235,253,446`; phase-split + resonate bonus |
| `maxDisrupt` | AGREE | port from `local StateHelper.js:172`; defense-phase only, `card.disruptPotential` |
| `maxSnipers` | AGREE | port from `local StateHelper.js:175`; defense-phase only, double-gate (SNIPE + potentiallyMoreAttack) |
| `oppAttackPotential` | AGREE | port from `local StateHelper.js:388,401,498`; no phase split, resonate bonus |
| `oppDisruptPotential` | AGREE | port from `local StateHelper.js:414`. Skip Cryo Kronus +999 hardcode (line 423) — Cryo Kronus not in ranked deck. |
| `oppSnipers` | AGREE | port from `local StateHelper.js:418`; double-gate, internal reduction not exported |
| `whiteGoldEstimate` | AGREE | port from `local replay_exporter.js:115-218` (inline closure); both bounds + current gold |
| `blackGoldEstimate` | AGREE | same as whiteGoldEstimate, player=1 |
| `boughtThisPhase` | AGREE | port from `local replay_exporter.js:61`; `creatorIdFromBuyOrAbility >= 0`, always emit |
| `bornThisTurn` | DISAGREE (material) | implement from `prismata-engine.js:7944` ONLY; emit when `creatorIdFromBeginTurn >= 0` |

**Counts: 10 AGREE, 1 DISAGREE (material), 0 BUNDLE-ONLY, 0 LOCAL-ONLY.**

> The single material disagreement (`bornThisTurn`) is low-complexity to fix: C++ already
> tracks the equivalent of `creatorIdFromBeginTurn` (units spawned by `beginOwnTurnScript`);
> it just needs to emit the field. The bundle emits it always; C++ should do the same.

---

## Per-field detail

### incomingAttack

**Status:** AGREE

**Shipped** (`prismata-engine.js:8110`):
```javascript
incomingAttack: state.oppMana ? state.oppMana.attack : 0,
// oppMana getter (lines 3365–3367): turn===WHITE ? blackMana : whiteMana
// Mana.attack getter (line 567): return this.pool[C.MANA_A]  (the 6th mana slot)
```

**Local** (`replay_exporter.js:227`):
```javascript
incomingAttack: state.oppMana ? state.oppMana.attack : 0,
```

**C++ implementation note:** Read the opponent's mana pool attack-resource integer directly (`GameState::getOpponentPlayer().getMana().attack`). Do NOT count `'A'` characters in a string — the integer is already available from the C++ `Resources` object. Null-guard is a no-op during live play but emit `0` defensively for end-of-game snapshots.

---

### maxAttack

**Status:** AGREE

**Shipped** (`prismata-engine.js:2639,2652,2686,2726,2744,2937`, read out at `8113`):
```javascript
maxAttack: state.helper ? state.helper.maxAttack : 0,
// Accumulated in StateHelper.update() with phase-split logic + resonate bonus
```

**Local** (`StateHelper.js:148,161,195,235,253,446`, read out at `replay_exporter.js:231`):
```javascript
maxAttack: state.helper ? state.helper.maxAttack : 0,
// Identical accumulation logic — all branches verified to match bundle
```

**C++ implementation note:** Implement as a two-pass loop over the turn player's units. Phase-sensitive:

- **Defense phase** — eligibility: `constructionTime <= 1 && delay <= 1 && !(lifespan==1 && ct==0 && delay==0) && !dead`. Add `beginOwnTurnScript.receive.attack` unconditionally; add `abilityScript.receive.attack` if health/charge suffice. Add resonate bonus (`ownAnnihilate[cardName].length`) in a post-loop pass.
- **Action phase** — for ROLE_SELLABLE: add `buyCost.attack`. For pre-existing non-beginTurn/non-buyOrAbility units with `constructionTime==0` and delay-condition: add `abilityScript.receive.attack` (ROLE_DEFAULT, health/charge check) or `abilityCost.attack` (ROLE_ASSIGNED/sacced). `beginOwnTurnScript` goes to `totalProducedThisTurn` only — **NOT** to `maxAttack`. Resonate bonus goes to `totalProducedThisTurn.attack` in action phase. For ROLE_DEFAULT's action-phase health check, use the bare `health >= healthUsed && charge >= chargeUsed` form (no `+ healthGained` adjustment). The `+ healthGained` adjustment applies only in the defense-phase path.

Fall back to `0` when StateHelper has not run (e.g. end-of-game).

---

### maxDisrupt

**Status:** AGREE

**Shipped** (`prismata-engine.js:2663`, read out at `8114`):
```javascript
this.maxDisrupt += card.disruptPotential;
// card.disruptPotential getter: targetAction==='disrupt' ? targetAmount : 0
// Accumulated inside defense-phase eligibility + health/charge check block only
```

**Local** (`StateHelper.js:172`):
```javascript
this.maxDisrupt += card.disruptPotential;   // same getter, same eligibility gate
```

**C++ implementation note:** Defense-phase only. Inside the same eligibility + health/charge block as `maxAttack`'s defense path. For each eligible own unit, add `targetAmount` if `targetAction === CHILL` (C++ uses `CHILL` for what JS calls `disrupt`). No action-phase accumulation. No own-side Cryo Kronus special case (that exists only for `oppDisruptPotential`). Fall back to `0` when StateHelper unavailable.

---

### maxSnipers

**Status:** AGREE

**Shipped** (`prismata-engine.js:2664–2668`, read out at `8115`):
```javascript
if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) { ++this.maxSnipers; }
}
// Defense-phase eligibility + health/charge block only
```

**Local** (`StateHelper.js:173–177`):
```javascript
if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) { ++this.maxSnipers; }
}
```

**C++ implementation note:** Defense-phase only. Double-gate: unit must have `targetAction == SNIPE` AND the static `potentiallyMoreAttack` flag from the card definition (Tarsier has it; most snipe-capable units do not) (verify that `CardType` exposes this flag — check `CardType.h` for a `potentiallyMoreAttack` member; if absent, it may need to be added from `cardLibrary.jso` during card loading). Same eligibility + health/charge block as `maxDisrupt`. Integer count — not a list. Fall back to `0` when StateHelper unavailable.

---

### oppAttackPotential

**Status:** AGREE

**Shipped** (`prismata-engine.js:2879,2892,2989`, read out at `8116`):
```javascript
oppAttackPotential: state.helper ? state.helper.oppAttackPotential : 0,
// No phase split for opponent side. Eligibility: ct<=1, delay<=1, not doom-1, !dead.
// beginOwnTurnScript.receive.attack: unconditional (no health/charge check).
// abilityScript.receive.attack: subject to health/charge check.
// Resonate: post-loop oppAnnihilate bonus.
```

**Local** (`StateHelper.js:388,401,498`):
```javascript
// Identical structure — no phase split, same health/charge gating asymmetry
```

**C++ implementation note:** Loop over opponent units. Eligibility: `constructionTime <= 1 && delay <= 1 && !(lifespan==1 && ct==0 && delay==0) && !dead` (note: the dead check is an inner guard in the JS source, not part of the outer ct/delay filter — the exported value is the same either way). No defense/action-phase split for the opponent calculation. Add `beginOwnTurnScript.receive.attack` unconditionally; add `abilityScript.receive.attack` only if health/charge check passes. Post-loop resonate bonus: for each unit in opponent's `oppAnnihilate` map, add `oppAnnihilate[cardName].length` to `oppAttackPotential`. Fall back to `0` when StateHelper unavailable.

---

### oppDisruptPotential

**Status:** AGREE

**Shipped** (`prismata-engine.js:2905,2914`, read out at `8117`):
```javascript
if (card.targetAction === C.TARGETACTION_DISRUPT) {
    this.oppDisruptPotential += card.targetAmount;         // line 2905 — inside health/charge check
}
// Special case outside health/charge block:
if (card.cardName === 'Cryo Kronus') {
    this.oppDisruptPotential += 999;                       // line 2914 — unconditional sentinel
}
```

**Local** (`StateHelper.js:414,423`):
```javascript
if (card.targetAction === C.TARGETACTION_DISRUPT) {
    this.oppDisruptPotential += card.targetAmount;         // line 414
}
if (card.cardName === 'Cryo Kronus') {
    this.oppDisruptPotential += 999;                       // line 423
}
```

**C++ implementation note:** Same opponent eligibility as `oppAttackPotential`. Inside the health/charge block: add `targetAmount` if `targetAction === CHILL`. **The Cryo Kronus +999 hardcode (line 423) can be skipped — Cryo Kronus is not in the ranked card library, so the literal `cardName === 'Cryo Kronus'` check is unreachable in any DSNN-relevant replay** (see the "Ranked-play scope" note at the top). Fall back to `0` when StateHelper unavailable.

---

### oppSnipers

**Status:** AGREE

**Shipped** (`prismata-engine.js:2909`, read out at `8118`):
```javascript
} else if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) { ++this.oppSnipers; }  // line 2909
}
// Post-computation internal: myDefenseReductionFromOppSnipers — NOT exported to JSON
```

**Local** (`StateHelper.js:418`):
```javascript
++this.oppSnipers;    // same double-gate, same post-computation reduction (internal only)
```

**C++ implementation note:** Same opponent eligibility + health/charge block as `oppDisruptPotential`. Double-gate: `targetAction === SNIPE && potentiallyMoreAttack` (verify that `CardType` exposes this flag — check `CardType.h` for a `potentiallyMoreAttack` member; if absent, it may need to be added from `cardLibrary.jso` during card loading). The post-computation `myDefenseReductionFromOppSnipers` (collecting own defenders with health ≤ 3, summing their health up to `oppSnipers` count) is internal to StateHelper — do NOT export it to the snapshot JSON. Only `oppSnipers` (the count) goes in the output. Fall back to `0` when StateHelper unavailable.

---

### whiteGoldEstimate

**Status:** AGREE

**Shipped** (`prismata-engine.js:7998–8101`, called at `8126`):
```javascript
whiteGoldEstimate: computeEconEstimate(0),
// Returns [lowerBound, upperBound] where:
//   lowerBound = income from guaranteed sources + current gold on hand
//   upperBound = income from all sources (including costly/sac abilities) + current gold
// Phase-sensitive: isDefensePhase = (phase==='defense' && turn===player)
```

**Local** (`replay_exporter.js:115–218`, called at `243`):
```javascript
whiteGoldEstimate: computeEconEstimate(0),
// Inline closure is a verified direct copy of the bundle function
```

**C++ implementation note:** Implement as a per-player closure (called twice, player=0 and player=1). For each player's own units in the eligibility window (`ct<=1, delay<=1, not doom-1, !dead`):

- `beginOwnTurnScript.receive.money`: always adds to both upper and lower bounds.
- `abilityScript.receive.money` (inside health/charge check): adds to upper bound. Also adds to lower bound ONLY if `abilityCost.isEmpty && abilitySac.length===0 && !abilityScript.selfsac` (i.e., free no-sac ability).
- `goldResonate` (Savior Drone mechanic): count `numDrones` for own Drones in window. Collect units with `goldResonate==='Drone'` into `goldAnnihilate` (defense phase, already ready) or `goldAnnihilateNext` (action/confirm phase, finishing construction). Post-loop: if `numDrones > 0` and the resonate map has an entry, add `entries.length * numDrones` to both bounds.

Add `currentGold` (player's mana pool `.money`) to both bounds before returning. Output format: `[lowerBound, upperBound]`.

Note: `isDefensePhase` is true only when both `phase==='defense'` AND `turn===player` — so during P0's defense, `computeEconEstimate(0)` uses the defense path and `computeEconEstimate(1)` uses the action path.

In the action/confirm phase, `goldAnnihilate` is never populated (only `goldAnnihilateNext` is). Do not apply the `goldAnnihilate` bonus in the action/confirm path.

---

### blackGoldEstimate

**Status:** AGREE

**Shipped** (`prismata-engine.js:8127`): `computeEconEstimate(1)` — identical function, player index=1.

**Local** (`replay_exporter.js:244`): `computeEconEstimate(1)` — same.

**C++ implementation note:** Same implementation as `whiteGoldEstimate` (see all notes there including the action-phase `goldAnnihilate` dead-branch), player index=1. Return `[lowerBound, upperBound]` using P1's mana `.money` as `currentGold`.

---

### boughtThisPhase

**Status:** AGREE

**Shipped** (`prismata-engine.js:7940`):
```javascript
boughtThisPhase: inst.creatorIdFromBuyOrAbility >= 0,
// Set on: SCRIPTTYPE_BUY (line 3736) and SCRIPTTYPE_ABILITY (line 3745)
// Default: -1 (Inst constructor line 1710)
// Reset: _clearInstArrowIds() at PHASE_CONFIRM transition (line 4569)
// types.ts: NON-OPTIONAL — must always emit
```

**Local** (`replay_exporter.js:61`):
```javascript
boughtThisPhase: inst.creatorIdFromBuyOrAbility >= 0,   // identical formula
```

**C++ implementation note:** Track an integer `creatorIdFromBuyOrAbility` on each CardInstance (default `-1`). Set it to the creator's card ID when a unit is spawned by a BUY action or an ABILITY action during the action phase. Reset fires at the PHASE_CONFIRM transition (the moment `phase` becomes `PHASE_CONFIRM`), which in C++ means at the top of the MOVE_COMMIT handler before any confirm-phase logic runs. Snapshots taken during the action phase see the un-reset values (correct). Emit `boughtThisPhase: (creatorIdFromBuyOrAbility >= 0)` as a boolean. NON-OPTIONAL — always emit, even when false. Units spawned by activated abilities (e.g. Plexo Cell spawning a Drone) get `true` just like purchased units.

---

### bornThisTurn

**Status:** DISAGREE (material)

**Shipped** (`prismata-engine.js:7944`):
```javascript
bornThisTurn: inst.creatorIdFromBeginTurn >= 0,
// Set on: SCRIPTTYPE_BEGINOWNTURN (line 3741) — units spawned during Swoosh (Robo Santa gifts, Bloodrager tokens, etc.)
// Default: -1 (Inst constructor line 1711)
// Reset: _clearInstArrowIds() at PHASE_CONFIRM transition (line 4570)
// types.ts: OPTIONAL (boolean?) — may omit when false, but bundle always emits
// Always emitted by bundle: instToCardJSON() unconditionally includes this field
```

**Local** (`replay_exporter.js:47–67`): **ABSENT.** `instToCardJSON()` does not include `bornThisTurn` at all. The underlying data (`inst.creatorIdFromBeginTurn`) is tracked in `Inst.js` and `State.js` — the exporter simply does not read it.

**Divergence:** Local's `instToCardJSON()` omits `bornThisTurn` entirely. `types.ts` marks the field `boolean?` (optional), so omitting it when false is technically valid. However, pile-sort's `cameOnTableThisPhase` reads `bornThisTurn` to place spawned units at the left of the play area (same as bought units). If C++ omits the field, Robo Santa gifts and similar begin-turn spawns will sort incorrectly. The shipped bundle emits it unconditionally — C++ must follow the bundle.

**C++ implementation note:** Track an integer `creatorIdFromBeginTurn` on each `CardInstance` (default `-1`). Set it to the spawning unit's card ID when a unit is created by a `beginOwnTurnScript` during the Swoosh phase. Reset to `-1` at the CONFIRM phase transition (same call site as `creatorIdFromBuyOrAbility`). Emit `bornThisTurn: (creatorIdFromBeginTurn >= 0)` as a boolean. Field is **optional** per types contract but emit it always (even when false), matching bundle behavior. Do NOT use this field's data for `boughtThisPhase` — the two fields use separate creator ID fields even though they reset at the same point.

---

## Bonus: structural fields with non-trivial C++ emission notes

These are structural (not derived), but Phase 3 implementers need precise guidance.

### phase / glassBroken

**Shipped:** `phase` is emitted as the phase string. `glassBroken` is read directly off the raw state in the replay player (not in `stateToCppJSON`). Local explicitly emits `glassBroken: state.glassBroken || false` in `stateToCppJSON`. Bundle reads `glassBroken` on the raw state object.

**C++ implementation note:** Emit BOTH `phase: 'breach'` AND `glassBroken: true` when in the breach state. The C++ serializer detects breach via the `glassBroken` flag on `GameState` and, when true, overrides the phase string to `'breach'` regardless of the engine's internal phase value (which remains `PHASE_DEFENSE` in both JS and C++). The PixiJS renderer expects this — `BoardRenderer` tests `phase === 'breach'`, not `glassBroken`. The renderer has two separate code paths that read these:
- `auto-clicks.ts` reads `gameState.glassBroken` directly.
- `TurnIndicator` and `PlayerBar` use `glassBroken || phase === 'breach'` as the breach signal.
- `BoardRenderer` derives its own internal `glassBroken` as `phase === 'breach'` and does NOT read `gameState.glassBroken`.

Emitting only one of the two will cause at least one renderer path to misbehave. Set both.

### boughtThisPhase vs bornThisTurn (reset timing)

Both `creatorIdFromBuyOrAbility` and `creatorIdFromBeginTurn` are reset together at the CONFIRM phase transition in JS. In C++, the equivalent reset fires at the PHASE_CONFIRM transition (the moment `phase` becomes `PHASE_CONFIRM`), which in C++ means at the top of the MOVE_COMMIT handler before any confirm-phase logic runs. Snapshots taken during the action phase see the un-reset values (correct).

### autoClicked

`autoClicked`: static card property from `CardType` / `cardLibrary.jso`. Emit `inst.card.autoClicked || false`. Not a derived field — no computation needed. Required because the spec's per-instance field list includes it.

---

## Self-review checklist

- [x] All 11 derived fields in summary table
- [x] Each has a clear status
- [x] AGREE entries have concrete C++ source-of-truth pointer (file + line)
- [x] DISAGREE entry (`bornThisTurn`) explains divergence and names shipped bundle as authority
- [x] Date and SHAs filled in (no placeholders)
- [x] Commit message specified in task spec
