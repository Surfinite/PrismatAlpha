cmake_minimum_required(VERSION 3.16)
project(PrismataAI LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include paths — engine_v2 headers resolve here (not source/engine/)
include_directories(
    ${CMAKE_SOURCE_DIR}/source/engine_v2
    ${CMAKE_SOURCE_DIR}/source/ai
    ${CMAKE_SOURCE_DIR}/source/testing
    ${CMAKE_SOURCE_DIR}/source
)

# Engine V2 sources — CONFIGURE_DEPENDS so cmake re-globs when files are added
file(GLOB ENGINE_V2_SOURCES CONFIGURE_DEPENDS "source/engine_v2/*.cpp")

# Static library to avoid compiling engine_v2 twice
add_library(engine_v2 STATIC ${ENGINE_V2_SOURCES})
target_compile_definitions(engine_v2 PRIVATE
    $<$<CONFIG:Debug>:PRISMATA_ASSERT_ALL>
)

# Test sources
file(GLOB TEST_SOURCES CONFIGURE_DEPENDS "source/engine_v2/tests/*.cpp")

# Engine V2 test executable
add_executable(prismata_engine_v2_tests ${TEST_SOURCES})
target_link_libraries(prismata_engine_v2_tests engine_v2)

# AI sources
file(GLOB AI_SOURCES CONFIGURE_DEPENDS "source/ai/*.cpp")

# Testing sources (tournament runner, --suggest CLI)
file(GLOB TESTING_SOURCES CONFIGURE_DEPENDS "source/testing/*.cpp")

# Full selfplay/tournament executable
add_executable(prismata_selfplay
    ${AI_SOURCES}
    ${TESTING_SOURCES}
)
target_link_libraries(prismata_selfplay engine_v2)
target_compile_definitions(prismata_selfplay PRIVATE
    $<$<CONFIG:Debug>:PRISMATA_ASSERT_ALL>
)
