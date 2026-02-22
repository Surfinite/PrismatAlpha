You are analyzing a completed Prismata game. Your task is to identify the key strategic decisions, turning points, and phases of the game based on the structured data provided.

## Game Rules Summary

Prismata is a turn-based, perfect-information strategy game. Two players buy units from 11 base-set units plus 5-8 random units from ~105. No luck, no hidden info. Goal: destroy all enemy units. P1 starts with 6 Drones + 2 Engineers; P2 gets 7 Drones + 2 Engineers (extra Drone compensates for going second).

Each turn has two phases: Defense (assign blockers against incoming attack) then Action (use abilities, buy units). Attack pools across all your attackers. If attack < defense, defender chooses which blocker absorbs (non-lethal damage heals). If attack >= defense: breach -- all blockers die, excess damage assigned by the attacker to any enemy units.

Resources: Gold (persists, from Drones), Green (persists, from Conduit), Blue (use-or-lose, from Blastforge), Red (use-or-lose, from Animus), Energy (use-or-lose, from Engineer).

Key concepts: Absorb (non-lethal damage on non-fragile blocker, heals next turn), Breach (attack exceeds total defense, attacker picks targets), Chill (prevents blocking), Prompt (zero build time), Frontline (targetable through blockers), Fragile (does not heal).

## Your Task

Analyze the game data and produce a structured JSON analysis. Guidelines:

- **Turning points**: Select from the provided `turning_point_candidates` list. Explain WHY each is significant. Do not invent turning points not in the candidates.
- **Phases**: Identify natural game phases (opening, midgame, endgame, or more specific labels). Short games (<12 rounds) may have no clear phases -- set `has_clear_phases` to false.
- **Mistakes**: Only cite a turn as a mistake if `ai_agrees` is false for that turn. If eval data is not available (`data_quality.has_eval` is false), omit numerical eval claims and focus on purchase patterns.
- **Player assessments**: Base on actual purchases shown in the data. Do not invent purchases. Use exact player names from the data (e.g., "Surfinite", not "Surfinite (P0)").
- **Set analysis**: What strategies does the random set enable? Which units are key?
- **Decisive factor**: One sentence explaining what decided the game outcome.

## Unit Knowledge

The game data includes a `unit_knowledge` field with strategic notes for each unit in the random set and relevant mechanics concepts. Use these to inform your analysis.

## Output Schema

Return a JSON object with exactly these fields:

```json
{
  "game_narrative_arc": "2-3 sentence summary of the entire game",
  "has_clear_phases": true,
  "phase_confidence": "high|medium|low",
  "phases": [
    {
      "name": "Phase name (flexible, not limited to Opening/Mid/End)",
      "rounds": [start_round, end_round],
      "summary": "What happened in this phase",
      "key_decisions": ["Decision 1", "Decision 2"]
    }
  ],
  "turning_points": [
    {
      "ply": 1,
      "round": 1,
      "player": 0,
      "description": "What happened",
      "impact": "Why it mattered",
      "eval_before": 50.0,
      "eval_after": 55.0
    }
  ],
  "player_assessments": [
    {
      "player": "PlayerName",
      "strategy_summary": "Overall strategy description",
      "strengths": ["Strength 1"],
      "mistakes": ["Mistake 1"],
      "notable_plies": [5, 12]
    }
  ],
  "set_analysis": "What strategies the random set enables",
  "decisive_factor": "One sentence: what decided the game"
}
```

Notes:
- `phases` may be empty if `has_clear_phases` is false
- `turning_points` may be empty if no significant swings occurred
- `eval_before`/`eval_after` should be null if eval data is not available
- `notable_plies` uses ply index (1-based half-turn), but descriptions should reference "Turn N" (round number) for readability
- `mistakes` array should be empty if no AI disagreements exist in the data
