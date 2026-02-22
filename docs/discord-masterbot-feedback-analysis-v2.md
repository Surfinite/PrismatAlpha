# Discord Community Feedback Analysis: Master Bot Behavioral Issues (v2)

**Analysis date:** 2026-02-22
**v1 date:** 2026-02-21
**Extraction metadata:**
- v1 source: Haiku model extraction from strategy_advice channel only (425 messages)
- v2 source: Sonnet-4 model extraction across 6 channels, 379 total chunks
- Channels: alpha_player_lounge, prismata_chat, questions_and_help, ask_a_dev, unit_and_game_design, strategy_advice
- Total insights extracted: 3,461 (350 MB-specific, 33 bot-related non-MB)
- MB insight categories: MB_BUG_REPORT (41), MB_WEAKNESS (90+), MB_COMPARISON (32), MB_EXPLOIT_STRATEGY (49), MB_FEATURE_REQUEST (20)
- Replay codes referenced: 40+ across all sections

**Data source:** 2,095 Discord messages from the Prismata community (2016-2026)
**Top contributors:** amalloy (92), mrguy888 (87), velizar_ (86), masn6811 (73), awaclus (71), shadourow (68), zera777 (58), liadahlia (43), steel0229e (39), p0lari (38), .holyfire (multiple high-value reports), .bky_1556, apooche (early alpha player, deep game knowledge)

---

## 1. ALREADY FIXED Issues

These issues were reported by the community and have been addressed in our codebase.

### 1A. Borehole Patroller Overvaluation (Pixie cost included)

**Status:** FIXED

The bot values Borehole Patroller based on its full purchase cost (5GBB), but part of that cost pays for a Pixie token that is created alongside it. The Borehole's intrinsic value is significantly less than its sticker price.

**Key reports:**
- **apooche** (2025-03-09): "Master bot generally values units based on their cost. For example it overvalues borehole patrollers because it doesn't consider the fact that part of their cost was for a pixie."
- **p0lari** (2018-04-14): "the solution that involves getting 4 cryos and freezing xeno would not win if the bot soaked on a borehole instead of both shield barriers"
- **awaclus** (2018-06-19): "the main difference between sentry and borehole is that the latter comes with a Pixie"
- **liquideggproduct** (2025-08): observed MB absorbing on Borehole Patroller over Steelsplitter and Doomed Wall, with apooche confirming it is because Patroller costs more

**Frequency:** ~6 explicit reports, confirmed by v2 extraction
**Community diagnosis matches our fix:** Yes -- the community correctly identified that part of Borehole's cost was for the Pixie.

### 1B. Corpus Overvaluation (Husk cost included)

**Status:** FIXED

Similar to Borehole -- Corpus (6RR) creates a prompt Husk when purchased. The bot valued Corpus at full cost without subtracting the Husk's value, leading to absurd defense assignments (absorbing on 0-stamina Corpus over a Wall).

**Key reports:**
- **sano712** (2020-06-23): "it's 2020 and master bot still absorbs on 0-stam corpus over wall :ThinkTank:"
- **chlobes** (2019-12-27): "absorbing on corpus over wall is pretty much always bad, and the fact that it absorbs on 0 stam corpus implies that it absorbs on 1 or 2 stam corpus over wall (which is true)"
- **.holyfire** (2025-01-05): "Ironically, I'm pretty sure that even a fresh Corpus is worth less than a wall... So that doesn't make much sense either way."
- **glacialblades666** (2025-03-09): "it also sacrifices walls to absorb on an empty corpus"
- **masn6811** (2020-12-08): "the sac wall to save corpus and click it is obviously bad"
- **siepu** (2021-05-14): "it treats vore as costing 8 compared to 4 for engis"
- **awaclus** (2020-04-16): shared replay `Qcb29-urWUb` demonstrating bot absorbing on empty Bombarder and soaking on Matrix

**Frequency:** 10+ explicit reports spanning 2018-2025, one of the most-discussed issues
**Community diagnosis matches our fix:** Yes -- correctly identified as a cost-decomposition problem.

**Additional replay codes:** `Qcb29-urWUb`, `eUfkH-nBFhd`

### 1C. Galvani Drone Targeting During Breach

**Status:** FIXED

MB would target Galvani Drones during breach instead of more valuable units (Drones, Walls, etc.), because it valued Galvani based on purchase cost rather than practical in-play value. A Galvani Drone in play is worth very little (already used its energy).

**Key reports:**
- **.holyfire** (2025-03-07): "Masterbot's Galvanophobia is just weird. It's bad enough that it targets Galvani when it could have killed drones instead, which literally strictly dominates. But targeting Galvani instead of breaching is just... Wow." **Replay: `78xVR-XRYE0`**
- **.holyfire** (2025-03-07): "It's painfully nonsensical to kill Galvani instead of drone, or -- as in this game -- Two Galvani instead of wall and drone."
- **p0lari** (2018-03-11): "these gauss cannons seem pretty bad to me, and so does killing galvanis instead of engis"

**Frequency:** ~5 explicit reports, confirmed across multiple channels
**Community diagnosis matches our fix:** Yes -- Galvani's in-play value is nearly zero; targeting it over Drones/Walls is strictly dominated.

### 1D. Health/Stamina Not Considered in Breach Targeting

**Status:** FIXED

MB ignored remaining health and stamina when comparing breach targets. A 2-health Tantalum Ray would be targeted over a full-health Steelsplitter, even though the Steelsplitter was worth more to kill.

**Key reports:**
- **.holyfire** (2025-03-09): "TIL Master Bot Apollo will target 2-Health Tantalum Ray rather than Steelsplitter. In general, MB seems to never consider Health or Stamina when comparing between different units."
- **apooche** (2025-08): Explicitly confirmed that Q auto-breach mishandles damaged fragile units (Colossi at 1hp vs full-health Gauss Cannon example)

**Frequency:** ~3 explicit reports
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
- **chlobes** (2019-12-27): Confirmed MB absorbs on Corpus over Wall even at 1-2 stamina, not just 0
- **velizar_** (2020-04-16) via `Qcb29-urWUb`: Replay showing bot absorbing on empty Bombarder and soaking on Matrix
- **Chieftain-specific bug** -- silentslayers (2020-06-17): "When using the absorb command (Q absorb), the bot soaks damage onto Xae rather than absorbing on Chieftain, because Chieftain has more HP and does not fit the standard soak heuristic." Elyot confirmed the heuristics do not handle Chieftain correctly and added it to the bug list.
- **Tia Threnody absorb bug** -- .holyfire (2024-03-15): "Master Bot (3s) will buy Tia Threnody and attempt to 'absorb' on it while simultaneously soaking on Centurion." **Replay: `Z7nus-v@YI5`**
- **Plexo Cell over absorb** -- velizar_ (2021-12-25): MB uses Plexo Cell instead of absorbing damage. **Replay: `WIXwx-YsqV+`**

**Frequency:** 20+ explicit reports, discussed repeatedly from 2018-2026
**Severity:** HIGH -- this is a pure heuristic bug. A unit with 0 stamina remaining is about to die regardless; absorbing on it wastes the absorb entirely.
**Fixability:** HEURISTIC LAYER -- defense assignment needs to factor in remaining stamina. A 0-stamina unit should be treated as soak-only (about to die), never as an absorb target.

**Replay codes:** `Wiieo-DVcO6` (T13-15), `MRleA-YHVhe`, `Qcb29-urWUb`, `Z7nus-v@YI5`, `WIXwx-YsqV+`

### 2B. Absorbing on Wrong Unit Class (MEDIUM SEVERITY)

Even with non-zero stamina, MB sometimes absorbs on the wrong unit because it uses cost as a proxy for absorb value. A high-cost unit that does something other than defend (e.g., Bombarder with attack ability, Corpus with click ability) is not necessarily a better absorb target than a cheaper dedicated defender.

**Key reports:**
- **siepu** (2021-05-14): "it treats vore as costing 8 compared to 4 for engis"
- **apooche** (2025-03-09): Summary explaining the root cause -- "Master bot generally values units based on their cost."
- **amalloy** (2018-10-06): Q defense will sacrifice a Steelsplitter to keep a Wall alive -- the wrong priority in most situations
- **apooche** (2018-10-07): Q defense can lose 3 Forcefields over 2 Walls when Forcefields are more valuable defenders
- **apooche** (2018-10-07): Q defense can lose an Infusion and 2 Engineers instead of 2 Walls, giving up granular attack value
- **amalloy** (2018-10-06): Q defense incorrectly absorbs onto Odin instead of Xaetron -- back-lining on Xaetron is almost always correct
- **jamberine** (2018-10-06): Q defense will absorb onto Tia Threnody instead of Infusion Grid, which is incorrect

