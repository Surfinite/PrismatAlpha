from replay_parser.resources import parse_resource_string
from replay_parser.models import ResourcePool

def test_parse_gold_only():
    assert parse_resource_string("6") == ResourcePool(gold=6)

def test_parse_multi_digit_gold():
    assert parse_resource_string("15") == ResourcePool(gold=15)

def test_parse_drone_cost():
    assert parse_resource_string("3H") == ResourcePool(gold=3, energy=1)

def test_parse_complex():
    # 'R' is not a valid resource character and is silently ignored
    assert parse_resource_string("6GGGRBB") == ResourcePool(gold=6, green=3, blue=2)

def test_parse_attack():
    assert parse_resource_string("AA") == ResourcePool(attack=2)

def test_parse_mixed_resources_and_attack():
    assert parse_resource_string("8AAAAAAAA") == ResourcePool(gold=8, attack=8)

def test_parse_gold_with_letters():
    assert parse_resource_string("5GGG") == ResourcePool(gold=5, green=3)

def test_parse_integer_input():
    assert parse_resource_string(3) == ResourcePool(gold=3)

def test_parse_none():
    assert parse_resource_string(None) == ResourcePool()

def test_parse_empty_string():
    assert parse_resource_string("") == ResourcePool()

def test_parse_zero():
    assert parse_resource_string("0") == ResourcePool()

def test_parse_red_is_c():
    assert parse_resource_string("4C") == ResourcePool(gold=4, red=1)

def test_parse_blastforge_cost():
    assert parse_resource_string("5") == ResourcePool(gold=5)

def test_parse_colossus_cost():
    assert parse_resource_string("15GBBCC") == ResourcePool(gold=15, green=1, blue=2, red=2)

def test_parse_all_resource_types():
    assert parse_resource_string("1GBCAH") == ResourcePool(
        gold=1, green=1, blue=1, red=1, attack=1, energy=1
    )
