"""Wonderboat / 1durbow comprehensive stats analysis."""
import json
from collections import Counter, defaultdict
from datetime import datetime
import statistics

with open('c:/libraries/prismata-replay-parser/expert_replays.json', 'r') as f:
    replays = json.load(f)

# Find all Wonderboat / 1durbow / 1durb0w games
WB_NAMES = set()
for r in replays:
    for pn in ['P1Name', 'P2Name']:
        name = r.get(pn, '')
        nl = name.lower()
        if nl in ('wonderboat', '1durbow', '1durb0w'):
            WB_NAMES.add(name)

print(f"Account names found: {WB_NAMES}")

games = []
for r in replays:
    is_p1 = r.get('P1Name', '') in WB_NAMES
    is_p2 = r.get('P2Name', '') in WB_NAMES
    if not (is_p1 or is_p2):
        continue

    wb_name = r.get('P1Name', '') if is_p1 else r.get('P2Name', '')
    wb_rating = r.get('P1RatingIni', 0) if is_p1 else r.get('P2RatingIni', 0)
    opp_rating = r.get('P2RatingIni', 0) if is_p1 else r.get('P1RatingIni', 0)
    opp_name = r.get('P2Name', '') if is_p1 else r.get('P1Name', '')

    result = r.get('Result', -1)
    if result == 0:
        wb_won = is_p1
    elif result == 1:
        wb_won = is_p2
    else:
        wb_won = None

    wb_position = 1 if is_p1 else 2
    start_ts = r.get('StartTime', 0)
    end_ts = r.get('EndTime', 0)
    duration_sec = end_ts - start_ts if end_ts > start_ts else 0

    games.append({
        'code': r.get('Code', ''),
        'account': wb_name,
        'wb_rating': wb_rating,
        'opp_rating': opp_rating,
        'opp_name': opp_name,
        'wb_won': wb_won,
        'wb_position': wb_position,
        'deck': r.get('Deck', []) or [],
        'start_time': start_ts,
        'duration': duration_sec,
        'end_condition': r.get('EndCondition', -1),
        'time_condition': r.get('TimeCondition', 0),
        'rating_change': r.get('P1RatingChange', 0) if is_p1 else r.get('P2RatingChange', 0),
    })

print(f'\n=== WONDERBOAT COMPREHENSIVE STATS ===')
print(f'Total Rated Games: {len(games)}')

# Per-account breakdown
acct_counts = Counter(g['account'] for g in games)
for acct, count in acct_counts.most_common():
    print(f'  {acct}: {count} games')

# Date range
dates = [datetime.fromtimestamp(g['start_time']) for g in games if g['start_time'] > 0]
if dates:
    print(f'Date Range: {min(dates).strftime("%Y-%m-%d")} to {max(dates).strftime("%Y-%m-%d")}')
    months = Counter()
    for d in dates:
        months[d.strftime('%Y-%m')] += 1
    print(f'Active Months: {len(months)}')
    peak_month = months.most_common(1)[0]
    print(f'Peak Month: {peak_month[0]} ({peak_month[1]} games)')

    years = Counter()
    for d in dates:
        years[d.year] += 1
    for y in sorted(years):
        print(f'  {y}: {years[y]} games')

# Rating (combined across accounts)
ratings = [g['wb_rating'] for g in games if g['wb_rating'] > 0]
if ratings:
    print(f'\n--- RATING ---')
    print(f'Peak Rating: {max(ratings):.0f}')
    print(f'Min Rating: {min(ratings):.0f}')
    print(f'Mean Rating: {statistics.mean(ratings):.0f}')
    print(f'Median Rating: {statistics.median(ratings):.0f}')
    recent_ratings = [g['wb_rating'] for g in sorted(games, key=lambda x: x['start_time']) if g['wb_rating'] > 0][-50:]
    print(f'Recent Rating (last 50 games avg): {statistics.mean(recent_ratings):.0f}')

    # Per account peak
    for acct in WB_NAMES:
        acct_r = [g['wb_rating'] for g in games if g['account'] == acct and g['wb_rating'] > 0]
        if acct_r:
            print(f'  {acct} peak: {max(acct_r):.0f}, avg: {statistics.mean(acct_r):.0f}')

