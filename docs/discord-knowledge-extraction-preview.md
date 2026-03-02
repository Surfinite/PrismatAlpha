# Discord Knowledge Extraction Preview
Generated: 2026-02-22T06:51:11.459764

## Statistics
- After dedup: 1426
- Duplicates removed: 9
- New insights: 133
- Confirms existing: 1293

### Category Distribution
| Category | Count |
|---|---|
| BALANCE_OPINION | 52 |
| COMMUNITY_JARGON | 12 |
| DEFENSE_STRATEGY | 1 |
| EXPERT_ASSESSMENT | 36 |
| GAME_MECHANIC | 93 |
| OPENING_THEORY | 162 |
| STRATEGY_RULE | 682 |
| UNIT_INTERACTION | 388 |

### Temporal Validity
| Validity | Count |
|---|---|
| historical | 36 |
| patch_dependent | 649 |
| timeless | 741 |

## Contradictions (0 -- ALL require review)
None detected (automated check only -- manual spot-check recommended).

## Top 50 High-Confidence New Insights

1. **[BALANCE_OPINION]** Big units tend to be more cost-efficient than small units because they are harder to obtain; if a plausible excuse to purchase a legendary exists, it is usually not a bad idea.
   - Author: amalloy | Date: 2019-09 | Temporal: timeless

2. **[COMMUNITY_JARGON]** "GF'd" (Greatly Favored) means the opponent has a significant advantage that approaches an autowin; players often overstate winrate implications when using this term.
   - Author: consensus | Date: 2018-04 | Temporal: timeless

3. **[COMMUNITY_JARGON]** Base set units are commonly abbreviated by their in-game hotkey: F = Forcefield (not FF which is ambiguous for two Forcefields); this notation is standard in replays and analysis.
   - Author: p0lari, steel0229e | Date: 2018-04 | Temporal: timeless

4. **[COMMUNITY_JARGON]** In Prismata notation, lowercase letters (r, g, b) denote resource types (red, green, blue) and uppercase letters (R, G, B) denote units that produce those resources. Gold is typically written with a standalone number (e.g., '2' means 2 gold), and can optionally be labeled as '2 gold' for clarity to new players. Capital G is reserved for Gaussite.
   - Author: mrguy888, apooche | Date: 2018-05-11 | Temporal: timeless

5. **[COMMUNITY_JARGON]** 'Splashing a color' means buying a small amount of one color in a build dominated by another color (e.g., buying one Red unit in a mostly Green economy).
   - Author: miuna6933 | Date: 2018-05 | Temporal: timeless

6. **[COMMUNITY_JARGON]** Sets are classified as 'tactical' when they feature aggressive attackers and low efficient defense, putting emphasis on exact health exchanges and narrow decision windows.
   - Author: namington | Date: 2018-06 | Temporal: timeless

7. **[COMMUNITY_JARGON]** 'Timewalking' refers to invalidating your opponent's entire turn or action for minimal cost, essentially giving yourself an extra turn. Borrowed from Magic: The Gathering terminology.
   - Author: swapgo, cogito3 | Date: 2018-07-07 | Temporal: timeless

8. **[EXPERT_ASSESSMENT]** Developer Elyot noted that StarCraft 2 has too much defender's advantage due to warp gate negating positional strategy, which was a problematic design that inspired Prismata's more balanced approach.
   - Author: elyot (Developer) | Date: 2018-02-07 | Temporal: timeless

9. **[EXPERT_ASSESSMENT]** Shalev's Rule (from Lunarch's original design specification) is a core design principle in Prismata: units that are individually weaker create more interesting decision-making through opportunity costs, and the game's adherence to this principle is a major design strength that distinguishes it from other card games.
   - Author: consensus | Date: 2018-03 | Temporal: timeless

10. **[EXPERT_ASSESSMENT]** Overall Player 2 winrate is ~52%, which is lower than many competitive games; set-specific advantages can exceed 58-65% (e.g., pure Redeemer mirrors) but true autowin sets are extremely rare.
   - Author: liadahlia, 307th, consensus | Date: 2018-04 | Temporal: historical

11. **[EXPERT_ASSESSMENT]** At 1600 MMR, most improvement comes from fixing mechanical errors (overteching, wasting energy in opening) rather than set reading. Watching high-level streams and replays becomes more valuable at 1700-1800+ when set reading is the limiting factor.
   - Author: 307th | Date: 2018-04-21 | Temporal: timeless

