# CMakeLists.txt for NeuralGTO C++ Pruning Module (T4.2c)
# Builds pybind11 extension for fast solver operations

cmake_minimum_required(VERSION 3.18)
project(neural_gto_pruner)

# C++17 standard (for structured bindings, improved over C++14)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Python and pybind11
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

# Include directories
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/..)

# Build the pybind11 extension module
pybind11_add_module(_solver_pruner_cpp solver_cpp/pruner_bindings.cpp)

# Set output directory to poker_gpt/ so Python can import it
set_target_properties(_solver_pruner_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/poker_gpt"
)

# Optimization flags
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_options(_solver_pruner_cpp PRIVATE -O3 -march=native)
endif()

# Installation (optional — for system-wide install)
install(TARGETS _solver_pruner_cpp LIBRARY DESTINATION poker_gpt)
