"""Build the complete per-unit ability/production/cost map across all units.

Reads the card library and emits unit_ability_map.md. All unit references are shown by
player-visible (UIName) display name. Resource codes: gold (bare digits), grn=G, blu=B,
red=C, nrg=H, atk=A  (e.g. "15GGG" = gold15 grn3). A bare integer receive means gold.

Columns separate the four distinct quantities so buy-cost is never conflated with click-cost:
  auto/turn       - produced automatically each turn (beginOwnTurnScript.receive)
  click->produces - produced when the activated ability is clicked (abilityScript.receive)
  click->creates  - units created by the click ability
  click cost      - what the click costs (abilityCost res + HPUsed + selfsac + abilitySac)
  buy cost        - what it costs to buy (buyCost res + buySac units)
"""
import json, re, os
from collections import Counter

LIB = "bin/asset/config/cardLibrary.jso"   # run from repo root
OUT = "docs/scratch/resource_conversions/unit_ability_map.md"

lib = json.load(open(LIB))
DISP = {k: (c.get("UIName", k) if isinstance(c, dict) else k) for k, c in lib.items()}
def dn(codename):           # engine codename -> player-visible display name
    return DISP.get(codename, codename)

def rvec(s):
    """Resource vector. Bare digits/int = gold; G grn, B blu, C red, H nrg, A atk."""
    o = {}
    if isinstance(s, (int, float)):
        if s: o["gold"] = int(s)
        return o
    if not isinstance(s, str):
        return o
    for n in re.findall(r"\d+", s):
        o["gold"] = o.get("gold", 0) + int(n)
    for ch, r in [("G", "grn"), ("B", "blu"), ("C", "red"), ("H", "nrg"), ("A", "atk")]:
        if s.count(ch):
            o[r] = s.count(ch)
    return o

def fmt(d):
    return " ".join(f"{k}{v}" for k, v in d.items()) if d else "-"

def units_list(lst):
    """For sac lists: [name] or [name, count]."""
    out = []
    for e in (lst or []):
        name = dn(e[0]); cnt = e[1] if (len(e) > 1 and isinstance(e[1], int)) else 1
        out.append(f"{name}x{cnt}")
    return ",".join(out)

def creates_list(lst):
    """For create lists: [name, owner, count, ...]. Flags creation for the opponent."""
    out = []
    for e in (lst or []):
        name = dn(e[0]); owner = e[1] if len(e) > 1 else "own"; cnt = e[2] if len(e) > 2 else 1
        tag = "" if owner == "own" else "->OPP"
        out.append(f"{name}x{cnt}{tag}")
    return ",".join(out)

rows = []
for k, c in lib.items():
    if not isinstance(c, dict):
        continue
    disp = c.get("UIName", k)
    ab = c.get("abilityScript") if isinstance(c.get("abilityScript"), dict) else {}
    bt = c.get("beginOwnTurnScript") if isinstance(c.get("beginOwnTurnScript"), dict) else {}

    auto = fmt(rvec(bt.get("receive", "")))                 # passive each turn
    click_prod = fmt(rvec(ab.get("receive", "")))           # produced by clicking
    click_creates = creates_list(ab.get("create")) + ("," + creates_list(bt.get("create")) if bt.get("create") else "")
    click_creates = click_creates.strip(",") or "-"

    # CLICK cost (activation)
    cc = []
    ac = rvec(c.get("abilityCost", ""))
    if ac: cc.append(fmt(ac))
    if c.get("HPUsed"): cc.append(f"hp{c['HPUsed']}")
    if ab.get("selfsac"): cc.append("sacSELF")
    if c.get("abilitySac"): cc.append("sac:" + units_list(c["abilitySac"]))
    click_cost = " ".join(cc) or "-"

    # BUY cost
    bc = rvec(c.get("buyCost", ""))
    buy = fmt(bc)
    if c.get("buySac"): buy += " sac:" + units_list(c["buySac"])

    chill = c.get("targetAmount") if c.get("targetAction") == "disrupt" else ""
    destroy = "snipe" if c.get("targetAction") == "snipe" else ("netherfy" if c.get("abilityNetherfy") else "")
    hp = (f"+{c['HPGained']}" + (f"/{c['HPMax']}" if c.get("HPMax") else "")) if c.get("HPGained") else ""
    needs = ",".join(dn(n) for n in c.get("needs", [])) or ""

    cat = "vanilla"
    if click_creates != "-" or (bt.get("create")): cat = "CREATE"
    elif chill: cat = "CHILL"
    elif destroy: cat = "DESTROY"
    elif any(r != "atk" for r in rvec(ab.get("receive", ""))) or any(r != "atk" for r in rvec(bt.get("receive", ""))): cat = "ECON"
    elif "atk" in rvec(ab.get("receive", "")) or "atk" in rvec(bt.get("receive", "")): cat = "attack"

    rows.append(dict(disp=disp, cat=cat, auto=auto, click_prod=click_prod, creates=click_creates,
                     click_cost=click_cost, chill=str(chill), destroy=destroy, hp=hp, buy=buy,
                     chg=c.get("charge", ""), life=c.get("lifespan", ""), needs=needs))

order = {"CREATE": 0, "CHILL": 1, "DESTROY": 2, "ECON": 3, "attack": 4, "vanilla": 5}
rows.sort(key=lambda r: (order[r["cat"]], r["disp"]))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write("# Per-unit ability / production / cost map\n\n")
    f.write("All names are player-visible (UIName). Resource codes: gold (bare digits) / grn / blu / "
            "red / nrg / atk. A bare-integer `receive` = gold. Buy-cost and click-cost are separate columns.\n\n")
    f.write("| unit | cat | auto/turn | click->produces | click->creates | click cost | chill | destroy | hp regen | buy cost | chg | life | needs |\n")
    f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in rows:
        f.write(f"| {r['disp']} | {r['cat']} | {r['auto']} | {r['click_prod']} | {r['creates']} | "
                f"{r['click_cost']} | {r['chill']} | {r['destroy']} | {r['hp']} | {r['buy']} | {r['chg']} | {r['life']} | {r['needs']} |\n")

print("category counts:", dict(Counter(r["cat"] for r in rows)))
print("wrote", OUT, "(", len(rows), "units )")
print()
print("=== spot-check the previously-wrong units ===")
for want in ["Militia", "Manticore", "Auride Core", "Savior", "Odin", "The Wincer", "Deadeye Operative"]:
    for r in rows:
        if r["disp"] == want:
            print(f"  {r['disp']:18s} auto={r['auto']:6s} clickProd={r['click_prod']:8s} creates={r['creates']:14s} "
                  f"clickCost={r['click_cost']:16s} buy={r['buy']}")
            break