12. **[EXPERT_ASSESSMENT]** Apooche's inflation math articles are the most trustworthy publicly available analysis because they present graphs across multiple inflation values rather than single-point conclusions, avoiding the critical error of assuming a specific inflation scenario.
   - Author: consensus | Date: 2018-04 | Temporal: timeless

13. **[EXPERT_ASSESSMENT]** When learning from bot games, replay a set where the bot beat you using strategy X, then play as the bot's side and try to execute that same strategy yourself; if you can win with it, you've validated it as playable and improved your fundamentals; if you can't, analyzing the differences reveals skill gaps.
   - Author: amalloy, mrguy888 | Date: 2018-10-22 | Temporal: timeless

14. **[EXPERT_ASSESSMENT]** Base Set Only (BSO) has been extensively analyzed by top players who consistently conclude P2 is winning, though no exhaustive proof exists; the analysis is sufficiently comprehensive that major oversights are unlikely, but theoretical certainty remains unachieved.
   - Author: mrguy888, amalloy, mtanzer, masn6811 | Date: 2019-04 | Temporal: timeless

15. **[EXPERT_ASSESSMENT]** A unit should only be considered truly overpowered if it has all three properties: high generality (buyable in many sets), high raw power (gives a large advantage to the player with access), and high set dictation (forces the rest of set strategy around it). Few units meet all three criteria simultaneously.
   - Author: junkmail | Date: 2019-10 | Temporal: timeless

16. **[EXPERT_ASSESSMENT]** Prismata skill can be acquired relatively quickly compared to chess, Go, or League—proficient players emerge within 1 year of regular play, whereas these games require years of study. However, top-level play remains mechanically complex and difficult to master.
   - Author: sano712, lyra1712 | Date: 2020-04-19 | Temporal: historical

