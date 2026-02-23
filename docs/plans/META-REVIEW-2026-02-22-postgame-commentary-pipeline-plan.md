# Meta-Review: Post-Game Replay Commentary Pipeline Plan

**Date:** 2026-02-22
**Plan reviewed:** `docs/plans/2026-02-22-postgame-commentary-pipeline-plan.md`
**Reviews analyzed:** 13 external reviews (R1-R13)
**Codebase validation:** 9 claims fact-checked against actual source code

---

## A.1 -- Review Summary Table

| Reviewer | Model/Source | Sentiment | Key Focus Areas | Unique Insight |
|----------|-------------|-----------|-----------------|----------------|
| **R1** | Critical Review | 85% sound, needs surgical simplification | Error recovery, token inflation, verification depth, Phase 6 overkill | Cost tracking with budget limits (`--max-cost`); idempotency with versioned filenames |
| **R2** | General Review | Solid but overengineered | Single-stage proof-of-concept, batch premature, few-shot token cost | Parallel sync via GNU `parallel` as batch alternative; single-stage as default with two-stage opt-in |
| **R3** | Detailed Technical | Well-researched but load-bearing assumptions | Token estimates wrong, nullable schema gap, prompt caching TTL for batch | `--eval-only` creates schema nullability gap that LLM prompts must handle; 30-min batch criterion is unrealistic |
| **R4** | Game-Aware | Overambitious schema for Haiku, style flags contradict scope | Analysis schema too deep for Haiku, `--validate-only` quality unsupported, prompts underspecified | `player_assessments[].mistakes` is a hallucination vector; golden output regression baseline |
| **R5** | Prompt-Focused | Prompts are the biggest risk | Prompts underspecified (80% of quality), few-shot fragile with only 3 examples, subprocess decision unresolved | Prompts deserve same field-level specificity as the Phase 1 JSON schema; grounding constraint instruction |
| **R6** | Verification-Focused | Meaningful gaps in robustness | Verification too shallow, `--validate-only` produces worse output, 8K token cap will be hit | `--validate-only` should produce structurally different (shorter) output; `--from-analysis` resume flag; output encoding specification |
| **R7** | Research-Savvy | Excellent research, prototype single-pass first | Two-stage unproven for Prismata scale, KB lookup brittle, C++ fallback chain | Pre-built `kb_units.json` at build time; config YAML for prompt/model parameters; BLEU/ROUGE scoring |
| **R8** | Grounding-Focused | Strong direction, caching/cost overconfident | Prompt caching TTL, turn/round indexing ambiguity, verification misses narrative hallucinations | Turn/round/ply indexing must be standardized; post-narrative verification + conditional repair loop; concept snippets beyond unit entries |
| **R9** | Truncated | Prompt caching critical, two-stage good | Prompt caching minimum token threshold, structured data foundation | Haiku 4.5 has **4096 token minimum** for prompt caching to engage -- system prompts under this threshold won't cache |
| **R10** | Skeptical | Well-researched but needs more skepticism | Single-stage experiment first, batch failure handling, verification expansion | Single-stage experiment as Phase 0.5 decision gate; extended thinking as alternative; verification-as-tool-call |
| **R11** | Harshest | Overly complex, conflates concerns | Haiku narrative quality insufficient, Sonnet should be default for narrative, too many output files | Make Sonnet default for narrative (Haiku for analysis); consolidate output into single file with metadata; serial batch fallback |
| **R12** | MiniMax M2.5 | Methodologically sound, may be overkill for typical games | Short-game optimization, fragile KB parsing, few-shot over-engineered for 3 examples | `--resume-stage2` flag for narrative-only reruns; exact token budget table per stage; short-game threshold for single-pass |
| **R13** | Narrative-Focused | Right architecture, prompts under-specified | Narrative prompt must exist as v0, few-shot token bomb, hallucination checks are theatre | LLM judge verification (200-token Haiku call to list unsupported claims); style distillation paragraphs instead of full examples; unit synergy appendix |

**Sentiment distribution:** 0 rejections, 2 harsh (R11, R12), 7 positive-with-caveats, 4 strongly positive. No reviewer rejected the core two-stage architecture outright, though 4 recommended testing single-stage first.

---

## A.2 -- Consensus Points

Ranked by number of reviewers who raised each point. Items marked with a codebase check have been validated against the actual source code.

### Near-Universal (8+ reviewers)

**1. Unit knowledge extraction via text search is fragile (12/13: all except R9)**
The plan proposes "simple text search for unit name headers in the KB files." Every reviewer flagged this as brittle.

**Codebase check:** CONFIRMED FRAGILE. `docs/commentary-knowledge/03-advanced-units.md` uses `###` headers for both unit names AND non-unit section headers (e.g., "### Tier 1A (Best Attackers)", "### Inflation Theory"). A text search for `### Plasmafier` would also match `### Centurion -- The Strongest Unit`. Substring collisions (e.g., "Drone" inside "Mega Drone" profiles) are a real risk.

