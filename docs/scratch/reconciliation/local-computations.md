# local-computations.md — Local js_engine derived-field computations

All line numbers refer to files under:
`c:/libraries/PrismataAI/js_engine/`

Primary files read:
- `StateHelper.js` — `StateHelper.update(s)` method (lines 66–522)
- `replay_exporter.js` — `stateToCppJSON(state)` and `instToCardJSON(inst)` (lines 46–246)
- `Inst.js` — constructor defaults and `toObject()` (lines 22–360)
- `State.js` — `_runScriptForward()` (lines 700–732), `_clearInstArrowIds()` (lines 1530–1553)

**Fidelity authority reminder:** where local disagrees with the shipped bundle
(`bundle-computations.md`), the bundle wins. This catalog is for Task 4's diff.

---

## Overview: where fields are written

| Field | Module | Writer location | Value source |
|---|---|---|---|
| `incomingAttack` | `replay_exporter` | line 227 | `state.oppMana.attack` (direct read) |
| `maxAttack` | `StateHelper.update()` | lines 148, 161, 195, 235, 253 | accumulated over own units |
| `maxDisrupt` | `StateHelper.update()` | line 172 | accumulated over own units |
| `maxSnipers` | `StateHelper.update()` | line 175 | accumulated over own units |
| `oppAttackPotential` | `StateHelper.update()` | lines 388, 401, 498 | accumulated over opp units |
| `oppDisruptPotential` | `StateHelper.update()` | lines 414, 423 | accumulated over opp units |
| `oppSnipers` | `StateHelper.update()` | line 418 | accumulated over opp units |
| `whiteGoldEstimate` | `computeEconEstimate(0)` | line 243 | inline closure in `stateToCppJSON` |
| `blackGoldEstimate` | `computeEconEstimate(1)` | line 244 | inline closure in `stateToCppJSON` |
| `boughtThisPhase` | `instToCardJSON()` | line 61 | `inst.creatorIdFromBuyOrAbility >= 0` |
| `bornThisTurn` | `instToCardJSON()` | **ABSENT** | field is NOT emitted |

The StateHelper-derived fields (`maxAttack` through `oppSnipers`) are read out in
`stateToCppJSON` via `state.helper.<field>` (lines 230–236). The `computeEconEstimate`
function is a standalone closure defined inside `stateToCppJSON` (lines 115–218).

**Null-guard pattern for StateHelper-derived fields (lines 230–236):**

```javascript
maxAttack:            state.helper ? state.helper.maxAttack : 0,
maxDisrupt:           state.helper ? state.helper.maxDisrupt : 0,
maxSnipers:           state.helper ? state.helper.maxSnipers : 0,
oppAttackPotential:   state.helper ? state.helper.oppAttackPotential : 0,
oppDisruptPotential:  state.helper ? state.helper.oppDisruptPotential : 0,
oppSnipers:           state.helper ? state.helper.oppSnipers : 0,
```

**AGREES with bundle** null-guard pattern (bundle lines 8113–8119). All six fields
fall back to `0` when `state.helper` is falsy.

---

## incomingAttack

**Computed at:** `replay_exporter.js:227`

**Inputs:** `state.oppMana` — the non-turn player's current mana pool.

```javascript
incomingAttack:   state.oppMana ? state.oppMana.attack : 0,
```

**Notes:** Direct read — identical formula to bundle (bundle line 8110). `oppMana` is
the opponent's mana pool as-is. `.attack` returns `this.pool[C.MANA_A]` (the attack
slot integer). The null-guard is safety-only; `oppMana` is always defined during play.

**AGREES with bundle.**

---

## maxAttack

**Computed at:** `StateHelper.js:42` (reset to 0 in `reset()`), accumulated in
`StateHelper.update(s)` at lines 148, 161, 195, 235, 253, and resonate bonus at line 446.

**Inputs:** `state.phase`, `state.turn`, `state.table`, card properties
(`beginOwnTurnScript`, `abilityScript`, `buyCost`, `resonate`), inst properties
(`health`, `charge`, `constructionTime`, `delay`, `lifespan`, `dead`, `role`, `deadness`,
`creatorIdFromBeginTurn`, `creatorIdFromBuyOrAbility`).

**Defense-phase path (lines 118–185 in StateHelper.js):**

