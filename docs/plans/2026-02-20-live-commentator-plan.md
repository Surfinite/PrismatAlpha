# Prismata Live AI Commentator — Implementation Plan

> **Goal**: Build a system that watches live Prismata games via the existing sniffer proxy and generates spoken AI commentary in real-time, suitable for Twitch streaming.
>
> **Status**: Phase 1 COMPLETE (text + chat injection). Phases 2-5 not started.
> **Date**: Feb 20, 2026

---

## Architecture Overview

```
Prismata Client <--> Sniffer Proxy <--> Game Server
                          |
                   @on_message handlers (existing)
                   +-- BeginGame: players, set, mergedDeck
                   +-- StartTurn: F6 capture -> board state JSON
                   +-- Click: real-time buy tracking
                   +-- EndTurn: time used, buy summary
                   +-- GameOver: result + replay code
                          |
                   CommentaryEngine (NEW)
                   +-- Turn event aggregator
                   +-- Game narrative accumulator
                   +-- Claude Haiku API (streaming)
                   +-- edge-tts (neural voice, async)
                          |
                    +-----+-----+
                    |           |
              VB-Cable      OBS WebSocket
              (audio)       (text captions)
                    |           |
                    +-----+-----+
                          |
                     OBS Scene
                   (Twitch stream)
```

## Phase 0: Documentation & API Reference

### Verified APIs (from discovery)

**Sniffer hook system** (`tools/prismata_sniffer.py`):
- `@on_message(msg_type, direction=None)` decorator — registers handler receiving `(msg_type, direction, params, raw_msg)`
- `session` — global `Session` object with thread-safe `.update(**kwargs)`, `.snapshot()`
- Session attributes: `.merged_deck`, `.players`, `.randomizer`, `.turn_number`, `.turn_buys`, `.last_f6_state`, `.game_phase`
- `_card_name_from_id(card_id)` — mergedDeck lookup, returns display name
- Turn lifecycle: BeginGame -> (StartTurn -> Click* -> EndTurn)* -> GameOver

**Claude API** (`pip install anthropic`):
- `client.messages.stream(model=, max_tokens=, system=, messages=)` — sync streaming context manager
- `stream.text_stream` — yields text tokens as they arrive
- Model: `claude-haiku-4-5-20251001` ($1/MTok in, $5/MTok out)
- Prompt caching: `cache_control={"type": "ephemeral"}` on system content blocks (5-min TTL, $0.10/MTok reads)

**TTS** (`pip install edge-tts`):
- `edge_tts.Communicate(text, voice, rate="+0%")` — async streaming TTS
- `.stream()` yields `{"type": "audio", "data": mp3_bytes}` chunks
- `.stream_sync()` — blocking generator equivalent
- Best voice for casting: `en-US-GuyNeural` (male, clear) or `en-GB-RyanNeural` (British esports feel)
- Latency: ~200-500ms to first audio chunk (network-dependent)
- Fallback: `pyttsx3` (offline SAPI5, ~50ms latency, worse voice quality)

**OBS integration** (`pip install obsws-python`):
- `obs.ReqClient(host, port, password)` — connects to OBS WebSocket v5 (built-in since OBS 28)
- `cl.set_input_settings(name="Commentary", settings={"text": "..."}, overlay=True)` — update text source
- Audio via VB-Cable: play decoded MP3 to "CABLE Input" device, OBS captures "CABLE Output"

**Audio playback** (`pip install sounddevice pydub`):
- `sounddevice.play(pcm_array, samplerate, device=cable_device_id)` — play to specific output device
- `pydub.AudioSegment.from_mp3(io.BytesIO(mp3_bytes))` — decode edge-tts MP3 chunks to PCM

### Game Knowledge Available

- `docs/wiki/PRISMATA_REFERENCE.md` — curated 11-section reference (resources, phases, base set, defense, breach, chill, strategy fundamentals, glossary, advanced unit quick reference)
- `bin/asset/config/cardLibrary.jso` — 105+ units with internal names, UINames, costs, toughness, abilities, scripts
- `docs/wiki/` — 448 raw wiki pages (too large for system prompt; use as retrieval source)
- `training/data/unit_index.json` — 161 canonical unit names
- **User can provide written strategy guides** — ideal for system prompt context (human-curated > wiki dumps)

### Cost Estimate

| Per game (40 turns) | Tokens | Cost |
|---|---|---|
| Input (system + state) | ~20,000 | $0.020 |
| Output (commentary) | ~2,000 | $0.010 |
| **Total** | **~22,000** | **~$0.03** |

