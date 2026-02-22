"""Generate Excalidraw .excalidraw file for Wonderboat stats — Helvetica, wide spacing."""
import json
import random

FONT = 2  # 1=Virgil(hand-drawn), 2=Helvetica(clean), 3=Cascadia(monospace)
CHAR_W = 0.62

def make_id():
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(random.choice(chars) for _ in range(10))

def seed():
    return random.randint(100000000, 999999999)

def text_el(x, y, text, font_size=20, color="#1e1e1e", text_align="left", width=None):
    if width is None:
        longest = max(len(line) for line in text.split('\n')) if '\n' in text else len(text)
        width = longest * font_size * CHAR_W + 20
    num_lines = text.count('\n') + 1
    height = font_size * 1.35 * num_lines
    return {
        "id": make_id(), "type": "text", "x": x, "y": y,
        "width": width, "height": height, "angle": 0,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": "a0", "roundness": None, "seed": seed(),
        "version": 1, "versionNonce": seed(), "isDeleted": False,
        "boundElements": None, "updated": 1, "link": None, "locked": False,
        "text": text, "fontSize": font_size, "fontFamily": FONT,
        "textAlign": text_align, "verticalAlign": "top",
        "containerId": None, "originalText": text, "autoResize": True,
        "lineHeight": 1.25,
    }

def rect_el(x, y, w, h, bg="transparent", stroke="#1e1e1e", sw=2, roughness=0, rnd=3):
    return {
        "id": make_id(), "type": "rectangle", "x": x, "y": y,
        "width": w, "height": h, "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": sw, "strokeStyle": "solid",
        "roughness": roughness, "opacity": 100, "groupIds": [], "frameId": None,
        "index": "a0", "roundness": {"type": rnd}, "seed": seed(),
        "version": 1, "versionNonce": seed(), "isDeleted": False,
        "boundElements": None, "updated": 1, "link": None, "locked": False,
    }

def ellipse_el(x, y, w, h, bg="transparent", stroke="#1e1e1e", sw=2):
    return {
        "id": make_id(), "type": "ellipse", "x": x, "y": y,
        "width": w, "height": h, "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": sw, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": "a0", "roundness": {"type": 2}, "seed": seed(),
        "version": 1, "versionNonce": seed(), "isDeleted": False,
        "boundElements": None, "updated": 1, "link": None, "locked": False,
    }

def line_el(points, x=0, y=0, color="#1e1e1e", width=2):
    return {
        "id": make_id(), "type": "line", "x": x, "y": y,
        "width": max(p[0] for p in points) - min(p[0] for p in points),
        "height": max(abs(p[1]) for p in points),
        "angle": 0, "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": width, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": "a0", "roundness": {"type": 2}, "seed": seed(),
        "version": 1, "versionNonce": seed(), "isDeleted": False,
        "boundElements": None, "updated": 1, "link": None, "locked": False,
        "points": points, "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": None,
    }

def build_excalidraw(elements):
    return {
        "type": "excalidraw", "version": 2,
        "source": "PrismataAI stats generator",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {}
    }

def section_title(els, x, y, text):
    els.append(text_el(x, y, text, 18, color="#868e96"))

