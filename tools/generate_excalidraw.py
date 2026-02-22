"""Generate Excalidraw .excalidraw files for SpiritFryer stats — v3: Helvetica, wider spacing."""
import json
import random

FONT = 2  # 1=Virgil(hand-drawn), 2=Helvetica(clean), 3=Cascadia(monospace)
# Helvetica renders wider in Excalidraw than the char count suggests.
# Use generous width multiplier to prevent clipping.
CHAR_W = 0.62

def make_id():
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(random.choice(chars) for _ in range(10))

def seed():
    return random.randint(100000000, 999999999)

def text_el(x, y, text, font_size=20, color="#1e1e1e", text_align="left", width=None):
    if width is None:
        # Account for multi-line: use longest line
        longest = max(len(line) for line in text.split('\n')) if '\n' in text else len(text)
        width = longest * font_size * CHAR_W + 20  # +20 padding to prevent clip
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

# ── Helpers ──────────────────────────────────────────────

def section_title(els, x, y, text):
    els.append(text_el(x, y, text, 18, color="#868e96"))

def h_bar_chart(els, x, y, data, bar_h=32, gap=8, max_w=220, label_w=100, show_val=True):
    """Horizontal bar chart. data = [(label, value, max_val, color), ...]"""
    for i, (label, val, mx, color) in enumerate(data):
        cy = y + i * (bar_h + gap)
        els.append(text_el(x, cy + bar_h // 2 - 10, label, 14, color="#495057", width=label_w))
        # bg track
        els.append(rect_el(x + label_w + 10, cy, max_w, bar_h, bg="#f1f3f5", stroke="#f1f3f5", sw=0))
        # fill
        fill = (val / mx) * max_w if mx > 0 else 0
        els.append(rect_el(x + label_w + 10, cy, fill, bar_h, bg=color, stroke=color, sw=0))
        if show_val:
            txt = f"{val}%" if isinstance(val, float) else str(val)
            els.append(text_el(x + label_w + 10 + fill + 8, cy + bar_h // 2 - 10, txt, 14, color="#1e1e1e"))
    return y + len(data) * (bar_h + gap)

def v_bar_chart(els, x, y, data, bar_w=50, gap=16, max_h=180):
    """Vertical bar chart. data = [(label, value, max_val, color), ...]"""
    n = len(data)
    chart_w = n * (bar_w + gap) - gap
    # baseline
    els.append(line_el([[0, 0], [chart_w + 20, 0]], x - 10, y + max_h, color="#dee2e6", width=1))
    for i, (label, val, mx, color) in enumerate(data):
        cx = x + i * (bar_w + gap)
        h = (val / mx) * max_h if mx > 0 else 0
        # bar
        els.append(rect_el(cx, y + max_h - h, bar_w, h, bg=color, stroke=color, sw=0))
        # value on top
        txt = str(val) if isinstance(val, int) else f"{val}"
        els.append(text_el(cx + 2, y + max_h - h - 24, txt, 14, color="#1e1e1e"))
        # label below
        els.append(text_el(cx - 2, y + max_h + 8, label, 12, color="#868e96"))
    return y + max_h + 40


# ════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ════════════════════════════════════════════════════════
def generate_dashboard():
    els = []
    W = 1350  # wider to give everything room

    # ── HEADER ──
    els.append(rect_el(0, 0, W, 80, bg="#1b1b2f", stroke="#1b1b2f", sw=0))
    els.append(text_el(30, 18, "SPIRITFRYER", 36, color="#ffffff"))
    els.append(text_el(400, 22, "Prismata Stats Profile", 28, color="#748ffc"))
    els.append(text_el(W - 380, 28, "2,984 games  |  May 2020 — May 2024", 16, color="#868e96"))

    # ── KEY STAT CARDS ──
    cards = [
        ("2,984",   "GAMES",       "#d0bfff"),
        ("2206",    "PEAK RATING", "#a5d8ff"),
        ("52.5%",   "WIN RATE",    "#b2f2bb"),
        ("469 hrs", "PLAY TIME",   "#ffec99"),
        ("14",      "BEST STREAK", "#ffc9c9"),
        ("156",     "OPPONENTS",   "#e5dbff"),
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
        ("2020 Q2", 2002, 2083), ("2021 Q1", 2045, 2153), ("2021 Q4", 2038, 2140),
        ("2022 Q1", 2055, 2139), ("2023 Q1", 2042, 2155), ("2024 Q1", 2117, 2206),
        ("2024 Q2", 2083, 2175),
    ]
    y_lo, y_hi = 1950, 2250
    # gridlines
    for r in [2000, 2050, 2100, 2150, 2200]:
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
        # dots
        els.append(ellipse_el(ch_x + px - 6, ch_y + py_a - 6, 12, 12, bg="#228be6", stroke="#228be6", sw=0))
        els.append(ellipse_el(ch_x + px - 5, ch_y + py_p - 5, 10, 10, bg="#f03e3e", stroke="#f03e3e", sw=0))
        # x label (single line, abbreviated)
        short_lbl = lbl.replace("20", "'").replace(" ", " ")
        els.append(text_el(ch_x + px - 25, ch_y + ch_h + 10, short_lbl, 12, color="#adb5bd"))

    els.append(line_el(pts_avg, ch_x, ch_y, color="#228be6", width=3))
    els.append(line_el(pts_peak, ch_x, ch_y, color="#f03e3e", width=2))
    # legend
    els.append(ellipse_el(ch_x + 14, ch_y + 12, 12, 12, bg="#228be6", stroke="#228be6", sw=0))
    els.append(text_el(ch_x + 32, ch_y + 10, "Avg Rating", 13, color="#495057"))
    els.append(ellipse_el(ch_x + 140, ch_y + 12, 12, 12, bg="#f03e3e", stroke="#f03e3e", sw=0))
    els.append(text_el(ch_x + 158, ch_y + 10, "Peak Rating", 13, color="#495057"))

    # ── GAMES PER YEAR (vertical bars) ──
    gpy_x = 880
    section_title(els, gpy_x, row1_y, "GAMES PER YEAR")
    years = [("2020", 307, "#d0bfff"), ("2021", 1110, "#a5d8ff"), ("2022", 290, "#b2f2bb"),
             ("2023", 525, "#ffec99"), ("2024", 752, "#ffc9c9")]
    v_bar_chart(els, gpy_x, row1_y + 55, [(y, v, 1110, c) for y, v, c in years],
                bar_w=60, gap=20, max_h=200)

    # ════════════════════════════════════════
    # ROW 2: WR by game length + WR by opp rating + P1/P2
    # ════════════════════════════════════════
    row2_y = 570

    # ── WIN RATE BY GAME LENGTH ──
    section_title(els, 0, row2_y, "WIN RATE BY GAME LENGTH")
    dur_data = [
        ("< 3 min",  39.0, 75, "#ffc9c9"),
        ("3-7 min",  46.7, 75, "#ffec99"),
        ("7-12 min", 56.2, 75, "#b2f2bb"),
        ("12+ min",  58.4, 75, "#69db7c"),
    ]
    h_bar_chart(els, 0, row2_y + 35, dur_data, bar_h=38, gap=12, max_w=220, label_w=90)

    # ── WIN RATE vs OPPONENT RATING ──
    opp_x = 440
    section_title(els, opp_x, row2_y, "WIN RATE vs OPPONENT RATING")
    opp_data = [
        ("< 1800",       72.1, 80, "#69db7c"),
        ("1800 - 1999",  62.9, 80, "#b2f2bb"),
        ("2000 - 2199",  45.9, 80, "#ffec99"),
        ("2200+",        26.7, 80, "#ffc9c9"),
    ]
    h_bar_chart(els, opp_x, row2_y + 35, opp_data, bar_h=38, gap=12, max_w=220, label_w=120)

    # ── P1 vs P2 ──
    p_x = 940
    section_title(els, p_x, row2_y, "P1 vs P2 WIN RATE")
    py = row2_y + 50
    # P1 circle
    els.append(ellipse_el(p_x + 10, py, 100, 100, bg="#a5d8ff", stroke="#74b9ff", sw=2))
    els.append(text_el(p_x + 38, py + 25, "P1", 16, color="#495057"))
    els.append(text_el(p_x + 22, py + 50, "49.9%", 20, color="#1e1e1e"))
    # P2 circle
    els.append(ellipse_el(p_x + 150, py, 100, 100, bg="#228be6", stroke="#1971c2", sw=2))
    els.append(text_el(p_x + 178, py + 25, "P2", 16, color="#ffffff"))
    els.append(text_el(p_x + 162, py + 50, "55.2%", 20, color="#ffffff"))
    # Note
    els.append(text_el(p_x + 40, py + 115, "P2 advantage: +5.3%", 14, color="#1971c2"))

    # ════════════════════════════════════════
    # ROW 3: Head-to-head bars + Unit WR bars
    # ════════════════════════════════════════
    row3_y = 810

    # ── HEAD-TO-HEAD (bar chart with 50% line) ──
    section_title(els, 0, row3_y, "HEAD-TO-HEAD vs TOP OPPONENTS")
    h2h = [
        ("Homeless",      48, "#ffec99"),
        ("jamberine",     26, "#ffc9c9"),
        ("TheSystem",     65, "#69db7c"),
        ("Kolento",       36, "#ffc9c9"),
        ("chole",         45, "#ffec99"),
        ("TheTrumpWall",  56, "#b2f2bb"),
        ("Steel",         42, "#ffec99"),
        ("coffeeyay",     44, "#ffec99"),
        ("Wonderboat",    17, "#ff8787"),
    ]
    h2h_bar_h = 30
    h2h_gap = 8
    h2h_label_w = 130
    h2h_max_w = 200
    h2h_data = [(name, wr, 80, c) for name, wr, c in h2h]
    h_bar_chart(els, 0, row3_y + 35, h2h_data,
                bar_h=h2h_bar_h, gap=h2h_gap, max_w=h2h_max_w, label_w=h2h_label_w)

    # 50% marker line
    marker_x = h2h_label_w + 10 + (50 / 80) * h2h_max_w
    h2h_top = row3_y + 35
    h2h_bot = h2h_top + len(h2h) * (h2h_bar_h + h2h_gap)
    els.append(line_el([[0, 0], [0, h2h_bot - h2h_top]], int(marker_x), h2h_top, color="#c92a2a", width=1))
    els.append(text_el(marker_x - 12, h2h_bot + 4, "50%", 11, color="#c92a2a"))

    # ── BEST & WORST UNITS (side by side bar charts, not mirrored) ──
    unit_x = 500
    section_title(els, unit_x, row3_y, "BEST UNITS (Win Rate)")
    uy = row3_y + 35
    best = [("Automaid", 64.7), ("Grimbotch", 63.2), ("Defense Grid", 59.3),
            ("Tesla Coil", 59.0), ("Oxide Mixer", 58.7)]
    best_data = [(n, v, 70, "#b2f2bb") for n, v in best]
    h_bar_chart(els, unit_x, uy, best_data, bar_h=30, gap=8, max_w=160, label_w=130)

    worst_x = 940
    section_title(els, worst_x, row3_y, "WORST UNITS (Win Rate)")
    worst = [("Arka Sodara", 26.1), ("Resophore", 33.3), ("Centrifuge", 38.7),
             ("Centurion", 39.3), ("Perforator", 42.4)]
    worst_data = [(n, v, 70, "#ffc9c9") for n, v in worst]
    h_bar_chart(els, worst_x, uy, worst_data, bar_h=30, gap=8, max_w=160, label_w=120)

    # ════════════════════════════════════════
    # ROW 4: Activity charts
    # ════════════════════════════════════════
    row4_y = 1160

    # ── GAMES BY DAY OF WEEK ──
    section_title(els, 0, row4_y, "GAMES BY DAY OF WEEK")
    dow = [("Mon", 326, "#a5d8ff"), ("Tue", 415, "#a5d8ff"), ("Wed", 400, "#a5d8ff"),
           ("Thu", 369, "#a5d8ff"), ("Fri", 393, "#a5d8ff"),
           ("Sat", 608, "#228be6"), ("Sun", 473, "#748ffc")]
    v_bar_chart(els, 15, row4_y + 40, [(d, v, 608, c) for d, v, c in dow],
                bar_w=48, gap=16, max_h=160)

    # ── TIME OF DAY ──
    tod_x = 510
    section_title(els, tod_x, row4_y, "TIME OF DAY (UTC)")
    tod = [("Morning",   207,  "#ffec99"),
           ("Afternoon", 841,  "#ffc078"),
           ("Evening",   1568, "#f06595"),
           ("Night",     368,  "#845ef7")]
    v_bar_chart(els, tod_x + 10, row4_y + 40, [(l, v, 1568, c) for l, v, c in tod],
                bar_w=75, gap=24, max_h=160)

    # ── DISCORD MESSAGES ──
    disc_x = 940
    section_title(els, disc_x, row4_y, "DISCORD MESSAGES")
    channels = [
        ("prismata_chat",   4583, "#7950f2"),
        ("general_chat",    3004, "#845ef7"),
        ("strategy_advice", 1233, "#9775fa"),
        ("unit_design",      887, "#b197fc"),
        ("alpha_lounge",     498, "#d0bfff"),
        ("other (4ch)",      774, "#e5dbff"),
    ]
    ch_data = [(n, v, 4583, c) for n, v, c in channels]
    h_bar_chart(els, disc_x, row4_y + 35, ch_data,
                bar_h=28, gap=8, max_w=160, label_w=140)
    disc_bot = row4_y + 35 + len(channels) * (28 + 8)
    els.append(text_el(disc_x, disc_bot + 8, "10,979 total messages", 15, color="#7950f2"))

    # ════════════════════════════════════════
    # ROW 5: How games end + Milestones
    # ════════════════════════════════════════
    row5_y = 1440

    # ── HOW GAMES END (stacked bar) ──
    section_title(els, 0, row5_y, "HOW GAMES END")
    ey = row5_y + 35
    total_games = 2984
    segments = [
        ("Resign 96%", 2851, "#a5d8ff"),
        ("Elim", 32, "#ffc9c9"),
        ("Other", 101, "#e5dbff"),
    ]
    stacked_w = 550
    sx = 0
    for label, count, color in segments:
        segment_w = max((count / total_games) * stacked_w, 4)
        els.append(rect_el(sx, ey, segment_w, 44, bg=color, stroke=color, sw=0))
        if segment_w > 50:
            els.append(text_el(sx + 10, ey + 11, label, 15, color="#1e1e1e"))
        sx += segment_w

    # Detail line below
    els.append(text_el(0, ey + 56, "Opp resigned: 1,491   |   SF resigned: 1,360   |   Eliminated opp 29x, got eliminated 3x", 13, color="#495057"))

    # ── MILESTONES (larger boxes, 3 columns) ──
    mile_x = 680
    section_title(els, mile_x, row5_y, "MILESTONES")
    milestones = [
        ("Best scalp",    "jamberine @ 2308",  "#b2f2bb"),
        ("Biggest upset", "+324 vs Msven",     "#a5d8ff"),
        ("Loss streak",   "10 games",          "#ffc9c9"),
        ("Peak month",    "Mar 2023: 464 gms", "#ffec99"),
        ("Xmas marathon", "76 games / 8.4 hrs","#d0bfff"),
        ("Win streak",    "14 games",          "#b2f2bb"),
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
    footer_y = row5_y + 200
    els.append(line_el([[0, 0], [W, 0]], 0, footer_y, color="#dee2e6", width=1))
    els.append(text_el(0, footer_y + 10,
        "Data: prismata-stats API  |  2,984 rated games  |  May 2020 — May 2024  |  Generated by PrismataAI",
        13, color="#adb5bd"))

    return build_excalidraw(els)


if __name__ == "__main__":
    random.seed(42)
    result = generate_dashboard()
    out_path = "tools/spiritfryer_stats.excalidraw"
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Generated {out_path} with {len(result['elements'])} elements")
