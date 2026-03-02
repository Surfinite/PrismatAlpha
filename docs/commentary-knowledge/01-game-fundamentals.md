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

---

### Why Pooled Combat (No Unit-on-Unit Fighting)
> Source: Lunarch Blog — Stepping Away from Unit-on-Unit Combat (Will Ma, Jul 2014)

Prismata deliberately abandons unit-on-unit combat. Instead of commanding each unit to attack a specific target, all attack damage is pooled together. At end of turn, the opponent assigns damage to their defenders; if all defenders die, the attacker assigns leftover damage to any units they choose. The origin of each point of damage is forgotten.

The design motivation: in a perfect-information game (no hidden information, no randomness), unit-on-unit combat creates an overwhelming branching factor of myopic tactical calculations that crowds out strategic thinking. During four years of prototyping, "all of the versions with unit-on-unit combat were bogged down by myopic calculations."

"Simplifying the tactics of a game exposes the strategic elements."

The result: "Even when gamestates get huge, with dozens (sometimes 100 or more) units on the table, you never find yourself feeling mindfucked by combat tactics. Combat is brisk: each unit simply charges headlong, contributing to your sum of attack damage."

Players focus on strategic decisions instead:
- Do I have enough time for a greedy economic build, or will early harassment disrupt me?
- If I plan a timing attack 5 turns out, will it deal enough damage to justify delaying my tech?
- Should I upgrade to sturdier Drones to become the "control player" in the late game?

"In practice, exact calculations more than one turn ahead are not useful in Prismata; it's much more efficient to rely on your strategic intuition instead."

Endgame exception: When few units remain, turn-by-turn tactical calculation becomes valuable. But most thinking happens beforehand. Prismata has "clarity" -- you can envision the endgame trajectory from early on and plan around turning points.

---

### Why No Randomness (The Chess960 Analogy)
> Source: Lunarch Blog — Removing RNG: How Eliminating Luck Can Benefit Strategy Card Games (Elyot Grant, Dec 2014)

Prismata eliminates decks entirely. Before each match, a fixed pool of units is randomly selected that both players can buy. This pool is different every time, guaranteeing unique experiences. But once the game begins, there is no randomness or hidden information.

"A good analogy is that of Chess960 -- a chess variant in which both players start the game with a back row of pieces that is randomized, but identical for both players. Randomness is used before the game begins to generate novelty in a way that is as fair as possible for both players, and once the game begins, there is no additional RNG whatsoever."

Benefits vs. luck-based games:
- **Novelty without unfairness**: "Because there are dozens of units with many interesting synergies and interactions among them, but you only get to see a tiny subset of these units each game, Prismata exhibits an incredibly addictive form of game-to-game novelty."
- **Victories feel earned**: "Many of our players report that their victories in Prismata feel incredibly satisfying, because players feel that they won because of their own skill, not because of favourable RNG."
- **Faster improvement**: "Players improve much more quickly because they always feel the consequences of their mistakes."
- **Decisive endings**: "The game is designed around decisive moments -- like a first big breach -- that quickly lead to a position in which one side is the clear victor."

---

### Game Length & Time Controls
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

"Games often finish in 10-15 turns, with the first few turns progressing much faster, so the total length of a 30-second-per-turn game averages about 10 minutes."

Time control scaling:
- **10 seconds/turn**: "Perfectly playable. You have to think fast, but you almost always have enough time. Experienced players love this mode."
- **7 seconds/turn**: "Some turns feel pretty tight. Being good at using hotkeys is important."
- **5 seconds/turn**: "StarCraft players will feel right at home. Certain strategies (e.g. lots of chill) become difficult to execute, while strategies requiring few clicks (like spamming Gauss Cannons) gain popularity."
- **3 seconds/turn**: "The Prismata equivalent of 300APM professional StarCraft, unplayable to most people."

---

### Why Supply Limits Exist
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

Supply limits serve three purposes:

1. **Games are forced to end**: "Before we introduced supply limits, some games ended in bizarre 'infinite loop draws' where one player would build a Wall every turn, the opponent would destroy a Wall every turn, and neither side would make progress."

2. **Economies are limited**: "Many beginners loved buying Drones, and beginner versus beginner matches often turned into huge, grindey slug-fests with 40 or more Drones per side."

3. **Increased design space**: "We discovered that varying the supply of a unit could lead to dramatic changes. We could create units with low supply that were extremely powerful, but couldn't be massed." This led to legendary (supply 1) units.

Important: supplies are NOT shared between players. "We experimented with this, but it ultimately led to unfun situations because players would rush to obtain the last remaining supplies of certain key units."

---

### Why "Kill Everything" Win Condition
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

Lunarch tried multiple win conditions: destroy everything, destroy all Drones, reduce life to zero. "Destroy everything" led to the most gameplay variety.

Having life points (like Magic/Hearthstone) "actually decreased gameplay variety substantially. Having life rarely introduced interesting strategies (you can't really play a 'burn deck' in Prismata) and it destroyed play styles that involved making lots of high HP units and no defense."

