# Discord Community Feedback Analysis: Master Bot Behavioral Issues

**Analysis date:** 2026-02-21
**Data source:** 2,095 Discord messages from the Prismata community (2016-2026)
**Channels scanned:** prismata_chat (1,204), strategy_advice (425), unit_and_game_design (137), ask_a_dev (121), questions_and_help (63), alpha_player_lounge (55), general_chat (53), general (21), dev_seeking_feedback (16)
**Top contributors:** amalloy (92), mrguy888 (87), velizar_ (86), masn6811 (73), awaclus (71), shadourow (68), zera777 (58), liadahlia (43), steel0229e (39), p0lari (38), .holyfire (multiple high-value reports), .bky_1556, apooche (early alpha player, deep game knowledge)

---

## 1. ALREADY FIXED Issues

These issues were reported by the community and have already been addressed in our codebase.

### 1A. Borehole Patroller Overvaluation (Pixie cost included)

**Status:** FIXED

The bot values Borehole Patroller based on its full purchase cost (5GBB), but part of that cost pays for a Pixie token that is created alongside it. The Borehole's intrinsic value is significantly less than its sticker price.

**Key reports:**
- **apooche** (2025-03-09): "Master bot generally values units based on their cost. For example it overvalues borehole patrollers because it doesn't consider the fact that part of their cost was for a pixie."
- **p0lari** (2018-04-14): "the solution that involves getting 4 cryos and freezing xeno would not win if the bot soaked on a borehole instead of both shield barriers"
- **Deleted User** (2020-07-14): Discussion of Borehole Patroller inflation formula, noting the Pixie cost should be separated.
- **awaclus** (2018-06-19): "the main difference between sentry and borehole is that the latter comes with a Pixie"

**Frequency:** ~6 explicit reports, referenced in broader valuation discussions
**Community diagnosis matches our fix:** Yes -- the community correctly identified that part of Borehole's cost was for the Pixie.

### 1B. Corpus Overvaluation (Husk cost included)

**Status:** FIXED

Similar to Borehole -- Corpus (6RR) creates a prompt Husk when purchased. The bot valued Corpus at full cost without subtracting the Husk's value, leading to absurd defense assignments (absorbing on 0-stamina Corpus over a Wall).

**Key reports:**
- **sano712** (2020-06-23): "it's 2020 and master bot still absorbs on 0-stam corpus over wall :ThinkTank:" (shadourow sarcastically replied: "That'll be fixed by fall 2019")
- **chlobes** (2019-12-27): "absorbing on \<unknown\> corpus over wall is prettimuch always bad, and the fact that it absorbs on 0 stam corpus implies that it absorbs on 1 or 2 stam corpus over wall (which is true)"
- **.holyfire** (2025-01-05): "Ironically, I'm pretty sure that even a fresh Corpus is worth less than a wall... So that doesn't make much sense either way."
- **glacialblades666** (2025-03-09): "it also sacrifices walls to absorb on an empty corpus"
- **masn6811** (2020-12-08): "the sac wall to save corpus and click it is obviously bad"
- **siepu** (2021-05-14): "it treats vore as costing 8 compared to 4 for engis (like, bot always absorbs on corpus instead of a wall)"
- **_sakuya** (2018-06-18): "Corpus buys you discount walls but they dont absorb"

**Frequency:** ~10+ explicit reports spanning 2018-2025, one of the most-discussed issues
**Community diagnosis matches our fix:** Yes -- correctly identified as a cost-decomposition problem.

### 1C. Galvani Drone Targeting During Breach

**Status:** FIXED

MB would target Galvani Drones during breach instead of more valuable units (Drones, Walls, etc.), because it valued Galvani based on purchase cost rather than practical in-play value. A Galvani Drone in play is worth very little (already used its energy).

**Key reports:**
- **.holyfire** (2025-03-07): "Masterbot's Galvanophobia is just weird. It's bad enough that it targets Galvani when it could have killed drones instead, which literally strictly dominates. But targeting Galvani instead of breaching is just... Wow." **Replay: `78xVR-XRYE0`**
- **.holyfire** (2025-03-07): "It's painfully nonsensical to kill Galvani instead of drone, or -- as in this game -- Two Galvani instead of wall and drone."
- **p0lari** (2018-03-11): "these gauss cannons seem pretty bad to me, and so does killing galvanis instead of engis"
- **xyotsuba** (2018-04-14): "he killed galvani so i wasted 2 blu"

**Frequency:** ~5 explicit reports
**Community diagnosis matches our fix:** Yes -- Galvani's in-play value is nearly zero; targeting it over Drones/Walls is strictly dominated.

### 1D. Health/Stamina Not Considered in Breach Targeting

**Status:** FIXED

MB ignored remaining health and stamina when comparing breach targets. A 2-health Tantalum Ray would be targeted over a full-health Steelsplitter, even though the Steelsplitter was worth more to kill.

**Key reports:**
- **.holyfire** (2025-03-09): "TIL Master Bot Apollo will target 2-Health Tantalum Ray rather than Steelsplitter. In general, MB seems to never consider Health or Stamina when comparing between different units."

**Frequency:** ~3 explicit reports (health/stamina in breach context)
**Community diagnosis matches our fix:** Yes.