# Win/Loss
decided = [g for g in games if g['wb_won'] is not None]
wins = sum(1 for g in decided if g['wb_won'])
losses = len(decided) - wins
draws = len(games) - len(decided)
wr = wins / len(decided) * 100 if decided else 0
print(f'\n--- WIN/LOSS ---')
print(f'Wins: {wins}')
print(f'Losses: {losses}')
print(f'Draws/Unknown: {draws}')
print(f'Win Rate: {wr:.1f}%')

# Filter out bot games for human-only stats
human_games = [g for g in games if g['opp_rating'] > 100]
decided_human = [g for g in human_games if g['wb_won'] is not None]
human_wins = sum(1 for g in decided_human if g['wb_won'])
print(f'Human-only games: {len(human_games)}, WR: {human_wins}/{len(decided_human)} = {human_wins/len(decided_human)*100:.1f}%')

# Win rate by position
p1_games = [g for g in decided if g['wb_position'] == 1]
p2_games = [g for g in decided if g['wb_position'] == 2]
p1_wins = sum(1 for g in p1_games if g['wb_won'])
p2_wins = sum(1 for g in p2_games if g['wb_won'])
if p1_games:
    print(f'\nAs P1 (goes first): {p1_wins}/{len(p1_games)} = {p1_wins/len(p1_games)*100:.1f}%')
if p2_games:
    print(f'As P2 (goes second): {p2_wins}/{len(p2_games)} = {p2_wins/len(p2_games)*100:.1f}%')

# Win rate vs rating tiers
print(f'\n--- WIN RATE BY OPPONENT RATING ---')
tiers = [(0, 1800, 'Under 1800'), (1800, 2000, '1800-1999'), (2000, 2200, '2000-2199'),
         (2200, 2400, '2200-2399'), (2400, 5000, '2400+')]
for lo, hi, label in tiers:
    tier_games = [g for g in decided if lo <= g['opp_rating'] < hi]
    if tier_games:
        tw = sum(1 for g in tier_games if g['wb_won'])
        print(f'  vs {label}: {tw}/{len(tier_games)} = {tw/len(tier_games)*100:.1f}%')

# Top opponents (most played)
print(f'\n--- MOST PLAYED OPPONENTS (Top 15) ---')
opp_counts = Counter(g['opp_name'] for g in games)
for opp, count in opp_counts.most_common(15):
    opp_decided = [g for g in decided if g['opp_name'] == opp]
    opp_wins = sum(1 for g in opp_decided if g['wb_won'])
    wr_str = f'{opp_wins}/{len(opp_decided)} ({opp_wins/len(opp_decided)*100:.0f}%)' if opp_decided else 'N/A'
    opp_rs = [g['opp_rating'] for g in games if g['opp_name'] == opp and g['opp_rating'] > 0]
    avg_opp_r = statistics.mean(opp_rs) if opp_rs else 0
    print(f'  {opp}: {count} games, WR: {wr_str}, avg rating: {avg_opp_r:.0f}')

# Game duration
durations = [g['duration'] for g in games if 30 < g['duration'] < 7200]
if durations:
    print(f'\n--- GAME DURATION ---')
    print(f'Avg Duration: {statistics.mean(durations)/60:.1f} min')
    print(f'Median Duration: {statistics.median(durations)/60:.1f} min')
    print(f'Shortest: {min(durations)/60:.1f} min')
    print(f'Longest: {max(durations)/60:.1f} min')
    quick = sum(1 for d in durations if d < 180)
    medium = sum(1 for d in durations if 180 <= d < 600)
    long_g = sum(1 for d in durations if d >= 600)
    print(f'Quick (<3min): {quick}, Medium (3-10min): {medium}, Long (10+min): {long_g}')

