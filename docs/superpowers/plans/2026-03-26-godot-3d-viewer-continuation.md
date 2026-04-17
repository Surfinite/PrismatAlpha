# Godot 3D Battlefield Viewer — Continuation Prompt

## Context

Implementing a Godot 4 application that renders Prismata replays as a 3D battlefield. This is a collaboration with community member "homander" (Discord) who will handle visual design/3D models once the framework is built.

## Key Files

- **Design spec:** `docs/superpowers/specs/2026-03-26-godot-3d-battlefield-viewer-design.md` (642 lines, 13 sections)
- **Implementation plan:** `docs/superpowers/plans/2026-03-26-godot-3d-battlefield-viewer.md` (1851 lines, Tasks 1-13)
- **Project memory:** `project_godot_3d_viewer.md` in claude-mem

## What's Done

- Full design spec: approved after 3 review passes
- Full implementation plan: approved after 2 review passes
- Both are committed to disk

## What To Do

Execute the implementation plan using subagent-driven development. The plan has two phases:

**Phase A (Tasks 1-9):** Build the Godot viewer with handcrafted test fixtures. No preprocessor dependency.
- Task 1: Godot project setup
- Task 2: Handcrafted test fixture (5-6 snapshots)
- Task 3: Provider (base + file)
- Task 4: Replay controller
- Task 5: Battlefield + unit nodes
- Task 6: Camera system
- Task 7: Visual hooks
- Task 8: UI / HUD
- Task 9A: Card sprite extraction
- Task 9B: Phase A integration test

**Phase B (Tasks 10-13):** Build the Node.js preprocessor to generate real snapshot data.
- Task 10: Card ID mapping
- Task 11: Position calculator port
- Task 12A: Schema validator
- Task 12B: Preprocessor core
- Task 13: Integration with real replays

## Critical Implementation Rules

1. Connect provider signals BEFORE loading data (GDScript signals are synchronous)
2. Never mutate snapshot dictionaries (they're cached and shared)
3. Hooks dispatch on forward transitions only
4. Don't assume seq 0 exists — navigate to min available seq
5. Event detection is heuristic for MVP — only guarantee buy/kill events

## Godot Installation

- **Editor:** `C:\libraries\Godot\Godot_v4.6.1-stable_win64.exe\Godot_v4.6.1-stable_win64.exe`
- **Console (for CLI validation):** `C:\libraries\Godot\Godot_v4.6.1-stable_win64.exe\Godot_v4.6.1-stable_win64_console.exe`

## Start Command

Use superpowers:subagent-driven-development to execute the plan task-by-task, starting from Task 1.
