# Native C++ Replay Export + PixiJS Local Viewer — Design

> **Date:** 2026-05-28
> **Status:** Design — pending implementation plan
> **Author:** Surfinite (with Claude)

## Context & Motivation

DSNN-vs-DaveAI A/B testing currently runs through `matchup_clean.js`, which drives
the **JS engine** and queries the C++ AI one turn at a time via the `--suggest`
bridge. That path works, but:

1. Dave's own C++ engine (`engine_v1`, in the `PrismataAI-dave-master` worktree on
   branch `dave-master-jsonclean`) is the engine he trusts and has always run
   tournaments through. When he's back, asking him to run tournaments *through the
   JS engine* purely so we can view replays is a hard sell — and unnecessary.
2. A win-rate number alone ("DSNN 46.1% vs SteamAI") doesn't tell us *where* the AI
   is weak. We need to **watch** bot-vs-bot games to build intuition — and they must
   look **pixel-identical to the real Prismata client**, or the visual is not worth
   building.

The prismata.live replay viewer is a faithful PixiJS recreation of the Flash client
(`prismata-ladder` repo, `game-renderer/`), shipped Mar 2026 and battle-tested by the
community. Recon established that **this renderer is a pure renderer**: given an array
of pre-computed game-state snapshots, it draws them directly. It only invokes the JS
engine when handed an *S3 click-list* (to reconstruct states). Feed it snapshots and
the JS engine is out of the loop entirely.

That unlocks a design where **all of our constraints hold simultaneously**:

- Tournaments run in Dave's C++ engine (he trusts it; no JS-engine-for-games sell).
- The JS engine is **not** involved in playing games.
- Replays render through the real, trusted PixiJS canvas (pixel-identical visuals).

## Goals

- Add a `--save-replays <dir>` capability to Dave's C++ tournament runner that emits,
  per game, a snapshot replay file the PixiJS viewer can render directly.
- The flag is **OFF by default and a verified true no-op** — zero effect on
  tournament results or AI search/playout speed when disabled.
- Stand up an **unlisted, client-side `/replay/local` page** on prismata.live where you
  drag-drop a replay file and watch it through the real PixiJS renderer — no local
  server, no JS-engine reconstruction.
- Achieve **visual fidelity** equal to a real-client replay, including derived display
  fields (gold estimate, attack/disrupt potential, incoming attack, etc.).

## Non-Goals

- Running tournaments through the JS engine. (Explicitly rejected.)
- Emitting the S3 click-list format from C++, or solving the click-emission problem.
  (We serialize the *actual* `GameState`, never wire-clicks.)
- Adding a public/linked replay-upload feature to prismata.live, or any backend/API
  change. The page is unlisted and fully client-side.
- Puzzle-editor parity. Fields touched only by `PuzzleController` are out of scope.
- Hand-to-Dave offline artifact / standalone bundle. (Considered; deferred. The
  C++ output format is identical, so a standalone viewer remains possible later.)

## Hard Constraints (design invariants)

1. **No-op when disabled.** No changes to `GameState` / `Move` / `Action` internals.
   No new fields, virtual calls, or allocations on the AI's hot path (search/playout).
   With `--save-replays` off, the serializer is never called; the only residual cost
   is one boolean check per *real* turn, outside the AI's timed region.
2. **Capture is a top-level observer.** Serialization reads the *real* states that
   actually occur in the game (a few hundred per game), never the millions of
   throwaway `GameState` copies the AI explores during search.
3. **Site bundle is the fidelity authority.** Where the local js_engine and the
   site's engine bundle disagree on a derived field, the site bundle wins.

## Architecture Overview

Three artifacts, one shared contract:

```
[Dave's C++ engine_v1]                          [prismata.live site]
  Tournament/Game loop                            /replay/local (unlisted)
    └─ ReplaySerializer (NEW)                        ├─ drag-drop file → gunzip → JSON
         GameState → snapshot JSON                   ├─ detect states[] → skip JS engine
         (gated by --save-replays)                   └─ feed PrismataBoard (PixiJS)
              │                                              ▲
              ▼                                              │
       game_XXXX.json.gz  ───────────────────────────────────┘
              │
              └────────── SHARED SNAPSHOT SCHEMA (contract) ──────────┘
```

## Part 1 — C++ snapshot serializer (engine_v1, `PrismataAI-dave-master`)

### Trigger
- New flag `--save-replays <dir>` (CLI) and/or `"saveReplays": "<dir>"` on the
  Tournament config block in `config.txt`. Default OFF.

