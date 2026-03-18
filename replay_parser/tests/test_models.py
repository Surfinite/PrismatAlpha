from replay_parser.models import ResourcePool, CardDef, UnitInstance, Action, Turn, ReplayData

def test_resource_pool_defaults():
    r = ResourcePool()
    assert r.gold == 0 and r.green == 0 and r.blue == 0
    assert r.red == 0 and r.energy == 0 and r.attack == 0

def test_resource_pool_add():
    a = ResourcePool(gold=3, green=1)
    b = ResourcePool(gold=2, blue=1)
    c = a + b
    assert c.gold == 5 and c.green == 1 and c.blue == 1

def test_resource_pool_can_afford():
    pool = ResourcePool(gold=6, green=2, blue=1)
    cost = ResourcePool(gold=4, green=1)
    assert pool.can_afford(cost)
    expensive = ResourcePool(gold=10)
    assert not pool.can_afford(expensive)

def test_resource_pool_subtract():
    pool = ResourcePool(gold=6, green=2)
    cost = ResourcePool(gold=3, green=1)
    result = pool - cost
    assert result.gold == 3 and result.green == 1

def test_resource_pool_max_affordable():
    pool = ResourcePool(gold=10, blue=3)
    cost = ResourcePool(gold=4, blue=1)
    assert pool.max_affordable(cost) == 2  # 10//4=2, 3//1=3, min=2

def test_card_def_construction():
    cd = CardDef(
        deck_index=5, name="Drone", rarity="trinket",
        buy_cost=ResourcePool(gold=3, energy=1), toughness=1,
        build_time=0, is_base_set=True, default_blocking=True,
        begin_turn_receive=None,
        ability_receive=ResourcePool(gold=1),
        ability_selfsac=False, ability_create=None,
        target_action=None, supply=20
    )
    assert cd.name == "Drone"
    assert cd.supply == 20

def test_unit_instance_construction():
    cd = CardDef(
        deck_index=5, name="Drone", rarity="trinket",
        buy_cost=ResourcePool(gold=3, energy=1), toughness=1,
        build_time=0, is_base_set=True, default_blocking=True,
        begin_turn_receive=None,
        ability_receive=ResourcePool(gold=1),
        ability_selfsac=False, ability_create=None,
        target_action=None, supply=20
    )
    unit = UnitInstance(
        instance_id=0, card_def=cd, owner=0,
        turns_until_ready=0, is_alive=True,
        used_ability_this_turn=False
    )
    assert unit.instance_id == 0
    assert unit.card_def.name == "Drone"