**Severity:** MEDIUM -- less impactful than 0-stam bug, but still costs absorb value
**Fixability:** HEURISTIC LAYER -- defense assignment should consider: (a) remaining stamina, (b) whether the unit has a click ability, (c) unit-specific roles (pure defenders vs. attackers that also soak).

**Architectural note (apooche, 2025-01):** "MB has approximately four fixed defense algorithms and applies MCTS only to choose among them. When all four algorithms are suboptimal for a given situation, MB cannot defend correctly." -- This is a fundamental architectural limit.

### 2C. Sacrificing Walls to Preserve Empty Corpus (LOW SEVERITY)

In some losing positions, MB will sacrifice a Wall (a permanent defender) to keep absorbing on an empty (0-stamina) Corpus.

**Key reports:**
- **glacialblades666** (2025-03-09): "it also sacrifices walls to absorb on an empty corpus"
- **masn6811** (2020-12-08) via `eUfkH-nBFhd`: Confirmed replay showing MB sac'ing Wall to save Corpus and clicking it

**Severity:** LOW -- usually occurs in already-lost positions
**Fixability:** HEURISTIC LAYER -- this is a consequence of 2A (stamina blindness)

### 2D. Q-Defense (Auto-Defend) Algorithm Bugs (MEDIUM SEVERITY)

The game's auto-defend Q algorithm has multiple known failure modes that MB also falls prey to. These were comprehensively documented in 2018 by apooche and amalloy.

**Key reports:**
- **amalloy** (2018-06-18): MB misdefends with Xaetron + lifespan-1 Doomed Wall -- prioritizes Xaetron as absorber, then sacrifices Doomed Wall first, resulting in unnecessary damage to Xaetron
- **apooche** (2018-06-18): "The Q (auto-defend) button is known to mishandle defense when a Xaetron is present" -- recommend never using Q with Xaetron on board
- **.holyfire** (2025-08-10) via `5VnVG-XG@fB`: "Q-defense incorrectly soaks on the Steelsplitter instead of the Wall" with Wall, Forcefield, two Rhinos (prompt) and a Steelsplitter plus Infusion Grid
- **sano712** (2023-04-21): "Q defense incorrectly prefers to soak Perforators over Steelsplitters"
- **flakmaniak** (2020-05-07): MB overblockes by 1 in Vai Mauronax sets, not accounting for freeze ability

**Severity:** MEDIUM -- affects any position requiring precise defense assignment
**Fixability:** HEURISTIC LAYER -- requires more sophisticated unit-role recognition

**Replay codes:** `5VnVG-XG@fB`

### 2E. Cauterizer Click Blindspot (LOW SEVERITY) - NEW IN V2

MB systematically ignores Cauterizer clicks, underdefending by 2 every turn and sacrificing an Arka unit as a consequence.

**Key report:**
- **liadahlia** (2018-03-10): "Master Bot repeatedly ignores Cauterizer clicks, underdefending by 2 each time and sacrificing an Arka unit." **Replay: `psDxO-FGMrE`**

**Severity:** LOW -- Cauterizer is an uncommon unit
**Fixability:** HEURISTIC LAYER -- likely a missing case in the click-ability handler

**Replay codes:** `psDxO-FGMrE`

---

## 3. BREACH / TARGETING Issues

### 3A. Chill Targeting is Extremely Poor (HIGH SEVERITY)

MB wastes chill (freeze) shots on units where freezing has no impact on the defense outcome, instead of freezing high-value absorbers.

**Key reports:**
- **alex319** (2020-11-20): "The master bot seems very poor at using chill. `izkDb-sy6uF` On turn 11 the master bot wastes 6 cryo ray shots chilling walls which don't even affect the outcome of the block, when it could have chilled the barrier instead." (shadourow confirmed: "Yes indeed")
- **.holyfire** (2023-01-30): Listed "Chill in general" as one of MB's worst areas
- **stacko** (2019-12-31): "Breaching with 0 attack by freezing: the Master Bot breach" -- describing MB freezing all defenders but having no attackers to capitalize
- **sonoja** (2018-10): "bot is very bad at handling freeze mechanics, appearing to always use freeze even when there is no exploit opportunity or breach situation"
- **velizar_** (2020-12): Noted that a lifespan-based Cryo Ray redesign was partially motivated by mitigating bot misuse of freeze targeting

**Frequency:** ~8 explicit reports across multiple channels
**Severity:** HIGH -- chill is one of the most strategically important mechanics. MB wasting chill on irrelevant targets is a major weakness.
**Fixability:** HEURISTIC LAYER (hard) -- chill targeting requires simulating the defense assignment after freezing. The optimal chill target is the one that maximizes breach damage by denying the most absorb/soak.

**Replay codes:** `izkDb-sy6uF` (turn 11)

### 3B. Breach-Avoidant Play: Kills Frontline/Economy Instead of Breaching (MEDIUM SEVERITY)

MB sometimes kills frontline units or economy (Wild Drones, Drones) when breaching would be strictly better.

**Key reports:**
- **velizar_** (2022-06-04): "`m+Yhp-rSaTr` Last turn: Bot chooses to kill two of my wild drones rather than to breach me for Lucina + 1 Tarsier"
- **vargus2254870** (2019-10-20): "bot holds lifespan 1 grimbotch instead of breaching"
- **zera777** (2019-10-20): "Even if breaching is not always correct, it's correct often enough that I'd program the bot to always do it."
- **cronos** (2020-02-15): MB treats Wild Drone as a blocker rather than recognizing it as a snipe target

**Frequency:** ~6 reports
**Severity:** MEDIUM
**Fixability:** HEURISTIC LAYER

**Replay codes:** `m+Yhp-rSaTr`

### 3C. Apollo Snipe Targeting (LOW SEVERITY)

MB makes suboptimal snipe target choices.

**Key reports:**
- **.holyfire** (2025-03-09): "Master Bot Apollo will target 2-Health Tantalum Ray rather than Steelsplitter" -- targeting by cost rather than remaining value
- **liquideggproduct** (2022-06-04): "Master bot sniped a conduit with Kinetic to stop Zemora from firing" -- amalloy responded skeptically that it was accidental
- **velizar_** (2020-04-15): "MB made multiple seemingly random Apollo snipes, including sniping a Tarsier when the player had Steelsplitters available as higher-priority targets"
- **velizar_** (2020-04-03) via `1o0XS-SbPpw`: MB immediately used Kinetic the turn after buying it to snipe a Conduit rather than saving it for more impact

**Severity:** LOW-MEDIUM
**Fixability:** Mostly addressed by health/stamina fix (1D)

**Replay codes:** `1o0XS-SbPpw`

### 3D. Asteri Useless Activation - NEW IN V2

MB clicks Asteri even when there is no possibility the barrier ability will affect the game state.

**Key report:**
- **.holyfire** (2025-01-14): "Master Bot will click Asteri even when there is no possibility that the barrier ability will have any effect on the game state."

**Severity:** LOW -- wastes a click; Asteri is uncommon
**Fixability:** HEURISTIC LAYER -- needs a pre-check for whether the barrier has any viable target

---

## 4. BUY / VALUATION Issues

### 4A. Gauss Cannon Rush Addiction (HIGH SEVERITY)

The single most-discussed strategic weakness. MB defaults to Gauss Cannon rushes far too often, especially in Thorium Dynamo sets. It ignores superior random set units in favor of base-set Gauss Cannons + Forcefields, resulting in trivially beatable play.

**Key reports:**
- **velizar_** (2019-07-19): "Typical game against master bot: getting a complex but intriguing set, then master bot rushes me with gauss cannons and defends with force fields, loses trivially to base set."
- **stacko** (2019-07-19): "Master bot always seems to think Thorium Dynamo = rush Gauss Cannons"
- **velizar_** (2020-01-01): "Master bot: gauss cannon rush `QuXEb-4GM0t`"
- **velizar_** (2020-02-26): "Bot's strategy: Thorium Gauss breach-proof, when gauss is out of supply engi/drone/forcefield, when engi is out of supply float all the gold (has 51 gold at the end of the game)" **Replay: `enK@3-JLgdD`**
- **velizar_** (2019-07-19): "AI goes dynamo gauss with walls: `i9LTQ-x+f9s`" / "Here I lose to Iso + Gauss + Thorium `BxFCp-Yz990`"
- **velizar_** (2019-07): Replay `CtRG2-BqL4o` -- MB ignored Arka entirely and still rushed Fabricator + Gauss
- **stacko** (2019-07-19): Confirmed: "Master bot always seems to think Thorium Dynamo = rush Gauss Cannons"

