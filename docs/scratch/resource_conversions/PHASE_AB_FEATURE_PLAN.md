# Production-vector features (Phase A+B) — plan & rationale

Captures the decision to lift unit *ability payloads* into the DeepSets static-property table.
Status: **feature definition done & validated; wiring + retrain deferred** pending the data decision.

## The hole

The model's 13 static properties capture *stats* (costs, HP, fragile, blocking, build_time,
lifespan, **base_attack**, has_ability, max_stamina) but almost no *ability payloads*. Attack is
the only `receive` resource given a feature; everything else a unit produces/does is visible only
through the learned 32-d embedding:

- **Economy generation** (gold/green/blue/red/energy) — invisible (Engineer/Animus/Thorium...).
- **Chill** (`disrupt` targetAmount 1–7: Cryo Ray → Vai Mauronax) — invisible.
- Unit **creation**, **snipe/netherfy** (destroy), prerequisites — invisible.

So Cryo Ray (chill 1) and Vai Mauronax (chill 7) look identical on offense (both base_attack 0);
Tatsu Nullifier and rare swing units are under-represented because their value lives in an
under-trained embedding.

## Why we build on principle, not on an ablation

The training corpora can't fairly measure these features:
- **Masterbot self-play** (the DSNN_MBonly corpus) **never uses ~14 units** humans play
  (Infusion Grid, Fission Turret, Blood Phage, Perforator, Nivo Charge, Lucina Spinos, …) and
  underuses a long tail 5–14× (Savior 13.8×, Plasmafier 7.5×, Frostbite 6.9×). MB guards avoid
  exactly the ability-rich units these features target → the ablation reads ~0 from lack of data,
  not lack of value.
- The **human corpus** that *does* use them is the contaminated one.

So a supervised ablation is structurally blind here. The features are **infrastructure**: they
help most under **RL** (on-policy data covers whatever the policy explores) and a future
**policy head** (choosing clicks needs to know what each unit produces). Decision: add them now;
accept the supervised retrain may show little, which is expected.

## Feature set (22 new columns; num_properties 13 → 35; token_dim 55 → 77)

Attack stays in the existing `base_attack` (its auto/click conflation is an open decision — see below).

**Phase A — production (split auto vs click; never summed):**
`auto_{gold,green,blue,red,energy}` (beginOwnTurnScript.receive, guaranteed/free),
`click_{gold,green,blue,red,energy}` (abilityScript.receive, optional), `chill_amount`.

**Phase B — cost side (to net the click production):**
`click_cost_{gold,green,blue,red,energy}` (abilityCost), `click_cost_hp` (HPUsed),
`click_selfsac`, `auto_selfsac`, `click_sac_units` (abilitySac count), `buy_sac_units` (buySac
count — kept distinct from click cost), `hp_regen` (HPGained).

**Left to the embedding (Tier 3 — not featurized):** `create` (value flips with owner — 5 units
create *for the opponent*, e.g. Valkyrion — and is recursive in the created unit), `destroy`
(conditional snipe/netherfy), `needs` (prerequisites). Created/destroyed units appear on the
board anyway where the model already sees them.

## Lessons baked into the generator (`build_feature_table.py`)

- `receive` is sometimes a **bare integer** = gold (Militia `receive:1`, Manticore `receive:3`);
  the first parser dropped these silently.
- **Auto and click production must not be summed** — Thorium is begin-turn `5G` (5 gold + 1 green)
  *and* a separate click `GGG→3`, not "8 gold." They are independent/additive, not either/or.
- **Create carries an owner** — `for opponent` is a drawback, not upside (Valkyrion, Arms Race…).
- **auto_selfsac** flags one-shot auto-bursters with no lifespan field (Centrifuge, Auric Impulse,
  Gauss Charge, Photonic Fibroid, Antima Comet) — without it they read as permanent engines.
- Resource codes: bare digits/int = gold, `G`=green, `B`=blue, `C`=red, `H`=energy, `A`=attack.

Open decision: `base_attack` still sums auto + click attack (same conflation). Left as-is for now;
split into `auto_attack`/`click_attack` later if it matters.

## Remaining steps to ship (single retrain)

1. Promote `property_table_candidate.json` → `training/property_table.json`.
2. `schema_v2.json`: `num_static_properties` 13→35, `token_dim` 55→77.
3. `model_deepsets.py`: `num_properties` default → 35.
4. Verify `vectorize_v2.py` reads the table length (auto-adapts).
5. Retrain (the only expensive step — gate on the data decision) → `export_weights_v2.py`.
6. Re-run the parity harness (`PrismataAI-dave-master/tools/parity/`): the C++ reads
   `num_properties` from the DSN2 header, so no engine edit — the harness auto-confirms the
   35-property model still ties out (|Δ| ~1e-6).

## Files here

- `unit_ability_map.md` — full per-unit ability/production/cost catalog (all 116, display names).
- `build_ability_map.py` — generates that catalog.
- `build_feature_table.py` — generates the candidate property table (the 22 new columns).
- `property_table_candidate.json` — the Phase A+B candidate (non-destructive; 35 properties).
- `README.md`, `graph.dot`, `graph.mmd` — the click-conversion resource graph (prior work).
