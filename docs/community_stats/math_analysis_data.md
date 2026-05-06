# Prismata Math Analysis Data

Community-sourced mathematical analysis from Google Sheets.
Detailed unit valuations and time-series calculations.

## Unit Valuations

Cost in Gold Equivalent (including build-time). Defense/Overall efficiency and breachproof values.

| Unit | Cost | Gold Equiv Cost | Defense Value (1st turn) | Defense Eff (1st turn) | Total Value (Long-term) | Overall Eff (Long-term) | Breachproof Eff | Comments |
|---|---|---|---|---|---|---|---|---|
| Engineer | 2.0000 | 2.0000 | 1.6903 | 8.2825 | 1.6903 | 8.2825 | 0.0000 | an engineer that prevents an exploit for 1 may be worth double!  more valuable when you need the energy. |
| Drone | 3E | 3.0000 | 1.6903 | 12.4238 | 2.5000 | 8.4000 | 2.5000 | a drone clicked 3 times is still worth ~2.5 (overall eff. ~9.74).  at four clicks this is about the same efficiency as engineer.  overall eff. 6 if the 3 would otherwise be floated.  holding a drone (that would otherwise live a long time) costs ~1.7, which is still ~0.6 better than getting exploited for 1, but probably worse when shutting off tech. |
| Conduit | 4.0000 | 4.0000 |  |  | 3.3333 | 8.4000 | 1.1111 |  |
| Blastforge | 5.0000 | 5.0000 |  |  | 4.1667 | 8.4000 | 1.3889 |  |
| Animus | 6.0000 | 6.0000 |  |  | 5.0000 | 8.4000 | 2.5000 |  |
| Forcefield | 1G + 1D | 4.8333 | 4.7329 | 7.1486 | 4.7329 | 7.1486 | 0.0000 | if you would otherwise be holding a drone, this is like paying G for 1 defense (really good!).  worse when shutting off tech |
| Gauss Cannon | 6G | 7.3333 |  |  | 7.0000 | 7.3333 | 1.4000 |  |
| Wall | 5B | 6.6667 | 7.0993 | 6.5734 | 7.0993 | 6.5734 | 0.0000 | calculations for use as soak.  first wall as an absorber is much more valuable. |
| Steelsplitter | 6B | 7.6667 | 5.0709 | 10.5832 | 7.0000 | 7.6667 | 2.3333 | hold (and die) loses ~0.58 compared to attack once then hold.  loses ~2.30 compared to attack forever |
| Tarsier | 4R | 5.0000 |  |  | 5.0000 | 7.0000 | 7.0000 | most efficient base set unit!  very slow, only a good buy if it's attacking 7+ times. |
| Rhino | 5R | 6.0000 | 4.7329 | 8.8741 | 5.1534 | 8.1500 | 1.7143 | flexible attack not accounted for.  also gets extra value vs. threatened damage that usually holds.  overall eff. 10.39 (prompt defense), 9.65 (attack once) |
| Aegis | 6GGG | 10.0000 | 11.8322 | 5.9161 | 11.8322 | 5.9161 | 0.0000 | a bit less efficient when floating green to buy it |
| Amporilla | 13RRR | 16.0000 |  |  | 16 (2), 24 (3), 32 (4) | 8 (2), 5.33 (3), 4 (4) | 8 (3), 10.66 (4) | efficient even with 3 tarsiers and at 13RRRR.  add 3 to cost if you can't spend 4 red/turn, add 6 to cost if you can't spend 3 red/turn |
| Antima Comet | 3GBR | 9.8000 |  |  | varies | varies |  | let's say each engi gets defensive value 1.25 (block on 2nd turn) and half the engis are bought a turn early.  then each engi generates 1 and this breaks even (overall eff. 8) around 9 engis and gains 1 for each additional engi |
| Apollo | 13BBB | 25.2000 |  |  | 24 (Wall), 32 (Tarsier) | 8 (Wall), 6 (Tarsier) | 6(Wall), 8(Tarsier) | actually better than indicated when sniping tarsiers, will fix later |
| Arka Sodara | 7BBR + 7A | 24.6667 | 16.5650 | 10.4236 | 48.2293 | 3.5801 |  | for alternate absorbers see other tab.  value and overall eff. assume you deny 0 absorb but get full absorb value and use it as an absorber.  even if we assume you get no absorb value and you use it as an attacker, overall eff. is still 6.17.  choosing to hold is worth ~2.97 more than choosing to attack because you get 4BV half a turn early and an additional 3BV a full turn early (can use wall and rebuy it next turn) |
| Arms Race | 8GBR | 12.0000 |  |  | 12.1429 | 6.9176 |  | overall eff. assumes engis block 2 then 2.  if engis all block in 2,3,4 turns it's 6.86,6,5.49.  first one may gain additional value with steelsplitter block. |
| Asteri Cannon | 16GGGG | 21.3333 |  |  | 25.8161 | 5.7845 | 1.5000 | a bit less efficient when floating green to buy it |
| Auric Impulse | 3E | 3.0000 |  |  | 2.8571 | 7.3500 |  |  |
| Auride Core | 1B | 2.6667 |  |  | varies | varies | varies | click twice right away (and deny absorb) is worth 2.625, click once right away only 1.5.  clicking offers fair value vs. not clicking so feel free to click whenever the 2 is put to use that turn |
| Barrier | 1G | 2.3333 | 2.3664 | 6.9021 | 2.3664 | 6.9021 | 0.0000 | doesn't give granularity!  also watch out for chill, esp. cryo ray. |
| Blood Pact | 3R | 3.0000 | 7.0993 | 2.9580 | 3.0232 | 6.9463 |  | overall eff. 12.21 (2 grimbotch attacks), 9.15 (1 attack), 6.87 (0 attacks).  slightly better if you don't still need to defend the threatened 1 attack.  for comparison, defending with a drone that would otherwise survive a long time is overall eff. 13.86 when not shutting off tech. |
| Blood Phage | 8RE | 9.0000 |  |  | 9.5000 | 6.6316 | 4.7500 | still overall eff. ~7.27 if we add one red to its cost.  click ability is a red sink that gives equal value. |
| Bloodrager | 7R + 3A | 14.0000 |  |  | 14.0000 | 7.0000 | 7.0000 | overall eff. for 2,1,0 attack is 6,5,4.  very good value for 1,0 attack even if floating a red. |
| Borehole Patroller | 6GB | 9.0000 |  |  | 9.0000 | 7.0000 | 3.5000 | gains extra value against threatened damage that usually holds. |
| Cauterizer | 11BRR | 14.6667 | 11.8322 | 8.6769 | 14.0000 | 7.3333 |  | slightly better as an attacker than defender.  gets extra value against threatened damage that usually holds.  more valuable than indicated when you're rebuying some of the engineers for defense each turn. |
| Centrifuge | 9.0000 | 9.0000 |  |  | 7.2886 | 8.6436 |  | can think of this as converting gold directly to (slightly overpriced) G/B/R |
| Centurion | 18GGBBR | 25.0000 | 18.1986 | 9.6161 | 45.9468 | 3.8088 |  | for alternate absorbers see other tab |
| Chieftain | 8GGB | 12.3333 | 11.8322 | 7.2965 | 14.2509 | 6.0581 | 0.9796 | for alternate absorbers see other tab.  almost as good as wall just as a blocker on its first turn!  slightly better (~0.09 total value) to hold first turn than to hold last turn. |
| Chrono Filter | 4.0000 | 4.0000 |  |  | 3.8889 | 7.2000 | 1.9444 | extra efficient at the cost of being awkward.  good value even if all BR is floated after the first three |
| Cluster Bolt | GGGG | 5.3333 |  |  | 5.6336 | 6.6269 |  | overall eff. ~6.81 if it doesn't cause you to buy additional defense this turn.  worse than 7.5 if you have to buy more than 1 defense.  keep in mind we ignored the cost of floating green to buy this |
| Colossus | 15GBBRR | 21.6667 | 13.5225 | 11.2159 | 26.6147 | 5.6986 | 3 (8 health), 24 (1 health) | for alternate absorbers see other tab |
| Corpus | 6RR | 14.1224 | 7.0993 | 7.8881 | 12.7843 | 7.7327 | 0.0000 | the clicks themselves have overall eff. ~6.93.  overall eff. ~9.24 without clicking.  cost shown includes clicks. |
| Cryo Ray | 1G | 2.3333 |  |  |  | #DIV/0! |  | chill will be analyzed later |
| Cynestra | 12GGGR | 17.0000 |  |  | 21.0000 | 5.6667 | 10.5000 | efficient attacker.  keep in mind cost of floating green not accounted for. |
| Deadeye Operative | 5BB | 8.3333 |  |  | 5.9321 | 9.8335 | 4.3465 | inefficient compared to drones (overall eff. 8)! |
| Defense Grid | 16BBB | 21.0000 | 11.8322 | 12.4238 | 32.1474 | 4.5727 |  | calculations assume 3 soak first turn, 4 absorb on first 6 turns, 7 soak last turn.  if only absorbing for 3,2,1,0, overall efficiences are 5.13,5.90,6.94,8.43 |
| Doomed Drone | 2E | 2.0000 | 1.6903 | 8.2825 | 2.2049 | 6.3494 | 1.5889 | still gets slightly more than 2 value if clicked all 4 times.  watch out for chill esp. cryo ray |
| Doomed Mech | 9BB | 12.3333 | 8.4515 | 10.2151 | 12.8532 | 6.7169 | 2.0711 | for alternate absorbers see other tab.  calculation assumes use as an attacker that blocks on last turn.  for use as a defender (only first one, compared to wall) overall eff. ~5.24 |
| Doomed Wall | 7B | 8.6667 | 9.4657 | 6.4091 | 12.3634 | 4.9070 | 0.0000 | for alternate absorbers see other tab |
| Drake | 12BB | 15.3333 | 1.0422 |  | 18.0000 | 5.9630 | 4.5000 | slightly less valuable when the 2 threat can be defended more efficiently (e.g. feral warden).  click ability costs 1 blastforge next turn (value 5) and gains 2 attack (value 4) assuming damage is rethreatened, so make sure it kills something more valuable than pure defense. |
| Ebb Turbine | 6B | 7.6667 |  |  | 6.2500 | 8.5867 | 1.5625 | clicking this for a drone that needed to be held gains ~0.69.  much better when clicking allows you to spend tech that would otherwise be wasted, but still seems like a bad unit to me most of the time.  may be good if going breachproof or against large amounts of chill. |
| Electrovore | 4R | 5.0000 | 3.3806 | 10.3531 | 7.0000 | 5.0000 | 3.5000 | Calculations assume you have the energy to power it and don't have to go out of your way to buy more.  If buying an engi with it is needed, overall eff. 7. |
| Endotherm Kit | 5GGGR | 27.4400 |  |  |  | #DIV/0! |  | chill will be analyzed later.  for comparison, buying the frostbites and cryos individually would cost 25.33 |
| Energy Matrix | 8BB | 11.3333 | 11.8322 | 6.7049 | 23.6643 | 3.3524 | 0.0000 | for alternate absorbers see other tab |
| Feral Warden | 5GR | 7.3333 | 7.0993 | 7.2308 | 9.0284 | 5.6858 | 2.3333 | calculations assume you block on this and rebuy wall the following turn (comparing against absorbing on wall every turn), although often with this unit in faster games you may not buy wall at all |
| Ferritin Sac | 1R | 2.0000 |  |  | 1.3605 | 10.2900 | 1.9048 |  |
| Fission Turret | 4G | 5.3333 |  |  | 6.4422 | 5.7951 |  | overall eff. 6.99 without the 3 green on the last turn |
| Flame Animus | 5B | 6.6667 |  |  | 6.7857 | 6.8772 | 4.7500 |  |
| Frost Brooder | 5RR | 7.0000 |  |  |  | #DIV/0! |  | chill will be analyzed later |
| Frostbite | 2R | 3.0000 |  |  | 4.2857 | 4.9000 |  | calculation assumes the full 3 damage must be defended, which is more true for smaller amounts of chill and/or breach-vulnerable units and/or large absorbers.  using this loses 3 attack, so equivalent value should be gained through absorb denial, lifespan units, and/or the value difference between the breach-vulnerable units that are killed compared to the equivalent amount of defense. |
| Galvani Drone | 1E | 1.0000 |  |  |  | #DIV/0! |  | analyze later |
| Gauss Charge | 1G | 2.3333 |  |  | 2.0000 | 8.1667 | 2.0000 |  |
| Gauss Fabricator | 12GGGG | 17.3333 |  |  | 16.3142 | 7.4373 | 2.0800 | doesn't pass overall eff. 8 until the last cannon has attacked twice |
| Gaussite Symbiote | 8RR | 10.0000 |  |  | 10.3333 | 6.7742 | 5.1667 | sacrificing gives up a 12-value unit and GGG (so 16 total) for 6 attack (12 value).  fine if killing something good or if unable to spend much green otherwise.  overall eff. 8.26 if bought and then sacrificed asap. |
| Grenade Mech | 10BB | 11.3333 |  |  | 13.0000 | 6.1026 | 1.7500 | click ability costs 6 and gains 6, so even value (overall eff. 8) |
| Grimbotch | 4R | 5.0000 | 3.3806 | 10.3531 | 5.8892 | 5.9431 | 2.2245 | overall eff. 7.31 if it attacks all 4 turns |
| Hannibull | 10BR | 11.6667 | 13.8322 | 5.9041 | 14.4036 | 5.6699 | 2.0000 | calculations assume use as soak, overall eff. assumes 1 threat is real.  worse if it can cost you absorb.  if trying to buy this when opponent has <7 attack, consider how much extra absorb you expect to gain and also how much absorb you expect to lose the turn it dies. |
| Hellhound | 5BR | 7.6667 |  |  | 8.6903 | 6.1755 | 7.0000 |  |
| Husk | 2R | 3.0000 | 2.3664 | 8.8741 | 2.3664 | 8.8741 | 0.0000 | overall eff. 6.93 when red would be floated |
| Iceblade Golem | 7BR | 9.6667 |  |  |  | #DIV/0! |  | analyze later |
| Immolite | 3R | 4.0000 |  |  | 4.0833 | 6.8571 | 4.0833 | sometimes can gain value by denying absorb during off turns and/or causing defense to be bought inefficently |
| Infusion Grid | 5B | 6.6667 | 6.7612 | 6.9021 | 10.9870 | 4.2474 | 0.0000 | click ability obviously good when granularity needed |
| Iso Kronus | 5G | 6.3333 |  |  | 5.8333 | 7.6000 | 1.6333 | sometimes can gain value by denying absorb during off turns and/or causing defense to be bought inefficently.  breachproof eff. assumes it's about to attack |
| Kinetic Driver | 5G | 6.3333 |  |  | 7.0132 | 6.3214 | 7.2700 | overall eff. 7.30 without the snipe.  calculation assumes sniping animus.  snipe can be much more valuable depending on how it affects opponent's turn. |
| Lancetooth | 6B + 2A | 11.6667 |  |  | 10.0000 | 8.1667 | 3.5000 | overall eff. 6.44, 5.11 for 1,0 attack |
| Lucina Spinos | 17RRRR | 21.0000 |  |  | 28.0000 | 5.2500 | 28.0000 | calculation ignores click ability.  click ability turns a drone (value 3) into either 2 defense next turn (value 3.46) or a 5-value attacker |
| Mahar Rectifier | 11GG | 13.6667 | 8.4515 | 11.3194 | 18.0268 | 5.3069 | 2.8000 | overall eff. 6.83 as an attacker |
| Manticore | 3BB | 6.3333 |  |  | 7.0000 | 6.3333 | 3.5000 | buying splitter then manticore averages to 7.0 overall eff.  click ability trades 2 attack (value 4) for 3, so only use to deny absorb (and not if losing lots of attack to deny small amounts of absorb) |
| Militia | 6B | 7.6667 |  |  | 7.0000 | 7.6667 | 1.7500 | click ability not great (trades 2 value for 1), but still a better purchase than steelsplitter when the defense won't be needed for a long time |
| Nitrocybe | 1R | 2.0000 | 1.2074 | 11.5955 | 1.9071 | 7.3411 | 2.0000 | great (overall eff. 4.28) when the red can't be spent, not terrible when the threat is real, but pretty inefficient otherwise |
| Nivo Charge | 2G | 3.3333 |  |  |  | #DIV/0! |  | chill will be analyzed later |
| Odin | 20BBB | 25.0000 | 21.9740 | 7.9640 | 39.9870 | 4.3764 |  | overall eff. 6.07 if held for soak (holding and not using for soak slightly worse) |
| Omega Splitter | 15BBB | 20.0000 |  |  | 28.8192 | 4.8579 | 3.5000 | overall eff. 6.67 after for use as an attacker |
| Ossified Drone |  |  |  |  |  | #DIV/0! |  |  |
| Oxide Mixer | 3B | 4.6667 |  |  | 3.6985 | 8.8325 | 1.5889 | pixies may gain additional value by exploiting.  also good for denying absorb early on, probably bad once you've reached the absorb threshold.  overall eff. 5.85 when blue is free. |
| Perforator | 3R | 4.0000 | 3.3806 | 8.2825 | 4.0000 | 7.0000 | 2.0000 | buying animus and then buying 2 perfs is overall eff. 7 |
| Pixie | 1B | 2.6667 |  |  | 2.0000 | 9.3333 | 2.0000 | may gain additional value by exploiting |
| Plasmafier | 12GGGB | 17.6667 |  |  | 21.7500 | 5.6858 |  |  |
| Plexo Cell | 2GG + 1D | 7.6667 | 9.4657 | 5.6696 | 9.4657 | 5.6696 | 0.0000 | aim to buy this once the opponent has (close to) 4 + absorb non-flexible attack.  watch out for chill. |
| Polywall | 10B | 11.6667 | 14.1986 | 5.7517 | 14.1986 | 5.7517 | 0.0000 | overall eff. 8.08 when 1 absorb denied |
| Protoplasm | 7GGRR | 11.6667 | 9.4657 | 8.6276 | 12.3948 | 6.5888 |  | overall eff. 6.41 when red is free |
| Redeemer | 10GB | 13.0000 |  |  | 13.7558 | 6.6154 | 5.2500 | holding first redeemer against wall and charges probably good.  better with better soak.  worse when defense has to be bought inefficiently. |
| Resophore | 1GR | 8.9637 |  | #DIV/0! |  | #DIV/0! |  |  |
| Savior |  |  |  | #DIV/0! |  | #DIV/0! |  |  |
| Scorchilla | 3GR | 5.3333 | 2.5872 | 14.4300 | 4.8165 | 7.7511 |  | holding for soak is bad, holding to absorb 2 (gets 3 defense a turn early and loses it next turn) is gaining ~0.27 in theory.  most of the value is in the first attack.  gains additional value when denying absorb. |
| Sentinel | 7GR | 9.3333 | 6.7612 | 9.6629 | 9.5988 | 6.8064 |  | overall eff. ~7.61 when blocking on first turn (instead of wall).  remember this unit is primarily defensive so 7.08 overall eff. is decent |
| Shadowfang | 8RRR | 11.0000 |  |  | 14.0000 | 5.5000 | 14.0000 |  |
| Shiver Yeti | 5R | 6.0000 | 4.7329 | 8.8741 |  | #DIV/0! |  |  |
| Shredder | 5B | 6.6667 | 6.7612 | 6.9021 | 7.3327 | 6.3642 | 1.7500 | calculations assume use as soak, overall eff. assumes threat is real.  it's a little better to hold than click, assuming you need the 4 defense this turn. |
| Steelforge |  |  |  | #DIV/0! |  | #DIV/0! |  |  |
| Synthesizer | 6B | 7.6667 |  |  | 6.6667 | 8.0500 | 1.6667 | click ability trades GGG (worth 4) for BB (worth 3.33).  overall eff. at generating blue ~9.2 (ignoring floated green), which is best use with one blastforge to get out triple blue units. |
| Tantalum Ray | 7GG | 9.6667 |  |  | 10.1778 | 6.6484 | varies |  |
| Tatsu Nullifier | 12RRRR | 16.0000 |  |  | 20.0000 | 5.6000 |  | overall eff. 8 as an attacker, calculations assume the chill threat forces out 3 defense.  does not account for denying absorb.  obviously even better vs. 4/5-health absorbers and/or defenders. |
| Tesla Coil | 11GGB | 15.3333 |  |  | 17.6903 | 6.0674 | 5.3333 | calculation assumes one of first two engis blocks, one engi is bought every turn after first.  watch out for engi supply, if this is an issue then granularity might be an issue too. |
| The Wincer | 9GBBR | 14.6667 |  |  | 15.3061 | 6.7076 |  | calculation just for first 15.  click ability overall eff. 7.11.  much better when defense can't be bought efficiently.  may gain value by denying absorb.  keep in mind the value in clicking it is mostly in forcing the opponent to buy 15 defense in 3 turns. |
| Thermite Core | 1B | 2.6667 |  |  | varies | varies | varies | click twice right away (and deny absorb) is worth 2.625, click once right away only 1.5. |
| Thorium Dynamo | 5E + 3D | 14.0000 |  |  | 11.3095 | 8.6653 | 1.9792 | note that this only costs 1 energy (energy ignored in calculations), so it's extra good in the early game when you're spending all your energy.  click ability turns GGG (value 4) into 3 gold, good for flexibility.  overall eff. would be 8.29 if you instantly turned all green into gold. |
| Thunderhead | 15GGGGGB | 23.3333 |  | #DIV/0! |  | #DIV/0! |  |  |
| Tia Thurnax | 7GGGR + 7D | 29.5000 |  | #DIV/0! | 35.5377 | 5.8107 |  | calculation assumes block on tia and rebuy wall next turn.  total value varies heavily depending on how inefficiently the opponent must defend and also a bit on how much defensive value the 4 health actually gets and when. |
| Trinity Drone | 2EG | 3.3333 |  |  | 2.5000 | 9.3333 | 1.5000 | click ability useful for flexibility, turns G (value 1.33) into 1 gold |
| Vai Mauronax | 13BRRRR | 18.6667 |  | #DIV/0! | 25.0000 | 5.2267 | 4.1667 | already overall eff. 6.22 as an attacker.  calculations assume the chill threat forces out 2 defense |
| Venge Cannon | 1GGG + 3D | 12.5000 |  |  | 14.0000 | 6.2500 | 1.5556 | in a breachproof situation click ability gains roughly 1 bv (value 2) for GGGG (value 5.33), but if you have conduits and no gold this is useful.  in non-breachproof situations click ability gains 3 attack (value 6) for the same price (5.33). |
| Vivid Drone | 2EE | 2.0000 |  |  | 2.5000 | 5.6000 | 7.5000 | engineer costs not accounted for.  very good buy when the energy would otherwise be wasted (e.g. after you would stop buying normal drones in a normal game). |
| Wild Drone |  |  |  | #DIV/0! |  | #DIV/0! |  |  |
| Xaetron | 11GGGGG | 17.6667 |  |  | 21.9740 | 5.6279 |  | overall eff. as an attacker ~7.94, ~6.12 as (slightly worse) energy matrix |
| Xeno Guardian | 5GBB | 9.6667 | 8.7612 | 7.7234 | 17.9870 | 3.7620 | 1.7500 | xeno guardians after the first are slightly more valuable used as defense right away rather than as attackers (overall eff. ~8.6), so only buy addional xenos when the defense is needed for something.  especially good at defending chill. |
| Zemora Voidbringer | 5GGG | 48.4042 |  |  | 46.6667 | 7.2606 |  |  |
| Valkyrion | 12GGBR | 17.3333 |  | #DIV/0! | 22.5779 | 5.3740 |  |  |

