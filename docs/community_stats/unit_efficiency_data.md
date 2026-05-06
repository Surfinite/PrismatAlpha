# Prismata Unit Efficiency Data

Community-sourced unit efficiency calculations from Google Sheets.
Efficiency (Eff) = (Benefit - Cost) / Cost. Diff = Benefit - Cost.
Cost and Benefit are in gold-equivalent units using the constants below.

## Constants

The highlighted values are "primitive" values used in formulas throughout.

### Primitive Values

| Parameter | Symbol | Value |
|---|---|---|
| Interest rate | i | 0.38 |
| Prompt soak | b | 2.40 |
| Green | cG | 1.33 |
| Blue | cB | 1.67 |
| Red | cR | 1.00 |
| Energy | e | 0.00 |

### Derived Values

| Parameter | Value |
|---|---|
| Discount | 0.28 |
| One-turn decay (t) | 0.72 |
| Half-turn decay | 0.85 |
| Forever (f) | 3.63 |
| Non-prompt soak | 1.74 |
| One-time attack | 2.04 |
| Permanent attack | 7.42 |

## Attackers

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Tarsier | 8% | 0.38 | 5.00 | 5.38 |  |
| Gauss Cannon | 1% | 0.09 | 7.33 | 7.42 |  |
| Steelsplitter | -3% | -0.25 | 7.67 | 7.42 |  |
| Immolite | 8% | 0.30 | 4.00 | 4.30 |  |
| Perforator | 20% | 0.79 | 4.00 | 4.79 | Always click |
| Electrovore | 0% | 0.02 | 5.00 | 5.02 | Commit existing Engineer |
| Electrovore* | 19% | 0.97 | 5.00 | 5.97 | Build Engineer to soak and power it every turn |
| Scorchilla | -3% | -0.14 | 5.33 | 5.20 | Always attack |
| Iso Kronus | -2% | -0.10 | 6.33 | 6.23 |  |
| Flame Animus | 9% | 0.62 | 6.67 | 7.28 |  |
| Blood Phage | 4% | 0.28 | 7.00 | 7.28 | Ignoring click ability |
| Tyranno Smorcus | 37% | 2.58 | 7.00 | 9.58 | Always click; assuming you've already built the Animus for it |
| Feral Warden | 1% | 0.09 | 7.33 | 7.42 | Ignoring absorb |
| Militia | 2% | 0.12 | 7.30 | 7.42 | Ignoring click ability |
| Hellhound | 19% | 1.49 | 7.67 | 9.16 |  |
| Urban Sentry | -7% | -0.58 | 8.00 | 7.42 | Ignoring absorb |
| Borehole Patroller | 5% | 0.46 | 9.00 | 9.46 |  |
| Zemora Voidbringer | 16% | 1.46 | 9.00 | 10.46 |  |
| Tantalum Ray | 11% | 1.08 | 9.67 | 10.75 |  |
| Xeno Guardian | -23% | -2.25 | 9.67 | 7.42 | Ignoring absorb |
| Gaussian Symbiote | 9% | 0.93 | 10.00 | 10.93 | Ignoring click ability |
| Shadowfang | 35% | 3.84 | 11.00 | 14.84 |  |
| Arms Race | 0% | 0.04 | 12.00 | 12.04 | Opp soaks Engineers ASAP; ignoring energy |
| Arms Race+ | 19% | 2.29 | 12.00 | 14.29 | Opp soaks Engineers after a one-turn delay; ignoring energy |
| Hannibull | 17% | 2.17 | 12.67 | 14.84 | Always attack |
| Mahar Rectifier | 9% | 1.17 | 13.67 | 14.84 | Always attack |
| Redeemer | 13% | 1.70 | 13.00 | 14.70 |  |
| Grenade Mech | 2% | 0.22 | 13.33 | 13.55 | Ignoring click ability |
| Venge Cannon | 15% | 1.94 | 12.89 | 14.84 | Ignoring click ability |
| The Wincer | 22% | 3.23 | 14.67 | 17.89 | Always click; ignoring Drone supply limitation |
| The Wincer* | 10% | 1.43 | 14.67 | 16.09 | Never click it; assume opponent defends for all 15 threat with soak |
| Cauterizer | 1% | 0.17 | 14.67 | 14.84 | As pure attacker, committing the Engineers without replacing them |
| Cauterizer* | 30% | 4.38 | 14.67 | 19.05 | As pure attacker, soaking and replacing all 4 Engineers every turn |
| Tesla Coil | 27% | 4.09 | 15.33 | 19.42 | Ignoring energy |
| Cynestra | 31% | 5.26 | 17.00 | 22.26 |  |
| Gauss Fabricator | 4% | 0.71 | 17.33 | 18.04 |  |
| Valkyrion | 9% | 1.59 | 17.33 | 18.92 | Always attack |
| Plasmafier | 29% | 5.09 | 17.67 | 22.75 | Always attack |
| Omega Splitter | 11% | 2.26 | 20.00 | 22.26 | Always attack |
| Asteri Cannon | 28% | 5.98 | 21.33 | 27.31 | Click every turn |
| Lucina Spinos | 41% | 8.68 | 21.00 | 29.68 | Ignoring click ability |
| Rhino | -11% | -0.65 | 6.00 | 5.35 | Soak when empty |
| Nitrocybe | -26% | -0.52 | 2.00 | 1.48 | Click to attack rather than soak |
| Gauss Charge | -12% | -0.29 | 2.33 | 2.04 |  |
| Pixie | -23% | -0.62 | 2.67 | 2.04 | Click immediately |
| Oxide Mixer | -17% | -0.77 | 4.67 | 3.89 |  |
| Grimbotch | 18% | 0.92 | 5.00 | 5.92 | Soak one 1 lifespan; ignoring its threat there |
| Grimbotch+ | 23% | 1.13 | 5.00 | 6.13 | Soak one 1 lifespan; counting its full 1 threat there |
| Fission Turret | 11% | 0.60 | 5.33 | 5.94 | Don't harvest |
| Fission Turret+ | 26% | 1.40 | 5.33 | 6.74 | Harvest on 1 lifespan |
| Cluster Bolt | 8% | 0.44 | 5.33 | 5.77 |  |
| Kinetic Driver | 0% | 0.01 | 6.33 | 6.35 | Don't shoot |
| Kinetic Driver+ | 10% | 0.62 | 6.33 | 6.95 | Shoot Animus on 1 lifespan |
| Chieftain 2 | 9% | 1.11 | 12.33 | 13.44 | Soak on 1 lifespan; ignoring threat |
| Chieftain 2+ | 11% | 1.40 | 12.33 | 13.73 | Soak on 1 lifespan; counting 1 threat on dying turn |
| Chieftain 2++ | 14% | 1.70 | 12.33 | 14.03 | Soak on 1 lifespan; counting all 2 threat on dying turn |
| Bombarder | 15% | 1.89 | 12.33 | 14.22 | Always attack; soak when empty |
| Tia Thurnax | 14% | 4.40 | 30.42 | 34.82 | Assuming no absorb on it; soak after |
| Mega Drone | -20% | -2.65 | 13.17 | 10.53 | Deny 0 absorb |
| Mega Drone+ | -5% | -0.60 | 11.13 | 10.53 | Deny 1 absorb |
| Mega Drone++ | 16% | 1.44 | 9.09 | 10.53 | Deny 2 absorb |
| Mega Drone+++ | 49% | 3.48 | 7.04 | 10.53 | Deny 3 absorb |
| Mega Drone++++ | 111% | 5.53 | 5.00 | 10.53 | Deny 4 absorb |
| Bloodrager | 5% | 0.71 | 14.13 | 14.84 | Deny 0 absorb |
| Bloodrager+ | 23% | 2.75 | 12.09 | 14.84 | Deny 1 absorb |
| Bloodrager++ | 48% | 4.80 | 10.04 | 14.84 | Deny 2 absorb |
| Bloodrager+++ | 85% | 6.84 | 8.00 | 14.84 | Deny 3 absorb |
| Lancetooth | -9% | -1.00 | 11.75 | 10.75 | Deny 0 absorb |
| Lancetooth+ | 11% | 1.04 | 9.71 | 10.75 | Deny 1 absorb |
| Lancetooth++ | 40% | 3.09 | 7.67 | 10.75 | Deny 2 absorb |

