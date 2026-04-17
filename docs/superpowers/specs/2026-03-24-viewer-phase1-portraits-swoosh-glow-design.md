# Viewer Visual Fidelity Phase 1: Portraits, Swoosh, Shield Glow

**Date**: 2026-03-24
**Status**: Approved
**Scope**: Three visual enhancements to the PixiJS spectator viewer

## Context

The viewer is a faithful recreation of the Prismata SWF client for spectators. We have decompiled AS3 source and extracted HD sprite sheets from the SWF for reference. Each feature must be verified against the real SWF client during implementation.

## Feature 1: Player Portraits

**SWF reference**: `UITopBar.as` / `UIBottomBarLeft.as` — 50x50 `UIAvatar` rendered from `GamePlayer.picture` field.

**Data source**: `playerInfo[n].portrait` in replay JSON (e.g. `"__Grenade Mech"`). Strip `__` prefix to get card display name, look up card art PNG already in the bundle.

**Rendering**: 50x50 cropped portrait next to each player's resource bar. Top player portrait near top-left, bottom player near bottom-left. Fallback: first letter of player name in a colored circle if portrait art not found.

**Verification**: Compare portrait placement against SWF screenshot showing player info bars.

## Feature 2: Swoosh Animation

**SWF reference**: `UIBoard.as` lines 352-925 — `beginSwoosh()` triggered on turn transitions. Uses `snipe_flash` sprite (673x308 HD) slashed across the defending player's board area.

**Trigger**: Detect `numTurns` increment in `BoardRenderer.updateState()`. The swoosh plays on the player who just finished being attacked (the defending player).

**Animation**:
- Sprite: `snipe_flash` from HD atlas (already extracted at `bin/asset/images/icons/extracted_hd/`)
- Needs to be added to asset bundle
- Fade in ~100ms, hold ~100ms, fade out ~300ms (total ~500ms)
- Positioned centered on defending player's board half
- Slight rotation to match SWF diagonal slash angle

**Verification**: Compare swoosh timing and position against SWF screenshots showing the slash animation mid-transition.

## Feature 3: Shield Glow (Breach Threat)

**SWF reference**: `UIAttackDefenseLayer.as` line 207 — `BlurFilter.createGlow(0xFF0000, 1, 10, 0.5)` applied to shield when attack exceeds defense. Also line 185: `shield_big_glow` texture exists as a separate pre-rendered glow variant.

**Approach**: Use the `shield_big_glow` texture (108x108, already extracted) instead of `shield_big` when breach octagon is showing. This is simpler than runtime filter effects and matches the SWF's own pre-rendered glow asset.

**Verification**: Compare shield appearance during breach threat against SWF screenshot.

## Files Modified

| File | Changes |
|------|---------|
| `js_engine/build_viewer_bundle.js` | Add `snipe_flash`, `shield_big_glow` to HD asset bundle |
| `BoardRenderer.ts` | Swoosh animation on turn change, shield glow swap, portrait rendering |

## Implementation Notes

- All new sprites come from `bin/asset/images/icons/extracted_hd/` (HD SWF atlas extraction)
- Portrait card art already in bundle as base64 PNGs
- No protocol or bridge changes needed
- Verify each feature against SWF screenshots before moving to next