17. **[EXPERT_ASSESSMENT]** Value math systems (like Yujiri's) are approximations useful for rough efficiency comparisons, but all single-value systems will be incorrect in some cases. A 33.3% interest rate model can serve as an alternative framework.
   - Author: anesotericman | Date: 2020-07 | Temporal: timeless

18. **[GAME_MECHANIC]** The Q key automatically collects gold from all drones without secondary costs and auto-selects a working defense and offense, useful for newer players unsure of their defenses but not necessarily optimal.
   - Author: kynarethnobaka | Date: 2018-01-14 | Temporal: timeless

19. **[GAME_MECHANIC]** When calculating defense against freeze, units you choose not to sacrifice are not blockers. You can exclude freeze options involving units you want to keep alive by simply not counting them as part of your defense pool—if they're frozen, they're no longer defending, but you also don't lose them.
   - Author: punf, mtanzer | Date: 2018-02 | Temporal: timeless

20. **[GAME_MECHANIC]** Base set only is the simplest unit pool; adding even a single unit to the pool drastically changes timings and interactions. Random set complexity increases exponentially with more units, making base set theory only theoretically relevant.
   - Author: steel0229e | Date: 2018-03 | Temporal: timeless

21. **[GAME_MECHANIC]** Buying an attacker that gets completely absorbed by the opponent's defense is strictly worse than holding the resources and waiting to deploy the attacker when it will matter.
   - Author: awaclus | Date: 2018-03 | Temporal: timeless

22. **[GAME_MECHANIC]** Holding a burst unit (like Arka or Omega) instead of clicking it provides defensive tempo advantage: the opponent must buy more soak to handle the held click turn, freeing up resources for the attacker to build more permanent attack. Holding is superior to clicking when wall absorb is available, as it avoids redundant defense spending.
   - Author: mtanzer, mrguy888 | Date: 2018-03 | Temporal: timeless

23. **[GAME_MECHANIC]** In the Armory rewards system, re-flipping cards is optimal only if your current 5-card set matches one of the known value combinations (e.g., r2-r3-b5-b10-g2); a heuristic is to re-flip if you have 3 cards of one color that synergize well, otherwise do not re-flip.
   - Author: jamesa7171, consensus | Date: 2018-04 | Temporal: timeless

24. **[GAME_MECHANIC]** When evaluating unit value through math, inflation rate (R) significantly affects comparisons between units with different time horizons and resource costs; providing multiple inflation scenarios is more useful than single-point outputs.
   - Author: mrguy888 | Date: 2018-04 | Temporal: timeless

25. **[GAME_MECHANIC]** Mathematical unit analysis in Prismata is only as useful as the quality of its assumptions; lazy mathematical assumptions can produce outputs that are worse than pure game knowledge if they ignore critical factors like unit timing, resource interactions, and early-game dynamics.
   - Author: mrguy888 | Date: 2018-04 | Temporal: timeless

26. **[GAME_MECHANIC]** Inflation is a key economic concept: the rate at which resources earn returns. In Prismata, using resources inefficiently (e.g., holding a Drone for defense instead of buying Wall) incurs an inflation cost equivalent to the returns that resource would have generated.
   - Author: liadahlia, amalloy, consensus | Date: 2018-05-11 | Temporal: timeless

27. **[GAME_MECHANIC]** Inflation (resource value over time) is asymmetrical between players: one player may face high inflation (needing defense/gold immediately) while the opponent faces low inflation (sitting breachproof). A player can have high inflation while their opponent has low inflation simultaneously.
   - Author: masn6811, Deleted User, liadahlia | Date: 2018-06-04 | Temporal: timeless

28. **[GAME_MECHANIC]** In high-inflation scenarios (e.g., red breach mirror), swords now are significantly more valuable than future swords, making immediate attack and Perfection clicks better than holding drones for later economic value.
   - Author: masn6811, Deleted User | Date: 2018-06-04 | Temporal: timeless

29. **[GAME_MECHANIC]** Inflation is the core mechanic governing unit purchasing decisions; it measures the compounding return on investment (ROI) of units over time. Drone inflation is approximately 4/3 (1.3333) per turn assuming free energy.
   - Author: namington | Date: 2018-06 | Temporal: timeless

30. **[GAME_MECHANIC]** Calculating freeze threats effectively requires adding chill to attack, then subtracting 'fake chill' (non-granular chills where defenders have less health than the chill value), rather than just adding attack and chill.
   - Author: consensus (namington, totally_not_fbi, cogito3) | Date: 2018-06 | Temporal: timeless

31. **[GAME_MECHANIC]** Area of Effect (AoE) in Prismata is defined as an effect that damages or affects all units in a region at the same cost regardless of how many units are hit, making it inherently difficult to balance—either cost-effective and broken, or ineffective and useless.
   - Author: cactus_wren, consensus | Date: 2018-07 | Temporal: timeless

32. **[GAME_MECHANIC]** Golden armor is the buildtime invulnerability mechanic that applies to units purchased (golden) but not to units created by other units or effects.
   - Author: consensus | Date: 2018-12-10 | Temporal: timeless

33. **[GAME_MECHANIC]** The balance between buying attack early (forcing opponent defense) and maintaining economy advantage is the single most important balancing factor in Prismata.
   - Author: mrguy888 | Date: 2019-05 | Temporal: timeless

34. **[GAME_MECHANIC]** Prismata decision-making is fundamentally about broad situational assessment rather than universal rules; context such as what defensive resources are available, what your opponent is forced to buy, and what immediate threats exist determine unit value more than cost alone.
   - Author: mrguy888 | Date: 2019-06-28 | Temporal: timeless

35. **[GAME_MECHANIC]** Prismata decision trees are extremely large even after eliminating strictly dominated moves, because floating gold, holding units, and various defensive options are rarely strictly dominated—they are context-dependent.
   - Author: consensus | Date: 2020-04 | Temporal: timeless

36. **[GAME_MECHANIC]** Inflation is the relative value of resources over time; as inflation increases (early to late game), the return on investment of attackers increases relative to drones because preventing damage becomes more valuable than generating income.
   - Author: .bky_1556 | Date: 2020-05 | Temporal: timeless

37. **[GAME_MECHANIC]** Unit efficiency calculations should account for interest rate (time value of resources). A 33.33% interest rate per turn is a reasonable approximation for standard midgame, making recurring gold or attack worth 3x the nominal value.
   - Author: anesotericman | Date: 2020-09-15 | Temporal: timeless

38. **[GAME_MECHANIC]** In Black Lab, the probability of flipping a color you don't have (like White with only Blue unlocked) is very low (~1 in 30), making it extremely expensive to convert shards into lab tickets for color-specific farming unless you specifically want Infusions.
   - Author: jamberine | Date: 2020-12-26 | Temporal: timeless

39. **[GAME_MECHANIC]** The RNG seeding system in Prismata causes all Robo Santa units in a single game to generate identical output (same unit type), likely due to how the RNG is deterministically seeded per unit rather than allowing true independent randomness.
   - Author: masn6811 | Date: 2018-05-25 | Temporal: timeless
   - Units: Robo Santa

40. **[OPENING_THEORY]** Effective planning involves establishing three core targets early: economy size, tech setup, and a general unit acquisition order. This outline can then be adjusted based on opponent actions, and even having 70% of a plan helps significantly.
   - Author: 307th | Date: 2018-03 | Temporal: timeless

41. **[OPENING_THEORY]** DD/DA (fastimus) is a strong P2 opening in sets without green, trading a drone for early attackers; it gets ~11 resources to spend on DTT or similar purchases and generally gives P2 the upper hand.
   - Author: star_bringer, medar | Date: 2018-07 | Temporal: timeless

42. **[OPENING_THEORY]** Learning a set by playing it multiple times (even losing on the same set) is more valuable than playing five different sets, because you can compare your execution to the bot or opponent's execution of the same strategy.
   - Author: consensus | Date: 2020-05 | Temporal: timeless

43. **[STRATEGY_RULE]** Tia Threnody is particularly weak against breachproof strategies because it cannot deal enough damage to force a breach, negating one of its primary advantages.
   - Author: f300xen | Date: 2018-03 | Temporal: patch_dependent
   - Units: Tia Threnody

44. **[STRATEGY_RULE]** Tia Threnody should generally be threatened rather than bought early. The threat of Tia restricts your opponent's options. When you do buy Tia, it's often because your opponent underestimated the threat and you are cashing in a winning position.
   - Author: amalloy | Date: 2018-05-16 | Temporal: patch_dependent
   - Units: Tia Threnody

45. **[STRATEGY_RULE]** Buying Tia Threnody should follow a principle: buy it if and only if doing so results in winning the game. There is no simple shortcut to determining when Tia is good; it requires evaluating the specific set context.
   - Author: consensus | Date: 2020-07 | Temporal: timeless
   - Units: Tia Threnody

46. **[STRATEGY_RULE]** In breachproof mirrors or when breachproof is clearly winning, the non-breachproof player should focus on long-game strategies with good absorbers and soaks because breachproof players eventually run out of economy while defenders maintain theirs.
   - Author: extratricky | Date: 2018-03 | Temporal: timeless

47. **[STRATEGY_RULE]** Absorbing on a non-fragile blocker (using all but one health) is highly efficient early game: you nullify more attacker value than the blocker's cost. You typically only get one quality absorber per game due to the efficiency constraint.
   - Author: .bky_1556 | Date: 2018-03 | Temporal: timeless

48. **[STRATEGY_RULE]** If you purchase an attack unit, you should use it to deal damage; holding an attack unit without clicking it for multiple turns allows the opponent to improve their defense relative to your threat, reducing the unit's value.
   - Author: crash_overlord, wilson0862 | Date: 2018-04 | Temporal: timeless

49. **[STRATEGY_RULE]** Breach-proof strategies generally lose to good defensive infrastructure (dedicated defense units like Wall, Infusion Grid); breach-proof games are rare and usually only viable at game's end when the defending player can no longer buy absorbers profitably.
   - Author: darkeisbein, steel0229e consensus | Date: 2018-04-12 | Temporal: timeless

50. **[STRATEGY_RULE]** There is no such thing as a true 0% winrate matchup (an 'autowin') in Prismata. While some sets may be heavily favored for one player, the other player always has a non-zero chance to win through superior play. Assuming an autowin prevents you from learning how to outplay your opponent.
   - Author: liadahlia, mtanzer, consensus | Date: 2018-05-11 | Temporal: timeless

## Category Samples (up to 5 per category)

### BALANCE_OPINION (52 total)
- [high] Venge Cannon is extremely efficient without the click ability when you do not have to buy drones alongside it. At a barrier value of 2.4, it is slightly more efficient than Shadowfang.
  _anesotericman, 2020-09-15_
- [medium] Centrifuge's post-nerf cost (3GG instead of 20GG) and effect creates a feeling of poor resource management when purchased, rather than enabling exciting game-swinging moments; this is psychologically different from the old version despite similar quantitative efficiency in niche cases.
  _masn6811, 2018-05-25_
- [medium] Buying both Manimus and Scorchilla is inefficient. Each is good for converting Red when you don't want it anymore—use one or the other, not both together.
  _tarolg, 2018-07-09_
- [medium] Arms Race is a fundamentally weak card; it becomes even worse in Galvani Drone sets (Galvani provides defensive economy that competes with Arms Race value) or Electrovore sets, making it not worth considering in those contexts.
  _awaclus, 2018-04_
- [medium] Arka Sadora's prompt mechanic enables counter-arka gameplay which can lead to stalled positions where neither player builds first Arka; the design masks over-tuning in cost/stats, similar to how Immaculon was over-buffed with Plexo Cells.
  _masn6811, 2018-05_

### COMMUNITY_JARGON (12 total)
- [high] 'Big red' refers to any strategy involving a 3+ red cost unit such as Amporilla or Lucina.
  _wiwiweb, 2018-05_
- [high] 'Splashing a color' means buying a small amount of one color in a build dominated by another color (e.g., buying one Red unit in a mostly Green economy).
  _miuna6933, 2018-05_
- [medium] "Value Wincer" refers to purchasing Wincer for its defensive value (15 HP worth more than 5 drones over 2.5 turns) without firing it, relying on tempo advantage. "Value Wincer Click" (or "Firing Wincer") refers to actually threatening to fire Wincer by then, gaining both the defensive tempo and burst damage.
  _masn6811, Deleted User, 2018-03_
- [high] Shock: a unit property describing units that threaten damage exceeding their tech cost. Drake threatens 4 damage with 2 tech (positive shock); Valkyrie threatens 4 damage with 4 tech (no shock).
  _mrguy888, 2018-04_
- [high] Base set units are commonly abbreviated by their in-game hotkey: F = Forcefield (not FF which is ambiguous for two Forcefields); this notation is standard in replays and analysis.
  _p0lari, steel0229e, 2018-04_

### DEFENSE_STRATEGY (1 total)
- [medium] Against Pixie-heavy attacks, buying Engineers preemptively for granularity is better than buying Walls reactively, as Walls are inefficient blockers against small distributed damage. Husks can be more efficient than Walls in specific pixie matchups.
  _steel0229e, 2018-04_

### EXPERT_ASSESSMENT (36 total)
- [medium] Chrono Filter is a superior alternative to Centrifuge in many situations because it provides good value in sets where it has strong payoffs, unlike Centrifuge which now requires very specific (mostly Vai-based) synergies to justify the investment.
  _namington, masn6811, 2018-05-25_
- [high] In sets where Matrix is available alongside Amporilla, the set is defined by these two units: Matrix is one of the best defensive units and shuts down rushes, while uncontested Amporilla in a high-econ game is game-ending.
  _p0lari, 2018-03_
- [high] In a Breachproof vs Big Red matchup (set: Venge Cannon, Cluster Bolt, Fabricate, Zemora Voidbringer, Aegis, Plexo Cell, Doomed Wall, Lucina), buying Conduits early for Cluster Bolt without establishing sufficient permanent damage is strategically weak.
  _p0lari, 2018-05-21_
- [high] Elyot Animus (DD/A opening) is named after Elyot Grant, one of the game's founders. It enables P1 to execute fast red rushes one turn faster than P2's standard double-Engineer opening, and is correct when the set features strong red rush units.
  _masn6811, 2018-03_
- [high] Overall Player 2 winrate is ~52%, which is lower than many competitive games; set-specific advantages can exceed 58-65% (e.g., pure Redeemer mirrors) but true autowin sets are extremely rare.
  _liadahlia, 307th, consensus, 2018-04_

### GAME_MECHANIC (93 total)
- [high] Unit efficiency calculations should account for interest rate (time value of resources). A 33.33% interest rate per turn is a reasonable approximation for standard midgame, making recurring gold or attack worth 3x the nominal value.
  _anesotericman, 2020-09-15_
- [high] Win conditions in Prismata differ from asymmetric card games; both players usually share the same win condition (having more damage than opponent can defend). Specific units become win conditions when they are so impactful that successfully activating them results in a very high win probability.
  _xyotsuba, liadahlia, consensus, 2018-05-12_
- [high] Grimbotch with 1 lifespan should almost never be used offensively when taking damage; defending (2 damage soak value) is vastly superior to attacking (1 damage output), unless breaching or exploiting specific positions.
  _namington, 2018-06_
- [high] Xaetron's charge mechanics: can fire twice in a row around turn 8-9 of holding it (assuming purchase turn is turn 1). Charges have Exhaust 1 property, making them similar in speed to Tarsier (Build Time 1).
  _consensus, 2018-06_
- [high] Gauss Cannon and Iso Kronus are roughly equivalent in efficiency when all damage is relevant; choice between them depends on opponent's defense composition and how you'll spend remaining gold.
  _mtanzer, 2018-03_

### OPENING_THEORY (162 total)
- [medium] The viability of 3-Engineer depends heavily on set units; sets with obvious punishers (fast attackers, high-efficiency aggro) make 2-Engineer correct, while sets with high-absorption defenders and slow threats make 3-Engineer correct.
  _pikachumemes, megasupp, spiritfryer, consensus, 2026-01_
- [medium] Double Thorium Dynamo opening can support double Gauss Cannon on turn 5 in the mirror matchup to cut off opponent drone production before they acquire another Dynamo.
  _.bky_1556, 2020-05_
- [medium] In base + Apollo + Lucina sets, neither player should commit to purchasing Lucina early because Apollo beats Lucina; the optimal play involves building defensively and letting the opponent misplay by committing to Lucina first.
  _mrguy888, 2018-09_
- [medium] In base set, P1's most efficient openings in a vacuum are DD DDE or DD DD DDA. DD DD is often preferred over DD DDE because it leaves the option for DDA or DDB on turn 3, whereas DD DDE locks into DDDB or DDDC.
  _extratricky, liadahlia, 2018-03_
- [medium] In base set with Thunderhead available, threatening or buying Thunderhead early is a strong opening strategy; double blue into double red as soon as you have Thunderhead threat is competitive.
  _consensus (mqp, punf, String), 2018-03_

### STRATEGY_RULE (682 total)
- [high] Attack units should be purchased when you have enough economy to jump from zero damage past opponent's absorption in one turn; purchasing attackers too early wastes value as they get absorbed gradually, while purchasing too late gives opponent an insurmountable defense lead.
  _xujhan, 2018-06_
- [medium] Against a greedy opening or big-unit rush, efficient small red units like Vore and Perforator are the standard punishment. What counts as 'efficient small red' depends on set and opponent strategy.
  _masn6811, 2018-05_
- [medium] In low-economy, fast-attack Scorchilla sets, buying Conduit first as P1 is generally losing; natural Animus or other fast openers are required.
  _mrguy888, 2019-05_
- [medium] In fast sets with Drake, Lancetooth, and Smorcus, P2 should consider aggressive openings like float 4 into BBD into Drake, or Smorcus opening (DA into Smorcus+DD) rather than single Iceblade builds.
  _silentslayers, 2021-09_
- [medium] Buying two Bloodragers to deny one absorb is inefficient—you effectively pay 12 gold per Bloodrager, which is no better value than buying Steelsplitters for pure attack.
  _zera777, 2019-09_

### UNIT_INTERACTION (388 total)
- [medium] Xeno's best use is hard countering freeze effects, not just serving as a general absorber.
  _pikachumemes., 2021-10_
- [medium] Centurion is typically not buyable if opponent threatens to attack with Tatsu Nullifier, Amorphous Aggregate, or Vai Mauronax due to cheap small red attackers forcing fast games.
  _silentslayers, 2021-08_
- [high] Perforator's delayed build time (2 turns to first attack) effectively costs attackers ~2 damage per turn compared to Tarsier, equivalent to giving the opponent ~4G per turn, making Perforator-based offenses cost approximately 6R per effective attack when fully considered.
  _amalloy, 2018-03-20_
- [medium] Galvani Drone is a superior alternative to standard Drones when you never want to build another Drone again, being significantly cheaper while serving the same economic role.
  _crash_overlord, 2018-03_
- [medium] Bloodrager can often be bought for only one real damage cost if timed correctly to deny some opponent absorb, making it a high-value early purchase in the right context.
  _.bky_1556, 2020-05_

## Developer Checklist
- [ ] Top 50 insights look genuinely useful to a Prismata player
- [ ] No category is producing systematically bad extractions
- [ ] Contradictions reviewed (decide: keep Discord version or KB version)
- [ ] Confidence levels feel appropriately calibrated
- [ ] COMMUNITY_JARGON samples look tone-appropriate
- [ ] Spot-check 5 insights against original Discord messages

**If review fails:** Return to Phase 1.5 and recalibrate. Do NOT proceed with bad extractions.