# Category 1: Game Fundamentals

## Game Overview
> Source: Wikipedia — Prismata

Prismata is a turn-based, perfect-information strategy game. Two players take turns purchasing units from a shared pool — the "base set" of 11 units available every game, plus a "random set" of 5-8 units randomly selected from ~105 competitive units. There is no luck, no hidden information, and no deck building. The goal is to destroy all opposing units.

Key properties:
- Perfect information: both players see everything
- No randomness: outcomes are fully deterministic
- Asymmetric starts: Player 1 goes first but Player 2 gets an extra Drone to compensate
- Win condition: destroy all enemy units

Development began in late 2010 by part-time MIT students. Originally a physical prototype called MCDS (Magic-Chess-Dominion-Starcraft). The game is frequently described as "turn-based StarCraft without a map" or "Hearthstone with workers and build orders instead of decks."

> Source: Dominion Strategy Forum — amalloy (Dec 2014)

"They used to call it MCDS, for Magic-Chess-Dominion-Starcraft, and you can really see the influence of all four of those games clearly. It's like Starcraft in that you're balancing economy, technology, attacking, and defending. Like chess, every turn can be planned ahead of time, if you can think fast enough (hint: you can't). Instead of constructed decks, the game starts Dominion-style, with similar starting boards and a 'base set' of 11 units. Like MtG, you're building up a board of attackers and defenders."

---

## Resources
> Source: Official Prismata Rules (blog.prismata.net, Aug 2014)

There are five resources in Prismata: gold, energy, green, blue, and red.

| Resource | Persistence | Produced By | Notes |
|----------|-------------|-------------|-------|
| **Gold** | Carries over | Drone (1/turn) | Primary resource. Few units lack a gold cost. |
| **Energy** | Decays end of turn | Engineer (1/turn) | Used for economic units (Drones). |
| **Green** (Gaussite) | Carries over | Conduit (1/turn) | Cheapest, least committal tech. Can stockpile. |
| **Blue** (Behemium) | Decays end of turn | Blastforge (1/turn) | Best for defense (Walls). |
| **Red** (Replicase) | Decays end of turn | Animus (2/turn) | Best for attack (Tarsiers, Rhinos). Expensive to fully utilize. |

**Key rule**: Gold and Green carry over. Energy, Blue, Red, and Attack decay at end of turn if unspent.

> Source: The Standard Style (307th, Prismata Library)

"Red and Blue are especially important to spend each turn, since they are valuable and disappear at the end of your turn if unspent. Wasting Red or Blue is occasionally correct, but not very often."

"As a rule of thumb, having one or two Gold or Green left over at the end of your turn is fine, but try to avoid floating three or more."

---

## Turn Structure & Phases
> Source: Wiki — Rules (Comprehensive Rules)

Each player's turn has two main phases:

### 1. Defense Phase (conditional)
If your opponent ended their turn with Attack Power remaining, all of that Attack Power is converted into damage and you must choose Blocking units in any order until all damage has been assigned. If a unit does not take lethal damage, that damage expires at the start of the next turn unless the unit has Fragile.

### 2. Action Phase
At the start of the action phase, units with "at the start of your turn" actions perform those actions now. During the action phase, you may buy any number of units if you can pay their costs, and you may click any units that can be clicked to perform an action (only once per click-unit per turn).

### Start-of-Turn Effects (Swoosh)
- All chill is removed from all units
- Lifespan decremented by 1; units at 0 lifespan die
- Exhaust counters decrement by 1
- Construction delay decrements by 1; units finishing construction become active
- Start-of-turn abilities trigger (auto-attack, resource generation, etc.)

---

## Combat Mechanics
> Source: Official Prismata Rules (blog.prismata.net)

Attack power is pooled from all attacking units. When you end your turn:

**If your attack < opponent's total defense:** The opponent defends — they choose which blockers take damage. The final unit may absorb partial damage (non-lethal).

**If your attack >= opponent's total defense:** BREACH. All opponent blockers are destroyed. Excess damage is assigned by the ATTACKER to any enemy units of their choice. The attacker targets highest-value, lowest-HP units first (Tarsiers, Drones, tech buildings).

> Source: Wiki — Rules

"A clicked unit cannot block (if it was originally blocking) until the start of your next turn."

"During a Breach, units with Buildtime cannot be damaged. This restriction is removed if all remaining targets cannot have damage applied ('Overkill')."

---

## Unit Mechanics
> Source: Official Rules + Wiki Unit Mechanics

### Core Properties
- **Health**: Hit points. Non-fragile units heal to full after surviving damage.
- **Blocker**: Can contribute HP to defense. Cannot block while ability is used.
- **Prompt**: Zero build time. Can block immediately when purchased.
- **Fragile**: Does NOT heal after taking damage. Permanent HP reduction. Cannot absorb.
- **Frontline**: Can be directly targeted by opponent even when blockers exist.
- **Build Time**: Turns after purchase before unit becomes active. Under construction = invulnerable.
- **Lifespan**: Unit dies when lifespan reaches 0 at start of owner's turn.
- **Stamina**: Number of times click ability can be used before depleted.
- **Exhaust**: Turns the unit's effect/ability is disabled after triggering.
- **Chill**: Prevents blocking. Unit with chill >= HP is "frozen" and cannot block.
- **Supply**: Max copies each player can buy. 1=Legendary, 4=Epic, 10=Rare, 20=Common.