With prompt caching on a larger system prompt (~3K tokens of game knowledge):
- First turn: $0.00375 cache write
- Turns 2-40: $0.0003/turn cache read (saves ~$0.10/game)
- **~$0.02/game with caching**

At 10 games/day streaming: **~$6/month**.

### Anti-Patterns to Avoid

- Do NOT import `prismata_sniffer` as a module from another script — the `@on_message` decorators fire at import time against the module-level `_dispatcher`. The commentary module must register its handlers in the same process.
- Do NOT use `pyttsx3` in a thread — it's not thread-safe. Use edge-tts (async) or run pyttsx3 on a dedicated thread with a queue.
- Do NOT block the sniffer proxy threads — all commentary/TTS work must be async or in background threads. The proxy threads forward TCP traffic; blocking them drops game packets.
- Do NOT send the full `raw_gameState` to Claude — it's enormous. Build a compact summary string.
- Do NOT call Claude on every Click message — aggregate per turn, generate commentary on EndTurn.

---

## Phase 1: Commentary Engine Core

**New file**: `tools/prismata_commentator.py`

### 1.1 Turn Event Aggregator

Register new `@on_message` handlers that build a per-turn event summary without interfering with existing handlers:

```python
# These handlers coexist with the existing sniffer handlers
@on_message("BeginGame", direction="S->C")  # game setup
@on_message("StartTurn", direction="S->C")  # turn boundary
@on_message("Click", direction="S->C")      # buy tracking (supplement existing)
@on_message("EndTurn", direction="S->C")     # turn boundary -> TRIGGER COMMENTARY
@on_message("GameOver")                      # game end -> final commentary
```

The aggregator builds a `TurnContext` dataclass per turn:
- Turn number, active player name
- Board state summary (from `session.last_f6_state` after StartTurn)
- Buys this turn (from `session.turn_buys`)
- Time used / time bank (from EndTurn params)
- Running attack/defense totals (derived from board state)
- Previous turn's context (for comparison / "eval shift" narrative)

### 1.2 Game Narrative Accumulator

Maintains a rolling window of the last ~5 turns of context for Claude, plus game-level metadata:
- Player names, randomizer set
- Economy trajectory (drone counts over time)
- Attack trajectory (total attack over time)
- Key moments log (first attack, first tech, breaches, large purchases)

This prevents Claude from seeing the game as isolated snapshots — it can narrate arcs like "Player 1 has been building economy for 6 turns and is finally converting to attack."

### 1.3 Board State Summarizer

Converts the raw F6 JSON into a compact text format for Claude (~200-400 tokens):

```
Turn 14 — Surfinite's turn (P1)
Set: Tarsier, Steelsplitter, Centurion, Amporilla, Zemora, Tatsu Nullifier, Iso Kronus, Feral Warden

Surfinite (P1): 8 gold, 2 green | 9 Drones, 2 Conduits, 3 Tarsiers, 2 Walls, 1 Engineer
  Attack: 3 | Defense: 5 (2 Walls + 1 Engineer)

OpponentName (P2): 6 gold, 1 blue | 7 Drones, 1 Blastforge, 1 Steelsplitter, 3 Walls, 2 Engineers
  Attack: 1 | Defense: 7 (3 Walls + 2 Engineers)

Last turn (P2): bought Steelsplitter, Wall | time: 8s
This turn (P1): bought Tarsier x2 | time: 5s

Recent: P1 has been ramping Tarsiers since turn 10. P2 is defensive-heavy with Walls.
```

### 1.4 Commentary Generation (Claude Haiku)

On each EndTurn, fire an async Claude API call:

```python
system = [
    {"type": "text", "text": PRISMATA_KNOWLEDGE, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": COMMENTARY_INSTRUCTIONS}
]
```

Where `COMMENTARY_INSTRUCTIONS` defines the personality:
```
You are an enthusiastic Prismata game commentator casting a live match.
Generate 1-2 sentences of natural commentary for this turn.
Style: energetic but knowledgeable, like an esports caster.
Focus on: strategic decisions, economy vs attack balance, key purchases, threats.
Do NOT list every unit — highlight what matters.
If nothing interesting happened, say something brief.
Keep it under 40 words. No emojis.
```

And `PRISMATA_KNOWLEDGE` is the curated game reference + any written guides the user provides.

### 1.5 Commentary Queue

A thread-safe queue that buffers generated commentary text:
- Commentary is generated async (background thread)
- TTS consumer reads from queue
- If a new turn's commentary arrives before the previous one finishes speaking, the old one is truncated/skipped (freshness > completeness)
- Special commentary types: `GAME_START` (longer intro), `GAME_OVER` (result summary), `TURN` (normal)

