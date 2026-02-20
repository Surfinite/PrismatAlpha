# Category 2: Base Set Units (11 units — in EVERY game)

## Economic Units

### Drone
> Source: Official Rules + PRISMATA_REFERENCE.md

- **Cost**: 3 gold + 1 energy | **Build Time**: 1 | **HP**: 1
- Click: produce 1 gold. Can hold back to block (1 HP blocker).
- Pays for itself in 3 turns. The core economy unit.
- Vulnerable to breach (1 HP). High-value target.

### Engineer
> Source: PRISMATA_REFERENCE.md + Foxclear's Noticeable Units guide (wiki) + Prismata Blog

- **Cost**: 1 gold | **Build Time**: 1 | **HP**: 1
- Blocker. Produces 1 energy/turn. Players start with 2.
- Key for defensive granularity. Provides the "small blockers" needed to make absorb efficient.
- **"Worth 6 gold but misleading"**: An Engineer appears to cost 1 gold but saves you 3 gold per Drone through energy production. Its real value to your economy is ~6 gold over its lifetime, but treating it as a free purchase leads to over-buying.
- **Don't buy a 3rd Engineer without an energy sink**: "Ask yourself: 'Will I need that Engineer to defend next turn?' If not, keep the gold." — Foxclear. The 3rd Engineer is only justified in medium-to-high economy sets with good absorbers.
- **Multiple spare Engineers = underteched**: "If you end up buying multiple Engineers to fill in, that's a sign you're probably underteched — consider getting a Conduit or extra Blastforge. A Gauss Cannon is often better than 3 Engineers." — Foxclear

### Conduit
> Source: PRISMATA_REFERENCE.md + Standard Style

- **Cost**: 4 gold | **Build Time**: 1 | **HP**: n/a (non-blocker)
- Produces 1 green/turn. Cheapest, least committal tech building.
- "One Conduit requires 3 Gold per turn to spend" (tech spending rule of thumb).
- Green carries over between turns, so Conduit is forgiving.

### Blastforge
> Source: PRISMATA_REFERENCE.md + Standard Style

- **Cost**: 5 gold | **Build Time**: 1 | **HP**: n/a (non-blocker)
- Produces 1 blue/turn. Best for defense (Walls).
- "One Blastforge requires 5 Gold per turn to spend."
- Blue decays — must be spent each turn.

### Animus
> Source: PRISMATA_REFERENCE.md + Standard Style

- **Cost**: 6 gold | **Build Time**: 1 | **HP**: n/a (non-blocker)
- Produces 2 red/turn. Best for attack (Tarsiers, Rhinos).
- "One Animus requires 8 Gold per turn to spend." Most expensive tech to maintain.
- Red decays — expensive to fully utilize. Common beginner mistake: buying Animus too early.

---

## Combat Units

### Tarsier
> Source: PRISMATA_REFERENCE.md + Tips

- **Cost**: 4 gold + 1 red | **Build Time**: 2 | **HP**: 1
- Constant 1 attack per turn (automatic, no click needed).
- Most efficient base attacker per gold spent.
- **Vulnerability**: 1 HP = prime breach target. "Breach-vulnerable."
- 2-turn build time means you need to plan ahead.

### Rhino
> Source: PRISMATA_REFERENCE.md + Tips

- **Cost**: 5 gold + 1 red | **Build Time**: 1 | **HP**: 2
- Prompt blocker. Stamina 2 (click to attack for 1, up to 2 times total).
- The "Rhino train" is a key tactic — buying 1-2 Rhinos per turn for steady defense.
- Versatile: can block without clicking, or click for attack (loses blocking that turn).

### Wall
> Source: PRISMATA_REFERENCE.md + Standard Style + Defense Concepts

- **Cost**: 5 gold + 1 blue | **Build Time**: 1 | **HP**: 3
- Prompt blocker. The best base set absorber (absorbs 2 damage per turn).
- "Making two Steelsplitters costs 12BB and does two damage per turn. A Wall can absorb two damage per turn and costs 5B. So absorb is over twice as efficient as attack." — 307th
- No granularity alone: 2 Walls = poor granularity (opponent attacks in multiples of 3 to deny absorb).
- 1 Wall + 2 Engineers = good granularity (handles any attack number).

### Steelsplitter
> Source: PRISMATA_REFERENCE.md + Tips

- **Cost**: 6 gold + 1 blue | **Build Time**: 1 | **HP**: 3
- Blocker. Click: attack for 1 (loses blocking that turn).
- Versatile but inefficient at either role. "Jack of all trades."
- Key for offensive finesse — opponent must guess whether you'll click or block.

