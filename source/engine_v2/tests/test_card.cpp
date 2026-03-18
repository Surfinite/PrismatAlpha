#include "Card.h"
#include "CardType.h"
#include "CardTypes.h"
#include "CardTypeData.h"
#include <cassert>
#include <iostream>

using namespace Prismata;

// Helper: card library must already be loaded by test_card_library before this runs.

// Create a ready-to-use Card via CardCreationMethod::Manual
static Card makeCard(const std::string & internalName, PlayerID player = 0)
{
    CardType type = CardTypes::GetCardType(internalName);
    return Card(type, player, CardCreationMethod::Manual, 0, 0);
}

// Create a card under construction
static Card makeBoughtCard(const std::string & internalName, PlayerID player = 0)
{
    CardType type = CardTypes::GetCardType(internalName);
    return Card(type, player, CardCreationMethod::Bought, 0, 0);
}

// ============================================================================
// Test: Card construction and initial state
// ============================================================================
void test_card_construction()
{
    // Drone: has ability (gold production), defaultBlocking=true, health=1
    Card drone = makeCard("Drone");
    assert(!drone.isDead());
    assert(drone.currentHealth() == 1);
    assert(drone.currentChill() == 0);
    assert(drone.getStatus() == CardStatus::Default);
    assert(drone.canBlock());
    assert(drone.canUseAbility());
    assert(!drone.isUnderConstruction());
    assert(!drone.isDelayed());
    assert(!drone.isFrozen());

    // Wall: no ability, defaultBlocking=true, health=3
    Card wall = makeCard("Wall");
    assert(!wall.isDead());
    assert(wall.currentHealth() == 3);
    assert(wall.canBlock());
    assert(!wall.canUseAbility());  // Wall has no ability
    assert(wall.getStatus() == CardStatus::Inert);  // No ability -> Inert via Manual

    // Tesla Tower (Tarsier): fragile, health=1, no ability, no blocking
    Card tarsier = makeCard("Tesla Tower");
    assert(!tarsier.isDead());
    assert(tarsier.currentHealth() == 1);
    assert(tarsier.getType().isFragile());
    assert(!tarsier.canBlock());  // defaultBlocking=false

    // Bought Drone should be under construction
    Card boughtDrone = makeBoughtCard("Drone");
    assert(boughtDrone.isUnderConstruction());
    assert(!boughtDrone.canBlock());
    assert(!boughtDrone.canUseAbility());

    std::cout << "  PASS: test_card_construction" << std::endl;
}

// ============================================================================
// Test: Ability use blocks blocking (the defense-reset fix)
// ============================================================================
void test_ability_use_blocks_blocking()
{
    // Drone: defaultBlocking=true, assignedBlocking=false
    // After using ability, card should NOT be able to block
    Card drone = makeCard("Drone");
    assert(drone.canBlock());
    assert(drone.canUseAbility());

    drone.useAbility();

    // After using ability: status=Assigned, assignedBlocking=false -> canBlock=false
    assert(drone.getStatus() == CardStatus::Assigned);
    assert(!drone.canBlock());
    assert(!drone.canUseAbility());  // Already used

    std::cout << "  PASS: test_ability_use_blocks_blocking" << std::endl;
}

// ============================================================================
// Test: Undo ability restores blocking
// ============================================================================
void test_undo_ability_restores_blocking()
{
    Card drone = makeCard("Drone");
    assert(drone.canBlock());

    drone.useAbility();
    assert(!drone.canBlock());
    assert(drone.getStatus() == CardStatus::Assigned);

    drone.undoUseAbility();
    assert(drone.canBlock());
    assert(drone.getStatus() == CardStatus::Default);
    assert(drone.canUseAbility());

    std::cout << "  PASS: test_undo_ability_restores_blocking" << std::endl;
}

// ============================================================================
// Test: Damage model - fragile cards
// ============================================================================
void test_damage_fragile()
{
    // Conduit: fragile, health=3, no blocking
    Card conduit = makeCard("Conduit");
    assert(conduit.currentHealth() == 3);
    assert(conduit.getType().isFragile());

    // Partial damage: fragile cards lose health directly
    conduit.takeDamage(1, DamageSource::Breach);
    assert(conduit.currentHealth() == 2);
    assert(!conduit.isDead());
    assert(conduit.wasBreached());

    // Lethal damage on fresh fragile card
    Card conduit2 = makeCard("Conduit");
    conduit2.takeDamage(3, DamageSource::Breach);
    assert(conduit2.currentHealth() == 0);
    assert(conduit2.isDead());

    // Over-damage on fragile card: health should not go negative
    Card conduit3 = makeCard("Conduit");
    conduit3.takeDamage(10, DamageSource::Breach);
    assert(conduit3.currentHealth() == 0);
    assert(conduit3.isDead());

    std::cout << "  PASS: test_damage_fragile" << std::endl;
}