**Frequency:** 15+ reports across multiple channels
**Severity:** HIGH -- the most exploitable pattern. Experienced players know MB will go Gauss rush and can counter it trivially.
**Fixability:** DEEP CHANGE -- fundamental issue with GreedyKnapsack evaluating units individually without considering game context.

**Replay codes:** `i9LTQ-x+f9s`, `BxFCp-Yz990`, `QuXEb-4GM0t`, `enK@3-JLgdD`, `0jBEo-Kbqz9`, `CtRG2-BqL4o`

### 4B. Mobile Animus / Rhino Misuse (MEDIUM SEVERITY)

MB buys Mobile Animus far too eagerly and too early, resulting in too many Rhinos and not enough permanent attack. The community documented that MB famously bought 9-10 Mobile Animuses in a single game (confirmed by developer elyot, who added a purchase limit that was later found to be overridden or ignored).

**Key reports:**
- **velizar_** (2020-02-11): "I love it when the bot buys out all the mobile animuses and turns them into rhinos while wasting the red / it's turn 10 and it bought 9 mobile animuses so far"
- **zera777** (2020-02-11): "Master Bot does suck with Mobile Animus. And also Rhinos. Sometimes MB buys 2 Tarsiers, then 10 Rhinos, then loses because it has almost no permanent attack. The goal of Rhino is to buy it as late as possible while still getting both attacks with it before soaking."
- **amalloy** (2018-05-01) via `VNw+z-CskPt`: Reported extreme bot misbehavior -- MB purchased all 10 available Mobile Animuses by turn 9, spending only 2 red resources total. Elyot confirmed.
- **amalloy** (2018-06-28) via `qJ0Jm-6@Sfb`: Bot (MoMoney) bought 9 Mobile Animuses, clicked them all, spent only 2 red total across entire game. Elyot confirmed buy limit was not working as intended.
- **vanitascabal6962** (2018-05-12) via `qivv4-6CAIG`: After fix attempt, bot may instead be buying and immediately clicking them

**Frequency:** ~10 reports + developer involvement
**Severity:** MEDIUM -- affects all games with Mobile Animus in the set
**Fixability:** HEURISTIC LAYER (tricky) -- Rhino timing requires understanding that temporary attack should be bought late for maximum value.

**Replay codes:** `VNw+z-CskPt`, `qJ0Jm-6@Sfb`, `qivv4-6CAIG`

### 4C. Grimbotch / Lifespan Unit Misuse (MEDIUM SEVERITY) - EXPANDED IN V2

MB buys lifespan units (Grimbotch, Rhino, Gauss Charge) but then fails to use them correctly, either holding them past their expiry window or treating them as permanent attackers.

**Key reports:**
- **flakmaniak** (2020-04-27): "Master Bot buys way too many Grimbotches and not enough Tarsiers."
- **vargus2254870** (2019-10-20): "bot holds lifespan 1 grimbotch instead of breaching"
- **amalloy** (2018-11-21): "MB recognizes that having attack is better than not, so it buys Grimbotches, but then fails to click them against the opponent's defense grid because it cannot search deep enough ahead to see their value, causing it to simply hold them unused."
- **amalloy** (2018-11-21): Confirmed zera's hypothesis: MB treats Grimbotch like a Tarsier due to limited lookahead depth. "It does not search very many turns ahead."
- **masn6811** (2019-10-20): "you should see when the master bot defends and then buys a bolt allowing an exact breach on centurion"

**Severity:** MEDIUM -- affects all lifespan unit sets
**Fixability:** DEEP CHANGE -- requires understanding timing of when to use lifespan units vs. permanent units. Shallow search (~2 turns ahead) cannot see value of holding Grimbotch for a later breach.

### 4D. Overteching / Wasting Tech Resources (MEDIUM SEVERITY)

MB sometimes buys tech buildings it doesn't need, wasting resources on infrastructure instead of units. V2 extraction significantly expanded this finding.

**Key reports:**
- **_theavatar** (2018-07): "Just watched Master Bot buy a second blastforge instead of a steelforge in a set without Drake or G-Mech"
- **zera777** (2020-05-23): "Master Bot is too terrified to buy attackers, instead choosing to overtech." (amalloy: "you're ahead only because master bot wasted $8 on two conduits")
- **masn6811** (2019-01-23): "when master bot opens DD DD DDA DDB, any player opener is going to feel like you made a mistake somehow" (describing MB getting both Animus AND Blastforge early when only one is needed)
- **velizar_** (2020-04-01): MB bought double Blastforge for Doomed Mech, double Animus for Lucina, Flame Animus, and Conduit all at once -- "doesn't prune redundant tech well"
- **flakmaniak** (2020-04-19): MB buys double Blastforge early but waits until turn 10 to buy Centurion, wasting blue in the interim -- confirmed by awaclus
- **amalloy** (2019-01-23): Invisible Rhino rendering bug observed (browser version) while MB was overteching

**Frequency:** ~10 reports
**Severity:** MEDIUM -- wasting 5-8 gold on unneeded tech is significant
**Fixability:** HEURISTIC LAYER -- buy algorithm needs to recognize when tech buildings have no remaining useful purchases to enable.

### 4E. Resource Floating (MEDIUM SEVERITY)

MB sometimes accumulates large amounts of unspent resources, particularly in the late game when supply runs out. V2 extraction added more specific examples.

**Key reports:**
- **zera777** (2020-03-25) via `mDFOe-tJKWK`: "This Master Bot floated GGGGGBBBRRRRR [5G 3B 5R] for the privilege of buying Bombarder as its first attacker."
- **velizar_** (2020-02-26): "when engi is out of supply float all the gold (has 51 gold at the end of the game)" **Replay: `enK@3-JLgdD`**
- **awaclus** (2018-06-27): Observed a bot (DrivenUpTheWall) pass its turn while floating 21 gold -- the most expensive unit costs 20 gold
- **drevoed** (2019-09-16): "Why the master bot holds 1 and exactly 1 drone here + floats 1 green?" (elyot replied: "When all roads lead to loss, master bot sometimes can't pick between different options")
- **zera777** (2020-03-24): MB is "limited to evaluating positions roughly 2 turns ahead" -- sometimes buys units that would have been useful earlier, "effectively thinking -1 turns ahead"

**Frequency:** ~8 reports
**Severity:** MEDIUM in early/mid game, LOW in endgame
**Fixability:** HEURISTIC LAYER for early/mid game -- buy algorithm should penalize plans that leave large resources unspent.

### 4F. Gauss Charge Over-Purchase (LOW-MEDIUM SEVERITY)

MB buys Gauss Charges (prompt 1-damage, consumed on use) when the damage will be entirely absorbed, providing no value.

**Key reports:**
- **velizar_** (2020-04-17): "the bot buys gauss charges when they are certain to be absorbed, very cool."
- **p0lari** (2020-03-24): "why is master bot buying double gauss charges into my wall"
- **sano712** (2022-07-29): "I don't recall ever seeing the bot buy cluster. It loves gauss charge though"
- **velizar_** (2020-04-29): MB bought 2 Gauss Charges against an already-built Urban Sentry -- community confirmed bot may not look far enough ahead to see the absorb

**Severity:** LOW-MEDIUM -- wastes 2G per charge, but individually small
**Fixability:** HEURISTIC LAYER -- buy algorithm should recognize when additional prompt attack won't exceed the opponent's defense threshold.

### 4G. Vivid Drone Misuse -- NEW IN V2

MB buys Vivid Drone after Savior comes online, apparently because the drone supply is exhausted and it still wants economy -- but Vivid Drone actually reduces net gold income (costs 2G + 2 energy to produce -1 gold per turn net).

**Key report:**
- **_theavatar** (2018-08-13): Observed MB buying Vivid Drones immediately after Savior came online, with community discussion of why this is wrong
- **amalloy** (2018-04-30): In Arms Race sets, MB "predictably buys multiple Vivid Drones in consecutive turns, making its behavior in those sets highly readable and exploitable"

**Severity:** LOW-MEDIUM -- Vivid Drone is a niche unit but the error pattern reveals a fundamental inability to evaluate negative-income economy units
**Fixability:** HEURISTIC LAYER -- needs to recognize that Vivid Drone has negative net gold income in most situations

### 4H. Doomed Drone Misuse -- NEW IN V2

