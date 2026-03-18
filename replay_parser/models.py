"""Data models for the Prismata replay parser."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResourcePool:
    """Prismata resource pool: gold, green (G), blue (B), red (C), energy (H), attack (A)."""
    gold: int = 0
    green: int = 0
    blue: int = 0
    red: int = 0
    energy: int = 0
    attack: int = 0

    def __add__(self, other: ResourcePool) -> ResourcePool:
        return ResourcePool(
            gold=self.gold + other.gold,
            green=self.green + other.green,
            blue=self.blue + other.blue,
            red=self.red + other.red,
            energy=self.energy + other.energy,
            attack=self.attack + other.attack,
        )

    def __sub__(self, other: ResourcePool) -> ResourcePool:
        """Subtract other from self. Does NOT clamp — negative values indicate a bug."""
        return ResourcePool(
            gold=self.gold - other.gold,
            green=self.green - other.green,
            blue=self.blue - other.blue,
            red=self.red - other.red,
            energy=self.energy - other.energy,
            attack=self.attack - other.attack,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResourcePool):
            return NotImplemented
        return (
            self.gold == other.gold
            and self.green == other.green
            and self.blue == other.blue
            and self.red == other.red
            and self.energy == other.energy
            and self.attack == other.attack
        )

    def can_afford(self, cost: ResourcePool) -> bool:
        """Return True if this pool covers every resource in cost."""
        return (
            self.gold >= cost.gold
            and self.green >= cost.green
            and self.blue >= cost.blue
            and self.red >= cost.red
            and self.energy >= cost.energy
            and self.attack >= cost.attack
        )

    def max_affordable(self, cost: ResourcePool) -> int:
        """Return the maximum number of times cost can be paid from this pool.

        For each non-zero field in cost, compute pool.X // cost.X.
        Returns the minimum across all such fields, or 0 if none can be bought.
        """
        limits: list[int] = []
        for self_val, cost_val in (
            (self.gold, cost.gold),
            (self.green, cost.green),
            (self.blue, cost.blue),
            (self.red, cost.red),
            (self.energy, cost.energy),
            (self.attack, cost.attack),
        ):
            if cost_val > 0:
                limits.append(self_val // cost_val)
        if not limits:
            return 0
        return min(limits)

    def copy(self) -> ResourcePool:
        return ResourcePool(
            gold=self.gold,
            green=self.green,
            blue=self.blue,
            red=self.red,
            energy=self.energy,
            attack=self.attack,
        )


@dataclass
class CardDef:
    """Definition of a card type from the game's mergedDeck."""
    deck_index: int
    name: str
    rarity: str
    buy_cost: ResourcePool
    toughness: int
    build_time: int
    is_base_set: bool
    default_blocking: bool
    begin_turn_receive: Optional[ResourcePool]
    ability_receive: Optional[ResourcePool]
    ability_selfsac: bool
    ability_create: Optional[list]      # e.g. [["Steelsplitter", "own"]]
    target_action: Optional[str]        # "snipe" or "disrupt" (chill)
    supply: int
    begin_turn_delay: int = 0


@dataclass
class UnitInstance:
    """A specific unit on the board."""
    instance_id: int
    card_def: CardDef
    owner: int
    turns_until_ready: int
    is_alive: bool
    used_ability_this_turn: bool


@dataclass
class Action:
    """A single parsed action within a turn."""
    action_type: str            # buy, buy_shift, ability, ability_shift,
                                # target, defend, commit, end_swipe, undo, revert, cancel_target
    unit_name: Optional[str]    # Display name of the unit involved
    deck_index: Optional[int]   # For buys: mergedDeck index
    instance_id: Optional[int]  # For abilities: instance ID
    quantity: int               # For shift-buys: how many purchased
    raw_click: dict             # Original {"_type": ..., "_id": ...}


@dataclass
class Turn:
    """All actions and state for one player-turn."""
    global_turn: int            # 0-indexed across both players
    player: int                 # 0 = P1, 1 = P2
    player_turn: int            # 1-indexed per player
    actions: list[Action] = field(default_factory=list)
    buys: list[str] = field(default_factory=list)
    abilities_used: list[str] = field(default_factory=list)
    resources_at_start: ResourcePool = field(default_factory=ResourcePool)
    resources_after: ResourcePool = field(default_factory=ResourcePool)
    units_owned: dict[str, int] = field(default_factory=dict)


@dataclass
class ReplayData:
    """Fully parsed replay."""
    code: str
    result: int
    card_defs: list[CardDef] = field(default_factory=list)
    randomizer: list[str] = field(default_factory=list)
    init_cards: list[list[tuple[int, str]]] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    total_global_turns: int = 0
    start_time: Optional[int] = None
    player_names: list[str] = field(default_factory=list)
