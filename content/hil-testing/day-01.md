---
title: "Day 01: Why HIL Testing: Firmware Testing Pyramid & Hardware Gap"
date: 2026-06-13
tags: ["til", "hil-testing", "hil", "testing", "strategy"]
---

## What I Explored Today

I spent the day mapping out our firmware testing strategy and realized we have a massive blind spot: we test software in isolation, but the moment it touches real hardware—GPIOs, ADCs, CAN transceivers—everything breaks. I dove into the firmware testing pyramid and the concept of the "hardware gap" to understand where Hardware-in-the-Loop (HIL) testing fits. The takeaway: without HIL, you're flying blind on the boundary between software and physics.

## The Core Concept

Most embedded teams know the classic test pyramid: unit tests at the bottom, integration tests in the middle, end-to-end (E2E) tests at the top. For firmware, that pyramid has a critical flaw—it assumes the hardware abstraction layer (HAL) is perfect. It never is.

The **hardware gap** is the disconnect between simulated/mocked hardware behavior and real silicon. A unit test might mock a GPIO pin to return `HIGH` when read, but the real pin might glitch on power-up, have pull-up resistor conflicts, or suffer from timing violations. These are not software bugs—they are system-level interactions that only appear when firmware runs on actual hardware.

HIL testing bridges this gap. In a HIL setup, you replace the physical plant (motors, sensors, actuators) with a real-time simulator that electrically mimics them. Your firmware runs on the real target microcontroller, connected to the simulator via actual wiring. The simulator injects faults, edge cases, and timing scenarios that no unit test can reproduce.

The firmware testing pyramid with HIL looks like this:
- **Unit tests** (fast, mock everything): Verify logic, state machines, algorithms.
- **Integration tests** (on target, no plant): Verify HAL drivers, interrupt handlers, RTOS scheduling.
- **HIL tests** (on target, with simulated plant): Verify closed-loop control, fault responses, timing constraints.
- **Field tests** (real hardware, real environment): Final validation.

Without HIL, you're essentially doing integration tests in the dark. You might verify that a CAN message is formatted correctly, but you won't know if the transceiver's dominant/recessive bit timing is off until the board is in a vehicle.

## Key Commands / Configuration / Code

Let's look at a concrete example. Suppose you're testing a PID controller for a DC motor. Your unit test might look like this (using CppUTest):

```cpp
// test_pid_controller.cpp
#include "CppUTest/TestHarness.h"
#include "pid_controller.h"

TEST_GROUP(PIDController)
{
    pid_controller_t pid;
    void setup() override {
        pid_init(&pid, 1.0, 0.1, 0.05, 100.0); // Kp, Ki, Kd, dt_ms
    }
};

TEST(PIDController, StepResponse)
{
    float output = pid_update(&pid, 100.0, 0.0); // setpoint=100, feedback=0
    // This only tests math, not hardware timing
    CHECK(output > 0);
}
```

Now, the HIL test equivalent (using a real-time simulator like Typhoon HIL or Speedgoat):

```python
# hil_test_pid.py (runs on HIL simulator host)
import hil_api
import time

# Configure HIL simulator
sim = hil_api.Simulator('motor_plant_model.slx')
sim.set_parameter('motor_inertia', 0.01)   # kg*m^2
sim.set_parameter('motor_resistance', 0.5) # ohms

# Connect to target via JTAG/SWD
debugger = hil_api.Debugger('stlink')
target = debugger.connect('stm32f407')

# Inject step command
target.write_variable('setpoint_rpm', 1000)
time.sleep(0.1)  # Let controller settle

# Read actual motor current from simulator
actual_current = sim.read_signal('motor_current_A')
assert actual_current < 2.0, "Overcurrent fault not handled!"

# Inject a fault: short circuit
sim.inject_fault('motor_phase_A', 'short_to_ground')
time.sleep(0.05)

# Verify firmware enters fault state
fault_flag = target.read_variable('fault_active')
assert fault_flag == 1, "Fault not detected by firmware!"
```

The key difference: the HIL test exercises the real ADC sampling, PWM generation, and interrupt latency of the target MCU. The unit test only checks math.

## Common Pitfalls & Gotchas

1. **Assuming HIL replaces all other testing.** It doesn't. HIL is slow (minutes per test) and expensive (simulator hardware costs $10k+). You still need fast unit tests for quick feedback. I've seen teams write 500 HIL tests and then wonder why CI takes 4 hours. Keep the pyramid balanced.

2. **Ignoring timing fidelity in the plant model.** Your HIL simulator must run the plant model in real-time (typically 10-100 µs timestep). If your model is too complex and misses the real-time deadline, the simulator will inject timing jitter that doesn't exist in the real system. Always verify the simulator's execution time with a scope or built-in profiler.

3. **Forgetting about electrical compatibility.** HIL simulators output analog voltages (0-10V, ±10V) and digital signals (3.3V, 5V logic). If your target board expects a 12V sensor signal, you need signal conditioning. I once fried a simulator channel because I forgot the target's ADC input was 5V-tolerant but the simulator output was 3.3V. Use optocouplers or level shifters.

## Try It Yourself

1. **Audit your current test pyramid.** List every test you have and categorize it: unit, integration (on target), HIL, or field. Calculate the ratio. If you have zero HIL tests, pick one critical control loop (e.g., motor speed, heater temperature) and write a single HIL test that verifies the firmware enters a safe state when the sensor is disconnected.

2. **Set up a minimal HIL loop.** If you have access to a simulator (even a cheap one like an Arduino with a DAC shield), create a simple plant model (e.g., RC low-pass filter as a "motor"). Connect it to your dev board's ADC and PWM pins. Write firmware that reads the ADC and adjusts the PWM duty cycle. Then inject a step change in the plant model's time constant and verify the firmware responds within 100 ms.

3. **Measure the hardware gap.** Take one of your existing unit tests that mocks a peripheral (e.g., SPI read). Run the same test on real hardware with a logic analyzer attached. Compare the timing: how long does the mocked version take vs. the real SPI transaction? Document the difference—this is your "gap metric."

## Next Up

Tomorrow, we'll dive into the test frameworks that make all this possible: **Unity, CppUTest, and Ztest**. I'll compare their strengths for embedded targets, show you how to set up a cross-compiler test runner, and demonstrate how to mock HAL functions without losing your mind. See you then.
