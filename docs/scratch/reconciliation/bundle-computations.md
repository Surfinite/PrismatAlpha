# bundle-computations.md — Shipped-bundle derived-field computations

All line numbers refer to:
`c:/libraries/prismata-ladder/prismata-ladder-site/public/js/prismata-engine.js`

This is the **fidelity authority**. Where this bundle disagrees with `js_engine/`, the
bundle's semantics are what the C++ snapshot exporter must match.

---

## Overview: where fields are written

| Field | Module | Writer location | Value source |
|---|---|---|---|
| `incomingAttack` | `replay_exporter` | 8110 | `state.oppMana.attack` (direct read) |
| `maxAttack` | `StateHelper.update()` | 2639, 2652, 2686, 2726, 2744, 2937 | accumulated over own units |
| `maxDisrupt` | `StateHelper.update()` | 2663 | accumulated over own units |
| `maxSnipers` | `StateHelper.update()` | 2666 | accumulated over own units |
| `oppAttackPotential` | `StateHelper.update()` | 2879, 2892, 2989 | accumulated over opp units |
| `oppDisruptPotential` | `StateHelper.update()` | 2905, 2914 | accumulated over opp units |
| `oppSnipers` | `StateHelper.update()` | 2909 | accumulated over opp units |
| `whiteGoldEstimate` | `computeEconEstimate(0)` | 8126 | inline closure in `stateToCppJSON` |
| `blackGoldEstimate` | `computeEconEstimate(1)` | 8127 | inline closure in `stateToCppJSON` |
| `boughtThisPhase` | `instToCardJSON()` | 7940 | `inst.creatorIdFromBuyOrAbility >= 0` |
| `bornThisTurn` | `instToCardJSON()` | 7944 | `inst.creatorIdFromBeginTurn >= 0` |

The StateHelper-derived fields (`maxAttack` through `oppSnipers`) are read out in
`stateToCppJSON` via `state.helper.<field>` (lines 8113–8119). The `computeEconEstimate`
function is a standalone closure defined inside `stateToCppJSON` (lines 7998–8101).

**Null-guard pattern for StateHelper-derived fields (lines 8113–8119):**

```javascript
maxAttack:            state.helper ? state.helper.maxAttack : 0,
maxDisrupt:           state.helper ? state.helper.maxDisrupt : 0,
maxSnipers:           state.helper ? state.helper.maxSnipers : 0,
oppAttackPotential:   state.helper ? state.helper.oppAttackPotential : 0,
oppDisruptPotential:  state.helper ? state.helper.oppDisruptPotential : 0,
oppSnipers:           state.helper ? state.helper.oppSnipers : 0,
```

All six StateHelper-derived fields are guarded by `state.helper ? ... : 0`. **C++ snapshot
output must emit `0` for all six of these fields when `StateHelper` computation has not run
or is unavailable** (e.g. end-of-game states where the helper may be null/uninitialized).
Emitting absent/undefined here would break viewer midline rendering.

---

## incomingAttack

**Computed at:** `prismata-engine.js:8110`

**Inputs:** `state.oppMana` (a `Mana` object) — the non-turn player's current mana pool.

```javascript
incomingAttack:   state.oppMana ? state.oppMana.attack : 0,
```

**Supporting definition — `oppMana` getter (lines 3365–3367):**

```javascript
get oppMana() {
    return this.turn === C.COLOR_WHITE ? this.blackMana : this.whiteMana;
}
```

**Supporting definition — `Mana.attack` getter (lines 567–568):**

```javascript
get attack() { return this.pool[C.MANA_A]; }
set attack(value) { this.pool[C.MANA_A] = value | 0; }
```

`MANA_A` is the attack slot in the 6-element mana pool `[gold, green, blue, red, energy, attack]`.
The mana string parser counts `'A'` characters and increments `pool[MANA_A]` for each (line 555).

**Notes:** This is a direct read — no lookahead computation. `oppMana` is the opponent's
mana pool as-is at the time the snapshot is taken. During the defense phase this reflects
the attacker's committed attack (how much incoming damage the defender must block). The
null-guard (`state.oppMana ? ... : 0`) exists for safety but `oppMana` is always defined
during play. The in-scope-fields.md note "count attack mana 'A' characters in the attacker's
mana string" is correct but slightly misleading — the field holds the integer count, not
the string. C++ should read the opponent mana pool's attack resource integer directly.