def h_bar_chart(els, x, y, data, bar_h=32, gap=8, max_w=220, label_w=100, show_val=True):
    """Horizontal bar chart. data = [(label, value, max_val, color), ...]"""
    for i, (label, val, mx, color) in enumerate(data):
        cy = y + i * (bar_h + gap)
        els.append(text_el(x, cy + bar_h // 2 - 10, label, 14, color="#495057", width=label_w))
        els.append(rect_el(x + label_w + 10, cy, max_w, bar_h, bg="#f1f3f5", stroke="#f1f3f5", sw=0))
        fill = (val / mx) * max_w if mx > 0 else 0
        els.append(rect_el(x + label_w + 10, cy, fill, bar_h, bg=color, stroke=color, sw=0))
        if show_val:
            txt = f"{val:.1f}%" if isinstance(val, float) else str(val)
            els.append(text_el(x + label_w + 10 + fill + 8, cy + bar_h // 2 - 10, txt, 14, color="#1e1e1e"))
    return y + len(data) * (bar_h + gap)

def v_bar_chart(els, x, y, data, bar_w=50, gap=16, max_h=180):
    """Vertical bar chart. data = [(label, value, max_val, color), ...]"""
    n = len(data)
    chart_w = n * (bar_w + gap) - gap
    els.append(line_el([[0, 0], [chart_w + 20, 0]], x - 10, y + max_h, color="#dee2e6", width=1))
    for i, (label, val, mx, color) in enumerate(data):
        cx = x + i * (bar_w + gap)
        h = (val / mx) * max_h if mx > 0 else 0
        els.append(rect_el(cx, y + max_h - h, bar_w, h, bg=color, stroke=color, sw=0))
        txt = str(val) if isinstance(val, int) else f"{val}"
        els.append(text_el(cx + 2, y + max_h - h - 24, txt, 14, color="#1e1e1e"))
        els.append(text_el(cx - 2, y + max_h + 8, label, 12, color="#868e96"))
    return y + max_h + 40


def generate_dashboard():
    els = []
    W = 1350

    # ── HEADER ──
    els.append(rect_el(0, 0, W, 80, bg="#1b1b2f", stroke="#1b1b2f", sw=0))
    els.append(text_el(30, 18, "WONDERBOAT", 36, color="#ffffff"))
    els.append(text_el(380, 22, "Prismata Stats Profile", 28, color="#748ffc"))
    els.append(text_el(W - 420, 28, "3,321 games  |  Mar 2020 — Feb 2026  |  Still active!", 16, color="#868e96"))

    # ── KEY STAT CARDS ──
    cards = [
        ("3,321",   "GAMES",       "#d0bfff"),
        ("2336",    "PEAK RATING", "#a5d8ff"),
        ("67.4%",   "WIN RATE",    "#b2f2bb"),
        ("637 hrs", "PLAY TIME",   "#ffec99"),
        ("26",      "BEST STREAK", "#ffc9c9"),
        ("163",     "OPPONENTS",   "#e5dbff"),
    ]
    card_w = 185
    card_h = 85
    card_gap = 22
    cx_start = (W - (len(cards) * card_w + (len(cards) - 1) * card_gap)) // 2
    cy = 105
    for i, (val, label, bg) in enumerate(cards):
        x = cx_start + i * (card_w + card_gap)
        els.append(rect_el(x, cy, card_w, card_h, bg=bg, stroke=bg, sw=0))
        els.append(text_el(x + 16, cy + 12, val, 30, color="#1e1e1e"))
        els.append(text_el(x + 16, cy + 55, label, 13, color="#495057"))

    # ════════════════════════════════════════
    # ROW 1: Rating chart + Games per year
    # ════════════════════════════════════════
    row1_y = 230

    # ── RATING OVER TIME (line chart) ──
    section_title(els, 0, row1_y, "RATING OVER TIME")
    ch_x, ch_y = 0, row1_y + 35
    ch_w, ch_h = 780, 240
    els.append(rect_el(ch_x, ch_y, ch_w, ch_h, bg="#fafafa", stroke="#e9ecef", sw=1))

    quarterly = [
        ("2020 Q2", 2177, 2248), ("2020 Q3", 2146, 2238), ("2020 Q4", 2198, 2256),
        ("2021 Q1", 2222, 2294), ("2021 Q2", 2220, 2279), ("2021 Q3", 2248, 2312),
        ("2021 Q4", 2235, 2278), ("2022 Q1", 2262, 2321),
        ("2023 Q2", 2240, 2291), ("2023 Q4", 2174, 2236),
        ("2024 Q2", 2238, 2290), ("2026 Q1", 2258, 2336),
    ]
    y_lo, y_hi = 2100, 2380
    for r in [2150, 2200, 2250, 2300, 2350]:
        yp = ch_y + ch_h - ((r - y_lo) / (y_hi - y_lo)) * ch_h
        els.append(line_el([[0, 0], [ch_w, 0]], ch_x, int(yp), color="#f1f3f5", width=1))
        els.append(text_el(ch_x + ch_w + 12, yp - 9, str(r), 12, color="#adb5bd"))

    pts_avg, pts_peak = [], []
    n = len(quarterly)
    for i, (lbl, avg, peak) in enumerate(quarterly):
        px = 40 + (i / (n - 1)) * (ch_w - 80)
        py_a = ch_h - ((avg - y_lo) / (y_hi - y_lo)) * ch_h
        py_p = ch_h - ((peak - y_lo) / (y_hi - y_lo)) * ch_h
        pts_avg.append([px, py_a])
        pts_peak.append([px, py_p])
        els.append(ellipse_el(ch_x + px - 6, ch_y + py_a - 6, 12, 12, bg="#228be6", stroke="#228be6", sw=0))
        els.append(ellipse_el(ch_x + px - 5, ch_y + py_p - 5, 10, 10, bg="#f03e3e", stroke="#f03e3e", sw=0))
        short_lbl = lbl.replace("20", "'")
        els.append(text_el(ch_x + px - 25, ch_y + ch_h + 10, short_lbl, 11, color="#adb5bd"))

    els.append(line_el(pts_avg, ch_x, ch_y, color="#228be6", width=3))
    els.append(line_el(pts_peak, ch_x, ch_y, color="#f03e3e", width=2))
    els.append(ellipse_el(ch_x + 14, ch_y + 12, 12, 12, bg="#228be6", stroke="#228be6", sw=0))
    els.append(text_el(ch_x + 32, ch_y + 10, "Avg Rating", 13, color="#495057"))
    els.append(ellipse_el(ch_x + 140, ch_y + 12, 12, 12, bg="#f03e3e", stroke="#f03e3e", sw=0))
    els.append(text_el(ch_x + 158, ch_y + 10, "Peak Rating", 13, color="#495057"))

    # ── GAMES PER YEAR (vertical bars) ──
    gpy_x = 880
    section_title(els, gpy_x, row1_y, "GAMES PER YEAR")
    years = [("2020", 1345, "#d0bfff"), ("2021", 1262, "#a5d8ff"), ("2022", 80, "#b2f2bb"),
             ("2023", 262, "#ffec99"), ("2024", 199, "#ffc9c9"), ("2025", 36, "#e5dbff"),
             ("2026", 137, "#748ffc")]
    v_bar_chart(els, gpy_x, row1_y + 55, [(y, v, 1345, c) for y, v, c in years],
                bar_w=48, gap=14, max_h=200)

    # ════════════════════════════════════════
    # ROW 2: WR by game length + WR by opp rating + P1/P2
    # ════════════════════════════════════════
    row2_y = 580

    # ── WIN RATE BY GAME LENGTH ──
    section_title(els, 0, row2_y, "WIN RATE BY GAME LENGTH")
    dur_data = [
        ("< 3 min",  41.2, 80, "#ffc9c9"),
        ("3-7 min",  68.7, 80, "#b2f2bb"),
        ("7-12 min", 70.3, 80, "#69db7c"),
        ("12+ min",  67.3, 80, "#b2f2bb"),
    ]
    h_bar_chart(els, 0, row2_y + 35, dur_data, bar_h=38, gap=12, max_w=220, label_w=90)

    # ── WIN RATE vs OPPONENT RATING ──
    opp_x = 440
    section_title(els, opp_x, row2_y, "WIN RATE vs OPPONENT RATING")
    opp_data = [
        ("< 1800",       61.7, 85, "#b2f2bb"),
        ("1800 - 1999",  78.1, 85, "#69db7c"),
        ("2000 - 2199",  65.5, 85, "#b2f2bb"),
        ("2200 - 2399",  49.9, 85, "#ffec99"),
    ]
    h_bar_chart(els, opp_x, row2_y + 35, opp_data, bar_h=38, gap=12, max_w=220, label_w=120)

    # ── P1 vs P2 ──
    p_x = 940
    section_title(els, p_x, row2_y, "P1 vs P2 WIN RATE")
    py = row2_y + 50
    els.append(ellipse_el(p_x + 10, py, 100, 100, bg="#a5d8ff", stroke="#74b9ff", sw=2))
    els.append(text_el(p_x + 38, py + 25, "P1", 16, color="#495057"))
    els.append(text_el(p_x + 20, py + 50, "65.1%", 20, color="#1e1e1e"))
    els.append(ellipse_el(p_x + 150, py, 100, 100, bg="#228be6", stroke="#1971c2", sw=2))
    els.append(text_el(p_x + 178, py + 25, "P2", 16, color="#ffffff"))
    els.append(text_el(p_x + 160, py + 50, "69.8%", 20, color="#ffffff"))
    els.append(text_el(p_x + 40, py + 115, "P2 advantage: +4.7%", 14, color="#1971c2"))

    # ════════════════════════════════════════
    # ROW 3: Head-to-head bars + Unit WR bars
    # ════════════════════════════════════════
    row3_y = 820

    # ── HEAD-TO-HEAD (bar chart with 50% line) ──
    section_title(els, 0, row3_y, "HEAD-TO-HEAD vs TOP OPPONENTS")
    h2h = [
        ("Homeless",     68, "#69db7c"),
        ("jamberine",    49, "#ffec99"),
        ("TheSystem",    78, "#69db7c"),
        ("Lycomedes",    65, "#b2f2bb"),
        ("Kolento",      55, "#b2f2bb"),
        ("chole",        76, "#69db7c"),
        ("Msven",        45, "#ffc9c9"),
        ("SpiritFryer",  81, "#69db7c"),
        ("Arkanishu",    54, "#b2f2bb"),
        ("Steel",        72, "#69db7c"),
    ]
    h2h_bar_h = 28
    h2h_gap = 8
    h2h_label_w = 120
    h2h_max_w = 200
    h2h_data = [(name, wr, 90, c) for name, wr, c in h2h]
    h_bar_chart(els, 0, row3_y + 35, h2h_data,
                bar_h=h2h_bar_h, gap=h2h_gap, max_w=h2h_max_w, label_w=h2h_label_w)

    # 50% marker line
    marker_x = h2h_label_w + 10 + (50 / 90) * h2h_max_w
    h2h_top = row3_y + 35
    h2h_bot = h2h_top + len(h2h) * (h2h_bar_h + h2h_gap)
    els.append(line_el([[0, 0], [0, h2h_bot - h2h_top]], int(marker_x), h2h_top, color="#c92a2a", width=1))
    els.append(text_el(marker_x - 12, h2h_bot + 4, "50%", 11, color="#c92a2a"))

    # ── BEST & WORST UNITS ──
    unit_x = 500
    section_title(els, unit_x, row3_y, "BEST UNITS (Win Rate)")
    uy = row3_y + 35
    best = [("Tia Thurnax", 76.1), ("Trinity Drone", 75.2), ("Arms Race", 73.7),
            ("Valkyrion", 72.9), ("Xeno Guardian", 72.3)]
    best_data = [(n, v, 85, "#b2f2bb") for n, v in best]
    h_bar_chart(els, unit_x, uy, best_data, bar_h=30, gap=8, max_w=160, label_w=130)

    worst_x = 940
    section_title(els, worst_x, row3_y, "WORST UNITS (Win Rate)")
    worst = [("Iso Kronus", 39.1), ("Ferritin Sac", 43.5), ("Twinbolt Felid", 45.8),
             ("Tatsu Nullifier", 55.3), ("Automaid", 56.8)]
    worst_data = [(n, v, 85, "#ffc9c9") for n, v in worst]
    h_bar_chart(els, worst_x, uy, worst_data, bar_h=30, gap=8, max_w=160, label_w=130)

    # ════════════════════════════════════════
    # ROW 4: Activity charts
    # ════════════════════════════════════════
    row4_y = 1200

    # ── GAMES BY DAY OF WEEK ──
    section_title(els, 0, row4_y, "GAMES BY DAY OF WEEK")
    dow = [("Mon", 448, "#a5d8ff"), ("Tue", 441, "#a5d8ff"), ("Wed", 501, "#a5d8ff"),
           ("Thu", 543, "#228be6"), ("Fri", 391, "#a5d8ff"),
           ("Sat", 539, "#748ffc"), ("Sun", 458, "#a5d8ff")]
    v_bar_chart(els, 15, row4_y + 40, [(d, v, 543, c) for d, v, c in dow],
                bar_w=48, gap=16, max_h=160)

    # ── TIME OF DAY ──
    tod_x = 510
    section_title(els, tod_x, row4_y, "TIME OF DAY (UTC)")
    tod = [("Morning",   578,  "#ffec99"),
           ("Afternoon", 566,  "#ffc078"),
           ("Evening",   1179, "#f06595"),
           ("Night",     998,  "#845ef7")]
    v_bar_chart(els, tod_x + 10, row4_y + 40, [(l, v, 1179, c) for l, v, c in tod],
                bar_w=75, gap=24, max_h=160)

    # ── ACCOUNTS ──
    acct_x = 940
    section_title(els, acct_x, row4_y, "ACCOUNTS")
    ay = row4_y + 40
    # Wonderboat box
    els.append(rect_el(acct_x, ay, 380, 70, bg="#d0bfff", stroke="#d0bfff", sw=0))
    els.append(text_el(acct_x + 16, ay + 10, "Wonderboat", 20, color="#1e1e1e"))
    els.append(text_el(acct_x + 16, ay + 40, "2,745 games  |  Peak 2336", 14, color="#495057"))
    # 1durbow box
    els.append(rect_el(acct_x, ay + 85, 380, 70, bg="#a5d8ff", stroke="#a5d8ff", sw=0))
    els.append(text_el(acct_x + 16, ay + 95, "1durbow", 20, color="#1e1e1e"))
    els.append(text_el(acct_x + 16, ay + 125, "576 games  |  Peak 2291", 14, color="#495057"))
    # Discord
    els.append(rect_el(acct_x, ay + 170, 380, 50, bg="#f1f3f5", stroke="#e9ecef", sw=1))
    els.append(text_el(acct_x + 16, ay + 180, "Discord: _wonderboat  |  34 messages", 14, color="#495057"))

    # ════════════════════════════════════════
    # ROW 5: How games end + Milestones
    # ════════════════════════════════════════
    row5_y = 1490

    # ── HOW GAMES END (stacked bar) ──
    section_title(els, 0, row5_y, "HOW GAMES END")
    ey = row5_y + 35
    total_games = 3321
    segments = [
        ("Resign 97.5%", 3238, "#a5d8ff"),
        ("Elim", 10, "#ffc9c9"),
        ("Other", 73, "#e5dbff"),
    ]
    stacked_w = 550
    sx = 0
    for label, count, color in segments:
        segment_w = max((count / total_games) * stacked_w, 4)
        els.append(rect_el(sx, ey, segment_w, 44, bg=color, stroke=color, sw=0))
        if segment_w > 50:
            els.append(text_el(sx + 10, ey + 11, label, 15, color="#1e1e1e"))
        sx += segment_w

    els.append(text_el(0, ey + 56,
        "Opp resigned: 2,176   |   WB resigned: 1,062   |   Eliminated opp 10x, NEVER been eliminated",
        13, color="#495057"))

    # ── MILESTONES ──
    mile_x = 680
    section_title(els, mile_x, row5_y, "MILESTONES & FUN FACTS")
    milestones = [
        ("Best scalp",      "jamberine @ 2315",   "#b2f2bb"),
        ("Biggest upset",   "+131 vs Msven",      "#a5d8ff"),
        ("Win streak",      "26 games",           "#b2f2bb"),
        ("Peak rating",     "2336 (Feb 2026!)",   "#ffec99"),
        ("Never eliminated","0 in 3,321 games",   "#d0bfff"),
        ("Longest session", "41 games / 6.4 hrs", "#e5dbff"),
    ]
    mx = mile_x
    my = row5_y + 35
    m_w = 200
    m_h = 65
    m_gap_x = 15
    m_gap_y = 12
    for i, (title, detail, bg) in enumerate(milestones):
        col = i % 3
        row = i // 3
        bx = mx + col * (m_w + m_gap_x)
        by = my + row * (m_h + m_gap_y)
        els.append(rect_el(bx, by, m_w, m_h, bg=bg, stroke=bg, sw=0))
        els.append(text_el(bx + 12, by + 10, title, 12, color="#495057"))
        els.append(text_el(bx + 12, by + 32, detail, 17, color="#1e1e1e"))

    # ── FOOTER ──
    footer_y = row5_y + 210
    els.append(line_el([[0, 0], [W, 0]], 0, footer_y, color="#dee2e6", width=1))
    els.append(text_el(0, footer_y + 10,
        "Data: prismata-stats API  |  3,321 rated games (Wonderboat + 1durbow)  |  Mar 2020 — Feb 2026  |  Generated by PrismataAI",
        13, color="#adb5bd"))

    return build_excalidraw(els)


if __name__ == "__main__":
    random.seed(99)
    result = generate_dashboard()
    out_path = "docs/wonderboat_stats.excalidraw"
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Generated {out_path} with {len(result['elements'])} elements")