"In the vast majority of games, having health actually changed nothing, because players would almost always prefer to destroy their opponents' economies rather than deal damage to their opponent's face."

---

### Why Drones Must Be Clicked
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

"In Prismata, the units that require clicking are precisely those units for which there is some trade-off when their ability is activated. In the case of Drones or Steelsplitter, they only block when they are left unclicked."

Originally ALL units had to be clicked, including Blastforge and Conduit. "It was strictly correct to click these units at the start of every turn; failing to click them was always a mistake." Auto-clicking was added for units with no trade-off; manual clicking was kept for units where not clicking has defensive value.

---

### Prismata Solvability
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

"Could somebody write a 'chess computer' for Prismata that could defeat the best human players? Could a computer AI solve the game and prove that the first (or second) player had a guaranteed way to win? The answer... Not even close."

Even with only a few units available (Drone, Engineer, Blastforge, Wall, Steelsplitter), an MIT expert and a StarCraft AI Competition winner both attempted to solve the game and could not.

---

### Detailed Buying & Cost Notation
> Source: Lunarch Blog — Official Prismata Rules (Will Ma, Aug 2014)

"The cost in gold is denoted by a number on top of the symbol; the cost in other resources is denoted by counting the symbols. For example, Drone costs 3 gold and 1 energy, while Shadowfang costs 6 gold and 3 red."

"There is a limit to how many of each unit you can buy. The pellets at the bottom indicate the supply of each unit you have remaining. Each unit has a different starting supply (either 1, 4, 10, or 20)."

"Unless otherwise stated, all units take a turn to construct." The clock icon with a number indicates remaining construction turns. "Units get constructed at the start of your turn, after which they immediately do something (if they do something at the start of your turn), can block, and can be clicked."

---

### Fragile — Detailed Mechanics
> Source: Lunarch Blog — Official Prismata Rules (Will Ma, Aug 2014)

"A lot of units costing green have the fragile property." Fragile means you can damage the unit during breach even without lethal damage -- it permanently reduces the unit's health, making it easier to kill on a later turn.

"In defense, a unit with fragile behaves the same as a normal unit, except if it absorbs damage as the last defender, its health is permanently reduced."

Non-fragile units heal to full after absorbing non-lethal damage. Fragile units do not.

---

### Build Time as a Design Tool
> Source: Lunarch Blog — Longer Build Times in Prismata (Elyot Grant, Sep 2015)

Most units have build time 1, but some have build time 2-6 (Tarsier=2, Centrifuge=3, Resophore=5, Zemora Voidbringer=6). Three purposes:

1. **Creating interesting gamestates**: "Some of my favourite situations are those when one player has a Zemora Voidbringer under construction, and their opponent is desperately trying to counterattack before it arrives. Build times allow some of the most dynamic and skill-testing Prismata situations."

2. **Balance tool**: "Tarsier was originally a 5R unit with build time 1. Its strength was too dominant, so we replaced it with the 4R build time 2 Tarsier you know and love today."

3. **Enabling combos**: Units with different build times can be staggered so they all come online at once for a burst -- "leaving your unsuspecting opponent dazed."

Why not more high build-time units? "It comes down to simplicity and clarity. Sometimes it's difficult to plan many turns ahead, and the resulting complexity can be intimidating."

---

### The Sniping Mechanic
> Source: Lunarch Blog — New Prismata Sniping Game Mechanic (Will Ma, Oct 2014)

Snipe is a targeted ability that bypasses the normal defense system. Instead of pooling damage that defenders can absorb, snipe directly kills a specific unit regardless of whether the opponent has blockers.

Deadeye Operative: snipes Drones without breaching. "In games where it feels impossible to breach high-health defenders like Defense Grid, Deadeye lets you be offensive without breaching."

