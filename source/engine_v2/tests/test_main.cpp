#include <iostream>

extern void run_resource_tests();

int main()
{
    run_resource_tests();
    std::cout << "\nAll tests PASSED" << std::endl;
    return 0;
}