### Hook point
- The top-level game driver (`Game::playNextTurn()` / the tournament's per-game loop),
  **after** the player's `Move` is returned **and the player's think-time timer has
  stopped** — so capture never counts against think-time budgets or `_playerTotalTimeMS`.
- When enabled, step the returned `Move` **action-by-action**, serializing a snapshot
  after each `Action`, so the viewer animates per buy / per attack (~12 states/turn),
  not whole-turn jumps. Also capture the initial (turn-0) state.
- When disabled, none of this runs.

### What each snapshot serializes (`GameState → JSON`)
- **Board `table[]`**, per instance: `instId`, `cardName` (UIName/display name),
  `owner`, `health`, `damage`, `role`, `deadness`, `constructionTime`, `charge`,
  `delay`, `lifespan`, `disruptDamage`, `blocking`, `boughtThisPhase`, `bornThisTurn`,
  `autoClicked`, `isFragile`, `defaultBlocking`, `cardType`.
- **Resources / phase:** `whiteMana`, `blackMana` (string encoding), `turn`,
  `numTurns`, `phase`, `glassBroken`.
- **Supply:** `cards[]`, `white/blackTotalSupply[]`, `white/blackSupplySpent[]`.
- **Derived display fields:** `incomingAttack`, `maxAttack`, `maxDisrupt`,
  `maxSnipers`, `oppAttackPotential`, `oppDisruptPotential`, `oppSnipers`,
  `whiteGoldEstimate`, `blackGoldEstimate` — sourced from engine_v1's `StateHelper`
  equivalents, implemented to **site-bundle semantics** (see Reconciliation).
- **Action labels** (`actions[]`): human-readable, from `Action::toHistoryString()`.

### Output file
- One `game_XXXX.json.gz` per game in `<dir>`, top-level:
  `{ replay, p0, p1, winner, winnerName, turns, cardSet[], states[], actions[], turnBoundaries[] }`
  — the exact shape `matchup_clean.js --save-replays` already produces and the PixiJS
  viewer already loads.

### Schema additions over the matchup baseline (surfaced 2026-05-28 visual review)

Two gaps in the matchup-format baseline became visible while validating Phase 2
against an existing replay. The C++ exporter must close both:

- **`playerInfo[]`** — matchup format carries only bare `p0: "DAVEAI"` / `p1: "DAVEAI"`
  strings, so DSNN-vs-Dave games render as "DAVEAI vs DAVEAI" with no way to tell
  which side ran which model. C++ exporter must add a top-level `playerInfo` array
  matching the structured shape the PixiJS PlayerBar consumes:
  `[{ displayName, portrait, badges, avatarFrame, ...optional config }, ...]`.
  At minimum `displayName` must include the differentiator — e.g.
  `"DAVEAI (HardestAI)"` and `"DAVEAI (DSNN_MBonly)"`. Optional richer fields
  (`difficulty`, `model`, `weightsFile`) can be added for tooling consumers.

- **Per-action timing** — matchup format has no `commandInfo`/`stateTimestampMs`,
  so the scrubber's turn-band heatmap can't render (`_drawHeatmap()` bails when
  `hasTiming === false`). C++ exporter must either emit real per-action wall-clock
  timestamps OR synthesize uniform spacing — the snapshot needs
  `stateTimestampMs[]` parallel to `states[]`, plus `turnStartMs[]` / `turnEndMs[]`
  parallel to `turnBoundaries[]`, plus a stub `commandInfo` object. The local
  viewer page synthesizes this for matchup replays today (`ensureSyntheticTiming`
  helper) as a temporary workaround; producing it at C++ export time keeps the
  viewer page generic.

## Part 2 — Unlisted client-side `/replay/local` page (prismata.live)

- **New route** `/replay/local` in the `prismata-ladder-site` Next.js app. Unlisted
  (not in nav), reachable by URL only.
- **Fully client-side:** drag-drop / file-picker → `FileReader` → gunzip
  (`DecompressionStream` or `pako`) → `JSON.parse`. The file never leaves the browser;
  no backend or API change.
- **Format detection:** if the replay has a `states[]` array (our C++ output), feed it
  to the snapshot path and **skip** `loadFromCode` / the JS-engine reconstruction. The
  existing S3 click-list branch keeps working unchanged.
- **Reuse:** the renderer source (`game-renderer/`) is tracked normally and the new
  page picks up renderer improvements automatically. The shipped `cardMeta` and
  `bundleAssets` are reused as-is. Net new page code is small and additive.

### Bundle entry point — required hand-edit (NOT a rebuild)

The currently-shipped `prismata-engine.js`'s `window.PrismataViewer` IIFE exposes
`loadFromCode`, `initLive`, `processClick`, `loadPuzzle`, steppers, and getters —
**no load-from-buffer or load-from-object entry**. `loadMatchupReplay` (line 8352)
and `processArrayBuffer` (line 8310) are internal to the IIFE.

So `/replay/local` cannot reach the snapshot render path without **adding a new
exported function** (e.g. `loadFromBuffer(arrayBuf)` or `loadFromObject(replay)`)
that wraps the existing internal `processArrayBuffer` / `loadMatchupReplay`.

**This edit must be applied directly to the shipped
`prismata-ladder-site/public/js/prismata-engine.js`, not to
`js_engine/build_viewer_bundle.js`** — per the standing rule that the bundle is
hand-edited and a fresh build via `build_viewer_bundle.js` regresses the puzzle
editor. Verified 2026-05-28 by a fresh build to a temp file: ~112-line net
deletion in the IIFE area vs. the shipped bundle. Pattern this after the
puzzle editor's `loadPuzzle` and the other editor extensions (`getCardMeta`,
`getAssets`, etc.) which are already in-bundle.