## Economy

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Drone | -12% | -0.37 | 3.00 | 2.63 |  |
| Doomed Drone | -5% | -0.09 | 2.00 | 1.91 | Don't soak |
| Doomed Drone+ | 15% | 0.29 | 2.00 | 2.29 | Soak on 1 lifespan |
| Wild Drone | -5% | -0.09 | 2.00 | 1.91 |  |
| Auric Impulse | -3% | -0.10 | 3.00 | 2.90 |  |
| Deadeye | -24% | -1.97 | 8.33 | 6.36 | Soak right after used up |
| Thorium Dynamo | -6% | -0.82 | 12.89 | 12.08 |  |
| Conduit | -12% | -0.49 | 4.00 | 3.51 |  |
| Blastforge | -12% | -0.61 | 5.00 | 4.39 |  |
| Animus | -12% | -0.74 | 6.00 | 5.26 |  |
| Ferritin Sac | -30% | -0.60 | 2.00 | 1.40 |  |
| Mobile Animus | -34% | -1.37 | 4.00 | 2.63 | Ignoring click ability |
| Mobile Animus 1 | -21% | -0.85 | 4.00 | 3.15 | Click for Rhino after 1 turn, which fully attacks then soaks |
| Steelforge | 10% | 0.39 | 4.00 | 4.39 | Ignoring click ability |
| Chrono Filter | 2% | 0.07 | 4.00 | 4.07 |  |
| Centrifuge | -16% | -0.81 | 5.00 | 4.19 |  |
| Synthesizer | -8% | -0.65 | 7.67 | 7.02 |  |
| Apollo | -8% | -1.38 | 18.00 | 16.62 | Shooting Tarsiers; ignoring threat |
| Apollo* | 10% | 1.84 | 18.00 | 19.84 | Shooting Tarsiers; counting all 3 threat |

