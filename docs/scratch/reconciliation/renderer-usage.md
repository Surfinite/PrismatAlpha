# renderer-usage.md — Field usage matrix across game-renderer files

Rows = fields on `GameState` and `CardInstance` as defined in `types.ts`.
Columns = renderer files examined (the 10 listed in the task spec, plus StatusOverlay.ts which
is called by UnitCard.ts and directly reads CardInstance fields).

`read` = the file accesses this field.
`-` = file does not access this field.

PuzzleController.ts is excluded per task spec — fields that appear ONLY there are marked `OUT OF SCOPE — puzzle only`.

---

## Legend for column abbreviations

| Abbrev | File |
|---|---|
| BR | BoardRenderer.ts |
| BV | BoardView.ts |
| RB | ResourceBar.ts — defined but **never updated** in BoardRenderer; instances stay invisible. No `read` marks expected. |
| PB | PlayerBar.ts |
| RV | RowView.ts |
| PV | PileView.ts |
| UC | UnitCard.ts |
| VS | visual-state.ts |
| PS | pile-sort.ts |
| AC | auto-clicks.ts |
| SO | StatusOverlay.ts (called from UnitCard.ts; reads CardInstance fields directly) |

---

## GameState fields

| Field | BR | BV | RB | PB | RV | PV | UC | VS | PS | AC | SO | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `whiteMana` | read | - | - | read | - | - | - | - | - | - | - | BR reads for attack parsing and passes to PB.update(mana,...). ResourceBar.update() is defined but never called — BR creates topResources/bottomResources at lines 556-596 then leaves them invisible; data flows only to PlayerBar. |
| `blackMana` | read | - | - | read | - | - | - | - | - | - | - | BR reads for attack parsing and passes to PB.update() |
| `turn` | read | - | - | - | - | - | - | - | - | - | - | BR reads as `gameState.turn`, passes `turnPlayer` downstream |
| `numTurns` | read | - | - | - | - | - | - | - | - | - | - | BR reads `gameState.numTurns` for timer index in static-timing path |
| `phase` | read | - | - | read | read | read | read | read | read | read | - | BR destructures it; passes as string to BV.update(), RowView.update(), PileView.update(), UnitCard.update(), VS.computeVisualState(), pile-sort, AC.pressQ() |
| `glassBroken` | read | - | - | read | - | - | - | - | - | read | - | BR reads for player bar update and big sword; AC reads for autoBreach branch |
| `incomingAttack` | read | - | - | - | - | - | - | - | - | read | - | BR reads in getPlayerAttack(); AC reads for autoDefense |
| `maxAttack` | read | - | - | - | - | - | - | - | - | - | - | BR reads in getPlayerAttack() |
| `maxDisrupt` | read | - | - | - | - | - | - | - | - | - | - | BR reads in getPlayerChill() |
| `maxSnipers` | read | - | - | - | - | - | - | - | - | - | - | BR reads in getPlayerAttack() |
| `oppAttackPotential` | read | - | - | - | - | - | - | - | - | - | - | BR reads in getPlayerAttack() |
| `oppDisruptPotential` | read | - | - | - | - | - | - | - | - | - | - | BR reads in getPlayerChill() |
| `oppSnipers` | read | - | - | - | - | - | - | - | - | - | - | BR reads in getPlayerAttack() |
| `cards` | read | - | - | - | - | - | - | - | - | - | - | BR passes gameState to BuyPanel.update(gameState, cardMetaMap) |
| `whiteTotalSupply` | read | - | - | - | - | - | - | - | - | - | - | BR passes gameState to BuyPanel.update() |
| `blackTotalSupply` | read | - | - | - | - | - | - | - | - | - | - | BR passes gameState to BuyPanel.update() |
| `whiteSupplySpent` | read | - | - | - | - | - | - | - | - | - | - | BR passes gameState to BuyPanel.update() |
| `blackSupplySpent` | read | - | - | - | - | - | - | - | - | - | - | BR passes gameState to BuyPanel.update() |
| `table` | read | - | - | - | - | - | - | - | - | read | - | BR destructures it and filters by owner; AC reads `gameState.table` |
| `whiteGoldEstimate` | read | - | - | read | - | - | - | - | - | - | - | BR passes to PB.update(...). ResourceBar.update(mana, goldEstimate) is defined but the RB instances are never updated/visible in BR (see whiteMana note). |
| `blackGoldEstimate` | read | - | - | read | - | - | - | - | - | - | - | BR passes to PB.update() for P1 |

---

## CardInstance fields