### Verification Checklist (Phase 1)

- [x] Run sniffer in proxy mode, play a bot game, confirm commentary engine receives all turn events — DONE (tested live on spectated games, Feb 20)
- [x] Confirm `TurnContext` is populated correctly (print to console) — DONE (GameNarrative + TurnRecord dataclass working)
- [x] Confirm board state summarizer produces readable compact text — DONE (GameContext.summary_for_llm() outputs ~200-400 token summaries)
- [x] Confirm Claude API call returns commentary (print to console) — DONE (Claude Haiku generating per-turn commentary)
- [x] Confirm commentary queue processes in order with skip-on-overflow — DONE (CommentaryWorker with maxsize=5 queue, drop-oldest)
- [ ] Measure end-to-end latency: EndTurn -> commentary text ready (target: <2s) — NOT MEASURED (qualitatively responsive, no precise timing)

---

## Phase 2: Text-to-Speech Pipeline

### 2.1 edge-tts Integration

Async TTS worker that consumes from the commentary queue:

```python
async def tts_worker(queue: asyncio.Queue, voice: str, output_device_id: int):
    while True:
        text = await queue.get()
        communicate = edge_tts.Communicate(text, voice, rate="+10%")
        mp3_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buffer.write(chunk["data"])
        # Decode and play
        mp3_buffer.seek(0)
        audio = AudioSegment.from_mp3(mp3_buffer)
        pcm = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
        sd.play(pcm, samplerate=audio.frame_rate, device=output_device_id)
        sd.wait()
```

### 2.2 Voice Selection & Tuning

Recommended voices for casting feel:
- `en-US-GuyNeural` — clear American male, good default
- `en-GB-RyanNeural` — British male, esports commentary feel
- `en-US-ChristopherNeural` — deeper American male
- `en-AU-WilliamNeural` — Australian (novelty option)

Rate: `+10%` to `+20%` for slightly faster delivery (matches casting energy).

### 2.3 Audio Output Routing

Two modes:
1. **Local preview**: Play to default audio device (for testing)
2. **Twitch mode**: Play to VB-Cable virtual device, OBS captures it

Device selection at startup:
```python
devices = sd.query_devices()
cable_id = next((i for i, d in enumerate(devices) if "CABLE Input" in d["name"]), None)
```

### 2.4 pyttsx3 Fallback

If edge-tts fails (no internet, MS endpoint down):
```python
engine = pyttsx3.init()
engine.setProperty('rate', 185)
engine.say(text)
engine.runAndWait()
```

Run on a dedicated thread with a queue — pyttsx3 is not thread-safe.

### Verification Checklist (Phase 2)

- [ ] edge-tts produces audible speech for sample commentary
- [ ] Audio plays to both default device and VB-Cable
- [ ] Commentary queue -> TTS pipeline works end-to-end (console + audio)
- [ ] Measure TTS latency: text ready -> first audio (target: <500ms)
- [ ] Fallback to pyttsx3 works when edge-tts fails
- [ ] Rapid turns don't cause audio overlap (queue skip logic works)

---

## Phase 3: OBS Integration (Twitch-Ready)

### 3.1 OBS Text Captions

Live subtitles in the stream via OBS WebSocket:

```python
import obsws_python as obs

obs_client = obs.ReqClient(host='localhost', port=4455, password='...')

def update_caption(text: str):
    obs_client.set_input_settings(
        name="CommentaryText",  # GDI+ text source in OBS
        settings={"text": text},
        overlay=True
    )
```

Update the text source when commentary is generated. Clear it after TTS finishes speaking (or after a timeout). This gives viewers both audio AND text subtitles.

### 3.2 OBS Scene Setup

Create an OBS scene with:
- **Game capture**: Prismata window
- **CommentaryText**: GDI+ text source, positioned at bottom of screen, styled as subtitle bar (semi-transparent background, white text, outline)
- **Audio Input Capture**: "CABLE Output" device (receives TTS audio from VB-Cable)
- Optional: **StatusText** source showing current turn number, player names, set

### 3.3 Commentary Overlay Styling

The text source should be styled for readability on stream:
- Font: bold sans-serif, ~24-28pt
- Color: white with black outline (2px)
- Background: semi-transparent dark bar (rgba(0,0,0,0.7))
- Position: bottom-center of screen
- Max width: 80% of screen (word wrap enabled)
- Auto-clear after 5 seconds or when next commentary arrives

### 3.4 Stream-Friendly Features

