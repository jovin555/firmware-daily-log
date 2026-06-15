---
title: "Day 03: Mocking Hardware in Unit Tests: CMock & FFF"
date: 2026-06-15
tags: ["til", "hil-testing", "cmock", "fff", "mocking"]
---

## What I Explored Today

Today I dug into the two most popular C mocking frameworks for embedded unit testing: CMock (part of the Unity/CMock/CException ecosystem) and FFF (Fake Function Framework). The goal was to understand how to isolate hardware-dependent code—like GPIO toggles, ADC reads, and UART sends—so we can test the logic *around* the hardware without needing the actual silicon. I built a small thermostat controller test suite using both frameworks to compare ergonomics, setup overhead, and runtime behavior.

## The Core Concept

Embedded firmware has a fundamental testing problem: most of our code talks directly to hardware registers, peripheral drivers, or RTOS APIs. You cannot run `HAL_GPIO_WritePin()` on your laptop. The traditional solution is to compile for the target and run on dev boards, but that kills iteration speed and makes CI/CD nearly impossible.

Mocking solves this by replacing real hardware functions with *test doubles*—functions that record calls, return canned values, and assert expected behavior. The key insight: **you don't need to test the hardware driver itself in unit tests** (that's what hardware-in-the-loop is for). You need to test *your application logic* that uses those drivers.

A good mock framework lets you:
- Verify that your code called the right function with the right arguments
- Control what the hardware function returns (e.g., "ADC read returns 0x3FF")
- Count how many times a function was called
- Assert call order when that matters

CMock generates mocks automatically from header files. FFF requires you to declare fakes manually but gives you more control and zero code generation step. Both are battle-tested in production embedded projects.

## Key Commands / Configuration / Code

### Setup with CMock (Unity-based)

First, install Ruby (CMock is a Ruby script that generates C mocks). Then create a `CMock.yml` config:

```yaml
# cmock.yml
:cmock:
  :mock_prefix: mock_
  :includes:
    - "unity.h"
  :includes_h_pre_orig_header:
    - "stdint.h"
  :treat_as:
    uint8_t:  "HEX8"
    uint16_t: "HEX16"
  :when_ptr:
    :compare: smart
```

Generate mocks from your hardware abstraction header:

```bash
# Generate mock for a simple GPIO driver header
ruby -I /path/to/cmock/lib /path/to/cmock/lib/cmock.rb \
  --config cmock.yml \
  --mock_path ./mocks \
  ./inc/gpio_driver.h
```

This creates `mocks/mock_gpio_driver.c` and `.h`. Now write a test:

```c
// test_thermostat.c
#include "unity.h"
#include "mock_gpio_driver.h"  // CMock-generated mock
#include "thermostat.h"        // Unit under test

void setUp(void) {}
void tearDown(void) {}

void test_heater_turns_on_when_temp_below_threshold(void) {
    // Arrange: tell the mock what to return
    adc_read_ExpectAndReturn(ADC_CHANNEL_TEMP, 1800);  // 18.00°C
    gpio_write_Expect(GPIO_HEATER, GPIO_HIGH);         // Expect call

    // Act
    thermostat_update();

    // Assert: Unity passes if all expectations met
}
```

### Setup with FFF (Header-only, no code generation)

FFF is a single header file. Declare fakes inline:

```c
// test_thermostat_fff.c
#include "unity.h"
#include "fff.h"
#include "thermostat.h"

// Declare fakes for hardware functions
FAKE_VALUE_FUNC(uint16_t, adc_read, uint8_t);
FAKE_VOID_FUNC(gpio_write, uint8_t, uint8_t);

void setUp(void) {
    RESET_FAKE(adc_read);
    RESET_FAKE(gpio_write);
    FFF_RESET_HISTORY();
}

void tearDown(void) {}

void test_heater_turns_on_when_temp_below_threshold(void) {
    // Arrange
    adc_read_fake.return_val = 1800;  // 18.00°C

    // Act
    thermostat_update();

    // Assert
    TEST_ASSERT_EQUAL(1, gpio_write_fake.call_count);
    TEST_ASSERT_EQUAL(GPIO_HEATER, gpio_write_fake.arg0_val);
    TEST_ASSERT_EQUAL(GPIO_HIGH, gpio_write_fake.arg1_val);
}
```

### The Unit Under Test (thermostat.c)

```c
#include "gpio_driver.h"
#include "adc_driver.h"

#define TEMP_THRESHOLD 2000  // 20.00°C in millivolts

void thermostat_update(void) {
    uint16_t temp_mv = adc_read(ADC_CHANNEL_TEMP);
    if (temp_mv < TEMP_THRESHOLD) {
        gpio_write(GPIO_HEATER, GPIO_HIGH);
    } else {
        gpio_write(GPIO_HEATER, GPIO_LOW);
    }
}
```

### Build and Run (CMock example with GCC)

```makefile
# Makefile snippet
CFLAGS = -I./inc -I./mocks -I/usr/local/include
TEST_SRC = test_thermostat.c ../src/thermostat.c mocks/mock_gpio_driver.c mocks/mock_adc_driver.c

test: $(TEST_SRC)
	gcc $(CFLAGS) -o test_runner $(TEST_SRC) -lunity -lcmock
	./test_runner
```

## Common Pitfalls & Gotchas

### 1. Forgetting to Reset Fakes Between Tests
FFF fakes retain state across test cases. If you don't call `RESET_FAKE()` in `setUp()`, call counts and return values leak between tests. This causes the most confusing failures—tests pass in isolation but fail in a suite.

### 2. CMock's Strict Argument Matching by Default
CMock expects exact pointer addresses by default. If your code passes a stack-allocated buffer, the mock will fail because the address changes each call. Use `:when_ptr :compare :smart` in your config to enable data comparison instead of address comparison, or use `ExpectWithArray` variants.

### 3. Mocking Functions You Don't Own
Never mock standard library functions (malloc, printf) or RTOS primitives—that way lies madness. Instead, wrap them in your own abstraction layer (e.g., `my_malloc`, `os_delay_ms`) and mock those. This keeps your tests maintainable and your production code clean.

## Try It Yourself

1. **Wrap a HAL function**: Take a `HAL_GPIO_TogglePin()` call in your existing code, wrap it in a thin `board_led_toggle()` function, and write a test using FFF that verifies it's called exactly 3 times when a button is pressed 3 times.

2. **Stub an ADC with CMock**: Generate a mock for a header that declares `uint16_t adc_read(uint8_t channel)`. Write a test that verifies your filter function calls `adc_read` with the correct channel and processes the returned value correctly.

3. **Test error handling**: Create a mock that returns an error code (e.g., `-1` from a sensor read). Write a test that verifies your code enters the error recovery path (calls `system_reset()` or sets an error flag) when the mock returns the error.

## Next Up

Tomorrow we move from mocking to **host-based testing**: compiling your firmware for Linux to run integration tests at native speed. We'll cover linker tricks, platform abstraction layers, and how to run your entire sensor fusion stack on a developer laptop without a single piece of real hardware.