---

## 2. DEFENSE / ABSORB Issues

### 2A. Stamina-Blind Defense Assignment (HIGH SEVERITY)

**The single most reported specific bug.** MB assigns defense purely based on unit cost, completely ignoring stamina. This causes it to absorb on 0-stamina units that are about to die anyway, wasting absorb on units that provide zero future value.

**Specific manifestations:**
- **0-stam Corpus over Wall** -- most commonly cited (see 1B above)
- **0-stam Deadeye over Wall** -- zakisan1 (2019-01-02): "Bot chose to absorb on 0 Stamina Deadeye instead of Wall -- I assume the AI still valued the Deadeye as if it had Stamina? `Wiieo-DVcO6`, Turn 13, 14 and 15."
- **0-stam Bombarder over Energy Matrix** -- siepu (2019-03-24): "Bombarder so strong Master Bot absorbs on the empty one instead of Energy Matrix `MRleA-YHVhe`"
- **0-stam Bombarder over Xeno/Energy Matrix** -- liquideggproduct (2023-01-31): "TIL: Master Bot will absorb on a 0 stamina Bombarder instead of Xeno or E Matrix"
- **.holyfire** (2025-01-05): "it seems it ignores stamina levels when assigning defense. e.g., absorbing on spent Corpus instead of Wall"
- **2 engis over 0-stam Rhino** -- sano712 (2019-12-26): "has master bot always chosen to soak 2 engis over 0-stam rhino? because i'm seeing this happen often"
- **chlobes** (2019-12-26): "masterbot doesn't understand stamina" (general summary)
- **chlobes** (2019-12-27): Detailed analysis explaining that absorbing on unknown-stamina Bombarder over E-Matrix is sometimes correct, but absorbing on any corpus over wall is always wrong.

**Frequency:** 15+ explicit reports, discussed repeatedly from 2018-2025
**Severity:** HIGH -- this is a pure heuristic bug. A unit with 0 stamina remaining is about to die regardless; absorbing on it wastes the absorb entirely. Costs MB absorb value every game where it has units with stamina.
**Fixability:** HEURISTIC LAYER -- the defense assignment phase needs to factor in remaining stamina. A 0-stamina unit should be treated as soak-only (about to die), never as an absorb target. Higher stamina units are more valuable absorb targets because absorb value scales with remaining life.

**Replay codes provided:** `Wiieo-DVcO6` (turns 13-15), `MRleA-YHVhe`

### 2B. Absorbing on Wrong Unit Class (MEDIUM SEVERITY)

Even with non-zero stamina, MB sometimes absorbs on the wrong unit because it uses cost as a proxy for absorb value. A high-cost unit that does something other than defend (e.g., Bombarder with attack ability, Corpus with click ability) is not necessarily a better absorb target than a cheaper dedicated defender.

**Key reports:**
- **siepu** (2021-05-14): "it treats vore as costing 8 compared to 4 for engis" -- Electrovore costs 8 (4GRR) and engis cost 4 (2G), but engis are better absorb targets in many situations.
- **apooche** (2025-03-09): Summary explaining the root cause -- "Master bot generally values units based on their cost."

**Severity:** MEDIUM -- less impactful than 0-stam bug, but still costs absorb value
**Fixability:** HEURISTIC LAYER -- defense assignment should consider: (a) remaining stamina, (b) whether the unit has already used its ability/attack this turn, (c) whether absorbing saves a unit that would otherwise die vs. one that would survive anyway.

### 2C. Sacrificing Walls to Preserve Empty Corpus (LOW SEVERITY)

In some losing positions, MB will sacrifice a Wall (a permanent defender) to keep absorbing on an empty (0-stamina) Corpus.

**Key reports:**
- **glacialblades666** (2025-03-09): "it also sacrifices walls to absorb on an empty corpus"
- **masn6811** (2020-12-08): "the sac wall to save corpus and click it is obviously bad, but the game is already lost by then"

**Severity:** LOW -- usually occurs in already-lost positions
**Fixability:** HEURISTIC LAYER -- this is a consequence of 2A (stamina blindness)

---

## 3. BREACH / TARGETING Issues (Beyond Already-Fixed)

### 3A. Chill Targeting is Extremely Poor (HIGH SEVERITY)

MB wastes chill (freeze) shots on units where freezing has no impact on the defense outcome, instead of freezing high-value absorbers.

**Key reports:**
- **alex319** (2020-11-20): "The master bot seems very poor at using chill. `izkDb-sy6uF` On turn 11 the master bot wastes 6 cryo ray shots chilling walls which don't even affect the outcome of the block, when it could have chilled the barrier instead" (shadourow confirmed: "Yes indeed")
- **.holyfire** (2023-01-30): Listed "Chill in general" as one of MB's worst areas
- **stacko** (2019-12-31): "Breaching with 0 attack by freezing: the Master Bot breach" -- describing MB freezing all defenders but having no attackers to capitalize, a useless move

**Frequency:** ~5-8 explicit reports
**Severity:** HIGH -- chill is one of the most strategically important mechanics. Correct chill targeting (freeze the absorber to deny absorb value) is a huge swing. MB wasting chill on irrelevant targets is a major weakness.
**Fixability:** HEURISTIC LAYER (hard) -- chill targeting requires simulating the defense assignment after freezing. The optimal chill target is the one that maximizes breach damage by denying the most absorb/soak. This is computationally expensive but can be approximated.

