"""
Convert TS replay state dump to C++ engine validation format.

Usage:
    python convert_replay_for_cpp.py <ts_state_dump.json> [output_file.json]

Reads a TS state dump (from dump_replay_states.js) and converts it to a format
the C++ engine's DoReplayValidation benchmark can consume.

The output file contains:
  - initial_state: C++ GameState JSON format for constructing the starting position
  - turns: per-turn action sequences + expected states for comparison
  - ts_states: raw TS states for Python-side comparison
"""

import json
import sys
import os
from collections import Counter

# Display name -> internal name mapping (from cardLibrary.jso)
# Only entries where UIName differs from internal name
DISPLAY_TO_INTERNAL = {
    "Aegis": "Fragilewall",
    "Amporilla": "Annihilator",
    "Animus": "Academy",
    "Apollo": "Flame Assassin",
    "Arka Sodara": "Roshan",
    "Asteri Cannon": "Giga Cannon",
    "Auric Impulse": "Bond",
    "Auride Core": "Hate Reactor",
    "Barrier": "Sound Barrier",
    "Blastforge": "Brooder",
    "Blood Pact": "Unholy Barrier",
    "Bloodrager": "Gnoll",
    "Cauterizer": "Demolition Mech",
    "Centurion": "Battalion",
    "Chieftain": "Tank",
    "Chrono Filter": "Electrophore",
    "Cluster Bolt": "Meteor Shower",
    "Cryo Ray": "Distractorod",
    "Cynestra": "Marauder",
    "Deadeye Operative": "Nether Warrior",
    "Doomed Wall": "Doomwall",
    "Electrovore": "Fickle Marine",
    "Endotherm Kit": "Disruption Kit",
    "Energy Matrix": "Golem",
    "Feral Warden": "HPMan",
    "Fission Turret": "Deconstructible Tower",
    "Flame Animus": "Piranha Academy",
    "Forcefield": "Blood Barrier",
    "Frost Brooder": "Psychosis Cannon",
    "Frostbite": "Screech Blast",
    "Gauss Cannon": "Minicannon",
    "Gauss Charge": "Flame Kin",
    "Gauss Fabricator": "Fabricator",
    "Gaussite Symbiote": "Gasplant",
    "Grenade Mech": "Blade",
    "Grimbotch": "Doomed Infantry",
    "Hannibull": "Statue",
    "Hellhound": "Grenadier",
    "Husk": "House",
    "Iceblade Golem": "Minimarshal",
    "Immolite": "Cowardly Marine",
    "Infusion Grid": "Hotel",
    "Iso Kronus": "Cyclic Attacker",
    "Kinetic Driver": "Arsonist",
    "Lucina Spinos": "Angelic",
    "Mahar Rectifier": "Viletrope",
    "Nivo Charge": "Volatile Blast",
    "Odin": "Furion",
    "Omega Splitter": "Supertreant",
    "Ossified Drone": "Neo Overlord",
    "Perforator": "Trickster",
    "Plasmafier": "BFD",
    "Plexo Cell": "Uberdefcell",
    "Protoplasm": "Pixieflower",
    "Redeemer": "Rukh",
    "Resophore": "Butter on Blood",
    "Rhino": "Elephant",
    "Scorchilla": "Rocket Artillery",
    "Shadowfang": "Flame Warrior",
    "Shiver Yeti": "Jester",
    "Shredder": "Panther",
    "Steelforge": "Conscription",
    "Steelsplitter": "Treant",
    "Synthesizer": "Factory",
    "Tarsier": "Tesla Tower",
    "Tatsu Nullifier": "Nightmare Cannon",
    "The Wincer": "Beam of Wincing",
    "Thermite Core": "Adrenaline Reactor",
    "Tia Thurnax": "Ephemeron",
    "Trinity Drone": "Machine",
    "Venge Cannon": "Ion Cannon",
    "Xeno Guardian": "Stone Guardian",
    "Zemora Voidbringer": "NeoContraption",
}

# Reverse mapping
INTERNAL_TO_DISPLAY = {v: k for k, v in DISPLAY_TO_INTERNAL.items()}


def display_to_internal(name):
    """Convert display name to internal name. Returns name unchanged if no mapping exists."""
    return DISPLAY_TO_INTERNAL.get(name, name)


