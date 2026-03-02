# The Complete Prismata Strategy Guide

*A comprehensive reference for competitive Prismata play, compiled from guides by 307th/Arkanishu (#1 rated), Yujiri (former #2 rated), Foxclear (wiki series), Elyot Grant and Will Ma (developers), and the broader competitive community.*

---

## Table of Contents

1. [What is Prismata?](#what-is-prismata)
2. [Resources & Economy](#resources--economy)
3. [Turn Structure & Combat](#turn-structure--combat)
4. [The Base Set (11 Units)](#the-base-set-11-units)
5. [The Standard Style](#the-standard-style)
6. [Defense Theory](#defense-theory)
7. [Offense Theory](#offense-theory)
8. [Set Reading](#set-reading)
9. [Openings & Build Orders](#openings--build-orders)
10. [Advanced Units](#advanced-units)
11. [Chill Theory](#chill-theory)
12. [Breachproof Strategy](#breachproof-strategy)
13. [Granularity & Abuse](#granularity--abuse)
14. [Gambit Theory](#gambit-theory)
15. [Endgame & Breach Targeting](#endgame--breach-targeting)
16. [Mathematical Framework](#mathematical-framework)
17. [Competitive Meta & History](#competitive-meta--history)

---

## What is Prismata?

Prismata is a turn-based, perfect-information strategy game created by Elyot Grant, Will Ma, and colleagues at MIT. Two players take turns purchasing units from a shared pool: 11 **base set** units available every game, plus a **random set** of 5-8 units drawn from approximately 105 competitive units. There is no randomness during gameplay, no hidden information, and no deck building. The goal is to destroy all of your opponent's units.

The game is frequently described as "turn-based StarCraft without a map" or "Hearthstone with workers instead of decks." The original prototype was called MCDS (Magic-Chess-Dominion-Starcraft), reflecting its design influences.

**Starting positions are asymmetric:**
- **Player 1** starts with 6 Drones and 2 Engineers (goes first)
- **Player 2** starts with 7 Drones and 2 Engineers (the extra Drone compensates for going second)

At 1800+ Elo, win rates are approximately P1: 48.6%, P2: 50.8%, Draw: 0.6%. P2's extra Drone enables exclusive openings that P1 cannot execute.

---

## Resources & Economy

There are five resources in Prismata:

| Resource | Persistence | Produced By | Notes |
|----------|-------------|-------------|-------|
| **Gold** | Carries over | Drone (1/turn) | Primary resource. Nearly every unit costs gold. |
| **Energy** | Decays | Engineer (1/turn) | Used to buy Drones. Important early, less so later. |
| **Green** (Gaussite) | Carries over | Conduit (1/turn) | Cheapest tech. Can stockpile safely. |
| **Blue** (Behemium) | Decays | Blastforge (1/turn) | Best for defense (Walls). Must spend each turn. |
| **Red** (Replicase) | Decays | Animus (2/turn) | Best for attack (Tarsiers, Rhinos). Expensive to utilize. |

**The float rule:** Gold and Green carry over between turns; Energy, Blue, Red, and Attack decay if unspent. As 307th puts it: "Red and Blue are especially important to spend each turn, since they are valuable and disappear at the end of your turn if unspent." Floating 1-2 Gold or Green is fine; avoid floating 3 or more.

**Tech spending rules of thumb** (307th):
- 1 Conduit needs ~3 Gold/turn to spend its green
- 1 Blastforge needs ~5 Gold/turn to spend its blue
- 1 Animus needs ~8 Gold/turn to spend its red

Overteching (buying more tech buildings than your Drones can support) is a common beginner mistake. If you have 15 Drones but 2 Blastforges, 2 Animuses, and 2 Conduits, you won't have enough gold to spend all your tech.

---

## Turn Structure & Combat

Each player's turn has two phases:

### Defense Phase
If your opponent has attack power, it converts to damage. You choose which of your blocking units take the hits, in any order. Non-fragile units heal to full after surviving damage (this is absorb). The last blocking unit may take partial damage.

### Action Phase
At the start, all swoosh effects trigger: chill is removed, lifespan decrements, exhaust counters tick down, units finish construction, and start-of-turn abilities fire (auto-attack, resource generation). You then buy units and click abilities in any order.

### Combat Resolution
Attack power is pooled from all your attacking units. When you end your turn:

- **If attack < opponent's defense:** They defend. They choose which blockers absorb damage. The last unit may take non-lethal damage that heals away.
- **If attack >= opponent's defense:** **BREACH.** All blockers are destroyed. The attacker assigns excess damage to any enemy units of their choice, typically targeting the highest-value, lowest-HP units (Tarsiers, Drones, tech buildings).

Breach is devastating because (1) you lose absorb entirely, (2) the attacker chooses the targets, and (3) your most valuable fragile units get killed. As 307th warns: "Even though cutting your defense close is good, actually allowing a breach is very bad."

---

## The Base Set (11 Units)

These units are available in every game. Mastering them is the foundation of all Prismata strategy.

### Economic Units

**Drone** (3G + 1E, BT 1, 1 HP) — Produces 1 gold/turn. The core economy unit. Pays for itself in 3 turns. Can hold back as a 1 HP blocker in emergencies. Prime breach target.

**Engineer** (1G, BT 1, 1 HP) — Blocker. Produces 1 energy/turn. Players start with 2. Critical for defensive granularity. Worth roughly 6 gold over its lifetime, but don't overbuy: a 3rd Engineer is only justified in medium-to-high economy sets with good absorbers. Multiple spare Engineers signals underteching.

**Conduit** (4G, BT 1) — Produces 1 green/turn. Cheapest, most forgiving tech. Green carries over, so wasting it is less painful than wasting blue or red.

**Blastforge** (5G, BT 1) — Produces 1 blue/turn. Essential for defense (Walls cost blue). Blue decays, so every blue must be spent.

**Animus** (6G, BT 1) — Produces 2 red/turn. Essential for attack (Tarsiers, Rhinos). Red decays and requires 8 gold/turn to fully utilize. The most expensive tech commitment.

### Combat Units

**Tarsier** (4G + 1R, BT 2, 1 HP) — Automatic 1 attack/turn. The most gold-efficient base set attacker. Two-turn build time means planning ahead. Breach-vulnerable at 1 HP.

**Rhino** (5G + 1R, BT 1, 2 HP) — Prompt blocker. Stamina 2: click to attack for 1 (up to twice total, loses blocking that turn). Versatile: block without clicking, or click for attack. The "Rhino train" (buying 1-2 per turn) provides steady, flexible defense.

**Wall** (5G + 1B, BT 1, 3 HP) — Prompt blocker. The standard absorber — absorbs 2 damage per turn. As 307th notes: "Two Steelsplitters cost 12BB and deal two damage per turn. A Wall absorbs two damage for 5B. Absorb is over twice as efficient as attack." Alone, Wall has poor granularity; pair with Engineers.

**Steelsplitter** (6G + 1B, BT 1, 3 HP) — Blocker. Click: attack for 1 (loses blocking). The "jack of all trades" — inefficient at either role but provides offensive finesse. The opponent never knows whether you'll click or block.

**Gauss Cannon** (6G + 1G, BT 1, 4 HP fragile) — Automatic 1 attack/turn. Fragile: damage is permanent. High HP makes it breach-resistant. Key unit for breachproof strategies.

**Forcefield** (1G, consumes a Drone, Prompt, 1 HP fragile) — Cheap prompt blocker. Converts Drones to emergency defense. Pure soak: dies on any damage assignment. Buy Conduits late-game to fund Forcefields.

---

## The Standard Style

The Standard Style, codified by 307th (Arkanishu, the top-rated player), is the baseline competitive framework. It consists of six principles:

### 1. Buy, Buy, Buy
Keep resources low by purchasing as much as possible each turn. Drones and attackers are investments that compound — getting them out one turn earlier snowballs. The exception: energy can be wasted in mid-to-late game without consequence.

### 2. Live on the Edge
Delay defense until the last possible moment. Defense does nothing until you need it. Buy exactly enough prompt defense to clear the breach warning, then spend everything else on Drones or attackers. But never actually allow a breach: "When you get breached, you can't absorb any of your opponent's attack, meaning that you take more damage, and on top of that they get to target your most vulnerable backline units."

### 3. Absorb is Awesome
Go for the biggest blocker in the set and absorb on it every turn. Absorb is the primary defender's advantage in Prismata. As Will Ma (co-founder) said: "Absorb is the strongest, most busted mechanic in the game, and you want to be taking advantage of it as often as possible." You can only absorb on one unit per turn, so get the biggest one available.

### 4. Changing Gears
Once your attack exceeds the absorb barrier (your opponent's absorber HP), your attackers are dealing real damage. Switch from Drones to attackers. Economy growth past this point yields diminishing returns.

### 5. How Many Drones?
Base economy size on the absorb barrier:
- Wall absorb (2): 12-15 Drones, stay on 2 Engineers
- 4-health absorber: ~20 Drones, consider 3rd Engineer
- 5+ health absorber: 20+ Drones, definitely 3rd Engineer
- No big absorber / aggressive set: <12 Drones

### 6. Setting Up Tech
Don't overtech. Plan tech to reach your absorber and attackers. If the absorber requires heavy tech (like Centurion needing CBBA), that accounts for most of your tech budget. If it's cheap (Doomed Wall needs only B), you have room for additional tech.

---

## Defense Theory

### Absorb
Non-fragile units heal to full after surviving damage. A Wall with 3 HP that takes 2 damage heals back to 3 — those 2 points of damage are effectively nullified. Absorb is the single strongest mechanic in the game.

**Block ordering matters:** With mixed fragile and non-fragile defense, assign fragile units first. Example: 7 damage against Aegis (fragile, 5 HP) + Wall (3 HP). Aegis takes 5 lethal, Wall absorbs remaining 2. Reversing the order wastes absorb potential.

### Soak
Defense that dies. Blockers sacrificed to take lethal damage. Purpose-built fragile units (Forcefield, Aegis) are the best soakers.

### Granularity
The ability to block any specific damage amount while maximizing absorb. Two Walls alone have poor granularity — the opponent can attack for 3 or 4 and force you to lose an entire Wall either way. Add Engineers for varied HP values: 1 Wall + 2 Engineers handles damage from 1 through 5 efficiently.

Maintain 1-2 spare Engineers at all times. Engineers aren't prompt — plan one turn ahead.

### Threat Types
The threat number (sword icon) isn't always accurate:
- **Real threat**: Defend against it or get breached.
- **Fake threat**: Units that can't actually attack (e.g., 3 Perforators powered by only 1 Animus — one is fake).
- **Dying threat**: Units your attack will kill before they can threaten you.
- **Absorber threat**: Clickable absorbers (Omega Splitter) that usually want to defend but could attack.
- **Fake freeze threat**: Excess chill that can't be efficiently applied (e.g., Nivo Charge's 5 chill when your biggest blocker has 2 HP = 3 wasted chill).

### Overdefending
Spending more on defense than necessary. "This is usually a very bad thing — those resources could be better used buying attackers or growing your economy." Check whether you actually need that extra Wall.

---

## Offense Theory

### The Pressure Bonus
"The more damage you have, the better additional damage is" — Yujiri. When opponents must buy defense, they exhaust efficient sources (Walls) first, then turn to expensive options (Rhinos, holding Drones). Concentrated burst forces inefficient responses. This is why pressure units (Scorchilla, Plasmafier) are balanced: weak when they force out cheap defense, strong when they force out expensive defense.

### Deny Absorb
Multiple techniques:
1. **Build-time attackers first** — The longer you go without dealing damage, the longer before the absorber matters. Tarsier (BT 2) denies absorb for an extra turn.
2. **Don't rush the second attacker** — If you have 1 attacker and the enemy has a Wall, a 2nd attacker does nothing until the 3rd arrives (2 damage gets absorbed, same as 1).
3. **Cost-attack units** — Lancetooth against a Wall is incredible because the Wall was already there absorbing; Lancetooth's 2 self-damage is literally worth 0 in that case.

### Offensive Finesse
Flexible attackers (Steelsplitter, Militia) can click for attack or hold back for defense/gold, forcing the opponent to guess your damage output. Against poor granularity, this creates exploits — attacking for specific amounts that deny absorb.

### Don't Waste Attack
"A common new player instinct is to blindly attack with everything, but if your opponent has a Wall and you have nothing except two Militias, attacking does nothing (Wall absorbs it) and you could have got 2 gold instead." Even with 3 Militias, don't attack into a Wall: 3 gold > killing 1 Engineer.

### Attackers Are Better Than Drones
Once past the absorb barrier, attackers are more efficient investments than Drones. You buy Drones first only because early attackers get blunted by absorb. The strategic question is always: when is the right time to switch?

---

## Set Reading

Set reading — analyzing the random units to determine strategy — is the most important skill in competitive Prismata. As the wiki puts it: "This is the most important advice of all. It is the key allowing one to take advantages, win games, and improve in the long run."

### The 6-Step Method (307th)

1. **Identify the best absorber.** This is "the closest to a sure thing you'll get in Prismata." It determines your defensive foundation and cascades into all subsequent decisions.

2. **Determine economy size.** Bigger absorber = bigger economy. Wall (absorb 2) → 12-15 Drones. Centurion (absorb 5) → 20-25+ Drones.

3. **Evaluate tech requirements.** What tech does the absorber need? What's left over for additional buildings?

4. **Plan offensive units.** Select attackers compatible with your tech setup. Random-set attackers are almost always better than base-set alternatives.

5. **Address soak needs.** Plan secondary defenses beyond absorption. Most absorbers need blue, so you'll have a Blastforge for Walls as soak.

6. **Select opening build order.** Choose an opening aligned with your gameplan, adjusted for P1 or P2.

### Strategic Archetypes (Foxclear)

Complex sets often support multiple viable strategies that interact in rock-paper-scissors patterns:

| Archetype | Beats | Loses To | Key Units |
|-----------|-------|----------|-----------|
| **Big Red** (RRR/RRRR) | High economy | Aggression, burst, breachproof | Amporilla, Vai, Tatsu, Lucina |
| **Aggressive** | High economy, Big Red | Mid-tier absorb, burst | Grimbotch, Fission Turret |
| **Defensive** | Breachproof | Big Red, aggression | Centurion, Defense Grid |
| **Breachproof** | Big Red, aggression | High economy, defensive | Gauss Cannon, Iso Kronus |
| **Damage Sink** | Good absorbers | High damage past capacity | Bloodrager, Thermite Core |

The player who commits first gets countered. Delay committing until your opponent tips their hand: "It is advisable to wait until your opponent plays a decisive move toward one strategy, and then go for the counter."

### Counters & Synergies
"Some units absolutely counter others." Shiver Yeti counters Plexo Cell. If your opponent can access the counter, treat the countered unit as absent from the set. But if they can't reach it, the countered unit is still live.

Synergies can be equally decisive: Valkyrion + Cryo Ray (freeze the Barriers), Redeemer + Thunderhead (Gauss Charges crash into Thunderhead on its last turn). Spotting these combinations early defines top-level play.

---

## Openings & Build Orders

### Notation
Each line = one turn. `/` separates turns. D = Drone, E = Engineer, A = Animus, B = Blastforge, C = Conduit, T = Tarsier, R = Rhino, W = Wall, S = Steelsplitter, G = Gauss Cannon, F = Forcefield. `1` = the relevant advanced unit.

### Key Player 1 Openings

| Opening | Notation | Economy | When to Use |
|---------|----------|---------|-------------|
| **Crazimus** | A | Ultra-low | "Only when you're sure anything else would lose to P2 Crazimus." |
| **Elyot Animus** | DD/A | Low | Ultra-aggressive. Viable with Electrovore, Grimbotch. "Eternally floating 2 gold." |
| **Fastuit** | DD/DC | Low | "P1's only viable line in Zemora or Tia rush sets." |
| **Natural Animus** | DD/DD/DDA | Standard | Default P1 red line. Best Feral Warden opening. |
| **Natural Blastforge** | DD/DD/DDB | Standard | Blue economic units (Flame Animus, Ebb Turbine). |
| **Econ Blastforge** | DD/DDE/DDD/DDDB | High | Standard for high-econ blue sets (Odin, Omega Splitter). |
| **Econ Condimus** | DD/DDE/DDD/DDDC/DDDA | High | "Go-to in high-econ Cynestra sets." |

### Key Player 2 Openings

| Opening | Notation | Economy | When to Use |
|---------|----------|---------|-------------|
| **Fastimus** | DD/DA | Low | "Typical P2 red rush." Blood Phage, Electrovore, Amporilla. |
| **Natural Conduit** | DD/DDC | Standard | **"Probably the best and most common opening overall."** |
| **Blastuit** | DD/DDC/DDB | Standard | "Standard for any midrange blue-green set." |
| **Double Animus** | DD/DD/DAA | Low-Med | Tatsu Nullifier or Shadowfang rushes (though Shadowfang rushes "are just bad"). |
| **Double Conduit** | DD/DDC/DDC | Medium | "Go-to in Zemora Voidbringer games." |
| **Econ Conduit** | DD/DDE/DDDC | High | "Often feels forced in high-econ sets." |

### P1/P2 Asymmetry
Most aggressive openings are P2-exclusive because of the extra Drone. However, Doomed Drone and Wild Drone make many P2 openings available to P1: Delayed Tia, Tatsu Rush, and Double Scorchilla all become P1-viable with these alternate economy units.

### Opening Philosophy
"Unlike chess, opening book study is largely ineffective in Prismata due to the random unit set present in each game." However, knowing aggressive builds is essential for both executing and defending against them: "Many aggressive builds are difficult or impossible to overcome if the opponent does not anticipate them."

---

## Advanced Units

### Absorber Rankings (307th)

Absorbers define the game. 307th ranked them on value (damage nullification efficiency), convenience (tech/build requirements), and clunkiness (difficulty obtaining full value):

**S Tier:** Centurion — "Currently the strongest unit in the game, and it is really rare that I will not go for it." Even worth buying against freeze (Foxclear).

**A Tier:** Defense Grid (strongest raw absorb, needs 3B, chill-vulnerable), Energy Matrix (reliable, convenient), Colossus (strong but clunky, fragile), Xeno Guardian (vigilant — attacks while defending).

**B Tier:** Infusion Grid, Bombarder, Urban Sentry, Omega Splitter, Doomed Wall, Xaetron (anti-abuse specialist), Doomed Mech, Mahar Rectifier, Feral Warden, Odin (primarily attacker), Chieftain.

**C Tier:** Protoplasm (weak early, strong late), Wall (convenient but weak).

**Rhino Tier:** Rhino (weakest absorber due to red's aggressive nature).

**Special:** Arka Sodara — Insanely high value under right circumstances, but costs 7 attack. Creates a paradox where both players avoid buying it first.

### Big Red Units (307th)

Expensive attackers costing 3-4 Red. High commitment, high reward:

- **Amporilla** (3R): Creates Tarsiers for scaling. "Four-Tarsier Amporilla is extremely strong." Vulnerable to early pressure.
- **Lucina Spinos** (3R): Self-sustaining via Perforators. Early punishment critical.
- **Tatsu Nullifier** (4R): "Hard counter to big absorbers." Breachproof neutralizes it.
- **Vai Mauronax** (4R): Legendary anti-absorber. Excels vs Centurion.
- **Shadowfang** (3R): "The least impactful big red. Just a vanilla, efficient attacker."

Big Red excels against high-economy strategies and delayed pressure (Zemora, Savior). Weak to aggressive low-econ strategies, burst damage, and economy sacrificers (Plasmafier, Venge Cannon).

### Noticeable Units (Foxclear)

Units that cannot be ignored in any set they appear:

**Centurion** — The strongest. Buy it almost always.

**Tia Thurnax** — Highest immediate impact. 7 burst damage. Timing is critical: higher economy = buy later. "Naked Tia" (without other attackers) rarely succeeds.

**Thunderhead** — Anti-aggression. "Will make any aggressive strategy crumble" unless opponent has burst (Gaussite Symbiote, Cluster Bolt). Amazing synergy with Redeemer.

**Xaetron** — Anti-abuse star. Regenerates health regardless of damage patterns. Never click unless opponent isn't attacking it. Dual-absorber strategy with Wall averages 5 absorb per turn.

**The Wincer** — Highest damage from a single unit. The second shot usually connects. You can HOLD The Wincer — the pressure alone does work. Against frontline defense, set up exact damage with permanent attackers and hold Wincer.

**Arka Sodara** — Whenever in the set, you need the 7-attack threshold with BBR tech. Counter-Arka (buying your own with exactly 7 damage) is well-known but "do not overestimate it — getting Arka first means you click it first."

**Thermite Core** — "Difficult to deal with. With the right set-up, you can deny absorb completely for a ridiculous cost." Counter: defend for exact without high-value absorbers, or go breachproof.

### Attacker Efficiency Rankings (Yujiri)

Yujiri created a mathematical efficiency framework using recursive inflation analysis. Drone inflation = 1.33 is baseline. Higher = more efficient:

**Powerhouse (>1.50):** Arka Sodara (1.74), Feral Warden (1.63), Odin clicks (1.64), Lucina (1.54-1.58), Plasmafier (1.54), Shadowfang (1.51), Cynestra (1.50).

**Strong (1.40-1.50):** Drake (1.48), Wincer (1.46), Hellhound (1.46 — "Best attacker in the game, spammable, no counter, no enabler"), Tesla Coil (1.46), Iceblade Golem (1.47 full chill), Apollo (1.41), Redeemer (1.41 — unique: scales with soak), Flame Animus (1.40), Zemora (1.40).

**Standard (1.35-1.39):** Tarsier (1.39 — baseline permanent red), Gauss Cannon (1.37), Scorchilla (1.36 — inefficient on paper but +3 pressure bonus), Steelsplitter (1.35 — base set worst).

---

## Chill Theory

307th dedicated six articles to chill — it's that important.

### Why Chill is Good
Chill prevents units from blocking, providing strategic value without direct damage:

1. **Absorb denial** — Freeze the strongest absorber. Effectively increases your damage output.
2. **Exploits** — Freeze blockers to disrupt granularity and reduce absorption.
3. **Eliminating doomed units** — Freeze a lifespan-1 unit so it dies without soaking any damage.
4. **Threat creation** — The most significant use. Chill threat forces the opponent to either buy extra defense (which you don't activate chill against, wasting their resources) or risk breach (when you do activate it). Either way, you win.

### Chill Unit Categories
**Low activation cost** (repeatedly cheap): Cryo Ray, Shiver Yeti, Tatsu Nullifier, Iceblade Golem, Nivo Charge, Vai Mauronax. Better at absorb denial and exploits.

**High activation cost** (significant per use): Frostbite, Frost Brooder, Endotherm Kit. Better at concentrated threat.

### Defending Against Chill

**Against absorb denial:** Maintain backup absorbers. You can't stop them from freezing your main one.

**Against exploits:** Build more Engineers for redundancy in blocking.

**Against freezing doomed units:** Delay doomed units at higher lifespan. Produce many to exhaust limited freeze.

**Gambits:** Allow a small breach rather than fully defending. Make both opponent options (breach or hold) roughly equal, minimizing their best outcome. Start small.

**Vigilance:** Units that block while doing something else (attacking, making gold). Xeno Guardian is the prime example. "I can't overemphasize enough how hard vigilant units counter threat" — 307th.

**Fake threat:** The breach warning assumes all chill is applied optimally. It often overestimates real threat. Calculate wasted chill from size mismatches and subtract from threat.

---

## Breachproof Strategy

"Breachproof plays completely differently from the Standard Style. You make your entire side resilient so that you can safely allow a breach." — 307th

### The Concept
Skip traditional defense. Mass high-HP green attackers (Gauss Cannons, Iso Kronuses) backed by alternative economy (Trinity Drones, Thorium Dynamos). Your opponent breaches you every turn, but damage is minimal because all your units have massive HP.

Mid-to-late game: the standard player defends with most resources; the breachproof player attacks with everything. The standard player destroys the breachproof player's economy (Drones). When the breachproof player's economy is gone, they reach peak attack. If the standard player survives a few more turns, they destroy the attackers and win.

### Types of Breachproof

**Pure Breachproof:** Convert Drones into Trinity Drone or Thorium Dynamo economy. Mass Gauss Cannons and Iso Kronuses. Green pressure (Cryo Ray, Nivo) helps. Weak against strong absorbers and soak.

**Semi-Breachproof:** No Trinity/Thorium needed. Enabled by Wild Drone (frontline, efficient) or Gauss Fabricator. "Easier to pull off."

**Venge All-in:** Save up Drones and green, then convert everything into Venge Cannons at once. Cluster Bolt is essential — "if Cluster Bolt isn't in the set, don't bother."

**Breachproof Transition:** Late-game shift when standard defense becomes unsustainable. Only works if your existing units are breach-resistant (not Tarsiers).

### The RPS Dynamic
Breachproof beats standard play → Standard (avoiding chill) beats breachproof → Big Red/Tatsu beats standard → Breachproof beats Big Red. Delay commitment: the first player to commit gets countered. Eventually resource constraints force partial commitment.

### Countering Breachproof
"Focus on non-BP units (Tarsiers, Steelsplitters) and your opponent's economy: Drones, or Trinity Drones. It is tempting to go for the BP attacking units like Gauss Cannon to reduce pressure, but it will simply let your opponent build more of them."

---

## Granularity & Abuse

### What is Granularity?
"The ability to defend efficiently with maximum absorb no matter what damage your opponent causes" — Foxclear. Two Walls against 3 attack = one Wall takes all 3, no absorb on the other. Add an Engineer: 1 on Engineer, absorb 2 on Wall. Better granularity.

Maintain 1-2 Engineers sitting around for granularity. Engineers aren't prompt — plan ahead. A 2-health defender (Rhino, Forcefield) alongside an Engineer covers both 1 and 2 soak needs.

### Abusing Defenses

**Attack for 0:** Use units that spend attack (Bloodrager, Thermite Core, Lancetooth, Arka Sodara) or skip-turn units (Scorchilla, Iso Kronus). Against big absorbers, this denies absorb entirely. Devastating against lifespan defenders like Plexo Cell.

**Granular attack:** Hold attackers (Steelsplitter, Militia) to hit specific numbers that deny absorb. Example: opponent has 2 Engineers + 2 Walls. Attacking for 5 = absorb 2 on Wall. Attacking for 4 = either absorb only 1, or lose both Engineers and absorb 2 but with zero granularity next turn. Always prefer the abuse if the held attacker has defensive value.

**Freeze for abuse:** Freeze Engineers with Cryo Ray or Iceblade Golem to strip granularity, then attack for the abusive number. "Usually OK to spend multiple Cryo Ray charges for even a 1-point abuse."

### Anti-Abuse Units
- **Engineer** — Core granularity unit.
- **Rhino** — Prompt, gains threat when opponent doesn't attack.
- **Xaetron** — "The star against any kind of abuse." Heals on off-turns, gains health at 0 attack, provides full defense on big turns.
- **Cauterizer/Sentinel/Hellhound** — Produce Engineers.

### The Fake Abuse Warning
"Having a granular attack is only worth it if you get an advantage for not attacking at full value." If holding an attacker provides no defensive value, just attack with it.

---

## Gambit Theory

### What is a Gambit?
"The decision to deliberately not defend fully when you have the ability to do so, and when you are not going breachproof" — Foxclear. You bet that your opponent won't attack at full power. Different from ignoring fake threat: all undefended threat is real.

### Why Gambit?
Greed. You prefer to spend resources on offense or economy rather than defense. Often the player who feels behind will gambit.

### Easy Gambits
**Lifespan attackers** (Grimbotch, Chieftain, Doomed Mech) are safe to gambit against. Clicking them to attack costs health AND defense tempo:
- 1 Grimbotch click: opponent loses 2 HP + 2 defense tempo. Must breach a Wall to break even.
- Chieftain: 7 HP + 7 defense tempo. Very safe gambit.
- Doomed Mech: 5 HP + absorber potential. Easy gambit.

### Dangerous Gambits
Don't gambit a Centurion (opponent removes pressure cheaply via breach). Don't gambit when your attackers are breach-vulnerable (Tarsiers, Shadowfangs) — the breach kills high-value units.

### Should You TAKE a Gambit?
"Play your defense as if you are accepting. Then try to defend against your opponent's next attack. If you end up in a worse position than what you gained, restart and refuse it."

### Gambit Chaos
"Sometimes, to respond to a gambit, you offer your own. When one is taken, it can quickly turn into chaos where both players offer a breach each turn." Usually means defense is desperate. Watch Forcefield supply — exhaustion can turn a good gambit bad.

---

## Endgame & Breach Targeting

The endgame is a "natural inflection point" where strategic priorities invert. Long-term investments (Tarsiers, economy) face a world where short-term burst (Grimbotch, Tia Thurnax) becomes more valuable.

### Game Phases (Foxclear)

1. **Develop Economy** — Buy Drones and Engineers. Don't waste gold or energy.
2. **Prepare the Battle** — Get tech (Green, Blue, Red). Stabilize economy.
3. **Set Up Absorption** — Attack numbers are low. Get the biggest absorber when it can absorb meaningfully. Can still expand economy.
4. **Over the Barrier** — Both players dealing real damage. Stop buying Drones. Concentrate on attack and defense. "Do not defend more than necessary!"
5. **Under Pressure** — Damage rising. Difficult to buy attackers while defending. May need Forcefields, held Drones, Steelsplitters on defense. Watch Wall supply.
6. **Crumbling Defenses** — One or both players breached. Target low-HP attackers, economy, and high-damage/low-health units.
7. **Draw** (rare) — Both players breached, attack forces destroyed, blue-health units remain. Blastforge with 3 blue HP can force a draw against 2 or less remaining attack.

### Breach Targeting Priority
When breaching, target in this order:
1. **Tarsiers** (1 HP, permanent attack — highest damage-per-health ratio)
2. **Drones** (1 HP, removes economy)
3. **Animus** (removes 2 red/turn)
4. **Blastforge** (removes 1 blue/turn)
5. **Other tech buildings** and high-value units

### Lifespan Units as Blockers
"Attacker-defenders with lifespan are almost always better off blocking than attacking on their last turn. Doomed Mech can either give you 2 attack or 5 defense on its last turn." — Yujiri

---

## Mathematical Framework

### Resource Values (Yujiri)
Derived from tech building balance (each produces 1/3 of cost per turn):
- Gold = 1.00 (baseline)
- Green = 1.33
- Blue = 1.67
- Red = 1.00 (Animus costs 6, produces 2)
- Energy ≈ 0.56

### Inflation
"How much more valuable things are now vs later." Drone inflation = 1.33x (9 gold now → 12 gold worth next turn). Higher inflation means prompt, fast units are relatively better.

Formula: `(cost + production_per_turn) / cost`

### Barrier Value
Wall costs 6.67 effective gold, gives 3 HP blocking → 1 BV ≈ 2.22 gold. Mixed with Engineers: approximate BV = 2.3 in base set.

### Key Equilibrium Points
- Tarsier/Rhino: 1.50 (above = Rhinos better, below = Tarsiers)
- Wall/Forcefield: 1.47
- Gauss Cannon/Tarsier: 1.47

### Why This Matters
Understanding inflation tells you when to buy what. In high-econ games with big absorbers, inflation is lower — non-permanent units (Grimbotch, Doomed Mech) become relatively better. In low-econ aggressive games, inflation is higher — prompt units and fast attackers dominate.

---

## Competitive Meta & History

### Development
Prismata was created at MIT in 2010 as a physical prototype. Kickstarter launched October 2014 ($125K raised). Steam Early Access began November 2017. The competitive community, while small, produced some of the deepest strategy analysis in any turn-based game.

### Key Figures
- **307th / Arkanishu** — #1 rated player. Author of The Standard Style and the Prismata Library blog (27 articles).
- **Yujiri** — Former #2 rated (~2100). Author of the most mathematically rigorous strategy content published for any game of this type.
- **Foxclear** — Competitive player. Authored 12 comprehensive wiki strategy guides (7 advanced + 5 beginner) with unmatched practical depth.
- **Msven** — Top player who won Grand Prix 2019. Known for dynamic playstyles. Championed the Militia buff.
- **Elyot Grant** — Co-founder/developer. The "Elyot Animus" rush is named after him.
- **Will Ma** — Co-founder. "Absorb is the strongest, most busted mechanic in the game."
- **amalloy** — Community contributor with popular video series.
- **RuinedShadows** — Author of "Master in a Month" learning roadmap.

### Grand Prix 2019
| Place | Player |
|-------|--------|
| 1st | Msven |
| 2nd | 307th / Arkanishu |
| 3rd | Apooche |

### Balance Philosophy
"Rather than simply hitting obvious outliers with nerfs, we took a more nuanced approach — adjusting units that created undesirable patterns while also buffing units that were underused." Key changes: Odin nerf (5 → 3 HP, most P1-favoring unit), Wild Drone redesign (entirely new unit), Militia buff (Msven's suggestion), Redeemer confirmed unbiased.

### On Autowins
Every Prismata set is theoretically an autowin for one player — true of all deterministic perfect-information games (Chess, Go, Checkers). But as Yujiri notes: "In most sets it only takes a very small mistake to make the theoretically-winning player lose. Most alleged autowins have counters that aren't immediately obvious."

### Learning Roadmap (RuinedShadows)
1. Campaign Chapter 1, Combat Training, read The Standard Style, practice vs Master Bot
2. Beat Master Bot ~30%, start ranked play (~level 28-32)
3. Watch 307th's videos, study Common Openings + Absorber Rankings + Set Reading
4. Deep set reading focus; tournament play
5. Master push: gambits, counters, synergies, freeze, granularity, exploits

"You don't need to be a strategy game genius. My ranked win rate was only about 43% when I entered Master Tier."

---

*This guide was compiled on February 20, 2026, from sources spanning 2014-2025. All strategic content is attributed to its original authors. The game's servers remain online though the competitive player base is small.*