**Verdict:** This is a real problem. Pre-built JSON index is the right fix.

---

**2. Remove `--style hype` and `--style casual` (10/13: R1, R2, R4, R5, R6, R7, R8, R10, R11, R13)**
The plan's own scope section excludes "commentary for non-expert audiences," yet `--style casual` is described as "accessible for non-expert audience." `--style hype` has no corresponding few-shot examples, no prompt specification, and no testing plan.

**Verdict:** Remove both. Ship `analytical` only. The architecture supports adding styles later.

---

**3. Phase 6 A/B comparison tool is premature (10/13: R1, R2, R3, R4, R5, R6, R7, R10, R12, R13)**
A solo developer with 3 test replays can just run the pipeline twice and read both outputs. Building a `--compare` tool with diff display adds implementation surface for no measurable benefit at this scale.

**Verdict:** Remove from Phase 6. Keep the quality rubric and `--test` mode. Defer A/B tooling indefinitely.

---

**4. Verification pass is too shallow (9/13: R1, R4, R5, R6, R8, R10, R11, R12, R13)**
The Phase 2c verification checks turn numbers, unit names, and eval values (within +/-2%). Reviewers consistently noted this misses:
- Invented purchases attributed to the wrong player
- False time pressure claims
- Incorrect eval directionality ("took a commanding lead" when eval swung against)
- Strategic claims that sound plausible but contradict the data

