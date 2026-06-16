---
title: "Day 04: FMEA: Failure Mode & Effects Analysis for Firmware"
date: 2026-06-16
tags: ["til", "cfse", "fmea", "failure-modes"]
---

## What I Explored Today

Today I dug into Failure Mode and Effects Analysis (FMEA) applied specifically to firmware — not the mechanical or electrical FMEA you see in hardware teams, but the software-centric variant that catches logic errors, race conditions, and state-machine bugs before they become field failures. I worked through a structured FMEA for a simple motor controller firmware module, documenting failure modes like "ADC reading stuck at zero" and "PWM duty cycle overflow," then traced each to its effect on system safety. The goal was to internalize how FMEA fits into the broader hazard analysis workflow: it’s the bottom-up, exhaustive counterpart to top-down methods like FTA.

## The Core Concept

FMEA is a systematic, bottom-up technique: you start with each component (or function, or variable) and ask, “What could go wrong here?” For firmware, that means every input, output, state variable, and control flow path. The “why” is simple — hardware FMEA alone misses software-specific failures. A resistor can’t “deadlock,” but a mutex can. A capacitor won’t “overflow a signed integer,” but a PID integrator will. By enumerating failure modes at the firmware level, you catch the silent logic bugs that escape unit tests and only manifest under rare timing conditions.

The output is a table (or spreadsheet) with columns: *Failure Mode*, *Cause*, *Effect*, *Severity*, *Occurrence*, *Detection*, *RPN* (Risk Priority Number), and *Recommended Action*. The RPN is the product of Severity × Occurrence × Detection, each rated 1–10. You then prioritize actions on items with RPN > 100 or Severity > 8.

## Key Commands / Configuration / Code

Here’s a real FMEA snippet for a firmware module that reads a throttle position sensor via ADC and drives a PWM output. I’ve annotated the thought process.

```c
// motor_control.c — simplified throttle-to-PWM mapping
// Failure Mode: ADC reading stuck at 0 due to hardware fault or DMA hang

// Cause: ADC peripheral clock gated, DMA descriptor corrupted, or sensor short to GND
// Effect: PWM duty cycle goes to 0% → motor stops → vehicle loses propulsion
// Severity: 9 (loss of propulsion at highway speed)
// Occurrence: 3 (rare, but DMA corruption happens with EMC noise)
// Detection: 2 (no software check — raw ADC value used directly)
// RPN: 9 * 3 * 2 = 54 (borderline, but severity > 8 demands action)

// Recommended Action: Add plausibility check with timeout
uint16_t read_throttle_with_plausibility(void) {
    static uint32_t last_valid_timestamp = 0;
    uint16_t raw = adc_read(THROTTLE_CHANNEL);
    
    // Plausibility: throttle must be > 5% (200/4095) after 100ms from boot
    if (raw < 200 && (HAL_GetTick() - last_valid_timestamp > 100)) {
        // Failure detected: enter safe state (0% PWM) and log fault
        fault_log(FAULT_THROTTLE_STUCK_LOW);
        return 0;  // safe value
    }
    
    if (raw > 200) {
        last_valid_timestamp = HAL_GetTick();
    }
    return raw;
}
```

```c
// Failure Mode: PWM duty cycle overflow due to integer multiplication
// Cause: throttle_percent * PWM_PERIOD overflows uint16_t when throttle_percent > 100
// Effect: PWM wraps to low duty → unexpected motor deceleration
// Severity: 7 (jerky motion, possible loss of control)
// Occurrence: 4 (happens if calibration yields >100% throttle)
// Detection: 4 (no range check before assignment)
// RPN: 7 * 4 * 4 = 112 (action required)

// Recommended Action: Use saturation arithmetic
uint16_t throttle_to_pwm(uint16_t throttle_percent) {
    uint32_t duty = (uint32_t)throttle_percent * PWM_PERIOD / 100;
    if (duty > PWM_PERIOD) duty = PWM_PERIOD;  // saturate
    return (uint16_t)duty;
}
```

For tracking, I use a CSV-based FMEA worksheet. Here’s the header:

```csv
Item,Function,Failure Mode,Cause,Effect,Sev,Occ,Det,RPN,Action,Owner,Status
1,Throttle read,ADC stuck low,DMA hang,Loss of propulsion,9,3,2,54,Add plausibility check,me,Open
2,PWM output,Overflow,No saturation,Jerk motion,7,4,4,112,Saturate duty cycle,me,Closed
```

## Common Pitfalls & Gotchas

1. **Confusing “Effect” with “Cause”** — A common mistake: writing “ADC stuck low” as both the failure mode and the effect. The *effect* is what the user or system experiences (e.g., “loss of propulsion”). The *cause* is the root mechanism (e.g., “DMA descriptor corrupted”). Keep the hierarchy clean or your RPN will be meaningless.

2. **Ignoring timing-dependent failures** — Firmware FMEA often misses race conditions and deadlocks because they’re hard to enumerate statically. For example, “ISR preempts main loop while writing shared variable” is a valid failure mode. Add a column for “Timing Condition” if your system has multiple threads or interrupts.

3. **Detection rating inflation** — Engineers tend to rate Detection as 1 or 2 because “the compiler will catch it” or “we have unit tests.” Real detection means runtime detection (watchdog, plausibility check, ECC). A compiler warning is not detection in the FMEA sense — it’s prevention. Be honest: if there’s no runtime check, Detection is 9 or 10.

## Try It Yourself

1. **Pick one firmware function** from your current project (e.g., a CAN message parser, a temperature sensor reader, or a state machine). List at least 5 failure modes for that function. For each, write the cause, effect, and assign Severity (1–10). Don’t worry about Occurrence/Detection yet.

2. **Calculate RPN** for each failure mode from task 1. Use realistic Occurrence (how often does this happen in the field?) and Detection (does your code have a runtime check?). Identify the top 3 items by RPN. Propose one concrete action for each.

3. **Add a plausibility check** to a piece of code you wrote recently. For example, if you read an ADC value, add a timeout-based sanity check like the one in the code block above. Test it by injecting a stuck-low condition in simulation or on hardware.

## Next Up

Tomorrow: **FTA: Fault Tree Analysis — Top-Down Hazard Decomposition**. We’ll start with a top-level hazard (e.g., “unintended motor acceleration”) and break it down into a tree of logical AND/OR gates, mapping software and hardware faults to the root cause. FTA complements FMEA perfectly — one is top-down, the other bottom-up. See you then.
