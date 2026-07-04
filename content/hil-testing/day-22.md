---
title: "Day 22: Mocking Hardware in Unit Tests: CMock & FFF"
date: 2026-07-04
tags: ["til", "hil-testing", "cmock", "fff", "mocking"]
---

## What I Explored Today

Today I dug into the two most popular C mocking frameworks for embedded unit testing: CMock (from the ThrowTheSwitch ecosystem) and FFF (Fake Function Framework). Both solve the same fundamental problem—how to test code that talks to hardware without having the hardware present—but they take radically different approaches. I spent the morning fighting with CMock's auto-generation pipeline and the afternoon appreciating FFF's simplicity, and I came away with a clear picture of when to use each.

## The Core Concept

Here's the reality of embedded unit testing: your code calls `HAL_GPIO_WritePin()`, `adc_read()`, or `spi_transfer()`, and those functions talk to registers or peripherals. You can't run that on your development machine. You need *mocks*—fake implementations that record calls, return controlled values, and let you assert on behavior.

The "why" is straightforward: without mocks, you're either skipping unit tests entirely (bad) or running integration tests on hardware (slow, expensive, and fragile). Mocks let you test your logic in isolation, on your laptop, in milliseconds.

The two frameworks I explored today represent different philosophies:

- **CMock** is an *auto-generating* mock framework. You give it a header file, it parses it with Ruby, and spits out a complete mock implementation with strict argument checking, return value control, and call ordering verification. It's powerful but opinionated.

- **FFF** is a *manual* mock framework. You write fake functions yourself (or use its macros to generate them), and it provides a lightweight API for recording calls, setting return values, and checking call counts. It's simpler, faster to compile, and gives you more control.

## Key Commands / Configuration / Code

### CMock Setup (with Unity test framework)

First, install the tools:
```bash
# Install Ruby and the ThrowTheSwitch tools
gem install ceedling
ceedling new my_project
cd my_project
```

CMock works best with Ceedling, which handles the build pipeline. Here's a typical test that mocks a hardware abstraction layer:

```c
// test/test_adc_driver.c
#include "unity.h"
#include "mock_adc_hal.h"  // Auto-generated from adc_hal.h

// The function under test reads ADC and returns scaled value
extern uint32_t read_temperature_sensor(void);

void setUp(void) {}
void tearDown(void) {}

void test_read_temperature_sensor_returns_scaled_value(void)
{
    // Arrange: tell the mock what to return
    adc_hal_read_ExpectAndReturn(ADC_CHANNEL_TEMP, 2048);
    
    // Act
    uint32_t result = read_temperature_sensor();
    
    // Assert
    TEST_ASSERT_EQUAL_UINT32(2500, result);  // 2048 * 1.22 = ~2500mV
}
```

The magic is in `mock_adc_hal.h`—CMock generates it from your header:
```c
// adc_hal.h (the real header)
#ifndef ADC_HAL_H
#define ADC_HAL_H
#include <stdint.h>

#define ADC_CHANNEL_TEMP 3

uint32_t adc_hal_read(uint8_t channel);
#endif
```

Run with:
```bash
ceedling test:all
```

### FFF Setup (standalone, no Ruby needed)

FFF is a single header file. Drop it in your project:

```c
// test/test_gpio_driver.c
#include "unity.h"
#include "fff.h"

// Declare fake functions
DEFINE_FFF_GLOBALS;
FAKE_VOID_FUNC(gpio_set_pin, uint8_t, bool);
FAKE_VALUE_FUNC(bool, gpio_read_pin, uint8_t);

// The function under test
extern void toggle_led(uint8_t pin);

void setUp(void)
{
    // Reset all fakes between tests
    FFF_RESET_HISTORY();
}

void tearDown(void) {}

void test_toggle_led_turns_on_when_off(void)
{
    // Arrange: mock says pin is currently low
    gpio_read_pin_fake.return_val = false;
    
    // Act
    toggle_led(5);
    
    // Assert: should have set pin high
    TEST_ASSERT_EQUAL_UINT8(5, gpio_set_pin_fake.arg0_val);
    TEST_ASSERT_EQUAL(true, gpio_set_pin_fake.arg1_val);
    TEST_ASSERT_EQUAL(1, gpio_set_pin_fake.call_count);
}
```

To link your code against the fakes instead of real hardware, you compile like this:
```bash
gcc -I./test -I./src \
    test/test_gpio_driver.c \
    src/gpio_driver.c \
    -o test_runner
./test_runner
```

## Common Pitfalls & Gotchas

**1. CMock's strict argument matching will surprise you.** If your function passes a pointer to a struct, CMock checks every byte by default. This is great for catching bugs, but it also means you need to set up expectations for *every* call, in order. Miss one, and the test fails with a cryptic "Expectation mismatch" error. Solution: use `_Ignore` variants (e.g., `adc_hal_read_ExpectAnyArgsAndReturn`) for calls you don't care about.

**2. FFF doesn't handle call ordering by default.** If your code calls `gpio_set_pin(5, true)` then `gpio_set_pin(6, false)`, FFF records both calls but doesn't enforce order. You can check `gpio_set_pin_fake.arg0_history[0]` and `arg0_history[1]` manually, but it's easy to forget. Solution: always check `call_count` and history arrays in order-dependent tests.

**3. Both frameworks struggle with static functions.** If your hardware abstraction functions are `static` (common in embedded code for encapsulation), neither CMock nor FFF can mock them directly. You'll need to either make them non-static for testing (ugly but pragmatic) or use linker-level mocking (wrap the symbol with `--wrap` in GCC).

## Try It Yourself

1. **Port a legacy module to FFF.** Take a function that calls `HAL_Delay()` and `HAL_GPIO_WritePin()` directly. Extract those calls into a hardware abstraction layer, then write unit tests using FFF that verify timing and pin states without real hardware.

2. **Set up CMock with Ceedling on a new project.** Create a simple `sensor_hal.h` with three functions (`init`, `read`, `deinit`). Generate the mock, then write a test that verifies `init` is called before `read` and `deinit` is called exactly once.

3. **Compare compile times.** Build a test suite with 10 mocked functions using CMock, then build the same tests with FFF. Time both. You'll likely find FFF compiles 5-10x faster—a real concern when you have hundreds of unit tests in CI.

## Next Up

Tomorrow: **Host-Based Testing: Running Firmware Tests on Linux**. We'll take the mocks we built today and run them in a full CI pipeline on a Linux host, covering cross-compilation tricks, linker scripts for testing, and how to simulate peripheral registers with memory-mapped structs.
