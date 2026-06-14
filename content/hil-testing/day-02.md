---
title: "Day 02: Test Frameworks for Embedded: Unity, CppUTest, Ztest"
date: 2026-06-14
tags: ["til", "hil-testing", "unity", "cpputest", "unit-tests"]
---

## What I Explored Today

Today I dug into the three dominant unit test frameworks for embedded C/C++: Unity, CppUTest, and Ztest (Zephyr's native framework). I evaluated each against real constraints—cross-compilation, minimal footprint, and integration with CI pipelines. The goal was to understand not just syntax, but which tool fits which stage of embedded development, from bare-metal firmware to RTOS-based systems.

## The Core Concept

Unit testing on embedded targets is fundamentally different from desktop testing. You can't `printf` your way through a race condition, and you can't rely on a full OS to manage test execution. The frameworks we use must run on the host (for rapid feedback) and on the target (for hardware validation). Each framework solves this differently:

- **Unity** — Pure C, single-file header, designed for resource-constrained targets. No dynamic allocation, no C++ exceptions. Ideal for bare-metal and bootloader code.
- **CppUTest** — C++-based, but tests C code just as well. Provides memory leak detection, mock support via CppUMock, and a test runner that integrates with CTest. Best for complex middleware and driver layers.
- **Ztest** — Built into Zephyr RTOS. Runs natively in Zephyr's test infrastructure, supports multi-threaded tests, and can execute on both host (native_posix) and target hardware. Mandatory for Zephyr-based projects.

The key insight: you don't pick one framework for your entire project. You pick the one that matches the layer you're testing. Unity for HAL-level register writes, CppUTest for protocol stacks, Ztest for RTOS task interactions.

## Key Commands / Configuration / Code

### Unity — Minimal Setup

```c
// test_led_driver.c
#include "unity.h"
#include "led_driver.h"

void setUp(void) {}    // called before each test
void tearDown(void) {} // called after each test

void test_LED_on_sets_pin_high(void) {
    // Arrange
    led_driver_init();
    
    // Act
    led_driver_set(LED_1, true);
    
    // Assert
    TEST_ASSERT_EQUAL_UINT16(0x0001, GPIO_PORT->OUT);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_LED_on_sets_pin_high);
    return UNITY_END();
}
```

Compile and run on host:
```bash
gcc -I unity/src -I. test_led_driver.c led_driver.c unity/src/unity.c -o test_led
./test_led
```

### CppUTest — With Memory Leak Detection

```cpp
// test_ring_buffer.cpp
#include "CppUTest/CommandLineTestRunner.h"
#include "CppUTest/TestHarness.h"
#include "ring_buffer.h"

TEST_GROUP(RingBuffer)
{
    void setup() override {
        rb = ring_buffer_create(16);
    }
    void teardown() override {
        ring_buffer_destroy(rb);  // CppUTest will report if this leaks
    }
    ring_buffer_t* rb;
};

TEST(RingBuffer, WriteAndReadBack)
{
    uint8_t data = 0xAB;
    ring_buffer_write(rb, &data, 1);
    
    uint8_t read_back = 0;
    ring_buffer_read(rb, &read_back, 1);
    
    CHECK_EQUAL(0xAB, read_back);
}

int main(int ac, char** av) {
    return CommandLineTestRunner::RunAllTests(ac, av);
}
```

Build with CMake:
```cmake
find_package(CppUTest REQUIRED)
add_executable(test_ring_buffer test_ring_buffer.cpp)
target_link_libraries(test_ring_buffer CppUTest CppUTestExt)
```

### Ztest — Zephyr Native

```c
// tests/drivers/test_gpio.c
#include <ztest.h>
#include <drivers/gpio.h>

static const struct device *gpio_dev;

static void test_gpio_pin_toggle(void)
{
    int ret;
    
    ret = gpio_pin_configure(gpio_dev, TEST_PIN, GPIO_OUTPUT);
    zassert_true(ret == 0, "GPIO configure failed");
    
    ret = gpio_pin_set(gpio_dev, TEST_PIN, 1);
    zassert_equal(ret, 0, "GPIO set failed");
    
    ret = gpio_pin_get(gpio_dev, TEST_PIN);
    zassert_equal(ret, 1, "Pin not high after set");
}

void test_main(void)
{
    gpio_dev = device_get_binding(TEST_GPIO_DEV);
    zassert_not_null(gpio_dev, "Device not found");
    
    ztest_test_suite(gpio_tests,
        ztest_unit_test(test_gpio_pin_toggle)
    );
    ztest_run_test_suite(gpio_tests);
}
```

Run on host:
```bash
west build -b native_posix tests/drivers/gpio
./build/zephyr/zephyr.exe
```

## Common Pitfalls & Gotchas

1. **Floating-point in Unity** — Unity's `TEST_ASSERT_EQUAL_FLOAT` uses a default epsilon of `1e-6f`, but on Cortex-M0 without hardware FPU, soft-float comparisons can be slow and imprecise. Always use integer comparisons for register-level tests.

2. **CppUTest memory leak detection on embedded targets** — CppUTest's `malloc` override works on Linux/macOS, but on bare-metal targets you must provide your own `malloc` wrapper. Many engineers forget this and get false positives or crashes when running tests on hardware.

3. **Ztest test ordering** — Ztest does NOT guarantee test execution order within a suite. If your tests share global state (e.g., a UART buffer), you'll get intermittent failures. Always use `setup()` and `teardown()` to reset state, or use `ztest_test_suite` with explicit ordering via `ztest_unit_test_setup_teardown`.

## Try It Yourself

1. **Port a legacy function to Unity** — Take a simple CRC-8 calculation from your production code. Write a Unity test that verifies it against known test vectors. Compile and run on your host machine. Verify the test fails when you introduce an off-by-one error.

2. **Add CppUTest memory leak detection** — Create a C module that allocates memory but never frees it. Write a CppUTest test that calls your function. Run with `--verbose` and observe the memory leak report. Fix the leak and confirm the test passes cleanly.

3. **Run a Ztest on native_posix** — If you have Zephyr installed, create a minimal test that toggles a GPIO on the simulated `native_posix` board. Use `zassert` macros to verify pin state. Run the test and inspect the output.

## Next Up

Tomorrow I'll tackle **Mocking Hardware in Unit Tests: CMock & FFF** — how to stub out hardware registers, simulate sensor readings, and test error paths without touching real hardware. We'll compare CMock's auto-generated mocks with FFF's lightweight fake function framework, and show a real example mocking an I2C EEPROM driver.