## Time-Series Calculations

Value accumulation over turns for various units and strategies.
Each column shows the cumulative value generated by that unit/strategy at turn N.

### Column Legend

| Col | Unit / Strategy |
|---|---|
| 0 | n Turns |
| 1 | 1 Defense in n Turns |
| 2 | 1 Defense for n Turns |
| 3 | 1 Attack in (n-1) Turns |
| 4 | 1 Attack for n Turns |
| 5 | 1 Gold for n Turns |
| 6 | Drone Blocks in n Turns |
| 7 | Steelsplitter (7.67) |
| 8 | Rhino (6) |
| 9 | Tarsier (5) |
| 10 | Arka Sodara (24.67), 7 soak first turn, deny 0 absorb, use as absorber |
| 11 | Arka Sodara (24.67), 0 soak first turn, deny 0 absorb, use as absorber |
| 12 | Arka Sodara (24.67), 7 soak first turn, deny 0 absorb, use as attacker |
| 13 | Arka Sodara (24.67), 0 soak first turn, deny 0 absorb, use as attacker |
| 14 | Arms Race (12), engis block 2 then 2 |
| 15 | Asteri Cannon (21.33) |
| 16 | Blood Pact (4) |
| 17 | Blood Pact (4), Grimbotch attacks twice |
| 18 | Blood Pact (4), Grimbotch attacks once |
| 19 | Blood Pact (4), Grimbotch never attacks |
| 20 | Borehole Patroller (6) |
| 21 | Cauterizer (14.67) |
| 22 | Cauterizer (14.67) |
| 23 | Centurion (25) |
| 24 | Chieftain (12.33), block first turn then attack |
| 25 | Chieftain (12.33), block last turn, 2 threat last turn |
| 26 | Chieftain (12.33), block last turn, 0 threat last turn |
| 27 | Colossus (21.67) |
| 28 | Corpus (8) |
| 29 | Corpus (11.75), one click |
| 30 | Corpus (14.56), two clicks |
| 31 | Deadeye Operative (7.33) |
| 32 | Defense Grid (21) |
| 33 | Doomed Mech (12.33), defender |
| 34 | Doomed Mech (12.33), attacker, hold on last turn |
| 35 | Drake (15.33) |
| 36 | Gauss Fabricator (17.33) |
| 37 | Grimbotch (5) |
| 38 | Immolite (4) |
| 39 | Iso Kronus (6.33) |
| 40 | Mahar Rectifier (13.67), absorb over wall every other turn |
| 41 | Mahar Rectifier (13.67), absorb over wall every other turn, opponent doesn't defend threatened damage |
| 42 | Odin (25), absorber |
| 43 | Odin (25), hold for soak |
| 44 | Odin (25), hold, no soak/absorb |
| 45 | Omega Splitter (20), absorber |
| 46 | Ossified Drone, click one lose one |
| 47 | Ossified Drone free red, click one lose one |
| 48 | Plasmafier (17.67) |
| 49 | Scorchilla (5.33) |
| 50 | Sentinel (9.33), block last turn |
| 51 | Sentinel (9.33), block first turn |
| 52 | Tantalum Ray (9.67) |
| 53 | Tesla Coil (15.33) |
| 54 | Valkyrion (17.33), attack every other turn with just one of them |
| 55 | Xaetron (17.67), absorb every turn |
| 56 | Xaetron (17.67), absorb every other turn |
| 57 | Xaetron (17.67), absorb every third turn |
| 58 | Xaetron (17.67), attacker |
| 59 | Xeno Guardian (9.67), absorber |
| 60 | Xeno Guardian (9.67), not absorber |
| 61 | Old Redeemer (9.33) |

