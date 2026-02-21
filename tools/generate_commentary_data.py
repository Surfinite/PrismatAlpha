"""Generate structured per-turn commentary data from a Prismata replay.

Fetches replay from S3, runs C++ --analyze for accurate buy extraction
(handles reverts, unlike naive click parsing), and outputs a human-readable
per-turn summary suitable for writing commentary.

Usage:
    python tools/generate_commentary_data.py REPLAY_CODE [--think-time MS] [--eval-only]

Examples:
    python tools/generate_commentary_data.py FxCfR-K49T+
    python tools/generate_commentary_data.py "FxCfR-K49T+" --think-time 200
    python tools/generate_commentary_data.py WjhmP-WWdXx --eval-only
"""
import sys
import os
import gzip
import json
import subprocess
import urllib.request
import urllib.parse
import argparse
from collections import Counter

REPLAY_URL = "http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/{}.json.gz"
REPLAY_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "bin", "replays_test")
EXE_PATH = os.path.join(os.path.dirname(__file__), "..", "bin", "Prismata_Testing_d.exe")

# The 11 base set units always available in every game
BASE_SET_NAMES = {
    "Drone", "Engineer", "Conduit", "Blastforge", "Animus",
    "Tarsier", "Rhino", "Wall", "Steelsplitter",
    "Gauss Cannon", "Forcefield",
}


def fetch_replay(code):
    """Fetch replay JSON from S3, caching locally."""
    os.makedirs(REPLAY_CACHE_DIR, exist_ok=True)
    safe_name = code.replace("+", "_PLUS_").replace("@", "_AT_")
    cache_path = os.path.join(REPLAY_CACHE_DIR, f"{safe_name}.json")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f), cache_path

    encoded = urllib.parse.quote(code, safe="")
    url = REPLAY_URL.format(encoded)
    print(f"Fetching {url} ...", file=sys.stderr)

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()

    data = gzip.decompress(raw)
    replay = json.loads(data)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(replay, f)
    print(f"Cached to {cache_path}", file=sys.stderr)

    return replay, cache_path


def get_deck_info(replay):
    """Extract randomized units (non-base-set) from mergedDeck."""
    md = replay.get("deckInfo", {}).get("mergedDeck", [])
    random_units = []
    for i, card in enumerate(md):
        name = card.get("name", card.get("UIName", f"id_{i}"))
        cost = card.get("buyCost", "?")
        supply = card.get("supply", "?")
        if name not in BASE_SET_NAMES:
            random_units.append({"name": name, "cost": cost, "supply": supply})
    return random_units


def get_players(replay):
    """Extract player names and ratings."""
    pi = replay.get("playerInfo", [])
    fr = replay.get("ratingInfo", {}).get("finalRatings", [])
    players = []
    for i, p in enumerate(pi):
        name = p.get("displayName", f"Player{i+1}")
        rating = int(fr[i].get("displayRating", 0)) if i < len(fr) else 0
        players.append({"name": name, "rating": rating})
    return players


def run_analyze(cache_path, think_time=50, player="OriginalHardestAI"):
    """Run C++ --analyze and parse JSON output."""
    exe = os.path.abspath(EXE_PATH)
    replay_path = os.path.abspath(cache_path)

    if not os.path.exists(exe):
        print(f"ERROR: exe not found at {exe}", file=sys.stderr)
        sys.exit(1)

    cmd = [exe, "--analyze", replay_path, "--player", player, "--think-time", str(think_time)]
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=os.path.join(os.path.dirname(__file__), "..", "bin"),
    )

    stdout = result.stdout.strip()
    if not stdout:
        print(f"ERROR: No output from --analyze", file=sys.stderr)
        if result.stderr:
            print(f"stderr: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON: {e}", file=sys.stderr)
        print(f"Raw output (first 500 chars): {stdout[:500]}", file=sys.stderr)
        sys.exit(1)


