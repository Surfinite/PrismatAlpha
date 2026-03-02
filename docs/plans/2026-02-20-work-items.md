# PrismataAI Non-Training Work Items (Feb 20, 2026)

## High Priority

1. **~~S3 deploy bucket stale~~** — DONE. Already current (verified Feb 20).
2. **~~Merge watcher-enhancements-v2 to master~~** — DONE. 16 commits, 81 files, fast-forward merged and pushed (Feb 20).
3. **Autopilot live test** — `prismata_autopilot.py` coded but never tested with actual bot game click injection.
4. **Sniffer live game state** — auto-F6 + clipboard + click tracking coded but not live-tested in an actual game.

## Medium Priority

5. **Commentator Phase 2: TTS** — `edge-tts` + `sounddevice` + VB-Cable for spoken commentary. Deps not installed. Plan: `docs/plans/2026-02-20-live-commentator-plan.md`.
6. **Commentator Phase 3: OBS integration** — `obsws-python` for live subtitle overlay.
7. **~~Sniffer supply limit enforcement~~** — DONE. Click counting now enforces per-player supply limits from mergedDeck rarity (legendary=1, rare=4). Revert handling added. (Feb 20).
8. **Post-game commentary automation** — Currently manual workflow. Could be a single script: `python commentate.py <replay_code>` → formatted Discord output.
9. **Dashboard actions.json** — Missing GCP launch, tournament eval, R12 training, sniffer/advisor start buttons. Config-driven, low effort.
10. **Twitch VOD transcription** — Msven's 18 Twitch-only highlights (~21 hours). `yt-dlp -x` + whisper for knowledge base.

## Lower Priority

11. **Watcher v2 e2e test coverage** — 22 existing scenarios don't cover cost_estimate, idle_fleet, azure_cleanup.
12. **Dashboard process visibility** — No panel for sniffer/commentator/autopilot status.
13. **Engine: undo snipe not implemented** — `source/engine/GameState.cpp:418`.
14. **Engine: UntapAvoidBreach zero-value optimization** — `source/ai/PartialPlayer_ActionAbility_UntapAvoidBreach.cpp:65`.
15. **Blocking feature mismatch** — C++ uses `CardStatus::Assigned`, Python uses `blocking AND abilityUsed`.
16. **Engine validation Phase B** — `export_for_cpp.js` missing, 849 replay failures uninvestigated.
17. **Commentator personality modes** — hype/analytical/dry/duo styles.
18. **`run_commentator.bat`** launcher doesn't exist yet.
19. **Reproducibility plan** — `--seed` implemented but not smoke-tested.

## Future / Blocked

20. **PUCT move ordering** — Infrastructure done, blocked on policy accuracy (13.3%, needs >30%).
21. **GUI spectator mode** (claude-mem #1385) — Render live board state from sniffer in SFML.
22. **Web-based remote advisor** (claude-mem #1524) — Serve eval over HTTP for phone/tablet.
23. **Phase 3 iterative RL** — AlphaZero loop, blocked on reaching >50% WR.