```javascript
if (s.phase === C.PHASE_DEFENSE) {
    if (inst.constructionTime <= 1 && inst.delay <= 1 &&
        !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) &&
        !inst.dead) {
        // ...
        if (card.beginOwnTurnScript !== null) {
            if (card.beginOwnTurnScript.receive.attack > 0) {
                pushToAttackers = true;
                this.maxAttack += card.beginOwnTurnScript.receive.attack;   // line 148
            }
            // ...
        }
        if (inst.health + card.healthGained >= card.healthUsed &&
            inst.charge + card.chargeGained >= card.chargeUsed) {
            if (card.abilityScript !== null) {
                if (card.abilityScript.receive.attack > 0) {
                    pushToAttackers = true;
                    this.maxAttack += card.abilityScript.receive.attack;    // line 161
                }
                // ...
            }
            // ...
        }
    }
}
```

**Action-phase path (lines 186–276 in StateHelper.js):**

```javascript
} else {
    // Action phase
    if (inst.role === C.ROLE_SELLABLE) {
        // ...
        this.maxAttack += card.buyCost.attack;    // line 195
        // ...
    } else if (!(inst.creatorIdFromBeginTurn >= 0 || inst.creatorIdFromBuyOrAbility >= 0)) {
        if (inst.constructionTime === 0 &&
            (inst.delay === 0 ||
             (inst.card.abilityScript !== null && inst.delay === inst.card.abilityScript.delay) ||
             (inst.card.beginOwnTurnScript !== null && inst.delay === inst.card.beginOwnTurnScript.delay))) {
            // ...
            if (card.beginOwnTurnScript !== null) {
                if (card.beginOwnTurnScript.receive.attack > 0) {
                    pushToAttackContributors = true;    // line 222 — NOTE: does NOT increment maxAttack
                }
                // ...
                this.totalProducedThisTurn.add(card.beginOwnTurnScript.receive);    // line 228
            }
            if (inst.role === C.ROLE_DEFAULT) {
                if (inst.health >= card.healthUsed && inst.charge >= card.chargeUsed &&
                    card.abilityScript !== null) {
                    if (card.abilityScript.receive.attack > 0) {
                        this.couldAttackThisTurn.push(inst);
                        this.maxAttack += card.abilityScript.receive.attack;    // line 235
                    }
                    // ...
                }
            } else if (inst.role === C.ROLE_ASSIGNED ||
                       inst.deadness === C.DEADNESS_SACCED ||
                       inst.deadness === C.DEADNESS_SELFSACCED) {
                if (card.abilityScript !== null) {
                    // ...
                    this.totalProducedThisTurn.add(card.abilityScript.receive);
                    this.maxAttack += card.abilityCost.attack;    // line 253
                    // ...
                }
            }
        }
    }
}
```

**Resonate resolution — own side (lines 435–461):**

```javascript
if (ownAnnihilate.hasOwnProperty(inst.card.cardName)) {
    if (s.phase === C.PHASE_DEFENSE) {
        if (!wentOff.hasOwnProperty(card.cardName)) {
            this.couldAttackThisTurn = this.couldAttackThisTurn.concat(
                ownAnnihilate[card.cardName]
            );
            wentOff[card.cardName] = true;
        }
        this.maxAttack += ownAnnihilate[card.cardName].length;    // line 446
    } else {
        // ...
        this.totalProducedThisTurn.attack += ownAnnihilate[card.cardName].length;    // action phase
    }
}
```

**Notes:** AGREES with bundle in all branches. The key asymmetry is preserved:
`beginOwnTurnScript.receive.attack` is added to `maxAttack` in the **defense** branch
(line 148) but NOT in the action branch (line 222 only sets `pushToAttackContributors`
and adds to `totalProducedThisTurn` — `maxAttack` is not incremented). This matches
bundle behavior (bundle notes: asymmetry at lines 2639 vs 2712–2719).

**One local difference in action-phase health check for ROLE_DEFAULT (line 231):**
Local uses `inst.health >= card.healthUsed && inst.charge >= card.chargeUsed` (no
`+ healthGained / + chargeGained` adjustment). Bundle action-phase path (line 2721)
uses the same bare `health >= healthUsed` form. **AGREES with bundle.**

**AGREES with bundle.**

---

## maxDisrupt

**Computed at:** `StateHelper.js:172` (inside `StateHelper.update()`).

