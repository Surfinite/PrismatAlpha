# in-scope-fields.md — In-scope field list for C++ replay export reconciliation

All fields on `GameState` and `CardInstance` (from `types.ts`) that are consumed by the
game-renderer files. This is the contract the C++ snapshot exporter must satisfy.

**Structural** = direct property of the engine's game state; value comes straight from the engine.
**Derived** = computed from the state (requires running logic over units or the game tree).

Fields marked `OUT OF SCOPE — puzzle only` appear only in `PuzzleController.ts` (which is
excluded from this task). No such fields were found — every field defined in types.ts is read
by at least one of the 10 renderer files.

---

## GameState fields — ALL IN SCOPE

### Structural GameState fields (7)

- `whiteMana` (structural) — P0 mana resource string. Read by BoardRenderer (attack calculation, player bar), ResourceBar, PlayerBar. C++ maps from GameState's mana resources.
- `blackMana` (structural) — P1 mana string. Same consumers.
- `turn` (structural) — Which player's turn (0 or 1). Read by BoardRenderer for all turn-sensitive display logic.
- `numTurns` (structural) — Turn counter (used to index per-turn timer data from ReplayTimingData). Read by BoardRenderer.
- `phase` (structural) — Game phase string: 'defense' | 'action' | 'confirm'. Read by BoardRenderer, RowView, PileView, UnitCard, visual-state, pile-sort, auto-clicks. NOTE: the C++ export should emit 'breach' as a phase variant too — BoardRenderer handles `phase === 'breach'` in multiple places (big sword, turn indicator, player bar).
- `glassBroken` (structural) — True when in breach (action phase + glass broken flag). Read by BoardRenderer and auto-clicks. C++ equivalent: `glassBroken` flag in GameState.
- `table` (structural) — Array of all CardInstance objects in play. Read by BoardRenderer and auto-clicks directly; all other renderer files receive unit arrays filtered from it.

### Structural GameState fields — supply/buy panel (5)

These are passed wholesale to BuyPanel.update() by BoardRenderer. BuyPanel.ts is not in the 10-file scope list, but BoardRenderer consumes them.

- `cards` (structural) — Array of purchasable card display names. Structural — comes from the deck definition.
- `whiteTotalSupply` (structural) — Total supply per card slot (P0). Structural — derived from card rarity rules or deck definition.
- `blackTotalSupply` (structural) — Total supply per card slot (P1).
- `whiteSupplySpent` (structural) — Supply spent per slot (P0). Structural — count of purchased instances.
- `blackSupplySpent` (structural) — Supply spent per slot (P1).

### Derived GameState fields (9)

These require computation over the game state. They are the high-fidelity-risk fields for C++ export.

- `incomingAttack` (derived) — Opponent's committed attack mana (remaining incoming damage during defense phase). Read by BoardRenderer (getPlayerAttack, big sword) and auto-clicks (autoDefense). Computation: count attack mana 'A' characters in the attacker's mana string.
- `maxAttack` (derived) — Turn player's attack potential if they ended their turn now. Read by BoardRenderer in getPlayerAttack(). Computation: sum attack of all ready attackers including those not yet assigned.
- `maxDisrupt` (derived) — Turn player's chill potential. Read by BoardRenderer in getPlayerChill(). Computation: sum chill targetAmount of all ready chilling units.
- `maxSnipers` (derived) — Count of snipers among the turn player's potential attackers. Read by BoardRenderer (getPlayerAttack, star suffix). Computation: count units with targetAction=snipe among potential attackers.
- `oppAttackPotential` (derived) — Predicted attack for the non-turn player next turn. Read by BoardRenderer. Computation: StateHelper equivalent — sum attack of non-turn player's live, non-delayed units.
- `oppDisruptPotential` (derived) — Predicted chill for the non-turn player next turn. Read by BoardRenderer (getPlayerChill, with fallback computation). Computation: sum chill targetAmount of non-turn player's live, non-delayed chilling units.
- `oppSnipers` (derived) — Snipers among non-turn player's predicted attackers. Read by BoardRenderer. Computation: count snipe-targeting units among non-turn player's potential attackers.
- `whiteGoldEstimate` (derived) — [min, max] gold P0 will have next turn. Read by BoardRenderer (passed to PlayerBar) and ResourceBar. Computation: current gold plus income from all live auto-gold units (Drones, Engineers, etc.), minus estimated spend — or just [income, income] if not spending.
- `blackGoldEstimate` (derived) — [min, max] gold P1 will have next turn. Same computation for P1.

---

## CardInstance fields — ALL IN SCOPE

### Structural CardInstance fields (13)

