# Native C++ Replay Export + PixiJS Local Viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--save-replays` to Dave's native C++ tournament runner so it emits snapshot replay files that render through the real PixiJS canvas on prismata.live via a new unlisted `/replay/local` drag-drop page.

**Architecture:** Three phases. Phase 1 produces a derived-field reconciliation table (knowledge artifact) that drives Phase 3 fidelity. Phase 2 stands up the viewer side (bundle hand-edit + React page) validated against existing matchup replays. Phase 3 adds the C++ serializer in Dave's engine_v1, gated by a true no-op invariant and validated against both the matchup oracle and the Phase 2 viewer.

**Tech Stack:** C++17 (engine_v1, MSBuild x86 / g++ Makefile), Node 18+ (matchup_clean.js oracle), React 18 + PixiJS v8 + Next.js 16 (ladder site), TypeScript, Vitest (renderer tests).

**Spec:** [docs/superpowers/specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md](../specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md)

**Branches/worktrees:**
- PrismataAI: `feature/cpp-replay-export-pixijs-viewer` (already exists; spec lives here)
- PrismataAI-dave-master worktree (`dave-master-jsonclean`): create child branch `feature/save-replays` before Phase 3 edits
- prismata-ladder: create branch `feature/replay-local-page` before Phase 2 edits