**Inputs:** Same defense-phase eligibility filter + health/charge check as `maxAttack`.
`card.disruptPotential` getter (returns `card.targetAmount` if `targetAction === 'disrupt'`, else 0).

```javascript
// Inside the same health/charge eligibility block (defense-phase path):
this.maxDisrupt += card.disruptPotential;    // line 172
```

**Notes:** Only accumulated in the **defense-phase** path (no action-phase accumulation).
Same as bundle (bundle line 2663). No own-side Cryo Kronus special case (that special
case exists only for `oppDisruptPotential`).

**AGREES with bundle.**

---

## maxSnipers

**Computed at:** `StateHelper.js:173–177` (inside `StateHelper.update()`).

**Inputs:** Same eligibility + health/charge check as `maxDisrupt`. `card.targetAction`,
`card.potentiallyMoreAttack`.

```javascript
// Inside the same health/charge eligibility block as maxDisrupt (defense-phase path):
if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) {
        ++this.maxSnipers;    // line 175
    }
}
```

**Notes:** Defense-phase only. Same double-gate (SNIPE + potentiallyMoreAttack) as bundle
(bundle lines 2664–2668).

**AGREES with bundle.**

---

## oppAttackPotential

**Computed at:** `StateHelper.js:50` (reset to 0), accumulated at lines 388, 401, 498.

**Inputs:** Opponent units (`inst.owner !== s.turn`), eligibility filter:
`constructionTime <= 1, delay <= 1`, not doom-1 (lifespan===1 && ct===0 && delay===0),
`!inst.dead`. Card properties: `beginOwnTurnScript`, `abilityScript`, `resonate`.

**Per-unit accumulation (lines 384–401):**

```javascript
pushToOppAttackers = false;
if (card.beginOwnTurnScript !== null &&
    card.beginOwnTurnScript.receive.attack > 0) {
    pushToOppAttackers = true;
    this.oppAttackPotential += card.beginOwnTurnScript.receive.attack;    // line 388
    this.oppGuaranteedAttack += card.beginOwnTurnScript.receive.attack;
}
// ...
if (inst.health + card.healthGained >= card.healthUsed &&
    inst.charge + card.chargeGained >= card.chargeUsed) {
    if (card.abilityScript !== null &&
        card.abilityScript.receive.attack > 0) {
        pushToOppAttackers = true;
        this.oppAttackPotential += card.abilityScript.receive.attack;    // line 401
    }
    // ...
}
```

**Resonate resolution — opponent side (lines 487–505):**

```javascript
if (oppAnnihilate.hasOwnProperty(card.cardName)) {
    if (!wentOff.hasOwnProperty(card.cardName)) {
        this.oppAttackers = this.oppAttackers.concat(
            oppAnnihilate[card.cardName]
        );
        wentOff[card.cardName] = true;
    }
    this.oppAttackPotential += oppAnnihilate[card.cardName].length;    // line 498
    this.oppGuaranteedAttack += oppAnnihilate[card.cardName].length;
}
```

**Notes:** No phase split for opponent side — same logic regardless of `state.phase`.
`beginOwnTurnScript` attack is unconditional (no health/charge check); `abilityScript`
attack is subject to health/charge check. Both match bundle behavior (bundle lines
2876–2893, 2989).

**AGREES with bundle.**

---

## oppDisruptPotential

**Computed at:** `StateHelper.js:54` (reset to 0), accumulated at lines 414 and 423.

**Inputs:** Same opponent eligibility + health/charge check. `card.targetAction`,
`card.targetAmount`. Special case: `card.cardName === 'Cryo Kronus'`.

```javascript
// Inside health/charge check block for opponent units (lines 412–419):
if (card.targetAction === C.TARGETACTION_DISRUPT) {
    pushToOppAttackers = true;
    this.oppDisruptPotential += card.targetAmount;    // line 414
} else if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) {
        pushToOppAttackers = true;
        ++this.oppSnipers;    // line 418
    }
}
// Cryo Kronus special case (outside health/charge block, inside !inst.dead guard):
if (card.cardName === 'Cryo Kronus') {
    this.oppDisruptPotential += 999;    // line 423
}
```

**Notes:** Cryo Kronus gets `+999` unconditionally (not subject to health/charge check)
whenever it is alive and within the opponent's eligibility window. This is the same
hardcoded sentinel as bundle (bundle line 2914). The `+999` makes the chill display show
unconditionally for any Cryo Kronus the opponent has.