### Gauss Cannon
> Source: PRISMATA_REFERENCE.md

- **Cost**: 6 gold + 1 green | **Build Time**: 1 | **HP**: 4 (fragile)
- Constant 1 attack per turn (automatic).
- Fragile — does NOT heal. High HP makes it breach-resistant.
- Key unit for breachproof strategies.

### Forcefield
> Source: PRISMATA_REFERENCE.md + Standard Style

- **Cost**: 1 green (consumes a Drone) | **Build Time**: prompt | **HP**: 1 (fragile)
- Cheap prompt fragile blocker. Converts Drones to defense.
- "In the late game, buy a Conduit for Forcefields" — emergency defense conversion.
- Pure soak: 1 HP, fragile, dies on any defense assignment.

---

## Base Set Strategic Summary
> Source: Standard Style (307th) + Tips (wiki)

The base set alone creates a complete game with economy (Drones/Engineers), tech (Conduit/Blastforge/Animus), attack (Tarsier/Gauss Cannon), flexible attack/defense (Rhino/Steelsplitter), pure defense (Wall/Forcefield), and emergency conversion (Forcefield consuming Drones).

The absorb barrier in base set only (BSO) is 2 (Wall absorbs 2). This means relatively small economies (~12-15 Drones) before switching to attackers.

---

## Developer Design Commentary on Base Set
> Source: Lunarch Studios Blog — "The Prismata Base Set" (Elyot Grant, Aug 2014)

"The base set units in Prismata allow you to ramp up your economy, invest in technologies, and obtain essential offensive and defensive capabilities that can supplement the rest of your forces."

**Intentionally weak by design**: "Prismata's base set units are not particularly strong; indeed, they're deliberately balanced to be a bit weak, just as a small nudge of encouragement to players, pushing them toward the sharper, more tactical units found in the random sets."

### Drone — Developer Lore & Strategy
"The standard protocol is to unleash six or seven Drones as an initial economic squadron." Gold production supports all other units. "Unspent gold can be stored for future use, allowing you to save up for a massive purchase that could turn the tide of battle."

**Breach vulnerability**: "Drones themselves are quite weak, often being the first target whenever your opponent breaches your defenses."

### Engineer — Developer Strategy Note
"In addition to producing the Energy required for building Drones, Engineers can also serve as your earliest blockers if you don't build any other defense in time. Engineers can even be purchased purely for defense later in battle, but there are often better options available."

### Conduit — Developer Design Philosophy
> Source: Lunarch Studios Blog — "Conduit Technology in Prismata" (Nov 2014)

"Conduit technology is some of the funnest in the game, and in many ways the most versatile." Green tech provides "super-cheap defense in a pinch (Forcefields), storable resources, and high — if Fragile — unit health."

**Playstyle identity**: "One of the best feelings in Prismata is amassing green and unleashing a devastating attack after letting your opponent ineffectively breach you a turn earlier. Playing with green tech is about calculated neglect, and knowing when to go all-in."

### Blastforge — Developer Strategy Note
"Many of the toughest units in Prismata are produced with Behemium. The key to defense is absorbing damage, and units on the blue branch of technology do this best, as they have fairly high amounts of health and suffer no permanent injury when attacked for less than lethal damage. Blue units also have the most flexibility in how much they attack for; many of them can stay back and defend if their attack isn't needed."

### Animus — Developer Strategy Note
"Unlike the Conduit and Blastforge, the Animus produces two units of Replicase per turn, doubling your unit production. A swarm of red units can be built up quickly, and they hit hard. The downside is that red technologies usually have low health. However, red units work well together, and you can often muster a defense based on sheer numbers."

### Forcefield — Developer Design Note
"In battle, Drones are most valuable early on, when production is still ramping up. However, as a confrontation reaches its later stages, Drones become far less useful. In this situation, the Forcefield is the perfect unit for upgrading your Drones into defense for the remainder of your forces."

### Gauss Cannon — Developer Design Note
"With a whopping five health, Gauss Cannons are the sturdiest attacker in the base set. A huge pile of Gauss Cannons can be literally impossible to kill if your opponent has a limited amount of attack. However, Gauss Cannons are fairly expensive, so it takes a while to accumulate a lot of them, leaving your opponent time to counterattack."

**Commentary insight — avoid pairing with Wall**: In sets with strong absorbers and no chill/burst, buying Gauss Cannons alongside Walls is redundant — "If I'm not soaking up damage with the Gauss Cannons for most of the game, I'm not getting any value out of their high amount of health." Tarsiers offer 47% more attack per gold in that scenario (8 attack for 38G vs 56G). Save Gauss Cannons for sets where their HP matters (breach risk, chill, or breachproof).

