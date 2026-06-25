---
title: "Day 13: CMake & CTest: Unified Build & Test System"
date: 2026-06-25
tags: ["til", "hil-testing", "cmake", "ctest"]
---

## What I Explored Today

Today I unified our HIL test rig's build and test orchestration under a single CMake + CTest pipeline. Previously, we had a fragmented setup: a Makefile for firmware compilation, a separate Python script to run hardware tests, and manual test-result parsing. By moving everything into CMake's `enable_testing()` and `add_test()` framework, we now get a single `cmake --build . && ctest` command that compiles the firmware, flashes the target, runs the HIL test suite, and reports pass/fail with standardized output. This is a game-changer for CI reproducibility.

## The Core Concept

CMake is the de facto build-system generator for embedded C/C++ projects, but most teams stop at `add_executable()`. The hidden superpower is **CTest**, CMake's built-in test driver. CTest doesn't care what language your tests are written in—it just runs commands, captures exit codes, and aggregates results. For HIL testing, this means you can define tests that:

- Compile and flash firmware to the target (via OpenOCD or J-Link Commander)
- Execute a Python test script that talks to the DUT over UART or CAN
- Run a native unit test binary on the host (simulating hardware with mocks)
- Parse log files for expected patterns

The key insight: **CTest treats every test as a black-box command**. You get parallel test execution (`-j`), resource allocation (test fixtures), and JUnit XML output for CI dashboards—all without writing a single line of custom test harness code.

## Key Commands / Configuration / Code

### 1. Minimal CMakeLists.txt with CTest Integration

```cmake
cmake_minimum_required(VERSION 3.20)
project(hil-rig VERSION 1.0.0 LANGUAGES C CXX)

# Enable CTest (must be before any add_test calls)
enable_testing()

# --- Firmware target ---
add_executable(firmware.elf
    src/main.c
    src/adc.c
    src/can_bus.c
)
target_include_directories(firmware.elf PRIVATE inc)
target_link_options(firmware.elf PRIVATE -Tlinker.ld)

# --- Custom command to flash via OpenOCD ---
add_custom_target(flash
    COMMAND openocd -f board/stm32f4discovery.cfg -c "program firmware.elf verify reset exit"
    DEPENDS firmware.elf
    COMMENT "Flashing firmware to target"
)

# --- HIL Test: Check CAN bus connectivity ---
add_test(
    NAME hil_can_connectivity
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/hil/test_can_connect.py
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)

# --- HIL Test: Validate ADC reading within tolerance ---
add_test(
    NAME hil_adc_accuracy
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/hil/test_adc_accuracy.py --tolerance 0.02
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)

# --- Native unit test (no hardware required) ---
add_executable(test_adc_logic tests/unit/test_adc_logic.c src/adc.c)
target_link_libraries(test_adc_logic PRIVATE cmocka)
add_test(NAME unit_adc_logic COMMAND test_adc_logic)
```

### 2. Test Fixtures for Hardware Setup/Teardown

CTest supports `FIXTURES_SETUP` and `FIXTURES_CLEANUP` to handle hardware power cycling or flashing:

```cmake
# Fixture: flash the board before any HIL test
add_test(
    NAME flash_fixture
    COMMAND cmake --build . --target flash
)
set_tests_properties(flash_fixture PROPERTIES FIXTURES_SETUP hil_rig)

# HIL tests depend on the fixture
add_test(NAME hil_can_connectivity COMMAND python3 test_can_connect.py)
set_tests_properties(hil_can_connectivity PROPERTIES FIXTURES_REQUIRED hil_rig)

# Cleanup: power off the rig
add_test(
    NAME power_off_fixture
    COMMAND python3 ${CMAKE_SOURCE_DIR}/tests/hil/power_off.py
)
set_tests_properties(power_off_fixture PROPERTIES FIXTURES_CLEANUP hil_rig)
```

### 3. Running the Full Pipeline

```bash
# Configure (one-time)
cmake -B build -DCMAKE_BUILD_TYPE=Debug

# Build firmware + tests
cmake --build build -j4

# Run all tests (builds are already done)
cd build && ctest --output-on-failure -j2

# Run only HIL tests (filter by name)
ctest -R "hil_" --output-on-failure

# Generate JUnit XML for CI
ctest --output-junit test_results.xml
```

### 4. Custom Test Runner for Embedded-Specific Needs

Sometimes you need to retry flaky hardware tests. Wrap the command in a shell script:

```bash
#!/bin/bash
# tests/hil/retry_wrapper.sh
MAX_RETRIES=3
for i in $(seq 1 $MAX_RETRIES); do
    if "$@"; then
        exit 0
    fi
    echo "Test failed (attempt $i/$MAX_RETRIES). Retrying..."
    sleep 2
done
exit 1
```

Then in CMakeLists.txt:
```cmake
add_test(NAME hil_can_connectivity
    COMMAND ${CMAKE_SOURCE_DIR}/tests/hil/retry_wrapper.sh
            python3 ${CMAKE_SOURCE_DIR}/tests/hil/test_can_connect.py
)
```

## Common Pitfalls & Gotchas

1. **CTest doesn't rebuild automatically.** `ctest` runs tests, but it does not invoke the build system. Always run `cmake --build .` first, or use `ctest --build-and-test` (less common). In CI, separate the build and test steps explicitly.

2. **Fixture ordering is fragile.** If your `FIXTURES_SETUP` test fails, CTest marks all dependent tests as `Not Run`—it does not automatically retry. For flaky hardware, wrap the fixture command in a retry loop (as shown above) or use `--repeat-until-fail` during debugging.

3. **Working directory matters.** Tests run from the build directory by default. If your Python scripts use relative paths for config files or logs, set `WORKING_DIRECTORY` explicitly to `${CMAKE_SOURCE_DIR}` or use absolute paths in the test command.

4. **Cross-compilation toolchain detection.** If you use a toolchain file for ARM/GCC, ensure `enable_testing()` is called *after* the toolchain is loaded. Otherwise, CTest may try to run ARM binaries on your x86 host and fail silently.

## Try It Yourself

1. **Add a CTest fixture for your board's power cycle.** Create a Python script that toggles a relay via GPIO, then define a `FIXTURES_SETUP` test that calls it. Verify that dependent HIL tests only run after the fixture passes.

2. **Parallelize your HIL tests.** If you have multiple identical test rigs, use `ctest -j4` and add `RESOURCE_LOCK` properties to prevent two tests from accessing the same UART port simultaneously.

3. **Integrate with your CI.** Add a step to your GitLab/Jenkins pipeline that runs `ctest --output-junit results.xml` and configure the CI to parse the JUnit report for pass/fail visualization.

## Next Up

Tomorrow, we dive into **Code Coverage for Embedded: gcov, lcov & Gcovr**—how to instrument your firmware for statement and branch coverage, run tests on the target (or in QEMU), and generate HTML reports that show exactly which lines of your ADC driver never executed.
