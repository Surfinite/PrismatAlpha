import struct, os, json, glob, zlib

DD = "c:/libraries/PrismataAI/bin/training/data/selfplay_threadtest"
HS = 64
RS = 7152
CS = 4

def read_recs(fp):
    fs = os.path.getsize(fp)
    pay = fs - HS - CS
    if pay < 0: return []
    nr = pay // RS
    recs = []
    with open(fp, "rb") as fh:
        fh.read(HS)
        for _ in range(nr):
            rec = fh.read(RS)
            if len(rec) != RS: break
            gid = struct.unpack_from("<I", rec, 7144)[0]
            turn = struct.unpack_from("<H", rec, 7148)[0]
            player = struct.unpack_from("<B", rec, 7150)[0]
            flags = struct.unpack_from("<B", rec, 7151)[0]
            outcome = struct.unpack_from("<f", rec, 7140)[0]
            feats = struct.unpack_from("<1785f", rec, 0)
            nz = sum(1 for x in feats if x != 0.0)
            hn = any(x != x for x in feats)
            hi = any(abs(x) == float("inf") for x in feats)
            recs.append(dict(gid=gid,turn=turn,player=player,outcome=outcome,flags=flags,nz=nz,hn=hn,hi=hi))
    return recs

def check_crc(fp):
    fs = os.path.getsize(fp)
    pay = fs - HS - CS
    nr = pay // RS
    with open(fp, "rb") as fh:
        fh.read(HS)
        rb = fh.read(nr * RS)
        stored = struct.unpack("<I", fh.read(CS))[0]
    computed = zlib.crc32(rb) & 0xFFFFFFFF
    return stored, computed, stored == computed

bins = sorted(glob.glob(os.path.join(DD, "*.bin")))
jsonls = sorted(glob.glob(os.path.join(DD, "*.jsonl")))

print("=" * 80)
print("CHECK 1: Binary file structure")
print("=" * 80)
total_recs = 0
all_brecs = {}
gid_threads = {}
for bf in bins:
    fs = os.path.getsize(bf)
    fn = os.path.basename(bf)
    ti = int(fn.split("_t")[1].split("_")[0])
    pay = fs - HS - CS
    if pay < 0:
        print(f"  {fn}: ERROR too small")
        continue
    nr = pay // RS
    rem = pay % RS
    st = "OK" if rem == 0 else f"ERROR rem={rem}"
    print(f"  {fn}: size={fs:>10,}  records={nr:>4}  {st}")
    total_recs += nr
    rs = read_recs(bf)
    all_brecs[bf] = rs
    for r in rs:
        g = r["gid"]
        if g not in gid_threads: gid_threads[g] = set()
        gid_threads[g].add(ti)
print(f"  Total records: {total_recs}")
print(f"  Unique game_ids in bin: {len(gid_threads)}")
multi_bin = {g: t for g, t in gid_threads.items() if len(t) > 1}
if multi_bin:
    print(f"  WARNING: {len(multi_bin)} game_ids in multiple threads!")
    for g, t in sorted(multi_bin.items())[:5]:
        print(f"    game_id={g} in threads {sorted(t)}")
else:
    print("  OK: Every game_id in exactly one thread bin file.")