// ============================================================================
// Test: Damage model - non-fragile cards
// ============================================================================
void test_damage_non_fragile()
{
    // Wall: non-fragile, health=3
    Card wall = makeCard("Wall");
    assert(wall.currentHealth() == 3);
    assert(!wall.getType().isFragile());

    // Non-fragile cards: takeDamage only kills when amount >= health
    // Health does NOT decrease for non-fragile on partial damage
    wall.takeDamage(2, DamageSource::Block);
    assert(!wall.isDead());
    assert(wall.currentHealth() == 3);  // Health unchanged for non-fragile
    assert(wall.getDamageTaken() == 2);

    // Lethal damage kills non-fragile card
    Card wall2 = makeCard("Wall");
    wall2.takeDamage(3, DamageSource::Block);
    assert(wall2.isDead());

    // Over-damage also kills
    Card wall3 = makeCard("Wall");
    wall3.takeDamage(5, DamageSource::Block);
    assert(wall3.isDead());
    assert(wall3.getDamageTaken() == 3);  // Capped at health

    std::cout << "  PASS: test_damage_non_fragile" << std::endl;
}

// ============================================================================
// Test: Freeze detection
// ============================================================================
void test_freeze_detection()
{
    // Wall: health=3, non-fragile
    Card wall = makeCard("Wall");
    assert(!wall.isFrozen());

    // Apply partial chill: not frozen
    wall.applyChill(2);
    assert(wall.currentChill() == 2);
    assert(!wall.isFrozen());
    assert(wall.canBlock());  // Not yet frozen

    // Apply enough chill to freeze: chill >= health
    wall.applyChill(1);
    assert(wall.currentChill() == 3);
    assert(wall.isFrozen());
    assert(!wall.canBlock());  // Frozen cards cannot block

    // Fragile card freeze: Tesla Tower (Tarsier), health=1
    Card tarsier = makeCard("Tesla Tower");
    // Tarsier doesn't have defaultBlocking, so canBlock is always false
    // But isFrozen should still work
    assert(!tarsier.isFrozen());
    tarsier.applyChill(1);
    assert(tarsier.isFrozen());

    std::cout << "  PASS: test_freeze_detection" << std::endl;
}

// ============================================================================
// Test: beginTurn clears chill for all cards
// ============================================================================
void test_begin_turn_clears_chill()
{
    Card wall = makeCard("Wall");
    wall.applyChill(2);
    assert(wall.currentChill() == 2);
    assert(!wall.isFrozen());

    wall.beginTurn();
    assert(wall.currentChill() == 0);
    assert(!wall.isFrozen());

    // Also verify chill is cleared even for delayed cards
    // Create a Drone, use ability (which may set delay), then beginTurn
    Card drone = makeCard("Drone");
    drone.applyChill(1);
    assert(drone.currentChill() == 1);
    assert(drone.isFrozen());

    drone.beginTurn();
    assert(drone.currentChill() == 0);
    assert(!drone.isFrozen());

    std::cout << "  PASS: test_begin_turn_clears_chill" << std::endl;
}

// ============================================================================
// Test: beginTurn lifecycle - construction, delay, lifespan
// ============================================================================
void test_begin_turn_lifecycle()
{
    // Bought Drone: under construction (buildTime=1)
    Card drone = makeBoughtCard("Drone");
    assert(drone.isUnderConstruction());
    assert(drone.getConstructionTime() == 1);
    assert(!drone.canBlock());
    assert(!drone.canUseAbility());

    // After one beginTurn: construction finished, card becomes ready
    drone.beginTurn();
    assert(!drone.isUnderConstruction());
    assert(drone.getConstructionTime() == 0);
    // After construction finishes, card gets refreshed (status set to Default for ability cards)
    assert(drone.getStatus() == CardStatus::Default);
    assert(drone.canBlock());
    assert(drone.canUseAbility());

    // Tesla Tower has buildTime=2, test two ticks
    Card tarsier = makeBoughtCard("Tesla Tower");
    assert(tarsier.isUnderConstruction());
    assert(tarsier.getConstructionTime() == 2);

    tarsier.beginTurn();
    assert(tarsier.isUnderConstruction());
    assert(tarsier.getConstructionTime() == 1);

    tarsier.beginTurn();
    assert(!tarsier.isUnderConstruction());
    assert(tarsier.getConstructionTime() == 0);

    std::cout << "  PASS: test_begin_turn_lifecycle" << std::endl;
}

// ============================================================================
// Test: beginTurn resets status from Assigned to Default
// ============================================================================
void test_begin_turn_resets_status()
{
    Card drone = makeCard("Drone");
    drone.useAbility();
    assert(drone.getStatus() == CardStatus::Assigned);
    assert(!drone.canBlock());

    // beginTurn should reset status to Default (for ability cards)
    drone.beginTurn();
    assert(drone.getStatus() == CardStatus::Default);
    assert(drone.canBlock());

    std::cout << "  PASS: test_begin_turn_resets_status" << std::endl;
}

