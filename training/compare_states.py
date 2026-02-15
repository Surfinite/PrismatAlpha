"""
Compare C++ engine output states with TS replay parser ground truth.

Usage:
    python compare_states.py <cpp_output.jsonl> <validation_input.json>

Reads:
  - C++ validation output (JSONL, one state per line from DoReplayValidation)
  - Validation input (JSON, from convert_replay_for_cpp.py, contains ts_state_before per turn)

Compares resources, unit counts, and supply per turn. Reports mismatches.
"""

import json
import sys
from collections import Counter

# Display name -> internal name mapping
DISPLAY_TO_INTERNAL = {
    "Aegis": "Fragilewall", "Amporilla": "Annihilator", "Animus": "Academy",
    "Apollo": "Flame Assassin", "Arka Sodara": "Roshan", "Asteri Cannon": "Giga Cannon",
    "Auric Impulse": "Bond", "Auride Core": "Hate Reactor", "Barrier": "Sound Barrier",
    "Blastforge": "Brooder", "Blood Pact": "Unholy Barrier", "Bloodrager": "Gnoll",
    "Cauterizer": "Demolition Mech", "Centurion": "Battalion", "Chieftain": "Tank",
    "Chrono Filter": "Electrophore", "Cluster Bolt": "Meteor Shower",
    "Cryo Ray": "Distractorod", "Cynestra": "Marauder",
    "Deadeye Operative": "Nether Warrior", "Doomed Wall": "Doomwall",
    "Electrovore": "Fickle Marine", "Endotherm Kit": "Disruption Kit",
    "Energy Matrix": "Golem", "Feral Warden": "HPMan",
    "Fission Turret": "Deconstructible Tower", "Flame Animus": "Piranha Academy",
    "Forcefield": "Blood Barrier", "Frost Brooder": "Psychosis Cannon",
    "Frostbite": "Screech Blast", "Gauss Cannon": "Minicannon",
    "Gauss Charge": "Flame Kin", "Gauss Fabricator": "Fabricator",
    "Gaussite Symbiote": "Gasplant", "Grenade Mech": "Blade",
    "Grimbotch": "Doomed Infantry", "Hannibull": "Statue",
    "Hellhound": "Grenadier", "Husk": "House", "Iceblade Golem": "Minimarshal",
    "Immolite": "Cowardly Marine", "Infusion Grid": "Hotel",
    "Iso Kronus": "Cyclic Attacker", "Kinetic Driver": "Arsonist",
    "Lucina Spinos": "Angelic", "Mahar Rectifier": "Viletrope",
    "Nivo Charge": "Volatile Blast", "Odin": "Furion",
    "Omega Splitter": "Supertreant", "Ossified Drone": "Neo Overlord",
    "Perforator": "Trickster", "Plasmafier": "BFD", "Plexo Cell": "Uberdefcell",
    "Protoplasm": "Pixieflower", "Redeemer": "Rukh",
    "Resophore": "Butter on Blood", "Rhino": "Elephant",
    "Scorchilla": "Rocket Artillery", "Shadowfang": "Flame Warrior",
    "Shiver Yeti": "Jester", "Shredder": "Panther", "Steelforge": "Conscription",
    "Steelsplitter": "Treant", "Synthesizer": "Factory", "Tarsier": "Tesla Tower",
    "Tatsu Nullifier": "Nightmare Cannon", "The Wincer": "Beam of Wincing",
    "Thermite Core": "Adrenaline Reactor", "Tia Thurnax": "Ephemeron",
    "Trinity Drone": "Machine", "Venge Cannon": "Ion Cannon",
    "Xeno Guardian": "Stone Guardian", "Zemora Voidbringer": "NeoContraption",
}
INTERNAL_TO_DISPLAY = {v: k for k, v in DISPLAY_TO_INTERNAL.items()}