MB does not hold Doomed Drones on 1 lifespan for defensive purposes, instead building Forcefields when holding a Doomed Drone would be more efficient.

**Key reports:**
- **flakmaniak** (2020-04-20): "Master Bot plays poorly with Doomed Drone: it does not hold Doomed Drones on 1 lifespan for defensive purposes nearly enough, and will instead build Forcefields." Confirmed by wilson0862.

**Severity:** LOW-MEDIUM
**Fixability:** HEURISTIC LAYER -- the lifespan-1 defensive holding heuristic is one of the top-requested improvements from community (consensus, 2020-04)

### 4I. Ebb Turbine Drone Loop -- NEW IN V2

MB buys 4 Ebb Turbines and clicks them all every turn to churn through its entire drone supply, then rebuys the drones -- a deeply inefficient loop.

**Key report:**
- **amalloy** (2018-06-16): "Master Bot plays very poorly with Ebb Turbine, buying 4 Ebb Turbines and clicking them all every turn to churn through its entire drone supply, then rebuying the drones."
- **namington** (2018-06-16): "Master Bot generally struggles with knowing when to stop buying drones and start buying attack units. The Ebb Turbine case is an extension of this broader weakness."

**Severity:** MEDIUM -- when Ebb Turbine is in the set, MB effectively burns its economy
**Fixability:** HEURISTIC LAYER -- needs economic transition detection

### 4J. Buying First Absorber into Absorb Denial (LOW SEVERITY)

MB buys expensive absorbers when the opponent has absorb denial.

**Key report:**
- **aa01blue** (2024-03-24): "masterbot buying first absorber fibroid into my vigilant urban sentry :kekW:"

**Severity:** LOW -- specific interaction
**Fixability:** DEEP CHANGE -- requires understanding opponent threat composition

### 4K. BSO (Base Set Only) Line Weakness -- NEW IN V2

MB does not know BSO opening theory at all. It appears to natural Conduit, which loses to almost every correctly-played line.

**Key reports:**
- **namington** (2018-06-07): "Master Bot does not know base set only (BSO) lines at all; it appears to nat conduit, which always loses except against a Master Bot blastforge opening."
- **extratricky** (2018-06-07): Tested a BSO game; MB made the move "WDD float 4GGG on turn 8" -- buying a Wall then floating 4 gold with no productive use
- **amalloy** (2019-01-23): Described MB's BSO behavior as predictable and suboptimal

**Severity:** MEDIUM -- BSO is a common game mode
**Fixability:** Opening book addition

---

## 5. STRATEGIC / PLANNING Weaknesses

### 5A. No Pressure / Passive Play (HIGH SEVERITY)

The single most impactful strategic weakness. MB never applies offensive pressure, allowing opponents to build up massive economies unchallenged.

**Key reports:**
- **amalloy** (2019-01-23): "master bot never puts any pressure on against any strategy"
- **masn6811** (2019-01-23): "mhm i play a lot of masterbot and its honestly not good practice"
- **307th** (2018-01-30): "master bot is good at tactics but terrible at strategy, so it would be kind of hard to learn strategy by playing against master bot"
- **masn6811** (2020-04-21): "MB only uses Q defense and never accepts non-obvious gambits. It assumes the human player will also Q-defend, making it exploitable by sacrificial attacks that a human would accept."
- **masn6811** (2020-04-21): "MB does not understand the concept of denying absorb: it will not use attack-costing units, click Thermite Core, or activate Auric Impulse specifically to deny an opponent's absorb opportunity. It also does not deny granularity."

**Frequency:** 15+ explicit reports across all channels
**Severity:** HIGH -- this is the fundamental strategic weakness. Players learn bad habits from MB (overvaluing economy, ignoring tempo).
**Fixability:** DEEP CHANGE -- pressure requires multi-turn planning.

### 5B. Cannot Handle Savior / High-Economy Games (MEDIUM SEVERITY)

MB struggles with Savior (delays game dramatically, allowing massive economy builds). It doesn't adjust its play to match the extended timeline.

**Key reports:**
- **masn6811** (2019-01-23): "bot did a shit job of pressuring savior"
- **apooche** (2018-08-13): "Master Bot has no coherent strategy for Savior and makes unintelligible plays whenever the unit is in the set. It cannot handle Savior's build-time correctly, failing to recognize the unit is on the board while it has build time remaining."
- **kristian1103** (2018-08-13): Root cause is that "MB doesn't recognize units on the board during build time" -- a general architectural limitation
- **.holyfire** (2025-10-05) via `scmG1-OcNum`: "MB resigned two turns before a player's Savior even finished construction, suggesting MB incorrectly over-weights the threat of Savior before it becomes active."
- **amalloy** (2018-06-18) via `65Qom-0yv6g`: MB nearly forced a draw in a Savior mirror but threw it by killing the opponent's last Savior instead of their last Drone

**Severity:** MEDIUM-HIGH -- Savior is a common set unit
**Fixability:** DEEP CHANGE -- requires understanding game phase transitions and build-time unit anticipation

**Replay codes:** `scmG1-OcNum`, `65Qom-0yv6g`

### 5C. Bot Never Gambits (MEDIUM SEVERITY)

MB never offers gambits (intentionally under-defending to gain tempo). Human players can predict this and play accordingly.

**Key reports:**
- **siepu** (2019-05-09): "Knowing that bot never gambits helps a lot"
- **amalloy** (2019-05-09): "master bot has a number of easily-exploitable flaws that you can predict ahead of time"
- **masn6811** (2020-04-21): "MB offers gambit attacks that require accepting a Rhino-onto-Wall or Wall-onto-Rhino sacrifice; MB will always keep its defensive units rather than accept such gambits, even when accepting would enable a breach of the opponent's Drone Grid."

**Frequency:** ~7 reports
**Severity:** MEDIUM
**Fixability:** DEEP CHANGE

### 5D. Shallow Lookahead -- New Summary in V2

A cross-cutting architectural weakness underlying many issues above.

**Key reports:**
- **zera777** (2020-03-24): "Master Bot is limited to evaluating positions roughly 2 turns ahead; it occasionally buys units that would have been more useful earlier, effectively thinking '-1 turns ahead'."
- **amalloy** (2018-11-21): MB treats Grimbotch like a Tarsier because it cannot see the value of holding it for a later breach
- **.jrkirby** (2018-06-16): "When it makes a mistake on a given set, it repeats that mistake every single time due to its deterministic nature."
- **elyot** (2020-04-20): "it needs exponentially more time to go even 1 ply deeper in search, which improves its performance only marginally" -- the bottleneck is heuristic evaluation quality, not search depth

**Severity:** HIGH -- underlies Zemora, Antima, Cluster Bolt, lifespan unit issues, and more
**Fixability:** DEEP CHANGE -- neural net evaluation is the correct fix

### 5E. Extra Gold Not Used Well in Opening (LOW-MEDIUM SEVERITY)

When given extra starting gold (handicap games), MB doesn't leverage it effectively.

**Key reports:**
- **awaclus** (2018-04-05): "master bot doesn't know how to take full advantage of the extra gold in the early game, whereas adept bot still does something sensible when you skip your first turn"
- **spiritfryer** (2018-03-04): "when we gave Masterbot extra gold to start with, it didn't use it on the first few turns. Does it use an opening book?"

**Severity:** LOW-MEDIUM -- only affects handicap games
**Fixability:** Opening book / heuristic

### 5F. Defense Grid Rush / Suboptimal Rushes (LOW SEVERITY)

MB sometimes rushes Defense Grid (a defensive structure) when it should be rushing attackers.

**Key reports:**
- **gadget246** (2018-03-14): "master bot is a very difficult opponent -- master bot: *goes 2 engineers into a defense grid set*"
- **shadourow** (2019-01-23): "Master Bot rushing Defense grid FeelsSafeMan" (masn6811: "not even the correct defense grid rush")

**Severity:** LOW -- comedic but infrequent
**Fixability:** Opening book fixes

### 5G. Premature Resign / Loss Detection Issues (LOW-MEDIUM SEVERITY)

MB occasionally resigns in positions that aren't actually lost.