---

## maxAttack

**Computed at:** `prismata-engine.js:2533` (reset/init), accumulated in `StateHelper.update()` at lines 2639, 2652, 2686, 2726, 2744, 2937.

**Inputs:** `StateHelper.update(state)` — `state.table`, `state.phase`, `state.turn`, card properties (`beginOwnTurnScript`, `abilityScript`, `buyCost`, resonate), inst properties (`health`, `charge`, `constructionTime`, `delay`, `lifespan`, `dead`, `role`, `deadness`).

**Full `StateHelper.update()` logic for `maxAttack` (verbatim, lines 2609–2953, relevant branches only):**

```javascript
// Outer branch on phase (line 2609):
if (s.phase === C.PHASE_DEFENSE) {
    // --- DEFENSE PHASE — own units (inst.owner === s.turn) ---
    // Eligibility filter for ownStuffAfterDefensePhase (lines 2611–2613):
    if (inst.constructionTime <= 1 && inst.delay <= 1 &&
        !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0) &&
        !inst.dead) {

        if (card.beginOwnTurnScript !== null) {
            if (card.beginOwnTurnScript.receive.attack > 0) {
                pushToAttackers = true;
                this.maxAttack += card.beginOwnTurnScript.receive.attack;    // line 2639
            }
        }
        if (inst.health + card.healthGained >= card.healthUsed &&
            inst.charge + card.chargeGained >= card.chargeUsed) {
            if (card.abilityScript !== null) {
                if (card.abilityScript.receive.attack > 0) {
                    pushToAttackers = true;
                    this.maxAttack += card.abilityScript.receive.attack;     // line 2652
                }
            }
            // (maxDisrupt / maxSnipers also accumulated here — see those fields)
        }
    }
} else {
    // --- ACTION PHASE (line 2677 else branch) — own units (inst.owner === s.turn) ---
    if (inst.role === C.ROLE_SELLABLE) {
        // Just-bought unit: refund its buy-cost attack to maxAttack (line 2686)
        this.maxAttack += card.buyCost.attack;                               // line 2686
    } else if (!(inst.creatorIdFromBeginTurn >= 0 || inst.creatorIdFromBuyOrAbility >= 0)) {
        if (inst.constructionTime === 0 &&
            (inst.delay === 0 ||
             (inst.card.abilityScript !== null && inst.delay === inst.card.abilityScript.delay) ||
             (inst.card.beginOwnTurnScript !== null && inst.delay === inst.card.beginOwnTurnScript.delay))) {

            // beginOwnTurnScript processed here (lines 2712–2719) — see Notes for asymmetry
            if (card.beginOwnTurnScript !== null) {
                if (card.beginOwnTurnScript.receive.attack > 0) {
                    pushToAttackContributors = true;                         // line 2714
                }
                this.totalProducedThisTurn.add(card.beginOwnTurnScript.receive); // line 2719
                // NOTE: maxAttack is NOT incremented here (see Notes — asymmetry)
            }

            // ROLE_DEFAULT path (lines 2721–2732):
            if (inst.role === C.ROLE_DEFAULT) {
                if (inst.health >= card.healthUsed && inst.charge >= card.chargeUsed &&
                    card.abilityScript !== null) {
                    if (card.abilityScript.receive.attack > 0) {
                        this.couldAttackThisTurn.push(inst);
                        this.maxAttack += card.abilityScript.receive.attack; // line 2726
                    }
                }
            } else if (inst.role === C.ROLE_ASSIGNED ||
                       inst.deadness === C.DEADNESS_SACCED ||
                       inst.deadness === C.DEADNESS_SELFSACCED) {
                if (card.abilityScript !== null) {
                    this.totalProducedThisTurn.add(card.abilityScript.receive); // line 2743
                    this.maxAttack += card.abilityCost.attack;               // line 2744
                }
            }
        }
    }
}

// RESONATE resolution — own side (lines 2924–2952)
// After the main loop, for each inst in ownStuffAfterDefensePhase:
if (ownAnnihilate.hasOwnProperty(inst.card.cardName)) {
    if (s.phase === C.PHASE_DEFENSE) {
        if (!wentOff.hasOwnProperty(card.cardName)) {
            wentOff[card.cardName] = true;
        }
        this.maxAttack += ownAnnihilate[card.cardName].length;           // line 2937
    } else {
        // action phase: goes to totalProducedThisTurn.attack instead
        this.totalProducedThisTurn.attack += ownAnnihilate[card.cardName].length;
    }
}
```

