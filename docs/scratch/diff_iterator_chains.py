"""
Three-column structural diff: LiveHardestAI_Root (local config.txt) vs
NewIterator_Root (SWF short blob) vs NewIterator_Root (SWF full blob).

Walks the move-iterator portfolio recursively (following PPPortfolio.include
and ActionAbility_Combination.combination), resolving every reachable partial
to its leaf definition. Normalizes the "Live_" prefix on local names so that
e.g. Live_BuyEconTech compares to BuyEconTech.

Writes a Markdown report to docs/scratch/iterator_diff_report.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_TXT = REPO_ROOT / "bin" / "asset" / "config" / "config.txt"
SWF_SHORT = REPO_ROOT / "tmp_swf_extract" / "93_AI.AIThreadHandler_aiParam_shortTextLoad.bin"
SWF_FULL = REPO_ROOT / "tmp_swf_extract" / "148_AI.AIThreadHandler_aiParamTextLoad.bin"

OUTPUT_MD = REPO_ROOT / "docs" / "scratch" / "iterator_diff_report.md"


# ---------------------------------------------------------------------------
# Loading


def _strip_line_comments(text: str) -> str:
    # config.txt uses // line comments which break strict JSON. There are no
    # // inside string literals in this file (verified by spot-check); a naive
    # regex is sufficient.
    return re.sub(r"//[^\n]*", "", text)


def load_config_txt(path: Path) -> dict:
    return json.loads(_strip_line_comments(path.read_text(encoding="utf-8")))


def load_swf(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Blob abstraction


class Blob:
    def __init__(self, name: str, data: dict, name_prefix_to_strip: str = ""):
        self.name = name
        self.move_iterators: dict = data.get("Move Iterators", {})
        self.partial_players: dict = data.get("Partial Players", {})
        self.opening_books: dict = data.get("Opening Books", {})
        self.filters: dict = data.get("Filters", {})
        self.buy_limits: dict = data.get("Buy Limits", {})
        self.prefix = name_prefix_to_strip

    def norm(self, n: str) -> str:
        if self.prefix and n.startswith(self.prefix):
            return n[len(self.prefix):]
        return n


# ---------------------------------------------------------------------------
# Resolution


def resolve_iterator_slots(blob: Blob, name: str, depth: int = 0) -> list[list[str]]:
    """Return PartialPlayers slots after merging in any `include` parent.

    The PPPortfolio convention is: the included parent's slots set the
    baseline, and the child's own PartialPlayers slots are appended in.
    """
    if depth > 20:
        raise RuntimeError(f"include chain too deep at {name}")
    cfg = blob.move_iterators.get(name)
    if cfg is None:
        return []
    base: list[list[str]] = [[], [], [], []]
    inc = cfg.get("include")
    if inc:
        parent = resolve_iterator_slots(blob, inc, depth + 1)
        for i, slot in enumerate(parent):
            base[i].extend(slot)
    own = cfg.get("PartialPlayers", [[], [], [], []])
    for i, slot in enumerate(own):
        if isinstance(slot, list):
            base[i].extend(slot)
    return base


def resolve_partial_chain(blob: Blob, name: str, depth: int = 0, visited: set | None = None) -> list[str]:
    """Flatten a partial through ActionAbility_Combination to leaf partials."""
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


# ---------------------------------------------------------------------------
# Diff helpers


def normalize_partial_definition(blob: Blob, cfg: dict) -> dict:
    """Return a comparable copy of a partial-player definition.

    Strips the blob's name prefix wherever names appear, so that a local
    Live_BuyOpeningBook entry compares cleanly to a SWF BuyOpeningBook entry.
    """
    out = json.loads(json.dumps(cfg))  # deep copy

    def fix(v):
        if isinstance(v, str):
            return blob.norm(v)
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: fix(val) for k, val in v.items()}
        return v

    result = fix(out)
    assert isinstance(result, dict)
    return result


def deep_diff_json(a, b, path: str = "") -> list[str]:
    """Return a list of human-readable difference strings between two JSON values."""
    diffs: list[str] = []
    if type(a) is not type(b):
        diffs.append(f"  - `{path or '<root>'}` type mismatch: {type(a).__name__} vs {type(b).__name__}")
        return diffs
    if isinstance(a, dict):
        keys = sorted(set(a) | set(b))
        for k in keys:
            sub_path = f"{path}.{k}" if path else k
            if k not in a:
                diffs.append(f"  - `{sub_path}`: missing on LEFT, RIGHT = `{json.dumps(b[k])[:200]}`")
            elif k not in b:
                diffs.append(f"  - `{sub_path}`: missing on RIGHT, LEFT = `{json.dumps(a[k])[:200]}`")
            else:
                diffs.extend(deep_diff_json(a[k], b[k], sub_path))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(f"  - `{path}` length mismatch: {len(a)} vs {len(b)}")
        for i in range(min(len(a), len(b))):
            diffs.extend(deep_diff_json(a[i], b[i], f"{path}[{i}]"))
    else:
        if a != b:
            diffs.append(f"  - `{path}`: LEFT=`{json.dumps(a)}` vs RIGHT=`{json.dumps(b)}`")
    return diffs


# ---------------------------------------------------------------------------
# Report


SLOT_NAMES = ["Defense", "ActionAbility", "ActionBuy", "Breach"]


def build_report(local: Blob, short: Blob, full: Blob,
                 local_root: str, swf_root: str) -> str:
    """Return the full markdown report string."""

    out: list[str] = []
    out.append("# Iterator-chain structural diff\n")
    out.append(f"- Local root: **{local_root}** (from `bin/asset/config/config.txt`)\n")
    out.append(f"- SWF short-blob root: **{swf_root}** (from `tmp_swf_extract/93_*.bin`)\n")
    out.append(f"- SWF full-blob root: **{swf_root}** (from `tmp_swf_extract/148_*.bin`)\n")
    out.append("\nLocal `Live_*` names are normalised to compare against SWF names.\n")
    out.append("Slots are the four PPPortfolio positions: Defense, ActionAbility, ActionBuy, Breach.\n\n")

    # Resolve all three trees.
    local_slots = resolve_iterator_slots(local, local_root)
    short_slots = resolve_iterator_slots(short, swf_root)
    full_slots = resolve_iterator_slots(full, swf_root)

    # ---------------------------------------------------------------- top-level slot comparison
    out.append("## 1. Slot membership (after include resolution)\n")
    for i, label in enumerate(SLOT_NAMES):
        ln = [local.norm(n) for n in local_slots[i]]
        sn = [short.norm(n) for n in short_slots[i]]
        fn = [full.norm(n) for n in full_slots[i]]
        out.append(f"### Slot {i} — {label}\n")
        out.append("| # | Local (normalised) | SWF short | SWF full |\n")
        out.append("|---|---|---|---|\n")
        for j in range(max(len(ln), len(sn), len(fn))):
            l = ln[j] if j < len(ln) else "—"
            s = sn[j] if j < len(sn) else "—"
            f = fn[j] if j < len(fn) else "—"
            mark = "" if (l == s == f) else " ❗"
            out.append(f"| {j} | `{l}` | `{s}` | `{f}` |{mark}\n")
        out.append("\n")

    # ---------------------------------------------------------------- per-branch chain resolution
    out.append("## 2. Per-slot chain resolution (ActionAbility_Combination flattened)\n")
    for i, label in enumerate(SLOT_NAMES):
        out.append(f"### Slot {i} — {label}\n")
        n_branches = max(len(local_slots[i]), len(short_slots[i]), len(full_slots[i]))
        for j in range(n_branches):
            l_name = local_slots[i][j] if j < len(local_slots[i]) else None
            s_name = short_slots[i][j] if j < len(short_slots[i]) else None
            f_name = full_slots[i][j] if j < len(full_slots[i]) else None
            l_chain = [local.norm(x) for x in resolve_partial_chain(local, l_name)] if l_name else []
            s_chain = [short.norm(x) for x in resolve_partial_chain(short, s_name)] if s_name else []
            f_chain = [full.norm(x) for x in resolve_partial_chain(full, f_name)] if f_name else []
            match_marker = "✅" if (l_chain == s_chain == f_chain) else "❗"
            out.append(f"**Branch {j}** {match_marker}  local=`{local.norm(l_name or '')}` | "
                       f"short=`{short.norm(s_name or '')}` | full=`{full.norm(f_name or '')}`\n\n")
            out.append("| # | Local chain | SWF short chain | SWF full chain |\n")
            out.append("|---|---|---|---|\n")
            for k in range(max(len(l_chain), len(s_chain), len(f_chain))):
                lc = l_chain[k] if k < len(l_chain) else "—"
                sc = s_chain[k] if k < len(s_chain) else "—"
                fc = f_chain[k] if k < len(f_chain) else "—"
                mark = "" if (lc == sc == fc) else " ❗"
                out.append(f"| {k} | `{lc}` | `{sc}` | `{fc}` |{mark}\n")
            out.append("\n")

    # ---------------------------------------------------------------- leaf definition diffs
    out.append("## 3. Leaf-partial definition diffs\n")
    out.append("All leaf partials reachable from any branch in any blob. "
               "Definitions are normalised (Live_ prefix stripped) before comparison.\n\n")

    # Collect all reachable leaves
    def collect_leaves(blob: Blob, slots: list[list[str]]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for slot in slots:
            for name in slot:
                for leaf in resolve_partial_chain(blob, name):
                    norm = blob.norm(leaf)
                    if norm not in out:
                        cfg = blob.partial_players.get(leaf)
                        if cfg is not None:
                            out[norm] = normalize_partial_definition(blob, cfg)
            # also include the top-level branch name itself if it's a leaf (atomic, no combination)
            for name in slot:
                cfg = blob.partial_players.get(name)
                if isinstance(cfg, dict) and cfg.get("type") != "ActionAbility_Combination":
                    norm = blob.norm(name)
                    if norm not in out:
                        out[norm] = normalize_partial_definition(blob, cfg)
        return out

    local_leaves = collect_leaves(local, local_slots)
    short_leaves = collect_leaves(short, short_slots)
    full_leaves = collect_leaves(full, full_slots)

    all_leaves = sorted(set(local_leaves) | set(short_leaves) | set(full_leaves))
    perfect: list[str] = []
    mismatched: list[str] = []
    missing: list[str] = []
    for name in all_leaves:
        in_local = name in local_leaves
        in_short = name in short_leaves
        in_full = name in full_leaves
        if not (in_local and in_short and in_full):
            missing.append(name)
        else:
            same = (local_leaves[name] == short_leaves[name] == full_leaves[name])
            (perfect if same else mismatched).append(name)

    out.append(f"- **{len(perfect)} leaves identical across all three sources**\n")
    out.append(f"- **{len(mismatched)} leaves with content diff**\n")
    out.append(f"- **{len(missing)} leaves present in only some sources**\n\n")

    if mismatched:
        out.append("### 3a. Leaves with content diffs (definitions normalised)\n\n")
        for name in mismatched:
            out.append(f"#### `{name}`\n")
            l = local_leaves[name]
            s = short_leaves[name]
            f = full_leaves[name]
            # local vs short
            diff_ls = deep_diff_json(l, s)
            diff_lf = deep_diff_json(l, f)
            diff_sf = deep_diff_json(s, f)
            if diff_ls:
                out.append("Local vs SWF short:\n")
                out.extend(line + "\n" for line in diff_ls)
                out.append("\n")
            if diff_lf and diff_lf != diff_ls:
                out.append("Local vs SWF full:\n")
                out.extend(line + "\n" for line in diff_lf)
                out.append("\n")
            if diff_sf:
                out.append("SWF short vs SWF full:\n")
                out.extend(line + "\n" for line in diff_sf)
                out.append("\n")

    if missing:
        out.append("### 3b. Leaves present in only some sources\n\n")
        out.append("| Leaf | Local | SWF short | SWF full |\n|---|---|---|---|\n")
        for name in missing:
            yn = lambda b: "✅" if b else "—"
            out.append(f"| `{name}` | {yn(name in local_leaves)} | "
                       f"{yn(name in short_leaves)} | {yn(name in full_leaves)} |\n")
        out.append("\n")

    if perfect:
        out.append("### 3c. Leaves identical across all three sources\n\n")
        for name in perfect:
            out.append(f"- `{name}`\n")
        out.append("\n")

    # ---------------------------------------------------------------- supporting tables: Buy Limits, Filters, OBs referenced
    out.append("## 4. Referenced supporting tables (chain-reachable only)\n")
    out.append("Walks the iterator chain in each source and collects every value that lives at "
               "the `buyLimits` / `filter` / `openingBook` key. The lookup uses each source's "
               "ORIGINAL (pre-normalisation) ref name to fetch content — so a local "
               "`Live_Ability_Filter` ref compares against the SWF's `Ability_Filter`, not "
               "against the bare `Ability_Filter` that exists in `config.txt` for the HardIterator "
               "family but is not on this chain.\n\n")

    def collect_chain_refs(blob: Blob, slots: list[list[str]], key: str) -> dict[str, str]:
        """Return {normalised_name: original_name} for refs at `key` reachable from the chain."""
        out_refs: dict[str, str] = {}
        for slot in slots:
            for branch in slot:
                for leaf in resolve_partial_chain(blob, branch):
                    cfg = blob.partial_players.get(leaf)
                    if not isinstance(cfg, dict):
                        continue
                    v = cfg.get(key)
                    if isinstance(v, str):
                        norm = blob.norm(v)
                        out_refs.setdefault(norm, v)
        return out_refs

    def emit_ref_table(label: str, key: str, table_attr: str) -> None:
        out.append(f"### {label}\n")
        l_refs = collect_chain_refs(local, local_slots, key)
        s_refs = collect_chain_refs(short, short_slots, key)
        f_refs = collect_chain_refs(full, full_slots, key)
        all_norm = sorted(set(l_refs) | set(s_refs) | set(f_refs))
        if not all_norm:
            out.append(f"_No `{key}` references in any chain._\n\n")
            return
        out.append("| Normalised name | Local ref (orig) | SWF short ref | SWF full ref | Content match? |\n")
        out.append("|---|---|---|---|---|\n")
        for norm in all_norm:
            l_orig = l_refs.get(norm)
            s_orig = s_refs.get(norm)
            f_orig = f_refs.get(norm)
            l_content = getattr(local, table_attr).get(l_orig) if l_orig else None
            s_content = getattr(short, table_attr).get(s_orig) if s_orig else None
            f_content = getattr(full, table_attr).get(f_orig) if f_orig else None
            match = "n/a"
            present = [c for c in (l_content, s_content, f_content) if c is not None]
            if len(present) == 3:
                same = l_content == s_content == f_content
                match = "✅ same" if same else "❗ DIFFER"
            elif len(present) == 2:
                match = "✅ same (where present)" if all(p == present[0] for p in present) else "❗ DIFFER (where present)"
            l_cell = f"`{l_orig}`" if l_orig else "—"
            s_cell = f"`{s_orig}`" if s_orig else "—"
            f_cell = f"`{f_orig}`" if f_orig else "—"
            out.append(f"| `{norm}` | {l_cell} | {s_cell} | {f_cell} | {match} |\n")
        out.append("\n")

    emit_ref_table("4a. Buy Limits referenced", "buyLimits", "buy_limits")
    emit_ref_table("4b. Filters referenced", "filter", "filters")
    emit_ref_table("4c. Opening Books referenced", "openingBook", "opening_books")

    return "".join(out)


# ---------------------------------------------------------------------------
# Main


def main() -> None:
    local_data = load_config_txt(CONFIG_TXT)
    short_data = load_swf(SWF_SHORT)
    full_data = load_swf(SWF_FULL)

    local = Blob("local", local_data, name_prefix_to_strip="Live_")
    short = Blob("swf-short", short_data, name_prefix_to_strip="")
    full = Blob("swf-full", full_data, name_prefix_to_strip="")

    report = build_report(local, short, full,
                          local_root="LiveHardestAI_Root",
                          swf_root="NewIterator_Root")
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(report, encoding="utf-8")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
