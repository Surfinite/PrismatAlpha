# Validate cardLibrary.jso Against Prismata Wiki

## Context

We have a file `bin/asset/config/cardLibrary.jso` containing unit definitions for our Prismata AI engine. It uses internal codenames as keys (e.g., "Tesla Tower" for Tarsier). We've confirmed via in-game screenshots that there are exactly **105 non-base units** in the random pool plus **11 base set units** = 116 total.

The authoritative mapping of display names to internal names is at `docs/valid_units.json`. The wiki uses **display names** (what humans see in-game).

We've already confirmed all 116 units exist in our library. Now we need to validate that the **stats are correct** for each unit, because:
- Some data may be from pre-balance-patch versions
- At least one unit (Vivid Drone) has supply=10 in the real game but our lib says `"rarity":"rare"` (which implies supply=4)
- The standard rarity→supply mapping is: `legendary=1, rare=4, normal=20, trinket=20` — but some units may have custom supply values

## Task

For each of the 105 non-base units, fetch the wiki page and compare against our cardLibrary.jso entry. The wiki URL pattern is `https://prismata.fandom.com/wiki/UNIT_NAME` (spaces become underscores).

### What to compare

For each unit, extract from the wiki:
1. **Cost** (gold + colored resources)
2. **HP/Toughness**
3. **Supply** (this is the key one — wiki shows exact supply)
4. **Build time**
5. **Abilities** (click ability, start-of-turn effects, on-buy effects)
6. **Fragile** (yes/no)
7. **Lifespan** (if any)
8. **Blocker** (yes/no — whether it has blocking ability)

Then compare against our cardLibrary.jso entry (look up using the internal name from `docs/valid_units.json`).

### Resource encoding in cardLibrary.jso

`buyCost` uses: digits=gold, `G`=green, `B`=blue, `C`=red (attack), `H`=energy. E.g., `"6BGGG"` = 6 gold + 1 blue + 3 green.

### How to run

```bash
cd c:/libraries/PrismataAI
```

1. Load `docs/valid_units.json` to get the display→internal name mapping
2. Load `bin/asset/config/cardLibrary.jso` to get our current stats
3. For each of the 105 non-base units, WebFetch `https://prismata.fandom.com/wiki/DISPLAY_NAME` (replace spaces with underscores)
4. Extract stats from wiki page
5. Compare against our entry

### Output

Create `docs/wiki_card_validation.md` with:

1. **Discrepancies table** — units where our data differs from wiki. Columns: Display Name | Field | Wiki Value | Our Value | Internal Name
2. **Supply audit** — for ALL 105 units, list the wiki supply vs our rarity-implied supply. Flag any where they don't match the standard mapping.
3. **Perfect matches** — count of units where everything matches
4. **Summary** with recommended fixes

### Important notes

- The wiki is the authority. If wiki and our data disagree, the wiki is correct.
- Pay special attention to the 6 units from the January 2019 balance patch: **Wild Drone** (major redesign), **Odin** (HP 4→3), **Militia** (cost 6B→3B + sac Drone), **Mobile Animus** (click cost 3→2), **Sentinel** (cost 7CG HP4→6CG HP3), **Blood Phage** (cost 8CH BT1→6CH BT2). Our SWF data is likely pre-patch for these.
- Some wiki pages may not load or may have unusual formatting. Skip those and note them.
- Do NOT modify cardLibrary.jso — just report findings. We'll fix in a separate step.
- Batch the WebFetch calls — do multiple units in parallel where possible to save time.
- You'll probably need to use agents to parallelize this effectively across 105 units.