# Unit frequency (excluding base set)
print(f'\n--- BEST WIN RATE UNITS (min 20 games) ---')
unit_counter = Counter()
unit_wins = Counter()
unit_games_ct = Counter()
base_set = {'Drone', 'Engineer', 'Conduit', 'Blastforge', 'Animus', 'Wall', 'Steelsplitter',
            'Tarsier', 'Rhino', 'Forcefield', 'Gauss Cannon'}
for g in games:
    if not g['deck']:
        continue
    for unit in g['deck']:
        unit_counter[unit] += 1
        if g['wb_won'] is not None:
            unit_games_ct[unit] += 1
            if g['wb_won']:
                unit_wins[unit] += 1

unit_wr = {}
for unit in unit_games_ct:
    if unit in base_set:
        continue
    if unit_games_ct[unit] >= 20:
        unit_wr[unit] = (unit_wins[unit] / unit_games_ct[unit] * 100, unit_games_ct[unit])

best_units = sorted(unit_wr.items(), key=lambda x: x[1][0], reverse=True)[:10]
for unit, (wr, n) in best_units:
    print(f'  {unit}: {wr:.1f}% ({n} games)')

print(f'\n--- WORST WIN RATE UNITS (min 20 games) ---')
worst_units = sorted(unit_wr.items(), key=lambda x: x[1][0])[:10]
for unit, (wr, n) in worst_units:
    print(f'  {unit}: {wr:.1f}% ({n} games)')

# Time controls
print(f'\n--- TIME CONTROLS ---')
tc_counter = Counter(g['time_condition'] for g in games)
for tc, count in tc_counter.most_common(10):
    print(f'  TC {tc}s: {count} games ({count/len(games)*100:.1f}%)')

# End condition
print(f'\n--- END CONDITIONS ---')
ec_map = {0: 'Resign', 1: 'Elimination', 2: 'Timeout', 3: 'Draw'}
ec_counter = Counter(g['end_condition'] for g in games)
for ec, count in ec_counter.most_common():
    label = ec_map.get(ec, f'Unknown({ec})')
    print(f'  {label}: {count} ({count/len(games)*100:.1f}%)')

resign_games = [g for g in decided if g['end_condition'] == 0]
wb_resigned = sum(1 for g in resign_games if not g['wb_won'])
opp_resigned = sum(1 for g in resign_games if g['wb_won'])
print(f'  WB Resigned: {wb_resigned}, Opponent Resigned: {opp_resigned}')

elim_games = [g for g in decided if g['end_condition'] == 1]
wb_eliminated = sum(1 for g in elim_games if not g['wb_won'])
opp_eliminated = sum(1 for g in elim_games if g['wb_won'])
print(f'  WB Eliminated opp: {opp_eliminated}, Got Eliminated: {wb_eliminated}')

# Rating trajectory
print(f'\n--- RATING TRAJECTORY ---')
sorted_games = sorted(games, key=lambda x: x['start_time'])
first_100_r = [g['wb_rating'] for g in sorted_games[:100] if g['wb_rating'] > 0]
last_100_r = [g['wb_rating'] for g in sorted_games[-100:] if g['wb_rating'] > 0]
if first_100_r and last_100_r:
    print(f'Avg Rating (first 100 games): {statistics.mean(first_100_r):.0f}')
    print(f'Avg Rating (last 100 games): {statistics.mean(last_100_r):.0f}')
    print(f'Rating Change: {statistics.mean(last_100_r) - statistics.mean(first_100_r):+.0f}')

# Quarterly
print(f'\nQuarterly Ratings:')
quarterly = defaultdict(list)
for g in sorted_games:
    if g['wb_rating'] > 0 and g['start_time'] > 0:
        d = datetime.fromtimestamp(g['start_time'])
        q = f'{d.year}-Q{(d.month-1)//3+1}'
        quarterly[q].append(g['wb_rating'])
