# Viewer Visual Fidelity — Continuation Prompt

> **Use this prompt to resume work in a new session.**

## Context

The PixiJS replay/live viewer is on branch `feature/live-viewer` in `<LADDER_REPO_PATH>\`. We completed Stream 1 (unit card polish), Stream 2 (board HUD), and added gold estimate `[min-max]` matching the SWF's StateHelper logic. 19 commits on the <ladder> branch, 5 on PrismataAI's ai-improvements branch.

**What's working:**
- Font strokes on all numbers, SWF-accurate icon positioning (verified against UIStatus.as, UIInst.as)
- Sword icon flipped, variable status numbers overlapping icons
- Midline HUD: attack/defense with chill next to each player's attack, danger `!` indicator
- Gold estimate `[min-max]` computed engine-side (faithful StateHelper port with goldResonate, phase-aware, current gold included)
- Chill snowflake overlay using Card_Chilled.png at SWF 0.3 scale
- 80 tests passing, build succeeds

**Completed plan:** `docs/superpowers/plans/2026-03-24-viewer-visual-fidelity.md`

## What's Next — Three Priority Items

### 1. Resource Bar: Numbers On Top of Icons
**Current:** Resource count renders beside the icon (icon + number side by side)
**SWF:** Count renders centered ON TOP of the resource gem icon
**Files:** `<ladder>-site/src/components/game-renderer/ResourceBar.ts`
**AS3 ref:** Look at `UIPlayerManaBar.as` for exact positioning

### 2. Buy Panel Visual Accuracy
**Current:** Buy panel shows card art, plain text cost, and supply number
**SWF:** Buy panel has colored resource pips (gold/green/blue/red/energy gems), proper supply bars, and specific styling
**Files:** `<ladder>-site/src/components/game-renderer/BuyCard.ts`, `BuyPanel.ts`
**AS3 ref:** `UIBuyColumn.as`, `UIBuyCard.as` — extract cost pip rendering, supply indicator styling, and card layout

### 3. Breach Animation Phase (Biggest Item)
**Current:** When breach happens, dead units just disappear. No visual feedback.
**SWF:** Full breach sequence with red flashing, damage numbers flying, unit destruction effects (skulls, fading), overkill indicators
**Key AS3 files:**
- `UIAnimationMain.as` — animation coordinator
- `SkullEffect.as` — death effect
- `AbsorbEffect.as` — damage absorption flash
- `UIBoard.as` — breach/overkill flow, large damage number overlay (the big "3" in screenshots)
- `ChillEffect.as` — chill particle burst (when unit gets chilled)
- `FrontlineEffect.as` — frontline glow pulse
- `FinishConstructionAnim.as` — construction complete sparkle

**Approach:** Start with the large breach damage number (simplest — just a big centered number overlay), then add unit death animations (skull fade-in is already partially implemented), then the red flash/pulse effects.

## Important Principles (from this session)

1. **Always verify against AS3 decompiled source** — don't guess positioning values. The decompiled files are at `prismata_decompiled/scripts/starlingUI/game/`
2. **100% parity goal** — We're faithfully reimplementing the real client's visuals, not creating our own interpretation. This is important because we're reimplementing existing game mechanics, not forcing an overlay onto viewers.
3. **Engine-side computation preferred** — Complex game logic (like gold estimate) should be computed in the JS engine bundle (`replay_exporter.js`) where it has full access to card data, not approximated in TypeScript.
4. **The `computeChill()` function uses cardMeta** — Chill data is on card metadata (targetAction/targetAmount), not on instance data.
5. **Card_Chilled.png is the snowflake overlay** — bg_chilled is the card BACKGROUND texture (Card_Blue_Frost.png), not the snowflake sprite.
6. **Shield overlays are 148x148 RGBA PNGs** — `highlight_blueshield.png` etc., designed as card-size overlays with baked-in transparency.

## Quick Start

```bash
cd <LADDER_REPO_PATH>/<ladder>-site
npx next dev --webpack
# Open http://localhost:3000/replay/++Lz6-V00@a (good test replay with chill, breach, complex boards)
```

Test replay codes in `<ladder>-site/tests/visual-baselines/replay-codes.txt`.