- **Commentary history panel** (optional): A second text source showing the last 3-5 commentary lines, scrolling up. Lets viewers who joined late catch up.
- **Game info panel**: Set name, player names, turn count — updated via OBS WebSocket on BeginGame.
- **"AI COMMENTATOR" badge**: Static image/text element so viewers know it's AI-generated.

### Verification Checklist (Phase 3)

- [ ] OBS WebSocket connection established from Python
- [ ] Text source updates in real-time during a game
- [ ] VB-Cable audio appears in OBS audio mixer
- [ ] Full pipeline: sniffer -> commentary -> TTS + captions -> OBS capture
- [ ] Stream preview shows synchronized audio + text
- [ ] No audio desync over a 20-minute game

---

## Phase 4: Game Knowledge & Commentary Quality

### 4.1 System Prompt Construction

The system prompt has three tiers of game knowledge:

**Tier 1 — Always included (~1,500 tokens, cached):**
- Resource types and decay rules
- Turn structure (Action, Breach, Defense phases)
- Base set units (11 units with costs and roles)
- Key strategic concepts (economy, tech, attack timing, granularity, absorb)

Source: Condense from `docs/wiki/PRISMATA_REFERENCE.md` sections 1-6, 9.

**Tier 2 — Per-game set info (~500 tokens, dynamic):**
- The 8 random units in this game's set, with costs, stats, and 1-line strategy note each
- Look up from `cardLibrary.jso` + a strategy blurb file

Source: `cardLibrary.jso` for stats, user-provided written guides for strategy blurbs.

**Tier 3 — Optional deep knowledge (~2,000 tokens, cached):**
- Written strategy guides from the user
- Common openings and counter-strategies
- Unit synergy notes (e.g., "Tarsier + Wall is the standard green attack package")

Source: User-provided guides, community knowledge.

### 4.2 Commentary Personality Modes

Support multiple "caster" personalities via system prompt variants:

| Mode | Style | Use Case |
|---|---|---|
| `hype` | Excitable, uses superlatives, dramatic | Entertainment streams |
| `analytical` | Calm, explains why moves are good/bad | Educational streams |
| `dry` | British understatement, witty | Comedy/personality streams |
| `duo` | Alternates between play-by-play and color | Premium feel (needs 2 TTS voices) |

User selects mode at startup via CLI arg: `--style hype`

### 4.3 Context-Aware Commentary Triggers

Not every turn deserves equal commentary. Priority system:

| Priority | Trigger | Example |
|---|---|---|
| HIGH | First attack purchased | "And there it is! Surfinite goes for the first Tarsier — the aggression begins!" |
| HIGH | Breach event | "BREACH! Three damage gets through and takes out two Drones!" |
| HIGH | Large economic swing | "Six Drones in one turn — that's a massive economic investment." |
| HIGH | Game over | Full result summary with context |
| MEDIUM | Tech building purchased | "Animus is down — red tech is online for Player 2." |
| MEDIUM | Unusual/creative buy | "Ooh, Zemora! That's a spicy pick in this set." |
| LOW | Standard economy turn | "Another round of Drones — both players building up." |
| SKIP | Identical to previous turn | (Say nothing, or minimal "more of the same") |

The aggregator assigns priority; low-priority turns get shorter/no commentary to avoid monotony.

### 4.4 Unit Name Pronunciation Guide

Some Prismata unit names are unusual. Include pronunciation hints in the TTS text:
- Zemora → "Zeh-MORE-ah"
- Tatsu Nullifier → "TAT-sue"
- Iso Kronus → "EYE-so CROW-nus"

Or: use SSML if edge-tts supports it (it partially does via `<phoneme>` tags).

### Verification Checklist (Phase 4)

- [x] System prompt fits within ~4K tokens total (Tier 1 + 2 + 3) — DONE (commentary_prompt.md ~2,400 tokens + dynamic set info)
- [x] Commentary references specific units and strategies correctly — DONE (tested live, Feb 20)
- [x] Commentary varies between high and low action turns — DONE (adaptive token budget: 40 fast / 120 long think)
- [x] No hallucinated unit names or abilities — DONE (mergedDeck lookup provides real unit data)
- [ ] Personality modes produce distinctly different output — NOT DONE (only one style implemented)
- [ ] Unit pronunciations sound correct via TTS — NOT DONE (Phase 2 dependency)

**Knowledge base status**: COMPLETE — 125+ sources processed across 7 category files (2,500+ lines in `docs/commentary-knowledge/`). Strategy guide synthesized at `docs/prismata-strategy-guide.md` (536 lines, 17 chapters). Condensed prompt at `tools/commentary_prompt.md`.

