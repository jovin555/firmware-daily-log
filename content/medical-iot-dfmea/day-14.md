---
title: "Day 14: DFMEA: Firmware & Software Failure Modes and IEC 62304 Linkage"
date: 2026-10-24
tags: ["til", "medical-iot-dfmea", "firmware", "iec62304"]
---

# Day 14: DFMEA: Firmware & Software Failure Modes and IEC 62304 Linkage

## What I Explored Today

Today I dug into how firmware and software failure modes fit into a DFMEA for a medical IoT device, and — more importantly — how each row of the DFMEA should trace back to a specific IEC 62304 software safety class and the corresponding lifecycle activities. The tricky part isn't listing failure modes; it's making the DFMEA defensible during an audit. A reviewer will ask "why is this software item Class B and not Class C?" and the answer has to live in the DFMEA, not in someone's head. I spent the day building the linkage: failure mode → hazardous situation → software safety class → required 62304 activities → verification evidence.

## The Core Concept

Hardware DFMEA is intuitive: a resistor opens, a capacitor shorts, a connector corrodes. Software doesn't "wear out," so the classic failure-mode taxonomy doesn't map cleanly. Instead, software failure modes are *behavioral*: an incorrect value, an unintended state transition, a missed deadline, a race condition, a stale data read, an unhandled exception, a silent watchdog reset.

The reason this matters for IEC 62304 is that the standard classifies software items by the *severity of harm* that a software failure could contribute to — Class A (no injury possible), Class B (non-serious injury possible), Class C (death or serious injury possible). That classification drives the rigor of your development process: Class C requires detailed design documentation, unit verification, and more rigorous integration testing than Class A. If your DFMEA doesn't establish the link between a failure mode and the class, you can't justify your lifecycle artifacts.

The practical workflow: for each software function, enumerate failure modes, trace each to a hazardous situation in your risk file (ISO 14971), determine the software safety class from the severity of that hazardous situation, then map the class to the required IEC 62304 activities. The DFMEA row becomes the traceability anchor. This is also where you catch the classic mistake of treating the whole firmware as one class — a device can have a Class C dosing control loop and a Class A logging function in the same image.

## Key Commands / Configuration / Code

A minimal DFMEA row as YAML, with the 62304 linkage made explicit. This is the artifact I'd actually put in the risk management file:

```yaml
# dfmea_sw_row.yaml — one software DFMEA line item
item_id: SW-DFMEA-014
function: "Deliver commanded insulin bolus within 200 ms of user confirmation"
failure_mode: "Bolus command accepted but delivery loop stalls (deadlock in pump task)"
# Local effect = what the software does wrong; system effect = what the device does
local_effect: "Pump task blocked; no delivery, no error raised to UI"
system_effect: "Under-delivery of insulin; hyperglycemia"
# Link to ISO 14971 hazard
hazard_id: HZ-007
hazardous_situation: "Sustained under-delivery during meal bolus"
severity: 8            # 1-10, per your risk matrix
probability: 3
detectability: 4
rpn: 96                # 8 * 3 * 4
# IEC 62304 classification — derived from severity of the hazardous situation
sw_safety_class: C     # death or serious injury possible -> Class C
# Required 62304 activities triggered by Class C
iec62304_activities:
  - "5.1.1 Software development planning"
  - "5.2.2 Software requirements analysis (detailed)"
  - "5.3.2 Software architectural design (detailed)"
  - "5.4.2 Detailed software design"
  - "5.5.2 Unit verification"
  - "5.6.2 Integration testing"
  - "5.7.2 System testing"
  - "6.2 Software risk management (ongoing)"
  - "7.1 Software configuration management"
  - "8.1.2 Software problem resolution"
# Mitigation / design control
mitigation: "Independent watchdog task monitors pump task heartbeat; on timeout, safe-state (stop delivery) + audible alarm"
verification: "Fault-injection test: suspend pump task via debugger, assert alarm within 500 ms"
```

The fault-injection test itself, as a real FreeRTOS snippet — this is the kind of verification evidence a Class C item needs:

```c
/* fault_inject_pump_stall.c — deliberately stall the pump task to verify watchdog */
#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"

extern TaskHandle_t pump_task_handle;
extern SemaphoreHandle_t alarm_sem;

/* Called from a test-only task. Suspends the pump task to simulate a deadlock. */
void test_inject_pump_stall(void)
{
    /* Suspend the pump task — simulates a blocked/deadlocked delivery loop */
    vTaskSuspend(pump_task_handle);

    /* Watchdog task should detect the missed heartbeat within its timeout
       and post to alarm_sem. Wait up to 1000 ms for the alarm. */
    if (xSemaphoreTake(alarm_sem, pdMS_TO_TICKS(1000)) == pdTRUE) {
        /* PASS: safe-state alarm raised within spec */
        test_log("PASS: pump stall detected, alarm raised");
    } else {
        /* FAIL: watchdog did not fire — Class C nonconformance */
        test_log("FAIL: no alarm within 1000 ms");
    }

    vTaskResume(pump_task_handle);
}
```

And the traceability check you can script in CI — every Class C DFMEA row must have a verification test ID that exists in the test suite:

```python
# trace_check.py — fail the build if a Class C DFMEA row lacks verification
import yaml, sys, glob

dfmea = [yaml.safe_load(open(f)) for f in glob.glob("dfmea/sw_*.yaml")]
tests = {t["id"] for t in (yaml.safe_load(open(f)) for f in glob.glob("tests/*.yaml"))}

missing = [
    row["item_id"] for row in dfmea
    if row["sw_safety_class"] == "C" and row.get("verification_test_id") not in tests
]
if missing:
    print("Class C rows missing verification:", missing)
    sys.exit(1)
print(f"OK: {len(dfmea)} rows traced")
```

## Common Pitfalls & Gotchas

**1. Classifying the whole firmware as one safety class.** Auditors will push back hard. A single binary can contain Class A logging, Class B telemetry, and Class C therapy control. Classify per software item (per 62304 §4.3), and let the DFMEA rows carry the class. If you lump everything into Class C "to be safe," you've just tripled your documentation burden for no risk benefit.

**2. Confusing software failure mode with hardware failure mode.** "MCU fails" is a hardware DFMEA row. The software row is "firmware fails to detect MCU brownout and continues with corrupted RAM." Keep them separate — they have different mitigations and different 62304 implications.

**3. Missing the "no fault found" failure mode.** Software's nastiest failure mode is silent incorrect behavior — a stale sensor value that looks plausible, a state machine that quietly drops a transition. These don't trigger watchdogs. Your DFMEA needs explicit rows for "plausible but wrong" and mitigations like range checks, cross-channel comparison, and CRC on stored parameters.

## Try It Yourself

1. **Build three DFMEA rows** for a function in your device (e.g., "read SpO2 and display"). Include one behavioral failure mode, one timing failure mode, and one "plausible but wrong" failure mode. Assign each a software safety class and justify it in one sentence.

2. **Write the fault-injection test** for the highest-severity row using your RTOS's task-suspend or a debugger breakpoint. Assert that your safe-state mitigation fires within a defined time budget, and log the result as verification evidence.

3. **Run the traceability check** against your existing DFMEA and test suite. Any Class C row without a linked verification test is a gap — fix it before your next design review.

## Next Up

Tomorrow: **DFMEA: Enclosure, Ingress Protection & Biocompatibility (ISO 10993)** — how mechanical and material failure modes (seal degradation, outgassing, leachables) enter the DFMEA, and how to link IP ratings and biocompatibility test results back to risk file entries.
