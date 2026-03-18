#include "Resources.h"
#include <cassert>
#include <iostream>

void test_parse_string()
{
    Prismata::Resources r("6BGGG");
    assert(r.amountOf(Prismata::Resources::Gold) == 6);
    assert(r.amountOf(Prismata::Resources::Blue) == 1);
    assert(r.amountOf(Prismata::Resources::Green) == 3);
    assert(r.amountOf(Prismata::Resources::Energy) == 0);
    assert(r.amountOf(Prismata::Resources::Red) == 0);
    assert(r.amountOf(Prismata::Resources::Attack) == 0);
    std::cout << "  PASS: test_parse_string" << std::endl;
}

void test_has_and_subtract()
{
    Prismata::Resources pool("10GG");
    Prismata::Resources cost("5G");
    assert(pool.has(cost));
    pool.subtract(cost);
    assert(pool.amountOf(Prismata::Resources::Gold) == 5);
    assert(pool.amountOf(Prismata::Resources::Green) == 1);
    assert(pool.has(cost));
    pool.subtract(cost);
    assert(!pool.has(cost));
    std::cout << "  PASS: test_has_and_subtract" << std::endl;
}

void test_add()
{
    Prismata::Resources a("3B");
    Prismata::Resources b("2BH");
    a.add(b);
    assert(a.amountOf(Prismata::Resources::Gold) == 5);
    assert(a.amountOf(Prismata::Resources::Blue) == 2);
    assert(a.amountOf(Prismata::Resources::Energy) == 1);
    std::cout << "  PASS: test_add" << std::endl;
}

void test_empty()
{
    Prismata::Resources empty;
    assert(empty.empty());
    Prismata::Resources notempty("1");
    assert(!notempty.empty());
    std::cout << "  PASS: test_empty" << std::endl;
}

void test_get_string_roundtrip()
{
    Prismata::Resources r("12HBBCGA");
    std::string s = r.getString();
    Prismata::Resources r2(s);
    assert(r == r2);
    std::cout << "  PASS: test_get_string_roundtrip" << std::endl;
}

void run_resource_tests()
{
    std::cout << "Running Resource tests..." << std::endl;
    test_parse_string();
    test_has_and_subtract();
    test_add();
    test_empty();
    test_get_string_roundtrip();
    std::cout << "All Resource tests PASSED" << std::endl;
}