**Replay codes provided:** `izkDb-sy6uF` (turn 11)

### 3B. Breach-Avoidant Play: Kills Frontline/Economy Instead of Breaching (MEDIUM SEVERITY)

MB sometimes kills frontline units or economy (Wild Drones, Drones) when breaching would be strictly better.

**Key reports:**
- **velizar_** (2022-06-04, via context): "`m+Yhp-rSaTr` Last turn: Bot chooses to kill two of my wild drones rather than to breach me for Lucina + 1 Tarsier"
- **p0lari** (2018-01-24, via context): "one big difference I know is it no longer chooses to kill your frontliners instead of breaching" -- this was historically fixed for frontline, but economy-vs-breach decisions remain problematic
- **vargus2254870** (2019-10-20, via context): "bot holds lifespan 1 grimbotch instead of breaching"
- **zera777** (2019-10-20, via context): "Even if breaching is not always correct, it's correct often enough that I'd program the bot to always do it."

**Frequency:** ~5 reports
**Severity:** MEDIUM -- breaching is usually better than killing economy when you have enough damage, but there are legitimate cases where killing economy is correct
**Fixability:** HEURISTIC LAYER -- the breach decision needs to compare the value of breach damage (killing high-cost units behind the defense line) vs. the value of killing exposed economy/frontline. Currently, the GreedyKnapsack may undervalue breach because it doesn't look ahead to see what units are behind the wall.

### 3C. Apollo Snipe Targeting (LOW SEVERITY)

MB makes suboptimal snipe target choices, though it occasionally shows glimmers of intelligence.

**Key reports:**
- **.holyfire** (2025-03-09): "Master Bot Apollo will target 2-Health Tantalum Ray rather than Steelsplitter" -- targeting by cost rather than remaining value
- **liquideggproduct** (2022-06-04): "Master bot sniped a conduit with Kinetic to stop Zemora from firing" -- amalloy responded skeptically: "ITYM it sniped a conduit because it owned a kinetic" (i.e., it was accidental, not strategic)

**Severity:** LOW -- Apollo is uncommon and snipe decisions are complex
**Fixability:** Mostly addressed by health/stamina fix (1D); remaining issues are strategic (snipe-to-deny-tech is deep planning)

---

## 4. BUY / VALUATION Issues

### 4A. Gauss Cannon Rush Addiction (HIGH SEVERITY)

The single most-discussed strategic weakness. MB defaults to Gauss Cannon rushes far too often, especially in Thorium Dynamo sets. It ignores superior random set units in favor of base-set Gauss Cannons + Forcefields, resulting in trivially beatable play.

**Key reports:**
- **velizar_** (2019-07-19): "Typical game against master bot: getting a complex but intriguing set, then master bot rushes me with gauss cannons and defends with force fields, loses trivially to base set."
- **stacko** (2019-07-19): "Master bot always seems to think Thorium Dynamo = rush Gauss Cannons"
- **velizar_** (2019-07-19): "AI goes dynamo gauss with walls: `i9LTQ-x+f9s`" / "Here I lose to Iso + Gauss + Thorium `BxFCp-Yz990`"
- **velizar_** (2020-01-01): "Master bot: gauss cannon rush `QuXEb-4GM0t`"
- **p0lari** (2020-03-24): "why is master bot buying double gauss charges into my wall"
- **velizar_** (2020-04-17): "Also the bot buys gauss charges when they are certain to be absorbed, very cool."
- **velizar_** (2020-02-26): "Bot's strategy: Thorium Gauss breach-proof, when gauss is out of supply engi/drone/forcefield, when engi is out of supply float all the gold (has 51 gold at the end of the game)" **Replay: `enK@3-JLgdD`**

**Frequency:** 15+ reports
**Severity:** HIGH -- this is the most exploitable pattern. Experienced players know MB will go Gauss rush and can counter it trivially with higher-economy base-set play.
**Fixability:** DEEP CHANGE -- this is a fundamental issue with the GreedyKnapsack buy algorithm, which evaluates units individually without considering the full game context. Gauss Cannons score highly on cost-efficiency metrics but are strategically weak in many sets. The neural net should eventually learn this, but heuristic fixes (e.g., penalizing Gauss Cannon purchases when better attackers exist) could help.

**Replay codes provided:** `i9LTQ-x+f9s`, `BxFCp-Yz990`, `QuXEb-4GM0t`, `enK@3-JLgdD`, `0jBEo-Kbqz9`

### 4B. Mobile Animus / Rhino Misuse (MEDIUM SEVERITY)

MB buys Mobile Animus (prompt Rhino producer) far too eagerly and too early, resulting in too many Rhinos and not enough permanent attack. Rhinos are supposed to be bought late (to get 2 attacks before soaking), but MB treats them as regular attackers.

