"""Simulator: walk replay clicks and populate turn-by-turn state."""
from __future__ import annotations

import logging
from typing import Optional

from replay_parser.models import (
    Action,
    CardDef,
    ReplayData,
    ResourcePool,
    Turn,
    UnitInstance,
)

logger = logging.getLogger(__name__)

# Click types that represent real game actions (can be undone/reverted).
_ACTIONABLE_CLICK_TYPES = frozenset(
    ["inst clicked", "inst shift clicked", "card clicked", "card shift clicked"]
)


def _preprocess_clicks(clicks: list[dict]) -> list[dict]:
    """Filter out clicks that were cancelled by undo/revert.

    Rules:
    - ``revert clicked``: discard ALL actionable clicks before the revert.
      Non-actionable clicks (space, end_swipe, emote) before the revert are
      also discarded.  Clicks *after* the revert are kept.
    - ``undo clicked``: discard the most recent actionable click.  Multiple
      consecutive undos each remove one more actionable click.
    - The undo/revert clicks themselves are removed from the output.
    - Non-actionable clicks that survive (space, end_swipe) are preserved.
    """
    # Work left-to-right; build a stack of surviving clicks.
    result: list[dict] = []

    for click in clicks:
        ct = click["_type"]

        if ct == "revert clicked":
            # Discard all actionable clicks accumulated so far.
            # Also discard non-actionable clicks (spaces etc.) since the player
            # restarted their turn — the phase structure resets too.
            result = [c for c in result if c["_type"] not in _ACTIONABLE_CLICK_TYPES
                      and c["_type"] not in ("space clicked", "end swipe processed")]
            # The revert click itself is not added.

        elif ct == "undo clicked":
            # Remove the most recent actionable click from the result.
            for i in range(len(result) - 1, -1, -1):
                if result[i]["_type"] in _ACTIONABLE_CLICK_TYPES:
                    result.pop(i)
                    break
            # The undo click itself is not added.

        else:
            result.append(click)

    return result


# Drone supply is per-player.  P0 starts with 6 Drones so gets 21 shop supply,
# P1 starts with 7 so gets 20 — giving both players equal total access (27).
_DRONE_SHOP_SUPPLY = {0: 21, 1: 20}