### Clicking Units
> Source: Official Rules (blog.prismata.net)

"A unit can only be clicked once per turn. On the battlefield, units that have already been clicked are indicated by dashed lines placed over them. A clicked unit cannot block (if it was originally blocking) until the start of your next turn."

### Unit Lifecycle
1. **Purchased**: Resources spent. Unit enters construction (golden, invulnerable).
2. **Under Construction**: Build time counts down each turn. Cannot act, cannot be targeted (except during overkill).
3. **Active**: Can use abilities, block, produce resources.
4. **Destroyed**: HP reduced to 0, lifespan expires, or sacrificed.

---

## Starting Positions
> Source: PRISMATA_REFERENCE.md + Official Rules

- Player 1: 6 Drones, 2 Engineers (goes first)
- Player 2: 7 Drones, 2 Engineers (extra Drone compensates for going second)

---

## Game Phases (Detailed)
> Source: Foxclear — Beginner's Strategy Guide: Economy (wiki)

A typical game breaks down into 6 phases:

### Phase 1: Develop Your Economy
Expand economy by buying Drones and Engineers. "You will try not to waste your gold or energy resources as you can easily fall behind for the whole game if you do so."

### Phase 2: Prepare the Battle
Focus shifts to getting Green, Blue, or Red tech. "You will also try not to waste GBR as they are pretty costly, particularly B and R that deplete at the end of the turn." Economy stabilizes by end of this phase.

### Phase 3: Set Up Absorption
"Both players' attack numbers are pretty low, therefore easy to absorb." Get the biggest absorber when it can absorb a decent amount. Can still expand economy here.

### Phase 4: Over the Barrier — All Out Attack
Both players now have more damage than the absorber can absorb. "You should not expand your economy anymore, you should concentrate on defending your opponent's attack and developing your own. Do not defend more than necessary!"

### Phase 5: Under Pressure
"The damage numbers of both players is going to rise. At some point, it will even be difficult to buy a single attacker more while still defending to prevent a breach." May need to buy Forcefields, hold Drones, or leave Steelsplitters on defense. Watch Wall supply.

### Phase 6: Crumbling Defenses
"One or both players will be unable to defend and will get breached." During breach, focus on low-HP attackers (Tarsiers, Shadowfangs), economy units (Drones), and high-damage/low-health units (Arka Sodara).

### Phase 7: Draw
Can occur when both players breached and most attack forces destroyed while blue-health units remain. "Special mention to Blastforge which, with its 3 blue health can obtain a draw if there is only 2 attack or less remaining."

---

## Threat Types (Detailed)
> Source: Foxclear — Beginner's Strategy Guide: Defending Threat or Breachproof (wiki)

**Fake threat**: Units that can't actually attack. "If a single Animus powers 3 Perforators, then one of them will not be able to attack — 1 of this threat is fake."

**Dying threat**: Units that will be killed by your own attack before they can attack you. Example: Rhino used as soak. "Be careful — be sure that your attack actually kills or shuts off the threatening unit no matter how your opponent defends."

**Fake freeze threat**: Excess chill that can't be efficiently applied. "If your opponent has Nivo Charge and your highest health defender is a Wall, then your opponent's actual freeze threat is the health of your Wall, meaning 2 of the 5 is actually fake freeze threat."

**Absorber threat**: Clickable absorbers like Omega Splitter. "Usually, your opponent will want to keep them on defense, as absorbing has bigger value than attacking. But it is usually real threat and needs to be defended."

**Real threat**: Everything else. Defend against it or get breached.

---

## Player Asymmetry Details
> Source: Prismata Blog — Balancing Openings series + Vendium Scrap design article

At 1800+ rating, win rates are approximately:
- **Player 1**: 48.6%
- **Player 2**: 50.8%
- **Draw**: 0.6%

P2's extra Drone enables exclusive openings (Natural Conduit, Fastimus) that P1 cannot execute. Lunarch addressed first-mover advantage through unit design rather than asymmetric rules.

---

## Branching Factor
> Source: Developer analysis

Prismata's branching factor varies dramatically:
- Simple turns (buy Drones): ~2-5 options
- Complex mid-game turns (multiple abilities + purchases): ~100-1000s options
- Defense phase: usually forced or near-forced

Unlike chess (~35 average branching factor), Prismata's variable branching means some turns are trivially simple while others have massive option spaces.

---

## Hotkey: Q Defense
> Source: Beginner's strategy guide (wiki)

"By pressing Q while defending, the AI makes the defense for you! This is called Q defense and it is quite accurate: it will use the best absorber as your absorber, and will prioritize low value units for soak."