**Key reports:**
- **velizar_** (2020-02-11): "I love it when the bot buys out all the mobile animuses and turns them into rhinos while wasting the red" / "it's turn 10 and it bought 9 mobile animuses so far"
- **zera777** (2020-02-11): "Master Bot does suck with Mobile Animus. And also Rhinos. Sometimes MB buys 2 Tarsiers, then 10 Rhinos, then loses because it has almost no permanent attack. The goal of Rhino is to buy it as late as possible while still getting both attacks with it before soaking."
- **ggmoyang** (2018-12-23): "Bot does weird things with mobile animus"
- **siepu** (2018-12-22): "master bot just galaxy brained me with the turn 2 double mobile animus opening"
- **nvlx** (2018-11-20): "master bot is up to something when buying all these mobile animus"
- **nvlx** (2020-02-14, via context): "i remember rigging all master bot achievements by adding at least zemora and mobile animus in the sets" (i.e., MB is so bad with these units that including them guarantees a win)

**Frequency:** ~8 reports
**Severity:** MEDIUM -- affects games with Mobile Animus in the set. MB wastes enormous resources on temporary attackers.
**Fixability:** HEURISTIC LAYER (tricky) -- Rhino timing requires understanding that temporary attack (lifespan) should be bought late for maximum value. The GreedyKnapsack evaluates units by immediate value-per-cost, which misses the timing dimension entirely.

### 4C. Grimbotch Over-Purchase (LOW-MEDIUM SEVERITY)

MB buys too many Grimbotches relative to Tarsiers.

**Key report:**
- **flakmaniak** (2020-04-27): "Master Bot buys way too many Grimbotches and not enough Tarsiers."

**Severity:** LOW-MEDIUM -- Grimbotch (3G, prompt blocker + 1 attack, lifespan 2) is soak-oriented, while Tarsier (4GR, permanent 1 attack) is attack-oriented. Over-buying Grimbotches results in low permanent attack.
**Fixability:** HEURISTIC LAYER -- similar to the Rhino problem; temporary units are overvalued relative to permanent ones.

### 4D. Overteching / Wasting Tech Resources (MEDIUM SEVERITY)

MB sometimes buys tech buildings (Blastforge, Conduit, Animus) that it doesn't need, wasting resources on infrastructure instead of units.