for q in sorted(quarterly.keys()):
    rs = quarterly[q]
    print(f'  {q}: avg {statistics.mean(rs):.0f}, peak {max(rs):.0f}, games {len(rs)}')

# Streaks
print(f'\n--- STREAKS ---')
sorted_decided = [g for g in sorted_games if g['wb_won'] is not None]
best_win_streak = 0
best_loss_streak = 0
cur_win = 0
cur_loss = 0
for g in sorted_decided:
    if g['wb_won']:
        cur_win += 1
        cur_loss = 0
        best_win_streak = max(best_win_streak, cur_win)
    else:
        cur_loss += 1
        cur_win = 0
        best_loss_streak = max(best_loss_streak, cur_loss)
print(f'Best Win Streak: {best_win_streak}')
print(f'Worst Loss Streak: {best_loss_streak}')

# Biggest upsets
print(f'\n--- BIGGEST UPSET WINS ---')
upset_wins = sorted([g for g in decided if g['wb_won'] and g['opp_rating'] > g['wb_rating']],
                     key=lambda x: x['opp_rating'] - x['wb_rating'], reverse=True)[:5]
for g in upset_wins:
    diff = g['opp_rating'] - g['wb_rating']
    print(f'  vs {g["opp_name"]} ({g["opp_rating"]:.0f}) when rated {g["wb_rating"]:.0f} (+{diff:.0f}) [{g["code"]}]')

print(f'\n--- BIGGEST UPSET LOSSES ---')
upset_losses = sorted([g for g in decided if not g['wb_won'] and g['opp_rating'] < g['wb_rating']],
                       key=lambda x: x['wb_rating'] - x['opp_rating'], reverse=True)[:5]
for g in upset_losses:
    diff = g['wb_rating'] - g['opp_rating']
    print(f'  vs {g["opp_name"]} ({g["opp_rating"]:.0f}) when rated {g["wb_rating"]:.0f} (-{diff:.0f}) [{g["code"]}]')

# Notable scalps
print(f'\n--- NOTABLE SCALPS ---')
big_wins = sorted([g for g in decided if g['wb_won']], key=lambda x: x['opp_rating'], reverse=True)[:5]
for g in big_wins:
    print(f'  Beat {g["opp_name"]} ({g["opp_rating"]:.0f}) [{g["code"]}]')

# Unique opponents
unique_opps = set(g['opp_name'] for g in games)
print(f'\nUnique Opponents: {len(unique_opps)}')
avg_opp = statistics.mean([g['opp_rating'] for g in games if g['opp_rating'] > 0])
print(f'Avg Opponent Rating: {avg_opp:.0f}')

# Time of day
print(f'\n--- TIME OF DAY (UTC) ---')
tod = Counter()
for g in games:
    if g['start_time'] > 0:
        h = datetime.fromtimestamp(g['start_time']).hour
        if 6 <= h < 12: tod['Morning (6-12)'] += 1
        elif 12 <= h < 18: tod['Afternoon (12-18)'] += 1
        elif 18 <= h < 24: tod['Evening (18-24)'] += 1
        else: tod['Night (0-6)'] += 1
for period in ['Morning (6-12)', 'Afternoon (12-18)', 'Evening (18-24)', 'Night (0-6)']:
    if period in tod:
        print(f'  {period}: {tod[period]} games ({tod[period]/len(games)*100:.1f}%)')

# Day of week
print(f'\n--- DAY OF WEEK ---')
dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
dow = Counter()
for g in games:
    if g['start_time'] > 0:
        d = datetime.fromtimestamp(g['start_time']).weekday()
        dow[dow_names[d]] += 1
for day in dow_names:
    if day in dow:
        print(f'  {day}: {dow[day]} games ({dow[day]/len(games)*100:.1f}%)')