### Values (Turns 0-20)

Showing first 21 rows. Full data has 999 rows (converging to steady-state values).

| Turn | 1 Defense in n Turns | 1 Defense for n Turn | 1 Attack in | 1 Attack for n Turns | 1 Gold for n Turns | Drone Blocks in n Tu | Steelsplitter | Rhino | Tarsier | Arka Sodara | Arka Sodara | Arka Sodara | Arka Sodara | Arms Race | Asteri Cannon | Blood Pact | Blood Pact | Blood Pact | Blood Pact | Borehole Patroller | Cauterizer | Cauterizer | Centurion | Chieftain | Chieftain | Chieftain | Colossus | Corpus | Corpus | Corpus | Deadeye Operative | Defense Grid | Doomed Mech | Doomed Mech | Drake | Gauss Fabricator | Grimbotch | Immolite | Iso Kronus | Mahar Rectifier | Mahar Rectifier | Odin | Odin | Odin | Omega Splitter | Ossified Drone, clic | Ossified Drone free  | Plasmafier | Scorchilla | Sentinel | Sentinel | Tantalum Ray | Tesla Coil | Valkyrion | Xaetron | Xaetron | Xaetron | Xaetron | Xeno Guardian | Xeno Guardian | Old Redeemer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 (Prompt) | 2.366 | 2.366 |  |  |  |  |  | 4.733 |  | 16.565 |  | 16.565 |  |  |  | 7.099 | 7.099 | 7.099 | 4.790 |  |  |  | 14.199 |  |  |  |  | 7.099 | 2.366 | 2.366 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 9.466 |  |  |  |  |  |  |
| 1.000 | 1.690 | 4.057 | 2.000 | 2.000 | 0.714 | 1.690 | 5.642 | 3.952 | 0.000 | 31.326 | 19.832 | 19.494 | 8.000 | 0.000 | 7.690 | 5.409 | 5.409 | 3.759 |  | 7.381 | 11.832 |  | 23.270 | 15.832 | 4.000 | 4.000 | 19.522 |  | 7.437 | 7.437 | 0.000 | 11.832 | 12.452 | 9.594 | 8.000 | 0.000 | 3.952 | 2.000 | 0.000 | 12.452 | 8.452 | 20.761 | 20.761 | 14.000 | 16.142 | -0.714 | 0.000 | 8.000 | 0.000 | 2.000 | 8.761 | 2.000 | 6.262 | 8.000 | 12.846 | 13.522 | 0.000 | 0.000 | 8.761 | 8.761 | -2.113 |
| 2.000 | 1.207 | 5.264 | 1.429 | 3.429 | 1.224 | 1.922 | 6.030 | 4.823 | 1.429 | 36.156 | 24.662 | 25.208 | 13.714 | 1.429 | 13.183 | 4.202 | 3.023 |  |  | 7.843 | 12.452 |  | 29.749 | 12.210 | 6.857 | 6.857 | 15.900 |  | 9.852 | 11.059 | 0.604 | 17.172 | 14.866 | 10.853 | 10.857 | 1.429 | 4.823 | 2.000 | 2.857 | 8.829 | 7.687 | 26.254 | 19.333 | 18.286 | 19.764 | -0.340 | 0.884 | 13.204 | 0.000 | 4.636 | 5.139 | 4.857 | 9.527 | 12.237 | 15.261 | 9.900 | 14.488 | 7.143 | 11.397 | 8.258 | 2.172 |
| 3.000 | 0.862 | 6.127 | 1.020 | 4.449 | 1.589 | 2.087 | 6.307 | 5.153 | 2.449 | 39.605 | 28.111 | 29.290 | 17.796 | 4.490 | 17.107 | 2.497 |  |  |  | 8.174 | 12.894 |  | 34.377 | 14.251 | 13.477 | 12.894 | 18.962 |  |  | 12.784 | 1.466 | 21.350 | 16.591 | 11.752 | 12.898 | 3.469 | 5.445 | 3.020 | 2.857 | 15.182 | 11.999 | 30.178 | 22.394 | 21.347 | 22.351 | -0.073 | 1.516 | 16.557 | 3.061 | 6.519 | 7.022 | 6.898 | 11.859 | 15.140 | 16.986 | 17.662 | 11.901 | 7.143 | 13.280 | 7.899 | 2.819 |
| 4.000 | 0.616 | 6.743 | 0.729 | 5.178 | 1.849 | 2.205 | 6.505 |  | 3.178 | 42.069 | 30.575 | 32.205 | 20.711 | 6.676 | 20.350 |  |  |  |  | 8.410 | 13.210 |  | 37.683 |  |  |  | 21.148 |  |  |  | 3.622 | 24.595 | 17.823 | 12.394 | 14.356 | 5.656 | 5.889 | 3.020 | 4.315 | 13.334 | 11.608 | 32.981 | 24.580 | 23.534 | 24.199 | 0.117 | 1.967 | 18.691 | 3.061 | 9.599 | 8.367 | 8.356 | 13.525 | 17.302 | 18.218 | 15.814 | 11.901 | 10.787 | 14.625 | 7.642 | 5.005 |
| 5.000 | 0.440 | 7.183 | 0.521 | 5.698 | 2.035 | 2.289 | 6.647 |  | 3.698 | 43.829 | 32.335 | 34.288 | 22.794 | 8.238 | 21.911 |  |  |  |  | 8.578 | 13.436 |  | 40.044 |  |  |  | 22.710 |  |  |  | 4.282 | 27.099 | 17.959 | 12.853 | 15.397 | 7.738 |  | 3.541 | 4.315 | 16.576 | 13.808 | 34.982 | 26.142 | 25.095 | 25.519 | 0.254 | 2.289 | 20.030 | 3.061 |  | 9.247 | 8.876 | 14.715 | 18.783 | 19.098 | 19.774 | 17.181 | 10.787 | 15.585 | 7.458 | 6.567 |
| 6.000 | 0.314 | 7.497 | 0.372 | 6.070 | 2.168 | 2.349 | 6.748 |  | 4.070 | 45.086 | 33.592 | 35.775 | 24.281 | 9.354 | 23.027 |  |  |  |  | 8.699 | 13.597 |  | 41.730 |  |  |  | 23.826 |  |  |  | 4.754 | 29.020 |  |  | 16.141 | 9.598 |  | 3.541 | 5.059 | 15.633 | 13.609 | 36.412 | 27.258 | 26.211 | 26.462 | 0.351 | 2.519 | 20.854 | 4.177 |  |  | 9.248 | 15.565 | 19.886 | 19.726 | 18.831 | 16.238 | 12.647 | 16.272 | 7.327 | 7.683 |
| 7.000 | 0.224 | 7.721 | 0.266 | 6.336 | 2.263 | 2.392 | 6.820 |  | 4.336 | 45.984 | 34.490 | 36.838 | 25.344 | 10.151 | 23.824 |  |  |  |  | 8.785 | 13.712 |  | 42.935 |  |  |  | 24.623 |  |  |  | 5.090 | 30.487 |  |  | 16.672 | 11.192 |  | 3.807 | 5.059 | 17.286 | 14.732 | 37.434 | 28.055 | 27.008 | 27.135 | 0.421 | 2.683 | 21.347 | 4.177 |  |  | 9.514 | 16.172 | 20.642 | 20.175 | 20.852 | 16.238 | 12.647 | 16.762 | 7.234 | 8.480 |
| 8.000 | 0.160 | 7.882 | 0.190 | 6.526 | 2.331 | 2.423 | 6.871 |  | 4.526 | 46.626 | 35.132 | 37.597 | 26.103 | 10.720 | 24.393 |  |  |  |  | 8.846 | 13.794 |  | 43.796 |  |  |  | 25.192 |  |  |  | 5.331 | 30.962 |  |  | 17.051 | 12.520 |  | 3.807 | 5.438 | 16.805 | 14.630 | 38.163 | 28.624 | 27.577 | 27.617 | 0.470 | 2.801 | 21.631 | 4.177 |  |  | 9.704 | 16.606 | 21.205 | 20.496 | 20.371 | 18.163 | 13.595 | 17.112 | 7.167 | 9.049 |
| 9.000 | 0.115 | 7.996 | 0.136 | 6.661 | 2.379 | 2.445 | 6.908 |  | 4.661 | 47.084 | 35.590 | 38.139 | 26.645 | 11.126 | 24.800 |  |  |  |  | 8.890 | 13.853 |  | 44.410 |  |  |  | 25.598 |  |  |  | 5.503 | 31.300 |  |  | 17.322 | 13.604 |  | 3.942 | 5.438 | 17.649 | 15.203 | 38.684 | 29.031 | 27.984 | 27.960 | 0.506 | 2.885 | 21.786 | 4.583 |  |  | 9.839 | 16.916 | 21.590 | 20.725 | 21.401 | 17.819 | 14.273 | 17.362 | 7.119 | 9.455 |
| 10.000 | 0.082 | 8.078 | 0.097 | 6.758 | 2.414 | 2.461 | 6.934 |  | 4.758 | 47.411 | 35.917 | 38.526 | 27.032 | 11.417 | 25.090 |  |  |  |  | 8.922 | 13.895 |  | 44.849 |  |  |  | 25.889 |  |  |  | 5.625 | 31.542 |  |  | 17.516 | 14.378 |  | 3.942 | 5.632 | 17.404 | 15.151 | 39.056 | 29.321 | 28.274 | 28.206 | 0.531 | 2.945 | 21.862 | 4.583 |  |  | 9.936 | 17.137 | 21.877 | 20.889 | 21.156 | 17.819 | 14.273 | 17.540 | 7.085 | 9.746 |
| 11.000 | 0.058 | 8.136 | 0.069 | 6.827 | 2.438 | 2.472 | 6.953 |  | 4.827 | 47.645 | 36.151 | 38.803 | 27.309 | 11.624 | 25.298 |  |  |  |  | 8.944 | 13.925 |  | 45.163 |  |  |  | 26.096 |  |  |  | 5.713 | 31.715 |  |  | 17.654 | 14.931 |  | 4.011 | 5.632 | 17.834 | 15.443 | 39.322 | 29.528 | 28.481 | 28.381 | 0.549 | 2.987 | 21.892 | 4.583 |  |  | 10.005 | 17.295 | 22.074 | 21.006 | 21.682 | 18.520 | 14.618 | 17.668 | 7.061 | 9.953 |
| 12.000 | 0.042 | 8.178 | 0.049 | 6.877 | 2.456 | 2.480 | 6.966 |  | 4.877 | 47.812 | 36.318 | 39.000 | 27.506 | 11.772 | 25.446 |  |  |  |  | 8.960 | 13.946 |  | 45.387 |  |  |  | 26.244 |  |  |  | 5.776 | 31.839 |  |  | 17.753 | 15.326 |  | 4.011 | 5.730 | 17.709 | 15.417 | 39.512 | 29.677 | 28.630 | 28.506 | 0.562 | 3.018 | 21.896 | 4.732 |  |  | 10.054 | 17.408 | 22.220 | 21.089 | 21.557 | 18.395 | 14.618 | 17.759 | 7.043 | 10.101 |
| 13.000 | 0.030 | 8.208 | 0.035 | 6.912 | 2.469 | 2.486 | 6.976 |  | 4.912 | 47.931 | 36.437 | 39.141 | 27.647 | 11.878 | 25.551 |  |  |  |  | 8.971 | 13.962 |  | 45.547 |  |  |  | 26.350 |  |  |  | 5.820 | 31.927 |  |  | 17.824 | 15.609 |  | 4.047 | 5.730 | 17.928 | 15.566 | 39.648 | 29.782 | 28.735 | 28.596 | 0.571 | 3.040 | 21.885 | 4.732 |  |  | 10.090 | 17.489 | 22.321 | 21.149 | 21.825 | 18.395 | 14.795 | 17.824 | 7.031 | 10.207 |
| 14.000 | 0.021 | 8.229 | 0.025 | 6.937 | 2.478 | 2.490 | 6.983 |  | 4.937 | 48.016 | 36.522 | 39.242 | 27.748 | 11.954 | 25.627 |  |  |  |  | 8.980 | 13.973 |  | 45.661 |  |  |  | 26.426 |  |  |  | 5.852 | 31.990 |  |  | 17.874 | 15.810 |  | 4.047 | 5.781 | 17.865 | 15.552 | 39.745 | 29.858 | 28.811 | 28.659 | 0.578 | 3.055 | 21.869 | 4.732 |  |  | 10.115 | 17.546 | 22.396 | 21.191 | 21.761 | 18.650 | 14.795 | 17.871 | 7.022 | 10.283 |
| 15.000 | 0.015 | 8.244 | 0.018 | 6.955 | 2.484 | 2.493 | 6.988 |  | 4.955 | 48.077 | 36.583 | 39.314 | 27.820 | 12.008 | 25.681 |  |  |  |  | 8.985 | 13.980 |  | 45.743 |  |  |  | 26.480 |  |  |  | 5.875 | 32.035 |  |  | 17.910 | 15.954 |  | 4.065 | 5.781 | 17.977 | 15.628 | 39.814 | 29.912 | 28.865 | 28.705 | 0.583 | 3.067 | 21.851 | 4.786 |  |  | 10.133 | 17.587 | 22.447 | 21.222 | 21.898 | 18.605 | 14.885 | 17.904 | 7.016 | 10.337 |
| 16.000 | 0.011 | 8.255 | 0.013 | 6.968 | 2.489 | 2.495 | 6.991 |  | 4.968 | 48.121 | 36.627 | 39.366 | 27.871 | 12.046 | 25.720 |  |  |  |  | 8.990 | 13.986 |  | 45.801 |  |  |  | 26.518 |  |  |  | 5.891 | 32.067 |  |  | 17.936 | 16.057 |  | 4.065 | 5.807 | 17.944 | 15.621 | 39.863 | 29.951 | 28.904 | 28.738 | 0.586 | 3.075 | 21.834 | 4.786 |  |  | 10.146 | 17.617 | 22.485 | 21.244 | 21.865 | 18.605 | 14.949 | 17.928 | 7.011 | 10.375 |
| 17.000 | 0.008 | 8.263 | 0.009 | 6.977 | 2.492 | 2.496 | 6.994 |  | 4.977 | 48.152 | 36.658 | 39.402 | 27.908 | 12.074 | 25.747 |  |  |  |  | 8.993 | 13.990 |  | 45.843 |  |  |  | 26.546 |  |  |  | 5.903 | 32.090 |  |  | 17.954 | 16.131 |  | 4.074 | 5.807 | 18.001 | 15.660 | 39.899 | 29.978 | 28.931 | 28.761 | 0.588 | 3.080 | 21.818 | 4.786 |  |  | 10.155 | 17.638 | 22.511 | 21.259 | 21.935 | 18.698 | 14.949 | 17.945 | 7.008 | 10.403 |
| 18.000 | 0.006 | 8.269 | 0.007 | 6.984 | 2.494 | 2.497 | 6.996 |  | 4.984 | 48.174 | 36.680 | 39.429 | 27.934 | 12.094 | 25.767 |  |  |  |  | 8.995 | 13.993 |  | 45.872 |  |  |  | 26.565 |  |  |  | 5.911 | 32.106 |  |  | 17.967 | 16.183 |  | 4.074 | 5.820 | 17.985 | 15.657 | 39.924 | 29.998 | 28.951 | 28.778 | 0.590 | 3.084 | 21.804 | 4.805 |  |  | 10.161 | 17.653 | 22.530 | 21.270 | 21.919 | 18.681 | 14.982 | 17.957 | 7.006 | 10.423 |
| 19.000 | 0.004 | 8.273 | 0.005 | 6.988 | 2.496 | 2.498 | 6.997 |  | 4.988 | 48.190 | 36.696 | 39.447 | 27.953 | 12.108 | 25.781 |  |  |  |  | 8.996 | 13.995 |  | 45.894 |  |  |  | 26.580 |  |  |  | 5.917 | 32.118 |  |  | 17.977 | 16.220 |  | 4.078 | 5.820 | 18.014 | 15.677 | 39.942 | 30.012 | 28.965 | 28.789 | 0.591 | 3.087 | 21.793 | 4.805 |  |  | 10.166 | 17.664 | 22.544 | 21.278 | 21.954 | 18.681 | 14.982 | 17.965 | 7.004 | 10.437 |
| 20.000 | 0.003 | 8.275 | 0.003 | 6.992 | 2.497 | 2.499 | 6.998 |  | 4.992 | 48.201 | 36.707 | 39.461 | 27.967 | 12.118 | 25.791 |  |  |  |  | 8.997 | 13.996 |  | 45.909 |  |  |  | 26.590 |  |  |  | 5.921 | 32.127 |  |  | 17.983 | 16.247 |  | 4.078 | 5.826 | 18.005 | 15.675 | 39.955 | 30.022 | 28.975 | 28.798 | 0.592 | 3.089 | 21.784 | 4.805 |  |  | 10.169 | 17.671 | 22.554 | 21.284 | 21.946 | 18.715 | 14.999 | 17.972 | 7.003 | 10.447 |