- `instId` (structural) — Unique instance ID. Read by BoardRenderer (hit areas), PileView (getInstIds), UnitCard (stored), pile-sort (tiebreak), auto-clicks.
- `cardName` (structural) — Card type name. Read by RowView (grouping), PileView (cardName), UnitCard (art loading, name label), auto-clicks (special-case names), StatusOverlay (special-case names).
- `owner` (structural) — 0 or 1. Read by BoardRenderer (filtering), RowView (gap logic), PileView (ownerIsTurnPlayer), visual-state (isBottomPlayer), pile-sort (ourTurnAction), auto-clicks.
- `health` (structural) — Current HP. Read by BoardRenderer (defense computation), visual-state (chill check), pile-sort (tiebreaks), auto-clicks (breach ordering, defense value), StatusOverlay (fragile HP display).
- `damage` (structural) — Damage taken this turn. Read by BoardRenderer (highlight urgency), visual-state (damage overlays, skull), pile-sort.
- `role` (structural) — 'default' | 'assigned' | 'sellable' | 'inert'. Read by BoardRenderer (highlight logic), RowView (big-gap separator), PileView (big-gap), visual-state (cover/shading), pile-sort (cameOnTableThisPhase, ROLE_ASSIGNED/ROLE_SELLABLE), auto-clicks (autoWork filter).
- `deadness` (structural) — Dead/alive state string. Read by BoardRenderer (hit-area filtering), PileView (alive count), visual-state (isDead), auto-clicks (eligibility checks).
- `constructionTime` (structural) — Turns remaining under construction. Read by BoardRenderer (computeTotalDefense blocks construction units), visual-state (alpha + cover), pile-sort (construction sort key), auto-clicks (breach secondary pass), StatusOverlay (build time display).
- `charge` (structural) — Charge counter. Read by pile-sort, auto-clicks (special-case charge checks), StatusOverlay (charge display).
- `delay` (structural) — Delay counter. Read by BoardRenderer (computeChill skips delayed units), pile-sort, StatusOverlay (delay icon).
- `lifespan` (structural) — Remaining lifespan (-1 = infinite). Read by pile-sort, auto-clicks (lifespan-1 blockers, value-of-unit), StatusOverlay (doom icon).
- `disruptDamage` (structural) — Chill damage accumulated on this unit. Read by BoardRenderer (computeChill), visual-state (isFullyChilled), pile-sort (canBlockAtStartOfPhase), StatusOverlay (chill icon display).
- `blocking` (structural) — Currently assigned as blocker. Read by BoardRenderer (computeDefense), visual-state (BACK_BLOCK frame), pile-sort (canBlockAtStartOfPhase, blocking sort key), auto-clicks (eligible blocker detection).

### Structural CardInstance fields with dual CardMeta overlap (3)

These are defined on CardInstance in types.ts AND as fields on CardMeta. The renderer reads them primarily via CardMeta (passed as a separate argument), but they appear on the CardInstance interface and must be present in the exported JSON.

- `isFragile` (structural) — True if fragile. Read directly on inst by auto-clicks (`inst.isFragile`). Also read via cardMeta.isFragile in pile-sort, visual-state (indirectly), StatusOverlay. Must be on the CardInstance export.
- `cardType` (structural) — 'unit' | 'spell'. Defined on CardInstance. Accessed via cardMeta.cardType in visual-state and StatusOverlay. The CardInstance export should include this for completeness, matching the contract.
- `defaultBlocking` (structural) — True if unit defaults to blocking. Defined on CardInstance. Accessed via cardMeta.defaultBlocking in visual-state. Should be on the CardInstance export.

### Derived CardInstance fields (2)

- `boughtThisPhase` (derived) — True if bought or click-created on the current turn (inst.creatorIdFromBuyOrAbility >= 0 in engine). Read by pile-sort (cameOnTableThisPhase). Computation: requires tracking whether the instance was created by a buy or ability action during the current turn.
- `bornThisTurn` (derived) — True if spawned by a begin-turn script. Read by pile-sort (cameOnTableThisPhase). Computation: requires tracking whether the instance was created by a beginTurn script (inst.creatorIdFromBeginTurn >= 0).

### Auto-clicks-only CardInstance field (1)

- `autoClicked` (structural/derived) — True if unit has a free no-cost/no-target/no-sac ability. Read only by auto-clicks.ts (autoWork). This is a per-card-type property derived from the card definition's abilityScript, not from live game state. It belongs on CardInstance for replay purposes but its value does not change during play — it is effectively a static card property. C++ can populate it once from cardLibrary.

---

## Summary counts

- **Total GameState fields in types.ts**: 20
- **Structural GameState**: 12 (7 core + 5 supply/buy)
- **Derived GameState**: 9 (incomingAttack, maxAttack, maxDisrupt, maxSnipers, oppAttackPotential, oppDisruptPotential, oppSnipers, whiteGoldEstimate, blackGoldEstimate) — NOTE: incomingAttack is simpler to derive than the others (just the attacker's A-count mana), the other 8 require running StateHelper-equivalent lookahead logic.
- **Fields out of scope (puzzle-only)**: 0

- **Total CardInstance fields in types.ts**: 19
- **Structural CardInstance**: 16 (13 pure + 3 CardMeta-overlap)
- **Derived CardInstance**: 2 (boughtThisPhase, bornThisTurn)
- **Static card-property CardInstance field**: 1 (autoClicked — from card definition, not live state)
- **Fields out of scope (puzzle-only)**: 0

---

## Key risk fields for C++ implementation

The 8 StateHelper-style derived fields (all except `incomingAttack`) require running an attack/chill potential calculation over the unit table. These are the fields most likely to diverge between C++ and JS if the logic is not ported exactly:

1. `maxAttack` — potential attack if turn ended now
2. `maxDisrupt` — potential chill if turn ended now
3. `maxSnipers` — sniper count among potential attackers
4. `oppAttackPotential` — predicted next-turn attack
5. `oppDisruptPotential` — predicted next-turn chill
6. `oppSnipers` — sniper count among predicted attackers
7. `whiteGoldEstimate` — [min, max] predicted gold
8. `blackGoldEstimate` — [min, max] predicted gold

`boughtThisPhase` and `bornThisTurn` are also derived but their computation is simpler:
track `creatorIdFromBuyOrAbility` and `creatorIdFromBeginTurn` in the C++ GameState.
