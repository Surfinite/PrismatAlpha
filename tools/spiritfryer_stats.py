"""SpyrFyr / SpiritFryer comprehensive stats analysis."""
import json
from collections import Counter, defaultdict
from datetime import datetime
import statistics

with open('c:/libraries/prismata-replay-parser/expert_replays.json', 'r') as f:
    replays = json.load(f)

# All SpiritFryer games
games = []
for r in replays:
    is_p1 = r.get('P1Name', '').lower() == 'spiritfryer'
    is_p2 = r.get('P2Name', '').lower() == 'spiritfryer'
    if not (is_p1 or is_p2):
        continue

    sf_rating = r.get('P1RatingIni', 0) if is_p1 else r.get('P2RatingIni', 0)
    opp_rating = r.get('P2RatingIni', 0) if is_p1 else r.get('P1RatingIni', 0)
    opp_name = r.get('P2Name', '') if is_p1 else r.get('P1Name', '')

    # Result: 0 = P1 wins, 1 = P2 wins, 2 = draw
    result = r.get('Result', -1)
    if result == 0:
        sf_won = is_p1
    elif result == 1:
        sf_won = is_p2
    else:
        sf_won = None

    sf_position = 1 if is_p1 else 2

    start_ts = r.get('StartTime', 0)
    end_ts = r.get('EndTime', 0)
    duration_sec = end_ts - start_ts if end_ts > start_ts else 0

    games.append({
        'code': r.get('Code', ''),
        'sf_rating': sf_rating,
        'opp_rating': opp_rating,
        'opp_name': opp_name,
        'sf_won': sf_won,
        'sf_position': sf_position,
        'deck': r.get('Deck', []),
        'start_time': start_ts,
        'duration': duration_sec,
        'end_condition': r.get('EndCondition', -1),
        'time_condition': r.get('TimeCondition', 0),
        'rating_change': r.get('P1RatingChange', 0) if is_p1 else r.get('P2RatingChange', 0),
    })

print(f'=== SPIRITFRYER COMPREHENSIVE STATS ===')
print(f'Total Rated Games: {len(games)}')

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

    # Games per year
    years = Counter()
    for d in dates:
        years[d.year] += 1
    for y in sorted(years):
        print(f'  {y}: {years[y]} games')

# Rating
ratings = [g['sf_rating'] for g in games if g['sf_rating'] > 0]
if ratings:
    print(f'\n--- RATING ---')
    print(f'Peak Rating: {max(ratings):.0f}')
    print(f'Min Rating: {min(ratings):.0f}')
    print(f'Mean Rating: {statistics.mean(ratings):.0f}')
    print(f'Median Rating: {statistics.median(ratings):.0f}')
    recent_ratings = [g['sf_rating'] for g in sorted(games, key=lambda x: x['start_time']) if g['sf_rating'] > 0][-50:]
    print(f'Recent Rating (last 50 games avg): {statistics.mean(recent_ratings):.0f}')

# Win/Loss
decided = [g for g in games if g['sf_won'] is not None]
wins = sum(1 for g in decided if g['sf_won'])
losses = len(decided) - wins
draws = len(games) - len(decided)
wr = wins / len(decided) * 100 if decided else 0
print(f'\n--- WIN/LOSS ---')
print(f'Wins: {wins}')
print(f'Losses: {losses}')
print(f'Draws/Unknown: {draws}')
print(f'Win Rate: {wr:.1f}%')

# Win rate by position
p1_games = [g for g in decided if g['sf_position'] == 1]
p2_games = [g for g in decided if g['sf_position'] == 2]
p1_wins = sum(1 for g in p1_games if g['sf_won'])
p2_wins = sum(1 for g in p2_games if g['sf_won'])
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
        tw = sum(1 for g in tier_games if g['sf_won'])
        print(f'  vs {label}: {tw}/{len(tier_games)} = {tw/len(tier_games)*100:.1f}%')