### Steelsplitter — Developer Design Note
"Designed for versatility, the Steelsplitter can attack for one damage, or serve as a three-health blocker, although it cannot do both simultaneously. Steelsplitters are more expensive than Walls, Gauss Cannons, or Tarsiers, making them an inefficient choice if you simply want a pure attacker or pure defender. Steelsplitters are at their best when flexibility is important."

### Tarsier — Developer Design Note
"Tarsiers are the most cost-efficient attacker in the base set, and can be pumped two-at-a-time from a single Animus, meaning you can amass a large force of them for a very low cost. However, Tarsiers have no defensive capabilities at all, and with a single point of health, they're obvious targets for your opponent during a breach. If your primary offense is a pack of Tarsiers, you'll want to commit as many resources as necessary to defending them, even sacrificing Drones if necessary."

**Build time matters**: "Tarsiers also take a turn longer to construct than most other units, so plan accordingly." (Build time 2 is a key balance parameter — originally 5R with BT1, changed to 4R with BT2 to reduce dominance.)

### Rhino — Developer Design Note
"One of the key roles of the Rhino is that of a prompt defender that can support and protect Tarsiers and other offensive units without the need for a Blastforge. The Rhino's ability to block right away and attack immediately afterwards makes them a valuable tool when trying to seize the initiative away from an opponent."

---

## Base Set Resource Spending Rules
> Source: Lunarch Studios Blog — "6 Common Prismata Mistakes" (Elyot Grant, Sep 2014)

**Tech spending ratios**:
- 5 Drones per Blastforge = 1 Wall per turn
- 9 Drones per Animus = 1 Tarsier + 1 Rhino per turn
- 13 Drones + Animus + Blastforge = 2 Tarsiers + 1 Wall per turn

**Resource waste is costly**: "If you have an insufficient amount of Gold production per turn, your main objective should be to not waste Blue or Red, because they do not get stored between turns. Wasting them can seem harmless, but you end up losing out on a lot of potential value."

**Conduit is forgiving**: "Many players buy a Conduit before getting Blue or Red technology. Conduits are less punishing, because Green is storable: you aren't punished for not spending it right away."

---

## Top Player Assessment (Synx)
> Source: Synx (Synxisback2k, top player) — Reddit unit review (r/Prismata, 2015)

- **Drake** (pre-buff era): "THE worst unit in the game right now. You never want a Drake. It is only slightly better than 3 Steelsplitters."
- **Steelsplitter**: Only mentioned as inferior to other options — consistent with Yujiri's 1.35 inflation rating (barely above Drone).
- **Militia**: "A great unit for most blue openings. One of my personal favorite units."
- **Gauss Cannon**: Not reviewed individually, but Gauss Fabricator is described as "great value unit, but very slow — usually only used in breachproof strats or insanely defensive sets."

---

## Applied Base Set Lessons from Expert Analysis

### Third Engineer as "Enemy Unit"
> Source: amalloy — "WDIL: sano vs Pyotar" (YouTube)

"This Engineer is an enemy unit." A $2 investment that sits unused compounds into lost tempo. Don't buy a 3rd Engineer unless you have an immediate energy sink that turn. In the Zamora/Cynestra game, the extra Engineer led to droning behind schedule and losing initiative.

### Steelsplitter Click vs Hold Decision
> Source: amalloy — "WDIL: TTK vs Miccull" (YouTube)

"You each click the Steelsplitter, dealing one damage to the opponent and taking two damage yourself. Why would you make that trade?" In games with large absorbers, clicking Steelsplitters to deal 1 damage while giving up 2 HP of absorb is almost always wrong. Hold back Steelsplitters for defense unless clicking enables a breach or kills a critical unit.

### Steelsplitter vs Double Drone in Slow Sets
> Source: Wonderboat — "Prismata Commentary: Kolento vs 307th" (YouTube)

"Splitter purchase is significantly worse than double Drone because Splitter just runs into a Wall." In slow sets with big absorbers, early Steelsplitter is inefficient because its attack gets fully absorbed. Prefer droning up and buying more impactful units later.

### Rhino Timing for Force Field Transition
> Source: Wonderboat — "Prismata Commentary: Kolento vs 307th" (YouTube)

"Buying Rhinos that expire into Force Field buys — the timing of when Rhinos start forcing out Force Fields is amazing." In the late game, Rhinos bought 2 turns before you need to transition to Force Fields serve double duty: immediate defense, then their expiry coincides with the Force Field phase.