def simulate(replay: ReplayData) -> None:
    """Walk all clicks in *replay* and populate ``replay.turns`` in-place.

    Requires that ``replay._command_info`` has been set by the decoder
    (contains ``commandList`` and ``clicksPerTurn``).
    """
    command_info = replay._command_info
    command_list = command_info["commandList"]
    clicks_per_turn = command_info["clicksPerTurn"]

    # Build card_def lookup by deck_index
    card_def_by_index: dict[int, CardDef] = {cd.deck_index: cd for cd in replay.card_defs}

    # ------------------------------------------------------------------
    # Initialization: populate unit rosters from init_cards
    # ------------------------------------------------------------------
    # Per-player roster: instance_id -> UnitInstance
    rosters: list[dict[int, UnitInstance]] = [{}, {}]
    # Tracks how many turns each unit has been ready (for begin_turn_delay)
    turns_since_ready: dict[int, int] = {}
    next_instance_id = 0

    for player_idx, player_init in enumerate(replay.init_cards):
        for count, card_name in player_init:
            # Find the CardDef for this card name
            card_def = _find_card_def_by_name(replay.card_defs, card_name)
            if card_def is None:
                logger.warning("Init card %r not found in card_defs", card_name)
                continue
            for _ in range(count):
                inst = UnitInstance(
                    instance_id=next_instance_id,
                    card_def=card_def,
                    owner=player_idx,
                    turns_until_ready=0,  # init cards start ready
                    is_alive=True,
                    used_ability_this_turn=False,
                )
                rosters[player_idx][next_instance_id] = inst
                # Init units are considered to have been ready "forever" —
                # they always satisfy begin_turn_delay on the first turn.
                turns_since_ready[next_instance_id] = 999
                next_instance_id += 1

    # ------------------------------------------------------------------
    # Supply tracking
    # ------------------------------------------------------------------
    # Shared supply for non-Drone cards (deck_index -> remaining)
    shared_supply: dict[int, int] = {}
    for cd in replay.card_defs:
        shared_supply[cd.deck_index] = cd.supply

    # Per-player Drone supply
    drone_card_def = _find_card_def_by_name(replay.card_defs, "Drone")
    drone_deck_index = drone_card_def.deck_index if drone_card_def else -1
    drone_supply: dict[int, int] = dict(_DRONE_SHOP_SUPPLY)

    # Per-player resources (mutable, carried across turns)
    resources: list[ResourcePool] = [ResourcePool(), ResourcePool()]

    # Player-turn counters (1-indexed per player)
    player_turn_counter = [0, 0]

    # ------------------------------------------------------------------
    # Walk turns
    # ------------------------------------------------------------------
    # Pre-slice clicks by clicksPerTurn, then fix boundary alignment.
    # Some replays have emotes that push buy+commit clicks into the next
    # turn's slice. Detect and fix: if a turn has no space click (no commit),
    # steal leading clicks from the next turn up through the commit spaces.
    turn_click_slices = []
    cmd_offset = 0
    for n_clicks in clicks_per_turn:
        turn_click_slices.append(command_list[cmd_offset: cmd_offset + n_clicks])
        cmd_offset += n_clicks

    # Fix iteratively: keep processing until no more spaceless turns remain
    changed = True
    while changed:
        changed = False
        for t in range(len(turn_click_slices) - 1):
            non_emote = [c for c in turn_click_slices[t]
                         if not c["_type"].startswith("emote")]
            has_space = any(c["_type"] == "space clicked" for c in non_emote)
            if not has_space:
                # This turn has no commit — steal from next turn until we get 2 spaces
                next_clicks = turn_click_slices[t + 1]
                steal_count = 0
                spaces_seen = 0
                for c in next_clicks:
                    if c["_type"].startswith("emote"):
                        steal_count += 1
                        continue
                    steal_count += 1
                    if c["_type"] == "space clicked":
                        spaces_seen += 1
                        if spaces_seen >= 2:
                            break
                if spaces_seen >= 1:  # Steal even with 1 space (may need another pass)
                    turn_click_slices[t].extend(next_clicks[:steal_count])
                    turn_click_slices[t + 1] = next_clicks[steal_count:]
                    changed = True

    replay.turns = []

    for global_turn, turn_clicks in enumerate(turn_click_slices):
        active_player = global_turn % 2
        player_turn_counter[active_player] += 1

        # --- Step 0: Remove clicks that were undone/reverted by the player ---
        turn_clicks = _preprocess_clicks(turn_clicks)

        # --- Step 0.5: Resource decay — only gold and green persist between turns ---
        # Blue, red, energy, and attack reset to 0 at turn start.
        pool = resources[active_player]
        pool.blue = 0
        pool.red = 0
        pool.energy = 0
        pool.attack = 0

        # --- Step 1: Credit passive income (beginOwnTurnScript.receive) ---
        _credit_passive_income(
            rosters[active_player], resources[active_player], turns_since_ready
        )

        # --- Step 2: Advance construction ---
        _advance_construction(rosters[active_player], turns_since_ready)

        # --- Step 3: Snapshot resources_at_start ---
        resources_at_start = resources[active_player].copy()

        # --- Step 4: Snapshot units_owned (start-of-turn, before buys) ---
        units_owned = _count_alive_units(rosters[active_player])

        # --- Step 5: Process clicks ---
        actions: list[Action] = []
        buys: list[str] = []
        abilities_used: list[str] = []
        space_count = 0
        # Track instances bought this turn (for un-buy detection)
        bought_this_turn: set[int] = set()
        # Confirm phase: space after any buy/ability enters confirm.
        # Space in confirm = commit (end turn). Any other click in confirm
        # just reverts confirm (back to action) — that click is skipped.
        in_confirm = False
        had_productive_click = False

        for click in turn_clicks:
            click_type = click["_type"]
            click_id = click["_id"]

            # Skip emotes
            if click_type.startswith("emote"):
                continue

            # Space = phase commit or confirm commit
            if click_type == "space clicked":
                if had_productive_click and not in_confirm:
                    in_confirm = True
                had_productive_click = False
                space_count += 1
                actions.append(Action(
                    action_type="commit",
                    unit_name=None,
                    deck_index=None,
                    instance_id=None,
                    quantity=0,
                    raw_click=click,
                ))
                continue

            # End swipe
            if click_type == "end swipe processed":
                actions.append(Action(
                    action_type="end_swipe",
                    unit_name=None,
                    deck_index=None,
                    instance_id=None,
                    quantity=0,
                    raw_click=click,
                ))
                continue

            # Confirm phase: first non-space click just reverts confirm.
            # Skip this click (it's not a real action), back to action phase.
            if in_confirm:
                in_confirm = False
                continue

            # Instance click (ability, defend, or un-buy)
            if click_type in ("inst clicked", "inst shift clicked"):
                is_shift = click_type == "inst shift clicked"
                inst = _find_instance(rosters, click_id)
                if inst is None:
                    logger.warning(
                        "Turn %d: inst click on unknown ID %d", global_turn, click_id
                    )
                    continue

                # Un-buy detection: clicking a unit bought this turn refunds the purchase.
                # Shift-click unbuys ALL bought instances of that card type.
                if click_id in bought_this_turn:
                    # Find all instances to unbuy
                    if is_shift:
                        # Shift: unbuy all bought instances of this card type
                        to_unbuy = [
                            iid for iid in bought_this_turn
                            if iid in rosters[active_player]
                            and rosters[active_player][iid].card_def.deck_index == inst.card_def.deck_index
                        ]
                    else:
                        to_unbuy = [click_id]

                    for uid in to_unbuy:
                        u = rosters[active_player].get(uid)
                        if u is None:
                            continue
                        # Refund the buy cost
                        resources[active_player] = resources[active_player] + u.card_def.buy_cost
                        # Restore supply
                        if u.card_def.name == "Drone":
                            drone_supply[active_player] += 1
                        else:
                            shared_supply[u.card_def.deck_index] = shared_supply.get(u.card_def.deck_index, 0) + 1
                        # Remove from roster and bought tracking
                        u.is_alive = False
                        bought_this_turn.discard(uid)
                        # Remove from buys list (last occurrence of this name)
                        name = u.card_def.name
                        for j in range(len(buys) - 1, -1, -1):
                            if buys[j] == name:
                                buys.pop(j)
                                break

                    actions.append(Action(
                        action_type="unbuy",
                        unit_name=inst.card_def.name,
                        deck_index=inst.card_def.deck_index,
                        instance_id=click_id,
                        quantity=len(to_unbuy),
                        raw_click=click,
                    ))
                    continue

                if space_count == 0:
                    # Phase 0 — could be defense OR early ability (turn 0 has no defense).
                    if inst.card_def.ability_receive is not None:
                        _process_ability(
                            rosters[active_player],
                            inst,
                            is_shift,
                            active_player,
                            resources,
                            actions,
                            abilities_used,
                            click,
                        )
                        had_productive_click = True
                    else:
                        # Defense click — NOT productive (doesn't trigger confirm)
                        actions.append(Action(
                            action_type="defend",
                            unit_name=inst.card_def.name,
                            deck_index=None,
                            instance_id=click_id,
                            quantity=1,
                            raw_click=click,
                        ))
                else:
                    # Phase 1+ — ability activation
                    _process_ability(
                        rosters[active_player],
                        inst,
                        is_shift,
                        active_player,
                        resources,
                        actions,
                        abilities_used,
                        click,
                    )
                    had_productive_click = True
                continue

            # Card buy (single)
            if click_type == "card clicked":
                card_def = card_def_by_index.get(click_id)
                if card_def is None:
                    logger.warning(
                        "Turn %d: card click on unknown deck index %d",
                        global_turn, click_id,
                    )
                    continue
                bought = _try_buy(
                    card_def, 1, active_player, resources, rosters,
                    shared_supply, drone_supply, drone_deck_index,
                    next_instance_id, turns_since_ready,
                )
                if bought > 0:
                    for b in range(bought):
                        bought_this_turn.add(next_instance_id + b)
                    next_instance_id += bought
                    buys.append(card_def.name)
                    had_productive_click = True
                    actions.append(Action(
                        action_type="buy",
                        unit_name=card_def.name,
                        deck_index=click_id,
                        instance_id=None,
                        quantity=1,
                        raw_click=click,
                    ))
                continue

            # Card shift-buy (buy as many as possible)
            if click_type == "card shift clicked":
                card_def = card_def_by_index.get(click_id)
                if card_def is None:
                    logger.warning(
                        "Turn %d: card shift click on unknown deck index %d",
                        global_turn, click_id,
                    )
                    continue
                available_supply = _get_supply(
                    card_def, active_player, shared_supply, drone_supply, drone_deck_index
                )
                max_count = resources[active_player].max_affordable(card_def.buy_cost)
                count = min(max_count, available_supply)
                if count > 0:
                    bought = _try_buy(
                        card_def, count, active_player, resources, rosters,
                        shared_supply, drone_supply, drone_deck_index,
                        next_instance_id, turns_since_ready,
                    )
                    for b in range(bought):
                        bought_this_turn.add(next_instance_id + b)
                    next_instance_id += bought
                    for _ in range(bought):
                        buys.append(card_def.name)
                    had_productive_click = True
                    actions.append(Action(
                        action_type="buy_shift",
                        unit_name=card_def.name,
                        deck_index=click_id,
                        instance_id=None,
                        quantity=bought,
                        raw_click=click,
                    ))
                continue

            # Cancel target — no state change
            if click_type == "cancel target processed":
                continue

            # Unknown click type — log and skip
            logger.warning(
                "Turn %d: unknown click type %r (id=%s)", global_turn, click_type, click_id
            )

        # --- Step 6: Snapshot resources_after ---
        resources_after = resources[active_player].copy()

        # --- Step 7: Reset per-turn flags ---
        for inst in rosters[active_player].values():
            inst.used_ability_this_turn = False

        # --- Step 8: Build Turn object ---
        turn = Turn(
            global_turn=global_turn,
            player=active_player,
            player_turn=player_turn_counter[active_player],
            actions=actions,
            buys=buys,
            abilities_used=abilities_used,
            resources_at_start=resources_at_start,
            resources_after=resources_after,
            units_owned=units_owned,
        )
        replay.turns.append(turn)