# Top opponents (most played)
print(f'\n--- MOST PLAYED OPPONENTS (Top 15) ---')
opp_counts = Counter(g['opp_name'] for g in games)
for opp, count in opp_counts.most_common(15):
    opp_decided = [g for g in decided if g['opp_name'] == opp]
    opp_wins = sum(1 for g in opp_decided if g['sf_won'])
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

# Unit frequency in decks (excluding base set)
print(f'\n--- MOST COMMON UNITS IN GAMES (Top 25, excl. base set) ---')
unit_counter = Counter()
unit_wins = Counter()
unit_games = Counter()
for g in games:
    if not g['deck']:
        continue
    for unit in g['deck']:
        unit_counter[unit] += 1
        if g['sf_won'] is not None:
            unit_games[unit] += 1
            if g['sf_won']:
                unit_wins[unit] += 1

base_set = {'Drone', 'Engineer', 'Conduit', 'Blastforge', 'Animus', 'Wall', 'Steelsplitter',
            'Tarsier', 'Rhino', 'Forcefield', 'Gauss Cannon'}
printed = 0
for unit, count in unit_counter.most_common(50):
    if unit in base_set:
        continue
    pct = count / len(games) * 100
    wr = unit_wins[unit] / unit_games[unit] * 100 if unit_games[unit] > 0 else 0
    print(f'  {unit}: {count} games ({pct:.1f}%), WR: {wr:.1f}%')
    printed += 1
    if printed >= 25:
        break

# Best and worst units (min 20 games)
print(f'\n--- BEST WIN RATE UNITS (min 20 games) ---')
unit_wr = {}
for unit in unit_games:
    if unit in base_set:
        continue
    if unit_games[unit] >= 20:
        unit_wr[unit] = (unit_wins[unit] / unit_games[unit] * 100, unit_games[unit])
best_units = sorted(unit_wr.items(), key=lambda x: x[1][0], reverse=True)[:10]
for unit, (wr, n) in best_units:
    print(f'  {unit}: {wr:.1f}% ({n} games)')

print(f'\n--- WORST WIN RATE UNITS (min 20 games) ---')
worst_units = sorted(unit_wr.items(), key=lambda x: x[1][0])[:10]
for unit, (wr, n) in worst_units:
    print(f'  {unit}: {wr:.1f}% ({n} games)')

# Time condition preference
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

# Who resigns more? (SF resign vs opp resign)
resign_games = [g for g in decided if g['end_condition'] == 0]
sf_resigned = sum(1 for g in resign_games if not g['sf_won'])
opp_resigned = sum(1 for g in resign_games if g['sf_won'])
print(f'  SF Resigned: {sf_resigned}, Opponent Resigned: {opp_resigned}')

elim_games = [g for g in decided if g['end_condition'] == 1]
sf_eliminated = sum(1 for g in elim_games if not g['sf_won'])
opp_eliminated = sum(1 for g in elim_games if g['sf_won'])
print(f'  SF Eliminated opp: {opp_eliminated}, Got Eliminated: {sf_eliminated}')

# Rating trajectory
print(f'\n--- RATING TRAJECTORY ---')
sorted_games = sorted(games, key=lambda x: x['start_time'])
first_100_r = [g['sf_rating'] for g in sorted_games[:100] if g['sf_rating'] > 0]
last_100_r = [g['sf_rating'] for g in sorted_games[-100:] if g['sf_rating'] > 0]
if first_100_r and last_100_r:
    print(f'Avg Rating (first 100 games): {statistics.mean(first_100_r):.0f}')
    print(f'Avg Rating (last 100 games): {statistics.mean(last_100_r):.0f}')
    print(f'Rating Change: {statistics.mean(last_100_r) - statistics.mean(first_100_r):+.0f}')