Apollo: snipes any unit with 3 or less health. Can snipe attackers (limiting opponent's damage), Walls (for a well-timed breach), or tech buildings (disrupting builds).

Combo example: "You can assign 2 damage to your opponent's Gauss Cannon in combat, and then use Apollo to finish it off on the same turn."

---

### Economy Sizing Rules of Thumb
> Source: Lunarch Blog — 6 Common Prismata Mistakes (Elyot Grant, Sep 2014)

"As a general rule of thumb, you should usually aim to have about 12-15 Drones and then stop buying them."

"Games of Prismata are won by attacking, and your primary goal should be to construct a powerful attacking force as quickly as possible. It's usually optimal to build only enough Drones to sustain the production of attackers, and then switch to spending all of your resources on buying attackers (and defenders, if necessary)."

Resource ratio guidance: "Try to ensure that you have enough Drones to produce the amount of Gold that you need to support your tech."
- 5 Drones per Blastforge = 1 Wall per turn
- 9 Drones per Animus = 1 Tarsier + 1 Rhino per turn
- 13 Drones + Animus + Blastforge = 2 Tarsiers + 1 Wall per turn

"Your main objective should be to not waste Blue or Red, because they do not get stored between turns."

---

### Attacker Efficiency vs. Defender Efficiency
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

Why you can't just buy Drones forever:

"To build one Wall per turn, you need five Drones and a Blastforge, which costs a total of 20 gold and 5 energy. To destroy one Wall per turn, you could buy just three Tarsiers, which costs a total of just 12 gold and 3 red."

"Clearly, the three Tarsiers are cheaper. In the long run, if you're buying Drones and your opponent is buying Tarsiers, you're going to fall behind. You should only buy enough Drones to get your economy started, and then spend most of the rest of your resources on ramping up your attack."

---

### Defense Minimum Principle
> Source: Lunarch Blog — 6 Common Prismata Mistakes (Elyot Grant, Sep 2014)

"Amassing a large amount of defense early is rarely (if ever) worth it, because you will fall behind in attack while your opponent's attack whittles down your Walls. The correct amount of defense to buy is usually just the minimum you need to have in order to not be breached. This means you want your total defense to be one higher than your opponent's potential attack next turn."

"Rather than preemptively buying Walls before your opponent has any attackers, opt for Steelsplitters or other attackers that can give you an early advantage. Then, after your opponent has bought their first attacker, get a Prompt defender that can absorb the damage right away."

Late-game shift: "It's important to continue buying as much defense as possible to prevent your opponent from breaching you, especially if you have breach-vulnerable units like Tarsiers."

---

### True vs. Displayed Attack
> Source: Lunarch Blog — 6 Common Prismata Mistakes (Elyot Grant, Sep 2014)

"Sometimes your opponent's 'true' attack potential is lower than the displayed attack potential value (in square brackets), because your opponent can be forced to lose an offensive unit on defense (e.g. a Steelsplitter or Rhino) before it gets the chance to deal damage on the opponent's next turn. Watch out for this so that you don't overcommit to defense."

---

### First Turn Conventions
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

"Opening your game of Prismata with two Drones is so common that we considered making the two players start with 7/8 Drones instead of 6/7 so that the first turn wasn't as inevitable."

DD is not always optimal: "The most obvious exception is when there are other economic units in the base set, because Drones are not always the most cost-effective worker in the current deck." Alternative Drone types include Wild Drone, Doomed Drone, and Vivid Drone.

"It's more common to get early technology as the second player because you can open with a Drone and Conduit, which produces the green resource needed to make Trinity Drones and other units that are useful in the early-game."

"Avoiding a DD opening also allows for degenerate rushes, which are particularly effective in blitz games."

---

### No Deck Building — Design Philosophy
> Source: Lunarch Blog — 10 Common Prismata Game Design Questions (Elyot Grant, Aug 2014)

"One of the big drawbacks of a game like StarCraft is that to be a professional player, you only need to be good at one race, which constitutes 3 of the 9 match-ups."

"With our game's setup, you have access to all three branches of tech in every game and you can choose what you want to build based on what's available. If you like mechs, then you can go blue every game, but it's not always the best choice to do so."

Removing pre-game choice "eliminated the implicit 'yomi luck' inherent in getting automatched against an opponent."

---

## Economy Sizing by Absorber
> Source: amalloy — WDIL series (multiple episodes, YouTube)

### Absorber-Driven Economy Sizing
"The first things to look at: what are the absorbers in the set, which will help govern our economy size." The available absorbers, not the desired attackers, should determine how many Drones to buy.

- **No big absorber (only Wall)**: 10-14 Drones. "There's no defense at all in this set, which means 9-14 Drones."
- **Centurion/Energy Matrix**: 18-22 Drones. "You need like high-teens to low-20s."
- **Defense Grid + Centurion**: 20+ Drones — but don't build both simultaneously (see Strategy Concepts).

"You want to judge your economy size based on the big defenders in the set because the bigger the absorbers are, the less advantageous it is to attack quickly."

### Good Soak Reduces Windsor Value
> Source: amalloy — "WDIL: TTK vs Miccull" (YouTube)

Good soak units (Paliwal, Plexo Cell) let the opponent cheaply absorb burst damage, reducing the effectiveness of big burst attackers like Windsor. Economy sizing must account for soak availability, not just absorber HP.

---

## Copying Your Opponent's Strategy
> Source: sileneundulata + amalloy — "League Game Analysis: WDIL with sileneundulata" (YouTube)

### "Just Do What Your Opponent Does But Worse"
"I know that personally I do this against strong players — I look at what they're doing and I think 'oh I better do what they do or I'm gonna lose.'" Copying an opponent's strategy is a common trap, especially against higher-rated players.

The correct approach: evaluate the set independently, identify the strongest plan for your player position, and execute it. "You looked at what I was doing, thought it was good, so you copied it without potentially looking for better lines that you're in your own position."

**Practical example (WDIL with sileneundulata)**: amalloy went 4th Engineer in a Lance Tooth set because sileneundulata did — but sileneundulata's 4th Engineer was a mistake born of playing too quickly. Both players ended up with the same suboptimal strategy instead of one exploiting the other's weakness.