# Units that die at the start of their owner's turn, either via
# beginOwnTurnScript (selfsac:true) or lifespan countdown reaching 0.
# C++ has already run beginTurn() (killing these units), but the TS parser
# doesn't simulate beginOwnTurnScript or lifespan death, so they remain
# alive in TS. Result: C++ has FEWER of these units than TS.
# Tolerate C++ < TS for the active player's units.
BEGIN_TURN_DEATH_UNITS = {
    # Selfsac units (beginOwnTurnScript: {selfsac: true})
    "Auric Impulse",    # Bond
    "Centrifuge",       # Centrifuge
    "Gauss Charge",     # Flame Kin
    "Gas Packet",       # Gas Packet (generated trinket)
    "Antima Comet",     # Antima Comet
    "Photonic Fibroid", # Photonic Fibroid
    # Lifespan units (die when lifespan counter reaches 0 at beginTurn)
    "Thermite Core",    # Adrenaline Reactor, lifespan=5
    "Arcflare",         # Arcflare, lifespan=4
    "Kinetic Driver",   # Arsonist, lifespan=6
    "Basilica",         # Basilica, lifespan=6
    "Fission Turret",   # Deconstructible Tower, lifespan=5
    "Defense Grid",     # Defense Grid, lifespan=7
    "Cryo Cell",        # Distractocell, lifespan=1
    "Doomed Drone",     # Doomed Drone, lifespan=4
    "Grimbotch",        # Doomed Infantry, lifespan=4
    "Doomed Mech",      # Doomed Mech, lifespan=5
    "Doomed Ship",      # Doomed Ship, lifespan=6
    "Doomed Wall",      # Doomwall, lifespan=3
    "Evaporoid",        # Evaporoid, lifespan=3
    "Gauss Fabricator", # Fabricator, lifespan=8
    "Innervi Field",    # Innervi Field, lifespan=3
    "Ionic Welder",     # Ionic Welder, lifespan=8
    "Moment's Peace",   # Moment's Peace, lifespan=1
    "Monk",             # Monk, lifespan=10
    "Oxide Mixer",      # Oxide Mixer, lifespan=4
    "Frost Brooder",    # Psychosis Cannon, lifespan=6
    "Barrier",          # Sound Barrier, lifespan=1
    "Sound Plan",       # Sound Plan, lifespan=1
    "Chieftain",        # Tank, lifespan=3
    "Thunderhead",      # Thunderhead, lifespan=3
    "Transtower",       # Transtower, lifespan=3
    "Plexo Cell",       # Uberdefcell, lifespan=1
    "Nivo Charge",      # Volatile Blast, lifespan=1
    "Forcefield",       # Forcefield, lifespan=5
}


def normalize_name(name):
    """Normalize to display name for consistent comparison."""
    return INTERNAL_TO_DISPLAY.get(name, name)


def parse_mana_string(mana_str):
    """Parse C++ mana string to resource dict."""
    res = {'gold': 0, 'energy': 0, 'blue': 0, 'red': 0, 'green': 0, 'attack': 0}
    i = 0
    gold_str = ""
    while i < len(mana_str) and mana_str[i].isdigit():
        gold_str += mana_str[i]
        i += 1
    if gold_str:
        res['gold'] = int(gold_str)
    char_map = {'H': 'energy', 'B': 'blue', 'C': 'red', 'G': 'green', 'A': 'attack'}
    while i < len(mana_str):
        c = mana_str[i]
        if c in char_map:
            res[char_map[c]] += 1
        i += 1
    return res


