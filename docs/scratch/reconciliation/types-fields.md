# types-fields.md — All fields defined on GameState and CardInstance in types.ts

Source: `c:/libraries/prismata-ladder/prismata-ladder-site/src/components/game-renderer/types.ts`

---

## CardInstance fields

| Field | TypeScript type | Notes |
|---|---|---|
| `instId` | `number` | Unique per-instance identifier |
| `cardName` | `string` | Card type name (display name) |
| `owner` | `number` | 0 or 1 |
| `health` | `number` | Current HP |
| `damage` | `number` | Damage taken this turn |
| `role` | `string` | 'default' \| 'assigned' \| 'sellable' \| 'inert' |
| `deadness` | `string` | 'alive' \| 'selfsacced' \| 'sacced' \| 'blocked' \| 'meleed' \| 'breached' \| 'sniped' \| 'autosniped' \| 'aged' |
| `constructionTime` | `number` | Turns remaining under construction (0 = ready) |
| `charge` | `number` | Charge counter |
| `delay` | `number` | Delay counter |
| `lifespan` | `number` | Turns remaining (-1 = infinite) |
| `disruptDamage` | `number` | Chill damage accumulated (m_currentChill in C++) |
| `blocking` | `boolean` | Currently assigned as blocker |
| `boughtThisPhase` | `boolean` | True if inst was created by buy or ability this phase |
| `bornThisTurn` | `boolean?` | True if spawned by a begin-turn script (Robo Santa, Bloodrager etc.) |
| `autoClicked` | `boolean?` | True if unit has a free no-cost/no-target/no-sac ability |
| `isFragile` | `boolean?` | True if unit is fragile (dies to any damage) |
| `cardType` | `string?` | 'unit' (default) or 'spell' |
| `defaultBlocking` | `boolean?` | True if unit defaults to blocking |

---

## GameState fields

| Field | TypeScript type | Notes |
|---|---|---|
| `whiteMana` | `string` | P0 mana string (digits=gold, G=green, B=blue, C=red, H=energy) |
| `blackMana` | `string` | P1 mana string |
| `turn` | `number` | 0 = P0's turn, 1 = P1's turn |
| `numTurns` | `number` | Turn counter (used for timer index) |
| `phase` | `string` | 'defense' \| 'action' \| 'confirm' |
| `glassBroken` | `boolean?` | True during breach (action phase with glass broken) |
| `incomingAttack` | `number?` | Opponent's attack mana (incoming damage during defense phase) |
| `maxAttack` | `number?` | Turn player's attack potential if they finished their turn now |
| `maxDisrupt` | `number?` | Turn player's chill potential |
| `maxSnipers` | `number?` | Snipers among turn player's potential attackers |
| `oppAttackPotential` | `number?` | Predicted attack for the non-turn player next turn |
| `oppDisruptPotential` | `number?` | Predicted chill for the non-turn player next turn |
| `oppSnipers` | `number?` | Snipers among non-turn player's predicted attackers |
| `cards` | `string[]` | Purchasable card display names |
| `whiteTotalSupply` | `number[]` | Total supply counts per card (P0) |
| `blackTotalSupply` | `number[]` | Total supply counts per card (P1) |
| `whiteSupplySpent` | `number[]` | Supply spent per card (P0) |
| `blackSupplySpent` | `number[]` | Supply spent per card (P1) |
| `table` | `CardInstance[]` | All unit instances in play |
| `whiteGoldEstimate` | `[number, number]?` | [min, max] gold for next turn (P0) |
| `blackGoldEstimate` | `[number, number]?` | [min, max] gold for next turn (P1) |

---

## Other exported interfaces (not CardInstance/GameState — out of scope for the reconciliation table)

- `CardMeta` — static per-card-type metadata (read from cardMetaMap, not the game state). **Overlaps with CardInstance on `isFragile`, `cardType`, `defaultBlocking`** — these are duplicated on both interfaces. The renderer reads them primarily via `cardMeta`, but they remain part of the CardInstance contract per types.ts; see in-scope-fields.md for the resolution.
- `CardMetaMap` — map of cardName → CardMeta
- `VisualState` — computed visual representation (internal to renderer, never in game state JSON)
- `ReplayTimingData` — timer data from replay JSON (separate from game state)
- `PlayerBarData` — player identity data (name, portrait, badges)