**AGREES with bundle.**

---

## oppSnipers

**Computed at:** `StateHelper.js:55` (reset to 0), incremented at line 418.

**Inputs:** Same opponent eligibility + health/charge check. `card.targetAction === SNIPE`,
`card.potentiallyMoreAttack`.

```javascript
} else if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) {
        pushToOppAttackers = true;
        ++this.oppSnipers;    // line 418
    }
}
```

**Post-computation — sniper defense reduction (lines 508–521):**

```javascript
if (this.oppSnipers > 0) {
    const myHealths = [];
    for (let di = 0; di < this.ownDefenders.length; di++) {
        inst = this.ownDefenders[di];
        if (inst.health <= 3) {
            myHealths.push(inst.health);
        }
    }
    myHealths.sort((a, b) => b - a); // Descending
    const limit = Math.min(this.oppSnipers, myHealths.length);
    for (let i = 0; i < limit; i++) {
        this.myDefenseReductionFromOppSnipers += myHealths[i];
    }
}
```

**Notes:** Same double-gate as bundle (SNIPE + potentiallyMoreAttack). The
`myDefenseReductionFromOppSnipers` side-computation is internal to StateHelper
and is not exported in the snapshot JSON — same as bundle.

**AGREES with bundle.**

---

## whiteGoldEstimate / blackGoldEstimate

**Computed at:** `replay_exporter.js:243–244` via `computeEconEstimate(0)` / `computeEconEstimate(1)`.

**Inputs (closure captures `state`):** `state.phase`, `state.turn`, `state.table`,
`state.whiteMana`, `state.blackMana`. Per-unit: `inst.owner`, `inst.constructionTime`,
`inst.delay`, `inst.lifespan`, `inst.dead`, `inst.health`, `inst.charge`,
`card.beginOwnTurnScript`, `card.abilityScript`, `card.abilityCost`, `card.abilitySac`,
`card.goldResonate`, `card.cardName`.

**Full `computeEconEstimate` function (lines 115–218 of `replay_exporter.js`):**

```javascript
function computeEconEstimate(player) {
    const C = require('./C');
    let econPotential = 0, econPotentialLower = 0;
    const goldAnnihilate = {};     // goldResonate name → [insts]
    const goldAnnihilateNext = {}; // for units finishing construction
    let numDrones = 0;
    const saviorResoName = 'Drone';
    const isDefensePhase = state.phase === C.PHASE_DEFENSE && state.turn === player;

    state.table.forEach(function(inst) {
        if (inst.owner !== player) return;
        const card = inst.card;

        if (isDefensePhase) {
            // Defense phase: compute for THIS turn (what we'll produce after defending)
            if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) && !inst.dead) {

                if (card.goldResonate != null) {
                    if (goldAnnihilate[card.goldResonate])
                        goldAnnihilate[card.goldResonate].push(inst);
                    else
                        goldAnnihilate[card.goldResonate] = [inst];
                }
                if (card.cardName === saviorResoName) numDrones++;

                if (card.beginOwnTurnScript && card.beginOwnTurnScript.receive) {
                    const money = card.beginOwnTurnScript.receive.money || 0;
                    econPotential += money;
                    econPotentialLower += money;
                }
                if (inst.health + (card.healthGained || 0) >= (card.healthUsed || 0) &&
                    inst.charge + (card.chargeGained || 0) >= (card.chargeUsed || 0)) {
                    if (card.abilityScript && card.abilityScript.receive) {
                        const money = card.abilityScript.receive.money || 0;
                        econPotential += money;
                        if (card.abilityCost && card.abilityCost.isEmpty &&
                            (!card.abilitySac || card.abilitySac.length === 0) &&
                            !(card.abilityScript && card.abilityScript.selfsac)) {
                            econPotentialLower += money;
                        }
                    }
                }
            }
        } else {
            // Action/confirm phase: compute for NEXT turn
            if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) && !inst.dead) {

                if (card.beginOwnTurnScript && card.beginOwnTurnScript.receive) {
                    const money = card.beginOwnTurnScript.receive.money || 0;
                    econPotential += money;
                    econPotentialLower += money;
                }
                if (inst.health + (card.healthGained || 0) >= (card.healthUsed || 0) &&
                    inst.charge + (card.chargeGained || 0) >= (card.chargeUsed || 0) &&
                    card.abilityScript && card.abilityScript.receive) {
                    const money = card.abilityScript.receive.money || 0;
                    econPotential += money;
                    if (card.abilityCost && card.abilityCost.isEmpty &&
                        (!card.abilitySac || card.abilitySac.length === 0) &&
                        !(card.abilityScript && card.abilityScript.selfsac)) {
                        econPotentialLower += money;
                    }
                }
                // goldResonate for units finishing construction (will be ready next turn)
                if (card.goldResonate != null && (inst.constructionTime === 1 || inst.delay === 1)) {
                    if (goldAnnihilateNext[card.goldResonate])
                        goldAnnihilateNext[card.goldResonate].push(inst);
                    else
                        goldAnnihilateNext[card.goldResonate] = [inst];
                }
                if (card.cardName === saviorResoName) numDrones++;
            }
        }
    });

    // goldResonate bonus: each goldResonate source multiplies by numDrones
    if (numDrones > 0) {
        if (isDefensePhase) {
            if (goldAnnihilate[saviorResoName]) {
                const bonus = goldAnnihilate[saviorResoName].length * numDrones;
                econPotential += bonus;
                econPotentialLower += bonus;
            }
        } else {
            if (goldAnnihilate[saviorResoName]) {
                const bonus = goldAnnihilate[saviorResoName].length * numDrones;
                econPotential += bonus;
                econPotentialLower += bonus;
            }
            if (goldAnnihilateNext[saviorResoName]) {
                const bonus = goldAnnihilateNext[saviorResoName].length * numDrones;
                econPotential += bonus;
                econPotentialLower += bonus;
            }
        }
    }

    // SWF: UIPlayerManaBar adds current gold to the estimate
    // turnMana.money for active player, oppMana.money for opponent
    const currentGold = (player === 0 ? state.whiteMana : state.blackMana).money || 0;
    return [econPotentialLower + currentGold, econPotential + currentGold];
}
```