**Key reports:**
- **stacko** (2022-04-13) via `X1ggL-LYHKj`: "master bot surrenders on turn 8 when I have 1 attacker and haven't dealt any actual damage yet."
- **velizar_** (2020-09-21) via `9TaJh-ntrow`: "Here the bot never buys any attackers before resigning. Just absorb, then soak, then more soak."
- **amalloy** (2018-03-25): "masterbot just resigned an easy win because it forgot about clusterbolt"
- **velizar_** (2020-09-14) via `LIIfR-GD6sF`: MB resigned despite opponent having only Clickers (very low damage units)
- **.holyfire** (2025-10-05) via `scmG1-OcNum`: MB resigned 2 turns before opponent's Savior even finished construction
- **.holyfire** (2026-01-20) via `ZxdlK-@ZTeE`: MB lost a game that would otherwise have been a draw because it had a charge remaining on its Venge Cannon -- mismanagement of Venge Cannon charges in close endgame
- **amalloy** (2020-09-14): Documented that MB's resignation logic triggers when enemy score is at least 1.3x the bot's score (total net worth of units on board), where "score" doesn't account for lifespan, under-construction, or future value

**Frequency:** ~8 reports
**Severity:** LOW-MEDIUM
**Fixability:** Requires better game-state evaluation (neural net should improve this)

**Replay codes:** `X1ggL-LYHKj`, `9TaJh-ntrow`, `LIIfR-GD6sF`, `scmG1-OcNum`, `ZxdlK-@ZTeE`

### 5H. Spend-All-Flexible-Attack on Engineers (LOW SEVERITY) -- NEW IN V2

MB always spends all of its flexible attack as long as doing so kills at least one Engineer, even if that means wasting many attackers (e.g., blowing 10 Pixies to kill one Engineer).

**Key report:**
- **amalloy** (2019-05): "Players can exploit this by holding back a unit like Chieftain and absorbing on Wall, baiting the bot into inefficient attacks."

**Severity:** LOW -- niche but exploitable
**Fixability:** HEURISTIC LAYER -- needs efficiency threshold before committing flexible attack

---

## 6. SPECIFIC UNIT BLINDSPOTS

### 6A. Zemora Voidbringer (HIGH -- MB Cannot Use It)

MB fundamentally cannot play Zemora correctly. Zemora requires stockpiling green resources to fire a massive attack, which requires multi-turn planning. MB's greedy turn-by-turn evaluation doesn't support this.

**Key reports:**
- **axmos** (2019-01-03): "master bot doesnt understand how to use zemora afaik"
- **jamberine** (2020-02-14): "I don't think I've ever seen master bot successfully fire a zemora / if master bot buys zemora you've probably already won"
- **nvlx** (2020-02-14): "i remember rigging all master bot achievements by adding at least zemora and mobile animus in the sets"
- **jamberine** (2020-02-14): MB doesn't understand that Zemora requires Gaussite -- it ignores opponent Conduits and targets Venge Cannons instead
- **velizar_** (2020-02-26): MB had a narrow winning line on turn 9 requiring it to destroy Conduits; it targeted Venge Cannons instead and lost
- **velizar_** (2020-03-24): MB "assumes Zemora always fires" when evaluating positions, causing premature resignation even in defensible positions

**Frequency:** ~10 reports across multiple channels
**Severity:** HIGH in Zemora sets -- essentially a free win for the player
**Fixability:** DEEP CHANGE -- requires understanding "save resources for future big turn"

### 6B. Antima Comet (HIGH -- MB Cannot Use It)

Antima Comet has a unique burst-damage mechanic that MB doesn't plan for. Similar to Zemora, it requires multi-turn resource planning. Historically associated with bot crashes.

**Key reports:**
- **.holyfire** (2023-01-30): Listed "Antima comet" as MB's #1 "terrible with" unit
- **iminabearsuit** (2019-12-10): "9/10 cases the bot has crashed, and it defaults to wacky bot (random moves) ...the last 10% antima comet is in the set."

**Frequency:** ~6 reports
**Severity:** HIGH in Antima sets
**Fixability:** DEEP CHANGE -- multi-turn planning required. Also historically associated with bot crashes.

### 6C. Cluster Bolt / Clustervenge (MEDIUM-HIGH)

MB struggles with Cluster Bolt (accumulates charges for burst damage) and Venge Cannon + Cluster combinations. Community has weaponized this against MB.

**Key reports:**
- **.holyfire** (2023-01-30): Listed "Clustervenge" as "terrible with"
- **amalloy** (2018-03-25): "masterbot just resigned an easy win because it forgot about clusterbolt"
- **sano712** (2022-07-29): "I don't recall ever seeing the bot buy cluster. It loves gauss charge though"
- **lyra1712** (2020-08): Galvani Drone + Venge Cannon + Cluster Bolt is described as the easiest known way to beat MB; confirmed strategy `r8Iip-iDQp3`
- **lyra1712** (2022-07-29) via `pRZrm-4XbNx`: Venge Cannon + Cluster Bolt + Galvani Drone rush + bait units = reliable achievement strategy

**Frequency:** ~8 reports
**Severity:** MEDIUM-HIGH
**Fixability:** DEEP CHANGE -- requires understanding charge accumulation and burst timing

**Replay codes:** `r8Iip-iDQp3`, `pRZrm-4XbNx`

### 6D. Tesla Coil (MEDIUM)

**Key report:**
- **.holyfire** (2023-01-30): Listed "Tesla Coil" as "terrible with"

**Severity:** MEDIUM -- Tesla Coil requires careful click timing
**Fixability:** HEURISTIC LAYER

### 6E. Ossified Drone (LOW-MEDIUM -- MB Ignores It)

MB reportedly never buys Ossified Drone.

**Key report:**
- **.holyfire** (2023-01-30): "Ignores IIRC: Ossified Drone"

**Severity:** LOW-MEDIUM
**Fixability:** Unknown -- may be in the buy candidate list already, just scored low

### 6F. Infusion Grid (MEDIUM -- Rarely Bought, Immediately Clicked)

MB almost never buys Infusion Grid, and when it does, immediately destroys what it bought.

**Key reports:**
- **lyra1712** (2019-02-16): "ive never seen master bot buy infusion grid ever i think"
- **reb46** (2022-07-29): "Saw the bot buy infusion grid for the first time ever and instantly click them on the turn after" (immediately destroyed what it just bought)
- **velizar_** (2022-04-29): "Master Bot needs to learn to properly use Infusion Grid"
- **flakmaniak** (2020-04): Identified Infusion Grid as one of the top 4 improvements needed for MB (alongside Doomed Drone lifespan, absorb denial, freeze units)

**Frequency:** ~6 reports
**Severity:** MEDIUM
**Fixability:** HEURISTIC LAYER -- the buy algorithm may undervalue prompt soak that can also be converted to gold.

### 6G. Electrovore + Galvani Interaction (MEDIUM)

MB has "defensive gaffes" when both Galvani Drone and Electrovores are in play.

**Key reports:**
- **.bky_1556** (2020-08-24): "Fast sets would rely on various Master Bot defensive gaffes while evaluating situations with both a Galvani Drone and Electrovores."
- **crash_overlord** (2018-02): "Master Bot plays poorly against Electrovore and against tier-2 blue opening strategies."

**Severity:** MEDIUM -- specifically exploitable unit combination
**Fixability:** HEURISTIC LAYER -- likely related to Galvani valuation (already partially fixed)

### 6H. Bombarder Timing (LOW-MEDIUM)

MB buys Bombarder too early and floats massive resources to afford it.

**Key report:**
- **zera777** (2020-03-25): MB floated 5G+3B+5R to buy Bombarder as first attacker (`mDFOe-tJKWK`)

**Severity:** LOW-MEDIUM
**Fixability:** HEURISTIC LAYER -- the buy algorithm should prefer cheaper attackers when expensive ones require floating many resources

**Replay codes:** `mDFOe-tJKWK`

### 6I. Centurion / Defense Interaction (LOW)

MB sometimes enables opponent Centurion by buying a second Animus needlessly, or buys Cluster Bolt enabling exact breach on its own Centurion.

**Key reports:**
- **masn6811** (2019-10-20): "you should see when the master bot defends and then buys a bolt allowing an exact breach on centurion"
- **masn6811** (2019-01-23): "or the bot buys second animus so you set up centurion and instead of buying lucina he just buys WTTD"

**Severity:** LOW
**Fixability:** DEEP CHANGE -- requires opponent modeling

### 6J. Kinetic / High-Value Snipe Unit Misuse -- NEW IN V2

MB immediately fires Kinetic the turn after buying it, rather than waiting for a higher-impact target.

**Key report:**
- **velizar_** (2020-04-03) via `1o0XS-SbPpw`: MB used Kinetic the very next turn after buying it to snipe a Conduit rather than saving it for more impactful use.

**Severity:** LOW-MEDIUM
**Fixability:** HEURISTIC LAYER -- needs timing heuristic for high-value one-shot abilities

### 6K. Savior Buy + Construction Blindspot -- NEW IN V2 (see also 5B)

