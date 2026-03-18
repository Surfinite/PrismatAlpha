"""Resource string parser for Prismata replay data."""
from replay_parser.models import ResourcePool

_CHAR_MAP = {
    'G': 'green',
    'B': 'blue',
    'C': 'red',
    'A': 'attack',
    'H': 'energy',
}


def parse_resource_string(value):
    """Parse Prismata resource string into ResourcePool.

    Format: digits = gold, G = green, B = blue, C = red, A = attack, H = energy.
    Unknown characters are silently ignored.
    Also accepts int (treated as gold) or None (returns empty pool).
    """
    if value is None:
        return ResourcePool()
    if isinstance(value, int):
        return ResourcePool(gold=value)

    result = ResourcePool()
    gold_digits = []
    for ch in value:
        if ch.isdigit():
            gold_digits.append(ch)
        elif ch in _CHAR_MAP:
            if gold_digits:
                result.gold += int(''.join(gold_digits))
                gold_digits = []
            field = _CHAR_MAP[ch]
            setattr(result, field, getattr(result, field) + 1)
    if gold_digits:
        result.gold += int(''.join(gold_digits))
    return result