**Writer in output object (lines 243–244):**

```javascript
whiteGoldEstimate: computeEconEstimate(0),
blackGoldEstimate: computeEconEstimate(1)
```

**Notes:**

- This closure is IDENTICAL to the bundle's `computeEconEstimate` (bundle lines
  7998–8101). The local version is a direct copy — same logic, same structure, same
  null-guards (`|| 0` on money). **AGREES with bundle.**

- The task context predicted this as "a likely divergence point" (local might pull
  from StateHelper instead of the inline closure). It does NOT — local uses the same
  inline closure pattern as the bundle. `StateHelper` computes related econ fields
  (`maxEcon`, `maxEconLowerBound`, `ownEconPotentialNextTurn`) but those are NOT
  what `replay_exporter.js` uses for `whiteGoldEstimate`/`blackGoldEstimate`. The
  closure is the emitter in both versions.

- **`goldAnnihilate` dead branch in non-defense path**: In the non-defense-phase
  branch, `goldAnnihilate` is never populated (only `goldAnnihilateNext` is), so
  `if (goldAnnihilate[saviorResoName])` at the resonate bonus section is always false
  and is a no-op. This dead-code path is present identically in both local and bundle.

**AGREES with bundle.**

---

## boughtThisPhase

**Computed at:** `replay_exporter.js:61` (inside `instToCardJSON()`).

**Inputs:** `inst.creatorIdFromBuyOrAbility` — set on `Inst` creation.

```javascript
boughtThisPhase:  inst.creatorIdFromBuyOrAbility >= 0,    // line 61
```

**Set-true sites — `_runScriptForward()` in `State.js` (lines 715, 724):**

```javascript
if (scriptType === C.SCRIPTTYPE_BUY) {
    createdInst = this._createInst(..., createIds[i][j]);
    inst.buyCreateIds[i][j] = createdInst.instId;
    createdInst.creatorIdFromBuyOrAbility = inst.instId;    // line 715
} else if (scriptType === C.SCRIPTTYPE_BEGINOWNTURN) {
    // sets creatorIdFromBeginTurn instead — see bornThisTurn
    createdInst.creatorIdFromBeginTurn = inst.instId;       // line 720
} else if (scriptType === C.SCRIPTTYPE_ABILITY) {
    createdInst = this._createInst(..., createIds[i][j]);
    inst.abilityCreateIds[i][j] = createdInst.instId;
    createdInst.creatorIdFromBuyOrAbility = inst.instId;    // line 724
}
```

