---
title: "Day 26: HAZOP: Hazard & Operability Study for Embedded Systems"
date: 2026-07-08
tags: ["til", "cfse", "hazop", "hazard"]
---

## What I Explored Today

Today I dug into HAZOP (Hazard and Operability Study) as applied to embedded systems. While HAZOP originated in the process industries (chemical plants, refineries), it maps surprisingly well to firmware and hardware design. The core idea is systematic: take a design, break it into nodes, apply guide words to each node, and identify deviations that could lead to hazards. I worked through a real example on a battery management system (BMS) firmware module, and the structured brainstorming forced me to find failure modes I’d normally miss in an ad-hoc review.

## The Core Concept

HAZOP is not about guessing hazards. It’s a **structured, team-based technique** that uses predefined *guide words* (e.g., NO, MORE, LESS, REVERSE, PART OF) combined with *process parameters* (e.g., voltage, current, temperature, state) to systematically enumerate deviations. For embedded systems, the “process” is often a control loop, a communication protocol, or a state machine.

Why this matters: In safety-critical firmware, a single unhandled deviation (e.g., “MORE than expected CAN messages per second”) can cause a watchdog timeout, a stack overflow, or a race condition. HAZOP forces you to ask “what if?” for every combination, then decide if the deviation is credible and hazardous. The output is a list of hazards, their causes, consequences, and required safety measures.

The key difference from FMEA (Failure Mode and Effects Analysis) is that HAZOP starts with *deviations from design intent*, not component failures. This catches design errors, not just hardware faults.

## Key Commands / Configuration / Code

I’ll show a HAZOP worksheet template and a concrete example for a BMS firmware module that reads cell voltage via an ADC.

**HAZOP Worksheet Template (CSV format for traceability):**

```csv
Node,Parameter,Guide Word,Deviation,Cause,Consequence,Safety Measure,Severity,Recommendation
```

**Example: BMS ADC Read Function**

```c
// Firmware: read_cell_voltage() in bms_adc.c
// Node: ADC sampling of cell voltage
// Parameter: Voltage reading (V_cell)
// Guide word: MORE

// Deviation: V_cell > 4.2V (overvoltage)
// Cause: ADC reference drift, resistor divider tolerance, noise spike
// Consequence: Overcharge hazard, thermal runaway
// Safety measure: Software comparison to OV threshold, fault flag set
// Severity: S3 (critical)

uint16_t read_cell_voltage(uint8_t cell_id) {
    // HAZOP identified: what if ADC returns 0xFFFF (stuck high)?
    uint16_t raw = adc_read_channel(cell_id);
    // Safety measure: range check
    if (raw > ADC_MAX_VALID) {
        fault_handler(FAULT_ADC_SATURATION, cell_id);
        return 0; // safe default
    }
    // Convert to millivolts
    uint32_t mv = (uint32_t)raw * ADC_REF_MV / ADC_RESOLUTION;
    // HAZOP identified: what if mv is MORE than expected due to divider error?
    if (mv > CELL_OV_THRESHOLD_MV) {
        fault_handler(FAULT_CELL_OVERVOLTAGE, cell_id);
        // Initiate discharge or open contactor
    }
    return (uint16_t)mv;
}
```

**HAZOP Table for this node (excerpt):**

| Node | Parameter | Guide Word | Deviation | Cause | Consequence | Safety Measure | Severity |
|------|-----------|------------|-----------|-------|-------------|----------------|----------|
| ADC Read | Voltage | MORE | V_cell > 4.2V | ADC ref drift | Overcharge fire | SW threshold + fault flag | S3 |
| ADC Read | Voltage | LESS | V_cell < 2.5V | Cell degradation | Under-voltage lockout | UVLO in BMS | S2 |
| ADC Read | Voltage | NO | No reading | ADC stuck, DMA fail | No protection | Watchdog + CRC on ADC data | S3 |
| ADC Read | Voltage | REVERSE | Negative reading | Wiring reversed | Reverse polarity damage | Hardware diode + SW sign check | S2 |
| CAN Tx | Message Rate | MORE | >100 msg/s | SW bug, bus storm | CAN controller overload | Rate limiter + bus-off recovery | S2 |

**How to run a HAZOP session (practical steps):**

1. **Define nodes**: Break your system into functional blocks (e.g., ADC read, CAN transmit, state machine transitions).
2. **Select parameters**: For each node, list measurable parameters (voltage, current, time, count, state).
3. **Apply guide words**: For each parameter, go through: NO, MORE, LESS, REVERSE, PART OF, OTHER THAN, EARLY, LATE.
4. **Record deviations**: Only note credible deviations (skip “MORE voltage on a digital pin” if it’s 3.3V fixed).
5. **Assign severity**: Use ASIL or SIL categories (S1=minor, S2=moderate, S3=critical, S4=catastrophic).
6. **Define safety measures**: Existing or required mitigations (HW/SW).

## Common Pitfalls & Gotchas

1. **Applying guide words too literally.** “REVERSE” on a temperature sensor reading doesn’t mean the temperature goes negative—it means the sensor wiring is reversed (e.g., thermocouple polarity). Think in terms of the physical interface, not just the data value.

2. **Ignoring timing deviations.** Embedded systems are real-time. Guide words “EARLY” and “LATE” are critical. A CAN message arriving 10 ms early could cause a buffer overflow if your state machine isn’t ready. Always include timing parameters.

3. **Confusing HAZOP with FMEA.** HAZOP starts with deviations from design intent; FMEA starts with component failure modes. Don’t mix them. If you find yourself listing “resistor open circuit,” you’re doing FMEA. HAZOP would say “MORE voltage due to resistor tolerance stack-up.”

## Try It Yourself

1. **Pick a simple firmware function** — e.g., a UART receive ISR. List three parameters (e.g., byte count, baud rate, data value). Apply guide words NO, MORE, and REVERSE to each. Write down one credible deviation and its consequence.

2. **Create a HAZOP worksheet** for a PWM output node controlling a motor. Parameters: duty cycle, frequency, phase. Guide words: MORE, LESS, NO. For each deviation, propose a safety measure (e.g., “if duty > 100%, clamp to 100% and set fault flag”).

3. **Review an existing code review comment** — take a recent code review where you flagged a potential issue. Re-frame it as a HAZOP deviation. What was the parameter? What guide word applies? Did you miss any other deviations for that same parameter?

## Next Up

Tomorrow, I’ll dive into **ISO 26262: Automotive Functional Safety & ASIL Levels** — how to map HAZOP outputs to ASIL ratings, and why a “MORE voltage” deviation might get you an ASIL D requirement for your ADC diagnostics.