# ======================================================================
# Helper functions
# ======================================================================


def _find_card_def_by_name(card_defs: list[CardDef], name: str) -> Optional[CardDef]:
    """Return the first CardDef matching *name*, or None."""
    for cd in card_defs:
        if cd.name == name:
            return cd
    return None


def _find_instance(
    rosters: list[dict[int, UnitInstance]], instance_id: int
) -> Optional[UnitInstance]:
    """Look up an instance across both player rosters."""
    for roster in rosters:
        if instance_id in roster:
            return roster[instance_id]
    return None


def _credit_passive_income(
    roster: dict[int, UnitInstance],
    pool: ResourcePool,
    turns_since_ready: dict[int, int],
) -> None:
    """Credit beginOwnTurnScript.receive for all ready, alive units."""
    for inst in roster.values():
        if not inst.is_alive:
            continue
        if inst.turns_until_ready > 0:
            continue  # still under construction
        cd = inst.card_def
        if cd.begin_turn_receive is None:
            continue
        # Check begin_turn_delay: unit must have been ready for >= delay turns
        ready_turns = turns_since_ready.get(inst.instance_id, 0)
        if ready_turns < cd.begin_turn_delay:
            continue
        # Credit the resources
        pool.gold += cd.begin_turn_receive.gold
        pool.green += cd.begin_turn_receive.green
        pool.blue += cd.begin_turn_receive.blue
        pool.red += cd.begin_turn_receive.red
        pool.energy += cd.begin_turn_receive.energy
        pool.attack += cd.begin_turn_receive.attack