| Field | BR | BV | RB | PB | RV | PV | UC | VS | PS | AC | SO | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `instId` | read | - | - | - | - | read | read | - | read | read | - | BR walks cards to find instId; PV.getInstIds(); UC stores `this._instId = inst.instId`; PS uses for tiebreak; AC reads inst.instId |
| `cardName` | - | - | - | - | read | read | read | - | - | read | read | RV groups by inst.cardName; PV sets pile.cardName; UC loads art by cardName; AC checks inst.cardName for special cases; SO checks inst.cardName |
| `owner` | read | - | - | - | read | read | - | read | read | read | - | BR filters by owner; RV reads insts[0]?.owner; PV reads instances[0]?.owner; VS reads inst.owner; PS reads a.owner; AC reads inst.owner |
| `health` | read | - | - | - | - | - | - | read | read | read | read | BR uses in computeDefense/computeTotalDefense; VS reads inst.health for chill check; PS reads inst.health; AC reads inst.health; SO shows inst.health count for fragile |
| `damage` | read | - | - | - | - | - | - | read | read | - | - | BR in updateHighlights (unit.damage > 0); VS reads inst.damage; PS reads inst.damage |
| `role` | read | - | - | - | read | read | - | read | read | read | - | BR in updateHighlights checks unit.role; RV checks i.role === 'sellable'; PV checks i.role === 'sellable'; VS reads inst.role; PS reads a.role; AC reads inst.role |
| `deadness` | read | - | - | - | - | read | - | read | - | read | - | BR filters alive/dead; PV checks instances[i].deadness; VS reads inst.deadness; AC reads inst.deadness |
| `constructionTime` | read | - | - | - | - | - | - | read | read | read | read | BR in computeTotalDefense checks constructionTime > 0; VS reads inst.constructionTime; PS reads a.constructionTime; AC reads inst.constructionTime; SO reads inst.constructionTime |
| `charge` | - | - | - | - | - | - | - | - | read | read | read | PS reads a.charge; AC reads inst.charge; SO shows charge count |
| `delay` | read | - | - | - | - | - | - | - | read | - | read | BR in computeChill checks delay > 0; PS reads inst.delay; SO shows delay count |
| `lifespan` | - | - | - | - | - | - | - | - | read | read | read | PS reads inst.lifespan; AC reads inst.lifespan; SO shows lifespan (doom) count |
| `disruptDamage` | read | - | - | - | - | - | - | read | read | - | read | BR in computeChill; VS reads inst.disruptDamage; PS reads inst.disruptDamage in canBlockAtStartOfPhase; SO shows disruptDamage |
| `blocking` | read | - | - | - | - | - | - | read | read | read | - | BR in computeDefense/computeTotalDefense; VS reads inst.blocking; PS reads inst.blocking; AC reads inst.blocking |
| `boughtThisPhase` | - | - | - | - | - | - | - | - | read | - | - | PS reads inst.boughtThisPhase in cameOnTableThisPhase() |
| `bornThisTurn` | - | - | - | - | - | - | - | - | read | - | - | PS reads inst.bornThisTurn in cameOnTableThisPhase() |
| `autoClicked` | - | - | - | - | - | - | - | - | - | read | - | AC reads inst.autoClicked in autoWork() |
| `isFragile` | - | - | - | - | - | - | - | - | read | read | read | PS reads meta.isFragile (CardMeta); AC reads inst.isFragile; SO reads inst.isFragile |
| `cardType` | - | - | - | - | - | - | - | read | - | - | read | VS reads cardMeta.cardType (CardMeta field, not CardInstance); SO reads cardMeta.cardType. NOTE: `cardType` on CardInstance is also defined in types.ts — it mirrors the card definition. Both VS and SO access it via cardMeta, but the types.ts field on CardInstance is in scope as part of the contract. |
| `defaultBlocking` | - | - | - | - | - | - | - | read | - | - | - | VS reads cardMeta.defaultBlocking. NOTE: `defaultBlocking` is defined on CardInstance in types.ts AND on CardMeta. VS accesses it via the cardMeta argument (Partial<CardMeta>). |

---

## Notes on access patterns

1. **Destructuring**: BR destructures `const { table, phase } = gameState` at line 823 — these are captured.
2. **Passthrough via function args**: `phase` and `turnPlayer` (derived from `gameState.turn`) are passed as plain strings/numbers to BV, RV, PV, UC, VS, and PS. They never access `gameState` directly — they receive the extracted value.
3. **BuyPanel passthrough**: `gameState.cards`, `whiteTotalSupply`, `blackTotalSupply`, `whiteSupplySpent`, `blackSupplySpent` are passed wholesale to `BuyPanel.update(gameState, cardMetaMap)`. BuyPanel.ts is not in the listed scope files, but BR clearly reads these fields by forwarding the entire gameState object.
4. **CardMeta vs CardInstance for `isFragile`, `cardType`, `defaultBlocking`**: These fields exist on both `CardInstance` (types.ts) and `CardMeta`. The renderer accesses them via the `cardMeta` argument (Partial<CardMeta>) in VS, PS, SO. The CardInstance versions are part of the contract but are cross-checked against CardMeta in most paths. `isFragile` on CardInstance is directly read by AC (`inst.isFragile`).
5. **StatusOverlay**: Not in the original 10-file list but called by UnitCard.ts and reads CardInstance fields directly. Included for completeness.