def internal_to_display(name):
    """Convert internal name to display name. Returns name unchanged if no mapping exists."""
    return INTERNAL_TO_DISPLAY.get(name, name)


def resources_to_mana_string(res):
    """Convert TS resource dict to C++ mana string format.

    C++ internal encoding (from Resources::GetChar()):
      Index 0 (Gold)   -> digits prefix
      Index 1 (Energy) -> 'H'
      Index 2 (Blue)   -> 'B'
      Index 3 (Red)    -> 'C'  (NOT 'R'!)
      Index 4 (Green)  -> 'G'
      Index 5 (Attack) -> 'A'
    """
    s = ""
    gold = res.get('gold', 0)
    if gold > 0:
        s += str(gold)
    s += 'H' * res.get('energy', 0)
    s += 'B' * res.get('blue', 0)
    s += 'C' * res.get('red', 0)
    s += 'G' * res.get('green', 0)
    s += 'A' * res.get('attack', 0)
    return s if s else "0"


def parse_mana_string(mana_str):
    """Parse C++ mana string back to resource dict.

    Format: optional digit prefix (gold), then characters H/B/C/G/A.
    """
    res = {'gold': 0, 'energy': 0, 'blue': 0, 'red': 0, 'green': 0, 'attack': 0}
    i = 0
    # Parse leading digits as gold
    gold_str = ""
    while i < len(mana_str) and mana_str[i].isdigit():
        gold_str += mana_str[i]
        i += 1
    if gold_str:
        res['gold'] = int(gold_str)
    # Parse character suffix
    char_map = {'H': 'energy', 'B': 'blue', 'C': 'red', 'G': 'green', 'A': 'attack'}
    while i < len(mana_str):
        c = mana_str[i]
        if c in char_map:
            res[char_map[c]] += 1
        i += 1
    return res


def ts_units_to_table(units, player):
    """Convert TS per-instance unit list to C++ table entries.

    Groups identical units by (name, health, delay, lifespan, charge, abilityUsed, blocking, building, frozen)
    to reduce table size via 'amount' field.
    """
    # Group units by their state signature
    groups = Counter()
    unit_props = {}
    for unit in units:
        name = unit['name']
        internal_name = display_to_internal(name)
        # Create a hashable state signature
        sig = (
            internal_name,
            unit.get('toughness', 1),
            unit.get('delay', 0),
            unit.get('lifespan'),  # can be null
            unit.get('charge'),    # can be null
            unit.get('abilityUsed', False),
            unit.get('blocking', False),
            unit.get('building', False),
            unit.get('frozen', False),
        )
        groups[sig] += 1
        unit_props[sig] = unit

    table = []
    for sig, count in groups.items():
        internal_name = sig[0]
        unit = unit_props[sig]
        entry = {
            "cardName": internal_name,
            "color": player,
            "amount": count,
        }
        # Add optional per-instance properties
        hp = unit.get('toughness', 1)
        hp_max = unit.get('toughnessMax', 1)
        if hp != hp_max:
            entry["health"] = hp
        delay = unit.get('delay', 0)
        if delay > 0:
            entry["delay"] = delay
        lifespan = unit.get('lifespan')
        if lifespan is not None and lifespan > 0:
            entry["lifespan"] = lifespan
        charge = unit.get('charge')
        if charge is not None and charge > 0:
            entry["charge"] = charge
        table.append(entry)
    return table