---

## Phase 5: Polish & Stream Production

### 5.1 Spectator Mode

The sniffer already works in spectator mode (captures spectated PvP games). Commentary system should:
- Detect whether we're playing or spectating (check `session.player_name` against `session.players`)
- Adjust perspective: "Player 1 buys..." vs "We buy..." (spectator vs player)
- Default to spectator/neutral perspective for Twitch (more natural for viewers)

### 5.2 Resilience

- **Claude API timeout**: If Haiku doesn't respond in 3s, skip commentary for that turn
- **TTS failure**: Fall back to pyttsx3, or just show text caption without audio
- **OBS disconnected**: Commentary still works in console-only mode
- **Sniffer reconnect**: If proxy connection drops and re-establishes, reset game state cleanly

### 5.3 Configuration File

`tools/commentator_config.json`:
```json
{
    "voice": "en-GB-RyanNeural",
    "voice_rate": "+15%",
    "style": "hype",
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 100,
    "tts_backend": "edge-tts",
    "obs_enabled": true,
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "audio_device": "CABLE Input",
    "caption_source_name": "CommentaryText",
    "caption_timeout_s": 6,
    "knowledge_file": "tools/prismata_casting_knowledge.md",
    "skip_low_priority": false
}
```

### 5.4 Launcher

`run_commentator.bat`:
```batch
@echo off
echo Starting Prismata Live Commentator...
echo.
echo Prerequisites:
echo   - Sniffer proxy running (python tools/prismata_sniffer.py proxy)
echo   - ANTHROPIC_API_KEY set in environment
echo   - OBS running with CommentaryText source (optional)
echo   - VB-Cable installed (optional, for Twitch audio)
echo.
python tools/prismata_commentator.py --style hype
pause
```

Or integrated into the existing `run_prismata_tools.bat` combined launcher.

### 5.5 Dual-Caster Mode (Stretch Goal)

Use two different Claude calls per turn with different system prompts:
- **Play-by-play**: Describes what happened ("Player 2 buys two Tarsiers and a Wall")
- **Color commentary**: Explains why it matters ("That's a defensive pivot — they're preparing for the Iso Kronus threat")

Each uses a different TTS voice. Alternate between them. This creates a natural broadcast feel.

### Verification Checklist (Phase 5)

- [ ] Full end-to-end test: sniffer + commentator + TTS + OBS
- [ ] 20-minute bot game produces continuous, varied commentary
- [ ] Spectator mode works (watch someone else's game)
- [ ] Graceful degradation: works without OBS, without VB-Cable
- [ ] Config file controls all tunables
- [ ] No crashes over a 1-hour session

---

## Dependency Summary

```
pip install anthropic      # Claude API
pip install edge-tts       # TTS (primary — neural voices, async)
pip install pyttsx3        # TTS (fallback — offline, SAPI5)
pip install sounddevice    # Audio output to VB-Cable
pip install pydub          # MP3 decoding from edge-tts
pip install obsws-python   # OBS WebSocket control (optional)
```

External:
- **VB-Cable** — free virtual audio driver (for Twitch audio routing)
- **OBS Studio 28+** — for streaming (built-in WebSocket v5)
- **ANTHROPIC_API_KEY** — environment variable

---

## Implementation Order & Time Estimate

| Phase | Description | Depends On | Rough Scope |
|---|---|---|---|
| 1 | Commentary engine core | Sniffer working | ~300 lines Python |
| 2 | TTS pipeline | Phase 1 | ~100 lines Python |
| 3 | OBS integration | Phase 2 + OBS setup | ~80 lines Python |
| 4 | Game knowledge & quality | Phase 1 + guides | ~prompt engineering |
| 5 | Polish & production | All above | ~config, resilience |

Phases 1-2 get you a working commentator in the console. Phase 3 makes it stream-ready. Phase 4 makes it good. Phase 5 makes it reliable.

---

## Open Questions

1. **Written guides**: User mentioned they can provide strategy guides — what format? Markdown? How detailed? This significantly impacts commentary quality.
2. **API key**: Does the user have an Anthropic API key set up, or need to create one?
3. **VB-Cable**: Already installed, or needs setup?
4. **Commentary language**: English only, or multilingual potential?
5. **Should commentary also speak during OUR turns** (when playing), or only opponent turns?
6. **Game AI eval**: Currently "not good enough" — at what point should we integrate C++ eval signals into commentary? (e.g., "The AI thinks this position is 60-40 in favor of Player 1")
