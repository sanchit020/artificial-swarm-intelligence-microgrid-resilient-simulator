cmake_minimum_required(VERSION 3.16)
project(asi_smart_power_grid LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Shared include directory
include_directories(cpp/include)

# Core ASI static library
add_library(asi_core STATIC
    cpp/src/network.cpp
    cpp/src/flow.cpp
    cpp/src/simulation.cpp
    cpp/src/optimizer.cpp
    cpp/src/output.cpp
)
target_include_directories(asi_core PUBLIC cpp/include)

# Solver engine executable
add_executable(asi_engine cpp/src/main.cpp)
target_link_libraries(asi_engine PRIVATE asi_core)

# C++ unit test executable
add_executable(asi_tests cpp/tests/test_main.cpp)
target_link_libraries(asi_tests PRIVATE asi_core)

if(MSVC)
  target_compile_options(asi_core PRIVATE /W4 /permissive-)
  target_compile_options(asi_engine PRIVATE /W4 /permissive-)
  target_compile_options(asi_tests PRIVATE /W4 /permissive-)
else()
  target_compile_options(asi_core PRIVATE -Wall -Wextra -Wpedantic)
  target_compile_options(asi_engine PRIVATE -Wall -Wextra -Wpedantic)
  target_compile_options(asi_tests PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()
add_test(NAME asi_unit_tests COMMAND asi_tests)