**Default (no creator) — `Inst` constructor (lines 103–104):**

```javascript
this.creatorIdFromBuyOrAbility = -1;
this.creatorIdFromBeginTurn = -1;
```

**Reset site — `_clearInstArrowIds()` (lines 1548–1549 in State.js), called at line 1398:**

```javascript
inst.creatorIdFromBuyOrAbility = -1;    // line 1548
inst.creatorIdFromBeginTurn = -1;       // line 1549
```

`_clearInstArrowIds()` is called at line 1398, immediately after `this.phase = C.PHASE_CONFIRM`
(line 1396), before `_manaRots()` and `_collectSpells()`.

**Notes:** Same formula as bundle (bundle line 7940: `inst.creatorIdFromBuyOrAbility >= 0`).
Both BUY and ABILITY scripts set this field, so ability-spawned units (e.g. Plexo Cell
spawning a Drone) have `boughtThisPhase === true`. Reset fires at PHASE_CONFIRM transition,
same as bundle (bundle notes call site "line 4419").

**AGREES with bundle.**

---

## bornThisTurn

**Computed at:** **ABSENT from local `instToCardJSON()`.**

`bornThisTurn` is NOT emitted by local `replay_exporter.js`. The `instToCardJSON()`
function (lines 47–67) does not include this field at all.

**Bundle behavior (bundle line 7944):**

```javascript
bornThisTurn:     inst.creatorIdFromBeginTurn >= 0,    // BUNDLE ONLY — not in local
```

**Local `instToCardJSON()` — full function for comparison (lines 47–67):**

```javascript
function instToCardJSON(inst) {
    return {
        instId:           inst.instId,
        cardName:         inst.card.UIName,
        owner:            inst.owner,
        health:           inst.health,
        damage:           inst.damage,
        role:             inst.role,
        deadness:         inst.deadness,
        constructionTime: inst.constructionTime,
        charge:           inst.charge,
        delay:            inst.delay,
        lifespan:         inst.lifespan,
        disruptDamage:    inst.disruptDamage,
        blocking:         inst.blocking,
        boughtThisPhase:  inst.creatorIdFromBuyOrAbility >= 0,
        defaultBlocking:  inst.card.defaultBlocking || false,
        isFragile:        inst.card.fragile || false,
        cardType:         inst.card.cardType || 'unit',
        autoClicked:      inst.card.autoClicked || false
    };
}
```

**The underlying data IS tracked** — `inst.creatorIdFromBeginTurn` is set at
`State.js:720` when `scriptType === C.SCRIPTTYPE_BEGINOWNTURN`, reset at
`State.js:1549` in `_clearInstArrowIds()`, and preserved through `Inst.toObject()`
(line 349) and the deserialization path (line 170). The field exists on every `Inst`.
The exporter simply does not read it.

**DIVERGES from bundle.** Bundle always emits `bornThisTurn`. Local never emits it.
Per `types.ts`, `bornThisTurn` is **optional** (`boolean?`), so omitting it when false
is technically legal. However, the bundle always emits it (even when false), and pile-sort
reads it via `cameOnTableThisPhase`. C++ snapshot exporter should follow the bundle and
always emit it.

---

## stateToCppJSON

This section quotes the full `stateToCppJSON()` function from `replay_exporter.js`
(lines 75–246). This is the canonical local emitter — it both reads and shapes every
snapshot field.