**Engine_v1 questions resolved from the code (2026-05-28):**
1. **Move atomicity → SEQUENTIAL.** `Game::doMove()` ([Game.cpp:66-91](../../../../../PrismataAI-dave-master/source/engine/Game.cpp#L66-L91)) loops over the move's actions and calls `Game::doAction(action)` for each, which in turn calls `m_state.doAction(action)`. Every action passes through the single chokepoint `Game::doAction`. **Task 16 takes Branch A; Branch B is deleted.**
2. **StateHelper coverage** — still uncertain until Phase 1 lands the reconciliation table. Surfaced inside Task 15 / Task 17 work via grepping `source/{ai,engine}` for each derived-field name. If a derived field has no engine_v1 equivalent, port it from `js_engine/StateHelper.js`/shipped bundle as a free function in `ReplaySerializer.cpp` (acknowledged risk listed below).

---

## Phase 1 — Derived-Field Reconciliation Table

Produces `docs/derived-field-reconciliation.md` listing, for each in-scope derived field, the shipped-bundle computation, the local-js-engine computation, and agree/disagree. This artifact is the contract Phase 3's derived-field code implements against.

**No code execution — discovery + writing. Self-validated by completeness.**

---

### Task 1: Enumerate in-scope derived fields

**Files:**
- Read: `c:/libraries/prismata-ladder/prismata-ladder-site/src/components/game-renderer/types.ts`
- Read: `c:/libraries/prismata-ladder/prismata-ladder-site/src/components/game-renderer/{BoardRenderer,BoardView,ResourceBar,PlayerBar,RowView,PileView,UnitCard,visual-state,pile-sort,auto-clicks}.ts`

- [ ] **Step 1: List every field on `GameState` and `CardInstance` defined in `types.ts`**

Read the full `types.ts`. Capture into a scratch list at `docs/scratch/reconciliation/types-fields.md` (create dir if needed). Note: only the renderer's *consumed* fields are in scope. Fields defined on the interface but never read by renderer code are still in-scope (they're the contract) but flag those whose values we'd need to provide.

- [ ] **Step 2: Grep each renderer file for which `GameState`/`CardInstance` fields it reads**

```bash
cd c:/libraries/prismata-ladder/prismata-ladder-site/src/components/game-renderer
# For each field name from Step 1, grep usages
grep -n "gameState\.<fieldName>\|state\.<fieldName>" *.ts
```

Build a usage matrix at `docs/scratch/reconciliation/renderer-usage.md`: rows = fields, columns = files, mark `read`/`-`.

- [ ] **Step 3: Exclude puzzle-only fields**

`PuzzleController.ts` is out of scope. If a field is *only* read by `PuzzleController.ts` (and not by any other renderer file), mark it `OUT OF SCOPE — puzzle only` and exclude from the table.

- [ ] **Step 4: Save the in-scope field list**

Write `docs/scratch/reconciliation/in-scope-fields.md`: one bullet per field, with a short note ("derived" or "structural") and which files consume it.

- [ ] **Step 5: Commit scratch artifacts**

```bash
cd c:/libraries/PrismataAI
git add docs/scratch/reconciliation/
git commit -m "phase1(recon): enumerate in-scope derived fields from game-renderer"
```

---

### Task 2: Catalog computation in the shipped site bundle

**Files:**
- Read: `c:/libraries/prismata-ladder/prismata-ladder-site/public/js/prismata-engine.js` (the SHIPPED bundle, NOT a fresh build — confirmed hand-divergent per spec)

- [ ] **Step 1: For each in-scope DERIVED field from Task 1, locate its computation in the shipped bundle**

The derived fields (from the spec): `incomingAttack`, `maxAttack`, `maxDisrupt`, `maxSnipers`, `oppAttackPotential`, `oppDisruptPotential`, `oppSnipers`, `whiteGoldEstimate`, `blackGoldEstimate`, plus any others Task 1 surfaced.

For each:
```bash
grep -n "<fieldName>" c:/libraries/prismata-ladder/prismata-ladder-site/public/js/prismata-engine.js
```

Find the writer (assignment site), the reader (where it's set on the snapshot object), and the upstream function that computes it.

- [ ] **Step 2: Quote each computation**

For each field, capture the exact function body that produces it, plus enough context to know the inputs. Save in `docs/scratch/reconciliation/bundle-computations.md`, formatted:

```markdown
## maxAttack

**Computed at:** `prismata-engine.js:NNNN-NNNN`

**Inputs:** [analyzer state, player ID]

```javascript
function computeMaxAttack(state, playerId) {
    // ... actual code copied verbatim from the bundle ...
}
```

**Notes:** [any subtle bits — sniper handling, dead unit exclusion, etc.]
```

- [ ] **Step 3: Commit**

```bash
git add docs/scratch/reconciliation/bundle-computations.md
git commit -m "phase1(recon): catalog shipped-bundle derived-field computations"
```

---

### Task 3: Catalog computation in local `js_engine/`

**Files:**
- Read: `c:/libraries/PrismataAI/js_engine/StateHelper.js`
- Read: `c:/libraries/PrismataAI/js_engine/State.js`
- Read: `c:/libraries/PrismataAI/js_engine/replay_exporter.js` (the `stateToCppJSON` function around line 75-246 emits the snapshot — that's the contract)
- Read: `c:/libraries/PrismataAI/js_engine/Inst.js`

- [ ] **Step 1: For each in-scope derived field, locate the LOCAL computation**

Same field list as Task 2. Use `grep -n "<fieldName>" js_engine/*.js`.

- [ ] **Step 2: Quote each computation**

Save in `docs/scratch/reconciliation/local-computations.md`, same format as Task 2's bundle-computations.md.

- [ ] **Step 3: Also quote `stateToCppJSON()` field-by-field**

This function in `replay_exporter.js` is the canonical local emitter — it both reads and shapes every snapshot field. Quote the whole function in `docs/scratch/reconciliation/local-computations.md` under a "## stateToCppJSON" section. It's the structural ground truth.

- [ ] **Step 4: Commit**

```bash
git add docs/scratch/reconciliation/local-computations.md
git commit -m "phase1(recon): catalog local js_engine derived-field computations"
```

---

### Task 4: Build the reconciliation table

**Files:**
- Create: `c:/libraries/PrismataAI/docs/derived-field-reconciliation.md`

- [ ] **Step 1: Build the comparison table**

For each in-scope field, compare the bundle and local quotes from Tasks 2 and 3. Classify as:
- **AGREE** — same inputs, same formula, same edge cases.
- **DISAGREE (cosmetic)** — equivalent value, different code style. Note both.
- **DISAGREE (material)** — different values in some game states. Site bundle wins; document what the local one does so we know what NOT to copy.
- **BUNDLE-ONLY** — local doesn't compute this; C++ must implement from scratch following the bundle.
- **LOCAL-ONLY** — local computes but bundle doesn't; renderer must not actually read it — verify and exclude.

- [ ] **Step 2: Write `docs/derived-field-reconciliation.md`**

Template:

```markdown
# Derived-Field Reconciliation — site-bundle authority

Per spec [2026-05-28-cpp-replay-export-pixijs-viewer-design.md](superpowers/specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md).

**Authority:** the shipped `prismata-ladder-site/public/js/prismata-engine.js`, hand-divergent from `js_engine/build_viewer_bundle.js`. Where local and shipped disagree, **shipped wins**.

**Date built:** YYYY-MM-DD against shipped-bundle sha `<git rev-parse HEAD:public/js/prismata-engine.js>` and PrismataAI master `<git rev-parse HEAD>`.

## Summary

| Field | Status | C++ source-of-truth |
|---|---|---|
| `maxAttack` | AGREE | port from local `StateHelper.js:XXX` |
| `whiteGoldEstimate` | DISAGREE (material) | port from `prismata-engine.js:XXXX` ONLY |
| ... | ... | ... |

## Per-field detail

### maxAttack
**Status:** AGREE
**Shipped:** [quoted code]
**Local:** [quoted code]
**C++ implementation note:** [one-liner, e.g. "loops attacker units; excludes sniped; sums attack score"]

### whiteGoldEstimate
**Status:** DISAGREE (material)
**Shipped:** [quoted code from prismata-engine.js]
**Local:** [quoted code from js_engine/StateHelper.js]
**Divergence:** [one paragraph — what local does that shipped doesn't, and why shipped is right]
**C++ implementation note:** match shipped exactly.

...
```

- [ ] **Step 3: Get user review on the reconciliation table**

Stop and have the user read `docs/derived-field-reconciliation.md`. Two things matter:
1. **Total scope:** does the field list look complete?
2. **Disagreement size:** how many fields are material disagreements? This directly sizes Phase 3 derived-field work.

- [ ] **Step 4: Commit the reconciliation doc**

```bash
git add docs/derived-field-reconciliation.md
git commit -m "phase1(recon): derived-field reconciliation table (site-bundle authority)"
```

- [ ] **Step 5: Decision gate — Phase 3 scope**

If the table shows ≥5 material disagreements OR any field is BUNDLE-ONLY with non-trivial computation, surface this to the user before Phase 3 starts — the C++ derived-field implementation may need its own sub-plan.

---

## Phase 2 — Browser-side viewer (`/replay/local` + bundle entry point)

Phase 2 ships an unlisted page on prismata.live that renders a dropped snapshot `.json.gz` through the existing PixiJS renderer. **Validated against existing `matchup_clean.js --save-replays` output before Phase 3 starts** — so the rendering path is proven before C++ work begins.

---

### Task 5: Branch + sanity-check the ladder workspace

**Files:** none changed in this task.

- [ ] **Step 1: Branch from ladder master**

```bash
cd c:/libraries/prismata-ladder
git status                            # should be clean; if not, stash/resolve first
git fetch origin
git checkout master
git pull
git checkout -b feature/replay-local-page
```

- [ ] **Step 2: Confirm dev server runs against current bundle**

```bash
cd c:/libraries/prismata-ladder/prismata-ladder-site
npm install   # idempotent
npm run dev   # starts Next dev server (Turbopack)
```

Open `http://localhost:3000/` in a browser. Confirm the site loads and an existing S3 replay works (`/replay/<somecode>`).

- [ ] **Step 3: Confirm tests run**

```bash
cd c:/libraries/prismata-ladder/prismata-ladder-site
npm test   # Vitest; should pass clean
```

- [ ] **Step 4: Sanity-check the existing internal `loadMatchupReplay` path**

In the browser dev console with a replay loaded:
```javascript
window.PrismataViewer    // confirm the global exists
Object.keys(window.PrismataViewer)   // confirm: NO loadFromBuffer / loadFromObject
```

Note the actual exposed surface for the next task.

- [ ] **Step 5: Stop the dev server, commit branch baseline**

```bash
# Nothing changed; just confirm clean state.
git status   # clean
```

---

### Task 6: Add `loadFromBuffer` to the shipped bundle (hand-edit)

**Files:**
- Modify: `prismata-ladder/prismata-ladder-site/public/js/prismata-engine.js` (HAND-EDIT — DO NOT rebuild via `build_viewer_bundle.js`)

**Why hand-edit:** Per spec, the shipped bundle is hand-divergent from `build_viewer_bundle.js` by ~112 lines in the IIFE area. Running the build script would regress the puzzle editor. We follow the same pattern as the existing `loadPuzzle` hand-edit.

- [ ] **Step 1: Read the existing entry points to pattern after**

```bash
grep -n "loadFromCode\|loadPuzzle\|loadMatchupReplay\|processArrayBuffer" \
  c:/libraries/prismata-ladder/prismata-ladder-site/public/js/prismata-engine.js
```

Read the function bodies of `loadFromCode` (around line 8290), `processArrayBuffer` (line 8310), and `loadMatchupReplay` (line 8352). Read the IIFE return at lines 9102-9124. Your new function will be a thin wrapper.

- [ ] **Step 2: Add `loadFromBuffer` as an internal function**

Insert immediately after `loadMatchupReplay` (around line 8400+, after its closing brace). Replace `<INSERT_LINE>` with the actual line number:

```javascript
    // Local-replay entry point: load a snapshot replay from an ArrayBuffer
    // (drag-drop on /replay/local). Supports gzipped JSON or raw JSON.
    // Distinct from loadFromCode (S3 fetch + click-list reconstruction)
    // because for snapshot replays states[] is pre-computed by C++ and we
    // skip the JS-engine reconstruction entirely.
    async function loadFromBuffer(arrayBuf) {
        if (!arrayBuf || arrayBuf.byteLength === 0) {
            throw new Error('loadFromBuffer: empty buffer');
        }
        // Detect gzip magic bytes (0x1f 0x8b)
        const bytes = new Uint8Array(arrayBuf);
        let jsonText;
        if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
            // Browser DecompressionStream path (works in modern Chrome/Edge/Firefox/Safari)
            const ds = new DecompressionStream('gzip');
            const decompressed = await new Response(
                new Blob([arrayBuf]).stream().pipeThrough(ds)
            ).arrayBuffer();
            jsonText = new TextDecoder().decode(decompressed);
        } else {
            jsonText = new TextDecoder().decode(arrayBuf);
        }
        const replayData = JSON.parse(jsonText);
        if (!replayData || !Array.isArray(replayData.states) || replayData.states.length === 0) {
            throw new Error('loadFromBuffer: replay has no states[] — not a snapshot replay');
        }
        loadMatchupReplay(replayData);
        return replayData;
    }
```

- [ ] **Step 3: Export `loadFromBuffer` from the IIFE return**

Find the return object at line ~9102. Add `loadFromBuffer: loadFromBuffer,` on a new line right after `loadFromCode: loadFromCode,`:

```javascript
    return {
        init: init, loadFromCode: loadFromCode,
        loadFromBuffer: loadFromBuffer,           // NEW
        initLive: initLive, processClick: processClick,
        // ...rest unchanged...
```

- [ ] **Step 4: Verify the bundle still parses and the site loads**

```bash
cd c:/libraries/prismata-ladder/prismata-ladder-site
npm run dev
```

Open `http://localhost:3000/`. In the browser dev console:
```javascript
typeof window.PrismataViewer.loadFromBuffer   // expect: 'function'
typeof window.PrismataViewer.loadFromCode     // expect: 'function' (sanity — didn't break existing)
```

Open an existing replay page (`/replay/<code>`). Confirm it still renders normally — proves we didn't break `loadFromCode`.

- [ ] **Step 5: Smoke-test `loadFromBuffer` with an existing matchup replay**

Find an existing matchup `.json.gz` (look in `c:/libraries/PrismataAI/bin/asset/replays/`). In the browser console with the dev server running:

```javascript
const file = await fetch('/path/to/test/game.json.gz').then(r => r.arrayBuffer());
const replay = await window.PrismataViewer.loadFromBuffer(file);
console.log(replay.states.length, 'states loaded');
window.PrismataViewer.setStateIndex(0);   // jump to start
// Visually: the board on /replay/<anything> should redraw to the first state
```

Expected: the function returns the replay object, `states.length` > 0, and either: (a) you're already on a replay page and the board redraws, or (b) we'll wire the page in Task 7.

- [ ] **Step 6: Commit the bundle hand-edit**

```bash
cd c:/libraries/prismata-ladder
git add prismata-ladder-site/public/js/prismata-engine.js
git commit -m "feat(engine-bundle): add loadFromBuffer for local snapshot replays

Hand-edit (NOT a rebuild — bundle is divergent from build_viewer_bundle.js
by ~112 lines per 2026-05-28 build+diff). Pattern after loadPuzzle.
Internal loadMatchupReplay/processArrayBuffer are unchanged; new export
is a thin wrapper that gunzips if needed and calls loadMatchupReplay.

Refs: docs/superpowers/specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md"
```

---

### Task 7: Create the `LocalReplayDropzone` component

**Files:**
- Create: `prismata-ladder/prismata-ladder-site/src/app/replay/local/LocalReplayDropzone.tsx`
- Create: `prismata-ladder/prismata-ladder-site/src/app/replay/local/__tests__/LocalReplayDropzone.test.tsx`

- [ ] **Step 1: Write the failing test**

Create the test file:

```tsx
// src/app/replay/local/__tests__/LocalReplayDropzone.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LocalReplayDropzone from '../LocalReplayDropzone';

describe('LocalReplayDropzone', () => {
    it('renders a drop hint when empty', () => {
        render(<LocalReplayDropzone onReplayLoaded={() => {}} />);
        expect(screen.getByText(/drag/i)).toBeInTheDocument();
    });

    it('calls onReplayLoaded after a successful drop', async () => {
        // Mock PrismataViewer.loadFromBuffer
        const mockReplay = { p0: 'A', p1: 'B', states: [{}], turns: 1 };
        (window as any).PrismataViewer = {
            loadFromBuffer: vi.fn().mockResolvedValue(mockReplay),
        };

        const onLoaded = vi.fn();
        render(<LocalReplayDropzone onReplayLoaded={onLoaded} />);

        const file = new File([new Uint8Array([0x7b, 0x7d])], 'game.json', { type: 'application/json' });
        const input = screen.getByTestId('replay-file-input') as HTMLInputElement;
        fireEvent.change(input, { target: { files: [file] } });

        await waitFor(() => {
            expect(onLoaded).toHaveBeenCalledWith(mockReplay);
        });
    });

    it('surfaces an error if loadFromBuffer rejects', async () => {
        (window as any).PrismataViewer = {
            loadFromBuffer: vi.fn().mockRejectedValue(new Error('bad replay')),
        };

        render(<LocalReplayDropzone onReplayLoaded={() => {}} />);
        const file = new File([new Uint8Array([0])], 'x', { type: '' });
        fireEvent.change(screen.getByTestId('replay-file-input'), { target: { files: [file] } });

        await waitFor(() => {
            expect(screen.getByText(/bad replay/i)).toBeInTheDocument();
        });
    });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd c:/libraries/prismata-ladder/prismata-ladder-site
npx vitest run src/app/replay/local/__tests__/LocalReplayDropzone.test.tsx
```

Expected: FAIL — module `../LocalReplayDropzone` not found.

- [ ] **Step 3: Implement the component**

Create the file:

```tsx
// src/app/replay/local/LocalReplayDropzone.tsx
'use client';

import { useCallback, useState } from 'react';

interface Props {
    onReplayLoaded: (replay: any) => void;
}

declare global {
    interface Window {
        PrismataViewer?: {
            loadFromBuffer: (buf: ArrayBuffer) => Promise<any>;
        };
    }
}

export default function LocalReplayDropzone({ onReplayLoaded }: Props) {
    const [error, setError] = useState<string | null>(null);
    const [isDragging, setIsDragging] = useState(false);

    const handleFile = useCallback(async (file: File) => {
        setError(null);
        if (!window.PrismataViewer?.loadFromBuffer) {
            setError('Engine bundle not loaded — refresh the page.');
            return;
        }
        try {
            const buf = await file.arrayBuffer();
            const replay = await window.PrismataViewer.loadFromBuffer(buf);
            onReplayLoaded(replay);
        } catch (e: any) {
            setError(e?.message ?? 'Failed to load replay');
        }
    }, [onReplayLoaded]);

    const onDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleFile(file);
    }, [handleFile]);

    const onFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) handleFile(file);
    }, [handleFile]);

    return (
        <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={onDrop}
            style={{
                border: `2px dashed ${isDragging ? '#4af' : '#888'}`,
                padding: '2rem',
                textAlign: 'center',
                borderRadius: '8px',
                background: isDragging ? '#0a2a4a' : 'transparent',
            }}
        >
            <p>Drag a replay <code>.json.gz</code> here, or:</p>
            <input
                data-testid="replay-file-input"
                type="file"
                accept=".json,.gz,.json.gz,application/json,application/gzip"
                onChange={onFileInputChange}
            />
            {error && <p style={{ color: '#f66', marginTop: '1rem' }}>{error}</p>}
        </div>
    );
}
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
npx vitest run src/app/replay/local/__tests__/LocalReplayDropzone.test.tsx
```

Expected: PASS, all 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/app/replay/local/LocalReplayDropzone.tsx src/app/replay/local/__tests__/
git commit -m "feat(replay-local): add LocalReplayDropzone with file + drag-drop input"
```

---

### Task 8: Build the `/replay/local` page

**Files:**
- Create: `prismata-ladder/prismata-ladder-site/src/app/replay/local/page.tsx`

- [ ] **Step 1: Read the existing replay page to pattern after**

Read `prismata-ladder/prismata-ladder-site/src/app/replay/[code]/page.tsx` end-to-end. Note how it:
- Loads the engine bundle via `<script>` tag (the `window.PrismataViewer` global setup).
- Loads `cardMeta` and `bundleAssets` via `PrismataViewer.getCardMeta()` / `getAssets()`.
- Builds the `replayTiming` and `timeline` props for `<PrismataBoard>`.
- Renders the playback controls.

You're going to mirror the structure but skip the S3 fetch and substitute the dropzone.

- [ ] **Step 2: Implement `page.tsx`**

```tsx
// src/app/replay/local/page.tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import LocalReplayDropzone from './LocalReplayDropzone';
import { PrismataBoard } from '@/components/game-renderer';
import { buildReplayTiming, buildTimeline } from '@/components/game-renderer/replay-timeline';
// NOTE: Confirm these imports against the actual game-renderer/index.ts exports
// when running this task; adjust if the actual export names differ.

export default function LocalReplayPage() {
    const [bundleReady, setBundleReady] = useState(false);
    const [replay, setReplay] = useState<any | null>(null);
    const [stateIndex, setStateIndex] = useState(0);
    const [cardMeta, setCardMeta] = useState<any>(null);
    const [bundleAssets, setBundleAssets] = useState<any>(null);

    // Wait for the engine bundle to be loaded by the <Script> tag in layout.
    useEffect(() => {
        function checkReady() {
            if (typeof window !== 'undefined' && (window as any).PrismataViewer?.loadFromBuffer) {
                setBundleReady(true);
                setCardMeta((window as any).PrismataViewer.getCardMeta());
                setBundleAssets((window as any).PrismataViewer.getAssets());
            } else {
                setTimeout(checkReady, 50);
            }
        }
        checkReady();
    }, []);

    const handleReplayLoaded = useCallback((r: any) => {
        setReplay(r);
        setStateIndex(0);
    }, []);

    if (!bundleReady) {
        return <main style={{ padding: '2rem' }}><p>Loading engine bundle…</p></main>;
    }

    return (
        <main style={{ padding: '1rem', fontFamily: 'system-ui' }}>
            <h1 style={{ marginBottom: '1rem' }}>Local Replay Viewer (unlisted)</h1>
            <p style={{ color: '#aaa', marginBottom: '1rem' }}>
                Drop a snapshot <code>.json.gz</code> from <code>matchup_clean.js --save-replays</code>
                or <code>Prismata_Standalone --save-replays</code>. Files stay in your browser.
            </p>

            {!replay && <LocalReplayDropzone onReplayLoaded={handleReplayLoaded} />}

            {replay && (
                <>
                    <div style={{ display: 'flex', gap: '1rem', margin: '1rem 0', alignItems: 'center' }}>
                        <button onClick={() => setReplay(null)}>← New replay</button>
                        <span>{replay.p0} vs {replay.p1} — winner: {replay.winnerName ?? replay.winner}</span>
                        <span style={{ marginLeft: 'auto' }}>
                            State {stateIndex + 1} / {replay.states.length}
                        </span>
                    </div>

                    <PrismataBoard
                        gameState={replay.states[stateIndex]}
                        cardMeta={cardMeta}
                        bundleAssets={bundleAssets}
                        p0Info={{ displayName: replay.p0 }}
                        p1Info={{ displayName: replay.p1 }}
                    />

                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                        <button onClick={() => setStateIndex(0)}>⏮</button>
                        <button onClick={() => setStateIndex((i) => Math.max(0, i - 1))}>◀</button>
                        <button onClick={() => setStateIndex((i) => Math.min(replay.states.length - 1, i + 1))}>▶</button>
                        <button onClick={() => setStateIndex(replay.states.length - 1)}>⏭</button>
                        <input
                            type="range"
                            min={0}
                            max={replay.states.length - 1}
                            value={stateIndex}
                            onChange={(e) => setStateIndex(parseInt(e.target.value, 10))}
                            style={{ flex: 1 }}
                        />
                    </div>

                    {replay.actions?.[stateIndex] && (
                        <p style={{ color: '#aaa', marginTop: '0.5rem' }}>
                            {replay.actions[stateIndex]}
                        </p>
                    )}
                </>
            )}
        </main>
    );
}
```

- [ ] **Step 3: Confirm engine bundle script tag is loaded for this route**

Check `prismata-ladder/prismata-ladder-site/src/app/layout.tsx` (or the replay route's layout). The `prismata-engine.js` `<Script>` tag should already load globally. If it's currently scoped to `/replay/[code]/layout.tsx` only, lift it to a shared parent layout so `/replay/local` also gets it. Confirm via dev tools network tab on the new page.

- [ ] **Step 4: Manual smoke test with a real existing matchup replay**

```bash
npm run dev
```

Open `http://localhost:3000/replay/local`. Drag in an existing `.json.gz` from `c:/libraries/PrismataAI/bin/asset/replays/<somedir>/game_0001.json.gz`. Confirm:
- No console errors.
- Board renders with units in the expected positions.
- Scrubbing the slider redraws the board.
- The action label updates per state.

If `<PrismataBoard>` complains about prop shape, adjust the props in Step 2 to match the actual interface (the props in the existing `/replay/[code]/page.tsx` are the source of truth).

- [ ] **Step 5: Commit**

```bash
git add src/app/replay/local/page.tsx
git commit -m "feat(replay-local): add unlisted /replay/local page with PixiJS rendering"
```

---

### Task 9: Visual parity check against a known matchup replay

**Files:** none — verification task.

- [ ] **Step 1: Find a recent existing matchup replay with a clean game**

Look in `c:/libraries/PrismataAI/bin/asset/replays/` for a directory with `game_*.json.gz`. Pick one ~20 turns long. Note `p0`, `p1`, winner.

- [ ] **Step 2: Load it in `/replay/local` AND in the old viewer side-by-side**

The old viewer: open the existing replay-to-HTML output, or run `node js_engine/replay_to_html.js <path>` and open the result.

The new viewer: `http://localhost:3000/replay/local`, drag in the same file.

- [ ] **Step 3: Watch the same 5 key moments in both viewers**

Compare visually at: (1) turn 1 end, (2) turn 5 end, (3) first breach if any, (4) ~halfway, (5) game over.

For each moment, check: same units on the table, same mana, same defenders assigned, same blocker state, same gold-estimate / attack number where displayed.

If any divergence — that's a Phase 1 / Phase 2 bug to flag. Likely candidate: a derived field the renderer reads but the snapshot doesn't include. Log into `docs/scratch/reconciliation/phase2-visual-deltas.md`.

- [ ] **Step 4: Commit any findings**

```bash
cd c:/libraries/PrismataAI
git add docs/scratch/reconciliation/phase2-visual-deltas.md   # if any deltas
git commit -m "phase2(verify): visual-parity findings against old viewer"
```

If no deltas: just note "Phase 2 visual parity clean, no deltas." in the commit message of an empty-tree no-op (skip if nothing changed).

---

### Task 10: Deploy `/replay/local` to prismata.live (unlisted)

**Files:** depends on existing deploy workflow.

- [ ] **Step 1: Confirm deploy mechanism**

Check `prismata-ladder/` for `.github/workflows/`, a `deploy.sh`, or memory `project_prismata_live_infrastructure.md`. The site auto-deploys via GitHub webhook on push to master per memory.

- [ ] **Step 2: Open PR from `feature/replay-local-page` → `master`**

```bash
cd c:/libraries/prismata-ladder
git push -u origin feature/replay-local-page
gh pr create --base master --title "feat(replay-local): unlisted /replay/local snapshot drag-drop page" \
  --body "Adds /replay/local — client-side snapshot replay viewer fed by drag-dropped .json.gz from matchup_clean.js or (Phase 3) Prismata_Standalone --save-replays. Hand-edited prismata-engine.js to add loadFromBuffer entry point; bundle build script NOT touched (per never-rebuild rule).

Spec: PrismataAI repo docs/superpowers/specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 3: User reviews PR + confirms merge**

Stop and have the user inspect the diff. The bundle hand-edit is the highest-attention piece; confirm it matches the editor-extension pattern.

- [ ] **Step 4: Merge + verify on prismata.live**

After merge and auto-deploy (per webhook), open `https://prismata.live/replay/local`. Drag in a known-good matchup replay. Confirm renders correctly in production.

- [ ] **Step 5: Phase 2 done — Phase 3 can start (or skip if not ready)**

End of Phase 2. The rendering pipeline is fully validated against the matchup oracle; Phase 3's C++ output renders the same way once it lands.

---

## Phase 3 — C++ snapshot serializer (Dave's engine_v1)

Adds `--save-replays <dir>` to `PrismataAI-dave-master/source/testing/`. Verified true no-op when disabled. Output matches the matchup oracle field-by-field and the shipped-bundle derived-field semantics (per Phase 1 table). Renders in `/replay/local` (Phase 2 deliverable).

**Gate:** ask Dave the two engine_v1 questions (StateHelper coverage; Move atomicity) before starting Task 13. Their answers affect Tasks 13 and 15.

---

### Task 11: Branch the dave-master worktree + baseline build

**Files:** none.

- [ ] **Step 1: Confirm dave-master worktree state**

```bash
cd c:/libraries/PrismataAI-dave-master
git status                         # should be clean
git branch --show-current          # expect: dave-master-jsonclean
```

- [ ] **Step 2: Create child branch for this work**

```bash
git checkout -b feature/save-replays
```

- [ ] **Step 3: Baseline build**

**Important:** the `dave-master` worktree builds differently from the main PrismataAI repo. CLAUDE.md documents `x86 + v143` for the main repo, but Dave's tree uses **x64 + PlatformToolset v145** and produces `PrismataAI.exe` (not `Prismata_Standalone.exe`) for the standalone. The plan invocation reflects the dave-master config:

```bash
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI-dave-master/visualstudio/Prismata.sln" \
  //t:Rebuild //p:Configuration=Release //p:Platform=x64 //p:PlatformToolset=v145 //m
```

Expected: `bin/Prismata_Testing.exe` and `bin/PrismataAI.exe` rebuilt cleanly. The GUI project may fail with SFML 3 vs SFML 2 API drift — that's pre-existing and unrelated; build only Testing + Standalone if needed.

**Known pre-existing vcxproj omissions** (resolved in commit `bfdac4e` on `feature/save-replays`): five orphan sources were not wired into the projects — `NeuralNet.{h,cpp}`, `Player_PortfolioGreedySearch.{h,cpp}`, `Player_RobustRootSearch.{h,cpp}`, `Player_RootParallelAlphaBeta.{h,cpp}` (in `Prismata_AI.vcxproj`), and `Random.{h,cpp}` (in `Prismata_Engine.vcxproj`). Already on the feature branch as a prerequisite commit.

- [ ] **Step 4: Run a baseline 2-game tournament with NO new code**

Pick an existing fast tournament config from `bin/asset/config/config.txt` (e.g. one with `"rounds":2`). Run it and capture the result + timing:

```bash
cd c:/libraries/PrismataAI-dave-master/bin
./Prismata_Testing.exe > baseline.log 2>&1
```

Save `baseline.log`. This is the reference for the no-op gate in Task 14.

- [ ] **Step 5: Commit branch baseline (no code changes yet)**

```bash
# Nothing to commit; just ensure clean.
git status   # clean
```

---

### Task 12: Add `--save-replays` flag plumbing (no-op stub)

**Files:**
- Modify: `PrismataAI-dave-master/source/testing/main.cpp` (or wherever CLI args are parsed)
- Modify: `PrismataAI-dave-master/source/testing/Tournament.h` (add `_saveReplaysDir` field)
- Modify: `PrismataAI-dave-master/source/testing/Tournament.cpp` (parse `"saveReplays"` config field; do nothing with it yet)
- Modify: `PrismataAI-dave-master/bin/asset/config/config.txt` (optional `"saveReplays"` field on a test tournament block)

The flag's plumbing lands first WITHOUT touching any AI/game-loop code. Validates the no-op invariant before any real serialization exists.

- [ ] **Step 1: Read existing CLI parsing in `main.cpp`**

```bash
grep -n "argv\|--" c:/libraries/PrismataAI-dave-master/source/testing/main.cpp
```

If there's no existing CLI arg parsing for `Prismata_Testing.exe`, we'll add `--save-replays` via the Tournament JSON config block instead (which already supports `name`, `rounds`, `players`, `threads`, etc.).

- [ ] **Step 2: Add `_saveReplaysDir` to `Tournament.h`**

```cpp
// In Tournament.h, in the private section:
std::string _saveReplaysDir;   // empty = disabled
```

- [ ] **Step 3: Parse the field in `Tournament.cpp`**

Find where Tournament parses its JSON config (around line 24-39 per recon). Add:

```cpp
// In Tournament::Tournament(...) constructor's JSON parsing block:
if (config.HasMember("saveReplays") && config["saveReplays"].IsString()) {
    _saveReplaysDir = config["saveReplays"].GetString();
}
```

- [ ] **Step 4: Add a test config block to `config.txt`**

Append (or modify an existing fast tournament):

```jsonc
{ "run":true, "type":"Tournament", "name":"SaveReplaysSmoke", "rounds":2,
  "UpdateIntervalSec":0, "Threads":1, "RandomCards":8,
  "saveReplays":"bin/asset/replays/dave_smoke",   // NEW
  "players":[ {"name":"HardestAIUCT","group":1}, {"name":"HardestAIUCT","group":2}] }
```

- [ ] **Step 5: Build + run with the flag set; confirm nothing else changes**

Build (see Task 11 Step 3). Run the smoke tournament. Confirm: no errors, no created files in the saveReplays dir (because no serialization code exists yet), results identical to baseline.

- [ ] **Step 6: Commit**

```bash
cd c:/libraries/PrismataAI-dave-master
git add source/testing/Tournament.{h,cpp} bin/asset/config/config.txt
git commit -m "feat(tournament): parse saveReplays config field (no-op stub)"
```

---

### Task 13: No-op invariant verification gate

**Files:** none — pure verification.

This is the gate the spec requires before any serialization code lands. We confirm that adding the flag (even with `saveReplays: ""` left unset) has no effect on tournament results.

- [ ] **Step 1: Run the baseline tournament WITHOUT the save-replays config field**

Edit `config.txt` so the smoke tournament does NOT have `"saveReplays"` set. Run:

```bash
cd c:/libraries/PrismataAI-dave-master/bin
./Prismata_Testing.exe > flag_off.log 2>&1
```

- [ ] **Step 2: Run the SAME tournament WITH `"saveReplays":"<dir>"` set**

Re-add the `saveReplays` field. Run:

```bash
./Prismata_Testing.exe > flag_on.log 2>&1
```

- [ ] **Step 3: Diff the result lines**

```bash
diff <(grep -E "^(Result|Win|P[12]|Total|Game [0-9]+:)" flag_off.log) \
     <(grep -E "^(Result|Win|P[12]|Total|Game [0-9]+:)" flag_on.log)
```

Expected: no diff. (Tournament uses PID+time random seed by default, so two cold runs of the same config aren't byte-identical anyway. For a real no-op proof we need to fix the seed first.)

- [ ] **Step 4: If results differ, fix the seeding so flag-on/flag-off comparison is meaningful**

Either: (a) add a `"seed":<int>` field to the Tournament config that overrides the PID-based seed, OR (b) run each tournament twice and confirm flag-on results land in the same envelope as flag-off-twice (statistical equivalence within ±√n noise).

For now, statistical equivalence is acceptable. Run each side 3× and confirm win counts are within ±1 across the runs.

- [ ] **Step 5: Document the no-op result**

Append to `docs/superpowers/specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md` under a new "Verification Log" section:

```markdown
## Verification Log

**2026-MM-DD — Phase 3 Task 13 no-op gate (stub):**
Ran `SaveReplaysSmoke` (2 rounds, HardestAIUCT vs HardestAIUCT) three times with
`saveReplays` set and three times without. Win counts: with={A,B,C}, without={D,E,F}.
Within noise envelope. Stub flag is a true no-op.
```

Commit:

```bash
cd c:/libraries/PrismataAI
git add docs/superpowers/specs/2026-05-28-cpp-replay-export-pixijs-viewer-design.md
git commit -m "phase3(verify): no-op gate log for stub --save-replays flag"
```

---

### Task 14: `ReplaySerializer` skeleton — header + empty impl

**Files:**
- Create: `PrismataAI-dave-master/source/testing/ReplaySerializer.h`
- Create: `PrismataAI-dave-master/source/testing/ReplaySerializer.cpp`
- Modify: `PrismataAI-dave-master/visualstudio/Prismata_Testing.vcxproj` (add the new sources to the Static Release + Release configs)

- [ ] **Step 1: Write the header**

```cpp
// source/testing/ReplaySerializer.h
#pragma once

#include <string>
#include <vector>
#include "../rapidjson/document.h"
#include "../engine/GameState.h"
#include "../engine/Move.h"

namespace Prismata
{

// Accumulates snapshots over the course of a single game, then writes
// one .json.gz file in the matchup-format schema the PixiJS viewer eats.
//
// Lifetime: one instance per game. Owned by TournamentGame when enabled;
// not constructed at all when --save-replays is disabled (zero overhead).
class ReplaySerializer
{
public:
    ReplaySerializer(const std::string & p0Name,
                     const std::string & p1Name,
                     const std::vector<std::string> & cardSet);

    // Capture the initial state (turn 0) before any move is applied.
    void captureInitialState(const GameState & state);

    // Capture per-action snapshots for a turn. Either inline-during-apply
    // (if Game applies actions one at a time) or post-hoc-via-clone-replay
    // (if Move is atomic) — Task 16 picks the approach based on Dave's answer.
    void captureMove(const GameState & preMoveState,
                     const Move & move,
                     const GameState & postMoveState);

    // Finalize: set winner + write `<dir>/game_<idx>.json.gz`.
    bool finalize(int winner,
                  int turns,
                  const std::string & outDir,
                  int gameIndex);

private:
    std::string _p0;
    std::string _p1;
    std::vector<std::string> _cardSet;
    rapidjson::Document _doc;        // root document; states[] / actions[] / turnBoundaries[]
    rapidjson::Value _states;        // owned by _doc
    rapidjson::Value _actions;
    rapidjson::Value _turnBoundaries;

    // Serialize one GameState to a JSON value (allocated in _doc.GetAllocator()).
    rapidjson::Value serializeState(const GameState & state);
};

} // namespace Prismata
```

- [ ] **Step 2: Write the empty .cpp**

```cpp
// source/testing/ReplaySerializer.cpp
#include "ReplaySerializer.h"

namespace Prismata
{

ReplaySerializer::ReplaySerializer(const std::string & p0Name,
                                   const std::string & p1Name,
                                   const std::vector<std::string> & cardSet)
    : _p0(p0Name), _p1(p1Name), _cardSet(cardSet)
{
    _doc.SetObject();
    _states.SetArray();
    _actions.SetArray();
    _turnBoundaries.SetArray();
}

void ReplaySerializer::captureInitialState(const GameState & /*state*/) {
    // Filled in Task 15.
}

void ReplaySerializer::captureMove(const GameState & /*pre*/,
                                   const Move & /*move*/,
                                   const GameState & /*post*/) {
    // Filled in Task 16.
}

bool ReplaySerializer::finalize(int /*winner*/, int /*turns*/,
                                const std::string & /*outDir*/, int /*gameIndex*/) {
    // Filled in Task 17.
    return false;
}

rapidjson::Value ReplaySerializer::serializeState(const GameState & /*state*/) {
    // Filled in Task 15.
    rapidjson::Value v(rapidjson::kObjectType);
    return v;
}

} // namespace Prismata
```

- [ ] **Step 3: Add the new sources to the VS project**

Open `visualstudio/Prismata_Testing.vcxproj` in a text editor. Find the `<ItemGroup>` for `<ClCompile>` source files; add `<ClCompile Include="..\source\testing\ReplaySerializer.cpp" />`. Find the `<ItemGroup>` for `<ClInclude>`; add `<ClInclude Include="..\source\testing\ReplaySerializer.h" />`. Per CLAUDE.md, also verify the Static Release config has matching include paths if any new include dirs were added (we didn't — `source/engine` is already on the path).

- [ ] **Step 4: Build + confirm linking**

```bash
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI-dave-master/visualstudio/Prismata.sln" \
  //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m
```

Expected: clean build. Skeleton compiles even though it does nothing.

- [ ] **Step 5: Commit**

```bash
cd c:/libraries/PrismataAI-dave-master
git add source/testing/ReplaySerializer.{h,cpp} visualstudio/Prismata_Testing.vcxproj
git commit -m "feat(serializer): ReplaySerializer skeleton (empty methods)"
```

---

### Task 15: Implement static field serialization (mana / phase / supply / table[])

**Files:**
- Modify: `PrismataAI-dave-master/source/testing/ReplaySerializer.cpp`
- Create: `PrismataAI-dave-master/source/testing/tests/serializer_test.cpp` (standalone test driver)

This task handles the *easy* fields — the structural ones that aren't derived. Derived fields wait for Task 17 (after the reconciliation table is the implementation guide).

- [ ] **Step 1: Write a failing standalone test**

Create the test driver:

```cpp
// source/testing/tests/serializer_test.cpp
//
// Standalone test driver. Compile and run manually:
//   cl /EHsc /std:c++17 /I..\..\rapidjson /I..\..\engine /I..\..\ai \
//      serializer_test.cpp ..\ReplaySerializer.cpp ...other deps... /Fe:serializer_test.exe
// or add a new VS project / CMake target if test infra exists.
//
// Initial test: serialize a freshly-initialized GameState and assert the JSON
// contains the structural keys we expect.

#include <iostream>
#include <string>
#include "../ReplaySerializer.h"
#include "../../engine/GameState.h"
#include "../../engine/Constants.h"
#include "../../rapidjson/writer.h"
#include "../../rapidjson/stringbuffer.h"

using namespace Prismata;

int main() {
    // Build a minimal valid GameState. The exact construction depends on
    // engine_v1's GameState API — match how TournamentGame.cpp builds one.
    GameState state;
    state.beginGame();   // or equivalent — match how Tournament sets up

    ReplaySerializer ser("PlayerA", "PlayerB", {"Drone", "Engineer", "Tarsier"});
    ser.captureInitialState(state);

    // Extract via finalize (writes to a temp file we read back).
    bool ok = ser.finalize(/*winner*/0, /*turns*/1, "./test_out", 0);
    if (!ok) { std::cerr << "finalize failed\n"; return 1; }

    // Read the written file and assert structural keys.
    // (Use rapidjson to parse the gunzipped content — simplest: leave .json
    //  uncompressed in test mode, or test the in-memory _doc directly.)

    std::cout << "OK\n";
    return 0;
}
```

Compile and run (will fail because `serializeState` is still empty).

- [ ] **Step 2: Implement `serializeState` — structural fields only**

Replace the stub in `ReplaySerializer.cpp`:

```cpp
rapidjson::Value ReplaySerializer::serializeState(const GameState & state) {
    auto & a = _doc.GetAllocator();
    rapidjson::Value v(rapidjson::kObjectType);

    // ---- Mana strings ----
    // engine_v1 mana → digits + B/G/C/H letter encoding (see CLAUDE.md mergedDeck note)
    v.AddMember("whiteMana", rapidjson::Value(state.getResources(0).getString().c_str(), a), a);
    v.AddMember("blackMana", rapidjson::Value(state.getResources(1).getString().c_str(), a), a);

    // ---- Turn / phase ----
    v.AddMember("turn", static_cast<int>(state.getActivePlayer()), a);
    v.AddMember("numTurns", static_cast<int>(state.getTurnNumber()), a);

    // phase string: engine_v1 has no PHASE_BREACH (glassBroken is a flag, not a phase).
    const char * phaseStr = "action";
    if (state.getActivePhase() == Phases::Defense) phaseStr = "defense";
    else if (state.getActivePhase() == Phases::Confirm) phaseStr = "confirm";
    v.AddMember("phase", rapidjson::Value(phaseStr, a), a);
    v.AddMember("glassBroken", state.glassBroken(), a);   // adjust API name if needed

    // ---- Supply arrays ----
    rapidjson::Value cards(rapidjson::kArrayType);
    rapidjson::Value whiteTotal(rapidjson::kArrayType);
    rapidjson::Value blackTotal(rapidjson::kArrayType);
    rapidjson::Value whiteSpent(rapidjson::kArrayType);
    rapidjson::Value blackSpent(rapidjson::kArrayType);

    for (size_t cardId = 0; cardId < state.numCards(); ++cardId) {
        const CardType & ct = state.getCardType(cardId);
        cards.PushBack(rapidjson::Value(ct.getUIName().c_str(), a), a);
        whiteTotal.PushBack(state.getCardSupply(0, cardId), a);
        blackTotal.PushBack(state.getCardSupply(1, cardId), a);
        whiteSpent.PushBack(state.getCardBought(0, cardId), a);
        blackSpent.PushBack(state.getCardBought(1, cardId), a);
    }
    v.AddMember("cards", cards, a);
    v.AddMember("whiteTotalSupply", whiteTotal, a);
    v.AddMember("blackTotalSupply", blackTotal, a);
    v.AddMember("whiteSupplySpent", whiteSpent, a);
    v.AddMember("blackSupplySpent", blackSpent, a);

    // ---- table[] (per-instance) ----
    rapidjson::Value table(rapidjson::kArrayType);
    for (size_t i = 0; i < state.numCards(); ++i) {
        // engine_v1 iterates via getNumCards / getCardByID — use the actual API
        const Card & c = state.getCardByID(i);
        rapidjson::Value inst(rapidjson::kObjectType);

        inst.AddMember("instId", static_cast<int>(c.getID()), a);
        inst.AddMember("cardName", rapidjson::Value(c.getType().getUIName().c_str(), a), a);
        inst.AddMember("owner", static_cast<int>(c.getPlayer()), a);
        inst.AddMember("health", c.currentHealth(), a);
        inst.AddMember("damage", c.getDamageTaken(), a);
        inst.AddMember("role", rapidjson::Value(c.getStatusString().c_str(), a), a);
        inst.AddMember("deadness", rapidjson::Value(c.isAlive() ? "alive" : "dead", a), a);   // refine in Task 17
        inst.AddMember("constructionTime", c.getConstructionTime(), a);
        inst.AddMember("charge", c.getCharge(), a);
        inst.AddMember("delay", c.getDelay(), a);
        inst.AddMember("lifespan", c.getLifespan(), a);
        inst.AddMember("disruptDamage", c.currentChill(), a);
        inst.AddMember("blocking", c.isBlocking(), a);
        inst.AddMember("boughtThisPhase", c.boughtThisTurn(), a);

        table.PushBack(inst, a);
    }
    v.AddMember("table", table, a);

    return v;
}
```

**Note:** The exact API names (`getResources`, `getActivePlayer`, `getCardSupply`, `getCardBought`, `getCardByID`, `numCards`, `Card::getStatusString`, etc.) are *engine_v1 API guesses*. Adjust to actual names by reading `source/engine/GameState.h` and `source/engine/Card.h` in the dave-master worktree. If a field has no engine_v1 accessor, that's a finding to record.

- [ ] **Step 3: Fill in `captureInitialState` and `captureMove` stubs to call `serializeState`**

```cpp
void ReplaySerializer::captureInitialState(const GameState & state) {
    auto & a = _doc.GetAllocator();
    _turnBoundaries.PushBack(0, a);
    _states.PushBack(serializeState(state), a);
    _actions.PushBack(rapidjson::Value("Start of game", a), a);
}

void ReplaySerializer::captureMove(const GameState & /*pre*/,
                                   const Move & move,
                                   const GameState & post) {
    auto & a = _doc.GetAllocator();
    // Per-turn boundary marker
    _turnBoundaries.PushBack(static_cast<int>(_states.Size()), a);

    // For now (Task 15), capture only the post-move state. Per-action stepping
    // lands in Task 16 once Dave answers the Move-atomicity question.
    _states.PushBack(serializeState(post), a);
    _actions.PushBack(rapidjson::Value(move.toHistoryString().c_str(), a), a);
}
```

- [ ] **Step 4: Run the test; expect it to pass**

```bash
# Build and run the standalone test driver (use compiler invocation from Step 1).
./serializer_test.exe
```

Expected: prints `OK`. If any structural field crashes (e.g. wrong accessor name), fix the engine_v1 API guess and rebuild.

- [ ] **Step 5: Commit**

```bash
git add source/testing/ReplaySerializer.cpp source/testing/tests/serializer_test.cpp
git commit -m "feat(serializer): serialize structural fields (mana/phase/supply/table)"
```

---

### Task 16: Per-action stepping via `Game::doAction` hook

**Files:**
- Modify: `PrismataAI-dave-master/source/engine/Game.h` (add hook member + setter)
- Modify: `PrismataAI-dave-master/source/engine/Game.cpp` (invoke hook from `doAction`)
- Modify: `PrismataAI-dave-master/source/testing/ReplaySerializer.h` (add `captureActionApplied`)
- Modify: `PrismataAI-dave-master/source/testing/ReplaySerializer.cpp` (impl `captureActionApplied`; simplify `captureMove`)
- Modify: `PrismataAI-dave-master/source/testing/TournamentGame.cpp` (wire the hook when `_serializer` is non-null)

**Resolved (2026-05-28 from the code):** `Game::doAction(...)` is the single chokepoint every Action passes through. We hook there once and capture every action automatically.

- [ ] **Step 1: Add the hook member + setter to `Game.h`**

In `Game.h`, near the other private members:

```cpp
#include <functional>

class Action;   // forward-declare if not already

class Game
{
public:
    using ActionAppliedHook = std::function<void(const GameState &, const Action &)>;
    void setActionAppliedHook(ActionAppliedHook hook) { _actionAppliedHook = std::move(hook); }

    // ...existing public API unchanged...

private:
    ActionAppliedHook _actionAppliedHook;   // default: empty/null, true no-op
    // ...existing private members...
};
```

The hook is default-empty — when no serializer is active, every action does one extra `if (_actionAppliedHook)` check against a null `std::function`, which is a single branch on a pointer. Negligible vs the existing `doAction` cost.

- [ ] **Step 2: Invoke the hook from `Game::doAction`**

In `Game.cpp:88-91`, change:

```cpp
bool Game::doAction(const Action & action)
{
    return m_state.doAction(action);
}
```

to:

```cpp
bool Game::doAction(const Action & action)
{
    bool ok = m_state.doAction(action);
    if (ok && _actionAppliedHook) _actionAppliedHook(m_state, action);
    return ok;
}
```

- [ ] **Step 3: Add `captureActionApplied` to the serializer (header + impl)**

In `ReplaySerializer.h`, add the declaration in the public section:

```cpp
// Called from Game::doAction's hook after each Action is applied.
void captureActionApplied(const GameState & state, const Action & action);
```

In `ReplaySerializer.cpp`:

```cpp
void ReplaySerializer::captureActionApplied(const GameState & state, const Action & action) {
    auto & a = _doc.GetAllocator();
    _states.PushBack(serializeState(state), a);
    _actions.PushBack(rapidjson::Value(action.toHistoryString().c_str(), a), a);
}
```

- [ ] **Step 4: Simplify `captureMove` — only records turn boundaries now**

The hook produces all per-action states automatically. `captureMove` becomes just a turn-boundary marker:

```cpp
void ReplaySerializer::captureMove(const GameState & /*pre*/,
                                   const Move & /*move*/,
                                   const GameState & /*post*/) {
    auto & a = _doc.GetAllocator();
    _turnBoundaries.PushBack(static_cast<int>(_states.Size()), a);
}
```

- [ ] **Step 5: Wire the hook in `TournamentGame.cpp` when serializer is active**

```cpp
if (_serializer) {
    game.setActionAppliedHook([this](const GameState & s, const Action & a) {
        _serializer->captureActionApplied(s, a);
    });
}
```

The lambda only exists when `_serializer` is non-null, so when `--save-replays` is off the hook is never installed and `Game::doAction` sees a default-null `std::function` — the if-check fails immediately. No measurable cost.

- [ ] **Step 6: Build + test driver**

```bash
"/c/Program Files/Microsoft Visual Studio/18/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "c:/libraries/PrismataAI-dave-master/visualstudio/Prismata.sln" \
  //t:Rebuild //p:Configuration=Release //p:Platform=x86 //m
./serializer_test.exe
```

Expected: PASS. The `states[]` array should have multiple entries per turn (one per action).

- [ ] **Step 7: Commit**

```bash
git commit -am "feat(engine+serializer): per-action snapshots via Game::doAction hook"
```

---

### Task 17: Derived fields per Phase 1 reconciliation table

**Files:**
- Modify: `PrismataAI-dave-master/source/testing/ReplaySerializer.cpp`
- Possibly modify: `PrismataAI-dave-master/source/ai/StateHelper.{h,cpp}` (or wherever engine_v1's derived-field computations live; or create new helpers if absent)

**Input:** `docs/derived-field-reconciliation.md` from Phase 1. Each field is implemented to its **shipped-bundle** semantics.

- [ ] **Step 1: Open the reconciliation table side-by-side**

Read `docs/derived-field-reconciliation.md`. For each in-scope derived field, you have:
- The shipped-bundle code (the formula to match)
- The local code (only useful where AGREE/cosmetic)
- The implementation note (the one-liner from Phase 1 Task 4 Step 2)

- [ ] **Step 2: For each AGREE field — port from local engine StateHelper**

For fields that AGREE between bundle and local, engine_v1 likely already has a method. Grep:
```bash
grep -rn "<fieldName>" c:/libraries/PrismataAI-dave-master/source/{ai,engine}
```

If found: call the existing method from `serializeState`. If not found but the local JS computation is simple: port it as a free function in `ReplaySerializer.cpp` (the JS was transpiled from C++ AS3 in the first place, so the formulas should map cleanly).

Example (hypothetical maxAttack):
```cpp
// In serializeState, append:
v.AddMember("maxAttack", computeMaxAttack(state, 0), a);
v.AddMember("oppAttackPotential", computeMaxAttack(state, 1), a);
```

With `computeMaxAttack` either calling `state.getStateHelper().maxAttack(0)` or being a new free function in the .cpp.

- [ ] **Step 3: For each DISAGREE / BUNDLE-ONLY field — implement to bundle semantics**

These are the high-risk fields. Read the bundle code from the reconciliation table and translate it to C++. Add a comment citing the line number in the shipped bundle.

```cpp
// whiteGoldEstimate — per prismata-engine.js:NNNN-NNNN (shipped, authoritative)
//                     Differs from js_engine/StateHelper.js: bundle <does X>, local <does Y>.
static std::pair<int,int> computeGoldEstimate(const GameState & state, PlayerID p) {
    // ... C++ translation of the bundle code ...
}
```

- [ ] **Step 4: Wire all derived fields into `serializeState`**

Append after the structural fields (at the end of `serializeState`):

```cpp
v.AddMember("incomingAttack", computeIncomingAttack(state), a);
v.AddMember("maxAttack", computeMaxAttack(state, 0), a);
v.AddMember("maxDisrupt", computeMaxDisrupt(state, 0), a);
v.AddMember("maxSnipers", computeMaxSnipers(state, 0), a);
v.AddMember("oppAttackPotential", computeMaxAttack(state, 1), a);
v.AddMember("oppDisruptPotential", computeMaxDisrupt(state, 1), a);
v.AddMember("oppSnipers", computeMaxSnipers(state, 1), a);

auto [wLow, wHigh] = computeGoldEstimate(state, 0);
rapidjson::Value wEst(rapidjson::kArrayType);
wEst.PushBack(wLow, a); wEst.PushBack(wHigh, a);
v.AddMember("whiteGoldEstimate", wEst, a);

auto [bLow, bHigh] = computeGoldEstimate(state, 1);
rapidjson::Value bEst(rapidjson::kArrayType);
bEst.PushBack(bLow, a); bEst.PushBack(bHigh, a);
v.AddMember("blackGoldEstimate", bEst, a);

// Also refine deadness from "alive"/"dead" to the rich reasons
// (alive | blocked | sacced | meleed | sniped | autosniped | aged)
// — per reconciliation table guidance on Card::deadness mapping.
```

- [ ] **Step 5: Build + smoke**

Build. Run the smoke tournament with `saveReplays` set. Open one of the produced `.json.gz` files in `/replay/local`. The board should look approximately right — derived numbers visible in HUD.

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(serializer): derived fields per reconciliation table (site-bundle semantics)"
```

---

### Task 18: Top-level wrapper + gzip + write

**Files:**
- Modify: `PrismataAI-dave-master/source/testing/ReplaySerializer.cpp` (implement `finalize`)
- Modify: `PrismataAI-dave-master/source/testing/TournamentGame.cpp` (construct + finalize serializer per game)

- [ ] **Step 1: Find/choose a zlib (gzip) implementation**

engine_v1 may already link against zlib via rapidjson or another dependency — search:
```bash
grep -rn "zlib\|gzip\|deflate" c:/libraries/PrismataAI-dave-master/source/
ls c:/libraries/PrismataAI-dave-master/source/*/zlib*
```

If zlib is present: use `gzwrite` / `gzopen`. If not: link in [miniz](https://github.com/richgel999/miniz) (single-header zlib-compat) — add `miniz.h` / `miniz.c` to `source/testing/`.

- [ ] **Step 2: Implement `finalize`**

```cpp
#include <fstream>
#include <filesystem>
#include "../rapidjson/writer.h"
#include "../rapidjson/stringbuffer.h"
// + zlib OR miniz include

bool ReplaySerializer::finalize(int winner, int turns,
                                const std::string & outDir, int gameIndex) {
    auto & a = _doc.GetAllocator();

    // Top-level fields per spec contract
    _doc.AddMember("replay", true, a);
    _doc.AddMember("p0", rapidjson::Value(_p0.c_str(), a), a);
    _doc.AddMember("p1", rapidjson::Value(_p1.c_str(), a), a);
    _doc.AddMember("winner", winner, a);

    const char * winnerName = (winner == 0 ? _p0.c_str() :
                                winner == 1 ? _p1.c_str() : "Draw");
    _doc.AddMember("winnerName", rapidjson::Value(winnerName, a), a);
    _doc.AddMember("turns", turns, a);

    rapidjson::Value cardSetArr(rapidjson::kArrayType);
    for (const auto & name : _cardSet) {
        cardSetArr.PushBack(rapidjson::Value(name.c_str(), a), a);
    }
    _doc.AddMember("cardSet", cardSetArr, a);

    _doc.AddMember("states", _states, a);
    _doc.AddMember("actions", _actions, a);
    _doc.AddMember("turnBoundaries", _turnBoundaries, a);

    // Serialize to string
    rapidjson::StringBuffer buf;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buf);
    _doc.Accept(writer);

    // Write gzipped to <outDir>/game_<idx>.json.gz
    std::filesystem::create_directories(outDir);
    char filename[64];
    snprintf(filename, sizeof(filename), "game_%04d.json.gz", gameIndex);
    std::string path = outDir + "/" + filename;

    // ... gzip-write `buf.GetString()` of length `buf.GetSize()` to `path` ...
    // (concrete zlib call sequence depends on chosen library)

    return true;
}
```

- [ ] **Step 3: Wire into `TournamentGame.cpp`**

```cpp
// In TournamentGame constructor or run() — when saveReplays is set:
std::unique_ptr<ReplaySerializer> _serializer;
if (!_tournament.getSaveReplaysDir().empty()) {
    _serializer = std::make_unique<ReplaySerializer>(
        _playerNames[0], _playerNames[1], _tournament.getCardSetNames()
    );
    _serializer->captureInitialState(_state);
}

// Per turn, after Game::playNextTurn():
if (_serializer) {
    _serializer->captureMove(_state /* pre — capture earlier */,
                             game.getPreviousMove(),
                             _state /* post */);
}

// At end of game:
if (_serializer) {
    int winnerInt = _winner == 0 ? 0 : _winner == 1 ? 1 : -1;
    _serializer->finalize(winnerInt, _turnsPlayed,
                          _tournament.getSaveReplaysDir(), _gameIndex);
    _serializer.reset();
}
```

- [ ] **Step 4: Build + smoke**

```bash
# Build, then run the smoke tournament with saveReplays set.
./Prismata_Testing.exe
ls -la bin/asset/replays/dave_smoke/
# Expect: game_0001.json.gz, game_0002.json.gz
```

- [ ] **Step 5: Manually inspect one output**

```bash
gunzip -c bin/asset/replays/dave_smoke/game_0001.json.gz | python -m json.tool | head -30
```

Confirm: top-level keys present, `states` is a non-empty array, each state has the expected fields.

- [ ] **Step 6: Re-run the no-op gate from Task 13**

Re-confirm that disabling `saveReplays` (empty/missing field) leaves the tournament identical to baseline. Statistical equivalence within ±√n.

- [ ] **Step 7: Commit**

```bash
git commit -am "feat(serializer): finalize/write game_NNNN.json.gz + wire into TournamentGame"
```

---

### Task 19: Oracle diff against `matchup_clean.js --save-replays`

**Files:**
- Create: `PrismataAI-dave-master/source/testing/tests/oracle_diff.md` (findings log)

This is the field-by-field fidelity check. We pick a single starting GameState, run it through both producers, and diff.

- [ ] **Step 1: Pick a fixed test state**

Use one of the deterministic test fixtures in `bin/asset/config/` or hand-craft a minimal GameState (e.g. turn 1, P0 has 6 Drones + 1 Engineer, P1 same). The state must be reproducible across both producers.

- [ ] **Step 2: Generate the C++ output**

Configure a 1-game tournament against that fixed state. Run with `saveReplays`. Capture `c_replay.json`:

```bash
gunzip -c bin/asset/replays/oracle/game_0001.json.gz > /tmp/c_replay.json
```

- [ ] **Step 3: Generate the JS-oracle output for the same starting state**

Use `matchup_clean.js --save-replays` with the same initial config. If reproducing the exact state requires custom setup, write a minimal JS harness that bypasses random-card selection and feeds the fixed state in.

```bash
node js_engine/matchup_clean.js \
  --player OriginalHardestAI --player OriginalHardestAI \
  --games 1 --think-time 100 \
  --save-replays /tmp/js_oracle/ \
  --seed 42        # if --seed exists; otherwise control by other means
gunzip -c /tmp/js_oracle/game_0001.json.gz > /tmp/js_replay.json
```

- [ ] **Step 4: Diff with awareness**

The diff won't be byte-identical (different action-string formatting, different float precision, possibly different turn lengths if AI is non-deterministic). What MUST agree:
- `states[0]` should match field-by-field (same initial state).
- `cards[]`, `whiteTotalSupply[]`, etc. should be identical at every state index where the state is the same.
- All in-scope derived fields should agree at `states[0]`.

```bash
# Use a json-aware diff. python helper:
python -c "
import json, sys
c = json.load(open('/tmp/c_replay.json'))
j = json.load(open('/tmp/js_replay.json'))
print('states[0] keys diff:', set(c['states'][0].keys()) ^ set(j['states'][0].keys()))
for k in sorted(set(c['states'][0]) | set(j['states'][0])):
    cv, jv = c['states'][0].get(k), j['states'][0].get(k)
    if cv != jv:
        print(f'DIFF {k}: c={cv!r} j={jv!r}')
"
```

- [ ] **Step 5: Resolve diffs**

For each diff:
- If it's a derived field where the reconciliation table says C++ should match shipped (and JS doesn't): expected. Document in `oracle_diff.md` and move on.
- If it's a structural field: C++ bug. Fix.
- If it's a formatting/precision issue: tolerate (document the tolerance).

- [ ] **Step 6: Commit findings**

```bash
git add source/testing/tests/oracle_diff.md
git commit -m "phase3(verify): oracle diff vs matchup_clean.js — findings log"
```

---

### Task 20: End-to-end visual verification via `/replay/local`

**Files:** none — verification only.

- [ ] **Step 1: Run a full DSNN-vs-DaveAI matchup with `saveReplays` enabled**

Configure a small tournament (4-8 games, 7s think) pitting `DSNN_MBonly` vs `HardestAIUCT` in Dave's tree. Run:

```bash
./Prismata_Testing.exe
```

This is the experimental setup the user has been wanting since the May 18 results.

- [ ] **Step 2: Copy the produced replays somewhere accessible**

Either to a local-disk folder or directly drag-drop into `/replay/local` from Windows Explorer.

- [ ] **Step 3: Watch 2-3 full games in `/replay/local`**

For each game:
- Confirm rendering doesn't crash.
- Confirm units land in expected positions.
- Confirm derived numbers (gold est, attack) match what you'd expect for that position.
- Note any "DSNN is weak HERE" observations — the whole reason for building this.

- [ ] **Step 4: Document observations**

Create `docs/scratch/dsnn-vs-dave-observations.md` with a few specific weakness notes. This is the user-facing payoff of the entire plan.

- [ ] **Step 5: Commit**

```bash
cd c:/libraries/PrismataAI
git add docs/scratch/dsnn-vs-dave-observations.md
git commit -m "phase3(verify): DSNN-vs-DaveAI visual observations from /replay/local"
```

---

### Task 21: Merge feature/save-replays into dave-master-jsonclean

**Files:** none — git workflow.

- [ ] **Step 1: User reviews the dave-master worktree branch diff**

```bash
cd c:/libraries/PrismataAI-dave-master
git log --oneline dave-master-jsonclean..feature/save-replays
git diff dave-master-jsonclean...feature/save-replays --stat
```

Stop and have the user review.

- [ ] **Step 2: Merge to dave-master-jsonclean**

```bash
git checkout dave-master-jsonclean
git merge --no-ff feature/save-replays -m "merge: --save-replays C++ snapshot serializer"
```

- [ ] **Step 3: Push (user confirms first)**

```bash
git push origin dave-master-jsonclean        # ONLY after user confirms
```

- [ ] **Step 4: Update CLAUDE.md (PrismataAI repo) with the new capability**

In `c:/libraries/PrismataAI/CLAUDE.md`, under "How to Build and Run", add a one-liner:

> **Save replays from a native C++ tournament:** Set `"saveReplays":"<dir>"` on the Tournament config block in `bin/asset/config/config.txt` (dave-master tree). View at https://prismata.live/replay/local.

Commit on `feature/cpp-replay-export-pixijs-viewer` branch in PrismataAI.

- [ ] **Step 5: Plan complete — close the feature branches**

The feature is shipped. Both feature branches can be deleted locally (the merge commits preserve history):

```bash
# Only after user confirms everything works end-to-end:
cd c:/libraries/PrismataAI && git branch -d feature/cpp-replay-export-pixijs-viewer
cd c:/libraries/PrismataAI-dave-master && git branch -d feature/save-replays
cd c:/libraries/prismata-ladder && git branch -d feature/replay-local-page
```

---

## Plan Self-Review Checklist

- [x] **Phase 1** delivers `docs/derived-field-reconciliation.md` (Task 4).
- [x] **C++ snapshot export** — Tasks 11-18 cover branch + flag + skeleton + structural + derived + finalize/wire.
- [x] **Bundle entry point** — Task 6 hand-edits the shipped bundle to add `loadFromBuffer`.
- [x] **`/replay/local` page** — Tasks 7-8 build the React component and page.
- [x] **No-op invariant** — Tasks 12-13 (stub gate) + Task 18 Step 6 (final re-confirm).
- [x] **Oracle diff** — Task 19.
- [x] **Visual parity** — Task 20.
- [x] **Engine_v1 questions for Dave** — flagged at the top + Task 16 gate.
- [x] **Bundle never-rebuild rule** — Task 6 Step 6 commit message + Task 21 Step 4 CLAUDE.md note + planned spec future-work item.
- [x] **Winner-encoding clarifier** — folded into Task 18 Step 2 (`winner` is `0=white / 1=black / -1=draw`).

## Open Risks / Watchpoints

1. **Task 15 engine_v1 API guesses.** Accessor names like `getResources`, `getCardSupply`, `getCardByID` are best-guesses. Reading the actual headers in dave-master is mandatory and may require renames mid-task.
2. ~~**Task 16 Move atomicity.**~~ *Resolved 2026-05-28: Branch A confirmed from `Game::doAction` chokepoint.*
3. **Task 17 derived-field divergence size.** If the reconciliation table shows many material disagreements, Task 17 grows substantially. The Phase 1 Task 4 Step 5 decision gate exists exactly to flag this before Phase 3 starts.
4. **Task 18 gzip dependency.** May require pulling in miniz; small but not zero new dependency.
5. **No-op gate seeding.** Statistical equivalence with PID-based seeding is acceptable but weaker than byte-identical. If a sharper gate is needed, add a `--seed` CLI to the tournament first.