def _advance_construction(
    roster: dict[int, UnitInstance],
    turns_since_ready: dict[int, int],
) -> None:
    """Decrement turns_until_ready for constructing units; track readiness age."""
    for inst in roster.values():
        if not inst.is_alive:
            continue
        if inst.turns_until_ready > 0:
            inst.turns_until_ready -= 1
            if inst.turns_until_ready == 0:
                # Just became ready — start tracking, but 0 turns of readiness so far
                turns_since_ready[inst.instance_id] = 0
        else:
            # Already ready — increment readiness counter
            tsr = turns_since_ready.get(inst.instance_id, 0)
            turns_since_ready[inst.instance_id] = tsr + 1


def _count_alive_units(roster: dict[int, UnitInstance]) -> dict[str, int]:
    """Count alive units by display name."""
    counts: dict[str, int] = {}
    for inst in roster.values():
        if inst.is_alive:
            name = inst.card_def.name
            counts[name] = counts.get(name, 0) + 1
    return counts


def _process_ability(
    roster: dict[int, UnitInstance],
    clicked_inst: UnitInstance,
    is_shift: bool,
    active_player: int,
    resources: list[ResourcePool],
    actions: list[Action],
    abilities_used: list[str],
    raw_click: dict,
) -> None:
    """Process an ability activation (single or shift-click)."""
    card_def = clicked_inst.card_def
    pool = resources[active_player]

    if is_shift:
        # Shift-click: activate ALL ready, alive instances of the same CardDef
        # owned by the active player that haven't used their ability this turn.
        targets = [
            inst for inst in roster.values()
            if inst.is_alive
            and inst.turns_until_ready == 0
            and inst.card_def.deck_index == card_def.deck_index
            and not inst.used_ability_this_turn
        ]
        count = 0
        for inst in targets:
            if card_def.ability_receive is not None:
                pool.gold += card_def.ability_receive.gold
                pool.green += card_def.ability_receive.green
                pool.blue += card_def.ability_receive.blue
                pool.red += card_def.ability_receive.red
                pool.energy += card_def.ability_receive.energy
                pool.attack += card_def.ability_receive.attack
            inst.used_ability_this_turn = True
            if card_def.ability_selfsac:
                inst.is_alive = False
            count += 1
        if count > 0 and card_def.name not in abilities_used:
            abilities_used.append(card_def.name)
        actions.append(Action(
            action_type="ability_shift",
            unit_name=card_def.name,
            deck_index=None,
            instance_id=clicked_inst.instance_id,
            quantity=count,
            raw_click=raw_click,
        ))
    else:
        # Single click: activate just this one instance
        if card_def.ability_receive is not None:
            pool.gold += card_def.ability_receive.gold
            pool.green += card_def.ability_receive.green
            pool.blue += card_def.ability_receive.blue
            pool.red += card_def.ability_receive.red
            pool.energy += card_def.ability_receive.energy
            pool.attack += card_def.ability_receive.attack
        clicked_inst.used_ability_this_turn = True
        if card_def.ability_selfsac:
            clicked_inst.is_alive = False
        if card_def.name not in abilities_used:
            abilities_used.append(card_def.name)
        actions.append(Action(
            action_type="ability",
            unit_name=card_def.name,
            deck_index=None,
            instance_id=clicked_inst.instance_id,
            quantity=1,
            raw_click=raw_click,
        ))


