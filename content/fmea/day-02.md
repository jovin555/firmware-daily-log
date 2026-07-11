---
title: "Day 02: DFMEA vs PFMEA vs FMEA-MSR: Key Differences"
date: 2026-07-11
tags: ["til", "fmea", "dfmea", "pfmea"]
---

## What I Explored Today

Today I dug into the three primary flavors of FMEA that every embedded systems engineer will encounter: Design FMEA (DFMEA), Process FMEA (PFMEA), and FMEA for Monitoring and System Response (FMEA-MSR). While they share the same core methodology—identify failure modes, assess risk, and define actions—each targets a fundamentally different phase of the product lifecycle. Confusing them leads to wasted effort, missed hazards, and audit findings. I focused on where the boundaries blur, especially when firmware and hardware interact.

## The Core Concept

Think of the product lifecycle as three distinct phases: *design*, *manufacturing*, and *operation*. Each phase has its own failure mechanisms.

- **DFMEA** asks: "Does the design itself have a weakness?" It examines the schematic, PCB layout, firmware architecture, and mechanical design. For an embedded system, this means looking at things like: "What happens if the watchdog timer fires during a critical EEPROM write?" or "Can an overvoltage on the CAN bus damage the transceiver?" The focus is on the *product's inherent robustness*.

- **PFMEA** asks: "Can the manufacturing or assembly process introduce a defect?" It examines soldering, programming, potting, testing, and handling. For example: "Could a misaligned reflow profile cause a cold solder joint on the voltage regulator?" or "What if the factory programmer loads the wrong firmware revision?" The focus is on *process variability and human error*.

- **FMEA-MSR** (Monitoring and System Response) asks: "If a failure occurs during operation, can the system detect it and respond safely?" This is the newest addition (from AIAG & VDA FMEA Handbook, 1st ed., 2019). It specifically addresses diagnostic coverage, fault reaction times, and degraded modes. For an embedded system, this is where you analyze: "Does the CRC check on sensor data trigger a safe state within 100 ms?" or "If the main MCU crashes, does the secondary watchdog force a reset and log the event?"

The critical insight: **A single failure mode can appear in all three FMEAs, but with different causes and controls.** For example, a "short circuit on the power rail" is a DFMEA failure mode (design weakness), a PFMEA failure mode (solder bridge from poor stencil), and an FMEA-MSR trigger (system must detect overcurrent and shut down). You must decide which analysis owns which aspect.

## Key Commands / Configuration / Code

When building an FMEA in a spreadsheet or tool, the column headers differ slightly. Here’s a practical template for each, with the columns that matter most.

**DFMEA Template (columns for embedded design):**
```
Item / Function | Failure Mode | Effect (local & system) | Cause (design weakness) | Current Controls (design review, simulation) | Severity | Occurrence | Detection | RPN | Recommended Action
```

**PFMEA Template (columns for manufacturing):**
```
Process Step | Failure Mode | Effect (on product) | Cause (process variation) | Current Controls (SPC, visual inspection) | Severity | Occurrence | Detection | RPN | Recommended Action
```

**FMEA-MSR Template (columns for runtime safety):**
```
Monitoring Function | Failure Mode | System Response | Detection Method (diagnostic) | Reaction Time | Severity | Occurrence | Detection | RPN | Recommended Action
```

**Example FMEA-MSR entry for a firmware watchdog:**
```
Monitoring Function: Watchdog timer (IWDG) on STM32F4
Failure Mode: Watchdog fails to reset on software lockup (e.g., infinite loop)
System Response: System enters safe state (all outputs to predefined safe values, LED blinks error code)
Detection Method: Independent windowed watchdog with hardware reset (not software-triggered)
Reaction Time: < 500 ms (window timeout)
Severity: 8 (loss of control, potential for unsafe state)
Occurrence: 3 (rare, but possible with memory corruption)
Detection: 2 (hardware watchdog is highly reliable)
RPN: 48
Recommended Action: Add secondary external watchdog (e.g., TPS3823) for critical safety functions.
```

**Python snippet to calculate RPN (Risk Priority Number):**
```python
# Simple RPN calculator for FMEA
def calculate_rpn(severity, occurrence, detection):
    """
    severity: 1-10 (1 = negligible, 10 = catastrophic)
    occurrence: 1-10 (1 = extremely unlikely, 10 = almost certain)
    detection: 1-10 (1 = almost certain detection, 10 = impossible to detect)
    """
    if not (1 <= severity <= 10 and 1 <= occurrence <= 10 and 1 <= detection <= 10):
        raise ValueError("All ratings must be between 1 and 10")
    return severity * occurrence * detection

# Example usage
rpn = calculate_rpn(severity=8, occurrence=3, detection=2)
print(f"RPN: {rpn}")  # Output: RPN: 48
```

## Common Pitfalls & Gotchas

1. **Using the same RPN threshold for all three FMEAs.** A DFMEA with RPN > 100 might trigger a design change, but an FMEA-MSR with RPN > 100 might be acceptable if the system response is fast enough. Always define separate action thresholds per FMEA type.

2. **Ignoring FMEA-MSR for non-safety-critical systems.** Even if your product isn't ISO 26262 or IEC 61508 certified, FMEA-MSR is invaluable for customer experience. A system that silently fails (e.g., a smart thermostat that stops heating without alerting the user) is a support nightmare.

3. **Mixing DFMEA and PFMEA causes.** A common mistake: listing "operator error" as a cause in DFMEA. That belongs in PFMEA. DFMEA causes must be design-related (e.g., "insufficient decoupling capacitance"). Keep the analysis clean.

## Try It Yourself

1. **Pick one failure mode from your current project** (e.g., "I2C bus lockup due to noise"). Write a DFMEA entry for it (design cause: missing pull-up resistors? bus capacitance too high?). Then write a PFMEA entry (process cause: poor soldering on the I2C lines?). Finally, write an FMEA-MSR entry (system response: I2C timeout handler? bus recovery sequence?).

2. **Audit your existing FMEA** (if you have one). Identify at least three entries that are in the wrong FMEA type. Move them to the correct analysis and update the causes and controls accordingly.

3. **Calculate RPN for a real failure mode** using the Python snippet above. Then ask: "If I add a hardware watchdog (Detection goes from 7 to 2), how does the RPN change?" Document the delta.

## Next Up

Tomorrow, we’ll tackle **FMEA Team Formation & Scope Definition**—specifically, how to assemble the right cross-functional team (hardware, firmware, test, manufacturing) and define the analysis boundary so you don’t end up analyzing the entire universe. We’ll also cover the dreaded "scope creep" and how to kill it with a simple boundary diagram.