def extract_cpp_state(cpp_state_json):
    """Extract comparable fields from C++ toJSONString() output."""
    state = json.loads(cpp_state_json) if isinstance(cpp_state_json, str) else cpp_state_json

    result = {
        'p0_resources': parse_mana_string(state.get('whiteMana', '0')),
        'p1_resources': parse_mana_string(state.get('blackMana', '0')),
        'active_player': state.get('turn', -1),
        'num_turns': state.get('numTurns', -1),
    }

    # Count units per type per player (normalize names to display names)
    p0_units = Counter()
    p1_units = Counter()
    p0_units_detail = []
    p1_units_detail = []

    for card in state.get('table', []):
        name = normalize_name(card.get('cardName', ''))
        owner = card.get('owner', 0)
        # Skip dead cards
        if card.get('deadness', 'alive') != 'alive':
            continue
        detail = {
            'name': name,
            'health': card.get('health', 0),
            'delay': card.get('delay', 0),
            'constructionTime': card.get('constructionTime', 0),
            'lifespan': card.get('lifespan', -1),
            'charge': card.get('charge', 0),
            'blocking': card.get('blocking', False),
        }
        if owner == 0:
            p0_units[name] += 1
            p0_units_detail.append(detail)
        else:
            p1_units[name] += 1
            p1_units_detail.append(detail)

    result['p0_unit_counts'] = dict(p0_units)
    result['p1_unit_counts'] = dict(p1_units)
    result['p0_units_detail'] = p0_units_detail
    result['p1_units_detail'] = p1_units_detail

    # Extract supply from the arrays
    cards = state.get('cards', [])
    white_total = state.get('whiteTotalSupply', [])
    black_total = state.get('blackTotalSupply', [])
    white_spent = state.get('whiteSupplySpent', [])
    black_spent = state.get('blackSupplySpent', [])

    supply = {}
    for i, card_name in enumerate(cards):
        display_name = normalize_name(card_name)
        p0_remaining = (white_total[i] - white_spent[i]) if i < len(white_total) and i < len(white_spent) else 0
        p1_remaining = (black_total[i] - black_spent[i]) if i < len(black_total) and i < len(black_spent) else 0
        supply[display_name] = {'p0': p0_remaining, 'p1': p1_remaining}

    result['supply'] = supply
    return result


def extract_ts_state(ts_state):
    """Extract comparable fields from TS state_before."""
    result = {
        'p0_resources': ts_state.get('p0_resources', {}),
        'p1_resources': ts_state.get('p1_resources', {}),
        'active_player': ts_state.get('active_player', -1),
    }

    # Count units per type per player
    p0_units = Counter()
    p1_units = Counter()
    for unit in ts_state.get('p0_units', []):
        p0_units[unit['name']] += 1
    for unit in ts_state.get('p1_units', []):
        p1_units[unit['name']] += 1

    result['p0_unit_counts'] = dict(p0_units)
    result['p1_unit_counts'] = dict(p1_units)
    result['supply'] = ts_state.get('supply', {})
    return result


def compare_resources(label, cpp_res, ts_res, turn_idx, mismatches, skip_transient=False):
    """Compare resource dicts.

    If skip_transient=True, only compare persistent resources (gold, green).
    Transient resources (energy, blue, red, attack) are cleared at beginTurn()
    and may differ due to state capture timing (C++ captures in Defense phase
    before beginTurn, TS captures after beginTurn in Action phase).
    """
    persistent = ['gold', 'green']
    transient = ['energy', 'blue', 'red', 'attack']
    resources_to_check = persistent if skip_transient else persistent + transient
    for res_type in resources_to_check:
        cpp_val = cpp_res.get(res_type, 0)
        ts_val = ts_res.get(res_type, 0)
        if cpp_val != ts_val:
            mismatches.append({
                'turn': turn_idx,
                'field': f'{label}_{res_type}',
                'cpp': cpp_val,
                'ts': ts_val,
            })


def compare_unit_counts(label, cpp_counts, ts_counts, turn_idx, mismatches,
                        active_player_after=-1):
    """Compare unit count dicts.

    Tolerates beginTurn death timing: units with selfsac or lifespan die at
    beginTurn(). C++ has already run beginTurn() (killing them), but the TS
    parser doesn't simulate this, so they remain alive in TS.
    We tolerate C++ having FEWER of these units than TS for the active player.
    """
    all_types = set(list(cpp_counts.keys()) + list(ts_counts.keys()))
    for unit_type in sorted(all_types):
        cpp_val = cpp_counts.get(unit_type, 0)
        ts_val = ts_counts.get(unit_type, 0)
        if cpp_val != ts_val:
            # Check for selfsac timing: C++ has FEWER because beginTurn()
            # already killed them. TS doesn't simulate beginOwnTurnScript,
            # so the units are still alive in TS.
            if (unit_type in BEGIN_TURN_DEATH_UNITS and cpp_val < ts_val
                    and active_player_after >= 0):
                player_idx = int(label.split('_')[0][1:])  # "p0" -> 0, "p1" -> 1
                if player_idx == active_player_after:
                    continue  # Tolerate: C++ correctly killed selfsac, TS didn't

            mismatches.append({
                'turn': turn_idx,
                'field': f'{label}_{unit_type}',
                'cpp': cpp_val,
                'ts': ts_val,
            })