In addition to the strategic Savior weakness, MB has a specific bug: it purchased Savior on turn 1 in one documented game.

**Key report:**
- **velizar_** (2019-09-10) via `bcmmA-YbKcj`: "A bugged replay shows Master Bot purchasing a Savior on turn 1, which is an anomalous opening."

**Replay codes:** `bcmmA-YbKcj`

### 6L. Venge Cannon Endgame Charge Mismanagement -- NEW IN V2

MB loses games or draws that should be won/drawn because of leftover Venge Cannon charges.

**Key report:**
- **.holyfire** (2026-01-20) via `ZxdlK-@ZTeE`: "MB lost a game that would otherwise have been a draw because it had a charge remaining on its Venge Cannon."

**Replay codes:** `ZxdlK-@ZTeE`

### 6M. Amporilla -- MB Never Uses It (LOW) -- NEW IN V2

**Key report:**
- **307th** (2018-01-30): "Master Bot does not use Amporilla (ampo), which may cause new players to underestimate the unit initially since they won't face it from the AI."

**Severity:** LOW -- Amporilla is a situational unit, but MB's total blindspot creates a knowledge gap for players who only practice against the bot

---

## 7. OTHER QUIRKS

### 7A. Wacky Bot Fallback on Crash (MEDIUM)

When Master Bot crashes mid-game (typically due to certain unit combinations), the server falls back to "Wacky Bot" behavior (random moves). This is a client-side fallback -- Wacky Bot is fully built into the client while MB runs as a separate external process (PrismataAI.exe).

**Key reports:**
- **p0lari** (2018-02-26): "I believe wacky bot behaviour is the fallback when master bot crashes"
- **allroc22** (2018-02-26): "Did someone accidentally replace Master Bot with Wacky Bot recently?" **Replay: `Zmsk5-WZsAz`**
- **iminabearsuit** (2019-12-10): "9/10 cases the bot has crashed, and it defaults to wacky bot"
- **mrguy888** (2020-11-15): "phosphorescent iso caused the bug"
- **apooche** (2018-04-27): Confirmed architecture: "Wacky Bot is built directly into the Prismata client, while Master Bot, Adept Bot, and BottyMcBotFace run as a separate external executable (PrismataAI.exe). If the external AI crashes or times out, the client-side Wacky Bot automatically takes over."
- **elyot** (2018-09): After localization patch, Master Bot began behaving like Wacky Bot in roughly half of all games due to an issue with localized card text
- **ruinedshadows** (2023-04-12): "Master Bot behaving like Wacky Bot shortly after server hiccups in April 2023"
- **velizar_** (2024-04): "The most reliable known trigger is playing a large number of units when there is no unit limit"

**Frequency:** ~12 reports across multiple channels spanning 2018-2024
**Severity:** MEDIUM -- complete loss of AI behavior
**Fixability:** Mostly improved in our fork, but specific unit combination triggers may remain

**Replay codes:** `Zmsk5-WZsAz`

### 7B. AI Thread Disconnect / Timeout Loop -- NEW IN V2

MB can run out of time during its turn and then continue taking its turn indefinitely, causing the game to display a "lost contact with the prismata AI thread" error.

**Key reports:**
- **masn6811** (2018-04-25): Reported recurring issue where AI would run out of time and still keep taking its turn, with error message persisting even after page refreshes
- **amalloy** (2018-06-08): "Master Bot caused a disconnect/crash by stalling long enough that Prismata announced it lost connection to the AI thread, forcing the human player to resign; a fix was reportedly being worked on by the developer."

**Frequency:** ~4 reports
**Severity:** MEDIUM -- forces game abandonment
**Fixability:** Timeout handling in our fork

### 7C. MB Rating Estimate: 1100-1400 Elo (Community Consensus)

The community debates MB's rating. Two estimates emerged: ~1400 Elo from ussgordoncaptain, and ~1100 Elo from mrguy888. Both are consistent with the observation that the bot historically peaked at Tier 6 on the ranked ladder (48% toward Tier 7).

**Key reports:**
- **ussgordoncaptain** (2018-01-01): "like master bot is a 1400 elo player"
- **mrguy888** (2019-05): "Master Bot is estimated at approximately 1100 Elo strength, making it beatable by players above roughly 1600 rating."
- **mrguy888** (2018-07): "Master Bot's ranked performance peaked at Tier 6 (48% toward Tier 7)"
- **elyot** (2020-04-20): "even getting 50% winrate against master bot takes most players many many hours of playing, could be 10-30 hours"
- **amalloy** (2022-07-16): "i was only in like the top 50, and i won about 95% of games against master bot"
- **.jrkirby** (2018-06-16): "On some sets it plays at roughly 2200 MMR equivalence, while on others it drops below 1200 MMR. When it makes a mistake on a given set, it repeats that mistake every single time due to its deterministic nature."

**Conclusion:** MB's effective rating is highly set-dependent, ranging from ~1200 to ~2200 depending on the units present. Average effective rating ~1400 Elo but highly variance-positive for exploitable sets.

### 7D. BottyMcBotFace vs Master Bot Comparison

**elyot** (2018-04-10): "BottyMcBotFace is actually over 100 points stronger than Master Bot" -- this casual bot uses a huge opening book of strong rushes plus AB pruning.

Key structural difference: BottyMcBotFace = Master Bot (7-second think time) + a large opening book. Deep Drone is rated slightly higher than BottyMcBotFace. The opening book advantage is significant, confirming that a hand-tuned opening book would be a quick improvement.

**awaclus** (2024-03): "The 7s Master Bot is not significantly stronger than the 3s Master Bot in practice; the main advantage of playing against the 7s bot is that it takes longer turns, giving the human player more total time to think each round."

### 7E. Compute Time Has Diminishing Returns

**elyot** (2020-04-20): "it needs exponentially more time to go even 1 ply deeper in search, which improves its performance only marginally"

This confirms that the bottleneck is heuristic evaluation quality, not search depth. Our neural net approach is the correct architectural fix.

### 7F. MB Always Picks a Color Early

**vanilvanil** (2023-02-07): "master bot always picks a colour" -- MB always buys a tech building (Animus/Blastforge/Conduit) early, rather than sometimes staying on pure gold economy. This is predictable and sometimes suboptimal.

### 7G. Pay-Gold-for-Attack Circular Dependency -- NEW IN V2

**elyot** (2020-11): "The Master Bot (and AI generally) cannot handle pay-gold-for-attack click abilities on units like the proposed Smorcus rework because it can create circular resource dependencies the AI's decision engine cannot resolve correctly."

This explains why such unit designs were avoided by the developer -- it was an explicit constraint of the bot architecture.

### 7H. Wacky Bot Triggered by Chat Command -- NEW IN V2

**p0lari** (2018-05-28): "Using the in-game chat command /RotatingInferno converts Master Bot into Wacky Bot behavior, making it trivially easy to beat with certain unit combinations."

This was used by players to farm daily rewards and achievements. Patch-dependent, probably fixed.

---

## 8. COMMUNITY EXPLOIT STRATEGIES (Synthesized from 49 MB_EXPLOIT_STRATEGY Insights)

The community has thoroughly catalogued how to beat MB. These are direct quotes from the strongest patterns:

### 8A. Guaranteed Win Unit Combinations

These unit selections have near-100% win rates against MB when used correctly:

| Strategy | Units | Reporter | Notes |
|---|---|---|---|
| Galvani + Venge + Cluster | Galvani Drone, Venge Cannon, Cluster Bolt | lyra1712 | "Easiest known way to beat MB." P1 line: C11/CC/CC/double Venge into Clusters. **Replay: `r8Iip-iDQp3`** |
| Zemora + Mobile Animus | Zemora Voidbringer, Mobile Animus | nvlx | "Rigged all Master Bot achievements" |
| Electrovore + Galvani + Infusion Grid | All three | .bky_1556 | Easy streak; MB has defensive gaffes with this combination |
| Venge Cannon alone | Venge Cannon | awaclus, f300xen | "Makes the Kappa challenge very easy" |
| Perforator + Animus spam | Animus | artificialhope | MB cannot defend early Perforator pressure |
| Smorcus rush | Animus + Smorcus | masn6811 | "MB cannot defend against aggressive Smorcus rushes (Elyot animus or Crazimus)" |
| Tarsier flood (P2 Fastimus) | Animus, Tarsier | hyreon | "Disgustingly easy" P2 Fastimus opening |
| Rectifiers + 11 Drones + 2 Conduits | Conduit | zera777 | 26-game win streak achieved |
| Centrifuge + Zemora + Blood Phage/Perforator | Zemora, Centrifuge | nvlx | MB buys these units and wastes them |

