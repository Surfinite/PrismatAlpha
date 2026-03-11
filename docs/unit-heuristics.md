# Unit-Specific Heuristics Catalog

Future portfolio extensions for units with non-obvious optimal play patterns. These would be implemented as alternative PartialPlayers added to the PPPortfolio, letting the search explore both "normal" and "heuristic-guided" branches.

## Architecture

The existing PPPortfolio iterates combinations across phases (Defense x Ability x Buy x Breach). Currently defense has only one entry (DefenseSolver). Adding unit-specific defense variants expands the search space cheaply — the evaluation function picks the winner.

## Heuristics

### Xaetron — Alternating Defense Cycle

**Pattern:** Alternate whether Xaetron is used for defense each turn. When Xaetron is low health, skip it for blocking (this defense and next turn's). This causes the action phase to overbuy defense to compensate, which sets up a much stronger position the turn after, when Xaetron is back at high health and can defend normally again.

**Implementation idea:** Check Xaetron's current health. If low, exclude it from the blocker pool in an alternate DefenseSolver. If high, play as normal. No cross-turn state tracking needed — health encodes which phase of the cycle you're in.

**Why hand-coded:** This two-turn cycle pattern is extremely hard to learn from data without massive compute. The heuristic is trivial to express and the search still evaluates whether it's actually beneficial in each board state.

---

*Add new entries here as more unit-specific patterns are identified.*