# Rating over time (quarterly)
print(f'\nQuarterly Ratings:')
quarterly = defaultdict(list)
for g in sorted_games:
    if g['sf_rating'] > 0 and g['start_time'] > 0:
        d = datetime.fromtimestamp(g['start_time'])
        q = f'{d.year}-Q{(d.month-1)//3+1}'
        quarterly[q].append(g['sf_rating'])
for q in sorted(quarterly.keys()):
    rs = quarterly[q]
    print(f'  {q}: avg {statistics.mean(rs):.0f}, peak {max(rs):.0f}, games {len(rs)}')

# Streaks
print(f'\n--- STREAKS ---')
sorted_decided = [g for g in sorted_games if g['sf_won'] is not None]
best_win_streak = 0
best_loss_streak = 0
cur_win = 0
cur_loss = 0
for g in sorted_decided:
    if g['sf_won']:
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
print(f'\n--- BIGGEST UPSET WINS (beat much higher rated) ---')
upset_wins = sorted([g for g in decided if g['sf_won'] and g['opp_rating'] > g['sf_rating']],
                     key=lambda x: x['opp_rating'] - x['sf_rating'], reverse=True)[:5]
for g in upset_wins:
    diff = g['opp_rating'] - g['sf_rating']
    print(f'  vs {g["opp_name"]} ({g["opp_rating"]:.0f}) when rated {g["sf_rating"]:.0f} (+{diff:.0f}) [{g["code"]}]')

print(f'\n--- BIGGEST UPSET LOSSES (lost to much lower rated) ---')
upset_losses = sorted([g for g in decided if not g['sf_won'] and g['opp_rating'] < g['sf_rating']],
                       key=lambda x: x['sf_rating'] - x['opp_rating'], reverse=True)[:5]
for g in upset_losses:
    diff = g['sf_rating'] - g['opp_rating']
    print(f'  vs {g["opp_name"]} ({g["opp_rating"]:.0f}) when rated {g["sf_rating"]:.0f} (-{diff:.0f}) [{g["code"]}]')

# Highest rated opponents beaten
print(f'\n--- NOTABLE SCALPS (highest rated beaten) ---')
big_wins = sorted([g for g in decided if g['sf_won']], key=lambda x: x['opp_rating'], reverse=True)[:5]
for g in big_wins:
    print(f'  Beat {g["opp_name"]} ({g["opp_rating"]:.0f}) [{g["code"]}]')

# Unique opponents count
unique_opps = set(g['opp_name'] for g in games)
print(f'\nUnique Opponents: {len(unique_opps)}')

# Average opponent rating
avg_opp = statistics.mean([g['opp_rating'] for g in games if g['opp_rating'] > 0])
print(f'Avg Opponent Rating: {avg_opp:.0f}')

# Deck size distribution
print(f'\n--- DECK SIZE ---')
deck_sizes = Counter(len(g['deck']) for g in games if g['deck'])
for size, count in sorted(deck_sizes.items()):
    print(f'  {size} units: {count} games ({count/len(games)*100:.1f}%)')

# Late night warrior? Time of day analysis
print(f'\n--- TIME OF DAY (UTC) ---')
tod = Counter()
for g in games:
    if g['start_time'] > 0:
        h = datetime.fromtimestamp(g['start_time']).hour
        if 6 <= h < 12:
            tod['Morning (6-12)'] += 1
        elif 12 <= h < 18:
            tod['Afternoon (12-18)'] += 1
        elif 18 <= h < 24:
            tod['Evening (18-24)'] += 1
        else:
            tod['Night (0-6)'] += 1
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
        tw = sum(1 for g in tier if g['sf_won'])
        print(f'  {label}: {tw}/{len(tier)} = {tw/len(tier)*100:.1f}%')

# Number of unique units seen
all_units = set()
for g in games:
    if g['deck']:
        all_units.update(g['deck'])
print(f'\nUnique Units Seen: {len(all_units)}')
print(f'Total Unit Appearances: {sum(unit_counter.values())}')