**Notes:** `maxAttack` accumulates the turn player's theoretical maximum attack if they end
their turn now. The computation is **phase-sensitive**:

- **Defense phase**: reads from `ownStuffAfterDefensePhase` (constructionTime ≤ 1, delay ≤ 1,
  not lifespan-1 imminent doom, not dead). Includes both `beginOwnTurnScript.receive.attack`
  and `abilityScript.receive.attack` subject to health/charge checks.
- **Action phase**: adds `buyCost.attack` for ROLE_SELLABLE (just-bought) units;
  for existing units adds `abilityScript.receive.attack` (ROLE_DEFAULT with health/charge)
  or `abilityCost.attack` (ROLE_ASSIGNED/sacced). Skips units created by beginTurn or buy/ability.
- **Resonate bonus**: after the main loop, for any unit in `ownAnnihilate` (units whose
  `card.resonate` matches another present unit's `card.cardName`) a count of
  `ownAnnihilate[name].length` is added during defense phase. In action phase this goes to
  `totalProducedThisTurn` instead.
- **Asymmetry to watch:** in the **defense** branch, `beginOwnTurnScript.receive.attack`
  contributes to `maxAttack` (line 2639). In the **action** branch (lines 2712–2719),
  `beginOwnTurnScript` is processed (its attack is added to `totalProducedThisTurn` via
  `this.totalProducedThisTurn.add(card.beginOwnTurnScript.receive)` and the unit is pushed
  to `contributedToAttackThisTurn`) but does **NOT** increment `maxAttack`. C++ port must
  replicate this asymmetry exactly or `maxAttack` will diverge in mid-action snapshots.

---

## maxDisrupt

**Computed at:** `prismata-engine.js:2663` (inside `StateHelper.update()`).

**Inputs:** Same as `maxAttack` own-unit loop. Specifically: `card.disruptPotential`, `inst.health + card.healthGained >= card.healthUsed`, `inst.charge + card.chargeGained >= card.chargeUsed`, same eligibility filter as `maxAttack` defense-phase path.

```javascript
// Inside the same health/charge eligibility block as maxAttack defense path:
this.maxDisrupt += card.disruptPotential;    // line 2663
```

**Supporting definition — `card.disruptPotential` getter (lines 1467–1472):**

```javascript
get disruptPotential() {
    if (this.targetAction === C.TARGETACTION_DISRUPT) {
        return this.targetAmount;
    }
    return 0;
}
```

**Notes:** Only incremented in the **defense phase** path (inside `ownStuffAfterDefensePhase`
eligibility, inside the health/charge check). No separate action-phase accumulation for
`maxDisrupt`. A unit contributes its `targetAmount` (the number of chill pips it delivers)
if it has `targetAction === 'disrupt'` and passes the health+charge check. Units without
a disrupt target action contribute 0. Note that Cryo Kronus's special case (line 2913)
applies only to `oppDisruptPotential` — there is no analogous own-side special case.

---

## maxSnipers

**Computed at:** `prismata-engine.js:2664–2668` (inside `StateHelper.update()`).

**Inputs:** Same eligibility filter + health/charge check as `maxDisrupt`. `card.targetAction === C.TARGETACTION_SNIPE` and `card.potentiallyMoreAttack`.

```javascript
// Inside the same health/charge eligibility block as maxDisrupt:
if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) {
        ++this.maxSnipers;    // line 2666
    }
}
```

**Supporting definition — `card.potentiallyMoreAttack` (lines 1412–1414):**

```javascript
this.potentiallyMoreAttack = false;
if (obj.hasOwnProperty('potentiallyMoreAttack') && !!obj.potentiallyMoreAttack) {
    this.potentiallyMoreAttack = true;
}
```

**Notes:** Only counts a unit as a sniper if it has BOTH `targetAction === 'snipe'` AND
`potentiallyMoreAttack === true`. The `potentiallyMoreAttack` flag is a static card
property from the card definition JSON (e.g. Tarsier has it). Units without the flag
(snipe-capable but whose snipe is their only attack contribution, like a hypothetical
pure sniper without attack from any other source) are not counted. This is the same
eligibility filter as `maxDisrupt` (defense-phase only, constructionTime ≤ 1, delay ≤ 1,
not dead, health/charge check). No action-phase accumulation.

---

## oppAttackPotential

**Computed at:** `prismata-engine.js:2541` (reset), accumulated at lines 2879, 2892, 2989.

**Inputs:** `StateHelper.update(state)` — opponent units (`inst.owner !== s.turn`), eligibility filter: `constructionTime ≤ 1, delay ≤ 1`, not lifespan-1 imminent doom, `!inst.dead`. Card properties: `beginOwnTurnScript`, `abilityScript`, `resonate`.

```javascript
// Opponent next-turn potential — eligibility filter (lines 2852–2853):
if (inst.constructionTime <= 1 && inst.delay <= 1 &&
    !(inst.lifespan === 1 && inst.constructionTime === 0 && inst.delay === 0)) {
    // ... (displayOppAttackPotential tracking) ...
    if (!inst.dead) {
        // beginOwnTurnScript attack contribution (line 2876–2881):
        if (card.beginOwnTurnScript !== null &&
            card.beginOwnTurnScript.receive.attack > 0) {
            pushToOppAttackers = true;
            this.oppAttackPotential += card.beginOwnTurnScript.receive.attack;   // line 2879
            this.oppGuaranteedAttack += card.beginOwnTurnScript.receive.attack;
        }
        // abilityScript attack contribution — subject to health/charge check (lines 2887–2893):
        if (inst.health + card.healthGained >= card.healthUsed &&
            inst.charge + card.chargeGained >= card.chargeUsed) {
            if (card.abilityScript !== null &&
                card.abilityScript.receive.attack > 0) {
                pushToOppAttackers = true;
                this.oppAttackPotential += card.abilityScript.receive.attack;    // line 2892
            }
        }
    }
}

// RESONATE resolution — opponent side (lines 2977–2996):
// After the main loop, for each inst in oppStuffNextTurn:
if (oppAnnihilate.hasOwnProperty(card.cardName)) {
    if (!wentOff.hasOwnProperty(card.cardName)) {
        this.oppAttackers = this.oppAttackers.concat(oppAnnihilate[card.cardName]);
        wentOff[card.cardName] = true;
    }
    this.oppAttackPotential += oppAnnihilate[card.cardName].length;              // line 2989
    this.oppGuaranteedAttack += oppAnnihilate[card.cardName].length;
}
```

**Notes:** Unlike the own-unit attack computation, the opponent path applies the same
eligibility filter regardless of phase (there is no defense/action-phase split for the
opponent side). The health/charge check applies to `abilityScript` attack but NOT to
`beginOwnTurnScript` attack (which is always guaranteed). Resonate (`card.resonate`)
units that match a present opposite-side unit have their count added to
`oppAttackPotential`. Dead units are excluded (the `!inst.dead` guard), but the outer
eligibility check (constructionTime/delay filter) runs before the dead check — meaning
`displayOppAttackPotential` can be set even for dead units with `attackPotential !== 0`.

---

## oppDisruptPotential

**Computed at:** `prismata-engine.js:2545` (reset), accumulated at lines 2905, 2914.

**Inputs:** Same opponent eligibility filter as `oppAttackPotential`. `card.targetAction === C.TARGETACTION_DISRUPT`, `card.targetAmount`, health/charge check. Special case: `card.cardName === 'Cryo Kronus'`.

```javascript
// Inside health/charge check block for opponent units (lines 2903–2915):
if (card.targetAction === C.TARGETACTION_DISRUPT) {
    pushToOppAttackers = true;
    this.oppDisruptPotential += card.targetAmount;           // line 2905
} else if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) {
        pushToOppAttackers = true;
        ++this.oppSnipers;
    }
}
// Special case outside the health/charge block (line 2913–2915):
if (card.cardName === 'Cryo Kronus') {
    this.oppDisruptPotential += 999;                         // line 2914
}
```

**Notes:** Cryo Kronus gets a hardcoded `+999` chill potential added unconditionally
(not subject to health/charge check) whenever it is alive and within the opponent's
eligibility window (constructionTime ≤ 1, delay ≤ 1, not doom-1, not dead per the outer
`if (!inst.dead)` guard). The 999 is a sentinel for "functionally unlimited chill" and
causes the chill display to show a chill icon unconditionally. There is no analogous
own-side special case for Cryo Kronus in `maxDisrupt`.

---

## oppSnipers

**Computed at:** `prismata-engine.js:2546` (reset), incremented at line 2909.

**Inputs:** Same opponent eligibility + health/charge check. `card.targetAction === C.TARGETACTION_SNIPE`, `card.potentiallyMoreAttack`.

```javascript
// Inside health/charge check block for opponent units (line 2906–2910):
} else if (card.targetAction === C.TARGETACTION_SNIPE) {
    if (card.potentiallyMoreAttack) {
        pushToOppAttackers = true;
        ++this.oppSnipers;    // line 2909
    }
}
```

**Post-computation — sniper defense reduction (lines 2998–3012):**

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

**Notes:** Same double-gate as `maxSnipers` — needs both `targetAction === 'snipe'` AND
`potentiallyMoreAttack`. The post-computation sniper defense reduction
(`myDefenseReductionFromOppSnipers`) is computed immediately after but is a separate
field not exported to the viewer's `GameState` JSON — it is internal to the JS
StateHelper (computed alongside `oppSnipers` and used by the bundle's own
defense-prediction display logic — never read by any renderer file, never exported to
the snapshot JSON, never touched by C++). Only own **defenders** (blocking units) with
health ≤ 3 are considered snipe targets; the reduction is sum of their health values up
to `oppSnipers` targets, sorted highest-health-first.

---

## whiteGoldEstimate / blackGoldEstimate

**Computed at:** `prismata-engine.js:8126–8127` via `computeEconEstimate(0)` / `computeEconEstimate(1)`.

**Inputs (closure captures `state`):** `state.phase`, `state.turn`, `state.table` (all insts), `state.whiteMana`, `state.blackMana`. Per-unit: `inst.owner`, `inst.constructionTime`, `inst.delay`, `inst.lifespan`, `inst.dead`, `inst.health`, `inst.charge`, `card.beginOwnTurnScript`, `card.abilityScript`, `card.abilityCost`, `card.abilitySac`, `card.goldResonate`, `card.cardName`.

**Full `computeEconEstimate` function (lines 7998–8101):**

```javascript
function computeEconEstimate(player) {
    const C = __require("C");
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
            if (goldAnnihilate[saviorResoName]) {            // always false in this branch
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

**Writer in output object (lines 8126–8127):**

```javascript
whiteGoldEstimate: computeEconEstimate(0),
blackGoldEstimate: computeEconEstimate(1)
```

**Notes:**

- Returns `[lowerBound, upperBound]` where the bounds differ only for ability-income units
  that have a cost or sac (`abilityCost.isEmpty === false` or `abilitySac.length > 0`
  or `selfsac === true`) — for those the income is optimistic but not guaranteed, so it
  only counts toward `econPotential` (upper) not `econPotentialLower` (lower).
  `beginOwnTurnScript` income always counts toward both bounds.
- Phase sensitivity: `isDefensePhase` is true only when `state.phase === 'defense'` AND
  it is the specified player's turn (`state.turn === player`). In other words, during P0's
  defense phase, `computeEconEstimate(0)` runs the defense path and
  `computeEconEstimate(1)` runs the action/confirm path — they use different logic.
- **`goldAnnihilate` dead branch**: In the non-defense-phase branch, `goldAnnihilate` is
  never populated (the `goldResonate` entries only go to `goldAnnihilateNext`). The check
  at line 8084 (`if (goldAnnihilate[saviorResoName])`) is therefore always false and is a
  no-op. Only `goldAnnihilateNext` contributes the resonate bonus in action/confirm phases.
- goldResonate (Savior Drone mechanic): `numDrones` counts the player's own Drones in
  the eligibility window. `goldAnnihilateNext[name]` collects units still under
  construction (constructionTime === 1 or delay === 1) whose `goldResonate` matches the
  Drone card name. Each such unit multiplies by numDrones and adds to the estimate.
- `currentGold` adds the player's current gold on hand (from their mana pool) so the
  estimate reflects what they'll have at the START of their next turn (income + carry).
- This function is a standalone closure inside `stateToCppJSON`. It is **not** part of
  `StateHelper` — it is computed fresh per snapshot on export, not cached in `state.helper`.

---

## boughtThisPhase

**Computed at:** `prismata-engine.js:7940` (inside `instToCardJSON()`).

**Inputs:** `inst.creatorIdFromBuyOrAbility` — set on `Inst` creation.

**Writer in `instToCardJSON` (lines 7925–7949):**

```javascript
function instToCardJSON(inst) {
    return {
        // ...
        boughtThisPhase:  inst.creatorIdFromBuyOrAbility >= 0,
        // ...
    };
}
```

**Set-true sites — `_runScript()` in `State` (lines 3733–3745):**

```javascript
if (scriptType === C.SCRIPTTYPE_BUY) {
    createdInst = this._createInst(this.cardNameToCard(temp.cardName), color, false, temp.buildTime, true, createIds[i][j]);
    inst.buyCreateIds[i][j] = createdInst.instId;
    createdInst.creatorIdFromBuyOrAbility = inst.instId;     // line 3736
} else if (scriptType === C.SCRIPTTYPE_BEGINOWNTURN) {
    // (sets creatorIdFromBeginTurn instead — see bornThisTurn)
    createdInst.creatorIdFromBeginTurn = inst.instId;
} else if (scriptType === C.SCRIPTTYPE_ABILITY) {
    createdInst = this._createInst(this.cardNameToCard(temp.cardName), color, false, temp.buildTime, temp.invuln, createIds[i][j]);
    inst.abilityCreateIds[i][j] = createdInst.instId;
    createdInst.creatorIdFromBuyOrAbility = inst.instId;     // line 3745
}
```

**Default (no creator) — `Inst` constructor (line 1710):**

```javascript
this.creatorIdFromBuyOrAbility = -1;
```

**Reset site — `_clearInstArrowIds()` (lines 4569), called at phase transition (line 4419):**

```javascript
inst.creatorIdFromBuyOrAbility = -1;   // line 4569
inst.creatorIdFromBeginTurn = -1;      // line 4570
```

`_clearInstArrowIds()` is called at line 4419 when `phase` transitions to `PHASE_CONFIRM`
(after the action phase ends and before MOVE_COMMIT is processed).

**Notes:** `boughtThisPhase` is `true` for any instance whose `creatorIdFromBuyOrAbility`
field is a non-negative integer (i.e., the instance was spawned by a BUY script or an
ABILITY script during the current action phase). The field stores the instId of the
creator unit, not a boolean. The exporter converts to boolean at read time.

Both SCRIPTTYPE_BUY and SCRIPTTYPE_ABILITY set this same field, so units created by
activated abilities (e.g. Plexo Cell spawning a Drone) have `boughtThisPhase === true`
just like purchased units. The reset happens at PHASE_CONFIRM transition, so snapshots
taken DURING the action phase will have the correct true/false state.

Per `types.ts`, this field is **NON-OPTIONAL** — must always be emitted (even when false).

---

## bornThisTurn

**Computed at:** `prismata-engine.js:7944` (inside `instToCardJSON()`).

**Inputs:** `inst.creatorIdFromBeginTurn` — set on `Inst` creation.

**Writer in `instToCardJSON` (line 7944):**

```javascript
bornThisTurn:     inst.creatorIdFromBeginTurn >= 0,
```

**Set-true site — `_runScript()` in `State` (line 3741):**

```javascript
} else if (scriptType === C.SCRIPTTYPE_BEGINOWNTURN) {
    C.ASSERT(createIds === null, 'Tried to give createIds for beginOwnTurnScript.');
    createdInst = this._createInst(this.cardNameToCard(temp.cardName), color, false, temp.buildTime, temp.invuln, this.nextInstId++);
    inst.beginOwnTurnCreateIds[i][j] = createdInst.instId;
    createdInst.creatorIdFromBeginTurn = inst.instId;        // line 3741
}
```

**Default (no creator) — `Inst` constructor (line 1711):**

```javascript
this.creatorIdFromBeginTurn = -1;
```

**Reset site:** Same `_clearInstArrowIds()` at line 4570 (same call site as `boughtThisPhase`).

**Notes:** `bornThisTurn` is `true` for instances spawned by a unit's `beginOwnTurnScript`
during the Swoosh phase (e.g. Robo Santa spawning gifts, Bloodrager tokens). These units
sort to the left of the play area alongside bought units in pile-sort. Stores the instId
of the spawning unit, converted to boolean by the exporter.

Unlike `boughtThisPhase`, this field is **optional** in `types.ts` (`boolean?`) — the
exporter always emits it (the `instToCardJSON` function always includes it), but C++ may
omit it when false per the types contract. The shipped bundle always emits it regardless.