def run_eval_only(cache_path):
    """Run C++ --eval (fast, no AI search) and parse JSON output."""
    exe = os.path.abspath(EXE_PATH)
    replay_path = os.path.abspath(cache_path)

    if not os.path.exists(exe):
        print(f"ERROR: exe not found at {exe}", file=sys.stderr)
        sys.exit(1)

    cmd = [exe, "--eval", replay_path]
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=os.path.join(os.path.dirname(__file__), "..", "bin"),
    )

    stdout = result.stdout.strip()
    if not stdout:
        print(f"ERROR: No output from --eval", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON: {e}", file=sys.stderr)
        sys.exit(1)


def format_buys(buy_list):
    """Format a sorted buy list into grouped string: 'Drone(2x), Wall, Tarsier'."""
    if not buy_list:
        return "(none)"
    counts = Counter(buy_list)
    parts = []
    for name in sorted(counts.keys()):
        c = counts[name]
        parts.append(f"{name}({c}x)" if c > 1 else name)
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Pure-Python resource tracker for click-level buy validation
# ---------------------------------------------------------------------------
# Resource indices: 0=gold, 1=energy, 2=blue, 3=red, 4=green, 5=attack
_RES_GOLD, _RES_ENERGY, _RES_BLUE, _RES_RED, _RES_GREEN, _RES_ATTACK = range(6)
_RES_NAMES = ["gold", "energy", "blue", "red", "green", "attack"]
# Gold(0) and Green(4) persist between turns; Energy(1), Blue(2), Red(3) are use-or-lose
_PERSIST = {_RES_GOLD, _RES_GREEN}
# Resource string char -> index (matches Resources.cpp GetChar)
_CHAR_MAP = {'H': _RES_ENERGY, 'B': _RES_BLUE, 'C': _RES_RED, 'G': _RES_GREEN, 'A': _RES_ATTACK}


def parse_resources(s):
    """Parse Prismata resource string into [gold, energy, blue, red, green, attack].

    Format: optional integer prefix = gold, then each char = 1 unit of that type.
    E.g. "5G" = 5 gold + 1 green, "3H" = 3 gold + 1 energy, "H" = 1 energy.
    Also accepts plain integers (e.g. receive: 1 in JSON → 1 gold).
    """
    res = [0] * 6
    if not s and s != 0:
        return res
    if isinstance(s, (int, float)):
        res[_RES_GOLD] = int(s)
        return res
    s = str(s)
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    if i > 0:
        res[_RES_GOLD] = int(s[:i])
    while i < len(s):
        idx = _CHAR_MAP.get(s[i])
        if idx is not None:
            res[idx] += 1
        i += 1
    return res


def _can_afford(resources, cost):
    """Check if resources[i] >= cost[i] for all 6 types."""
    return all(resources[i] >= cost[i] for i in range(6))


def _subtract(resources, cost):
    for i in range(6):
        resources[i] -= cost[i]


def _add(resources, received):
    for i in range(6):
        resources[i] += received[i]


def _res_str(resources):
    """Format resources as compact string for debug: '8g 2e 1b'."""
    parts = []
    abbr = "gebrcA"
    for i in range(6):
        if resources[i]:
            parts.append(f"{resources[i]}{abbr[i]}")
    return " ".join(parts) if parts else "0"


class _CardInstance:
    """One card instance in a player's inventory."""
    __slots__ = ("type_idx", "build_time", "ability_used")

    def __init__(self, type_idx, build_time):
        self.type_idx = type_idx
        self.build_time = build_time
        self.ability_used = False


class ResourceTracker:
    """Validate BUY clicks by tracking resources through the replay commandList.

    Processes each player-turn:
      1. Decrement build times for under-construction cards
      2. Clear use-or-lose resources (energy, blue, red)
      3. Apply beginOwnTurnScript for all finished (build_time <= 0) cards
      4. Process clicks: inst activations produce resources, card clicks attempt buys
      5. Revert undoes the last action on the stack
    """

    def __init__(self, replay, verbose=False):
        self.verbose = verbose
        md = replay.get("deckInfo", {}).get("mergedDeck", [])
        self.commands = replay.get("commandInfo", {}).get("commandList", [])
        self.clicks_per_turn = replay.get("commandInfo", {}).get("clicksPerTurn", [])

        # Build card property table indexed by mergedDeck position
        self.card_props = []
        self.name_to_idx = {}  # card name -> mergedDeck index
        for ci, card in enumerate(md):
            name = card.get("name", card.get("UIName", f"id_{ci}"))
            self.name_to_idx[name] = ci
            props = {
                "name": name,
                "buy_cost": parse_resources(card.get("buyCost", "0")),
                "build_time": card.get("buildTime", 1),
                "begin_script": None,  # auto-production at turn start
                "ability_recv": None,  # resources received from ability
                "ability_cost": None,  # resources spent on ability (if any)
                "buy_sac": [],         # [(card_name, count), ...]
            }
            bot = card.get("beginOwnTurnScript", {})
            if isinstance(bot, dict) and "receive" in bot:
                props["begin_script"] = parse_resources(bot["receive"])
            ab = card.get("abilityScript", {})
            if isinstance(ab, dict) and "receive" in ab:
                props["ability_recv"] = parse_resources(ab["receive"])
            ac = card.get("abilityCost", "")
            if ac:
                props["ability_cost"] = parse_resources(ac)
            for sac_entry in card.get("buySac", []):
                if isinstance(sac_entry, list) and len(sac_entry) >= 2:
                    props["buy_sac"].append((sac_entry[0], sac_entry[1]))
            self.card_props.append(props)

        # Per-player state
        self.resources = [[0] * 6, [0] * 6]
        self.cards = [[], []]  # list of _CardInstance per player
        self.inst_to_type = {}  # instId -> (type_idx, player_idx)
        self.next_inst_id = 0

        # Set up initial cards from initInfo
        init_info = replay.get("initInfo", {})
        init_cards = init_info.get("initCards", [])
        for player_idx, entries in enumerate(init_cards):
            for count, name in entries:
                type_idx = self.name_to_idx.get(name, -1)
                if type_idx < 0:
                    continue
                for _ in range(count):
                    ci = _CardInstance(type_idx, 0)  # initial cards are ready
                    self.cards[player_idx].append(ci)
                    self.inst_to_type[self.next_inst_id] = (type_idx, player_idx)
                    self.next_inst_id += 1

    def _log(self, msg):
        if self.verbose:
            print(f"  [RT] {msg}", file=sys.stderr)

    def _turn_start(self, player_idx):
        """Decrement build times, clear use-or-lose, apply beginOwnTurnScript."""
        # Decrement build times first (so buildTime=1 cards become ready this turn)
        for ci in self.cards[player_idx]:
            if ci.build_time > 0:
                ci.build_time -= 1
            ci.ability_used = False

        # Clear use-or-lose resources
        for i in range(6):
            if i not in _PERSIST:
                self.resources[player_idx][i] = 0

        # Apply beginOwnTurnScript for all finished cards
        for ci in self.cards[player_idx]:
            if ci.build_time <= 0:
                bs = self.card_props[ci.type_idx]["begin_script"]
                if bs:
                    _add(self.resources[player_idx], bs)

        self._log(f"Turn start P{player_idx}: res={_res_str(self.resources[player_idx])}, "
                   f"cards={self._card_summary(player_idx)}")

    def _card_summary(self, player_idx):
        """Compact summary of card inventory for debug."""
        counts = Counter()
        for ci in self.cards[player_idx]:
            name = self.card_props[ci.type_idx]["name"]
            suffix = f"(b{ci.build_time})" if ci.build_time > 0 else ""
            counts[name + suffix] += 1
        return ", ".join(f"{name}x{c}" if c > 1 else name
                         for name, c in sorted(counts.items()))

    def _activate_ability(self, player_idx, type_idx):
        """Activate one card's ability. Returns resource change or None if can't."""
        props = self.card_props[type_idx]
        if not props["ability_recv"]:
            return None
        if props["ability_cost"] and not _can_afford(self.resources[player_idx], props["ability_cost"]):
            return None
        if props["ability_cost"]:
            _subtract(self.resources[player_idx], props["ability_cost"])
        _add(self.resources[player_idx], props["ability_recv"])
        return True

    def _handle_inst_click(self, player_idx, inst_id, shift, action_stack):
        """Handle inst clicked / inst shift clicked."""
        lookup = self.inst_to_type.get(inst_id)
        if lookup is None:
            # Unknown instId — could be from an opponent's card or unmapped
            self._log(f"Unknown instId {inst_id} for P{player_idx}")
            return

        type_idx, owner = lookup
        if owner != player_idx:
            # Clicking an opponent's card (e.g. snipe target) — not resource production
            return

        name = self.card_props[type_idx]["name"]
        if not self.card_props[type_idx]["ability_recv"]:
            # No ability to produce resources (e.g. Wall, Tarsier attack)
            return

        if shift:
            # Shift-click: activate ALL unspent cards of this type
            activated = 0
            for ci in self.cards[player_idx]:
                if ci.type_idx == type_idx and ci.build_time <= 0 and not ci.ability_used:
                    result = self._activate_ability(player_idx, type_idx)
                    if result:
                        ci.ability_used = True
                        activated += 1
                    else:
                        break  # Can't afford ability cost — stop activating
            self._log(f"Shift-activate {name} x{activated}: res={_res_str(self.resources[player_idx])}")
            action_stack.append(("inst_shift", type_idx, activated))
        else:
            # Single click: activate ONE card
            for ci in self.cards[player_idx]:
                if ci.type_idx == type_idx and ci.build_time <= 0 and not ci.ability_used:
                    result = self._activate_ability(player_idx, type_idx)
                    if result:
                        ci.ability_used = True
                        self._log(f"Activate {name}: res={_res_str(self.resources[player_idx])}")
                        action_stack.append(("inst_single", type_idx, inst_id))
                    break

    def _try_buy(self, player_idx, card_idx):
        """Attempt one purchase. Returns card name if successful, None if not."""
        if card_idx < 0 or card_idx >= len(self.card_props):
            return None
        props = self.card_props[card_idx]
        cost = props["buy_cost"]

        if not _can_afford(self.resources[player_idx], cost):
            return None

        # Check buySac requirements
        sac_positions = []
        for sac_name, sac_count in props["buy_sac"]:
            sac_type_idx = self.name_to_idx.get(sac_name, -1)
            available = []
            for ci_pos, ci in enumerate(self.cards[player_idx]):
                if ci.type_idx == sac_type_idx and ci.build_time <= 0 and ci_pos not in sac_positions:
                    available.append(ci_pos)
            if len(available) < sac_count:
                return None
            sac_positions.extend(available[:sac_count])

        # Execute buy
        _subtract(self.resources[player_idx], cost)

        # Remove sacrificed cards (reverse order to preserve indices)
        removed = []
        for pos in sorted(sac_positions, reverse=True):
            removed.append(self.cards[player_idx].pop(pos))

        # Add new card
        new_card = _CardInstance(card_idx, props["build_time"])
        self.cards[player_idx].append(new_card)
        new_inst_id = self.next_inst_id
        self.inst_to_type[new_inst_id] = (card_idx, player_idx)
        self.next_inst_id += 1

        return props["name"], new_card, removed, sac_positions, new_inst_id

    def _handle_card_click(self, player_idx, card_idx, shift, action_stack):
        """Handle card clicked / card shift clicked. Returns list of bought names."""
        bought_names = []
        name = self.card_props[card_idx]["name"] if 0 <= card_idx < len(self.card_props) else "?"

        if shift and name == "Drone":
            max_buys = 20  # buy max affordable
        else:
            max_buys = 1

        for _ in range(max_buys):
            result = self._try_buy(player_idx, card_idx)
            if result is None:
                if not bought_names:
                    self._log(f"REJECT buy {name}: can't afford ({_res_str(self.resources[player_idx])})")
                break
            bought_name, new_card, removed, sac_positions, new_inst_id = result
            bought_names.append(bought_name)
            action_stack.append(("buy", card_idx, new_card, removed, sac_positions, new_inst_id))

        if bought_names:
            self._log(f"Buy {format_buys(bought_names)}: res={_res_str(self.resources[player_idx])}")

        return bought_names

    def _handle_revert(self, player_idx, action_stack):
        """Undo last action."""
        if not action_stack:
            return

        entry = action_stack.pop()
        action_type = entry[0]

        if action_type == "buy":
            _, card_idx, new_card, removed, sac_positions, new_inst_id = entry
            # Restore resources
            _add(self.resources[player_idx], self.card_props[card_idx]["buy_cost"])
            # Remove bought card
            if new_card in self.cards[player_idx]:
                self.cards[player_idx].remove(new_card)
            # Restore sacrificed cards
            for pos, card in zip(sorted(sac_positions), removed):
                self.cards[player_idx].insert(pos, card)
            # Remove instId mapping
            if new_inst_id in self.inst_to_type:
                del self.inst_to_type[new_inst_id]
            self.next_inst_id = max(self.next_inst_id - 1, 0)
            name = self.card_props[card_idx]["name"]
            self._log(f"Revert buy {name}: res={_res_str(self.resources[player_idx])}")

        elif action_type == "inst_shift":
            _, type_idx, count = entry
            # Reverse all activations
            props = self.card_props[type_idx]
            reversed_count = 0
            for ci in self.cards[player_idx]:
                if ci.type_idx == type_idx and ci.ability_used and reversed_count < count:
                    if props["ability_recv"]:
                        _subtract(self.resources[player_idx], props["ability_recv"])
                    if props["ability_cost"]:
                        _add(self.resources[player_idx], props["ability_cost"])
                    ci.ability_used = False
                    reversed_count += 1
            self._log(f"Revert shift-activate {props['name']} x{reversed_count}")

        elif action_type == "inst_single":
            _, type_idx, inst_id = entry
            props = self.card_props[type_idx]
            for ci in self.cards[player_idx]:
                if ci.type_idx == type_idx and ci.ability_used:
                    if props["ability_recv"]:
                        _subtract(self.resources[player_idx], props["ability_recv"])
                    if props["ability_cost"]:
                        _add(self.resources[player_idx], props["ability_cost"])
                    ci.ability_used = False
                    break
            self._log(f"Revert activate {props['name']}")

    def run(self):
        """Process full replay. Returns list of {turn_idx, shared_turn, player, buys}."""
        cmd_offset = 0
        results = []

        for turn_idx, click_count in enumerate(self.clicks_per_turn):
            player_idx = turn_idx % 2
            clicks = self.commands[cmd_offset:cmd_offset + click_count]
            cmd_offset += click_count

            self._turn_start(player_idx)
            action_stack = []
            turn_buys = []

            for click in clicks:
                ctype = click.get("_type", "")
                cid = click.get("_id", -1)

                if "inst" in ctype and "clicked" in ctype:
                    shift = "shift" in ctype
                    self._handle_inst_click(player_idx, cid, shift, action_stack)
                elif "card" in ctype and "clicked" in ctype:
                    shift = "shift" in ctype
                    bought = self._handle_card_click(player_idx, cid, shift, action_stack)
                    turn_buys.extend(bought)
                elif ctype == "revert clicked":
                    # Undo — also remove from turn_buys if it was a buy
                    if action_stack and action_stack[-1][0] == "buy":
                        name = self.card_props[action_stack[-1][1]]["name"]
                        if name in turn_buys:
                            turn_buys.remove(name)
                    self._handle_revert(player_idx, action_stack)

            shared_turn = turn_idx // 2 + 1
            results.append({
                "turn_idx": turn_idx,
                "shared_turn": shared_turn,
                "player": player_idx,
                "buys": turn_buys,
            })

        return results


def print_summary(code, replay, analysis):
    """Print human-readable per-turn summary."""
    players = get_players(replay)
    deck = get_deck_info(replay)
    winner = analysis.get("winner", -1)
    turns = analysis.get("turns", [])

    winner_str = f"P{winner+1} ({players[winner]['name']}) wins" if winner >= 0 else "unknown result"

    # Check stepper reliability
    total_clicks = analysis.get("stepper_total_clicks", 0)
    applied_clicks = analysis.get("stepper_applied_clicks", 0)
    benign_skips = analysis.get("stepper_benign_skips", 0)
    stepper_reliable = total_clicks > 0 and (applied_clicks + benign_skips) > total_clicks * 0.8

    print(f"=== {code} ===")
    print(f"{players[0]['name']} ({players[0]['rating']}) vs {players[1]['name']} ({players[1]['rating']}) -- {winner_str}")
    print(f"Set: {', '.join(u['name'] for u in deck)}")
    print(f"Turns analyzed: {analysis.get('turns_analyzed', '?')}")
    if total_clicks > 0:
        print(f"Stepper: {applied_clicks}/{total_clicks} clicks applied, {benign_skips} skips"
              f" {'(RELIABLE)' if stepper_reliable else '(UNRELIABLE — click buys may overcount)'}")

    if "agreement_rate" in analysis:
        rate = analysis["agreement_rate"]
        agrees = analysis.get("agreements", "?")
        total = analysis.get("turns_analyzed", "?")
        print(f"Agreement rate: {rate:.0%} ({agrees}/{total})")

    if "biggest_mistake" in analysis:
        bm = analysis["biggest_mistake"]
        print(f"Biggest mistake: Turn {bm.get('turn', '?')} (eval drop: {bm.get('eval_drop', 0):.2f})")

    if "eval_swing" in analysis:
        print(f"Max eval swing: {analysis['eval_swing']:.2f}")

    print()

    for t in turns:
        turn_num = t["turn"] // 2 + 1
        player_idx = t["player"]
        player_name = players[player_idx]["name"] if player_idx < len(players) else f"P{player_idx+1}"
        pct = t.get("eval_pct", "?")

        line = f"T{turn_num} P{player_idx+1} ({player_name}) [eval {pct}]:"

        if "human_buy" in t:
            click_buys = t["human_buy"]
            validated_buys = t.get("validated_buy", [])

            # Use validated buys if available, fall back to click buys
            if validated_buys:
                line += f"  Bought: {format_buys(validated_buys)}"
                if click_buys != validated_buys:
                    line += f"  (clicks: {format_buys(click_buys)})"
            else:
                line += f"  Bought: {format_buys(click_buys)}"
                if not stepper_reliable:
                    line += "  [unvalidated]"

            if "buy_agree" in t:
                ai_buys = t.get("ai_buy", [])
                if t["buy_agree"]:
                    line += "  |  AI agrees"
                elif ai_buys:
                    line += f"  |  AI would buy: {format_buys(ai_buys)}"
        else:
            line += f"  (eval only)"

        print(line)

    print()
    print("--- End of analysis ---")


def print_validated_buys(code, replay, validated_turns):
    """Print resource-validated per-turn buy summary (no C++ needed)."""
    players = get_players(replay)
    deck = get_deck_info(replay)

    print(f"=== {code} (Python resource validation) ===")
    print(f"{players[0]['name']} vs {players[1]['name']}")
    print(f"Set: {', '.join(u['name'] for u in deck)}")
    print()

    for t in validated_turns:
        shared = t["shared_turn"]
        pidx = t["player"]
        pname = players[pidx]["name"] if pidx < len(players) else f"P{pidx+1}"
        buys_str = format_buys(t["buys"]) if t["buys"] else "(none)"
        print(f"T{shared} P{pidx+1} ({pname}):  {buys_str}")

    print()
    print("--- End of validation ---")


def main():
    parser = argparse.ArgumentParser(description="Generate commentary data from replay")
    parser.add_argument("code", help="Replay code (e.g., FxCfR-K49T+)")
    parser.add_argument("--think-time", type=int, default=50, help="AI think time in ms (default: 50, x86 OOMs at 200+)")
    parser.add_argument("--player", default="OriginalHardestAI", help="AI player for comparison (default: OriginalHardestAI)")
    parser.add_argument("--eval-only", action="store_true", help="Skip AI search, just neural eval per turn")
    parser.add_argument("--validate", action="store_true",
                        help="Pure-Python resource validation (no C++ exe needed)")
    parser.add_argument("--verbose", action="store_true", help="Show resource tracking debug output")
    args = parser.parse_args()

    replay, cache_path = fetch_replay(args.code)

    if args.validate:
        tracker = ResourceTracker(replay, verbose=args.verbose)
        validated = tracker.run()
        print_validated_buys(args.code, replay, validated)
        return

    if args.eval_only:
        analysis = run_eval_only(cache_path)
    else:
        analysis = run_analyze(cache_path, args.think_time, args.player)

    if not analysis.get("ok", False):
        print(f"ERROR: Analysis failed: {analysis.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)

    print_summary(args.code, replay, analysis)


if __name__ == "__main__":
    main()