def compare_supply(cpp_supply, ts_supply, turn_idx, mismatches):
    """Compare supply dicts."""
    all_types = set(list(cpp_supply.keys()) + list(ts_supply.keys()))
    for unit_type in sorted(all_types):
        cpp_entry = cpp_supply.get(unit_type, {'p0': 0, 'p1': 0})
        ts_entry = ts_supply.get(unit_type, {'p0': 0, 'p1': 0})
        for player in ['p0', 'p1']:
            cpp_val = cpp_entry.get(player, 0)
            ts_val = ts_entry.get(player, 0)
            if cpp_val != ts_val:
                mismatches.append({
                    'turn': turn_idx,
                    'field': f'supply_{unit_type}_{player}',
                    'cpp': cpp_val,
                    'ts': ts_val,
                })


def compare_states(cpp_output_path, validation_input_path):
    """Main comparison function."""
    # Read C++ output (multi-line JSONL — toJSONString() uses newlines)
    cpp_states = []
    with open(cpp_output_path, 'r') as f:
        content = f.read()
    # Split on the entry delimiter pattern: each entry starts with {"turn":
    import re
    entries = re.split(r'(?=\{"turn":)', content)
    for entry in entries:
        entry = entry.strip()
        if entry:
            try:
                cpp_states.append(json.loads(entry))
            except json.JSONDecodeError as e:
                print(f"  WARNING: Failed to parse JSONL entry ({len(entry)} chars): {e}")
                print(f"    First 100 chars: {entry[:100]}")
                continue

    # Read validation input (contains TS states)
    with open(validation_input_path, 'r') as f:
        validation = json.load(f)

    turns = validation.get('turns', [])
    replay_code = validation.get('replay_code', 'unknown')

    print(f"=== State Comparison: {replay_code} ===")
    print(f"C++ states: {len(cpp_states)}")
    print(f"TS turns:   {len(turns)}")

    # The C++ output has:
    #   - turn=-1: initial state
    #   - turn=0: state after turn 0's actions (should match turn 1's state_before)
    #   - turn=1: state after turn 1's actions (should match turn 2's state_before)
    #   etc.

    all_mismatches = []
    turns_compared = 0
    turns_matched = 0

    # Phase constants: Action=0, Defense=1, Breach=2, Confirm=3, Swoosh=4
    PHASE_DEFENSE = 1

    for i, cpp_entry in enumerate(cpp_states):
        cpp_turn = cpp_entry.get('turn', -1)

        if cpp_turn == -1:
            # Initial state - compare with turn 0's state_before
            if turns:
                ts_state = extract_ts_state(turns[0]['ts_state_before'])
                cpp_state = extract_cpp_state(cpp_entry['state'])

                mismatches = []
                compare_resources('p0_resources', cpp_state['p0_resources'],
                                  ts_state['p0_resources'], -1, mismatches)
                compare_resources('p1_resources', cpp_state['p1_resources'],
                                  ts_state['p1_resources'], -1, mismatches)
                compare_unit_counts('p0_units', cpp_state['p0_unit_counts'],
                                    ts_state['p0_unit_counts'], -1, mismatches)
                compare_unit_counts('p1_units', cpp_state['p1_unit_counts'],
                                    ts_state['p1_unit_counts'], -1, mismatches)

                all_mismatches.extend(mismatches)
                turns_compared += 1
                if not mismatches:
                    turns_matched += 1
                else:
                    print(f"\n  Turn INITIAL: {len(mismatches)} mismatches:")
                    for m in mismatches:
                        print(f"    {m['field']}: C++={m['cpp']} TS={m['ts']}")
        else:
            # State after turn N's actions should match turn N+1's state_before
            next_turn_idx = cpp_turn + 1
            if next_turn_idx < len(turns):
                ts_state = extract_ts_state(turns[next_turn_idx]['ts_state_before'])
                cpp_state = extract_cpp_state(cpp_entry['state'])

                # Resource timing difference between C++ and TS state captures:
                # - TS state_before = state at start of Action phase (after beginTurn)
                # - C++ state = captured after turn transition, which may be:
                #   * Action phase (phase=0): beginTurn WAS called for the active player
                #   * Defense phase (phase=1): beginTurn was NOT called yet
                #
                # Transient resources (energy, blue, red, attack) are cleared by
                # beginTurn(), so:
                # - Non-active player: ALWAYS has stale transient resources (not yet
                #   cleared — their next beginTurn hasn't run). Skip transient comparison.
                # - Active player in Defense: beginTurn hasn't run yet. Skip transient.
                # - Active player in Action: beginTurn HAS run. Compare normally.
                phase_after = cpp_entry.get('phase_after', 0)
                active_after = cpp_entry.get('active_player_after', -1)
                in_defense = (phase_after == PHASE_DEFENSE)

                mismatches = []
                # P0 resources: skip transient if P0 is non-active, or if in Defense phase
                p0_skip = (active_after != 0) or in_defense
                compare_resources('p0_resources', cpp_state['p0_resources'],
                                  ts_state['p0_resources'], cpp_turn, mismatches,
                                  skip_transient=p0_skip)
                # P1 resources: skip transient if P1 is non-active, or if in Defense phase
                p1_skip = (active_after != 1) or in_defense
                compare_resources('p1_resources', cpp_state['p1_resources'],
                                  ts_state['p1_resources'], cpp_turn, mismatches,
                                  skip_transient=p1_skip)
                compare_unit_counts('p0_units', cpp_state['p0_unit_counts'],
                                    ts_state['p0_unit_counts'], cpp_turn, mismatches,
                                    active_player_after=active_after)
                compare_unit_counts('p1_units', cpp_state['p1_unit_counts'],
                                    ts_state['p1_unit_counts'], cpp_turn, mismatches,
                                    active_player_after=active_after)
                compare_supply(cpp_state.get('supply', {}),
                               ts_state.get('supply', {}), cpp_turn, mismatches)

                all_mismatches.extend(mismatches)
                turns_compared += 1
                if not mismatches:
                    turns_matched += 1
                else:
                    player_name = turns[cpp_turn].get('player_name', f'P{turns[cpp_turn]["active_player"]}')
                    phase_note = " [Defense phase — transient resources skipped]" if in_defense else ""
                    print(f"\n  After turn {cpp_turn} ({player_name}){phase_note}: {len(mismatches)} mismatches:")
                    for m in mismatches[:10]:  # show first 10
                        print(f"    {m['field']}: C++={m['cpp']} TS={m['ts']}")
                    if len(mismatches) > 10:
                        print(f"    ... and {len(mismatches) - 10} more")

    # Summary
    print(f"\n--- Comparison Summary ---")
    print(f"Replay:           {replay_code}")
    print(f"Turns compared:   {turns_compared}")
    print(f"Turns matched:    {turns_matched}")
    print(f"Turns mismatched: {turns_compared - turns_matched}")
    print(f"Total mismatches: {len(all_mismatches)}")

    if all_mismatches:
        # Categorize mismatches
        categories = Counter()
        for m in all_mismatches:
            field = m['field']
            if field.startswith('p0_resources') or field.startswith('p1_resources'):
                categories['Resources'] += 1
            elif field.startswith('p0_units') or field.startswith('p1_units'):
                categories['Unit counts'] += 1
            elif field.startswith('supply'):
                categories['Supply'] += 1
            else:
                categories['Other'] += 1

        print(f"\nMismatch categories:")
        for cat, count in categories.most_common():
            print(f"  {cat}: {count}")

        # First divergence
        first = all_mismatches[0]
        print(f"\nFirst divergence: turn {first['turn']}, {first['field']}")
        print(f"  C++: {first['cpp']}")
        print(f"  TS:  {first['ts']}")
    else:
        print("\nNo mismatches found!")

    print(f"\nNote: When C++ state is in Defense phase (phase=1), transient resources")
    print(f"(energy, blue, red, attack) are skipped because beginTurn() hasn't been")
    print(f"called yet. Only persistent resources (gold, green) are compared.")

    match_rate = (turns_matched / turns_compared * 100) if turns_compared > 0 else 0
    print(f"\nMatch rate: {match_rate:.1f}%")
    print(f"=== End Comparison ===")

    return len(all_mismatches) == 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python compare_states.py <cpp_output.jsonl> <validation_input.json>")
        sys.exit(1)

    success = compare_states(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