```javascript
/**
 * Convert a JS engine State to C++ GameState JSON format.
 *
 * @param {State} state - JS engine State object
 * @returns {Object} GameState JSON compatible with GameState::initFromJSON()
 */
function stateToCppJSON(state) {
    // Resource strings — Mana.toString() produces the same format as C++ Resources::getString()
    // (digits for gold, H/B/C/G/A characters — parser is order-independent)
    const whiteMana = state.whiteMana.toString();
    const blackMana = state.blackMana.toString();

    // Build cards array and supply arrays — only include cards with nonzero supply or purchases
    const cards = [];
    const whiteTotalSupply = [];
    const blackTotalSupply = [];
    const whiteSupplySpent = [];
    const blackSupplySpent = [];

    const numCards = state.cards.length;
    for (let i = 0; i < numCards; i++) {
        const ws = state.whiteSupply[i] || 0;
        const bs = state.blackSupply[i] || 0;
        const wb = state.whiteBought[i] || 0;
        const bb = state.blackBought[i] || 0;

        // Include card if it was ever buyable (has supply or was purchased)
        if (ws > 0 || bs > 0 || wb > 0 || bb > 0) {
            cards.push(state.cards[i].UIName);
            whiteTotalSupply.push(ws); // whiteSupply is the initial total (constant)
            blackTotalSupply.push(bs);
            whiteSupplySpent.push(wb);
            blackSupplySpent.push(bb);
        }
    }

    // Build table array — include all cards (dead units rendered with skull until swoosh)
    const table = [];
    state.table.forEach(function(inst) {
        table.push(instToCardJSON(inst));
    });

    // Gold estimate for next turn — faithful port of StateHelper.update() econ logic.
    // Computes [lowerBound, upperBound] for each player.
    // This runs from the OPPONENT's perspective of "next turn" — for the active player
    // (state.turn), we compute what they'll have when their next turn starts.
    function computeEconEstimate(player) {
        const C = require('./C');
        let econPotential = 0, econPotentialLower = 0;
        const goldAnnihilate = {};     // goldResonate name → [insts]
        const goldAnnihilateNext = {}; // for units finishing construction
        let numDrones = 0;
        const saviorResoName = 'Drone';
        const isDefensePhase = state.phase === C.PHASE_DEFENSE && state.turn === player;

        state.table.forEach(function(inst) {
            if (inst.owner !== player) return;
            const card = inst.card;

            if (isDefensePhase) {
                // Defense phase: compute for THIS turn (what we'll produce after defending)
                if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                    !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) && !inst.dead) {

                    if (card.goldResonate != null) {
                        if (goldAnnihilate[card.goldResonate])
                            goldAnnihilate[card.goldResonate].push(inst);
                        else
                            goldAnnihilate[card.goldResonate] = [inst];
                    }
                    if (card.cardName === saviorResoName) numDrones++;

                    if (card.beginOwnTurnScript && card.beginOwnTurnScript.receive) {
                        const money = card.beginOwnTurnScript.receive.money || 0;
                        econPotential += money;
                        econPotentialLower += money;
                    }
                    if (inst.health + (card.healthGained || 0) >= (card.healthUsed || 0) &&
                        inst.charge + (card.chargeGained || 0) >= (card.chargeUsed || 0)) {
                        if (card.abilityScript && card.abilityScript.receive) {
                            const money = card.abilityScript.receive.money || 0;
                            econPotential += money;
                            if (card.abilityCost && card.abilityCost.isEmpty &&
                                (!card.abilitySac || card.abilitySac.length === 0) &&
                                !(card.abilityScript && card.abilityScript.selfsac)) {
                                econPotentialLower += money;
                            }
                        }
                    }
                }
            } else {
                // Action/confirm phase: compute for NEXT turn
                if (inst.constructionTime <= 1 && inst.delay <= 1 &&
                    !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) && !inst.dead) {

                    if (card.beginOwnTurnScript && card.beginOwnTurnScript.receive) {
                        const money = card.beginOwnTurnScript.receive.money || 0;
                        econPotential += money;
                        econPotentialLower += money;
                    }
                    if (inst.health + (card.healthGained || 0) >= (card.healthUsed || 0) &&
                        inst.charge + (card.chargeGained || 0) >= (card.chargeUsed || 0) &&
                        card.abilityScript && card.abilityScript.receive) {
                        const money = card.abilityScript.receive.money || 0;
                        econPotential += money;
                        if (card.abilityCost && card.abilityCost.isEmpty &&
                            (!card.abilitySac || card.abilitySac.length === 0) &&
                            !(card.abilityScript && card.abilityScript.selfsac)) {
                            econPotentialLower += money;
                        }
                    }
                    // goldResonate for units finishing construction (will be ready next turn)
                    if (card.goldResonate != null && (inst.constructionTime === 1 || inst.delay === 1)) {
                        if (goldAnnihilateNext[card.goldResonate])
                            goldAnnihilateNext[card.goldResonate].push(inst);
                        else
                            goldAnnihilateNext[card.goldResonate] = [inst];
                    }
                    if (card.cardName === saviorResoName) numDrones++;
                }
            }
        });

        // goldResonate bonus: each goldResonate source multiplies by numDrones
        if (numDrones > 0) {
            if (isDefensePhase) {
                if (goldAnnihilate[saviorResoName]) {
                    const bonus = goldAnnihilate[saviorResoName].length * numDrones;
                    econPotential += bonus;
                    econPotentialLower += bonus;
                }
            } else {
                if (goldAnnihilate[saviorResoName]) {
                    const bonus = goldAnnihilate[saviorResoName].length * numDrones;
                    econPotential += bonus;
                    econPotentialLower += bonus;
                }
                if (goldAnnihilateNext[saviorResoName]) {
                    const bonus = goldAnnihilateNext[saviorResoName].length * numDrones;
                    econPotential += bonus;
                    econPotentialLower += bonus;
                }
            }
        }

        // SWF: UIPlayerManaBar adds current gold to the estimate
        // turnMana.money for active player, oppMana.money for opponent
        const currentGold = (player === 0 ? state.whiteMana : state.blackMana).money || 0;
        return [econPotentialLower + currentGold, econPotential + currentGold];
    }

    return {
        whiteMana:        whiteMana,
        blackMana:        blackMana,
        turn:             state.turn,
        numTurns:         state.numTurns,
        phase:            state.phase,
        glassBroken:      state.glassBroken || false,
        incomingAttack:   state.oppMana ? state.oppMana.attack : 0,
        // --- StateHelper-derived fields consumed by the viewer's midline ---
        // Turn player's potential next-attack / chill (shown bracketed during their defense phase)
        maxAttack:            state.helper ? state.helper.maxAttack : 0,
        maxDisrupt:           state.helper ? state.helper.maxDisrupt : 0,
        maxSnipers:           state.helper ? state.helper.maxSnipers : 0,
        // Opponent's predicted next-turn output (shown bracketed outside defense)
        oppAttackPotential:   state.helper ? state.helper.oppAttackPotential : 0,
        oppDisruptPotential:  state.helper ? state.helper.oppDisruptPotential : 0,
        oppSnipers:           state.helper ? state.helper.oppSnipers : 0,
        cards:            cards,
        whiteTotalSupply: whiteTotalSupply,
        blackTotalSupply: blackTotalSupply,
        whiteSupplySpent: whiteSupplySpent,
        blackSupplySpent: blackSupplySpent,
        table:            table,
        whiteGoldEstimate: computeEconEstimate(0),
        blackGoldEstimate: computeEconEstimate(1)
    };
}
```

