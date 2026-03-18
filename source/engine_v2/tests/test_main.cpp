#include <iostream>

extern void run_resource_tests();
extern void run_card_library_tests();
extern void run_card_tests();
extern void run_game_state_tests();

int main()
{
    run_resource_tests();
    run_card_library_tests();
    run_card_tests();
    run_game_state_tests();
    std::cout << "\nAll tests PASSED" << std::endl;
    return 0;
}
