---
title: "Day 21: Test Frameworks for Embedded: Unity, CppUTest, Ztest"
date: 2026-07-03
tags: ["til", "hil-testing", "unity", "cpputest", "unit-tests"]
---

## What I Explored Today

I spent the day comparing three unit test frameworks that dominate embedded C/C++ testing: Unity, CppUTest, and Ztest (from Zephyr RTOS). While all three serve the same fundamental purpose—validating that individual functions behave correctly in isolation—they differ significantly in syntax, feature set, and ecosystem integration. I built the same test suite for a simple sensor driver using each framework, then evaluated compile times, memory footprint, and CI integration complexity.

## The Core Concept

Unit testing in embedded systems is fundamentally different from desktop or web testing. On a microcontroller, you cannot simply `printf` debug or run a test suite on the target hardware without careful resource management. The frameworks we use must be lightweight, often running on the host machine (x86/Linux) to avoid flashing cycles, yet still compile with the same toolchain flags as the target binary.

The three frameworks solve this in different ways:

- **Unity** is a pure-C framework designed for minimal footprint. It compiles to ~2-3 kB of ROM and has zero dynamic allocation. It's ideal for running tests directly on a microcontroller with limited RAM.
- **CppUTest** is C++-based but fully supports C code. It provides richer features like mock support, memory leak detection, and test groups. It's the go-to for larger projects where test infrastructure complexity is acceptable.
- **Ztest** is the Zephyr RTOS native test framework. It integrates deeply with the Zephyr build system (CMake/west) and provides hardware abstraction layer (HAL) mocking out of the box. If you're using Zephyr, it's the natural choice.

The key insight: choose your framework based on where you run tests (host vs. target) and how much test infrastructure overhead your project can tolerate.

## Key Commands / Configuration / Code

### Unity Example (C, host-compiled)

```c
// test_sensor.c
#include "unity.h"
#include "sensor_driver.h"

static int16_t mock_adc_value;

void setUp(void) {
    mock_adc_value = 0;
    sensor_init();
}

void tearDown(void) {
    sensor_deinit();
}

void test_sensor_read_returns_correct_temperature(void) {
    // Arrange
    mock_adc_value = 512;  // 1.65V on 12-bit ADC
    set_adc_mock_value(mock_adc_value);
    
    // Act
    int32_t temp = sensor_read_temperature();
    
    // Assert
    TEST_ASSERT_INT32_WITHIN(2, 2500, temp);  // 25.00°C ± 0.02°C
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_sensor_read_returns_correct_temperature);
    return UNITY_END();
}
```

Compile and run:
```bash
gcc -I./unity -I./src test_sensor.c unity.c src/sensor_driver.c -o test_sensor
./test_sensor
```

### CppUTest Example (C++, host-compiled)

```cpp
// test_sensor.cpp
#include "CppUTest/TestHarness.h"
#include "sensor_driver.h"

extern "C" {
    static int16_t mock_adc;
    int16_t __wrap_adc_read(uint8_t channel) {
        return mock_adc;
    }
}

TEST_GROUP(SensorTestGroup)
{
    void setup() override {
        mock_adc = 0;
        sensor_init();
    }
    void teardown() override {
        sensor_deinit();
    }
};

TEST(SensorTestGroup, TemperatureConversion)
{
    mock_adc = 1023;  // 3.3V on 10-bit ADC
    int32_t temp = sensor_read_temperature();
    CHECK_EQUAL(3300, temp);  // 33.00°C
}
```

Build with CMake:
```cmake
find_package(CppUTest REQUIRED)
add_executable(test_sensor test_sensor.cpp)
target_link_libraries(test_sensor CppUTest::CppUTest)
target_link_options(test_sensor PRIVATE -Wl,--wrap=adc_read)
```

### Ztest Example (Zephyr native)

```c
// test_sensor.c
#include <ztest.h>
#include "sensor_driver.h"

/* Ztest automatically handles setUp/tearDown via ztest_test_suite */
static void test_temperature_reading(void)
{
    /* Ztest provides its own assert macros */
    int32_t temp = sensor_read_temperature();
    zassert_true(temp > 0 && temp < 5000,
                 "Temperature out of range: %d", temp);
}

void test_main(void)
{
    ztest_test_suite(sensor_tests,
                     ztest_unit_test(test_temperature_reading));
    ztest_run_test_suite(sensor_tests);
}
```

Run with Zephyr's twister:
```bash
west build -b native_posix tests/sensor/ -t run
```

## Common Pitfalls & Gotchas

1. **Mixing C and C++ linkage silently breaks tests.** When using CppUTest with C code, remember `extern "C"` around your header includes and mocked functions. Forgetting this causes linker errors that look like missing symbols, but actually are name-mangling mismatches.

2. **Unity's `TEST_ASSERT_EQUAL` uses `==` for integers but `strcmp` for strings.** This seems obvious, but I've seen engineers pass `char*` pointers and get false passes because both pointers pointed to the same string literal in read-only memory. Use `TEST_ASSERT_EQUAL_STRING` explicitly.

3. **Ztest's `zassert` macros do not halt test execution by default.** Unlike Unity's `TEST_ASSERT` which aborts the current test, Ztest continues running subsequent assertions. This can lead to cascading failures that obscure the root cause. Use `zassert_true` with a fatal flag or wrap in `TC_PRINT` for debugging.

## Try It Yourself

1. **Port a legacy test to Unity.** Take an existing test that uses ad-hoc `assert()` calls and rewrite it using Unity's `TEST_ASSERT_INT32_WITHIN` and `TEST_ASSERT_EQUAL_STRING` macros. Measure the binary size difference.

2. **Add memory leak detection with CppUTest.** Create a test that intentionally leaks memory (malloc without free). Run it with `--leak-check=full` and observe CppUTest's leak report. Then fix the leak and confirm the test passes cleanly.

3. **Run a Ztest suite on native_posix.** Create a minimal Zephyr application with a single test that exercises a math function (e.g., `sqrt` from math.h). Build and run with `west build -b native_posix -t run`. Verify the test passes in under 100ms.

## Next Up

Tomorrow we dive into **Mocking Hardware in Unit Tests: CMock & FFF**. We'll replace real ADC, GPIO, and UART peripherals with controlled fakes, enabling deterministic testing of error paths and edge cases that are nearly impossible to trigger on real hardware.
