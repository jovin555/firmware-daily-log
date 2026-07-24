---
title: "Day 15: FMEA-MSR: Monitoring & System Response for Safety"
date: 2026-07-24
tags: ["til", "fmea", "fmea-msr", "monitoring"]
---

## What I Explored Today

Today I dug into FMEA-MSR (Monitoring and System Response), the often-overlooked supplement to traditional DFMEA that addresses what happens *after* a fault occurs but *before* the system fails catastrophically. While standard FMEA assumes a single-point failure leads directly to an effect, MSR acknowledges that many safety-critical systems have built-in diagnostics, fault reaction paths, and degraded operating modes. I worked through an ISO 26262-aligned example for an automotive brake-by-wire pedal sensor, mapping out how the monitoring layer detects a plausibility fault, triggers a system response, and transitions the vehicle into a safe state—all within the fault tolerant time interval.

## The Core Concept

Traditional FMEA asks: "If this component fails, what happens to the system?" That's necessary but insufficient for modern embedded systems. FMEA-MSR asks the follow-up: "Given that the system *can* detect this failure, what does it *do* about it, and is that response good enough?"

The "why" is rooted in functional safety standards (ISO 26262, IEC 61508). These standards require that a system not only be reliable but also *diagnosable* and *recoverable*. A sensor that drifts 5% may not cause immediate harm, but if the monitoring function fails to detect it, the system could silently degrade into a hazardous state. MSR forces you to explicitly model:

- **Detection mechanism**: How does the system know something is wrong? (e.g., watchdog timer, CRC, plausibility check, sensor cross-comparison)
- **Response action**: What does the system do when it detects the fault? (e.g., limp-home mode, shutdown, alert operator)
- **Fault tolerant time interval (FTTI)**: How long can the system tolerate the fault before the hazard occurs?
- **Diagnostic coverage**: What percentage of latent faults does the monitoring catch?

The key insight: MSR turns a "failure" into a "detected, managed event." It moves you from *reactive* safety (we hope it doesn't fail) to *proactive* safety (we know it will fail, and we have a plan).

## Key Commands / Configuration / Code

Below is a practical example using Python to simulate an MSR analysis for a brake pedal position sensor. This is the kind of logic you'd embed in an ECU's diagnostic manager.

```python
# FMEA-MSR Simulation: Brake Pedal Position Sensor Monitoring
# Assumptions: Two redundant hall-effect sensors (Sensor A, Sensor B)
# FTTI = 100ms, diagnostic coverage target = 90%

import time
import random

class BrakePedalMonitor:
    def __init__(self, ftti_ms=100, threshold_percent=15):
        self.ftti_ms = ftti_ms          # Fault tolerant time interval in ms
        self.threshold = threshold_percent  # Allowed deviation between sensors
        self.last_fault_time = None
        self.safe_state_engaged = False

    def read_sensors(self):
        """Simulate sensor readings with possible drift or stuck fault."""
        # Normal operation: both sensors read ~50% pedal travel
        sensor_a = 50.0 + random.gauss(0, 1.0)
        sensor_b = 50.0 + random.gauss(0, 1.0)
        
        # Inject fault: sensor A drifts high (simulate short to supply)
        if random.random() < 0.05:  # 5% chance of fault per call
            sensor_a = 85.0 + random.gauss(0, 0.5)
            print("[FAULT] Sensor A drift detected (simulated)")
        
        return sensor_a, sensor_b

    def plausibility_check(self, a, b):
        """Cross-compare sensors; return True if fault detected."""
        deviation = abs(a - b)
        if deviation > self.threshold:
            return True
        return False

    def system_response(self):
        """Execute safe state transition: limp-home mode."""
        print("[RESPONSE] Engaging limp-home mode: brake pressure limited to 30%")
        print("[RESPONSE] Illuminating brake warning lamp")
        print("[RESPONSE] Logging DTC: P057C - Brake Pedal Position Sensor Plausibility")
        self.safe_state_engaged = True

    def monitor_cycle(self):
        """One monitoring cycle: read, check, respond if needed."""
        a, b = self.read_sensors()
        fault_detected = self.plausibility_check(a, b)
        
        if fault_detected and not self.safe_state_engaged:
            self.last_fault_time = time.time_ns() // 1_000_000  # ms
            print(f"[MONITOR] Fault detected at t={self.last_fault_time} ms")
            self.system_response()
        elif not fault_detected and self.safe_state_engaged:
            # Fault cleared; could reset if designed for it
            print("[MONITOR] Fault cleared, system may resume normal operation")
            self.safe_state_engaged = False
        else:
            print(f"[MONITOR] Normal: A={a:.1f}%, B={b:.1f}%, deviation={abs(a-b):.1f}%")

# Run simulation
monitor = BrakePedalMonitor(ftti_ms=100, threshold_percent=15)
for cycle in range(10):
    print(f"\n--- Cycle {cycle+1} ---")
    monitor.monitor_cycle()
    time.sleep(0.05)  # 50ms cycle time (within FTTI)
```

**Key observations from the code:**
- The plausibility check runs every 50ms, well within the 100ms FTTI.
- The response is immediate and deterministic: limp-home mode, not full shutdown (avoids sudden loss of braking).
- Diagnostic coverage is implicit: the cross-comparison catches drift but not common-mode failures (e.g., both sensors shorted to ground). That's a gap you'd document in the MSR worksheet.

## Common Pitfalls & Gotchas

1. **Ignoring the fault tolerant time interval (FTTI).** I've seen teams design a beautiful monitoring scheme that runs diagnostics every 500ms, but the system becomes hazardous in 200ms. The monitoring period *must* be shorter than the FTTI, including worst-case execution time and communication delays. Always measure your loop jitter.

2. **Assuming 100% diagnostic coverage.** No single monitoring method catches everything. A CRC on a CAN message catches bit flips but not a stuck-at-zero sensor. A watchdog catches CPU hangs but not a logic error in the application code. MSR requires you to explicitly state the coverage percentage and justify it (e.g., "plausibility check covers 85% of drift faults per ISO 26262-5 Table D.1").

3. **Confusing "system response" with "fault containment."** A limp-home mode that limits brake pressure is a *response*, but if the fault is in the power supply, the response itself may fail. Your MSR must consider whether the response path is independent of the fault path. If the sensor fault also corrupts the actuator driver, your limp-home won't work.

## Try It Yourself

1. **Extend the simulation:** Add a third redundant sensor and implement a "2-out-of-3 voting" monitoring scheme. Compare the diagnostic coverage vs. the dual-sensor approach. Document the trade-off in cost vs. safety.

2. **Create an MSR worksheet entry:** For a real or imagined system (e.g., an electric power steering torque sensor), write one row of an FMEA-MSR table. Include: Failure Mode, Detection Method, Response Action, FTTI, Diagnostic Coverage (%), and Verification Method (e.g., "Injection test at integration lab").

3. **Measure your own loop timing:** On your embedded target (STM32, AURIX, etc.), implement a simple monitoring task that toggles a GPIO. Use an oscilloscope or logic analyzer to measure the worst-case jitter. Compare it to your system's FTTI. If the jitter exceeds 20% of FTTI, you need to redesign your scheduler.

## Next Up

Tomorrow we bridge the gap from analysis to execution: **Control Plans: From FMEA to Production Controls**. We'll look at how the detection and response actions from your MSR become concrete test points, inspection criteria, and process controls on the manufacturing line. No more abstract worksheets—we're wiring safety into the production flow.
