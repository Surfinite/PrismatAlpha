"""
For every player config in each of the three sources (local config.txt, SWF
short blob, SWF full blob), report which opening books that player consumes
via its RootMoveIterator and MoveIterator chains.

Reuses the same resolver semantics as diff_iterator_chains.py:
 - PPPortfolio.include is followed
 - ActionAbility_Combination.combination is flattened
 - ActionBuy_OpeningBook is a leaf; its openingBook reference is captured

Writes a Markdown report to docs/scratch/ob_consumption_map.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_TXT = REPO_ROOT / "bin" / "asset" / "config" / "config.txt"
SWF_SHORT = REPO_ROOT / "tmp_swf_extract" / "93_AI.AIThreadHandler_aiParam_shortTextLoad.bin"
SWF_FULL = REPO_ROOT / "tmp_swf_extract" / "148_AI.AIThreadHandler_aiParamTextLoad.bin"
OUTPUT_MD = REPO_ROOT / "docs" / "scratch" / "ob_consumption_map.md"


def _strip_line_comments(text: str) -> str:
    return re.sub(r"//[^\n]*", "", text)


def load_json_or_jsonish(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(_strip_line_comments(text))


class Blob:
    def __init__(self, name: str, data: dict):
        self.name = name
        self.move_iterators: dict = data.get("Move Iterators", {})
        self.partial_players: dict = data.get("Partial Players", {})
        self.opening_books: dict = data.get("Opening Books", {})
        self.players: dict = data.get("Players", {})


def resolve_iterator_slots(blob: Blob, name: str | None, depth: int = 0) -> list[list[str]] | None:
    if name is None:
        return None
    if depth > 20:
        return None
    cfg = blob.move_iterators.get(name)
    if cfg is None:
        return None
    base: list[list[str]] = [[], [], [], []]
    inc = cfg.get("include")
    if inc:
        parent = resolve_iterator_slots(blob, inc, depth + 1)
        if parent:
            for i, slot in enumerate(parent):
                base[i].extend(slot)
    own = cfg.get("PartialPlayers", [[], [], [], []])
    for i, slot in enumerate(own):
        if isinstance(slot, list):
            base[i].extend(slot)
    return base


def resolve_partial_chain(blob: Blob, name: str, depth: int = 0,
                          visited: set | None = None) -> list[str]:
    if visited is None:
        visited = set()
    if name in visited or depth > 20:
        return [name]
    visited2 = visited | {name}
    cfg = blob.partial_players.get(name)
    if cfg is None or not isinstance(cfg, dict):
        return [name]
    if cfg.get("type") == "ActionAbility_Combination":
        out: list[str] = []
        for c in cfg.get("combination", []):
            out.extend(resolve_partial_chain(blob, c, depth + 1, visited2))
        return out
    return [name]


def collect_obs_from_iterator(blob: Blob, iterator_name: str | None) -> list[tuple[str, str]]:
    """Return [(partial_name, opening_book_name), ...] reached from the iterator."""
    if not iterator_name:
        return []
    slots = resolve_iterator_slots(blob, iterator_name)
    if not slots:
        return []
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for slot in slots:
        for partial_name in slot:
            # Walk the chain — but only flatten ActionAbility_Combination.
            # ActionBuy_OpeningBook itself is a leaf.
            for leaf in resolve_partial_chain(blob, partial_name):
                cfg = blob.partial_players.get(leaf)
                if isinstance(cfg, dict) and cfg.get("type") == "ActionBuy_OpeningBook":
                    ob = cfg.get("openingBook", "?")
                    key = (leaf, ob)
                    if key not in seen:
                        seen.add(key)
                        out.append(key)
    return out


def format_ob_entry(blob: Blob, ob_name: str) -> str:
    entries = blob.opening_books.get(ob_name)
    if entries is None:
        return f"`{ob_name}` (MISSING)"
    return f"`{ob_name}` ({len(entries)})"


def build_player_table(blob: Blob, header_extra: str = "") -> str:
    out: list[str] = []
    out.append(f"### Source: {blob.name}{header_extra}\n\n")
    if not blob.players:
        out.append("_No Players section in this blob._\n\n")
        return "".join(out)
    out.append("| Player | RootMoveIterator | MoveIterator | OBs consumed (root) | OBs consumed (per-node) |\n")
    out.append("|---|---|---|---|---|\n")
    for player_name in sorted(blob.players.keys()):
        cfg = blob.players[player_name]
        if not isinstance(cfg, dict):
            continue
        root_it = cfg.get("RootMoveIterator")
        node_it = cfg.get("MoveIterator")
        # Some Player types use `iterator` instead (e.g. RandomFromIterator)
        if root_it is None and node_it is None:
            it = cfg.get("iterator")
            root_it = node_it = it
        # PPSequence-style players don't have an iterator
        if cfg.get("type") == "Player_PPSequence":
            # Treat the PartialPlayers list as one "slot"
            pp_list = cfg.get("PartialPlayers", [])
            obs: list[tuple[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for partial_name in pp_list:
                for leaf in resolve_partial_chain(blob, partial_name):
                    leaf_cfg = blob.partial_players.get(leaf)
                    if isinstance(leaf_cfg, dict) and leaf_cfg.get("type") == "ActionBuy_OpeningBook":
                        ob = leaf_cfg.get("openingBook", "?")
                        key = (leaf, ob)
                        if key not in seen:
                            seen.add(key)
                            obs.append(key)
            ob_root = ", ".join(format_ob_entry(blob, ob) for _, ob in obs) or "—"
            out.append(f"| `{player_name}` | _PPSequence_ | — | {ob_root} | — |\n")
            continue
        ob_root = collect_obs_from_iterator(blob, root_it)
        ob_node = collect_obs_from_iterator(blob, node_it)
        ob_root_s = ", ".join(format_ob_entry(blob, ob) for _, ob in ob_root) or "—"
        ob_node_s = ", ".join(format_ob_entry(blob, ob) for _, ob in ob_node) or "—"
        out.append(f"| `{player_name}` | `{root_it or '—'}` | `{node_it or '—'}` | {ob_root_s} | {ob_node_s} |\n")
    out.append("\n")
    return "".join(out)


def build_report(local: Blob, short: Blob, full: Blob) -> str:
    out: list[str] = []
    out.append("# Per-player opening-book consumption map\n\n")
    out.append("For each player config in each source, lists the opening books reachable from "
               "its RootMoveIterator (used at the search root) and its MoveIterator (used at "
               "every search node). `(N)` after each OB name is its entry count. "
               "Iterators are resolved through `PPPortfolio.include`; partials are flattened "
               "through `ActionAbility_Combination.combination`.\n\n")
    out.append("## 1. Summary of OBs defined in each source\n\n")
    for blob in (local, short, full):
        names = sorted(blob.opening_books.keys())
        total = sum(len(v) if isinstance(v, list) else 0 for v in blob.opening_books.values())
        out.append(f"- **{blob.name}**: {len(names)} OBs, {total} entries total\n")
        out.append(f"  - {', '.join(names)}\n")
    out.append("\n")

    out.append("## 2. Per-player OB consumption\n\n")
    out.append(build_player_table(local, " (local config.txt)"))
    out.append(build_player_table(short, " (SWF short blob — used for AI_NO_OPENINGS difficulties)"))
    out.append(build_player_table(full, " (SWF full blob — used for everything else, e.g. BL_Normal_Master)"))

    out.append("## 3. Highlights\n\n")

    # Cross-check: HardestAI in SWF short blob
    if "HardestAI" in short.players:
        obs = collect_obs_from_iterator(short, short.players["HardestAI"].get("RootMoveIterator"))
        out.append(f"- **SWF HardestAI** (= live MasterBot per UINotHonorableIcon.as:50) consumes "
                   f"{len(obs)} OB(s) at its root: "
                   f"{', '.join(format_ob_entry(short, ob) for _, ob in obs)}.\n")
    if "LiveHardestAIUCT" in local.players:
        obs = collect_obs_from_iterator(local, local.players["LiveHardestAIUCT"].get("RootMoveIterator"))
        out.append(f"- **Local LiveHardestAIUCT** consumes "
                   f"{len(obs)} OB(s) at its root: "
                   f"{', '.join(format_ob_entry(local, ob) for _, ob in obs)}.\n")
    if "HardestAI" in local.players:
        obs = collect_obs_from_iterator(local, local.players["HardestAI"].get("RootMoveIterator"))
        out.append(f"- **Local HardestAI** (HardIterator_Root family) consumes "
                   f"{len(obs)} OB(s) at its root: "
                   f"{', '.join(format_ob_entry(local, ob) for _, ob in obs) or '—'}.\n")
    out.append("\n")
    return "".join(out)


def main() -> None:
    local = Blob("local", load_json_or_jsonish(CONFIG_TXT))
    short = Blob("swf-short", load_json_or_jsonish(SWF_SHORT))
    full = Blob("swf-full", load_json_or_jsonish(SWF_FULL))
    report = build_report(local, short, full)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(report, encoding="utf-8")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