def ts_state_to_cpp_json(ts_state, card_set, active_player, turn_number=0):
    """Convert a TS state_before to C++ GameState JSON format.

    This produces a JSON object that can be loaded by GameState(rapidjson::Value).
    """
    cpp_state = {
        "whiteMana": resources_to_mana_string(ts_state['p0_resources']),
        "blackMana": resources_to_mana_string(ts_state['p1_resources']),
        "phase": "action",
        "turn": active_player,
        "numTurns": turn_number,
        # Use display names for cards array (GetCardType accepts both)
        "cards": list(card_set),
    }

    # Build table from per-instance units
    table = []
    table.extend(ts_units_to_table(ts_state.get('p0_units', []), 0))
    table.extend(ts_units_to_table(ts_state.get('p1_units', []), 1))
    cpp_state["table"] = table

    # Build supply arrays (must match order of cards array)
    supply = ts_state.get('supply', {})
    white_total = []
    black_total = []
    white_spent = []
    black_spent = []

    for card_name in card_set:
        card_supply = supply.get(card_name, {})
        # TS supply gives remaining, but C++ wants total and spent
        # We don't know the original total from TS alone; we'll compute from
        # remaining + number of units of that type on the board
        p0_remaining = card_supply.get('p0', 0)
        p1_remaining = card_supply.get('p1', 0)

        # Count units of this type on the board
        p0_on_board = sum(1 for u in ts_state.get('p0_units', []) if u['name'] == card_name)
        p1_on_board = sum(1 for u in ts_state.get('p1_units', []) if u['name'] == card_name)

        p0_total = p0_remaining + p0_on_board
        p1_total = p1_remaining + p1_on_board

        white_total.append(p0_total)
        black_total.append(p1_total)
        white_spent.append(p0_on_board)
        black_spent.append(p1_on_board)

    cpp_state["whiteTotalSupply"] = white_total
    cpp_state["blackTotalSupply"] = black_total
    cpp_state["whiteSupplySpent"] = white_spent
    cpp_state["blackSupplySpent"] = black_spent

    return cpp_state


def convert_actions(ts_actions, active_player, ts_state_before=None):
    """Convert TS action dict to C++ action sequence.

    TS format: {bought: [...], activated: [...], defended_with: [...],
                breach_targets: [...], snipe_targets: [...]}

    C++ engine phase order within a player's turn:
      Defense (against opponent's previous attack) -> Swoosh -> Action -> Confirm
    So defense comes FIRST, then action phase.

    C++ action sequence order:
    1. ASSIGN_BLOCKER for each defender (Defense phase, if needed)
    2. END_PHASE (end defense -> Swoosh -> beginTurn -> Action)
    3. ASSIGN_FRONTLINE for enemy frontline units (Action phase)
    4. USE_ABILITY for each activated unit (Action phase)
    5. SNIPE/CHILL for targeting abilities (Action phase)
    6. BUY for each bought unit (Action phase)
    7. END_PHASE (end action -> Confirm -> next player)
    8. ASSIGN_BREACH for each breach target (Breach phase, if wipeout)
    9. END_PHASE (end breach phase, if breach happened)
    """
    actions = []

    # Separate frontline kills from actual breach targets (RC#6 fix)
    # Frontline/undefendable units are killed via ASSIGN_FRONTLINE during Action phase,
    # NOT via ASSIGN_BREACH during Breach phase.
    breach_targets = ts_actions.get('breach_targets', [])
    frontline_targets = []
    actual_breach_targets = []

    if ts_state_before and breach_targets:
        # Get opponent's units to check which are frontline
        opponent_key = 'p1_units' if active_player == 0 else 'p0_units'
        opponent_units = ts_state_before.get(opponent_key, [])

        # Build set of frontline unit names (frontline is a type-level property)
        frontline_names = {u['name'] for u in opponent_units if u.get('frontline', False)}

        for target in breach_targets:
            if target in frontline_names:
                frontline_targets.append(target)
            else:
                actual_breach_targets.append(target)
    else:
        actual_breach_targets = breach_targets

    # Defense phase FIRST (defending against opponent's attack from previous turn)
    if ts_actions.get('defended_with', []):
        for unit_name in ts_actions['defended_with']:
            actions.append({
                "type": "ASSIGN_BLOCKER",
                "card_name": unit_name,
            })
        actions.append({"type": "END_PHASE"})

    # Action phase: frontline kills first, then abilities, snipe/chill, then buys
    for unit_name in frontline_targets:
        actions.append({
            "type": "ASSIGN_FRONTLINE",
            "card_name": unit_name,
        })

    for unit_name in ts_actions.get('activated', []):
        actions.append({
            "type": "USE_ABILITY",
            "card_name": unit_name,
        })

    for unit_name in ts_actions.get('snipe_targets', []):
        actions.append({
            "type": "SNIPE",
            "card_name": unit_name,
        })

    for unit_name in ts_actions.get('bought', []):
        actions.append({
            "type": "BUY",
            "card_name": unit_name,
        })

    # End action phase
    actions.append({"type": "END_PHASE"})

    # Breach phase (non-frontline breach targets only)
    if actual_breach_targets:
        for unit_name in actual_breach_targets:
            actions.append({
                "type": "ASSIGN_BREACH",
                "card_name": unit_name,
            })
        actions.append({"type": "END_PHASE"})

    return actions


