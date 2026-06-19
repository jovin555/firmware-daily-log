---
title: "Day 07: ISO 26262: Automotive Functional Safety & ASIL Levels"
date: 2026-06-19
tags: ["til", "cfse", "iso26262", "asil", "automotive"]
---

## What I Explored Today

Today I dug into the risk classification backbone of ISO 26262: Automotive Safety Integrity Levels (ASIL). While the standard itself is a sprawling document covering everything from management to production, ASIL determination is where the rubber meets the road for embedded engineers. I worked through the Hazard Analysis and Risk Assessment (HARA) process, mapped severity, exposure, and controllability parameters to actual vehicle scenarios, and traced how an ASIL rating cascades down from a system-level hazard to individual software requirements and hardware metrics.

## The Core Concept

ASIL isn't a checkbox—it's a quantitative risk management framework. Every hazard in a vehicle is evaluated across three parameters:

- **Severity (S0–S3)**: How bad are the injuries? S1 = light/moderate, S2 = severe/life-threatening, S3 = fatal.
- **Exposure (E0–E4)**: How often is the vehicle in the hazardous situation? E1 = very low, E4 = high probability per driving hour.
- **Controllability (C0–C3)**: Can the driver avoid the harm? C1 = simply controllable, C2 = normally controllable, C3 = difficult to control.

The ASIL level (A, B, C, D) is derived from the combination. QM (Quality Management) means no safety requirement—standard automotive quality suffices. ASIL D is the most stringent, reserved for hazards like unintended braking at highway speed.

Why this matters for firmware engineers: ASIL determines your development process rigor, required diagnostic coverage, and hardware failure rate targets. An ASIL D software component demands 99%+ diagnostic coverage for single-point faults, while ASIL A might only need 60%. This directly impacts your code architecture, redundancy schemes, and testing strategy.

## Key Commands / Configuration / Code

Here’s a practical example of how ASIL requirements translate into a software safety mechanism. Consider a brake-by-wire pedal position sensor. The hazard is "unintended acceleration due to sensor reading stuck at max." We assign S3, E3, C2 → ASIL C.

The safety requirement: "The pedal position sensor shall detect a stuck-at-max fault within 10ms and transition to a safe state (zero torque request)."

Below is a C implementation of a plausibility check with a software-based watchdog timer. This is typical for ASIL B/C software components.

```c
// pedal_sensor_safety.c
// ASIL C: Stuck-at-max detection with periodic self-test

#include <stdint.h>
#include <stdbool.h>

#define PEDAL_MAX_THRESHOLD  950   // ADC counts, 10-bit
#define PEDAL_MIN_THRESHOLD  50    // ADC counts, noise floor
#define STUCK_TIMEOUT_MS     10    // 10ms detection window
#define SAMPLE_INTERVAL_MS   2     // 2ms periodic task

static uint16_t last_raw_value = 0;
static uint32_t stuck_counter = 0;
static bool stuck_fault = false;

// Called every 2ms from safety-critical timer ISR
void PedalSensor_Monitor(uint16_t raw_adc_value) {
    // 1. Range check: detect out-of-range (hardware fault or short)
    if (raw_adc_value > PEDAL_MAX_THRESHOLD || raw_adc_value < PEDAL_MIN_THRESHOLD) {
        stuck_fault = true;
        return;
    }

    // 2. Stuck-at detection: compare with previous sample
    if (raw_adc_value == last_raw_value) {
        stuck_counter += SAMPLE_INTERVAL_MS;
        if (stuck_counter >= STUCK_TIMEOUT_MS) {
            stuck_fault = true;   // Signal safe state transition
        }
    } else {
        stuck_counter = 0;        // Value changed, reset timer
    }

    last_raw_value = raw_adc_value;
}

// Called by application layer to check safety status
bool PedalSensor_IsFaulted(void) {
    return stuck_fault;
}

// Diagnostic coverage: periodic self-test of the monitor logic
// Required by ISO 26262-6 Table 5 for ASIL C
bool PedalSensor_SelfTest(void) {
    // Inject a stuck condition and verify detection
    uint16_t test_value = 500;
    PedalSensor_Monitor(test_value);
    PedalSensor_Monitor(test_value);  // second call simulates stuck
    PedalSensor_Monitor(test_value);  // third call should trigger

    bool test_passed = stuck_fault;
    stuck_fault = false;             // clear for normal operation
    stuck_counter = 0;
    last_raw_value = 0;

    return test_passed;
}
```

The self-test function is critical—ISO 26262 requires diagnostic coverage for latent faults in the safety mechanism itself. Without periodic self-test, a bug in the monitor code could silently disable protection.

## Common Pitfalls & Gotchas

1. **Confusing ASIL with SIL (IEC 61508)**  
   Automotive ASIL uses different parameters (controllability doesn't exist in SIL). Don't reuse SIL ratings from industrial projects—the HARA must be vehicle-specific. A valve controller in a factory (SIL 2) might be QM in a car if the driver can easily override it.

2. **Ignoring dependent failure analysis (DFA)**  
   Many engineers assign ASIL D to a redundant system (e.g., dual MCUs) but forget to analyze common-cause failures. A single power supply glitch can kill both channels. ISO 26262-9 Clause 7 requires DFA for all safety mechanisms—document your independence assumptions.

3. **Over-engineering for ASIL B**  
   ASIL B often requires only 90% diagnostic coverage for single-point faults. I've seen teams implement full lockstep cores and triple voting for ASIL B tasks. This wastes cost and power. Match the rigor to the level—use the tables in ISO 26262-5 (hardware) and ISO 26262-6 (software) to determine exactly what coverage you need.

## Try It Yourself

1. **Perform a mini-HARA**: Pick a common automotive function (e.g., electric window lift). Identify one hazard (e.g., window closes on occupant's arm). Assign S, E, C values using the ISO 26262-3 tables. What ASIL do you get? (Hint: S1, E3, C2 → ASIL A.)

2. **Calculate diagnostic coverage**: Using the code above, modify the `STUCK_TIMEOUT_MS` to 20ms. Calculate the new diagnostic coverage for a stuck-at fault. Does it still meet ASIL C requirements per ISO 26262-5 Table 6? (Answer: 90% coverage requires detection within 10ms for most fault models—20ms may drop you to ASIL B.)

3. **Implement a self-test**: Extend the `PedalSensor_SelfTest()` function to also test the range-check logic (inject a value > PEDAL_MAX_THRESHOLD). Verify that the fault flag is set and cleared correctly.

## Next Up

Tomorrow I'll tackle **ASIL Decomposition: Splitting Safety Requirements**. When you have an ASIL D requirement but only ASIL B components available, you can decompose the requirement into redundant ASIL B(B) or ASIL C(D) paths. I'll show you the math, the independence rules, and the common mistakes that invalidate your decomposition argument.