Source for the rule: `~/.claude/projects/c--libraries-prismata-ladder/memory/feedback_engine_bundle_no_rebuild.md` (workspace-local memory, not in any committed file). A one-liner pointer in
`prismata-ladder/CLAUDE.md` would make it discoverable; suggested as a small parallel
improvement, tracked under Future Work.

## Shared Data Contract (snapshot schema)

The single artifact both halves depend on. Pin it as a documented schema so the C++
producer and the viewer input can't silently drift.

**Top level**
```
{
  "replay": true,
  "p0": string, "p1": string,
  "winner": number,        // 0 = white wins, 1 = black wins, -1 = draw
  "winnerName": string,
  "turns": number,
  "cardSet": string[],     // random units in play (UINames)
  "states": GameState[],   // one per action (the animation frames)
  "actions": string[],     // parallel labels ("Buy Drone", "Assign blocker", ...)
  "turnBoundaries": number[] // indices into states[] where each turn starts
}
```

**⚠ Winner-encoding clarifier.** The matchup-format `winner` above (0=white /
1=black / -1=draw) is **different from** the S3 replay format's `result` field
(0=P1 wins / 1=P2 wins / 2=draw, per CLAUDE.md). `loadMatchupReplay` consumes the
matchup encoding, so the two are internally consistent — but validation tooling and
any future cross-format work must keep them apart.

**`GameState`** — fields as listed in Part 1. Authoritative field list and types are
the renderer's `game-renderer/types.ts` `GameState` interface.

**`CardInstance`** (`table[]`) — fields as listed in Part 1; authoritative source is
`game-renderer/types.ts`.

## Derived-Field Reconciliation (fidelity)

There are (at least) three places this logic can disagree:
1. **Local `js_engine/`** (`replay_exporter.js stateToCppJSON`, `StateHelper.js`,
   `State.js`, `Inst.js`) — drives `matchup_clean.js`, our run-games oracle.
2. **Shipped site bundle** (`prismata-ladder-site/public/js/prismata-engine.js`) —
   the file users actually load on prismata.live, most eyes on it, treated as
   faithful to the real client. Hand-divergent from `build_viewer_bundle.js`
   (verified 2026-05-28: fresh build differs by ~112 lines in the IIFE area).
3. **Renderer contract** (`game-renderer/types.ts` + consumers) — what's actually
   read & drawn.

Empirically (2026-05-28 grep): all three reference the derived fields; the shipped
site bundle **does** compute them; the renderer actively reads them; and some
references live only in `PuzzleController.ts` (out of scope, confirming some
of the puzzle-editor additions are unrelated to replay rendering).

**Resolution rules:**
- **Scope** = fields the *renderer* reads. Fields touched only by puzzle paths are excluded.
- **Value semantics** = how the **shipped site bundle** computes each in-scope field.
  Site wins on any disagreement.
- **Authority source** = **the shipped `prismata-engine.js`** specifically, NOT a
  fresh `build_viewer_bundle.js` output. Because of the documented hand-edit
  divergence, reading the build script for the answer could pin the wrong value.
- **Harness** = the local matchup engine, trusted only where it agrees with the
  shipped bundle.

**Deliverable:** a one-time **reconciliation table** built *before* C++ coding — for
each in-scope field, record the shipped-bundle computation, the local-engine
computation, and agree/disagree. The C++ serializer implements to the shipped-bundle
column.

## Verification & Testing

1. **No-op proof (gate):** run an identical-seed tournament with vs. without
   `--save-replays`; assert **byte-identical results** and within-noise timing.
2. **Field-by-field oracle diff:** compare C++ output to `matchup_clean.js
   --save-replays` for the same position; fast, catches the bulk of fields.
3. **Authority check:** for any field where the matchup engine and the site bundle
   disagree (per the reconciliation table), test C++ against the **site-bundle** value.
4. **C++ unit test:** serializer on a crafted `GameState` (alive/dead units, blocking,
   chill, construction, charge, breach) → expected JSON.
5. **Visual parity:** load a C++ replay in `/replay/local`, watch a full game, compare
   against a known real-client replay of a comparable position.

