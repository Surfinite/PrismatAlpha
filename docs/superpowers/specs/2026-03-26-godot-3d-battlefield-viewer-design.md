# Prismata 3D Battlefield Viewer — Design Spec

**Date:** 2026-03-26
**Status:** Ready for implementation planning
**Collaborators:** Surfinite (framework/engine), homander (visual design/3D models)

## Overview

A Godot 4 application that renders Prismata games as a 3D battlefield with free camera controls. Replays are displayed on a terrain plane with two armies facing each other (north/south mirror layout), viewed from an angled Mechabellum-style camera with a top-down strategic toggle.

The architecture is event-driven with pluggable visual hooks. The framework handles game data, replay navigation, and unit placement. The visual layer (homander's domain) handles animations, effects, 3D models, and cinematic polish.

### Design Principles

1. **Snapshot is truth, events are hints.** The board state snapshot is authoritative. Events are animation suggestions. Missing or unsupported events result in correct board state with no animation — never incorrect state.
2. **Battlefield reconciles first, hooks decorate after.** Node existence is owned by the battlefield layer, never by hooks.
3. **Framework vs sandbox.** Homander works in `visual/` and `assets/`. Everything else is framework.
4. **Forward-compatible.** Data shapes and interfaces support future playable client and live spectating, even though MVP is replay-only.

### Phased Data Source Strategy

- **Phase 1:** Pre-baked snapshot JSON files (Node.js preprocessor → Godot reads files)
- **Phase 2:** WebSocket bridge to live JS engine (same data shape, push-based)
- **Phase 3:** Native GDScript game logic (fully standalone, no external dependencies)

All three produce the same `BoardSnapshot` shape. The Godot rendering side does not change between phases.

## 1. Core Terms

| Term | Definition |
|------|-----------|
| **Snapshot** | Complete authoritative board state at a point in time. Contains all unit positions, stats, resources, and the events that led to this state. |
| **seq** | Strictly increasing global integer identifying a snapshot. Multiple snapshots may share the same `turn`. Replay advances by seq, not turn. |
| **turn** | Game-level turn number (increments per player-turn). For game meaning, not replay navigation. |
| **Provider** | Async data source that produces snapshots. Swappable (file, WebSocket, native). |
| **ReplayController** | Owns seq position, snapshot cache, playback state. Drives the replay timeline. |
| **Battlefield** | Scene manager. Reconciles node state to match authoritative snapshot. Owns unit registry. |
| **Hook** | Pluggable visual handler for a specific event type. Decorative only — never owns node existence. |
| **VisualContext** | Context object passed to hooks. Contains snapshots, unit registry, camera, helpers. |

## 2. BoardSnapshot Schema

```json
{
  "schemaVersion": 1,
  "seq": 37,
  "turn": 4,
  "phase": "action",
  "presentationFlags": { "glassBroken": false, "swoosh": false },
  "activePlayer": 0,
  "viewPlayer": 0,
  "matchMeta": {
    "matchId": "replay_abc123",
    "players": [
      { "id": 0, "name": "Surfinite" },
      { "id": 1, "name": "homander" }
    ]
  },
  "players": [
    {
      "id": 0,
      "resources": {
        "gold": 7,
        "green": 0,
        "blue": 2,
        "red": 0,
        "energy": 0,
        "attack": 0
      },
      "units": [
        {
          "id": 12,
          "cardId": "drone",
          "displayName": "Drone",
          "internalName": "Drone",
          "stats": {
            "hp": 1,
            "maxHp": 1,
            "attack": 0,
            "chill": 0
          },
          "state": {
            "mode": "idle",
            "blocking": false,
            "attacking": false,
            "chilled": 0,
            "buildTurnsRemaining": 0,
            "lifespan": -1,
            "fragile": false,
            "frontline": false
          },
          "render": {
            "row": "middle",
            "slot": 10
          }
        }
      ]
    }
  ],
  "events": [
    {
      "type": "buy",
      "player": 0,
      "cardId": "tarsier",
      "unitId": 45
    }
  ],
  "actionOptions": null
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schemaVersion` | int | Schema version. Provider must reject unsupported versions. |
| `seq` | int | Strictly increasing. Globally monotonic across the whole match. |
| `turn` | int | Game turn number. May repeat across multiple seqs. |
| `phase` | string | `"action"`, `"defense"`, `"confirm"`. JS engine phases only. See `presentationFlags` for breach/swoosh. |
| `presentationFlags` | object | Optional renderer hints synthesized by preprocessor. `glassBroken` (bool): breach is occurring. `swoosh` (bool): begin-turn transition. These are NOT engine phases — they are visual state derived from engine flags. |
| `activePlayer` | int | 0 or 1. Whose turn/phase it is. |
| `players` | array[2] | Player 0 (blue/bottom) and Player 1 (red/top). |
| `players[].id` | int | 0 or 1. |
| `players[].resources` | object | gold, green, blue, red, energy, attack. |
| `players[].units` | array | All living units for this player. |
| `events` | array | Ordered event list for this snapshot transition. |

### Unit Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Stable across the match. Used for Godot node tracking. |
| `cardId` | string | Stable lowercase snake_case identifier derived from display name (e.g., `"drone"`, `"tarsier"`, `"tesla_tower"`). Used for asset lookups, code branching, filesystem paths. The preprocessor generates these from `cardLibrary.jso`. |
| `displayName` | string | Human-readable name for UI (e.g., `"Drone"`, `"Tarsier"`, `"Tesla Tower"`). |
| `internalName` | string | Engine internal name (e.g., `"Drone"`, `"Tesla Tower"`). Optional — for engine/preprocessor debugging. |
| `stats.hp` | int | Current HP. |
| `stats.maxHp` | int | Maximum HP. |
| `stats.attack` | int | Attack value this unit contributes. |
| `stats.chill` | int | Chill ability amount (0 if none). |
| `state.mode` | string | Primary mode: `"idle"`, `"under_construction"`, `"exhausted"`. |
| `state.blocking` | bool | Currently assigned as blocker. |
| `state.attacking` | bool | Currently committed to attack. |
| `state.chilled` | int | Turns of chill remaining (0 = not chilled). |
| `state.buildTurnsRemaining` | int | 0 = ready. >0 = under construction. |
| `state.lifespan` | int | Turns until death. -1 = permanent. |
| `state.fragile` | bool | Takes permanent damage (HP doesn't regenerate). |
| `state.frontline` | bool | Undefendable — can be targeted through blockers. |
| `render.row` | string | `"front"`, `"middle"`, `"back"`. Assigned by layout algorithm (see Placement Rules in Section 6). |
| `render.slot` | int | Position within row (0-29 sparse). Assigned by layout algorithm based on unit properties. |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `viewPlayer` | int | Perspective player for future playable client. Default: 0. |
| `presentationFlags` | object | Renderer hints: `glassBroken` (bool), `swoosh` (bool). Synthesized by preprocessor. |
| `matchMeta` | object | Match metadata: `matchId` (string), `players` (array of `{id, name}`). Present on first snapshot, optional on subsequent. |
| `actionOptions` | object\|null | Legal moves. Null for replay mode. Reserved for Phase 3. |

### First-Snapshot Conventions

- First visible snapshot is seq 0.
- `prev_snapshot` is `null` on first display.
- `events` on first snapshot should be empty (no prior state to transition from).
- Battlefield treats `prev = null` as an empty board — all units in seq 0 are spawned, none removed.
- `matchMeta` should be present on seq 0 for UI initialization (player names, match ID).

### Seq Semantics

- `seq` is strictly increasing across the whole match (no gaps expected, but tolerate them).
- Each snapshot is one complete board state after a committed action or phase transition.
- Multiple snapshots may share the same `turn` (e.g., seq 34-38 are all turn 4, different phases/actions).
- Providers must deliver snapshots in seq order. Replay only advances once the exact requested seq exists.
- Granularity: one snapshot per click batch or phase transition. Approximately 4-8 snapshots per turn pair.

### Schema Versioning

- Every snapshot carries `schemaVersion`.
- Provider must reject snapshots with unsupported `schemaVersion`.
- Battlefield and hooks only operate on validated snapshots.
- When schema changes: bump version, update provider validation, update Godot parsing.

## 3. Event Types

Events are ordered within the `events` array. They describe what happened to produce this snapshot from the previous one. All events are advisory — the snapshot is authoritative.

### Event Catalog

```
buy           — unit purchased
kill          — unit destroyed
sacrifice     — unit sacrificed (ability cost, lifespan expiry)
assign_blocker — unit assigned to defend
breach_start  — defense breached, unblocked damage incoming
breach_kill   — unit killed during breach
ability       — targeted ability used (chill, snipe, etc.)
phase_change  — game phase transition
turn_start    — new turn begins (after swoosh)
```

### Event Payloads

```json
{ "type": "buy", "player": 0, "cardId": "tarsier", "unitId": 45 }

{ "type": "kill", "player": 1, "unitId": 22,
  "cause": { "type": "combat", "sourceUnitId": 12 } }

{ "type": "kill", "player": 1, "unitId": 22,
  "cause": { "type": "blocker_killed" } }

{ "type": "sacrifice", "player": 0, "unitId": 44,
  "reason": "ability_cost" }

{ "type": "sacrifice", "player": 0, "unitId": 44,
  "reason": "lifespan" }

{ "type": "assign_blocker", "player": 1, "unitId": 22,
  "incomingDamage": 4 }

{ "type": "breach_start", "player": 1, "unblockedDamage": 3 }

{ "type": "breach_kill", "player": 1, "unitId": 18,
  "damage": 2, "sourcePlayer": 0,
  "cause": { "type": "breach", "sourcePlayer": 0 } }

{ "type": "ability", "player": 0, "unitId": 33,
  "ability": { "type": "chill", "targetId": 18, "amount": 1 } }

{ "type": "ability", "player": 0, "unitId": 7,
  "ability": { "type": "snipe", "targetId": 19, "damage": 1 } }

{ "type": "phase_change", "phase": "defense", "activePlayer": 1 }

{ "type": "turn_start", "turn": 5, "activePlayer": 0 }
```

### Event Dispatch Rules

- Events are dispatched in array order.
- Missing handler for an event type = silent no-op.
- Hook execution does not alter authoritative state.
- Hooks are non-blocking. Replay does not wait for hook completion.
- Multiple hooks may respond to the same event type (future: hook registry with priority).

## 4. Provider Interface

```
class BaseProvider:

    # Signals
    signal snapshot_available(seq: int)
    signal provider_reset()
    signal provider_error(message: String)

    # Methods (required)
    func request_snapshot(seq: int) -> void
    func get_snapshot(seq: int) -> Variant          # BoardSnapshot dict or null
    func has_snapshot(seq: int) -> bool
    func get_latest_seq() -> int              # returns -1 if no snapshots loaded

    # Methods (optional, provider-dependent)
    func is_live() -> bool                          # true for WebSocket, false for file
    func can_seek() -> bool                         # true for file/native, maybe for WebSocket
    func get_total_seqs() -> int                    # -1 if unknown (live mode)
```

### Provider Lifecycle

1. Provider is initialized with a data source (file path, WebSocket URL, or game config).
2. Provider begins loading/connecting.
3. As snapshots become available, provider emits `snapshot_available(seq)`.
4. ReplayController immediately fetches and caches: `cache[seq] = provider.get_snapshot(seq)`.
5. On error: provider emits `provider_error(message)`. UI shows error state.
6. On disconnect/reset: provider emits `provider_reset()`. ReplayController clears cache.

**Cache ownership:** Provider owns transport and temporary availability. ReplayController owns the long-lived navigation cache used for stepping/scrubbing. Once a snapshot is cached by ReplayController, it does not need the provider again for that seq.

### Phase-Specific Behavior

| | FileProvider | WebSocketProvider | NativeProvider |
|---|---|---|---|
| Load pattern | Pre-load all seqs on init | Push as received | Generate on demand |
| `is_live()` | false | true | false |
| `can_seek()` | true | only backward in cache | true |
| `get_total_seqs()` | known | -1 | known after generation |
| Latency | instant | network-dependent | computation-dependent |

## 5. ReplayController

### Responsibilities

- Owns current `seq` position
- Owns snapshot cache (dictionary: `seq → BoardSnapshot`)
- Drives playback: play/pause, step forward/back, speed control, scrub
- Emits `snapshot_changed(prev, current)` when seq advances

### Signal

```
signal snapshot_changed(prev_snapshot: Variant, current_snapshot: Variant, transition_type: String)
```

- `prev_snapshot` is null on the first snapshot (seq 0).
- `transition_type` is `"forward"`, `"backward"`, or `"jump"`. See Section 6 Transition Direction Policy.

**Note on backward navigation:** When stepping backward (seq N → seq N-1), `prev_snapshot` is the later state (seq N) and `current_snapshot` is the earlier state (seq N-1). The names refer to "what was showing" and "what to show now", not chronological order. Hook implementations must not assume `prev` is always chronologically earlier.

### Cache Policy

- **MVP:** Cache all snapshots. Prismata games are short (~70 turns, ~300-500 seqs). Memory is not a concern.
- **Turn index:** ReplayController maintains a `turn → first_seq` dictionary, built as snapshots are cached. Enables O(1) jump-to-turn.
- **Future:** LRU or windowed cache for very long replays or live mode.

### Navigation Behavior

| Action | Behavior |
|--------|----------|
| Step forward | Advance to seq + 1. If not available: wait (live) or no-op (file). |
| Step backward | Go to seq - 1. Always available from cache. |
| Jump to turn N | Look up first seq where `turn == N` from `turn_index` mapping. Jump to it. |
| Scrub to position | Map scrubber position to seq range. Jump to nearest seq. |
| Auto-play | Advance one seq per tick. Speed configurable (0.5x, 1x, 2x, 4x). |
| Pause | Stop auto-advance. |

### Edge Cases

| Situation | Behavior |
|-----------|----------|
| Scrub past `latest_seq` | Clamp to `latest_seq`. |
| Live mode, requested seq not yet available | Show loading indicator. Advance when `snapshot_available` fires. |
| Provider error | Pause replay. Show error in UI. Retain cache for backward scrub. |
| Provider reset | Clear cache. Reset to seq 0. |

## 6. Battlefield Reconciliation

### Transition Direction Policy

Navigation type determines whether hooks fire:

| Navigation | Direction | Hooks dispatched? |
|------------|-----------|-------------------|
| Step forward | forward | Yes — events describe this transition |
| Auto-play | forward | Yes |
| Step backward | backward | **No** — events describe how seq N-1 was reached from seq N-2, not the reverse of seq N → seq N-1 |
| Jump to turn | jump | **No** — arbitrary jump, events not meaningful for this transition |
| Scrub | jump | **No** |

Backward and jump transitions perform authoritative reconciliation only. The board lands in the correct state; no animation plays. This keeps the MVP simple and avoids semantically wrong hook invocations.

**Future:** Reverse hooks or transition-aware animation can be added in cinematic mode.

### Apply Pipeline (canonical order)

1. ReplayController selects target snapshot, determines transition type (`forward`, `backward`, `jump`).
2. ReplayController emits `snapshot_changed(prev, current, transition_type)`.
3. Battlefield receives signal.
4. Battlefield reconciles authoritative node state (see below).
5. Battlefield updates unit registry and 3D transforms.
6. **If `transition_type == "forward"`:** Battlefield dispatches `current.events` to VisualHooks with `VisualContext`.
7. Camera and UI respond to new state.
8. Frame completes.

### Reconciliation Algorithm

For each player, compare `prev.players[p].units` vs `current.players[p].units` by `id`:

1. **Spawn:** Unit in `current` but not `prev` → create `UnitNode3D`, add to registry, place at `render.row`/`render.slot` position.
2. **Update:** Unit in both → update stats, state, render position. Move node if slot changed.
3. **Remove:** Unit in `prev` but not `current` → remove from registry, `queue_free()` the node.

### Unit Registry

- Dictionary: `int (unitId) → UnitNode3D`
- Battlefield is the sole owner. No other layer adds/removes entries.
- Hooks access registry read-only via `VisualContext.get_unit_node(unitId)`.

### Placement Rules

**Spatial layout:**
- 3 rows per player: front, middle, back.
- Rows are parallel planes on the terrain, perpendicular to the north-south axis.
- Player 0 (blue): rows grow southward from center (front nearest center).
- Player 1 (red): rows grow northward from center (front nearest center, mirrored).
- Within a row: units placed left-to-right by `render.slot` value.
- Spacing: proportional, auto-cramped when row is dense.
- Future: unit grouping/stacking when multiple identical units exist (e.g., 8 Drones as a clump with count badge).

**Row assignment algorithm (implemented in preprocessor):**
The preprocessor assigns `render.row` and `render.slot` based on unit properties from `cardLibrary.jso`. This replicates the SWF client's 30-position sparse grid mapped to 3 rows:

| Row | Positions | Units assigned |
|-----|-----------|---------------|
| front | 0-9 | Engineers, default blockers (no ability), blockers with ability, undefendable/frontline units |
| middle | 10-19 | Drones, flexible units with abilities, blockers that also attack |
| back | 20-29 | Tech buildings (Conduit, Blastforge, Animus), pure attackers, spells, economy structures |

Within each row, slot assignment follows priority based on named base units first (Drone=10, Engineer=0, Conduit=20, Blastforge=21, Animus=22), then by unit property combinations (defaultBlocking, hasAbility, attack, undefendable, spell). Full mapping must be extracted from the PixiJS viewer's layout logic or the AS3 decompiled source during preprocessor implementation.

### Node Removal Policy: Snap-First (MVP)

- Battlefield removes dead unit nodes immediately during reconciliation.
- Hooks may only play detached effects (particles at the death position, not on the node).
- **Future upgrade path:** Battlefield marks node `pending_removal` instead of `queue_free()`. Hook calls `complete_removal()` after animation. Requires adding a removal queue and timeout fallback.

## 7. Visual Hook Contract

### VisualContext

Passed to every hook invocation. Provides everything a hook needs without tree traversal.

```
class VisualContext:
    var prev_snapshot: Variant          # previous BoardSnapshot (null on first)
    var current_snapshot: Variant       # current BoardSnapshot
    var camera: OrbitCamera             # camera controller
    var battlefield_root: Node3D        # battlefield scene root

    # Unit lookups (registry is internal — hooks access via these methods)
    func get_unit_node(unit_id: int) -> UnitNode3D         # living unit in current snapshot
    func has_unit_node(unit_id: int) -> bool
    func get_all_unit_nodes_for_player(player_id: int) -> Array[UnitNode3D]

    # Position helpers
    func get_unit_world_position(unit_id: int) -> Vector3  # position in CURRENT snapshot
    func get_prev_unit_world_position(unit_id: int) -> Vector3  # position in PREV snapshot (for death effects)

    # Scene helpers
    func get_player_root(player_id: int) -> Node3D
    func spawn_effect(effect_scene: PackedScene, position: Vector3) -> Node3D
```

**Dead-unit position lookup:** Since snap-first removes nodes during reconciliation, `get_unit_node()` returns null for units that died this transition. Use `get_prev_unit_world_position(unit_id)` in kill/sacrifice/breach_kill hooks to spawn death effects at the correct location. This reads from a position cache that battlefield populates before reconciliation.

### Hook Interface

```
class BaseHook:
    func handle_event(event: Dictionary, context: VisualContext) -> void
```

### Hook Dispatch

```
class VisualHooks:
    var hooks: Dictionary    # event_type string → Array[BaseHook]

    func dispatch(events: Array, context: VisualContext):
        for event in events:
            var type = event["type"]
            if type in hooks:
                for hook in hooks[type]:
                    hook.handle_event(event, context)
```

### Hook Rules

| Rule | Detail |
|------|--------|
| Hooks are decorative only | Never create/destroy unit nodes. Never modify authoritative state. |
| Non-blocking | Replay does not wait for hook completion. Hooks manage their own timing. |
| Missing handler = no-op | Unsupported event types are silently ignored. |
| Stateless preferred | Hooks should derive behavior from VisualContext, not internal state. |
| Camera requests are advisory | Hooks call `camera.request_focus(position)`, camera may ignore if user is active. |

### MVP Hook Implementations

| Event | MVP Behavior |
|-------|-------------|
| `buy` | Spawn particle burst at unit position (simple flash). |
| `kill` | Spawn particle burst at death position (simple flash). |
| `sacrifice` | Same as kill. |
| `breach_start` | No-op. |
| `breach_kill` | No-op. |
| `ability` | No-op. |
| `assign_blocker` | No-op. |
| `phase_change` | No-op. |
| `turn_start` | No-op. |

## 8. Camera System

### Controls

- **Orbit:** Left-click drag rotates around focus point.
- **Zoom:** Scroll wheel. Clamped between close-up and full-field view.
- **Pan:** Middle-click drag or right-click drag moves focus point.
- **Top-down toggle:** Keybind (T or numpad 5). Snaps to overhead, locks rotation. Toggle again to return.

### Default View

Angled Mechabellum-style: ~45° pitch, looking at center divide, both armies visible. Camera starts at a distance where all 3 rows per player are visible.

### Priority Rules

| Priority | Source | Behavior |
|----------|--------|----------|
| 1 (highest) | User input | Active drag/zoom always controls. Cancels cinematic focus. |
| 2 | Top-down toggle | Locks pitch to 90°, disables orbit rotation until toggled off. |
| 3 | Cinematic focus | `camera.request_focus(position, duration)`. Smooth pan to target. Ignored if user is actively dragging. Auto-expires. |
| 4 (lowest) | Shake | Additive offset. Never steals control. Decays over time. |

### Camera API (for hooks)

```
func request_focus(target: Vector3, duration: float = 1.0) -> void
func shake(intensity: float = 0.5, duration: float = 0.3) -> void
func is_user_active() -> bool
```

## 9. UI Layer

### Replay HUD

- **Turn counter:** "Turn 4 — P0 Action" (derived from snapshot `turn`, `phase`, `activePlayer`).
- **Scrubber:** Horizontal bar. Seq position mapped to bar width. Click to jump. Drag to scrub.
- **Playback controls:** Play/pause, step forward, step back, speed (0.5x/1x/2x/4x).

### Resource Bars

- One per player, positioned at screen edges (top for P1, bottom for P0).
- Shows gold, green, blue, red, energy, attack.
- Updates from `current_snapshot.players[p].resources`.

### Error/Loading States

| State | UI Behavior |
|-------|-------------|
| Loading replay | "Loading..." overlay. Scrubber disabled. |
| Provider error | "Error: {message}" toast. Replay paused. Backward scrub still works. |
| Live: waiting for seq | Scrubber shows buffering indicator at end. |
| End of replay | "Game Over" overlay. Scrubber at max. |

## 10. File Structure

```
prismata-3d/
├── project.godot
├── providers/
│   ├── base_provider.gd              # async interface (signals + methods)
│   ├── file_provider.gd              # Phase 1: pre-baked JSON
│   ├── websocket_provider.gd         # Phase 2: live JS engine
│   └── native_provider.gd            # Phase 3: GDScript engine
├── replay/
│   └── replay_controller.gd          # seq navigation, cache, playback
├── battlefield/
│   ├── battlefield.gd                # reconciler + scene owner
│   ├── battlefield.tscn              # terrain, lighting, skybox
│   ├── unit_node.gd                  # single unit (sprite, state display)
│   └── unit_node.tscn                # unit scene template
├── visual/
│   ├── visual_hooks.gd               # event dispatcher
│   ├── visual_context.gd             # context object for hooks
│   ├── hooks/
│   │   ├── buy_hook.gd               # MVP: spawn flash
│   │   ├── kill_hook.gd              # MVP: death flash
│   │   └── ...                       # future: breach, ability, etc.
│   ├── effects/                      # particle scenes, animations
│   └── utils/                        # shared helpers (tweens, spawners)
├── camera/
│   ├── orbit_camera.gd               # free orbit/zoom/pan
│   └── camera_modes.gd               # top-down toggle, cinematic focus
├── ui/
│   ├── replay_hud.gd                 # scrubber, turn counter, playback
│   └── resource_bar.gd               # per-player resource display
├── data/                             # sample snapshot JSON, test fixtures
└── assets/
    ├── card_sprites/                 # 2D card art (MVP placeholders)
    └── models/                       # 3D models (homander, future)
```

### Collaboration Boundary

| Who | Owns | Touches |
|-----|------|---------|
| Surfinite | `providers/`, `replay/`, `battlefield/`, `camera/`, `ui/`, `data/` | Everything except visual content |
| Homander | `visual/hooks/`, `visual/effects/`, `assets/models/` | Visual polish, 3D models, animations |
| Shared | `visual/visual_hooks.gd`, `visual/visual_context.gd` | Hook interface (changes need agreement) |

## 11. MVP Scope

What the first prototype delivers:

- [ ] Load pre-baked snapshot JSON from file
- [ ] Step through seqs with arrow keys
- [ ] 3 rows per player rendered as 3D lanes on flat terrain
- [ ] Units displayed as upright 2D sprites (card art) — cardboard standees
- [ ] Free orbit camera with zoom/pan + top-down toggle
- [ ] Units appear/disappear as bought/destroyed (with simple particle flash)
- [ ] Turn counter and phase indicator
- [ ] Resource bars for both players
- [ ] Scrubber bar for navigation
- [ ] Play/pause auto-advance

What MVP explicitly does NOT include:

- 3D models (placeholder sprites only)
- Cinematic animations (breach, abilities, etc.)
- Sound
- Buy panel / action UI
- Live spectating (WebSocket provider)
- Native game logic (GDScript engine)
- Unit grouping/stacking
- Playable client features

## 12. Future Extensions

Documented for reference. Not in scope for MVP.

| Extension | Description | Dependency |
|-----------|-------------|------------|
| Visual grace period | `pending_removal` + `complete_removal()` for death animations | Hook system working |
| WebSocket provider | Live spectating from JS engine or prismata.live | Phase 2 |
| Native provider | GDScript game logic, fully standalone | Phase 3 |
| Playable client | `actionOptions` populated, click-to-act UI | Phase 3 + networking |
| Unit grouping | Stack identical units, show count badge | Battlefield layout refactor |
| Reconciler extraction | `board_reconciler.gd` split from `battlefield.gd` | If battlefield.gd grows complex |
| 3D models | Replace card sprites with homander's models | Asset pipeline |
| Cinematic mode | Replay pauses for hook animations, directed camera | Hook timing integration |

## 13. Preprocessor (Phase 1 tooling)

A Node.js script that converts replay JSON → pre-baked snapshot JSON.

```bash
node tools/replay_to_snapshots.js replay.json.gz -o snapshots/
# Output: snapshots/match_001.json (array of BoardSnapshot objects)
```

Uses the existing JS engine to replay click-by-click, emitting a snapshot after each click batch / phase transition. Reuses:
- `js_engine/` modules for game state
- `cardLibrary.jso` for unit metadata and internal→display name mapping
- Layout algorithm (row/slot assignment from unit properties — see Section 6 Placement Rules)

The preprocessor must:
1. Validate output against `schemaVersion` and required fields before writing.
2. Generate stable `cardId` (lowercase snake_case from display name) and populate `displayName` / `internalName`.
3. Populate `presentationFlags` (`glassBroken` from engine flag, `swoosh` from `beginTurn` call).
4. Assign `render.row` and `render.slot` based on the layout algorithm.
5. Cache unit positions before each reconciliation step so `get_prev_unit_world_position()` works for dead units.
6. Include `matchMeta` on seq 0 with player names and match identifier.

This is the bridge between the existing PrismataAI codebase and the Godot project.
