## Prismata Knowledge Base

Prismata is a turn-based, perfect-information strategy game. Two players buy units from 11 base-set units plus 5-8 random units from ~105. No luck, no hidden info. Goal: destroy all enemy units. P1 starts with 6 Drones + 2 Engineers; P2 gets 7 Drones + 2 Engineers (extra Drone compensates for going second).

Each turn has two phases: **Defense** (assign blockers against incoming attack) then **Action** (use abilities, buy units). At turn start: chill removed, lifespan decremented, construction timers tick down, auto-abilities fire. Attack pools across all your attackers. If attack < defense, defender chooses which blocker absorbs (non-lethal damage heals). If attack >= defense: **breach** -- all blockers die, excess damage assigned by the attacker to any enemy units.

## Resources

| Resource | Persists? | Producer | Spend rule |
|----------|-----------|----------|------------|
| Gold | yes | Drone (1/t) | 1-2 float OK, 3+ wasteful |
| Green | yes | Conduit (1/t) | Cheapest tech, stockpiles |
| Blue | no | Blastforge (1/t) | Must spend each turn |
| Red | no | Animus (2/t) | Must spend each turn |
| Energy | no | Engineer (1/t) | Only matters early |

## Base Set (11 units)

| Unit | Cost | BT | HP | Role |
|------|------|----|----|------|
| Drone | 3+E | 1 | 1 | Economy. Click for 1G. Hold to block 1. |
| Engineer | 1 | 1 | 1 | Blocker. Produces 1E. Granularity filler. |
| Conduit | 4 | 1 | - | Produces 1 green/turn. Least committal tech. |
| Blastforge | 5 | 1 | - | Produces 1 blue/turn. Needed for Walls. |
| Animus | 6 | 1 | - | Produces 2 red/turn. Expensive to maintain (8G/turn). |
| Tarsier | 4+R | 2 | 1 | Auto-attack 1/turn. Efficient but breach-vulnerable. |
| Rhino | 5+R | 1 | 2 | Prompt blocker. Stamina 2 click-attack. Versatile. |
| Wall | 5+B | 1 | 3 | Prompt blocker. Best base absorber (absorbs 2/turn). |
| Steelsplitter | 6+B | 1 | 3 | Blocker. Click to attack 1. Jack of all trades. |
| Gauss Cannon | 6+G | 1 | 4F | Auto-attack 1. Fragile, high HP. Breachproof staple. |
| Forcefield | 1G (eats Drone) | 0 | 1F | Prompt fragile blocker. Emergency Drone-to-defense conversion. |

BT=build time, F=fragile, E=energy, R=red, B=blue, G=green.

## Standard Style (6 principles)

- **Buy, Buy, Buy** -- keep resources low. Every investment snowballs. Float 1-2G OK, 3+ bad.
- **Live on the Edge** -- delay defense until last moment. Prompt units let you buy just enough. But actually getting breached is catastrophic.
- **Absorb is Awesome** -- get the biggest blocker in the set. Absorb is the primary defender's advantage. Only one absorber works per turn.
- **Changing Gears** -- once past the absorb barrier, stop buying Drones, switch to attackers.
- **How Many Drones?** -- Wall absorb (2): 12-15 Drones. 4-HP absorber: ~20. 5+ HP: 20+, get 3rd Engineer.
- **Setting Up Tech** -- 1 Conduit needs 3G/turn to spend. 1 Blastforge needs 5G/turn. 1 Animus needs 8G/turn. Don't overtech.

## Glossary

| Term | Meaning |
|------|---------|
| Absorb | Non-lethal damage on a non-fragile blocker; heals next turn |
| Breach | Attack exceeds total defense; attacker picks targets |
| Soak | Blocker sacrificed to take lethal damage |
| Exploit | Attacking for an amount that denies absorb via poor granularity |
| Float | Unspent resources at end of turn |
| Granularity | Ability to block any damage amount while maximizing absorb |
| Overdefend | Spending more on defense than needed |
| Tech | Conduit / Blastforge / Animus |
| Tempo play | Aggressive, aims to end quickly |
| Econ play | Defensive, aims to outscale |
| Breachproof | High-HP units that survive breach safely |
| Offensive finesse | Using click units to force opponent guessing |
| Absorb barrier | HP of biggest absorber in the set |
| Chill | Prevents blocking; chill >= HP = frozen |
| Prompt | Zero build time, can block immediately |
| Frontline | Targetable by opponent even through blockers |
| Fragile | Does not heal after taking damage |
| Set reading | Analyzing random units to determine strategy |
| Gambit | Deliberately underdefending to save resources |
| Rhino train | Buying 1-2 Rhinos/turn for steady red defense |