**Verdict:** Extend verification. Add buy-attribution checks (verify stated buys appear in the correct player's `buys` array), eval directionality checks (verify `eval_delta` sign matches claimed direction), and winner identification checks. These are all programmatic -- no extra LLM call needed.

---

### Strong Consensus (5-7 reviewers)

**5. Add `--dry-run` flag (7/13: R1, R2, R3, R5, R7, R10, R13)**
Show assembled prompts, token counts, and estimated cost without making API calls. Essential for prompt iteration.

**Verdict:** Must-do. Trivial to implement and saves real API dollars during development.

---

**6. C++ auto-fallback chain needed (7/13: R1, R3, R4, R6, R10, R11, R12)**
The plan acknowledges `--analyze` can timeout on 40+ turn games but doesn't specify automatic fallback in the Phase 4 orchestration. The pipeline should try `--analyze`, fall back to `--eval-only` on timeout, and fall back to `--validate-only` if C++ fails entirely.

**Codebase check:** CONFIRMED. The C++ exe can OOM (x86 4GB limit) and timeout on long games. `uP8mG-tr75d` (39 turns) is a test replay that could hit this.

**Verdict:** Must-do. Catch subprocess timeout, retry with degraded mode, set a flag in the JSON so downstream prompts adjust.

---

**7. Token estimates are optimistic (6/13: R2, R3, R5, R6, R8, R12)**
The plan estimates ~4K input for analysis and ~6K for narrative. Real numbers:
- Narrative: condensed KB (~2,400 tokens) + one few-shot example (~3,500 tokens) + analysis JSON (~2,000 tokens) + user template + unit knowledge = ~10K+, not 6K.
- The plan's own anti-pattern guard ("Do NOT exceed 8K input tokens for narrative") contradicts its cost table.

**Verdict:** Re-estimate before implementation. Measure actual token counts on the 3 test replays. Update cost table accordingly.

---

**8. Prompts are underspecified (5/13: R5, R6, R8, R11, R13)**
The plan meticulously describes JSON schemas, CLI flags, and file paths, but the actual system prompts -- which determine 80% of output quality -- are hand-waved as "new file: `analysis_system.md`." No content outline, no key instructions, no structural guidance.

**Verdict:** Add at minimum: the analysis prompt's section structure, key instructions for what constitutes a "turning point," the narrative prompt's framing sentence and core stylistic directives, and the user message template structure with labeled placeholders.

---

**9. Subprocess vs import must be resolved (5/13: R3, R5, R6, R11, R12)**
The plan says "subprocess or import" and the anti-pattern guard says "Do NOT import if it has side effects at module level."

**Codebase check:** REVIEWERS ARE WRONG about side effects. `generate_commentary_data.py` has a clean `if __name__ == "__main__"` guard at line 688. No module-level side effects. `argparse` is inside `main()`. **Import is safe.** R5, R6, R10, R11, R12 all assumed side effects exist -- they do not.

**Verdict:** Should resolve in the plan, but the answer is the opposite of what most reviewers assumed. **Import is the cleaner option.** The plan should commit to import with a callable function interface, not subprocess.

---

**10. Batch failure handling missing (5/13: R1, R6, R10, R12, R13)**
What happens when analysis for game 3 of a 15-game batch fails? The plan doesn't specify whether to continue with successful games, retry individually, or abort.

**Verdict:** Should-do. Separate into success/failed lists, proceed with narrative batch for successes, report failures.

---

**11. Game length handling needed (5/13: R4, R6, R8, R10, R12)**
An 8-turn rush needs different treatment than a 40-turn grind. The current schema forces games into "Opening/Development/Midgame/Endgame" phases that may not apply to rush games.

**Verdict:** Should-do. Classify games as short (<12 rounds), medium (12-25), long (>25). Adjust target message count, analysis depth, and turning point expectations accordingly.

---

**12. Remove `tier` from schema (3/13: R5, R6, R8)**

**Codebase check:** CONFIRMED. No `tier` field exists in `cardLibrary.jso` or replay JSON. The `"tier": "rare"` in the plan's schema is an invention. Tiers only exist as human-curated annotations in the knowledge base markdown files.

**Verdict:** Must-do. Remove `tier` from the Phase 1 schema. It would encourage hallucinations.

---

### Moderate Consensus (3-4 reviewers)

**13. Test single-stage before committing to two-stage (4/13: R2, R7, R10, R12)**
The research citations (WSC Sports, IBM Wimbledon) are for live sports video processing -- a fundamentally different domain from turn-based card games with already-structured replay data. A single-stage experiment on the 3 test replays costs ~$0.10 and could save significant implementation complexity.

**Verdict:** Consider. The two-stage architecture is well-justified by research, and the plan author's manual workflow already follows an analyze-then-narrate pattern. However, a quick single-stage test is cheap enough to be worth doing as a sanity check, not as a replacement.

---

**14. Few-shot selection over-engineered for 3 examples (3/13: R11, R12, R13)**
With only 3 manually-written commentaries, the dynamic selection logic is essentially hardcoded. The "if upset, if long game" branching adds complexity for minimal gain.

**Verdict:** Consider simplifying. Use one good example as default, add the second only for long games. Document that selection logic will expand as more commentaries are written.

---

**15. Prompt caching TTL incorrect for batch (3/13: R6, R8, R9)**
The plan uses `"cache_control": {"type": "ephemeral"}` with a "5-min cache" comment. But Batch API processes asynchronously over minutes to hours. The 5-minute ephemeral TTL may expire mid-batch.

**Codebase check:** R9 adds a critical detail: Haiku 4.5 has a **4096-token minimum** for prompt caching to engage. If the "shared prefix" is under 4096 tokens, caching won't fire at all.

**Verdict:** Should-do. Verify cache TTL behavior for batch. Ensure cached prefix exceeds 4096 tokens. Update cost estimates to reflect possible cache misses in batch mode.

---

**16. `--resume-stage2` flag needed (1/13: R12, but supported implicitly by R4, R6)**
If analysis succeeds but narrative fails (API error, bad output), there's no way to retry just Stage 2 from saved analysis JSON.

**Verdict:** Should-do. The intermediate file caching already saves `analysis_{CODE}.json`. Auto-detecting this and skipping to Stage 2 is straightforward and high-value for prompt iteration.

---

## A.3 -- Outlier Points

These were raised by only one reviewer but are potentially meritorious.

**[R1] Cost tracking with budget limits (`--max-cost`)**
Add a flag that aborts if estimated cost exceeds a threshold. Given the $805 AWS billing shock, this is defensive engineering that fits the user's risk profile. **Worth adding.**

**[R3] 30-minute batch criterion is unrealistic**
The plan's nice-to-have says "<30 min for 100-game batch." Two sequential Batch API rounds could take 30-90 minutes. **Drop or qualify this criterion.**

**[R4] Golden output regression baseline**
Save the first good auto-generated commentary for each test replay as a reference file. Before shipping prompt changes, manually diff against the golden file. **Simple and valuable.**

**[R6] Output encoding specification**
The context document flags Windows `cp1252` as a known gotcha. No phase-level anti-pattern guard specifies `encoding='utf-8'` for file writes. **Add to Phase 4 anti-pattern guards.**

**[R8] Turn/round/ply indexing ambiguity**
The schema uses `"round": 1` with `"player": 0`, but commentary excerpts use "T8." If the canonical index isn't standardized, verification checks will reject valid output or miss invalid output. **Worth standardizing.**

**[R8] Concept snippets beyond unit entries**
The plan only pulls from `03-advanced-units.md`. But concepts like "Absorb theory," "Chill mechanics," and "timing" from `01-game-fundamentals.md` and `04-strategy-concepts.md` explain *why* turning points matter. **Worth considering for V2.**

**[R9] Haiku 4.5 minimum cacheable prefix is 4096 tokens**
If the shared system prompt is under 4096 tokens, caching simply won't engage. This is a hard technical constraint that the plan ignores. **Critical to verify.**

**[R12] `--resume-stage2` for narrative-only reruns**
Already covered in consensus #16 above. **Should-do.**

**[R13] LLM judge verification (200-token Haiku call)**
After Stage 2, fire a cheap call: "List every factual claim in the commentary not directly supported by the analysis JSON." If non-empty, regenerate once. **Interesting but adds complexity; consider for V2.**

**[R13] Unit synergy appendix**
A 200-token mini-section listing known two-card synergies for the random set so the model can spot combos. **Nice idea for V2, not MVP.**

---

## A.4 -- Category Breakdown

### Architecture & Design

**Two-stage pipeline is the right architecture**
Raised by: R1, R2, R3, R4, R5, R6, R7, R8, R10, R11, R12, R13 (all 13, though 4 recommend testing single-stage first)

All reviewers acknowledged the two-stage split is well-justified by research. The WSC Sports, GetStream, and academic survey citations are concrete and relevant. The specific decision to use structured output for analysis and free-form for narrative was praised as well-reasoned.

**Codebase validation:** The manual commentary workflow already follows an analyze-then-narrate pattern, which supports the architecture choice.

**Analysis:** Keep the two-stage architecture. The single-stage experiment suggestion (R2, R7, R10, R12) is worth ~$0.10 and takes 30 minutes. Run it as a sanity check before Phase 2 implementation, but don't gate the plan on it.

---

**Subprocess vs import decision**
Raised by: R3, R4, R5, R6, R11, R12

**Codebase validation:** `generate_commentary_data.py` has a clean `if __name__ == "__main__"` guard. `argparse` is inside `main()`. No module-level side effects. All constant definitions (`REPLAY_URL`, `BASE_SET_NAMES`, etc.) are benign. **Import is safe and preferable.**

**Analysis:** The plan should commit to import. Extract the core logic into a callable function (e.g., `extract_game_data(code, mode="full")`) that returns the structured dict. This avoids subprocess serialization overhead, enables proper error propagation, and shares memory for the unit knowledge cache.

---

**Intermediate file caching is excellent**
Raised by: R1, R2, R3, R4, R5, R6, R8, R10, R12

Every reviewer who mentioned the `data_*.json` / `analysis_*.json` / `commentary_*.txt` caching praised it. R5 suggested moving caching from Phase 4 to Phase 1 (cache `data_*.json` immediately after extraction). This is a good refinement.

**Analysis:** Keep as-is. Move `data_*.json` caching to Phase 1.

---

### Risks & Concerns

**CRITICAL: Time data may not be available from stored replays**
Raised by: **NO REVIEWER** caught this. This is a meta-reviewer finding from codebase validation.

**Codebase validation:** The plan's schema includes `time_used`, `time_bank`, and `time_control` fields. However, `time_used` and `time_bank` come from the **live wire protocol** (EndTurn messages contain `timeTaken`), NOT from stored replay JSON on S3. The S3 stored replay JSON only has `commandList` (clicks) and `clicksPerTurn`. There is no `time_used` per turn in the stored format.

This means:
- For replays captured via the sniffer proxy (live games), time data IS available in the sniffer's recorded messages.
- For replays fetched from S3 (the plan's primary source), time data is **NOT available**.
- R10 mentions adding time pressure analysis, R8 mentions time data, R13 mentions `timeUsed` -- all assume this data exists in the replay JSON. It does not.

**Impact:** The schema includes fields that will be null/absent for the vast majority of replays. Commentary referencing time pressure ("Player X was running low on time") would be hallucinated unless the model is explicitly told time data is unavailable.

**Recommendation:** Remove `time_used`, `time_bank`, and `time_control` from the core schema. Add them as optional fields populated only when the data source is a sniffer capture (not an S3 replay). Add an explicit instruction in both prompts: "Do NOT reference time pressure or clock status unless `has_time_data` is true in the data."

---

**`stepper_applied_pct` is not a direct field**
Raised by: R13 (noted they couldn't see the schema)

**Codebase validation:** The C++ outputs `stepper_total_clicks`, `stepper_applied_clicks`, `stepper_benign_skips`. The percentage is calculated in Python: `(applied + benign) / total > 0.8`. The `stepper_reliable` boolean is derived from this threshold (hardcoded at line 574 of `generate_commentary_data.py`).

**Impact:** Minor. The plan's schema shows `stepper_applied_pct` as a field, which is fine -- it just needs to be computed from the underlying C++ outputs. Not a real issue.

---

**Analysis schema may be overambitious for Haiku**
Raised by: R4, R5, R10

The proposed schema requires 8 top-level concepts with nested arrays. R4 specifically noted that `player_assessments[].mistakes` will likely be hallucinated for players who played well (the model will fabricate minor errors), and `commentary_hooks` asks for meta-reasoning that is hit-or-miss at Haiku quality.

**Analysis:** This is a legitimate concern. Reduce the V1 schema: drop `commentary_hooks` (meta-reasoning), make `key_decisions` in phases optional, and constrain `mistakes` to only cite turns where `ai_agrees == false`. This limits the hallucination surface without losing the schema's core value.

---

**`--validate-only` produces fundamentally worse output**
Raised by: R4, R6

Without `eval_pct`, `eval_delta`, `ai_buys`, and `ai_agrees`, the analysis stage loses its most valuable inputs. The plan lists "works without C++ exe" as a must-have success criterion AND "quality parity with manual examples" as another must-have -- these cannot both be true for `--validate-only` mode.

**Analysis:** R6's suggestion is correct: `--validate-only` should produce a structurally different (shorter) output format. Lower the quality bar for this mode explicitly. It's a fallback, not the primary path.

---

### Suggested Removals / Simplifications

**Remove `--style hype` and `--style casual`** (10/13)
Covered in consensus point #2. Remove.

**Remove Phase 6 A/B comparison tool** (10/13)
Covered in consensus point #3. Remove.

**Remove `tier` from schema** (3/13, but codebase-confirmed)
Covered in consensus point #12. Remove.

**Remove `--batch-codes` inline CLI option** (R6)
Having both `--batch codes.txt` and `--batch-codes "A,B,C"` is minor convenience. Replay codes contain `+` and `@` which complicate CSV parsing. Support file input only.

**Analysis:** Good simplification. Remove.

**Simplify few-shot selection** (R1, R2, R11, R12, R13)
With only 3 examples, the dynamic selection is essentially hardcoded. Use one good default example; add the second only for games matching specific criteria.

**Analysis:** Simplify but don't eliminate. The heuristic ("if upset, use upset example") is trivial to implement and genuinely helps. Just don't over-engineer it.

---

### Suggested Additions / Features

**`--dry-run` flag** (7/13)
Covered in consensus point #5. Must-do.

**C++ auto-fallback chain** (7/13)
Covered in consensus point #6. Must-do.

**Game length classification** (5/13)
Covered in consensus point #11. Should-do.

**Pre-built unit knowledge JSON index** (R2, R3, R4, R7, R8, R12)
Instead of runtime text search, pre-parse KB files into `tools/unit_knowledge_index.json` keyed by exact unit name. O(1) lookup at game time. Name normalization failures are visible during preprocessing.

**Analysis:** This is the right fix for the fragile KB extraction. Should-do.

**`max_tokens` specification for API calls** (R6)
The plan never specifies the `max_tokens` parameter. For Stage 1 (structured, ~2K out): `max_tokens=2500`. For Stage 2 (narrative, ~3K out): `max_tokens=4096`. Getting this wrong causes silent truncation.

**Analysis:** Should-do. Pin these values in the plan.

**Replay code validation at startup** (R6)
A simple regex check for the replay code format before fetching from S3 saves wasted work on typos.

**Analysis:** Minor but cheap. Should-do.

---

### Alternative Approaches

**Single-stage with chain-of-thought** (R2, R5, R7, R10, R12)
A single call with "First analyze in JSON, then write commentary" might achieve 85-90% quality at 50% cost. Worth testing as Phase 0.5 decision gate.

**Analysis:** Worth a ~$0.10 experiment. Don't gate the plan on it, but run the test before committing to Phase 2 implementation.

**Pre-built unit knowledge cache** (R2, R3, R4, R7, R8, R12)
Consensus alternative to runtime text search. Already addressed above.

**Sonnet for analysis, Haiku for narrative** (R1, R11, R12)
Analysis requires deeper strategic understanding; narrative is more stylistic. Cost: ~$0.04/game vs $0.02/game.

**Analysis:** Interesting but backwards from R11 (who suggested Haiku analysis + Sonnet narrative). The plan's current approach (Haiku for both with Sonnet opt-in) is the right starting point. Test quality before adding model-split complexity.

**Algorithmic pre-analysis instead of LLM analysis** (R4, R5, R8)
Use eval deltas to identify turning points deterministically, then pass pre-computed candidates to the narrative LLM. Eliminates a hallucination vector and an API call.

**Analysis:** This is a strong idea. Eval deltas > threshold = turning point is deterministic, free, and correct. The LLM is better at *interpreting* turning points than *identifying* them. However, the LLM adds value in phase detection and player assessment. Consider a hybrid: deterministic turning points + LLM for phase boundaries and strategic interpretation.

---

### Confirmed Good / Keep As-Is

These elements were praised by multiple reviewers with no dissent:

1. **Two-stage pipeline architecture** -- research-backed, matches manual workflow
2. **Haiku default with Sonnet upgrade option** -- correct cost/quality trade-off
3. **Intermediate file caching** -- universally praised as the best decision in the plan
4. **Anti-pattern guards per phase** -- specific, experienced, prevent regressions
5. **Programmatic verification pass concept** -- right approach (cheap, deterministic), even if scope needs expansion
6. **Following `discord_knowledge_extractor.py` batch pattern** -- proven, reduces risk
7. **Phase ordering and dependency graph** -- correct
8. **Cost tracking per run** -- essential for a cost-conscious developer
9. **`--validate-only` fallback concept** -- good for portability (even if quality bar needs clarification)
10. **Structured output for analysis, free-form for narrative** -- correct split

---

### Implementation Details & Nits

- **Model names inconsistent:** "Haiku 4.5" in prose vs `claude-haiku-4-5-20251001` in code. Use SDK constants. (R2, R10)
- **`--validate-only` vs `--validate` naming:** The plan uses `--validate-only` but the existing tool has `--validate`. Match existing naming. (R1)

**Codebase check:** CONFIRMED. `generate_commentary_data.py` has `--validate` flag, not `--validate-only`. The plan's CLI should match.

- **Phase 2b schema uses Python type annotations** (`str`, `[int, int]`) instead of JSON Schema format. Label as pseudocode or convert to proper JSON Schema. (R4, R6, R8)
- **`--think-time 50` flag appears in CLI example but is undefined.** Remove from examples or document. (R4, R6, R12)
- **Phase 3b references line numbers** ("lines 163-178") in a living document. Use section names instead. (R3, R4)
- **Replay code filename encoding:** `+` and `@` in replay codes need consistent encoding for filenames. (R2, R7, R8)
- **Phase 5 "parallelizable" claim for Phase 1:** C++ exe is x86, 4GB limit. Concurrent C++ subprocesses need a concurrency limit (probably 1-2). (R5)

---

### Dependencies & Integration

**arXiv citation 2506.17294 may be problematic** (R3, R4, R6)
The arXiv ID `2506.xxxxx` implies a June 2025 paper. This is plausible (plan date is Feb 2026), but three reviewers flagged it for verification.

**Analysis:** The paper likely exists (submitted June 2025, plan written Feb 2026). Verify the URL works and the citation is accurate. If the paper doesn't exist, this undermines the research foundation.

**No `jsonschema` validation of the schema file** (R3, R7)
`commentary_schema.json` is created but never used programmatically. Either add `jsonschema.validate()` after Phase 1 JSON generation, or drop the schema file and document the structure inline.

**Analysis:** Add validation. It's a one-line `jsonschema.validate()` call and catches drift early.

---

### Future Considerations

- **Unit synergy detection** (R11, R13): Recognize combos like "Plasmafier + Galvani Drone." Worth adding to V2 once single-unit knowledge works.
- **Comparative analysis** (R11): Compare to other games with the same unit set from 31K expert replays. Ambitious but compelling.
- **Self-improving few-shot pool** (R7): Use generated commentaries that pass quality rubric as future few-shot examples. Natural quality flywheel.
- **Local small model for Stage 1** (R13): A 3B model fine-tuned on Prismata positions could replace the LLM analysis call. Breaks the API cost curve entirely. Long-term goal.

---

## A.5 -- Conflicts & Contradictions

### Conflict 1: Two-stage vs single-stage

**Pro two-stage (R1, R5, R6, R8):** Research-backed. Analysis and narrative require different cognitive modes. Structured intermediate enables verification. Manual workflow already follows this pattern.

**Pro single-stage (R2, R7, R10, R12):** Prismata games are simpler than sports broadcasting. 15-turn games don't need the overhead. Single-pass with chain-of-thought might achieve 90% quality at 50% cost.

**Recommendation:** Keep two-stage as the architecture. Run a single-stage experiment (~$0.10) on the 3 test replays before Phase 2 implementation. If single-stage quality is genuinely comparable, consider it as a `--fast` mode for short games (<12 rounds). The two-stage pipeline's value increases with game complexity.

---

### Conflict 2: Sonnet as default vs Haiku as default

**Haiku default (R1, R2, R3, R7, R10, R12, R13):** Cost-conscious. Haiku with excellent prompts + few-shot examples + structured data can match Sonnet. Community is small; cost per game matters.

**Sonnet default (R11):** "If Haiku can't achieve quality parity with manual examples, Sonnet must be default regardless of cost. The community will judge quality, not cost efficiency."

**Recommendation:** Keep Haiku as default. The manual commentaries prove that *data quality* matters more than model capability. The prompts and structured data do the heavy lifting. Offer `--model sonnet` for premium quality. Re-evaluate after testing on 10+ diverse replays.

---

### Conflict 3: Multiple output files vs consolidated single file

**Multiple files (R1, R3, R4, R5, R6, R8, R10, R12, R13):** Separate `data_*.json`, `analysis_*.json`, and `commentary_*.txt` enables debugging and prompt iteration without re-running expensive steps. Universally praised.

**Single file (R11):** "Too many output files creates clutter. Should be single commentary file with analysis appended as metadata."

**Recommendation:** Keep multiple files. The debugging and iteration value far outweighs the "clutter" concern. A solo developer iterating on prompts needs to inspect intermediates. This was one of the most universally praised design decisions.

---

### Conflict 4: Full few-shot examples vs style-distilled summaries

**Full examples (R3, R5, R6):** Concrete examples produce better style matching than abstract rules, especially for Haiku. The WSC Sports research validates dynamic few-shot selection.

**Style distillation (R1, R2, R7, R13):** Replace 3.5K-token examples with 400-500 token "style guides." Saves tokens, more generalizable.

**Recommendation:** Start with full examples (the token cost is acceptable for V1). If the 8K narrative token budget is consistently exceeded, extract style templates as a fallback. Don't pre-optimize -- measure first.

---

### Conflict 5: Prompt files (separate .md) vs inline Python strings

**Separate files (R5, R6, R8):** Easier to iterate, version, and review. Matches the plan's approach.

**Inline strings (R1):** "Three separate prompt files creates maintenance burden. Use Python string templates with clear sections."

**Recommendation:** Keep separate files. Prompt iteration is the primary development activity for this pipeline. Separate files enable quick editing without touching Python code, diff-friendly version control, and easier collaboration (e.g., sharing a prompt file for external review). The "maintenance burden" of 3 files is trivial.

---

## A.6 -- Recommended Plan Changes

### Must-Do (High consensus, high impact, addresses real risks)

**M1. Pre-build unit knowledge JSON index**
Replace runtime text search with a pre-processed `tools/unit_knowledge_index.json`. Parse KB files once, keyed by exact unit name as it appears in `mergedDeck`. Log warnings during build for units with no KB entry. O(1) lookup at game time. Regenerate when KB updates (manual or scripted).

**M2. Remove `--style hype` and `--style casual`**
Ship `analytical` only. Contradicts stated scope. No prompts, no examples, no testing plan for other styles.

**M3. Remove Phase 6 A/B comparison tool**
Defer indefinitely. Keep quality rubric and `--test` mode.

**M4. Add `--dry-run` flag**
Assemble prompts, print token counts and estimated cost, exit without API calls. Add in Phase 2, not Phase 6.

**M5. Add C++ auto-fallback chain**
`--analyze` timeout -> `--eval-only` -> `--validate-only`. Set `"analysis_mode"` flag in JSON so downstream prompts adjust expectations. Log warnings at each degradation.

**M6. Extend verification pass**
Add: buy attribution per player per turn, eval directionality sign check, winner identification, phase round range gap/overlap detection. All programmatic.

**M7. Remove `tier` from Phase 1 schema**
Does not exist in replay data or cardLibrary. Would encourage hallucinations.

**M8. Remove time data fields from core schema (or mark optional)**
`time_used`, `time_bank`, `time_control` are NOT available from S3 stored replays. Only available from live sniffer captures. Mark as optional with `has_time_data` boolean. Add explicit prompt instruction: "Do NOT reference time pressure unless `has_time_data` is true." **This is a critical finding that no reviewer caught.**

**M9. Resolve subprocess vs import: commit to import**
`generate_commentary_data.py` has a clean `if __name__ == "__main__"` guard. No module-level side effects. Import is safe and preferable. Extract core logic into a callable function.

---

### Should-Do (Strong suggestions that meaningfully improve the plan)

**S1. Re-estimate token counts with real measurements**
Before Phase 2, run the 3 test replays through Phase 1, assemble the full prompts, and measure actual token counts. Update the cost table and success criteria.

**S2. Add game length classification**
Short (<12 rounds): 2-3 messages, 0-1 turning points, simplified phase structure. Medium (12-25): current schema. Long (>25): focus on top 6 eval swings, auto-fallback to `--eval-only` if `--analyze` times out.

**S3. Add prompt content outlines**
Include at minimum: analysis prompt section structure, key instructions for turning point identification, narrative prompt framing and stylistic directives, user message template with labeled placeholders.

**S4. Add `--resume-stage2` / auto-detect cached analysis**
If `analysis_{CODE}.json` exists and `data_{CODE}.json` exists, skip to Stage 2. Enable narrative-only reruns for prompt iteration.

**S5. Specify `max_tokens` for both API calls**
Stage 1: `max_tokens=2500`. Stage 2: `max_tokens=4096`. Prevents silent truncation.

**S6. Add batch failure handling**
Separate success/failed lists after analysis batch. Proceed with narrative batch for successes. Report failures. Optionally retry failed games synchronously.

**S7. Remove `--batch-codes` inline option**
Support file input only. Replay codes contain `+` and `@` which complicate delimiter parsing.

**S8. Add schema nullability for `--eval-only` mode**
Mark `eval_pct`, `eval_delta`, `ai_buys`, `ai_agrees`, `agreement_rate`, `biggest_mistake` as nullable. Add conditional phrasing in analysis prompt: "If eval data is not available, omit numerical eval claims."

**S9. Verify prompt caching prerequisites**
Confirm Haiku 4.5's minimum cacheable prefix is 4096 tokens. Ensure the shared system prompt exceeds this. For batch, verify cache TTL behavior and update cost estimates.

**S10. Add `jsonschema.validate()` call**
Validate Phase 1 JSON output against `commentary_schema.json` before proceeding to Phase 2.

---

### Consider (Good ideas worth thinking about -- pick list)

**C1. Run single-stage experiment as Phase 0.5**
Cost: ~$0.10. Time: 30 minutes. Tests whether single-stage Haiku with structured data + few-shot achieves 90%+ quality. If yes, consider as `--fast` mode for short games.

**C2. Deterministic turning point detection**
Pre-compute turning points from eval deltas (|eval_delta| > threshold). Pass as candidates to the LLM instead of asking it to identify them. Eliminates a hallucination vector. LLM still interprets *why* they matter.

**C3. Constrain `mistakes` to AI-flagged turns**
In analysis prompt: "Only cite a turn as a mistake if `ai_agrees` is false for that turn." Limits hallucination surface.

**C4. Golden output regression baseline**
Save first good auto-generated commentary per test replay as reference. Diff against golden file before shipping prompt changes.

**C5. Post-narrative LLM verification (V2)**
A 200-token Haiku call: "List every factual claim not supported by the analysis JSON." If non-empty, regenerate once. Adds cost but catches subtle hallucinations.

**C6. Reduce analysis schema for V1**
Drop `commentary_hooks` (meta-reasoning is unreliable), make `key_decisions` optional, constrain `mistakes`. Expand in V2 after validating Haiku's performance.

**C7. `--max-cost` budget limit**
Abort if estimated cost exceeds threshold. Defensive engineering that fits the user's risk profile.

**C8. Standardize turn indexing**
Define a canonical index (ply? round+player? T-number?) used consistently in schema, verification, and prompts. Prevents "T8" vs "round 4, player 1" confusion.

---

### Reject (Suggestions to ignore, and why)

**X1. Make Sonnet the default for narrative (R11)**
The manual commentaries prove data quality > model capability. Haiku at $0.02/game vs Sonnet at $0.10/game is a 5x cost difference. For a solo developer posting "dozens per week," this matters. Keep Haiku default with Sonnet opt-in.

**X2. Consolidate output into a single file (R11)**
Multiple intermediate files is one of the plan's best decisions. Debugging and prompt iteration require inspecting intermediates. The "clutter" is a feature.

**X3. Use a local 3B model for Stage 1 (R13)**
Requires GPU setup, fine-tuning infrastructure, and ongoing maintenance. Completely disproportionate to the project scale. Reject for now; revisit if API costs become a bottleneck.

**X4. Replace batch mode with `parallel -j4` (R2)**
This doesn't get the 50% Batch API discount. For 100 games, that's $1.75 savings. The proven batch pattern from `discord_knowledge_extractor.py` is already written and tested.

**X5. Use Ollama/Llama3.2 for analysis (R7)**
Same issue as X3. Local model infrastructure is disproportionate to the scale of this project.

**X6. Remove intermediate file caching (R11)**
Every other reviewer praised this. Hard reject.

**X7. Drop the 8K token limit entirely (R13: "Haiku context is 200K")**
The 8K limit is a *cost* constraint, not a context-length constraint. Sending 200K tokens to Haiku would cost orders of magnitude more. The limit should be a soft cap with a trim strategy, but it shouldn't be removed.

**X8. `xz` compression for cached JSON (R13)**
Over-engineering for JSON files that are 10-50KB each. Standard filesystem is fine.

---

## A.7 -- What Stays

The following elements were confirmed as solid by the review consensus and should remain unchanged (or with only minor refinements noted above):

1. **Two-stage LLM pipeline (analysis then narrative)** -- research-backed, matches manual workflow, enables verification between stages.

2. **Haiku 4.5 as default model with Sonnet opt-in** -- correct cost/quality trade-off for the project scale.

3. **Phase 1 structured JSON extraction** -- highest-value work in the plan. Decouples data extraction from LLM calls.

4. **Intermediate file caching (`data_*.json`, `analysis_*.json`, `commentary_*.txt`)** -- universally praised. Move `data_*.json` caching to Phase 1.

5. **Anti-pattern guards per phase** -- specific, experienced, prevent regressions. Keep all of them.

6. **Programmatic verification pass (Phase 2c)** -- right approach (cheap, deterministic). Expand scope per M6 above.

7. **Structured output for analysis, free-form for narrative** -- correct split. JSON constraints help parseability; prose needs flexibility.

8. **Following `discord_knowledge_extractor.py` batch pattern** -- proven code, reduces risk.

9. **Cost tracking per run** -- essential for a cost-conscious developer.

10. **Phase ordering (1-4 core, 5-6 enhancements)** -- correct dependency chain.

11. **Dynamic few-shot selection concept** -- the instinct is right (match example to game characteristics). Simplify the implementation for V1 given only 3 examples, but preserve the architecture for expansion.

12. **Separate prompt files for each stage** -- enables iteration without touching Python code.

13. **`--validate-only` fallback concept** -- valuable for portability. Clarify that quality expectations are lower in this mode.

14. **Phase 5 batch processing with Batch API** -- 50% discount is real. Two-batch sequential approach (analysis first, narrative second) correctly handles the dependency chain. Fix the failure handling per S6.

15. **The 3 test replays** (`FxCfR-K49T+`, `WjhmP-WWdXx`, `uP8mG-tr75d`) -- cover upset, Masters mirror, and long grind. R3 correctly notes missing coverage for rush games and buySac mechanics; add these as additional test cases, don't replace the existing three.