### Steady-State Values (Turn 999)

| Unit | Value at Turn 999 |
|---|---|
| n Turns | 998.0000 |
| 1 Defense in n Turns | 0.0000 |
| 1 Defense for n Turns | 8.2825 |
| 1 Attack in (n-1) Turns | 0.0000 |
| 1 Attack for n Turns | 7.0000 |
| 1 Gold for n Turns | 2.5000 |
| Drone Blocks in n Turns | 2.5000 |
| Steelsplitter (7.67) | 7.0000 |
| Tarsier (5) | 5.0000 |
| Arka Sodara (24.67), 7 soak first turn, deny 0 absorb, use as absorber | 48.2293 |
| Arka Sodara (24.67), 0 soak first turn, deny 0 absorb, use as absorber | 36.7352 |
| Arka Sodara (24.67), 7 soak first turn, deny 0 absorb, use as attacker | 39.4941 |
| Arka Sodara (24.67), 0 soak first turn, deny 0 absorb, use as attacker | 28.0000 |
| Arms Race (12), engis block 2 then 2 | 12.1429 |
| Asteri Cannon (21.33) | 25.8161 |
| Borehole Patroller (6) | 9.0000 |
| Cauterizer (14.67) | 14.0000 |
| Centurion (25) | 45.9468 |
| Colossus (21.67) | 26.6147 |
| Deadeye Operative (7.33) | 5.9321 |
| Defense Grid (21) | 32.1474 |
| Drake (15.33) | 18.0000 |
| Gauss Fabricator (17.33) | 16.3142 |
| Immolite (4) | 4.0833 |
| Iso Kronus (6.33) | 5.8333 |
| Mahar Rectifier (13.67), absorb over wall every other turn | 18.0268 |
| Mahar Rectifier (13.67), absorb over wall every other turn, opponent doesn't defend threatened damage | 15.6935 |
| Odin (25), absorber | 39.9870 |
| Odin (25), hold for soak | 30.0469 |
| Odin (25), hold, no soak/absorb | 29.0000 |
| Omega Splitter (20), absorber | 28.8192 |
| Ossified Drone, click one lose one | 0.5944 |
| Ossified Drone free red, click one lose one | 3.0944 |
| Plasmafier (17.67) | 21.7500 |
| Scorchilla (5.33) | 4.8165 |
| Tantalum Ray (9.67) | 10.1778 |
| Tesla Coil (15.33) | 17.6903 |
| Valkyrion (17.33), attack every other turn with just one of them | 22.5779 |
| Xaetron (17.67), absorb every turn | 21.2979 |
| Xaetron (17.67), absorb every other turn | 21.9740 |
| Xaetron (17.67), absorb every third turn | 18.7252 |
| Xaetron (17.67), attacker | 15.0200 |
| Xeno Guardian (9.67), absorber | 17.9870 |
| Xeno Guardian (9.67), not absorber | 7.0000 |
| Old Redeemer (9.33) | 10.4718 |