### 8B. Opening Exploits

- **Turn-1 Steelsplitter float**: Stacko (2021-12): "Forces Master Bot to build a Wall instead of a Militia, manipulating its defensive decision-making in the opening."
- **Offer Rhino-onto-Wall gambits**: masn6811 (2020-04-21): "MB will always keep its defensive units rather than accept such gambits, even when accepting would enable a breach of the opponent's Drone Grid."
- **Animus rush (turn 1)**: vanitascabal6962 (2018-05): "Turn-1 Animus into rush against Master Bot is an effective strategy for earning the Rush Master achievement because Master Bot misresponds with inefficient tech purchases."
- **High-economy sets with many defense units**: shadourow (2020-02): "Adding all the defense units makes Master Bot really bad at really high econ."

### 8C. Things MB Is Actually Good At

Counter-evidence from the community -- MB is harder to beat when:
- **Small unit sets** (fewer units): p0lari (2018-03): "Beating casual bots becomes harder when the unit count is reduced, because the AI struggles more with gameplan selection in richer sets where it can default to familiar patterns." MB is better at tactics than strategy.
- **Low-econ tactical mirrors**: mtanzer (2018-03): "MB is strongest in low-economy tactical mirrors (e.g., Grimbotch sets) where precise arithmetic matters."
- **Gauss/Blastforge rush**: masn6811 (2018-03): "Rushing Gauss Cannon / Blastforge is cited as the number one way to lose to Master Bot" -- MB is strong at defending or countering this specific rush.
- **Grimbotch/Vore red sets**: masn6811 (2020-04): "MB is competent with small red units like Grimbotch and Vore, defaulting to a fast Animus build."

### 8D. The Hidden Pattern Effect

**amalloy** (2019-05): "Knowing Master Bot's predictable weaknesses allows players to make plays that are suboptimal against strong humans but optimal against the bot. Players who know they are facing Master Bot have a measurably higher winrate than against an anonymous opponent of equivalent strength."

mrguy888 (2019-05): "Players who previously found it easy to beat when knowing it was Master Bot performed noticeably worse against it when it was disguised as a ladder opponent, suggesting exploitable patterns are a significant component of its apparent weakness."

---

## 9. BOT COMPARISON (from 32 MB_COMPARISON Insights)

### Bot Strength Hierarchy (Community Consensus)

| Bot | Relative Strength | Notes |
|---|---|---|
| Deep Drone | Strongest | Master Bot + large opening book, highest bot rating on community spreadsheet |
| BottyMcBotFace | Very Strong | Master Bot (7s) + opening book; 100+ rating points stronger than standard MB |
| Master Bot (7s/3s) | Strong | The benchmark; 3s and 7s not significantly different in quality (7s gives human more think time) |
| Adept Bot | Medium | Some players prefer it for high-econ practice; better at certain rush defenses |
| Expert Bot | Medium-Low | Good stepping stone before Master Bot |
| Casual bots (EpiCRusheR etc.) | Weak | Execute specific strategies; educational for beginners only |
| Wacky Bot | Random | No strategic logic; cannot reliably buy Drones |

### Key Comparative Findings

- **Opening book is the key differentiator**: BottyMcBotFace, Deep Drone, and "MasterBot2016" all use the same underlying logic as MB but with larger opening books. This is a significant strength advantage, suggesting our PrismatAI would benefit greatly from an opening book keyed to the top units in each random set.
- **Architecture is the bottleneck**: mtanzer (2018-03): "Master Bot uses alpha-beta search with heuristics that generate a small subset of moves to evaluate each turn, rather than any neural network or data-driven component. Community members note this architecture makes it meaningfully weaker than a hypothetical NN-based bot trained on game data."
- **MB was on ranked ladder**: steel0229e (2018-04): MB historically placed at approximately Tier 6 on the ranked ladder in an earlier era. Under the current player distribution, it likely places at Tier 5 or lower.
- **Adept Bot for high-econ**: Some players prefer Adept Bot over Master Bot for practice because Adept Bot plays with a higher-econ style (shadourow, 2024-02).
- **Bot games as a skill bridge**: Community consensus is that consistently beating MB indicates readiness for the lower end of the ranked ladder.

---

## 10. COMMUNITY FEATURE REQUESTS (from 20 MB_FEATURE_REQUEST Insights)

Ranked by reported frequency and developer interest:

1. **Grandmaster Bot / stronger AI** (multiple reporters, 2022-2026): Community explicitly asks for a bot stronger than MB. Suggestions include AlphaGo-style approach (candidate moves + board state evaluation) and opening book keyed to top units per set. aperture: spiritfryer (2026-02), apooche (2026-02).

2. **Analysis-mode AI suggestion button** (apooche, 2019-02; deadhour agreed): "An analysis-mode button that retrieves the Master Bot's recommended move for the current board state without leaving analysis mode." -- This is directly related to our `--suggest` CLI mode (DONE).

3. **Continuous difficulty slider** (velizar_, 2020-04): Rather than discrete levels (Basic/Adept/Expert/Master), players want a slider. Master Bot ceiling is not sufficient for experienced players.

4. **Curated unit list for bot-friendly sets** (velizar_, 2020-04, 2020-03): "Create and publish a curated list of units that Master Bot plays well with, so players can construct custom game sets optimized for bot play." Identified known-bad units: Zemora, Mobile Animus.

5. **Earlier concession** (masn6811, amalloy, 2018-05): "Community members want MB to concede earlier in clearly losing positions, rather than prolonging games through excessive soaking with Blood Pact." amalloy: "quintuple Blood Pact while behind by ~10 attack is just cruel."

6. **Specific improvements requested by flakmaniak (2020-04):** (1) correctly hold Doomed Drones on 1 lifespan for defense, (2) understand and execute absorb denial, (3) understand granularity denial, (4) correctly handle freeze units.

7. **Higher think time option** (velizar_, 2021-01): Players want a 20-second think time option beyond the existing 7-second maximum.

8. **MMR cap for bot games raised** (zezetel, 2024-06): "Consistently beating Master Bot should qualify players for a 1500 rating floor." silentslayers: "raise the MMR cap for bot games."

9. **Bot game pause/resume** (jeacaveo, 2020-03): "Ability to pause an in-progress bot game when a ranked match becomes available, rather than being forced to abandon the bot game."

10. **Quick Play vs Master Bot awards Casual Match trophies** (bifurcatedbitch, 2018-04): Experienced players shouldn't have to choose between earning rewards and playing challenging bot games.

---

## Summary: Priority Rankings (Updated v2)

### Tier 1 -- Highest Impact, Most Reported

| Issue | Section | Reports (v1) | Reports (v2) | Fixability |
|---|---|---|---|---|
| Stamina-blind defense | 2A | 15+ | 20+ | Heuristic |
| Gauss Cannon rush addiction | 4A | 15+ | 15+ | Deep change |
| No offensive pressure / no gambits | 5A, 5C | 10+ | 15+ | Deep change |
| Zemora incompetence | 6A | 8+ | 10+ | Deep change |
| Chill targeting | 3A | 5-8 | 8+ | Heuristic (hard) |

### Tier 2 -- High Impact, Actionable

| Issue | Section | Reports | Fixability |
|---|---|---|---|
| Mobile Animus / Rhino misuse | 4B | 10+ | Heuristic |
| Antima Comet incompetence | 6B | 6+ | Deep change |
| Overteching | 4D | 10+ | Heuristic |
| Resource floating | 4E | 8+ | Heuristic |
| Cluster Bolt blindspot | 6C | 8+ | Deep change |
| Lifespan unit misuse (Grimbotch etc.) | 4C | 8+ | Deep change |
| Savior handling | 5B | 8+ | Deep change |
| Q-defense algorithm bugs | 2D | 10+ | Heuristic |
| BSO line weakness | 4K | 4+ | Opening book |

### Tier 3 -- Medium Impact, Worth Fixing

| Issue | Section | Reports | Fixability |
|---|---|---|---|
| Absorb on wrong unit class | 2B | 5-8 | Heuristic |
| Breach-avoidant play | 3B | 6 | Heuristic |
| Infusion Grid ignored / misused | 6F | 6 | Heuristic |
| Gauss Charge over-purchase | 4F | 5+ | Heuristic |
| Ebb Turbine drone loop | 4I | 2 | Heuristic |
| Doomed Drone lifespan holding | 4H | 2 | Heuristic |
| Vivid Drone misuse | 4G | 2 | Heuristic |
| Electrovore + Galvani gaffes | 6G | 3 | Heuristic |