## Soak / Defense

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Wall | 8% | 0.53 | 6.67 | 7.20 |  |
| Forcefield | -3% | -0.16 | 4.96 | 4.80 |  |
| Rhino | -20% | -1.20 | 6.00 | 4.80 | Soak immediately |
| Rhino+ | -11% | -0.64 | 6.00 | 5.36 | Soak immediately; count 1 threat of you absorbing on it |
| Barrier | 3% | 0.07 | 2.33 | 2.40 |  |
| Husk | -20% | -0.60 | 3.00 | 2.40 |  |
| Blood Pact | -26% | -1.03 | 4.00 | 2.97 | Opp soaks Grimbotch at end; you fully defends its 1 threat |
| Photonic Fibroid | -10% | -0.53 | 5.33 | 4.80 | Ignoring threat |
| Photonic Fibroid+ | 1% | 0.03 | 5.33 | 5.36 | Soak; counting 1 threat |
| Photonic Fibroid++ | 11% | 0.59 | 5.33 | 5.93 | Soak; counting all 2 threat |
| Innervi Field 0 | 8% | 0.53 | 6.67 | 7.20 | Soak immediately |
| Innervi Field 1 | 4% | 0.29 | 6.67 | 6.96 | Soak in 1 turn |
| Innervi Field 2 | -5% | -0.37 | 6.67 | 6.30 | Soak in 2 turns |
| Feral Warden | -2% | -0.13 | 7.33 | 7.20 | Ignoring threat or absorb |
| Plexo Cell | 32% | 2.30 | 7.30 | 9.60 |  |
| Corpus 0 | -10% | -0.80 | 8.00 | 7.20 | Soak immediately |
| Corpus 2 | -13% | -1.02 | 8.00 | 6.98 | Full clicks, then soak |
| Doomed Wall | 11% | 0.93 | 8.67 | 9.60 |  |
| Aegis | 20% | 2.00 | 10.00 | 12.00 |  |
| Energy Matrix | 6% | 0.67 | 11.33 | 12.00 |  |
| Polywall | 23% | 2.73 | 11.67 | 14.40 |  |
| Protoplasm | -18% | -2.07 | 11.67 | 9.60 | Soak immediately; ignoring threat |
| Protoplasm++++ | 2% | 0.18 | 11.67 | 11.85 | Soak immediately; counting all 4 threat |
| Engineer | -13% | -0.26 | 2.00 | 1.74 |  |
| Nitrocybe | -37% | -0.74 | 2.00 | 1.26 | Hold and soak; ignoring threat |
| Nitrocybe+ | -17% | -0.33 | 2.00 | 1.67 | Hold and soak; counting all 1 threat |
| Infusion Grid | 4% | 0.29 | 6.67 | 6.96 |  |
| Shredder | 4% | 0.29 | 6.67 | 6.96 | Ignoring threat |
| Shredder+ | 13% | 0.85 | 6.67 | 7.52 | Hold and soak; counting 1 full threat |
| Sentinel | 13% | 1.08 | 8.33 | 9.42 | Click all the way then soak |
| Xeno Guardian | -7% | -0.67 | 9.67 | 9.00 | Soak next turn |
| Chieftain 0 | -1% | -0.16 | 12.33 | 12.17 | Soak immediately; ignoring threat |
| Chieftain 1 | 5% | 0.57 | 12.33 | 12.91 | Soak in 1 turn; ignoring threat |
| Chieftain 2 | 9% | 1.11 | 12.33 | 13.44 | Soak in 2 turns; ignoring threat |
| Chieftain 2+ | 11% | 1.40 | 12.33 | 13.73 | Soak on 1 lifespan; counting 1 threat on dying turn |
| Chieftain 2++ | 14% | 1.70 | 12.33 | 14.03 | Soak on 1 lifespan; counting all 2 threat on dying turn |
| Hannibull | 12% | 1.55 | 12.67 | 14.22 | Hold and soak; ignoring threat |
| Hannibull+ | 17% | 2.11 | 12.67 | 14.78 | Hold and soak; counting 1 threat in addition to its 1 attack |
| Cauterizer | -17% | -2.49 | 14.67 | 12.17 | Soak it and Engineers immediately; ignoring threat |
| Cauterizer+ | -13% | -1.93 | 14.67 | 12.74 | Soak it and Engineers immediately; counting 1 threat |
| Cauterizer++ | -9% | -1.37 | 14.67 | 13.30 | Soak it and Engineers immediately; counting all 2 threat |