def _get_supply(
    card_def: CardDef,
    active_player: int,
    shared_supply: dict[int, int],
    drone_supply: dict[int, int],
    drone_deck_index: int,
) -> int:
    """Return the remaining supply for a card, respecting per-player Drone supply."""
    if card_def.deck_index == drone_deck_index:
        return drone_supply.get(active_player, 0)
    return shared_supply.get(card_def.deck_index, 0)


def _deduct_supply(
    card_def: CardDef,
    count: int,
    active_player: int,
    shared_supply: dict[int, int],
    drone_supply: dict[int, int],
    drone_deck_index: int,
) -> None:
    """Deduct *count* from the appropriate supply pool."""
    if card_def.deck_index == drone_deck_index:
        drone_supply[active_player] = drone_supply.get(active_player, 0) - count
    else:
        shared_supply[card_def.deck_index] = shared_supply.get(card_def.deck_index, 0) - count


def _try_buy(
    card_def: CardDef,
    count: int,
    active_player: int,
    resources: list[ResourcePool],
    rosters: list[dict[int, UnitInstance]],
    shared_supply: dict[int, int],
    drone_supply: dict[int, int],
    drone_deck_index: int,
    next_instance_id: int,
    turns_since_ready: dict[int, int],
) -> int:
    """Attempt to buy *count* copies of *card_def*. Returns number actually bought."""
    pool = resources[active_player]
    available = _get_supply(card_def, active_player, shared_supply, drone_supply, drone_deck_index)
    actual = min(count, available)

    # Double-check affordability for each unit
    bought = 0
    for _ in range(actual):
        if not pool.can_afford(card_def.buy_cost):
            break
        # Deduct cost
        pool.gold -= card_def.buy_cost.gold
        pool.green -= card_def.buy_cost.green
        pool.blue -= card_def.buy_cost.blue
        pool.red -= card_def.buy_cost.red
        pool.energy -= card_def.buy_cost.energy
        pool.attack -= card_def.buy_cost.attack

        # Create new unit instance
        iid = next_instance_id + bought
        inst = UnitInstance(
            instance_id=iid,
            card_def=card_def,
            owner=active_player,
            turns_until_ready=card_def.build_time,
            is_alive=True,
            used_ability_this_turn=False,
        )
        rosters[active_player][iid] = inst

        # Track readiness for units with build_time == 0
        if card_def.build_time == 0:
            turns_since_ready[iid] = 0
        # else: will be set when construction completes in _advance_construction

        bought += 1

    # Deduct supply
    if bought > 0:
        _deduct_supply(
            card_def, bought, active_player,
            shared_supply, drone_supply, drone_deck_index,
        )

    return bought
