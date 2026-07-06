---
title: "Day 24: FMEA: Failure Mode & Effects Analysis for Firmware"
date: 2026-07-06
tags: ["til", "cfse", "fmea", "failure-modes"]
---

## What I Explored Today

Today I dove deep into applying Failure Mode and Effects Analysis (FMEA) specifically to firmware—not just the hardware it runs on. While FMEA originated in mechanical and electrical engineering, firmware FMEA is distinct because software failures don't "wear out" like resistors or gears. Instead, they stem from design errors, timing races, and state corruption. I worked through a real example on a motor controller's PID loop, documenting failure modes like "ADC reading stuck at previous value" and "watchdog timer overflow during ISR." The goal: catch systematic faults before they become field failures.

## The Core Concept

FMEA is a bottom-up, inductive hazard analysis technique. You start with each component or function, ask "what could go wrong here?" and trace the effects up to the system level. For firmware, the "components" are not resistors—they are functions, tasks, ISRs, shared memory regions, and communication buffers.

Why do firmware FMEA? Because hardware FMEA alone misses software-specific failure modes:
- **Latent state corruption**: A global variable gets clobbered by a DMA transfer, but the effect only manifests 10 seconds later.
- **Timing inversions**: A high-priority task preempts a lower one, causing a stale sensor value to be used in a safety calculation.
- **Stack overflow**: Not a hardware failure, but a firmware design flaw that corrupts return addresses.

The output of a firmware FMEA is a table: Failure Mode → Cause → Local Effect → System Effect → Detection Method → Severity/Occurrence/Detection ratings (RPN). The key difference from hardware: you must consider *sequences* of events, not just single-point failures. A single bit-flip in a register might be harmless, but a bit-flip *during a context switch* while holding a mutex can cause a deadlock.

## Key Commands / Configuration / Code

Here is a practical FMEA template I use in a spreadsheet (or a Markdown table in a git repo). The columns are tailored for firmware.

```markdown
| ID | Function / Module | Failure Mode | Cause | Local Effect | System Effect | Detection | S | O | D | RPN | Mitigation |
|----|-------------------|--------------|-------|--------------|---------------|-----------|----|----|----|-----|------------|
| F1 | PID Controller   | ADC reading stuck at previous value | DMA channel not reconfigured after sleep mode | Integral windup in PID | Motor overshoots target, possible overcurrent | Watchdog timer (WDT) reset if loop time exceeds 100ms | 8 | 3 | 2 | 48 | Add ADC sanity check: if |new - old| > threshold, clamp output |
| F2 | CAN TX Buffer    | Buffer overflow | ISR writes to buffer while main loop reads without mutex | Corrupted CAN message ID | Wrong actuator command sent | CRC mismatch on receiver | 9 | 4 | 5 | 180 | Add mutex; use double-buffering with atomic pointer swap |
| F3 | Watchdog ISR     | WDT fires during ISR entry | ISR takes >100ms due to nested interrupt | System reset | Loss of control for 500ms (reboot time) | None (reset already happened) | 7 | 2 | 8 | 112 | Move heavy processing to task; ISR should only set flag |
```

**Severity (S)**: 1 (no effect) to 10 (hazardous, potential injury).  
**Occurrence (O)**: 1 (extremely unlikely) to 10 (almost certain).  
**Detection (D)**: 1 (always caught by test) to 10 (no detection possible until field failure).  
**RPN** = S × O × D. Target: RPN < 100 for safety-critical items.

**Real code example**: Adding a sanity check for the ADC reading (mitigation for F1 above):

```c
// In PID controller task, called every 10ms
int32_t adc_raw = adc_read_channel(ADC_CH_CURRENT);

// Sanity check: reject readings that jump more than 20% from previous
static int32_t prev_adc_raw = 0;
int32_t delta = abs(adc_raw - prev_adc_raw);
if (delta > (prev_adc_raw / 5)) {  // 20% threshold
    // Log failure mode, use last valid value
    log_fmea_event(FMEA_ID_ADC_STUCK, prev_adc_raw, adc_raw);
    adc_raw = prev_adc_raw;
    // Optionally: trigger a diagnostic trouble code (DTC)
}
prev_adc_raw = adc_raw;

// Now safe to use adc_raw in PID calculation
```

## Common Pitfalls & Gotchas

1. **Confusing "cause" with "effect"**  
   In firmware FMEA, a common mistake is listing "bit flip" as the cause. The *cause* is the design flaw that allows a bit flip to matter (e.g., "no ECC on SRAM" or "no CRC on CAN frame"). The *effect* is what the system does wrong. Be precise: "DMA channel misconfiguration" not "data corruption."

2. **Ignoring timing failures**  
   Hardware FMEA often assumes components fail independently. Firmware FMEA must account for *race conditions* and *priority inversion*. A failure mode like "Task A writes to shared buffer while Task B reads it" is a valid entry. Don't skip it just because it's "rare"—in embedded systems, rare timing events happen every few hours.

3. **Overlooking detection methods**  
   Many teams list "watchdog timer" as a detection method for everything. A WDT only detects that the system hung—it doesn't detect a wrong-but-fast calculation. For each failure mode, ask: "Can we detect this *before* the system does something unsafe?" If the answer is "no," that's a red flag. Your detection D rating should be high (hard to detect), and you need a mitigation.

## Try It Yourself

1. **Pick one function in your current firmware** (e.g., a UART receive ISR, a temperature sensor reading, a PWM duty cycle update). Write down 3 failure modes for that function. For each, fill in Cause, Local Effect, System Effect, and Detection. Calculate RPN.

2. **Add a sanity check** to one of your sensor readings (like the ADC example above). Use a threshold that rejects implausible jumps. Log the event with a unique FMEA ID. Run your system and inject a stuck value (e.g., comment out the ADC read and reuse the last value). Verify the sanity check catches it.

3. **Review your existing code for a shared resource** (global variable, buffer, hardware register) accessed from both an ISR and a main-loop task. Document the failure mode "race condition on [resource name]" in your FMEA table. Propose a mitigation (mutex, atomic access, or disable interrupts around access).

## Next Up

Tomorrow: **FTA: Fault Tree Analysis - Top-Down Hazard Decomposition**. We'll flip the perspective—start with a top-level hazard (e.g., "motor runs uncontrolled") and decompose it into a tree of contributing faults. FTA complements FMEA by showing how multiple failures combine to cause a hazard. Bring your logic gates.