## Open Questions / Risks

- **Derived-field divergence size** — unknown until the reconciliation table is built.
  If large, Part 1's derived-field work grows. Mitigation: build the table first.
- **engine_v1 `StateHelper` coverage** *(ask Dave directly)* — need to confirm
  engine_v1 exposes equivalents for every in-scope derived field (gold estimate,
  attack/disrupt potential).
- **Per-action stepping fidelity** *(ask Dave directly)* — whether engine_v1 applies
  a `Move` atomically or action-by-action determines whether we snapshot inline or
  replay actions on a clone to generate intermediate frames.
- **Asset availability** — the site already hosts card art / backgrounds / HUD; the
  unlisted page reuses them, so no asset packaging needed (a benefit of the site route).

## Out of Scope / Future Work

- **Bundle/source backfill.** The shipped `prismata-engine.js` is hand-divergent from
  `build_viewer_bundle.js` by ~112 lines (mostly puzzle-editor extensions).
  Identifying that divergent code and porting it into the build script — so a fresh
  rebuild becomes safe again — is real work but not blocking. Recent PrismataAI
  commits (`4781666 loadPuzzle`, `f553796 uniqueCards cache`, `f866ae4 getCardMeta`,
  `3ba3643 getAssets`, `8bfcbea StateHelper potentials`, `880886a replay emotes`,
  `deaa5fa multiple emotes`) suggest substantial backfill already happened; what
  remains is the residual ~112 lines.
- **Discoverable no-rebuild rule.** The constraint lives only in a workspace-local
  memory file. A one-liner in `prismata-ladder/CLAUDE.md` (and a clarifying comment
  in the bundle header, which currently says the opposite) would make it
  point-at-able for collaborators.
- **Standalone offline viewer.** The site-route choice means there's no hand-to-Dave
  zip artifact. If that need surfaces later, the C++ replay format is unchanged;
  a build-script-generated standalone PixiJS page becomes a future deliverable
  with no contract churn.

## Review Decision

External `/document-context` review **skipped**. The substantive risk in this design
lives in undocumented local constraints (the never-rebuild rule, the shipped-bundle
divergence) — exactly the kind of thing a no-code-access reviewer can't see. A
ladder-workspace session review surfaced both, plus the missing entry-point and the
winner-encoding clarifier, all folded above. The two remaining engine_v1 risks are
for Dave, not a reviewer.

## Verification Log

**2026-05-28 — Phase 3 Task 13 no-op gate (stub flag, by inspection):**
The Task 12 stub adds one CLI/config path:
`_saveReplaysDir = tournamentValue["saveReplays"].GetString()` (Tournament.cpp:35).
Grep confirms zero readers of `_saveReplaysDir` or `getSaveReplaysDir()` anywhere
in `source/` — the field is written in the Tournament constructor and never
consulted. The flag's stub form is therefore a no-op by construction; no empirical
run is needed to prove it. (An earlier attempt at an empirical gate burned ~100
minutes on 4 unintended HardestAIUCT-vs-HardestAIUCT runs at `TimeLimit:7000` and
produced asymmetric 8-0 results — both because the mirror match exposes a P1
advantage with `SkipColorSwap` and because the gate was over-engineered for a stub
that does nothing.) The empirical gate is reused at Task 18 when `_saveReplaysDir`
actually drives serialization — at that point we'll re-verify with `TimeLimit:100`
on a faster smoke tournament.

## Affected Locations (reference)

| Area | Path |
|---|---|
| C++ tournament runner | `PrismataAI-dave-master/source/testing/Tournament.cpp`, `TournamentGame.cpp` |
| C++ game loop | `PrismataAI-dave-master/source/engine/Game.{h,cpp}` |
| C++ move/action | `PrismataAI-dave-master/source/engine/Move.h`, `Action.h` |
| C++ config parse | `PrismataAI-dave-master/source/ai/AIParameters.cpp` |
| New: C++ serializer | `PrismataAI-dave-master/source/testing/` (new file) |
| Oracle (JS) | `PrismataAI/js_engine/replay_exporter.js` (`stateToCppJSON`) |
| Site renderer | `prismata-ladder/prismata-ladder-site/src/components/game-renderer/` |
| Site engine bundle (HAND-EDIT, do not rebuild) | `prismata-ladder/prismata-ladder-site/public/js/prismata-engine.js` |
| New: local page | `prismata-ladder/prismata-ladder-site/src/app/replay/local/` |
| Bundle build source (do NOT use for bundle changes — divergent) | `PrismataAI/js_engine/build_viewer_bundle.js` |
| No-rebuild rule (workspace memory) | `~/.claude/projects/c--libraries-prismata-ladder/memory/feedback_engine_bundle_no_rebuild.md` |
