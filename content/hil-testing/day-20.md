---
title: "Day 20: Why HIL Testing: Firmware Testing Pyramid & Hardware Gap"
date: 2026-07-02
tags: ["til", "hil-testing", "hil", "testing", "strategy"]
---

## What I Explored Today

Today I stepped back from wiring and test harnesses to ask a fundamental question: *Why do we even need HIL testing?* After all, we have unit tests, integration tests, and software-in-the-loop (SIL) simulations. I spent the day mapping the firmware testing pyramid against real-world embedded projects and discovered the "hardware gap"—the dangerous blind spot between pure software tests and the physical system. Understanding this gap is the foundation for every HIL decision we'll make in this series.

## The Core Concept

The classic software testing pyramid (unit → integration → system → acceptance) is a great starting point, but it fails embedded systems in a critical way: it assumes the hardware platform is a perfect, deterministic abstraction. In firmware, the hardware is not a platform—it's an active participant with non-ideal behavior.

Consider this: a unit test can verify that your PID controller computes the correct output given a perfect sensor reading. But what happens when that sensor has 50mV of ripple, a 2ms latency, and occasional dropouts? The software logic is correct, but the *system* fails. That's the hardware gap.

The firmware testing pyramid must account for three layers of hardware interaction:

1. **Pure Software (Unit/Module tests)** – No hardware. Tests logic, state machines, math. Fast, cheap, runs on host.
2. **Software-on-Target (SIL/PIL)** – Code runs on real MCU but with simulated peripherals. Catches compiler issues, stack problems, timing drift.
3. **Hardware-in-the-Loop (HIL)** – Real hardware, real I/O, simulated plant. Catches analog noise, timing jitter, power sequencing, and electrical interactions.

HIL sits at the top because it's the most expensive and slowest, but it's the only layer that closes the hardware gap. Without it, you're shipping code that works on your desk but fails in the field.

## Key Commands / Configuration / Code

Let's make this concrete. Here's a typical firmware module—a thermocouple temperature reader with cold-junction compensation. We'll see how each test layer handles it.

```c
// thermocouple.c - simplified MAX31855 driver
#include "thermocouple.h"
#include "spi.h"

float thermocouple_read_temp(void) {
    uint8_t rx_buf[4] = {0};
    spi_transfer(TC_CS, NULL, rx_buf, 4);  // read 4 bytes
    
    int32_t raw = ((int32_t)rx_buf[0] << 24) |
                  ((int32_t)rx_buf[1] << 16) |
                  ((int32_t)rx_buf[2] << 8)  |
                  ((int32_t)rx_buf[3]);
    
    // Check fault bits (bit 16 = open circuit)
    if (raw & 0x00010000) return -1.0f;  // fault
    
    // Extract 14-bit thermocouple temperature (bits 31-18)
    int16_t tc_raw = (raw >> 18) & 0x3FFF;
    if (tc_raw & 0x2000) tc_raw |= 0xC000;  // sign extend
    return tc_raw * 0.25f;  // 0.25°C per LSB
}
```

**Unit test (pure software, no hardware):**
```c
// test_thermocouple.c
void test_tc_normal_reading(void) {
    // Mock: return 0x1F400000 -> tc_raw=0x007D -> 125 * 0.25 = 31.25°C
    spi_mock_set_rx_buf(0x1F, 0x40, 0x00, 0x00);
    float temp = thermocouple_read_temp();
    TEST_ASSERT_FLOAT_WITHIN(0.01, 31.25, temp);
}

void test_tc_open_circuit(void) {
    // Mock: set fault bit 16
    spi_mock_set_rx_buf(0x00, 0x01, 0x00, 0x00);
    float temp = thermocouple_read_temp();
    TEST_ASSERT_EQUAL_FLOAT(-1.0, temp);
}
```

**HIL test (real hardware, simulated plant):**
```python
# hil_test_thermocouple.py - runs on HIL test system
import pyvisa
import time

def test_thermocouple_accuracy():
    # Configure HIL simulator to output 0.1mV steps (simulating 2.5°C steps)
    hil = pyvisa.ResourceManager().open_resource('TCPIP0::192.168.1.100::inst0::INSTR')
    
    for temp_c in range(0, 100, 10):
        # Set simulator DAC to output thermocouple voltage + cold-junction
        # Type K: 40.0uV/°C, cold junction at 25°C
        voltage_mv = (temp_c - 25) * 0.040  # relative to 25°C CJC
        hil.write(f"SOURCE:VOLTAGE {voltage_mv:.4f}")  # set DAC
        time.sleep(0.05)  # allow ADC settling
        
        # Read actual firmware output via debug UART
        firmware_temp = float(hil.query("READ:UART0"))  # "31.25"
        
        # Check accuracy (expect ±2°C due to noise and quantization)
        assert abs(firmware_temp - temp_c) < 2.0, \
            f"Failed at {temp_c}°C: got {firmware_temp}°C"
    
    hil.close()
```

The unit test catches logic bugs. The HIL test catches analog noise, SPI timing, and CJC drift—things no mock can reproduce.

## Common Pitfalls & Gotchas

**1. Treating HIL as a "bigger integration test"**
I've seen teams write HIL tests that are just integration tests running on real hardware. They verify that SPI transactions complete, but they don't inject analog faults, noise, or timing violations. A proper HIL test must stress the *hardware interface*, not just the software path. If your HIL test doesn't include a failing sensor, a noisy power rail, or an off-spec clock, you're not closing the hardware gap.

**2. Ignoring the plant model fidelity**
Your HIL is only as good as your plant model. I once spent three days debugging a motor controller that passed HIL but failed in the field. The issue? Our plant model used an ideal 12V supply, but the real system had a 0.5V drop during high current draw. The firmware's undervoltage lockout never triggered in HIL. Always model the power supply, cable impedance, and environmental parasitics—at least to first order.

**3. Forgetting that HIL is about timing, not just values**
A common mistake: verifying that a CAN message contains the correct payload, but not measuring *when* it arrives. In a real system, a 2ms delay in a 100Hz control loop can cause instability. Your HIL should timestamp every I/O event and check against real-time constraints. Use the HIL's FPGA or real-time processor to measure latency, not just the firmware's internal timers.

## Try It Yourself

1. **Map your current project to the firmware testing pyramid.** List every test you have (unit, integration, SIL, HIL). For each, note what hardware interactions it *doesn't* cover. Identify one hardware gap—something that could fail in the field but no test catches.

2. **Write a unit test for a simple ADC driver** (e.g., reading a potentiometer). Then write a HIL test that injects a noisy analog signal (use a function generator or HIL analog output) and verify the firmware's filtering algorithm actually works. Measure the noise rejection in dB.

3. **Add a timing assertion to an existing HIL test.** If you have a control loop that runs at 1kHz, add a test that measures the jitter between consecutive loop iterations. Use a logic analyzer or the HIL's digital input to capture the firmware's "heartbeat" GPIO toggle. Assert that jitter stays under 100μs.

## Next Up

Tomorrow we dive into **Test Frameworks for Embedded: Unity, CppUTest, Ztest**. We'll compare the three major C/C++ test frameworks, show how to set up each one for an STM32 project, and discuss when to use a host-based runner vs. on-target execution. Bring your linker scripts.
