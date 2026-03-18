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
    """Definition of a card type from the game's mergedDeck.

    Shared across all unit instances of the same card type.
    """
    deck_index: int
    name: str
    rarity: str                        # "trinket", "normal", "rare", "legendary"
    buy_cost: ResourcePool
    toughness: int
    build_time: int                    # turns until ready after purchase (0 = immediate)
    is_base_set: bool
    default_blocking: bool
    begin_turn_receive: Optional[ResourcePool]   # passive income each turn
    ability_receive: Optional[ResourcePool]      # resources received on ability use
    ability_selfsac: bool                        # ability sacrifices the unit
    ability_create: Optional[str]               # name of unit created by ability (if any)
    target_action: Optional[str]                # "chill" / "snipe" / None
    supply: int                                  # max units purchasable (20/4/1 by rarity)
    begin_turn_delay: int = 0                   # turns before passive income starts (e.g. Chrono Filter)


@dataclass
class UnitInstance:
    """A specific unit on the board.

    References a CardDef for type information; tracks per-instance mutable state.
    """
    instance_id: int
    card_def: CardDef
    owner: int                         # 0 = player 0, 1 = player 1
    turns_until_ready: int             # 0 = ready to act/block
    is_alive: bool
    used_ability_this_turn: bool


@dataclass
class Action:
    """A single parsed click action within a turn."""
    action_type: str                   # e.g. "BUY", "USE_ABILITY", "ASSIGN_BLOCKER", "CHILL", etc.
    instance_id: Optional[int]        # instance ID of the unit clicked (None for UI-level actions)
    card_name: Optional[str]          # card name for BUY actions (resolved from deck_index)
    raw_type: str                     # original _type string from commandList
    raw_id: int                       # original _id value from commandList


@dataclass
class Turn:
    """All actions and state for one player-turn."""
    turn_number: int
    player: int                        # 0 or 1
    actions: list[Action] = field(default_factory=list)
    resources_at_start: Optional[ResourcePool] = None
    resources_spent: Optional[ResourcePool] = None
    resources_gained: Optional[ResourcePool] = None


@dataclass
class ReplayData:
    """Fully parsed replay.

    Populated by the decoder; turn resource tracking added by the simulator.
    """
    code: str
    player_names: list[str]           # [p0_name, p1_name]
    result: int                        # 0 = P0 wins, 1 = P1 wins, 2 = draw
    card_defs: dict[int, CardDef]     # deck_index → CardDef
    turns: list[Turn] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # raw replay fields (ratings, timestamp, etc.)