## Absorb

Note: This sheet contains #REF! errors (broken cross-sheet references in exported HTML).

| Unit | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|
| Centurion | #REF! | 25.00 | #REF! |  |
| Energy Matrix | #REF! | 11.33 | #REF! |  |
| Feral Warden | #REF! | 26.63 | #REF! | Rebuy every turn |
| Xeno Guardian | #REF! | 9.67 | #REF! |  |
| Doomed Wall | #REF! | 18.25 | #REF! | Soak when dying, rebuy |
| Xaetron | #REF! | 17.67 | #REF! | No juggling |
| Mahar Rectifier | #REF! | 23.57 | #REF! | Pair; ignoring threat |
| Infusion Grid | #REF! | 6.67 | #REF! |  |
| Urban Sentry | #REF! | 8.00 | #REF! |  |
| Omega Splitter | #REF! | 20.00 | #REF! | Ignoring threat |
| Protoplasm | #REF! | 42.37 | #REF! | Rebuy every turn |
| Doomed Mech | #REF! | 17.03 | #REF! | Soak when dying and rebuy; ignoring threat |
| Wall | #REF! | 6.67 | #REF! |  |

## Click Abilities

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Trinity Drone | -25% | -0.33 | 1.33 | 1.00 | Thorium Dynamo click is 3 times this |
| Auride Core | -2% | -0.04 | 2.04 | 2.00 | Assuming no absorb denied and extra damage only kills opponent's soak |
| Tyranno Smorcus | 2% | 0.04 | 2.00 | 2.04 | Assuming extra damage only kills defense |
| Ebb Turbine | 14% | 0.37 | 2.63 | 3.00 |  |
| Ossified Drone | 20% | 0.57 | 2.91 | 3.48 | Soak the created Ossified Drone next turn; ignoring potential value of soaking the clicked Ossified Drone now |
| Manticore | -27% | -1.09 | 4.09 | 3.00 | Assuming no absorb denied and extra damage would only kill opponent's soak |
| Lucina Spinos | 32% | 1.16 | 3.63 | 4.79 | Assuming Perforator are always clicked |
| Synthesizer | -17% | -0.67 | 4.00 | 3.33 |  |
| Drake | -7% | -0.30 | 4.39 | 4.09 | Assuming extra damage only kills opponent's soak |
| Mobile Animus | 16% | 0.72 | 4.63 | 5.35 | Rhino clicks through then soaks |
| Venge Cannon | 15% | 0.80 | 5.33 | 6.13 | Ignoring value of Venge Cannon health |
| Grenade Mech | 14% | 0.74 | 5.39 | 6.13 |  |
| Steelforge | 7% | 0.45 | 6.96 | 7.42 | Valuing Steelsplitter as pure attacker |
| Odin | 10% | 0.75 | 7.42 | 8.17 | Assuming extra damage only kills opponent's soak; ignoring Odin absorb/soak |
| Corpus | 9% | 0.88 | 9.80 | 10.68 | Click and soak it next turn compared to soaking it now |
| Gaussian Symbiote | -18% | -2.67 | 14.93 | 12.26 |  |

