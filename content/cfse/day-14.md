---
title: "Day 14: Diversity & Redundancy: Hardware & Software Strategies"
date: 2026-06-26
tags: ["til", "cfse", "redundancy", "diversity"]
---

## What I Explored Today

Today I dug into the practical implementation of diversity and redundancy at the system architecture level—specifically how to combine dissimilar hardware channels and diverse software implementations to detect and tolerate faults. I focused on the difference between *identical redundancy* (two of the same thing) and *diverse redundancy* (two different things that compute the same result), and why ISO 26262 and IEC 61508 mandate diversity for ASIL D / SIL 3+ systems. I also worked through a concrete example of a dual-channel brake-by-wire controller with diverse sensor processing paths.

## The Core Concept

Redundancy alone is not enough. If you put two identical microcontrollers running identical software, a single design flaw (e.g., a timing bug in the scheduler, a compiler optimization error, or a silicon errata) will cause both channels to fail identically. That’s a *common cause failure* (CCF). Diversity breaks the symmetry.

The goal is to ensure that if one channel fails due to a systematic fault (software bug, hardware design flaw), the other channel—being different in some critical dimension—will still produce a correct result. The dimensions of diversity include:

- **Hardware diversity**: Different microcontroller families (e.g., Infineon TriCore vs. NXP S32K), different clock sources, different ADC reference voltages.
- **Software diversity**: Different algorithms (e.g., PID vs. state-space control), different programming languages (C vs. Ada), different toolchains, or even different development teams.
- **Temporal diversity**: Staggered execution times, different sampling windows.

The architecture pattern is almost always a *comparator* or *voter*: two (or three) diverse channels compute the same function, and a comparison unit checks for agreement. For ASIL D, a 2oo2 (two-out-of-two) architecture with diversity is common; for SIL 4, 2oo3 (two-out-of-three) with triple modular redundancy.

## Key Commands / Configuration / Code

Below is a simplified example of a dual-channel diverse brake pressure controller. Channel A uses a PID controller on an Infineon TC3xx; Channel B uses a state-space controller on an NXP S32K. The comparison is done by a safety logic unit (e.g., a CPLD or an ASIL-D safety monitor).

**Channel A (Infineon TriCore, PID):**
```c
// ch_a_brake_control.c
#include "safety_types.h"

// PID gains tuned for Channel A's sensor characteristics
static const float Kp = 2.5f, Ki = 0.8f, Kd = 0.1f;

safety_status_t ch_a_compute_brake_pressure(float target_pressure, float actual_pressure) {
    static float integral = 0.0f, prev_error = 0.0f;
    float error = target_pressure - actual_pressure;
    integral += error * PID_DT;
    float derivative = (error - prev_error) / PID_DT;
    float output = (Kp * error) + (Ki * integral) + (Kd * derivative);
    prev_error = error;

    // Clamp output to [0, MAX_PRESSURE]
    if (output < 0.0f) output = 0.0f;
    if (output > MAX_PRESSURE) output = MAX_PRESSURE;

    // Output is sent to safety comparator via dedicated SPI
    spidma_send(SPI_CH_A, (uint32_t*)&output, sizeof(output));
    return SAFETY_OK;
}
```

**Channel B (NXP S32K, State-Space):**
```c
// ch_b_brake_control.c
#include "safety_types.h"

// State-space matrices (pre-computed, stored in flash with CRC)
static const float A[2][2] = {{0.98f, 0.02f}, {-0.01f, 0.97f}};
static const float B[2] = {0.15f, 0.05f};
static const float C[2] = {1.0f, 0.0f};

static float x[2] = {0.0f, 0.0f};

safety_status_t ch_b_compute_brake_pressure(float target_pressure, float actual_pressure) {
    // State update
    float u = target_pressure - actual_pressure;
    float x_next[2];
    x_next[0] = A[0][0]*x[0] + A[0][1]*x[1] + B[0]*u;
    x_next[1] = A[1][0]*x[0] + A[1][1]*x[1] + B[1]*u;
    x[0] = x_next[0];
    x[1] = x_next[1];

    float output = C[0]*x[0] + C[1]*x[1];

    // Clamp output
    if (output < 0.0f) output = 0.0f;
    if (output > MAX_PRESSURE) output = MAX_PRESSURE;

    // Output via dedicated CAN FD (different bus than Ch A)
    canfd_send(CAN_CH_B, CAN_ID_BRAKE_OUTPUT, (uint8_t*)&output, sizeof(output));
    return SAFETY_OK;
}
```

**Safety Comparator (CPLD, Verilog snippet):**
```verilog
// safety_comparator.v
module brake_comparator (
    input  [15:0] pressure_a,   // from Ch A via SPI
    input  [15:0] pressure_b,   // from Ch B via CAN FD
    input         clk,
    output reg    fault,
    output reg    actuate
);
    // Tolerance window: 5% of full scale
    localparam TOLERANCE = 16'd3277;  // 5% of 65535

    always @(posedge clk) begin
        if (abs(pressure_a - pressure_b) > TOLERANCE) begin
            fault <= 1'b1;
            actuate <= 1'b0;  // Disable actuator on mismatch
        end else begin
            fault <= 1'b0;
            actuate <= 1'b1;
        end
    end
endmodule
```

## Common Pitfalls & Gotchas

1. **False diversity**: Using two different microcontroller families but the same compiler, same core IP (e.g., both ARM Cortex-M4), or same silicon foundry. A single errata affecting the Cortex-M4 core will still take down both channels. True diversity requires different core architectures (e.g., TriCore vs. Cortex-R5) or at minimum different silicon masks.

2. **Comparator tolerance too tight or too loose**: If the tolerance window is too small, normal numerical differences between diverse algorithms (e.g., PID vs. state-space settling time) will trigger false positives. If too large, you mask real faults. The tolerance must be derived from worst-case numerical analysis of both algorithms, plus ADC quantization and timing jitter. I typically set it to 3–5% of full scale after Monte Carlo simulation.

3. **Ignoring temporal alignment**: The two channels must compare values sampled at the *same* instant. If Channel A samples at t=0 and Channel B samples at t=5 ms, a fast transient (e.g., a pressure spike) will cause a mismatch even if both are working correctly. Use synchronized sampling triggers (e.g., a shared hardware timer or a sync pulse from the safety comparator).

## Try It Yourself

1. **Diversity audit**: Take an existing dual-channel design in your project. List all dimensions of diversity: microcontroller family, compiler, clock source, ADC reference, algorithm type, and communication bus. Identify at least one CCF that could still slip through.

2. **Implement a diverse voter**: Write a C function that takes two 16-bit values (from two channels) and a tolerance parameter. Return `OK` if the values agree within tolerance, `FAULT` otherwise. Add a counter that triggers a safe state after N consecutive mismatches (to debounce transient faults).

3. **Simulate a common cause failure**: In your lab setup, inject a single-bit fault into the clock source (e.g., by introducing a glitch on the oscillator). Observe whether both channels fail simultaneously. If they do, add a diverse clock monitor (e.g., a watchdog with a different timebase) and re-test.

## Next Up

Tomorrow: **Watchdog Timers: Hardware & Software WDT Strategies** — We’ll cover windowed watchdogs, independent external watchdogs, and how to architect a multi-layer watchdog hierarchy that catches both transient hangs and systematic timing violations.