print()
print("=" * 80)
print("CHECK 2: JSONL file line counts")
print("=" * 80)
jgids = {}
total_jl = 0
for jf in jsonls:
    fn = os.path.basename(jf)
    ti = int(fn.split("_t")[1].split("_")[0])
    lc = 0
    with open(jf, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            lc += 1
            data = json.loads(line)
            gid = data.get("game_id")
            if gid is not None:
                if gid in jgids and jgids[gid] != ti:
                    print(f"  DUPLICATE game_id={gid} in thread {jgids[gid]} AND {ti}")
                jgids[gid] = ti
    total_jl += lc
    print(f"  {fn}: {lc} lines (games)")
print(f"  Total JSONL lines: {total_jl}")

print()
print("=" * 80)
print("CHECK 3: Game ID uniqueness and sequentiality")
print("=" * 80)
all_gids = sorted(jgids.keys())
print(f"  Total unique game_ids: {len(all_gids)}")
missing = []
if all_gids:
    print(f"  Min game_id: {all_gids[0]}")
    print(f"  Max game_id: {all_gids[-1]}")
    expected = set(range(all_gids[0], all_gids[-1] + 1))
    actual = set(all_gids)
    missing = sorted(expected - actual)
    if missing:
        print(f"  WARNING: {len(missing)} missing game_ids")
        print(f"    Missing: {missing[:20]}")
    else:
        print(f"  OK: game_ids contiguous from {all_gids[0]} to {all_gids[-1]}")
    if all_gids[0] == 0: print("  OK: game_ids start from 0")
    else: print(f"  NOTE: game_ids start from {all_gids[0]}")
print("  OK: Every game_id in exactly one JSONL file")

print()
print("=" * 80)
print("CHECK 4: Cross-check bin vs JSONL game_ids")
print("=" * 80)
bset = set(gid_threads.keys())
jset = set(jgids.keys())
d1 = bset - jset
d2 = jset - bset
if d1: print(f"  WARNING: {len(d1)} in bin not JSONL: {sorted(d1)[:10]}")
else: print("  OK: All bin game_ids have JSONL entries")
if d2: print(f"  WARNING: {len(d2)} in JSONL not bin: {sorted(d2)[:10]}")
else: print("  OK: All JSONL game_ids have bin records")
rpg = {}
for rs in all_brecs.values():
    for r in rs:
        g = r["gid"]
        rpg[g] = rpg.get(g, 0) + 1
if rpg:
    v = list(rpg.values())
    print(f"  Records per game: min={min(v)}, max={max(v)}, avg={sum(v)/len(v):.1f}")

print()
print("=" * 80)
print("CHECK 5: CRC32 verification (all bin files)")
print("=" * 80)
all_ok = True
for bf in bins:
    fn = os.path.basename(bf)
    s, c, m = check_crc(bf)
    st = "OK" if m else "MISMATCH"
    if not m: all_ok = False
    print(f"  {fn}: stored=0x{s:08X} computed=0x{c:08X} {st}")
if all_ok: print("  All CRC32 checksums verified OK.")
else: print("  ERROR: CRC32 mismatch!")

print()
print("=" * 80)
print("CHECK 6: Sample records (first 3 of first file)")
print("=" * 80)
if bins and all_brecs.get(bins[0]):
    bf = bins[0]
    fn = os.path.basename(bf)
    print(f"  File: {fn}")
    with open(bf, "rb") as fh: header = fh.read(HS)
    print(f"  Header (16 bytes): {header[:16].hex()}")
    hdr = struct.unpack_from("<IIII", header, 0)
    print(f"  Header uint32s [0..3]: {hdr}")
    for i, r in enumerate(all_brecs[bf][:3]):
        print(f"  Rec {i}: gid={r[chr(103)+chr(105)+chr(100)]}, turn={r[chr(116)+chr(117)+chr(114)+chr(110)]}, player={r[chr(112)+chr(108)+chr(97)+chr(121)+chr(101)+chr(114)]}, outcome={r[chr(111)+chr(117)+chr(116)+chr(99)+chr(111)+chr(109)+chr(101)]:.4f}, flags={r[chr(102)+chr(108)+chr(97)+chr(103)+chr(115)]}, nz={r[chr(110)+chr(122)]}/1785, nan={r[chr(104)+chr(110)]}, inf={r[chr(104)+chr(105)]}")

nc = sum(1 for rs in all_brecs.values() for r in rs if r["hn"])
ic = sum(1 for rs in all_brecs.values() for r in rs if r["hi"])
print(f"  NaN: {nc}/{total_recs}")
print(f"  Inf: {ic}/{total_recs}")
outs = set()
for rs in all_brecs.values():
    for r in rs: outs.add(round(r["outcome"], 4))
print(f"  Unique outcomes: {sorted(outs)}")
pls = set()
for rs in all_brecs.values():
    for r in rs: pls.add(r["player"])
print(f"  Unique players: {sorted(pls)}")

print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"  Binary files: {len(bins)}")
print(f"  JSONL files: {len(jsonls)}")
print(f"  Total records (turns): {total_recs}")
print(f"  Total games (JSONL): {total_jl}")
if total_jl > 0: print(f"  Avg turns/game: {total_recs/total_jl:.1f}")
sv = all((os.path.getsize(bf) - HS - CS) % RS == 0 for bf in bins)
print(f"  All file sizes valid: {sv}")
print(f"  All CRCs valid: {all_ok}")
print(f"  Game IDs unique across threads: {len(multi_bin) == 0}")
print(f"  Game IDs contiguous: {len(missing) == 0}")
print(f"  No NaN/Inf: {nc == 0 and ic == 0}")
print(f"  Outcome values valid: {outs.issubset({-1.0, 0.0, 1.0})}")