# Win rate by game length
print(f'\n--- WIN RATE BY GAME LENGTH ---')
dur_tiers = [(0, 180, 'Quick (<3m)'), (180, 420, 'Medium (3-7m)'), (420, 720, 'Long (7-12m)'), (720, 99999, 'Marathon (12m+)')]
for lo, hi, label in dur_tiers:
    tier = [g for g in decided if lo < g['duration'] < hi]
    if tier:
        tw = sum(1 for g in tier if g['wb_won'])
        print(f'  {label}: {tw}/{len(tier)} = {tw/len(tier)*100:.1f}%')

# Session analysis
print(f'\n--- ACTIVITY ---')
sessions = []
current_session = [sorted_games[0]]
for g in sorted_games[1:]:
    if g['start_time'] - current_session[-1]['start_time'] > 7200:
        sessions.append(current_session)
        current_session = [g]
    else:
        current_session.append(g)
sessions.append(current_session)
session_lengths = [len(s) for s in sessions]
print(f'Total Sessions: {len(sessions)}')
print(f'Avg Games/Session: {statistics.mean(session_lengths):.1f}')
print(f'Longest Session: {max(session_lengths)} games')
longest_session = max(sessions, key=len)
if longest_session[0]['start_time'] > 0:
    dur_hrs = (longest_session[-1]['start_time'] - longest_session[0]['start_time'] + longest_session[-1].get('duration', 0)) / 3600
    d = datetime.fromtimestamp(longest_session[0]['start_time'])
    print(f'  Date: {d.strftime("%Y-%m-%d")}, Duration: ~{dur_hrs:.1f} hours')

games_per_day = defaultdict(int)
for g in games:
    if g['start_time'] > 0:
        d = datetime.fromtimestamp(g['start_time']).strftime('%Y-%m-%d')
        games_per_day[d] += 1
peak_day = max(games_per_day.items(), key=lambda x: x[1])
active_days = len(games_per_day)
print(f'Most Games in a Day: {peak_day[1]} ({peak_day[0]})')
print(f'Active Days: {active_days}')
print(f'Avg Games/Active Day: {len(games)/active_days:.1f}')

total_play_minutes = sum(g['duration'] for g in games if 30 < g['duration'] < 7200) / 60
print(f'Total Play Time: {total_play_minutes/60:.0f} hours ({total_play_minutes:.0f} minutes)')

# Head-to-head vs notable players
notable = ['Homeless', 'jamberine', 'Kolento', 'coffeeyay', 'Steel', 'Polari', 'Lycomedes',
           'Msven', 'SpiritFryer', 'Arkanishu', 'Elyot', 'Weill', 'chole', 'TheSystem']
print(f'\n--- HEAD-TO-HEAD vs NOTABLE PLAYERS ---')
for name in notable:
    pg = [g for g in decided_human if g['opp_name'] == name]
    if pg:
        pw = sum(1 for g in pg if g['wb_won'])
        print(f'  vs {name}: {pw}-{len(pg)-pw} ({pw/len(pg)*100:.0f}%)')

# Unique units seen
all_units = set()
for g in games:
    if g['deck']:
        all_units.update(g['deck'])
print(f'\nUnique Units Seen: {len(all_units)}')

# Playing up vs down
print(f'\n--- PLAYING UP vs DOWN ---')
up_games = [g for g in decided_human if g['opp_rating'] > g['wb_rating'] + 50]
down_games = [g for g in decided_human if g['opp_rating'] < g['wb_rating'] - 50]
even_games = [g for g in decided_human if abs(g['opp_rating'] - g['wb_rating']) <= 50]
if up_games:
    up_w = sum(1 for g in up_games if g['wb_won'])
    print(f'  Playing UP (opp 50+ higher): {up_w}/{len(up_games)} = {up_w/len(up_games)*100:.1f}%')
if even_games:
    even_w = sum(1 for g in even_games if g['wb_won'])
    print(f'  Even match (within 50): {even_w}/{len(even_games)} = {even_w/len(even_games)*100:.1f}%')
if down_games:
    down_w = sum(1 for g in down_games if g['wb_won'])
    print(f'  Playing DOWN (opp 50+ lower): {down_w}/{len(down_games)} = {down_w/len(down_games)*100:.1f}%')