**Key reports:**
- **_theavatar** (2018-07-11): "Just watched Master Bot buy a second blastforge instead of a steelforge in a set without Drake or G-Mech" (shadourow confirmed: "yup")
- **zera777** (2020-05-23): "Master Bot is too terrified to buy attackers, instead choosing to overtech." (amalloy's reply: "you're ahead only because master bot wasted $8 on two conduits")
- **masn6811** (2019-01-23): "when master bot opens DD DD DDA DDB, any player opener is going to feel like you made a mistake somehow" (describing MB getting both Animus AND Blastforge early when only one is needed)
- **masn6811** (2019-01-23): "or when you build 3 blastforges after savior and are like 'okay, i bought splitters, i guess i got too many forges' where the reality is that bot did a shit job of pressuring savior"

**Frequency:** ~8 reports
**Severity:** MEDIUM -- wasting 5-8 gold on unneeded tech is significant
**Fixability:** HEURISTIC LAYER -- the buy algorithm needs to recognize when tech buildings have no remaining useful purchases to enable.

### 4E. Resource Floating (MEDIUM SEVERITY)

MB sometimes accumulates large amounts of unspent resources, particularly in the late game when supply runs out.

**Key reports:**
- **zera777** (2020-03-25): "This Master Bot floated GGGGGBBBRRRRR [5G 3B 5R] for the privilege of buying Bombarder as its first attacker. `mDFOe-tJKWK`"
- **velizar_** (2020-02-26): "when engi is out of supply float all the gold (has 51 gold at the end of the game)" **Replay: `enK@3-JLgdD`**
- **drevoed** (2019-09-16): "Why the master bot holds 1 and exactly 1 drone here + floats 1 green?" (elyot replied: "When all roads lead to loss, master bot sometimes can't pick between different options because they don't have any meaningful difference in the outcome")

**Frequency:** ~6 reports
**Severity:** MEDIUM in early/mid game (floating significant resources = lost tempo), LOW in endgame (sometimes there is nothing to buy)
**Fixability:** HEURISTIC LAYER for early/mid game -- the buy algorithm should penalize plans that leave large amounts of resources unspent. Late-game floating when supply is exhausted is harder to fix without deeper planning.

### 4F. Gauss Charge Over-Purchase (LOW-MEDIUM SEVERITY)

MB buys Gauss Charges (prompt 1-damage, consumed on use) when the damage will be entirely absorbed, providing no value.

**Key reports:**
- **velizar_** (2020-04-17): "the bot buys gauss charges when they are certain to be absorbed, very cool."
- **p0lari** (2020-03-24): "why is master bot buying double gauss charges into my wall"
- **sano712** (2022-07-29): "I don't recall ever seeing the bot buy cluster. It loves gauss charge though"

**Severity:** LOW-MEDIUM -- wastes 2G per charge, but individually small
**Fixability:** HEURISTIC LAYER -- the buy algorithm should recognize when additional prompt attack won't exceed the opponent's defense threshold.

### 4G. Buying First Absorber into Absorb Denial (LOW SEVERITY)

MB buys expensive absorbers when the opponent has absorb denial (e.g., Urban Sentry's vigilant snipe can destroy the absorber before it gets value).

**Key report:**
- **aa01blue** (2024-03-24): "masterbot buying first absorber fibroid into my vigilant urban sentry :kekW:"

**Severity:** LOW -- specific interaction
**Fixability:** DEEP CHANGE -- requires understanding opponent threat composition

---

## 5. STRATEGIC / PLANNING Weaknesses

### 5A. No Pressure / Passive Play (HIGH SEVERITY)

The single most impactful strategic weakness. MB never applies offensive pressure, allowing opponents to build up massive economies unchallenged. This makes it poor practice for ladder play.

**Key reports:**
- **amalloy** (2019-01-23): "master bot never puts any pressure on against any strategy"
- **masn6811** (2019-01-23): "mhm i play a lot of masterbot and its honestly not good practice"
- **amalloy** (2019-01-23): "it's really easy to overvalue, for example, absorb denial against master bot, because he always builds absorb anyway"
- **masn6811** (2019-01-23): "or when you build 3 blastforges after savior... the reality is that bot did a shit job of pressuring savior"
- **masn6811** (2019-01-23): "i found the opposite with absorb denial a lot actually. often i dont use my absorb denial because bot makes no effort to protect his boreholes"
- **307th** (2018-01-30): "master bot is good at tactics but terrible at strategy, so it would be kind of hard to learn strategy by playing against master bot"

**Frequency:** 10+ explicit reports, frequently discussed as MB's core limitation
**Severity:** HIGH -- this is the fundamental strategic weakness. A bot that never pressures allows the opponent to play greedily with impunity. Players learn bad habits from MB (overvaluing economy, ignoring tempo).
**Fixability:** DEEP CHANGE -- pressure requires multi-turn planning (recognizing when opponent is greedy and punishing with rush). The neural net may eventually learn this from expert games.

### 5B. Cannot Handle Savior / High-Economy Games (MEDIUM SEVERITY)

MB struggles with Savior (delays game dramatically, allowing massive economy builds). It doesn't adjust its play to match the extended timeline.

**Key reports:**
- **masn6811** (2019-01-23): "bot did a shit job of pressuring savior"
- **shadourow** (2020-02-14, via context): "that also works by adding all the defence units, as master bot is really bad at really high econ"

**Severity:** MEDIUM
**Fixability:** DEEP CHANGE -- requires understanding game phase transitions

### 5C. Bot Never Gambits (MEDIUM SEVERITY)

MB never offers gambits (intentionally under-defending to gain tempo). Human players can predict this and play accordingly, knowing MB will always defend fully.

**Key reports:**
- **siepu** (2019-05-09): "Knowing that bot never gambits helps a lot"
- **amalloy** (2019-05-09): "master bot has a number of easily-exploitable flaws that you can predict ahead of time by making plays that are non-optimal against a good player"
- **awaclus** (2019-05-09, via context): "there are things that the Master Bot does that helps you beat it when you know it's going to do those things"

**Frequency:** ~5 reports
**Severity:** MEDIUM -- predictability is exploitable. Against human players, the threat of a gambit forces different defensive choices.
**Fixability:** DEEP CHANGE -- gambling requires risk assessment and opponent modeling, which is fundamentally beyond heuristic play.

### 5D. Extra Gold Not Used Well in Opening (LOW-MEDIUM SEVERITY)

When given extra starting gold (handicap games), MB doesn't leverage it effectively.

**Key reports:**
- **awaclus** (2018-04-05): "master bot doesn't know how to take full advantage of the extra gold in the early game, whereas adept bot still does something sensible when you skip your first turn"
- **spiritfryer** (2018-03-04): "when we gave Masterbot extra gold to start with, it didn't use it on the first few turns. Does it use an opening book?"

**Severity:** LOW-MEDIUM -- only affects handicap games
**Fixability:** Opening book / heuristic -- pre-computed responses for common gold advantages

### 5E. Defense Grid Rush / Suboptimal Rushes (LOW SEVERITY)

MB sometimes rushes Defense Grid (a defensive structure) when it should be rushing attackers, or executes rush strategies poorly.

**Key reports:**
- **gadget246** (2018-03-14): "'master bot is a very difficult opponent' -- master bot: *goes 2 engineers into a defense grid set* :OMEGALUL:"
- **shadourow** (2019-01-23): "Master Bot rushing Defense grid FeelsSafeMan" (masn6811: "not even the correct defense grid rush")

**Severity:** LOW -- comedic but infrequent
**Fixability:** Opening book fixes

### 5F. Premature Resign / Loss Detection Issues (LOW SEVERITY)

MB occasionally resigns in positions that aren't actually lost, or misidentifies the game state.

**Key reports:**
- **stacko** (2022-04-13): "`X1ggL-LYHKj` master bot surrenders on turn 8 when I have 1 attacker and haven't dealt any actual damage yet. (deadeye + venge shenanigans - they have no drones left)"
- **velizar_** (2020-09-21): "`9TaJh-ntrow` Here the bot never buys any attackers before resigning. Just absorb, then soak, then more soak."
- **amalloy** (2018-03-25): "masterbot just resigned an easy win because it forgot about clusterbolt"

**Frequency:** ~4 reports
**Severity:** LOW -- rare
**Fixability:** Requires better game-state evaluation

**Replay codes provided:** `X1ggL-LYHKj`, `9TaJh-ntrow`

---

## 6. SPECIFIC UNIT BLINDSPOTS

### 6A. Zemora (HIGH -- MB Cannot Use It)

MB fundamentally cannot play Zemora correctly. Zemora requires stockpiling green resources to fire a massive attack, which requires multi-turn planning. MB's greedy turn-by-turn evaluation doesn't support this.

**Key reports:**
- **axmos** (2019-01-03): "master bot doesnt understand how to use zemora afaik" (siepu confirmed: "^") / "almost every other time keeping green low / not building 8+ conduits is a good thing"
- **jamberine** (2020-02-14): "I don't think I've ever seen master bot successfully fire a zemora" / "if master bot buys zemora you've probably already won"
- **nvlx** (2020-02-14, via context): "i remember rigging all master bot achievements by adding at least zemora and mobile animus in the sets"
- **velizar_** (2019-12-10, via context): "Or a Zemora set" (listing sets where bot plays terribly)

**Frequency:** ~8 reports
**Severity:** HIGH in Zemora sets -- essentially a free win for the player
**Fixability:** DEEP CHANGE -- Zemora requires understanding "save resources for future big turn," antithetical to greedy optimization. A special-case heuristic (e.g., "if you have Zemora, stockpile green") could help but would be fragile.

### 6B. Antima Comet (HIGH -- MB Cannot Use It)

Antima Comet has a unique burst-damage mechanic that MB doesn't plan for. Similar to Zemora, it requires multi-turn resource planning.

**Key reports:**
- **.holyfire** (2023-01-30): Listed "Antima comet" as MB's #1 "terrible with" unit
- **velizar_** (2019-12-10, via context): "So why is the bot so bad when Antima is in the set" (iminabearsuit: "9/10 cases the bot has crashed, and it defaults to wacky bot (random moves)")
- **.bky_1556** (2020-08-24, via context): Suggests including Galvani + Antima + Chrono as a guaranteed win combo against MB

**Frequency:** ~6 reports
**Severity:** HIGH in Antima sets
**Fixability:** DEEP CHANGE -- multi-turn planning required. Also historically associated with bot crashes (wacky bot fallback).

### 6C. Cluster Bolt / Clustervenge (MEDIUM-HIGH)

MB struggles with Cluster Bolt (accumulates charges for burst damage) and Venge Cannon + Cluster combinations.

**Key reports:**
- **.holyfire** (2023-01-30): Listed "Clustervenge" as "terrible with"
- **amalloy** (2018-03-25): "masterbot just resigned an easy win because it forgot about clusterbolt"
- **sano712** (2022-07-29): "I don't recall ever seeing the bot buy cluster. It loves gauss charge though"
- **liquideggproduct** (2023-10-10): "I've seen MB buy Cluster Bolt" / "But it could behave differently when there are no attackers or drones"
- **lyra1712** (2022-07-29, via context): "does he ever buy cluster? im not even sure"

**Frequency:** ~6 reports
**Severity:** MEDIUM-HIGH -- cluster is common and MB's inability to use or defend against burst damage is a significant weakness
**Fixability:** DEEP CHANGE -- requires understanding charge accumulation and burst timing

### 6D. Tesla Coil (MEDIUM)

**Key report:**
- **.holyfire** (2023-01-30): Listed "Tesla Coil" as "terrible with"

**Severity:** MEDIUM -- Tesla Coil requires careful click timing
**Fixability:** HEURISTIC LAYER -- Tesla Coil's click ability could potentially be handled with a specialized heuristic

### 6E. Ossified Drone (LOW-MEDIUM -- MB Ignores It)

MB reportedly never buys Ossified Drone.

**Key report:**
- **.holyfire** (2023-01-30): "Ignores IIRC: Ossified Drone"

**Severity:** LOW-MEDIUM -- Ossified Drone is niche
**Fixability:** Unknown -- may be in the buy candidate list already, just scored low by the knapsack

### 6F. Infusion Grid (MEDIUM -- Rarely Bought)

MB almost never buys Infusion Grid (5GB, prompt 4HP blocker, click to gain 3G and destroy it).

**Key reports:**
- **lyra1712** (2019-02-16): "ive never seen master bot buy infusion grid ever i think"
- **ggmoyang** (2019-02-16, via context): "Why the AI don't buy infusion grid in this situation?"
- **reb46** (2022-07-29): "Saw the bot buy infusion grid for the first time ever and instantly click them on the turn after" (i.e., it immediately destroyed what it just bought)
- **.bky_1556** (2020-08-24, via context): Referenced "bot's lack of foresight with Infusion Grid"

**Frequency:** ~5 reports
**Severity:** MEDIUM -- Infusion Grid is a powerful flexible unit that MB ignores
**Fixability:** HEURISTIC LAYER -- the buy algorithm may undervalue prompt soak that can also be converted to gold. Its value is context-dependent (great when you need defense flexibility).

### 6G. Electrovore + Galvani Interaction (MEDIUM)

MB has "defensive gaffes" when both Galvani Drone and Electrovores are in play.

**Key reports:**
- **.bky_1556** (2020-08-24): "Fast sets would rely on various Master Bot defensive gaffes while evaluating situations with both a Galvani Drone and Electrovores."
- **.bky_1556** (2020-08-24, via context): "Personally, if I were trying for a streak, I'd use P2 Electrovore, Galvani Drone, Mobile Animus, Infusion Grid, Trinity Drone, +5 random."

**Severity:** MEDIUM -- specifically exploitable unit combination
**Fixability:** HEURISTIC LAYER -- likely related to Galvani valuation (already partially fixed)

### 6H. Bombarder Timing (LOW-MEDIUM)

MB buys Bombarder too early and floats massive resources to afford it.

**Key report:**
- **zera777** (2020-03-25): MB floated 5G+3B+5R to buy Bombarder as first attacker (`mDFOe-tJKWK`)

**Severity:** LOW-MEDIUM
**Fixability:** HEURISTIC LAYER -- the buy algorithm should prefer cheaper attackers when expensive ones require floating many resources

### 6I. Centurion/Defense Interaction (LOW)

MB sometimes enables opponent Centurion (big absorber) by buying a second Animus needlessly.

**Key report:**
- **masn6811** (2019-10-20): "you should see when the master bot defends and then buys a bolt allowing an exact breach on centurion"
- **masn6811** (2019-01-23): "or the bot buys second animus so you set up centurion and instead of buying lucina he just buys WTTD"

**Severity:** LOW
**Fixability:** DEEP CHANGE -- requires opponent modeling

---

## 7. OTHER QUIRKS

### 7A. Wacky Bot Fallback on Crash (MEDIUM)

When Master Bot crashes mid-game (typically due to certain unit combinations), the server falls back to "Wacky Bot" behavior (random moves). Players experience this as MB suddenly making completely random moves.

**Key reports:**
- **p0lari** (2018-02-26): "I believe wacky bot behaviour is the fallback when master bot crashes, and those crashes have happened more often recently"
- **allroc22** (2018-02-26): "Did someone accidentally replace Master Bot with Wacky Bot recently?" **Replay: `Zmsk5-WZsAz`**
- **iminabearsuit** (2019-12-10, via context): "9/10 cases the bot has crashed, and it defaults to wacky bot (random moves) ...the last 10% antima comet is in the set."
- **Deleted User** (2020-11-15): "Every time I play at turn 3 wacky bot always concedes"
- **mrguy888** (2020-11-15, via context): "phosphorescent iso caused the bug"

**Frequency:** ~10 reports
**Severity:** MEDIUM -- complete loss of AI behavior. Historically associated with Antima Comet and Phosphorescent Iso units.
**Fixability:** Already improved in our fork (more robust error handling), but crash scenarios with specific unit combinations may still exist.

### 7B. MB Rating Estimate: ~1400 Elo (Community Consensus)

The community generally estimates MB at around 1400-1500 Elo. Top players (~1800+) win 95-100% of the time.

**Key reports:**
- **ussgordoncaptain** (2018-01-01): "like master bot is a 1400 elo player"
- **elyot** (2020-04-20): "even getting 50% winrate against master bot takes most players many many hours of playing, could be 10-30 hours"
- **amalloy** (2022-07-16): "i was only in like the top 50, and i won about 95% of games against master bot"
- **sano712** (2022-07-16): "I'm not even close to a top player and I think I'd win at least 99 out of 100 games against master bot if I really tried"

### 7C. Exploitable Patterns Known to Community

The community has identified specific reliable strategies to beat MB:

- **Galvani + Antima + Chrono** = guaranteed win (amalloy via context)
- **Include Zemora or Mobile Animus** in set = guaranteed win (nvlx)
- **Include Electrovore + Galvani + Infusion Grid** = easy streak (.bky_1556)
- **Fast Tarsier line** beats MB in most sets (redrame)
- **Hannibul rush** exploits MB's tendency to overtech instead of defending (zera777)
- **Skip first turn** and still win in some sets (iminabearsuit, steel0229e)
- **10-Drone Hannibul rush** -- MB "too terrified to buy attackers" (zera777)
- **P2 Fastimus (fast Animus)** -- disgustingly easy (hyreon)
- **Venge Cluster with bait units** for the bot (lyra1712)

### 7D. BottyMcBotFace is 100+ Points Stronger Than MB

**elyot** (2018-04-10): "BottyMcBotFace is actually over 100 points stronger than Master Bot" -- this casual bot uses a huge opening book of strong rushes plus AB pruning. The opening book appears to be a significant strength advantage.

### 7E. Compute Time Has Diminishing Returns

**elyot** (2020-04-20): "it needs exponentially more time to go even 1 ply deeper in search, which improves its performance only marginally"

This confirms that the bottleneck is the heuristic evaluation quality, not search depth. Improving the evaluation function (via neural net or better heuristics) is more impactful than deeper search.

### 7F. MB Always Picks a Color Early

**vanilvanil** (2023-02-07): "master bot always picks a colour" -- MB always buys a tech building (Animus/Blastforge/Conduit) early, rather than sometimes staying on pure gold economy. This is predictable and sometimes suboptimal.

---

## Summary: Priority Rankings

### Tier 1 -- Highest Impact, Most Reported

| Issue | Section | Reports | Fixability |
|---|---|---|---|
| Stamina-blind defense | 2A | 15+ | Heuristic |
| Gauss Cannon rush addiction | 4A | 15+ | Deep change |
| No offensive pressure | 5A | 10+ | Deep change |
| Zemora incompetence | 6A | 8+ | Deep change |

### Tier 2 -- High Impact, Actionable

| Issue | Section | Reports | Fixability |
|---|---|---|---|
| Chill targeting | 3A | 5-8 | Heuristic (hard) |
| Mobile Animus / Rhino misuse | 4B | 8+ | Heuristic |
| Antima Comet incompetence | 6B | 6+ | Deep change |
| Overteching | 4D | 8 | Heuristic |
| Resource floating | 4E | 6 | Heuristic |
| Cluster Bolt blindspot | 6C | 6 | Deep change |

### Tier 3 -- Medium Impact, Worth Fixing

| Issue | Section | Reports | Fixability |
|---|---|---|---|
| Absorb on wrong unit class | 2B | 3-5 | Heuristic |
| Breach-avoidant play | 3B | 5 | Heuristic |
| Never gambits | 5C | 5 | Deep change |
| Infusion Grid ignored | 6F | 5 | Heuristic |
| Gauss Charge over-purchase | 4F | 3 | Heuristic |
| Electrovore + Galvani gaffes | 6G | 2 | Heuristic |

### Tier 4 -- Low Impact / Niche

| Issue | Section | Reports | Fixability |
|---|---|---|---|
| Grimbotch over-purchase | 4C | 1 | Heuristic |
| Bombarder timing | 6H | 1 | Heuristic |
| Ossified Drone ignored | 6E | 1 | Unknown |
| Tesla Coil incompetence | 6D | 1 | Heuristic |
| Always picks a color early | 7F | 1 | Opening book |
| Premature resign | 5F | 4 | Evaluation |

---

## Appendix: All Replay Codes Referenced

| Code | Issue | Reporter | Date |
|---|---|---|---|
| `Wiieo-DVcO6` | 0-stam Deadeye absorb over Wall (T13-15) | zakisan1 | 2019-01-02 |
| `MRleA-YHVhe` | 0-stam Bombarder absorb over E-Matrix | siepu | 2019-03-24 |
| `78xVR-XRYE0` | Galvani targeted over Drones during breach | .holyfire | 2025-03-07 |
| `izkDb-sy6uF` | Chill wasted on walls instead of barrier (T11) | alex319 | 2020-11-20 |
| `i9LTQ-x+f9s` | Gauss Cannon rush with Thorium Dynamo | velizar_ | 2019-07-19 |
| `BxFCp-Yz990` | Lost to Iso + Gauss + Thorium | velizar_ | 2019-07-19 |
| `QuXEb-4GM0t` | Gauss Cannon rush ignoring set | velizar_ | 2020-01-01 |
| `enK@3-JLgdD` | Thorium Gauss, 51g floated at end | velizar_ | 2020-02-26 |
| `0jBEo-Kbqz9` | (related Thorium Gauss game) | velizar_ | 2020-02-26 |
| `mDFOe-tJKWK` | Floated 5G+3B+5R to buy Bombarder | zera777 | 2020-03-25 |
| `X1ggL-LYHKj` | Premature resign T8, no damage dealt | stacko | 2022-04-13 |
| `9TaJh-ntrow` | Never bought attackers, just defended and resigned | velizar_ | 2020-09-21 |
| `m+Yhp-rSaTr` | Killed Wild Drones instead of breaching for Lucina | velizar_ | 2022-06-04 |
| `Zmsk5-WZsAz` | Wacky bot fallback (crash) | allroc22 | 2018-02-26 |
| `QHAH0-HoPdz` | (general MB weakness demo) | amalloy | 2018-06-30 |
| `JL6Y6-3VpKU` | MB weak vs Galvani variants | .bky_1556 | 2018-04-08 |
| `dc6f5-rWjui` | MB weak vs Galvani variants | .bky_1556 | 2018-04-08 |
| `20Y9x-VJozp` | (general odd MB game) | shadourow | 2019-07-26 |

---

## Appendix: Impact on Our Neural Net Training

Several community observations are directly relevant to our self-play training pipeline:

1. **Cost-based valuation is the root cause** of most issues (apooche, 2025-03-09). Our Will Score heuristic uses resource cost as a proxy for value. The neural net should learn unit-in-context values that diverge from cost (e.g., 0-stam Corpus worth ~0, fresh Galvani worth ~1G).

2. **Temporary vs. permanent attack distinction** (Rhino, Grimbotch, Gauss Charge) is critical and not captured by cost. Our feature vector includes lifespan/stamina, so the neural net can in principle learn this.

3. **Multi-turn planning** (Zemora, Antima, Cluster) is fundamentally beyond heuristic play. The neural net plus search should eventually handle these, as they require valuing future resource accumulation.

4. **Chill optimization** is computationally expensive but high-impact. Even a simple "freeze the absorber first" heuristic would be a massive improvement.

5. **The community explicitly asks for reporting channels** for bot issues (phin8459, 2019-09-02; zakisan1, 2019-01-02). Our improvements would be well-received.
