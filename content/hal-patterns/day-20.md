---
title: "Day 20: Testing HALs: Mocking Hardware with Fakes & Hardware-in-the-Loop"
date: 2026-07-20
tags: ["til", "hal-patterns", "hal-testing", "mocking"]
---

## What I Explored Today

Today I tackled the hardest part of HAL development: testing. You can't run production code on a dev board in CI, and you can't trust untested abstractions. I spent the day implementing a dual-layer test strategy: **link-time fakes** for unit tests (fast, deterministic, runs on any host) and **hardware-in-the-loop (HIL)** for integration validation (real pins, real timing). The key insight: your HAL interface must be designed for testability from day one, or you'll end up with untestable spaghetti that only works on the bench.

## The Core Concept

A HAL is a contract between application code and silicon. Testing that contract requires two complementary approaches:

1. **Mocking/Faking** — Replace the real hardware driver with a software simulation that implements the same API. This lets you test application logic, error handling, and edge cases without touching a single GPIO pin. Fakes run in milliseconds on your laptop.

2. **Hardware-in-the-Loop** — Run the real HAL driver against actual hardware, but with a test harness that can inject faults, measure timing, and verify state. This catches silicon errata, timing violations, and pin configuration bugs that fakes can't simulate.

The trick is making the HAL interface *injectable*. If your HAL functions are hardcoded calls to vendor SDKs, you can't fake them. If they're function pointers or weak symbols, you can swap implementations at link time.

## Key Commands / Configuration / Code

### 1. Designing an Injectable HAL (C Example)

```c
// hal_gpio.h — The contract
typedef struct {
    void (*set_pin)(uint8_t pin, bool state);
    bool (*get_pin)(uint8_t pin);
    int (*init)(void);
} hal_gpio_t;

// Default implementation (real hardware)
extern hal_gpio_t hal_gpio_default;

// Application code uses the interface, not the hardware directly
void led_blink(hal_gpio_t *gpio, uint8_t pin, uint32_t ms) {
    gpio->set_pin(pin, true);
    delay_ms(ms);
    gpio->set_pin(pin, false);
}
```

### 2. Building a Fake for Unit Testing

```c
// test_fakes/hal_gpio_fake.c
#include "hal_gpio.h"

static bool fake_pin_state[256] = {0};
static int fake_init_called = 0;
static int fake_set_calls = 0;

static void fake_set_pin(uint8_t pin, bool state) {
    fake_pin_state[pin] = state;
    fake_set_calls++;
}

static bool fake_get_pin(uint8_t pin) {
    return fake_pin_state[pin];
}

static int fake_init(void) {
    fake_init_called = 1;
    memset(fake_pin_state, 0, sizeof(fake_pin_state));
    return 0; // Always succeed
}

hal_gpio_t hal_gpio_default = {
    .set_pin = fake_set_pin,
    .get_pin = fake_get_pin,
    .init = fake_init
};

// Test helpers (exposed in test_fakes/hal_gpio_fake.h)
int fake_gpio_get_init_count(void) { return fake_init_called; }
bool fake_gpio_get_pin_state(uint8_t pin) { return fake_pin_state[pin]; }
void fake_gpio_reset(void) { 
    fake_init_called = 0; 
    fake_set_calls = 0;
    memset(fake_pin_state, 0, sizeof(fake_pin_state)); 
}
```

### 3. Unit Test with Ceedling/Unity

```c
// test/test_led_blink.c
#include "unity.h"
#include "hal_gpio.h"
#include "test_fakes/hal_gpio_fake.h"

void setUp(void) {
    fake_gpio_reset();
}

void test_led_blink_sets_pin_high_then_low(void) {
    hal_gpio_t *gpio = &hal_gpio_default;
    
    led_blink(gpio, 5, 100);
    
    TEST_ASSERT_TRUE(fake_gpio_get_pin_state(5)); // High after first set
    // In a real test, you'd mock delay_ms too, then check low
}
```

### 4. Hardware-in-the-Loop with Pytest + STM32CubeProgrammer

```python
# test_hil/test_gpio_output.py
import serial
import time
import subprocess

def test_gpio_toggle_accuracy():
    """Verify GPIO toggle meets timing spec using logic analyzer"""
    # Flash test firmware
    subprocess.run(["STM32_Programmer_CLI", "-c", "port=SWD", 
                    "-w", "build/hil_test.bin", "0x08000000", 
                    "-rst"], check=True)
    
    # Open UART backchannel from DUT
    ser = serial.Serial('/dev/ttyACM0', 115200, timeout=5)
    
    # Send command to start 1kHz toggle on PA0
    ser.write(b"TOGGLE PA0 1000\n")
    time.sleep(0.1)
    
    # Read back measured frequency from DUT's timer capture
    response = ser.readline().decode().strip()
    freq = float(response.split(':')[1])
    
    # Assert within 1% tolerance
    assert abs(freq - 1000.0) / 1000.0 < 0.01, f"Freq {freq} out of spec"
```

## Common Pitfalls & Gotchas

1. **Fake Drift** — Your fake GPIO never fails, never glitches, and always responds instantly. Real hardware has setup/hold times, drive strength limits, and pull-up/pull-down quirks. Always validate your fakes against HIL results at least once per release. I've seen fakes pass for months while the real hardware was stuck in a brownout reset loop.

2. **Link-Time Symbol Conflicts** — If your HAL uses weak symbols (GCC `__attribute__((weak))`) for default implementations, be careful with test file ordering. The linker picks the first strong symbol it finds. If you link `hal_gpio_real.o` before `hal_gpio_fake.o`, you'll get the real hardware driver in your unit test. Use explicit `--wrap` flags or separate build configurations.

3. **HIL Test Flakiness** — Hardware tests fail for non-software reasons: bad cables, power supply noise, probe capacitance loading a pin. Always add retry logic with exponential backoff, and log environmental data (voltage, temperature) alongside test results. A failing HIL test should trigger a hardware review, not just a code fix.

## Try It Yourself

1. **Extract a function-pointer HAL** — Take your existing GPIO driver (any vendor) and refactor it to use a struct of function pointers. Write a fake that logs every call with timestamps. Verify your application logic still works with the fake.

2. **Build a HIL test for PWM** — Write a test firmware that outputs a 1kHz PWM on a timer channel. Use a logic analyzer or oscilloscope (or even a $10 Saleae clone) to measure actual frequency and duty cycle. Automate the measurement via Python and assert against your HAL's spec sheet.

3. **Inject a fault** — Modify your fake to simulate a hardware fault (e.g., `set_pin` returns an error after 100 calls). Write a unit test that verifies your application handles the fault correctly (retries, logs, resets). This catches error-handling bugs that only appear after months of runtime.

## Next Up

Tomorrow: **Interrupt Abstraction: ISR Registration Patterns Across Vendors**. We'll look at how STM32's NVIC, NXP's LPC, and Microchip's PIC handle interrupt registration, and build a unified ISR manager that works across all three without sacrificing latency or priority control.
