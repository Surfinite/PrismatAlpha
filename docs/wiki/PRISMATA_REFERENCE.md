# Prismata Game Reference

> Curated from the Prismata Wiki (448 pages). Intended as a compact knowledge base for AI development and engine verification.

## Table of Contents

1. [Game Overview](#game-overview)
2. [Resources](#resources)
3. [Turn Structure & Phases](#turn-structure--phases)
4. [Unit Mechanics](#unit-mechanics)
5. [Base Set Units](#base-set-units)
6. [Defense Concepts](#defense-concepts)
7. [Breach Mechanics](#breach-mechanics)
8. [Chill & Freeze](#chill--freeze)
9. [Strategy Fundamentals](#strategy-fundamentals)
10. [Glossary](#glossary)
11. [Advanced Units Quick Reference](#advanced-units-quick-reference)

---

## Game Overview

Prismata is a turn-based perfect-information strategy card game by Lunarch Studios. Two players take turns purchasing units and using abilities to build attack, defend their units, and ultimately destroy all of their opponent's units. There is no luck, no hidden information, and no deck building — every game uses the same 11 base set units plus 8 randomly selected advanced units.

Key properties:
- **Perfect information**: Both players see everything
- **No randomness**: Outcomes are fully deterministic
- **Asymmetric starts**: Player 1 goes first but Player 2 gets an extra Drone to compensate
- **Random set**: Each game uses base set + 8 random advanced units (from a pool of ~105 competitive units)
- **Win condition**: Destroy all enemy units

---

## Resources

Six resources are used to purchase units:

| Resource | Icon | Persistence | Produced By | Notes |
|----------|------|-------------|-------------|-------|
| **Gold** | gold | Carries over | Drone (1/turn) | Primary resource. Few units lack a gold cost. |
| **Energy** | energy | **Decays** end of turn | Engineer (1/turn) | Used for economic units (Drones). |
| **Green** (Gaussite) | green | Carries over | Conduit (1/turn) | Tech resource. Can be stockpiled. |
| **Blue** (Behemium) | blue | **Decays** end of turn | Blastforge (1/turn) | Tech resource. Best for defense. |
| **Red** (Replicase) | red | **Decays** end of turn | Animus (2/turn) | Tech resource. Best for attack. |
| **Attack** | attack | **Decays** end of turn | Various | Deals damage to enemy units. |

**Key rule**: Gold and Green carry over between turns. Energy, Blue, Red, and Attack decay at end of turn if unspent.

**Tech building economics**: An Animus costs about 8 Gold/turn to fully spend its 2 Red. Roughly 3-6 Gold per 1 tech resource is the standard ratio for unit costs.

---

## Turn Structure & Phases

Each player's turn consists of three phases:

### 1. Action Phase
Two sub-phases:
- **Using Abilities**: Click units to activate abilities (attack, chill, sacrifice, etc.). Using a blocker's ability stops it from blocking this turn.
- **Purchasing Units**: Spend resources to buy new units. Units under construction ("golden") are invulnerable.

### 2. Breach Phase (conditional)
Triggered when the active player's attack >= opponent's total blocking defense:
- All enemy blockers are destroyed (wipeout)
- Remaining attack is freely assigned to any enemy units (the attacker chooses targets)
- **Overkill**: If all active units destroyed and attack remains, units under construction become vulnerable

### 3. Defense Phase (conditional)
If the opponent has attack > 0:
- Defending player assigns damage to their blockers
- Blockers take damage; non-fragile blockers heal to full if they survive (absorb)
- Goal: Keep defense > opponent's attack to prevent breach

### Turn Numbering
- `m_turnNumber` increments once per **player-turn** (not per round)
- Turn 0 = Player 1's first turn, Turn 1 = Player 2's first turn, etc.

### Start-of-Turn Effects (Swoosh)
At the start of each turn:
- All chill is removed from all units
- Lifespan decremented by 1; units at 0 lifespan die
- Exhaust counters decrement by 1
- Construction delay decrements by 1; units finishing construction become active
- Start-of-turn abilities trigger (auto-attack, resource generation, etc.)

---

## Unit Mechanics

### Core Properties

| Property | Icon | Description |
|----------|------|-------------|
| **Health** | HP | Hit points. Non-fragile units heal to full after surviving damage. |
| **Attack** | attack | Damage dealt each turn (constant or via ability). |
| **Blocker** | block | Can contribute HP to defense. Cannot block while ability is used. |
| **Prompt** | prompt | Blocker with 0 build time. Can block on the turn purchased. Cannot use abilities on purchase turn. |
| **Fragile** | fragile | Does NOT heal after taking damage. Permanent HP reduction. Cannot absorb. |
| **Frontline** | frontline | Can be directly targeted by opponent even when blockers exist. Often has high HP to compensate. |
| **Build Time** | buildtime | Turns after purchase before the unit becomes active. Under construction = invulnerable. |
| **Lifespan** | lifespan | Unit dies when lifespan reaches 0 at start of owner's turn. |
| **Stamina** | stamina | Number of times the click ability can be used before it's depleted. |
| **Exhaust** | exhaust | Turns the unit's effect/ability is disabled after triggering. |
| **Chill** | chill | Prevents blocking. A unit with chill >= its HP is "frozen" and cannot block. |
| **Supply** | — | Max copies each player can buy. 1=Legendary, 4=Epic, 10=Rare, 20=Common. |

### Unit Lifecycle
1. **Purchased**: Resources spent. Unit enters construction (golden, invulnerable).
2. **Under Construction**: Build time counts down each turn. Cannot act, cannot be targeted (except during overkill).
3. **Active**: Can use abilities, block, produce resources. Start-of-turn effects apply.
4. **Destroyed**: HP reduced to 0, lifespan expires, or sacrificed.

### Ability Mechanics
- Click ability: Manual activation. Using it on a blocker stops that blocker from blocking.
- Start-of-turn effect: Automatic. Triggers at the start of each turn (swoosh phase).
- Self-sacrifice (selfsac): Some abilities destroy the unit as part of activation.
- Targeting: Some abilities require selecting a target unit (snipe, chill).

---

## Base Set Units

The 11 base set units appear in every game:

### Economic Units

| Unit | Cost | Build | HP | Key Properties |
|------|------|-------|----|----------------|
| **Drone** | 3 gold + 1 energy | 1 | 1 | Click: produce 1 gold. Can hold back to block (1 HP). Pays for itself in 3 turns. |
| **Engineer** | 1 gold | 1 | 1 | Blocker. Produces 1 energy/turn. Players start with 2. Key for defensive granularity. |
| **Conduit** | 4 gold | 1 | — | Produces 1 green/turn. Cheapest, least committal tech building. |
| **Blastforge** | 5 gold | 1 | — | Produces 1 blue/turn. Best for defense (Walls). |
| **Animus** | 6 gold | 1 | — | Produces 2 red/turn. Best for attack (Tarsiers, Rhinos). Expensive to fully utilize. |

### Combat Units

| Unit | Cost | Build | HP | Key Properties |
|------|------|-------|----|----------------|
| **Tarsier** | 4 gold + 1 red | **2** | 1 | Constant 1 attack. Most efficient base attacker. Vulnerable to breach (1 HP). |
| **Rhino** | 5 gold + 1 red | 1 | 2 | Prompt blocker. Stamina 2 (click to attack for 1). "Rhino train" is a key tactic. |
| **Wall** | 5 gold + 1 blue | 1 | 3 | Prompt blocker. Best base set absorber (absorbs 2/turn). No granularity alone. |
| **Steelsplitter** | 6 gold + 1 blue | 1 | 3 | Blocker. Click: attack for 1 (loses blocking). Versatile but inefficient at either role. |
| **Gauss Cannon** | 6 gold + 1 green | 1 | 4 (fragile) | Constant 1 attack. Fragile — does not heal. High HP makes it breach-resistant. |
| **Forcefield** | 1 green (consumes a Drone) | prompt | 1 (fragile) | Cheap prompt fragile blocker. Converts Drones to defense. |

### Starting Units
- Player 1: 6 Drones, 2 Engineers
- Player 2: 7 Drones, 2 Engineers (compensates for going second)

---

## Defense Concepts

### Absorb
The most important defensive mechanic. Non-fragile units that survive damage heal to full instantly. A unit with N health absorbs up to N-1 damage per turn.

**Absorb barrier**: Maximum possible absorb, determined by the highest-HP non-fragile blocker in the set. Wall = 2 absorb. Energy Matrix = 4 absorb. Centurion = 5 absorb. Higher absorb barrier means players should build more economy before attacking.

**Key insight**: "Absorb is the strongest, most busted mechanic in the game" — Will Ma, Lunarch Studios founder. Return on investment: **Absorb > Attack > Economy**.

### Soak
Defense that dies (not absorb). Blockers sacrificed to absorb damage into the absorber. Fragile blockers are pure soak.

### Defensive Granularity
The ability to block any attack number and absorb the maximum amount. Requires blockers of varying HP. A pair of Engineers provides granularity against most attacks.

**Example**: 2 Walls alone = poor granularity (opponent attacks in multiples of 3 to deny absorb). 1 Wall + 2 Engineers = good granularity (can handle any attack number).

### Preventive Defense
Buying non-prompt blockers in advance. Often more cost-efficient:
- Infusion Grid vs Wall: more HP for less cost
- Shredder vs Wall: more HP + threat
- Perforator vs Rhino: 2 gold cheaper

---

## Breach Mechanics

### When Breach Occurs
Attack >= total defense (sum of all active blockers' HP) triggers breach:
1. All blockers are destroyed
2. Excess attack is assigned by the **attacker** to any enemy units of their choice
3. Attacker targets highest-value, lowest-HP units first (Tarsiers, Drones, tech buildings)

### Overkill
After all active units are destroyed, if attack remains, units under construction lose invulnerability and can be targeted.

### Breach-Vulnerable Units
Low-HP, high-value units (Tarsier 1HP, Vivid Drone 1HP, Lucina Spinos 2HP) are prime breach targets. Build units with similar HP to deny easy targets.

### Breachproof Strategy
Make all your units have high HP or low value so breach doesn't hurt. Counters chill-based strategies.

---

## Chill & Freeze

### Mechanics
- Chill is applied to individual enemy blockers
- A unit with chill >= its HP is **frozen** and cannot block
- All chill is removed from all units at the start of each turn
- Chill does NO direct damage — it bypasses defense

### Strategic Uses
1. **Freeze small defenders** to break granularity (freeze Engineers, force inefficient blocks)
2. **Freeze large absorber** to deny absorb (freeze Wall/Energy Matrix)
3. **Ensure breach** by nullifying enough blocking HP
4. **Kill lifespan units** by freezing blockers on their last turn (effectively converts chill to damage)

### Chill Units (from cheapest to most expensive)

| Unit | Chill Amount | Notes |
|------|-------------|-------|
| Frostbite | 4 | Self-sacrifice. One-time burst. Produced by Frost Brooder/Endotherm Kit. |
| Cryo Ray | 1/turn | Permanent chill. Good for granularity denial. Lifespan 4. |
| Shiver Yeti | 2/turn | Must click (loses blocking). Good for freezing absorbers. |
| Iceblade Golem | 1/turn | No activation cost. Constant pressure. |
| Tatsu Nullifier | 4/turn | No activation cost. Massive constant freeze. |
| Nivo Charge | 5 | Self-sacrifice. Huge burst, but limited supply. |
| Vai Mauronax | 7/turn | Click: trade 1 attack for 7 chill. Devastating. |

### Counters to Chill
- **Breachproof**: No high-value targets = chill wasted
- **Vigilant units**: Attack while blocking (Xeno Guardian, Ossified Drone)
- **Awkward HP values**: Defenders that waste chill (e.g., 2HP blockers vs 3-chill units)
- **Multiple absorbers**: Backup absorber when primary is frozen
- **Gambit**: Allow controlled breach, forcing opponent to spend Frostbites

---

## Strategy Fundamentals

### Game Phases

1. **Economy Phase**: Build Drones. How many depends on absorb barrier — bigger absorber = more Drones needed (12-15 for Wall absorb, more for bigger absorbers).

2. **Transition Phase**: Set up tech buildings, buy first attackers. Don't rush your biggest absorber — it should wait until it can absorb near-maximum.

3. **Attack & Absorb Phase**: Deploy biggest absorber. Pump attack. Prioritize long-term attackers (Tarsier, Tantalum Ray).

4. **Attack & Defense Phase**: Opponent's attack exceeds your absorb. Buy defense + attack. Switch to short/medium-term attackers (Rhino, Grimbotch, Plasmafier). Buy a Conduit for Forcefields.

5. **Defense Phase**: All resources go to not getting breached. Hang on until opponent breaks.

6. **Breach Phase**: One/both sides breached. Game usually ends here. Some sets allow breachproof endgames.

### Key Strategic Principles

- **Attack is an investment**: Risk-free, generates long-term value. Better than economy once past absorb.
- **Absorb is king**: First few attackers are inefficient (absorbed). Build economy first to overcome absorb barrier quickly.
- **Read the set**: Determine key units (win conditions) vs support units. Plan tech path accordingly.
- **Take the initiative**: Mirroring opponent one turn late = losing. Break symmetry or attack first.
- **Offensive finesse**: Click/don't-click flexibility lets you exploit opponent's lack of granularity.
- **Float management**: Avoid floating more than 2 Gold or Green per turn. Plan purchases to minimize waste.
- **Build order matters**: Player 1 and Player 2 have different optimal openings. 3rd Engineer is common for P1.

### Common Opening Patterns

**Player 1 (6 Drones, 2 Engineers)**:
- Natural Blastforge: DD / DD / DDB
- 3rd Engineer Blastforge: DD / DDE / DDD / DDDB (very common)
- Natural Animus: DD / DD / DDA
- Elyot Animus: DD / A (fringe, ultra-aggressive)

**Player 2 (7 Drones, 2 Engineers)**:
- Natural Conduit: DD / DDC (very common)
- 3rd Engineer Conduit: DD / DDE / DDDC
- Fastimus: DD / DA
- P2 Masterbot: DD / DB (for Flame Animus sets)

### Economy Sizing
- Wall absorb barrier (2): 12-15 Drones
- Energy Matrix absorb barrier (4): 15-18 Drones
- Centurion absorb barrier (5): 18+ Drones
- No big absorber / aggro set: <12 Drones

### Key Tactical Concepts

- **Fake damage**: Attack total > actual achievable damage (e.g., 3 Drakes but only 2 Blastforges)
- **Fake chill**: Chill total > actually usable chill (e.g., 10 chill vs only 6 HP of blockers)
- **Exploit**: Attacking for an amount opponent can't absorb efficiently
- **Threat**: Forcing extra defense without dealing damage (Drake click, Odin click)
- **Vigilance**: Units that attack while blocking (unofficial term, from MTG)
- **Train**: Buying 1-2 lifespan/stamina units per turn for steady defense (Rhino train, Chieftain train)

---

## Glossary

| Term | Definition |
|------|-----------|
| **Absorb** | Non-fragile units heal damage they survive. Max absorb = HP - 1. |
| **Absorber** | The unit chosen to absorb damage each turn. Usually highest-HP non-fragile blocker. |
| **Absorb barrier** | Max possible absorb in a set. Equals biggest non-fragile blocker's HP minus 1. |
| **Advanced units** | Non-base-set units. Balanced to be slightly stronger than base set. |
| **Breachproof** | Strategy where no units are breach-vulnerable, so breach is harmless. |
| **Burst damage** | One-time large damage (Cluster Bolt, The Wincer, Grenade Mech). |
| **Chill** | Effect that prevents blocking. Unit frozen when chill >= HP. Resets each turn. |
| **Deny absorb** | Preventing opponent from absorbing maximum damage. |
| **Economy** | Drone count + income from tech buildings + alternate Drones. |
| **Exploit** | Attacking for amount opponent can't absorb efficiently. |
| **Fake chill/damage** | Displayed total exceeds actual achievable value. |
| **Float** | Unspent Gold or Green at end of turn. Ideally <= 2. |
| **Fragile** | Takes permanent damage (no healing). Cannot absorb. |
| **Frontline** | Can be targeted directly even with blockers present. |
| **Gambit** | Intentionally allowing breach at a calculated cost. |
| **Golden unit** | Unit under construction. Invulnerable (except during overkill). |
| **Granularity** | Having blockers to handle any attack number efficiently. |
| **Inflation** | Importance of getting value now vs later. Increases over game time. |
| **Key unit** | Win condition unit (Zemora, Odin, Tia Thurnax, Asteri Cannon). |
| **Legendary** | Supply of 1. |
| **Line** | Planned sequence of moves, usually in opening. |
| **Mirror** | Both players using same strategy. |
| **Overteched** | Too many tech buildings, not enough Gold to spend tech resources. |
| **Prompt** | Zero build time blocker. Can block immediately when purchased. |
| **Sink** | Easy way to spend tech resources (Nitrocybe = red sink). |
| **Soak** | Blockers that die on defense (not absorbing). |
| **Support unit** | Defensive/utility unit that assists key units. |
| **Tech buildings** | Conduit, Blastforge, Animus (+ Chrono Filter, Flame Animus, Synthesizer, Steelforge). |
| **Tech resources** | Green, Blue, Red. |
| **Threat** | Forces extra defense without dealing damage (Drake, Odin clicks). |
| **Train** | Buying 1-2 units per turn for steady defense/attack stream. |
| **Underteched** | Not enough tech resources to spend Gold efficiently. Fixable by adding tech buildings. |
| **Vigilant** | Can block while also doing something useful (attack without click). |
| **Wipeout** | Destroying all enemy blockers, triggering breach. |

### Common Abbreviations

| Abbrev. | Meaning |
|---------|---------|
| D | Drone |
| E | Engineer (or Energy) |
| W | Wall |
| T | Tarsier |
| S | Steelsplitter |
| R | Rhino (or Red resource) |
| G | Gauss Cannon (or Green resource) |
| F | Forcefield |
| A | Animus |
| B | Blastforge (or Blue resource) |
| C | Conduit |
| P1 / P2 | Player 1 / Player 2 |
| BSO | Base Set Only |

---

## Advanced Units Quick Reference

105 competitive advanced units exist. Here are notable categories and examples:

### Big Absorbers (define the absorb barrier)

| Unit | HP | Cost | Notes |
|------|------|------|-------|
| Energy Matrix | 5 | 9 gold + 2 blue | Non-fragile blocker. Absorbs 4/turn. Dominant defender. |
| Centurion | 6 | 15 gold + 2 blue | Absorbs 5/turn. Huge economy required. |
| Defense Grid | 10 | 20 gold + 3 blue | Absorbs 9/turn. Legendary. Game-defining. |
| Plexo Cell | 4 | 4 gold + 1 green | Lifespan 3. Excellent value soak/absorb. Consumes Drone. |
| Infusion Grid | 6 | 7 gold | Non-prompt. Great HP/cost ratio. Colorless. |
| Doomed Wall | 4 | 4 gold + 1 blue | Lifespan 3. Cheap prompt absorber. |

### Key Attackers

| Unit | Attack | Cost | Notes |
|------|--------|------|-------|
| Drake | 2 + click(2, sac Blastforge) | 12 gold + 2 blue | Huge threat. 4 HP. |
| Scorchilla | 2 (exhaust 1) | 8 gold + 1 red | Flexible attack (click or don't). |
| Amporilla | 0 | 4 gold + 1 red | Doubles Tarsier production. Supply 4. |
| Iso Kronus | 2 (exhaust 1) | 8 gold + 1 green | Fragile 4HP. Sync for massive burst. |
| Asteri Cannon | 1 + click(3) | 14 gold + 2 green | Build 3. Constant 4 attack. Fragile 6HP. |
| Shadowfang | 2 | 7 gold + 1 red | 1 HP. Breach vulnerable. |

### Legendary Units (Supply 1)

| Unit | Cost | Notes |
|------|------|-------|
| Odin | 20 gold + 3 blue | Comes with 3 Steelsplitters. Click: sac Steelsplitter for 4 attack. |
| Tia Thurnax | 12 gold + 2 red | 5 HP. Lifespan 3 + exhaust 1. Click: 7 attack. |
| Lucina Spinos | 14 gold + 1 blue + 1 green | 2 HP (breach vulnerable). Produces Husks (1 attack each turn). |
| Zemora Voidbringer | 23 gold + 3 green | Build 5. Produces attackers forever. Very long-term investment. |
| Savior | 16 gold + 2 blue | Build 3. Produces Forcefields. Defensive powerhouse. |
| Cynestra | 10 gold + 2 red | Build 2. 3 attack. Click: sac enemy unit + sac self. Legendary assassin. |
| Centrifuge | 7 gold | Produces 1 of each tech resource per turn. Universal tech fix. |

### Chill Units
See [Chill & Freeze](#chill--freeze) section above.

### Frontline Units
High HP, targetable without breach. Examples: Feral Warden, Borehole Patroller, Chieftain, Xeno Guardian.

### Notable Mechanics

| Unit | Mechanic |
|------|----------|
| Deadeye Operative | Snipe: click to destroy any enemy unit with 1 HP |
| Plasmafier | Click: consume all Drones to attack for 2x consumed |
| Trinity Drone | Produces 1 gold + 1 green. 1 HP. Alternative Drone. |
| Vivid Drone | Produces 3 gold. 1 HP. High-value breach target. |
| Grenade Mech | Click: self-sacrifice for 4 burst damage. |
| Bloodrager | Click: opponent loses 1 attack but you gain 1 permanent attack. Denies absorb. |
| Militia | Click: produce 1 gold. Blocker with 2 HP. Vigilant-like. |
| Wild Drone | 0 cost, 1 energy. Produces 1 gold + 1 green. Free but limited supply. |
| Auric Impulse | 1 gold. Produces 1 gold. Basically free economy. Limited supply 4. |

### Self-Sacrifice (Selfsac) Units
Units that destroy themselves when using their ability:
- Frostbite (4 chill burst)
- Grenade Mech (4 attack burst)
- Nivo Charge (5 chill burst)
- Cluster Bolt (4 damage, targets chosen by attacker)
- The Wincer (consume Drone, deal attack)
- Grimbotch (4 attack, lifespan 1 — attacks then dies)

**Engine note**: Selfsac units are destroyed in the TypeScript replay parser at a different timing than in the C++ engine (known tooling discrepancy, not an engine bug).

---

## Engine-Relevant Notes

### Internal Name System
The C++ engine uses codenames for units, not display names. Key mappings:

| Display Name | Internal Name | | Display Name | Internal Name |
|---|---|---|---|---|
| Tarsier | Tesla Tower | | Blastforge | Brooder |
| Steelsplitter | Treant | | Rhino | Elephant |
| Forcefield | Blood Barrier | | Gauss Cannon | Minicannon |
| Husk | House | | Gauss Charge | Flame Kin |
| Drake | Drake | | Odin | Furion |
| Energy Matrix | Golem | | Centurion | Battalion |
| Scorchilla | Rocket Artillery | | Frostbite | Screech Blast |

Full 105-unit mapping is in CLAUDE.md.

### Card Library (cardLibrary.jso)
Master unit definitions file containing:
- Internal name, display name
- Cost (gold, green, blue, red, energy, attack cost)
- HP, build time, lifespan, supply, stamina
- Ability scripts (beginOwnTurnScript, abilityScript, etc.)
- Blocker, fragile, frontline, prompt flags

### Validation Status
287 replays tested. C++ engine is correct. All 209 FAILs trace to TypeScript tooling bugs (RC#5 snipe targets, RC#6 frontline-to-breach, selfsac timing).