**Structural observations:**

1. `glassBroken` is emitted here (`state.glassBroken || false`) — present in local,
   **absent from bundle's `stateToCppJSON`** output object. The bundle reads `glassBroken`
   off the raw state object directly in the replay player; local explicitly includes it.
   For C++ export this is fine — emit it.

2. All six StateHelper fields use the same `state.helper ? state.helper.<field> : 0`
   null-guard pattern as the bundle.

3. `bornThisTurn` is absent (see dedicated section above).

4. `autoClicked` IS present in local `instToCardJSON()` (line 65: `autoClicked: inst.card.autoClicked || false`).
   The bundle catalog does not mention `autoClicked` in its `instToCardJSON` quote — this
   may be a local addition or the bundle catalog may have omitted it. Not a derived field
   (it's a static card property), but worth noting for Task 4.

---

## Summary of divergences from bundle

| Field | Status | Detail |
|---|---|---|
| `incomingAttack` | AGREES | Identical formula |
| `maxAttack` | AGREES | All branches match |
| `maxDisrupt` | AGREES | Defense-phase only, same gate |
| `maxSnipers` | AGREES | Defense-phase only, same double-gate |
| `oppAttackPotential` | AGREES | Same eligibility, same resonate bonus |
| `oppDisruptPotential` | AGREES | Cryo Kronus +999 hardcode present |
| `oppSnipers` | AGREES | Same double-gate, same sniper reduction |
| `whiteGoldEstimate` | AGREES | Inline closure is a direct copy of bundle |
| `blackGoldEstimate` | AGREES | Inline closure is a direct copy of bundle |
| `boughtThisPhase` | AGREES | Same `creatorIdFromBuyOrAbility >= 0` formula |
| `bornThisTurn` | **DIVERGES** | Bundle emits it; local `instToCardJSON()` does NOT include this field at all |

**One additional structural note (not a derived field):** Local `instToCardJSON()` includes
`autoClicked` (line 65). Check whether the bundle's `instToCardJSON` also emits it — the
bundle catalog quote may have omitted it. Not a derived-field concern for C++ but worth
verifying in Task 4.