// ============================================================================
// Test: Breach calculations
// ============================================================================
void test_breach_calculations()
{
    // Non-fragile Wall: health=3
    Card wall = makeCard("Wall");
    assert(wall.isBreachable());
    assert(!wall.isOverkillable());
    assert(!wall.canBreachFor(0));  // Can't breach for 0
    assert(!wall.canBreachFor(2));  // Not enough damage for non-fragile
    assert(wall.canBreachFor(3));   // Exact health
    assert(wall.canBreachFor(5));   // Over-damage OK

    // Fragile Conduit: health=3
    Card conduit = makeCard("Conduit");
    assert(conduit.isBreachable());
    assert(!conduit.canBreachFor(0));
    assert(conduit.canBreachFor(1));  // Fragile: any damage > 0 works
    assert(conduit.canBreachFor(3));

    // Under construction: not breachable, but overkillable
    Card boughtWall = makeBoughtCard("Wall");
    assert(!boughtWall.isBreachable());
    assert(boughtWall.isOverkillable());
    assert(boughtWall.canOverkillFor(3));
    assert(!boughtWall.canOverkillFor(2));  // Non-fragile needs full health

    // Dead cards: not breachable or overkillable
    Card deadWall = makeCard("Wall");
    deadWall.kill(CauseOfDeath::Breached);
    assert(!deadWall.isBreachable());
    assert(!deadWall.isOverkillable());

    std::cout << "  PASS: test_breach_calculations" << std::endl;
}

// ============================================================================
// Test: canUseAbility checks
// ============================================================================
void test_can_use_ability()
{
    // Drone: has ability, status=Default -> can use
    Card drone = makeCard("Drone");
    assert(drone.canUseAbility());

    // After using: can't use again (status=Assigned)
    drone.useAbility();
    assert(!drone.canUseAbility());

    // Wall: no ability -> can't use
    Card wall = makeCard("Wall");
    assert(!wall.canUseAbility());

    // Under construction: can't use
    Card boughtDrone = makeBoughtCard("Drone");
    assert(!boughtDrone.canUseAbility());

    // Dead card: can't use
    Card deadDrone = makeCard("Drone");
    deadDrone.kill(CauseOfDeath::Breached);
    assert(!deadDrone.canUseAbility());

    // Rhino: has charges (charge=2), ability uses 1 charge
    // After 2 uses it should be out of charges
    CardType rhinoType = CardTypes::GetCardType("Rhino");
    Card rhino(rhinoType, 0, CardCreationMethod::Manual, 0, 0);
    assert(rhino.canUseAbility());
    assert(rhino.getCurrentCharges() == 2);

    rhino.useAbility();
    assert(rhino.getCurrentCharges() == 1);
    // Rhino has status=Assigned after use, so can't use until beginTurn
    assert(!rhino.canUseAbility());

    // After beginTurn, status resets, still has 1 charge
    rhino.beginTurn();
    assert(rhino.canUseAbility());
    assert(rhino.getCurrentCharges() == 1);

    rhino.useAbility();
    assert(rhino.getCurrentCharges() == 0);

    // After beginTurn with 0 charges: can't use ability
    rhino.beginTurn();
    assert(!rhino.canUseAbility());

    std::cout << "  PASS: test_can_use_ability" << std::endl;
}

// ============================================================================
// Test: Chill (canBeChilled)
// ============================================================================
void test_chill()
{
    Card wall = makeCard("Wall");
    assert(wall.canBeChilled());

    // Apply some chill
    wall.applyChill(2);
    assert(wall.canBeChilled());  // Still has room: chill=2 < health=3

    // Apply to freeze
    wall.applyChill(1);
    assert(!wall.canBeChilled());  // Frozen: chill=3 >= health=3

    // Frozen card can't block
    assert(!wall.canBlock());

    // Under-construction card can't be chilled
    Card boughtWall = makeBoughtCard("Wall");
    assert(!boughtWall.canBeChilled());

    // Dead card can't be chilled
    Card deadWall = makeCard("Wall");
    deadWall.kill(CauseOfDeath::Breached);
    assert(!deadWall.canBeChilled());

    std::cout << "  PASS: test_chill" << std::endl;
}

void run_card_tests()
{
    std::cout << "Running Card tests..." << std::endl;
    test_card_construction();
    test_ability_use_blocks_blocking();
    test_undo_ability_restores_blocking();
    test_damage_fragile();
    test_damage_non_fragile();
    test_freeze_detection();
    test_begin_turn_clears_chill();
    test_begin_turn_lifecycle();
    test_begin_turn_resets_status();
    test_breach_calculations();
    test_can_use_ability();
    test_chill();
    std::cout << "All Card tests PASSED" << std::endl;
}
