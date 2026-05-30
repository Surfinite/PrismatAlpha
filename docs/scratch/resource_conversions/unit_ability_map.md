# Per-unit ability / production / cost map

All names are player-visible (UIName). Resource codes: gold (bare digits) / grn / blu / red / nrg / atk. A bare-integer `receive` = gold. Buy-cost and click-cost are separate columns.

| unit | cat | auto/turn | click->produces | click->creates | click cost | chill | destroy | hp regen | buy cost | chg | life | needs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Asteri Cannon | CREATE | atk3 | - | Barrierx1 | hp3 |  |  |  | gold16 grn4 |  |  | Barrier |
| Corpus | CREATE | - | - | Huskx3 | gold4 red1 |  |  |  | gold6 red2 | 2 |  | Husk |
| Defense Grid | CREATE | - | - | Dronex1 | - |  |  |  | gold16 blu3 |  | 7 | Drone |
| Frost Brooder | CREATE | - | - | Frostbitex1 | - |  |  |  | gold5 red2 |  | 6 | Frostbite |
| Gauss Fabricator | CREATE | - | - | Gauss Cannonx1 | - |  |  |  | gold12 grn4 |  | 8 | Gauss Cannon |
| Gaussite Symbiote | CREATE | grn1 atk1 | - | Gauss Chargex6 | grn3 sacSELF |  |  |  | gold8 red2 |  |  | Gauss Charge |
| Grenade Mech | CREATE | atk1 | - | Pixiex3 | gold1 sac:Blastforgex1 |  |  |  | gold10 blu2 |  |  | Pixie,Blastforge |
| Infusion Grid | CREATE | - | - | Huskx4 | red1 sacSELF |  |  |  | gold5 blu1 |  |  | Husk |
| Lucina Spinos | CREATE | atk4 | - | Perforatorx1 | red1 sac:Dronex1 |  |  |  | gold17 red4 |  |  | Perforator,Drone |
| Mobile Animus | CREATE | red1 | - | Rhinox1 | gold2 sacSELF |  |  |  | gold4 |  |  | Rhino |
| Ossified Drone | CREATE | gold1 | - | Ossified Dronex1 | red1 sac:Dronex1 |  |  |  | gold2 red1 sac:Dronex1 |  |  | Drone |
| Oxide Mixer | CREATE | - | - | Pixiex1 | - |  |  |  | gold3 blu1 |  | 4 | Pixie |
| Savior | CREATE | - | - | Plasmafierx1 | sac:Dronex1 |  |  |  | gold6 sac:Dronex6 |  |  | Plasmafier,Drone |
| Sentinel | CREATE | - | atk1 | Engineerx1 | - |  |  |  | gold6 grn1 red1 | 3 |  | Engineer |
| Steelforge | CREATE | blu2 | - | Steelsplitterx1 | gold1 blu2 sac:Dronex1 |  |  |  | gold4 sac:Blastforgex1 |  |  | Blastforge,Drone,Steelsplitter |
| Tantalum Ray | CREATE | atk1 | - | Gauss Chargex1 | hp3 |  |  |  | gold7 grn2 |  |  | Gauss Charge |
| Thermite Core | CREATE | - | - | Pixiex2 | atk2 |  |  |  | gold1 blu1 |  | 5 | Pixie |
| Valkyrion | CREATE | - | atk4 | Barrierx2->OPP | - |  |  |  | gold12 grn2 blu1 red1 |  |  | Barrier |
| Venge Cannon | CREATE | atk2 | - | Gauss Chargex3 | grn4 hp2 |  |  |  | gold1 grn3 sac:Dronex3 |  |  | Gauss Charge,Drone |
| Xaetron | CREATE | - | - | Gauss Chargex5 | hp7 |  |  | +4/12 | gold11 grn5 |  |  | Gauss Charge |
| Cryo Ray | CHILL | - | - | - | hp1 | 1 |  |  | gold1 grn1 |  |  |  |
| Frostbite | CHILL | - | - | - | sacSELF | 3 |  |  | gold2 red1 |  |  |  |
| Iceblade Golem | CHILL | atk1 | - | - | - | 2 |  |  | gold7 blu1 red1 |  |  |  |
| Nivo Charge | CHILL | - | - | - | sacSELF | 5 |  |  | gold2 grn1 |  | 1 |  |
| Shiver Yeti | CHILL | - | - | - | - | 2 |  |  | gold5 red1 |  |  |  |
| Tatsu Nullifier | CHILL | atk2 | - | - | - | 5 |  |  | gold12 red4 |  |  |  |
| Vai Mauronax | CHILL | atk3 | - | - | atk1 | 7 |  |  | gold13 blu1 red4 |  |  |  |
| Apollo | DESTROY | - | - | - | - |  | snipe |  | gold13 blu3 |  |  |  |
| Deadeye Operative | DESTROY | - | - | - | - |  | netherfy |  | gold5 blu2 | 3 |  | Drone |
| Kinetic Driver | DESTROY | atk1 | - | - | gold2 sacSELF |  | snipe |  | gold5 grn1 |  | 6 |  |
| Animus | ECON | red2 | - | - | - |  |  |  | gold6 |  |  |  |
| Auric Impulse | ECON | gold4 | - | - | - |  |  |  | gold3 nrg1 |  |  |  |
| Auride Core | ECON | - | gold2 | - | atk1 |  |  |  | gold1 blu1 |  |  |  |
| Blastforge | ECON | blu1 | - | - | - |  |  |  | gold5 |  |  |  |
| Blood Phage | ECON | gold1 atk1 | gold1 | - | red1 |  |  |  | gold6 red1 nrg1 |  |  |  |
| Centrifuge | ECON | gold3 grn2 blu2 red2 | - | - | - |  |  |  | gold5 |  |  |  |
| Chrono Filter | ECON | blu1 red1 | - | - | - |  |  |  | gold4 |  |  |  |
| Conduit | ECON | grn1 | - | - | - |  |  |  | gold4 |  |  |  |
| Doomed Drone | ECON | - | gold1 | - | - |  |  |  | gold2 nrg1 |  | 4 |  |
| Drone | ECON | - | gold1 | - | - |  |  |  | gold3 nrg1 |  |  |  |
| Ebb Turbine | ECON | gold2 | gold3 nrg1 | - | sac:Dronex1 |  |  |  | gold6 blu1 nrg1 |  |  | Drone |
| Engineer | ECON | nrg1 | - | - | - |  |  |  | gold2 |  |  |  |
| Ferritin Sac | ECON | - | gold1 blu1 | - | sacSELF |  |  |  | gold1 red1 |  |  |  |
| Fission Turret | ECON | atk1 | grn3 | - | nrg3 sacSELF |  |  |  | gold4 grn1 |  | 5 |  |
| Flame Animus | ECON | red1 atk1 | - | - | - |  |  |  | gold5 blu1 |  |  |  |
| Galvani Drone | ECON | - | gold1 | - | nrg1 |  |  |  | gold1 nrg1 |  |  |  |
| Manticore | ECON | atk2 | gold3 | - | atk2 |  |  |  | gold3 blu2 sac:Steelsplitterx1 |  |  | Steelsplitter |
| Mega Drone | ECON | - | gold4 | - | - |  |  |  | gold5 nrg3 atk4 |  |  |  |
| Militia | ECON | atk1 | gold1 | - | atk1 |  |  |  | gold3 blu1 sac:Dronex1 |  |  | Drone |
| Synthesizer | ECON | grn2 | blu2 | - | grn3 |  |  |  | gold6 blu1 |  |  |  |
| Thorium Dynamo | ECON | gold5 grn1 | gold3 | - | grn3 |  |  |  | gold5 nrg1 sac:Dronex3 |  |  | Drone |
| Trinity Drone | ECON | gold3 | gold1 | - | grn1 |  |  |  | gold2 grn1 nrg1 sac:Dronex2 |  |  | Drone |
| Vivid Drone | ECON | gold3 | - | - | - |  |  |  | gold2 nrg2 sac:Dronex2 |  |  | Drone |
| Wild Drone | ECON | gold1 | - | - | - |  |  |  | gold2 nrg1 |  |  |  |
| Zemora Voidbringer | ECON | - | gold8 atk8 | - | grn8 |  |  |  | gold5 grn3 |  |  |  |
| Arka Sodara | attack | - | atk4 | - | - |  |  |  | gold7 blu2 red1 atk7 |  |  |  |
| Bloodrager | attack | atk2 | - | - | - |  |  |  | gold7 red1 atk3 |  |  |  |
| Bombarder | attack | - | atk3 | - | - |  |  |  | gold8 blu2 red1 | 2 |  |  |
| Borehole Patroller | attack | atk1 | - | - | - |  |  |  | gold6 grn1 blu1 |  |  | Pixie |
| Cauterizer | attack | - | atk2 | - | nrg4 |  |  |  | gold11 blu1 red2 |  |  | Engineer |
| Centurion | attack | atk2 | - | - | - |  |  |  | gold18 grn2 blu2 red1 |  |  |  |
| Chieftain | attack | - | atk2 | - | - |  |  |  | gold8 grn2 blu1 |  | 3 |  |
| Colossus | attack | - | atk3 | - | - |  |  |  | gold15 grn1 blu2 red2 |  |  |  |
| Cynestra | attack | atk3 | - | - | - |  |  |  | gold12 grn3 red1 |  |  |  |
| Doomed Mech | attack | - | atk2 | - | - |  |  |  | gold9 blu2 |  | 5 |  |
| Drake | attack | atk2 | atk2 | - | sac:Blastforgex1 |  |  |  | gold12 blu2 |  |  | Blastforge |
| Electrovore | attack | - | atk1 | - | nrg1 |  |  |  | gold4 red1 |  |  |  |
| Feral Warden | attack | - | atk1 | - | - |  |  |  | gold5 grn1 red1 |  |  |  |
| Gauss Cannon | attack | atk1 | - | - | - |  |  |  | gold6 grn1 |  |  |  |
| Gauss Charge | attack | atk1 | - | - | - |  |  |  | gold1 grn1 |  |  |  |
| Grimbotch | attack | - | atk1 | - | - |  |  |  | gold4 red1 |  | 4 |  |
| Hannibull | attack | atk1 | atk1 | - | - |  |  |  | gold10 blu1 red1 |  |  |  |
| Hellhound | attack | atk1 | - | - | - |  |  |  | gold5 blu1 red1 |  |  | Engineer |
| Immolite | attack | - | atk1 | - | - |  |  |  | gold3 red1 |  |  |  |
| Iso Kronus | attack | atk2 | - | - | - |  |  |  | gold5 grn1 |  |  |  |
| Lancetooth | attack | - | atk2 | - | - |  |  |  | gold6 blu1 atk2 |  |  |  |
| Mahar Rectifier | attack | - | atk2 | - | - |  |  | +2 | gold11 grn2 |  |  |  |
| Nitrocybe | attack | - | atk1 | - | sacSELF |  |  |  | gold1 red1 |  |  |  |
| Odin | attack | - | atk4 | - | sac:Steelsplitterx1 |  |  |  | gold20 blu3 |  |  | Steelsplitter |
| Omega Splitter | attack | - | atk3 | - | - |  |  |  | gold15 blu3 |  |  |  |
| Perforator | attack | - | atk1 | - | red1 |  |  |  | gold3 red1 |  |  |  |
| Photonic Fibroid | attack | atk2 | - | - | - |  |  |  | gold3 grn1 red1 |  |  |  |
| Pixie | attack | - | atk1 | - | sacSELF |  |  |  | gold1 blu1 |  |  |  |
| Plasmafier | attack | - | atk4 | - | sac:Dronex1 |  |  |  | gold12 grn3 blu1 |  |  | Drone |
| Protoplasm | attack | - | atk4 | - | sacSELF |  |  |  | gold7 grn2 red2 |  |  |  |
| Redeemer | attack | - | atk3 | - | - |  |  |  | gold10 grn1 blu1 |  |  | Gauss Charge |
| Rhino | attack | - | atk1 | - | - |  |  |  | gold5 red1 | 2 |  |  |
| Scorchilla | attack | - | atk3 | - | - |  |  |  | gold3 grn1 red1 |  |  |  |
| Shadowfang | attack | atk2 | - | - | - |  |  |  | gold8 red3 |  |  |  |
| Shredder | attack | - | atk1 | - | - |  |  |  | gold5 blu1 |  |  |  |
| Steelsplitter | attack | - | atk1 | - | - |  |  |  | gold6 blu1 |  |  |  |
| Tarsier | attack | atk1 | - | - | - |  |  |  | gold4 red1 |  |  |  |
| Tesla Coil | attack | - | atk3 | - | sac:Engineerx1 |  |  |  | gold11 grn2 blu1 |  |  | Engineer |
| The Wincer | attack | - | atk15 | - | sac:Dronex5 |  |  |  | gold9 grn1 blu2 red1 |  |  | Drone |
| Thunderhead | attack | atk4 | - | - | - |  |  |  | gold15 grn5 blu1 |  | 3 |  |
| Tia Thurnax | attack | - | atk7 | - | - |  |  |  | gold7 grn3 red1 sac:Dronex7 | 3 |  | Drone |
| Tyranno Smorcus | attack | atk1 | atk1 | - | red2 |  |  |  | gold5 red2 |  |  |  |
| Urban Sentry | attack | atk1 | - | - | - |  |  |  | gold5 grn1 blu1 |  |  |  |
| Xeno Guardian | attack | atk1 | - | - | - |  |  |  | gold5 grn1 blu2 |  |  |  |
| Aegis | vanilla | - | - | - | - |  |  |  | gold6 grn3 |  |  |  |
| Amporilla | vanilla | - | - | - | - |  |  |  | gold13 red3 |  |  | Tarsier |
| Antima Comet | vanilla | - | - | - | - |  |  |  | gold3 grn1 blu1 red1 |  |  | Engineer |
| Arms Race | vanilla | - | - | - | - |  |  |  | gold8 grn1 blu1 red1 |  |  | Engineer,Tarsier,Steelsplitter,Gauss Cannon |
| Barrier | vanilla | - | - | - | - |  |  |  | gold1 grn1 |  | 1 |  |
| Blood Pact | vanilla | - | - | - | - |  |  |  | gold3 red1 |  |  | Husk,Grimbotch |
| Cluster Bolt | vanilla | - | - | - | - |  |  |  | grn4 |  |  | Gauss Charge |
| Doomed Wall | vanilla | - | - | - | - |  |  |  | gold7 blu1 |  | 3 |  |
| Endotherm Kit | vanilla | - | - | - | - |  |  |  | gold5 grn3 red1 |  |  | Frostbite,Cryo Ray |
| Energy Matrix | vanilla | - | - | - | - |  |  |  | gold8 blu2 |  |  |  |
| Forcefield | vanilla | - | - | - | - |  |  |  | gold1 grn1 sac:Dronex1 |  |  | Drone |
| Husk | vanilla | - | - | - | - |  |  |  | gold2 red1 |  |  |  |
| Innervi Field | vanilla | - | - | - | - |  |  | +1/5 | gold4 grn2 |  | 3 |  |
| Plexo Cell | vanilla | - | - | - | - |  |  |  | gold2 grn2 sac:Dronex1 |  | 1 | Drone |
| Polywall | vanilla | - | - | - | - |  |  |  | gold10 blu1 |  |  |  |
| Resophore | vanilla | - | - | - | - |  |  |  | gold1 grn1 red1 |  |  | Forcefield |
| Wall | vanilla | - | - | - | - |  |  |  | gold5 blu1 |  |  |  |
