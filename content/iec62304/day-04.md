---
title: "Day 04: Risk Management Primer: ISO 14971 & FMEA"
date: 2026-06-16
tags: ["til", "iec62304", "iso14971", "fmea", "risk"]
---

## What I Explored Today

I dove into the risk management framework required by IEC 62304, specifically how ISO 14971 (the harmonized risk management standard for medical devices) integrates with software development. The key realization: risk management isn't a document you write once—it's a continuous thread through the entire V-model lifecycle. Today I focused on the practical mechanics of performing a Failure Mode and Effects Analysis (FMEA) for embedded medical software, including how to map hazards to software items and calculate risk priority numbers (RPNs) that actually drive design decisions.

## The Core Concept

ISO 14971 defines risk as the combination of the probability of occurrence of harm and the severity of that harm. For software, this is tricky because software doesn't "wear out" like hardware—its failure modes are deterministic, not stochastic. A bug in a timer overflow handler either exists or it doesn't; there's no MTBF for a logic error.

The standard requires a structured process: hazard identification → risk estimation → risk evaluation → risk control → verification of control effectiveness → residual risk evaluation. For embedded systems, the most practical tool is FMEA (Failure Mode and Effects Analysis). You systematically ask: "What can fail in this software component? What causes it? What happens? How bad is it? How likely is it? Can we detect it?"

The output is a living spreadsheet (or database) that ties every software requirement and unit test back to a specific risk control. This is what auditors look for—traceability from hazard to requirement to test case.

## Key Commands / Configuration / Code

Here's a practical FMEA template structure for an embedded medical device firmware module. I use this as a CSV that feeds into a Python script for RPN calculation and traceability matrix generation.

```csv
# fmea_template.csv - Risk Analysis for PWM Motor Controller Module
# Columns: ID, Function, Failure Mode, Cause, Local Effect, System Effect, Severity (1-10), Occurrence (1-10), Detection (1-10), RPN, Current Controls, Recommended Action
FMEA-001,PWM duty cycle calculation,Incorrect duty cycle due to timer overflow,32-bit timer counter wraps at 0xFFFFFFFF without saturation logic,Motor speed exceeds commanded value,Patient receives excessive therapy dose,9,4,3,108,"Watchdog timer resets MCU on timeout","Add saturation check after timer read; implement range check in ISR"
FMEA-002,PWM duty cycle calculation,Stuck-at-zero output due to GPIO config corruption,EMI-induced bit flip in GPIO control register,Motor stops,Therapy delivery halts - no harm but alarm triggers,3,5,2,30,"CRC on register config; periodic self-test","Add register refresh in main loop every 100ms"
FMEA-003,Watchdog timer service,Watchdog not serviced due to infinite loop,Pointer dereference to NULL in state machine,MCU reset,Therapy interruption < 200ms - acceptable per SRS,2,6,8,96,"Static analysis; MISRA-C checks","Add null pointer check before state transition; increase WDT timeout margin"
```

To calculate RPN and generate a risk matrix:

```python
# risk_analysis.py - Process FMEA CSV and flag unacceptable risks
import csv
import sys

RISK_THRESHOLD = 100  # RPN above this requires mandatory risk control

def process_fmea(csv_path):
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            severity = int(row['Severity (1-10)'])
            occurrence = int(row['Occurrence (1-10)'])
            detection = int(row['Detection (1-10)'])
            rpn = severity * occurrence * detection
            
            print(f"{row['ID']}: RPN={rpn} (S={severity}, O={occurrence}, D={detection})")
            
            if rpn >= RISK_THRESHOLD:
                print(f"  ⚠️  UNACCEPTABLE - Must implement: {row['Recommended Action']}")
            elif severity >= 8 and rpn >= 50:
                print(f"  ⚠️  HIGH SEVERITY - Consider additional controls")
            else:
                print(f"  ✅  Acceptable residual risk")

if __name__ == "__main__":
    process_fmea(sys.argv[1])
```

For traceability, I embed risk IDs directly in requirement files:

```c
// motor_controller.h
/**
 * @brief Sets PWM duty cycle for therapy motor.
 * @param duty_cycle_percent 0-100
 * @note Risk Control: FMEA-001 - Saturation check prevents timer overflow
 * @note Risk Control: FMEA-002 - Register refresh prevents stuck output
 */
void motor_set_duty_cycle(uint8_t duty_cycle_percent);
```

## Common Pitfalls & Gotchas

**1. Treating Occurrence like hardware MTBF**
Software doesn't fail randomly. An occurrence rating of 2 (remote) for a NULL pointer dereference is wrong if the code path is always executed. Use occurrence based on *how often the hazardous situation occurs*, not how often the software crashes. A bug in a 1 kHz ISR has occurrence 10; a bug in a rarely-triggered calibration routine might be 2.

**2. Detection ratings that assume perfect testing**
Detection should reflect the probability of catching the failure *before release* with your current verification activities. If your only detection is "code review" but you have no checklist for overflow patterns, detection is 8-9, not 2. Be honest—auditors will ask for evidence of detection capability.

**3. Forgetting that risk controls must be verified**
If you add a saturation check (FMEA-001), you need a unit test that proves it works. I've seen FMEAs with beautiful controls but zero corresponding test cases. The ISO 14971 audit trail requires: hazard → risk control requirement → verification test → test result. No test = no control.

## Try It Yourself

1. **Create an FMEA for a real embedded component**: Pick a simple function in your current project (e.g., a CRC checksum calculator, a UART receive ISR, or a battery voltage monitor). List 3-5 failure modes. Assign severity, occurrence, and detection ratings. Calculate RPNs. Identify which items need risk controls.

2. **Implement a risk control with traceability**: Write a C function that includes a saturation check for a timer value. Add Doxygen comments linking to your FMEA ID. Then write a unit test (using Ceedling or Unity) that verifies the saturation behavior. Confirm the test passes.

3. **Audit your detection ratings**: Take your FMEA from task 1. For each failure mode, list exactly what detection method you have (code review? static analysis? unit test? integration test?). Re-rate detection honestly. How many RPNs cross your threshold now? This exercise usually reveals gaps.

## Next Up

Tomorrow: **Regulatory Submissions: 510(k), PMA & Technical Files** — We'll walk through the actual documents you need to prepare for FDA and EU MDR submission, including the dreaded Software Description Document and the Essential Requirements Checklist. Bring your binder.