def convert_replay(ts_dump_path, output_path=None):
    """Convert a TS state dump to C++ validation format."""
    with open(ts_dump_path, 'r') as f:
        ts_dump = json.load(f)

    card_set = ts_dump['card_set']
    turns = ts_dump['turns']

    if not turns:
        print("ERROR: No turns in state dump")
        return None

    # Build initial state from first turn's state_before
    first_turn = turns[0]
    initial_state = ts_state_to_cpp_json(
        first_turn['state_before'],
        card_set,
        first_turn['active_player'],
        turn_number=0
    )

    # Build per-turn data
    output_turns = []
    for i, turn in enumerate(turns):
        turn_data = {
            "turn_index": i,
            "active_player": turn['active_player'],
            "player_name": turn.get('player_name', ''),
            "is_bot": turn.get('is_bot', False),
            "actions": convert_actions(turn['actions'], turn['active_player'],
                                       turn.get('state_before')),
        }

        # Expected state = next turn's state_before (if available)
        if i + 1 < len(turns):
            next_turn = turns[i + 1]
            turn_data["expected_state"] = ts_state_to_cpp_json(
                next_turn['state_before'],
                card_set,
                next_turn['active_player'],
                turn_number=i + 1
            )

        # Also include raw TS state for Python-side comparison
        turn_data["ts_state_before"] = turn['state_before']
        turn_data["ts_actions"] = turn['actions']

        output_turns.append(turn_data)

    output = {
        "replay_code": ts_dump.get('replay_code', ''),
        "format": ts_dump.get('format', 0),
        "players": ts_dump.get('players', []),
        "card_set": card_set,
        "dominion_set": ts_dump.get('dominion_set', []),
        "total_turns": ts_dump.get('total_turns', len(turns)),
        "initial_state": initial_state,
        "turns": output_turns,
        "name_mapping": DISPLAY_TO_INTERNAL,
    }

    if output_path is None:
        base = os.path.splitext(os.path.basename(ts_dump_path))[0]
        output_path = os.path.join(os.path.dirname(ts_dump_path), f"{base}_cpp.json")

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"Converted {len(turns)} turns from {ts_dump.get('replay_code', '?')}")
    print(f"Card set: {len(card_set)} cards ({len(ts_dump.get('dominion_set', []))} dominion)")
    print(f"Output: {output_path}")
    print(f"Initial state mana: P0={initial_state['whiteMana']} P1={initial_state['blackMana']}")

    # Validate the conversion
    validate_conversion(output)

    return output


def validate_conversion(output):
    """Run basic sanity checks on the converted output."""
    errors = 0

    # Check initial state has cards
    initial = output['initial_state']
    if not initial.get('cards'):
        print("  ERROR: initial_state has no cards")
        errors += 1

    if not initial.get('table'):
        print("  ERROR: initial_state has no table entries")
        errors += 1

    # Check supply arrays match cards array length
    n_cards = len(initial.get('cards', []))
    for arr_name in ['whiteTotalSupply', 'blackTotalSupply', 'whiteSupplySpent', 'blackSupplySpent']:
        arr = initial.get(arr_name, [])
        if len(arr) != n_cards:
            print(f"  ERROR: {arr_name} has {len(arr)} entries, expected {n_cards}")
            errors += 1

    # Check each turn has actions
    for i, turn in enumerate(output['turns']):
        if not turn.get('actions'):
            print(f"  WARNING: turn {i} has no actions")

    # Check name mapping round-trip
    for display, internal in DISPLAY_TO_INTERNAL.items():
        back = INTERNAL_TO_DISPLAY.get(internal)
        if back != display:
            print(f"  ERROR: name mapping not bijective: {display} -> {internal} -> {back}")
            errors += 1

    if errors == 0:
        print("  Validation: PASSED")
    else:
        print(f"  Validation: {errors} errors")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python convert_replay_for_cpp.py <ts_state_dump.json> [output.json]")
        sys.exit(1)

    ts_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    result = convert_replay(ts_path, out_path)
    if result is None:
        sys.exit(1)
