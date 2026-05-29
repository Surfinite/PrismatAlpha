"""
Tier-A feature-build check (complements the Tier-B value parity).

Tier-B (compare_parity.py) feeds the C++-extracted tokens into PyTorch and confirms the
forward+weights are faithful GIVEN those tokens -- but it canNOT catch a feature-BUILD bug
(wrong owner / wrong unit_index / a dropped or phantom instance would feed the same garbage
to both sides and still "match").

Tier-A checks, independently of the engine's beginPhase() mutations (which can change
construction/hp/lifespan on load), the invariants that must hold regardless:
  1. name->unit_index mapping: unit_index.json[ui_name] == dump unit_index   (pure lookup)
  2. owner feature: instance[0] == declared owner per instance
  3. instance count + per-owner count == alive (non-dead) table cards in the source gameState
  4. supply unit_index mapping == unit_index.json[ui_name]
  5. no dropped_instances (no live real card mapped to -1)
  6. hp_ratio in [0,1]; current_hp >= 0

Usage:
  python tier_a_check.py <state.json> <dump.json> [<state2.json> <dump2.json> ...]
"""

import json
import sys

UNIT_INDEX = "C:/libraries/PrismataAI-dave-master/bin/asset/config/unit_index.json"


def load_unit_index():
    with open(UNIT_INDEX) as f:
        return json.load(f)["units"]


def check(state_path, dump_path, name2idx):
    with open(state_path) as f:
        gs = json.load(f)
        gs = gs.get("gameState", gs)
    with open(dump_path) as f:
        dump = json.load(f)

    problems = []
    table = gs.get("table", [])
    alive = [c for c in table if not c.get("dead", False)]
    alive_by_owner = {0: 0, 1: 0}
    for c in alive:
        alive_by_owner[c.get("owner", 0)] = alive_by_owner.get(c.get("owner", 0), 0) + 1

    insts = dump["instances"]
    dump_by_owner = {0: 0, 1: 0}

    # 1+2: mapping + owner per instance
    for it in insts:
        ui = it["ui_name"]
        if ui not in name2idx:
            problems.append(f"ui_name '{ui}' not in unit_index.json")
        elif name2idx[ui] != it["unit_index"]:
            problems.append(f"mapping mismatch {ui}: dump={it['unit_index']} index.json={name2idx[ui]}")
        if it["instance"][0] != it["owner"]:
            problems.append(f"owner feature mismatch {ui}: inst[0]={it['instance'][0]} owner={it['owner']}")
        dump_by_owner[it["owner"]] = dump_by_owner.get(it["owner"], 0) + 1
        # 6: hp sanity
        hp, hpr = it["instance"][5], it["instance"][6]
        if hp < 0:
            problems.append(f"{ui}: current_hp<0 ({hp})")
        if not (-1e-6 <= hpr <= 1.0 + 1e-6):
            problems.append(f"{ui}: hp_ratio out of [0,1] ({hpr})")

    # 3: counts (alive table cards == mapped instances + dropped)
    dropped = len(dump.get("dropped_instances", []))
    mapped_total = len(insts)
    if mapped_total + dropped != len(alive):
        problems.append(f"count mismatch: alive_table={len(alive)} mapped={mapped_total} dropped={dropped}")
    for o in (0, 1):
        # dropped instances also carry owner; account for them
        drop_o = sum(1 for d in dump.get("dropped_instances", []) if d.get("owner") == o)
        if dump_by_owner.get(o, 0) + drop_o != alive_by_owner.get(o, 0):
            problems.append(f"owner {o} count: alive={alive_by_owner.get(o,0)} dump={dump_by_owner.get(o,0)}+drop{drop_o}")

    # 4: supply mapping
    for s in dump["supply"]:
        if s["ui_name"] in name2idx and name2idx[s["ui_name"]] != s["unit_index"]:
            problems.append(f"supply mapping mismatch {s['ui_name']}")

    # 5: dropped
    if dropped:
        problems.append(f"{dropped} dropped (unmapped live) instances: {dump['dropped_instances']}")

    return problems, len(alive), mapped_total, dropped


def main():
    args = sys.argv[1:]
    if len(args) < 2 or len(args) % 2 != 0:
        print("usage: python tier_a_check.py <state.json> <dump.json> [...]")
        sys.exit(2)
    name2idx = load_unit_index()
    print(f"{'state':30s} {'alive':>6s} {'mapped':>7s} {'drop':>5s} {'verdict':>8s}")
    print("-" * 62)
    any_fail = False
    for i in range(0, len(args), 2):
        sp, dp = args[i], args[i + 1]
        problems, alive, mapped, dropped = check(sp, dp, name2idx)
        ok = not problems
        if not ok:
            any_fail = True
        import os
        print(f"{os.path.basename(sp):30s} {alive:6d} {mapped:7d} {dropped:5d} {'PASS' if ok else 'FAIL':>8s}")
        for p in problems:
            print(f"    - {p}")
    print("-" * 62)
    print("Tier-A:", "ALL PASS" if not any_fail else "FAIL")
    sys.exit(0 if not any_fail else 1)


if __name__ == "__main__":
    main()