### Tier 4 -- Low Impact / Niche

| Issue | Section | Reports | Fixability |
|---|---|---|---|
| Cauterizer click blindspot | 2E | 1 | Heuristic |
| Asteri useless activation | 3D | 1 | Heuristic |
| Bombarder timing | 6H | 1 | Heuristic |
| Ossified Drone ignored | 6E | 1 | Unknown |
| Tesla Coil incompetence | 6D | 1 | Heuristic |
| Always picks a color early | 7F | 1 | Opening book |
| Kinetic immediate-fire | 6J | 1 | Heuristic |
| Venge Cannon endgame charge | 6L | 1 | Heuristic |
| Amporilla never purchased | 6M | 1 | Unknown |
| Premature resign | 5G | 8+ | Evaluation |
| Spend-all-flexible on Engineers | 5H | 1 | Heuristic |

---

## Appendix A: All Replay Codes Referenced

| Code | Issue | Reporter | Date |
|---|---|---|---|
| `Wiieo-DVcO6` | 0-stam Deadeye absorb over Wall (T13-15) | zakisan1 | 2019-01-02 |
| `MRleA-YHVhe` | 0-stam Bombarder absorb over E-Matrix | siepu | 2019-03-24 |
| `Qcb29-urWUb` | Empty Bombarder absorb, Matrix soak | awaclus | 2020-04-16 |
| `Z7nus-v@YI5` | MB absorbs on Tia Threnody, soaks on Centurion | .holyfire | 2024-03-15 |
| `WIXwx-YsqV+` | MB uses Plexo Cell instead of absorbing | velizar_ | 2021-12-25 |
| `eUfkH-nBFhd` | MB sac'd Wall to save Corpus and click it | masn6811 | 2020-12-08 |
| `psDxO-FGMrE` | MB ignores Cauterizer clicks, underdefends | liadahlia | 2018-03-10 |
| `5VnVG-XG@fB` | Q-defense soaks Steelsplitter over Wall | .holyfire | 2025-08-10 |
| `78xVR-XRYE0` | Galvani targeted over Drones during breach | .holyfire | 2025-03-07 |
| `izkDb-sy6uF` | Chill wasted on walls instead of barrier (T11) | alex319 | 2020-11-20 |
| `m+Yhp-rSaTr` | Killed Wild Drones instead of breaching | velizar_ | 2022-06-04 |
| `1o0XS-SbPpw` | Kinetic immediately used to snipe Conduit | velizar_ | 2020-04-03 |
| `i9LTQ-x+f9s` | Gauss Cannon rush with Thorium Dynamo | velizar_ | 2019-07-19 |
| `BxFCp-Yz990` | Lost to Iso + Gauss + Thorium | velizar_ | 2019-07-19 |
| `QuXEb-4GM0t` | Gauss Cannon rush ignoring set | velizar_ | 2020-01-01 |
| `enK@3-JLgdD` | Thorium Gauss, 51g floated at end | velizar_ | 2020-02-26 |
| `0jBEo-Kbqz9` | Related Thorium Gauss game | velizar_ | 2020-02-26 |
| `CtRG2-BqL4o` | MB ignores Arka, Fabricator + Gauss rush | velizar_ | 2019-07-19 |
| `VNw+z-CskPt` | Bot bought 10 Mobile Animuses by turn 9 | amalloy | 2018-05-01 |
| `qJ0Jm-6@Sfb` | Bot bought 9 Mobile Animuses, spent 2 red total | amalloy | 2018-06-28 |
| `qivv4-6CAIG` | Fix attempt: bot now clicks Mobile Animus immediately | vanitascabal6962 | 2018-05-12 |
| `mDFOe-tJKWK` | Floated 5G+3B+5R to buy Bombarder | zera777 | 2020-03-25 |
| `scmG1-OcNum` | Resigned 2 turns before Savior finished construction | .holyfire | 2025-10-05 |
| `65Qom-0yv6g` | Nearly won Savior mirror but threw by targeting wrong unit | amalloy | 2018-06-18 |
| `bcmmA-YbKcj` | MB purchased Savior on turn 1 (bugged) | velizar_ | 2019-09-10 |
| `X1ggL-LYHKj` | Premature resign T8, no damage dealt | stacko | 2022-04-13 |
| `9TaJh-ntrow` | Never bought attackers, just defended and resigned | velizar_ | 2020-09-21 |
| `LIIfR-GD6sF` | MB resigned against player with only Clickers | velizar_ | 2020-09-14 |
| `ZxdlK-@ZTeE` | MB lost draw due to unused Venge Cannon charge | .holyfire | 2026-01-20 |
| `r8Iip-iDQp3` | Galvani + Venge + Cluster exploit demo | lyra1712 | 2020-08-24 |
| `pRZrm-4XbNx` | Venge + Cluster + Galvani achievement win | lyra1712 | 2022-07-29 |
| `j6TOF-M2yA5` | Red Base (Tarsimus) P1/P2 asymmetry | hyreon | 2019-10-21 |
| `3@0pW-fHoKx` | Multiple severe bot errors in one game | velizar_ | 2020-04-27 |
| `Zmsk5-WZsAz` | Wacky bot fallback (crash) | allroc22 | 2018-02-26 |
| `8GY2m-UYL2b` | Game freeze from Wincer with unremoved skin | awaclus | 2020-12-04 |
| `vyZ7a-5qIlL` | Gauss rush sufficient to beat MB | miuna6933 | 2018-06-26 |
| `iELGb-ZzOit` | Drake strategy to beat MB | zera777 | 2020-02-25 |
| `wuhoL-ijMk6` | Animus rush works vs bot but not vs BED | siepu | 2019-03-16 |
| `gaC27-oK@6d` | Custom high-econ set achievement win | lyra1712 | 2022-07-29 |
| `QHAH0-HoPdz` | General MB weakness demo | amalloy | 2018-06-30 |
| `JL6Y6-3VpKU` | MB weak vs Galvani variants | .bky_1556 | 2018-04-08 |
| `dc6f5-rWjui` | MB weak vs Galvani variants | .bky_1556 | 2018-04-08 |
| `20Y9x-VJozp` | General odd MB game | shadourow | 2019-07-26 |
| `2u@BR-+IP8v` | Ultra-high econ set Comeback King achievement | shadourow | 2018-11 |

---

## Appendix B: Impact on Our Neural Net Training

Several community observations are directly relevant to our self-play training pipeline:

1. **Cost-based valuation is the root cause** of most issues (apooche, 2025-03-09). Our Will Score heuristic uses resource cost as a proxy for value. The neural net should learn unit-in-context values that diverge from cost (e.g., 0-stam Corpus worth ~0, fresh Galvani worth ~1G, Doomed Drone on lifespan-1 = valuable blocker).

2. **Temporary vs. permanent attack distinction** (Rhino, Grimbotch, Gauss Charge) is critical and not captured by cost. Our feature vector includes lifespan/stamina, so the neural net can in principle learn this.

3. **Multi-turn planning** (Zemora, Antima, Cluster, Ebb Turbine drone loop) is fundamentally beyond heuristic play. The neural net plus search should eventually handle these, as they require valuing future resource accumulation.

4. **Chill optimization** is computationally expensive but high-impact. Even a simple "freeze the absorber first" heuristic would be a massive improvement.

5. **Opening book matters**: BottyMcBotFace and Deep Drone are meaningfully stronger than MB purely because of opening book additions. A hand-tuned opening book keyed to the top units per set would be a quick, high-value improvement before or alongside neural net deployment.

6. **Set-specific consistency**: .jrkirby's observation that "when it makes a mistake on a given set, it repeats that mistake every single time due to its deterministic nature" highlights that our current OriginalHardestAI baseline has systematic set-dependent weaknesses. Our neural net should generalize across sets rather than memorizing set-specific bad habits.

7. **The community explicitly asks for reporting channels** for bot issues (phin8459, 2019-09-02; zakisan1, 2019-01-02). Our improvements, especially the 51.9% WR milestone, would be well-received.

8. **Gauss Charge absorb blindness** (velizar_, 2020-04): MB buys Gauss Charges when they will be fully absorbed by an already-built Urban Sentry or Infusion Grid. The neural net needs to learn opponent absorb capacity from the feature vector.

9. **Architectural confirmation**: apooche's 2025-01 note that "MB has approximately four fixed defense algorithms and applies MCTS only to choose among them" confirms our approach of using neural evaluation with alpha-beta search is architecturally superior, not just quantitatively better.