## Holds

### Hold for soak

Value of holding the unit to be soak, without losing absorb. Assuming that clicking it would only kill opponent's soak, that is, opponent has defended fully.

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Drone hold | -34% | -1.23 | 3.63 | 2.40 |  |
| Drone hold (2 defense) | 32% | 1.17 | 3.63 | 4.80 | If you'd be exploited for 1 damage otherwise at no cost to opponent |
| Splitter hold | -24% | -2.26 | 9.46 | 7.20 | Assuming you'd keep attacking with it otherwise |
| Shredder hold | 1% | 0.14 | 9.46 | 9.60 | Assuming you'd keep attacking with it otherwise, and opponent wouldn't click it |
| Hannibull hold | 0% | -0.08 | 16.88 | 16.80 | Assuming you'd keep attacking with it otherwise, and opponent wouldn't click it |
| Perforator hold | -18% | -1.03 | 5.83 | 4.80 | Assuming you'd keep attacking with it otherwise |

### Soak without holding

Letting the unit die as soak rather than overdefending it. Value as of the turn you'd otherwise build prompt soak to defend it.

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Soak Ossified Drone | 82% | 2.17 | 2.63 | 4.80 |  |
| Soak Xeno Guardian | 29% | 2.18 | 7.42 | 9.60 |  |
| Soak Urban Sentry | -3% | -0.22 | 7.42 | 7.20 |  |
| Soak Borehole Patroller | -35% | -2.62 | 7.42 | 4.80 |  |
| Drone breached | -9% | -0.23 | 2.63 | 2.40 | Ignoring the absorb loss happening from this breach |

### Default absorber: Wall

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Steelsplitter hold | -3% | -0.06 | 2.04 | 1.98 | Full-health Feral Warden is the same, ignoring future value of its health |
| Scorchilla hold | 39% | 0.55 | 1.43 | 1.98 | Assuming holding doesn't deny opponent absorb; ignoring future value of Scorchilla health |
| Redeemer hold | -28% | -1.75 | 6.13 | 4.38 |  |
| Plasmafier hold | -21% | -1.16 | 5.54 | 4.38 | Ignoring future value of Plasmafier health |
| Lancetooth hold | 7% | 0.30 | 4.09 | 4.38 |  |
| Mega Drone hold | 10% | 0.38 | 4.00 | 4.38 |  |
| Doomed Mech hold | 66% | 2.70 | 4.09 | 6.78 | Mahar Rectifier is the same, ignoring the value of its health while regenerating |
| Chieftain hold lifespan 3 | 20% | 0.82 | 4.09 | 4.91 | Assume the Chieftain would also have full threat on last lifespan if it survived |
| Omega Splitter hold | 50% | 3.05 | 6.13 | 9.18 |  |
| Arka Sodara hold | 42% | 3.41 | 8.17 | 11.58 |  |
| Colossus hold | 128% | 7.85 | 6.13 | 13.98 | Ignoring future value of Colossus health |

### Default absorber: Infusion Grid

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Lancetooth hold | -35% | -1.44 | 4.09 | 2.64 |  |
| Mega Drone hold | -34% | -1.36 | 4.00 | 2.64 |  |
| Doomed Mech hold | 23% | 0.96 | 4.09 | 5.04 | Mahar Rectifier is the same, ignoring the value of its health while regenerating |
| Chieftain hold lifespan 3 | -22% | -0.92 | 4.09 | 3.17 | Assume the Chieftain would also have full threat on last lifespan if it survived |
| Omega Splitter hold | 21% | 1.31 | 6.13 | 7.44 |  |
| Arka Sodara hold | 20% | 1.67 | 8.17 | 9.84 |  |
| Colossus hold | 100% | 6.11 | 6.13 | 12.24 | Ignoring future value of Colossus health |

### Default absorber: Energy Matrix

| Unit | Eff | Diff | Cost | Benefit | Notes |
|---|---|---|---|---|---|
| Doomed Mech hold | -19% | -0.78 | 4.09 | 3.30 | Mahar Rectifier is the same, ignoring the value of its health while regenerating |
| Omega Splitter hold | -7% | -0.42 | 6.13 | 5.70 |  |
| Arka Sodara hold | -1% | -0.07 | 8.17 | 8.10 |  |
| Colossus hold | 71% | 4.38 | 6.13 | 10.50 | Ignoring future value of Colossus health |
