"""Build the candidate property_table with the full Phase A+B production/cost vector.

NON-DESTRUCTIVE: writes property_table_candidate.json (does not overwrite the live table).
Attack stays in the existing base_attack (its auto/click conflation is a separate decision).

Phase A (production, split auto vs click - never summed):
  auto_gold auto_green auto_blue auto_red auto_energy       (beginOwnTurnScript.receive)
  click_gold click_green click_blue click_red click_energy  (abilityScript.receive)
  chill_amount                                              (disrupt targetAmount)

Phase B (cost side, to net the click production):
  click_cost_gold click_cost_green click_cost_blue click_cost_red click_cost_energy  (abilityCost)
  click_cost_hp        (HPUsed)
  click_selfsac        (1 if the click sacrifices the unit itself)
  click_sac_units      (# of OTHER units sacrificed per click; abilitySac)
  buy_sac_units        (# of units sacrificed to BUY; buySac - kept distinct from click cost)
  hp_regen             (HPGained per turn; self-regen durability)
"""
import json, re, os

PT_IN  = "training/property_table.json"
LIB    = "bin/asset/config/cardLibrary.jso"
PT_OUT = "docs/scratch/resource_conversions/property_table_candidate.json"

RES = ["gold", "green", "blue", "red", "energy"]
PHASE_A = ([f"auto_{r}" for r in RES] + [f"click_{r}" for r in RES] + ["chill_amount"])
PHASE_B = ([f"click_cost_{r}" for r in RES] +
           ["click_cost_hp", "click_selfsac", "auto_selfsac", "click_sac_units", "buy_sac_units", "hp_regen"])
NEW_COLS = PHASE_A + PHASE_B

lib = json.load(open(LIB))
by_disp = {c.get("UIName", k): c for k, c in lib.items() if isinstance(c, dict)}

def rvec(s):
    o = {}
    if isinstance(s, (int, float)):
        if s: o["gold"] = int(s)
        return o
    if not isinstance(s, str):
        return o
    for n in re.findall(r"\d+", s):
        o["gold"] = o.get("gold", 0) + int(n)
    for ch, r in [("G", "green"), ("B", "blue"), ("C", "red"), ("H", "energy"), ("A", "attack")]:
        if s.count(ch):
            o[r] = s.count(ch)
    return o

def sac_count(lst):
    return sum((e[1] if (len(e) > 1 and isinstance(e[1], int)) else 1) for e in (lst or []))

def vals(c):
    if not isinstance(c, dict):
        return [0] * len(NEW_COLS)
    bt = c.get("beginOwnTurnScript") if isinstance(c.get("beginOwnTurnScript"), dict) else {}
    ab = c.get("abilityScript") if isinstance(c.get("abilityScript"), dict) else {}
    auto = rvec(bt.get("receive", ""))
    click = rvec(ab.get("receive", ""))
    chill = c.get("targetAmount", 0) if c.get("targetAction") == "disrupt" else 0
    cost = rvec(c.get("abilityCost", ""))
    a = [auto.get(r, 0) for r in RES] + [click.get(r, 0) for r in RES] + [chill]
    b = ([cost.get(r, 0) for r in RES] +
         [c.get("HPUsed", 0), 1 if ab.get("selfsac") else 0, 1 if bt.get("selfsac") else 0,
          sac_count(c.get("abilitySac")), sac_count(c.get("buySac")), c.get("HPGained", 0)])
    return a + b

pt = json.load(open(PT_IN))
base_n = len(pt["property_names"])
pt["property_names"] = pt["property_names"] + NEW_COLS
pt["num_properties"] = len(pt["property_names"])

nz = 0
for disp, rec in pt["units"].items():
    v = vals(by_disp.get(disp))
    rec["properties"] = rec["properties"] + v
    if any(v):
        nz += 1

os.makedirs(os.path.dirname(PT_OUT), exist_ok=True)
json.dump(pt, open(PT_OUT, "w"), indent=1)
print(f"num_properties: {base_n} -> {pt['num_properties']}  (+{len(NEW_COLS)}: {len(PHASE_A)} A + {len(PHASE_B)} B)")
print(f"units with any non-zero new column: {nz} / {len(pt['units'])}")
print(f"wrote candidate: {PT_OUT}\n")

# Diff focused on Phase B (cost side) so the new columns can be eyeballed
N = pt["property_names"]
def col(rec, name): return rec["properties"][N.index(name)]
print("=== Phase B cost columns (units with any cost/sac/regen) ===")
print(f"{'unit':18s} {'cost(res)':14s} {'hp':>3s} {'self':>4s} {'sacU':>4s} {'buySac':>6s} {'regen':>5s}")
rows = []
for disp, rec in pt["units"].items():
    costres = " ".join(f"{r[0]}{col(rec,'click_cost_'+r)}" for r in RES if col(rec, "click_cost_" + r))
    hp = col(rec, "click_cost_hp"); self_ = col(rec, "click_selfsac")
    sacu = col(rec, "click_sac_units"); buysac = col(rec, "buy_sac_units"); regen = col(rec, "hp_regen")
    if costres or hp or self_ or sacu or buysac or regen:
        rows.append((disp, costres or "-", hp, self_, sacu, buysac, regen))
for disp, cr, hp, s, su, bs, rg in sorted(rows):
    print(f"{disp:18s} {cr:14s} {hp:3d} {s:4d} {su:4d} {bs:6d} {rg:5d}")
