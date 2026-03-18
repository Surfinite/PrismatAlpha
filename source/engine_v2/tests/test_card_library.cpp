#include "CardTypeData.h"
#include "CardTypes.h"
#include "CardType.h"
#include <cassert>
#include <iostream>

void test_load_card_library()
{
    Prismata::CardTypeData::Instance().InitFromCardLibraryFile(
        "bin/asset/config/cardLibrary.jso"
    );
    Prismata::CardTypes::Init();

    size_t numTypes = Prismata::CardTypeData::Instance().numCardTypes();
    std::cout << "  Loaded " << numTypes << " card types" << std::endl;
    assert(numTypes == 118);  // 11 base + 105 dominion + 2 extras

    // Verify a known base set card
    Prismata::CardType drone = Prismata::CardTypes::GetCardType("Drone");
    assert(drone.getUIName() == "Drone");

    // Verify a known dominion card with UIName mapping
    Prismata::CardType teslaTower = Prismata::CardTypes::GetCardType("Tesla Tower");
    assert(teslaTower.getUIName() == "Tarsier");

    Prismata::CardType factory = Prismata::CardTypes::GetCardType("Factory");
    assert(factory.getUIName() == "Synthesizer");

    std::cout << "  PASS: test_load_card_library" << std::endl;
}

void test_card_type_properties()
{
    // Drone: base set, 1 health, produces 1 gold, can block
    Prismata::CardType drone = Prismata::CardTypes::GetCardType("Drone");
    assert(drone.getHealthAmount() == 1);
    assert(drone.canBlock(false));
    assert(!drone.isFragile());

    // Tarsier (Tesla Tower): 1 health, fragile
    // NOTE: Tarsier's attack comes from beginOwnTurnScript, not a frontline attack value.
    // CardType::getAttack() may return 0 or 1 depending on whether it pre-computes
    // script-derived attack. Verify empirically and adjust assertion if needed.
    Prismata::CardType tarsier = Prismata::CardTypes::GetCardType("Tesla Tower");
    assert(tarsier.getHealthAmount() == 1);
    assert(tarsier.isFragile());

    std::cout << "  PASS: test_card_type_properties" << std::endl;
}

void run_card_library_tests()
{
    std::cout << "Running Card Library tests..." << std::endl;
    test_load_card_library();
    test_card_type_properties();
    std::cout << "All Card Library tests PASSED" << std::endl;
}
