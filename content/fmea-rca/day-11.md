---
title: "Day 11: D7: Preventing Recurrence \u2014 Updating FMEA & Control Plans"
date: 2026-07-20
tags: ["til", "fmea-rca", "d7", "prevention"]
---

## What I Explored Today

Today I worked through D7 of the 8D process — the step that separates a temporary fix from a permanent solution. After validating corrective actions in D6, D7 forces us to institutionalize those changes so the failure mode never returns. I focused on updating two living documents: the Process FMEA (pFMEA) and the associated Control Plan. In my embedded systems context, this meant revising a DFMEA for a battery management system (BMS) voltage sense line that had failed due to ESD ingress, then updating the production test fixture’s Control Plan to include a new 100% hipot test.

## The Core Concept

D7 is about *systemic prevention*, not just component-level fixes. If you only replace a failed FET without updating your FMEA, you’ve fixed one unit but left the entire product line vulnerable. The FMEA is your risk register; D7 is where you re-evaluate every RPN (Risk Priority Number) that the corrective action might have changed.

Why update both FMEA and Control Plan? The FMEA captures *what could go wrong* and *why*. The Control Plan captures *how you detect and prevent it during production*. They are two sides of the same coin. If you add a TVS diode to the BMS sense line (the corrective action), the FMEA must reflect the new prevention control, and the Control Plan must specify how to verify that diode is present and functional on every unit.

The key metric here is the **revised RPN**. After implementing the corrective action, you re-score Severity (S), Occurrence (O), and Detection (D). If the new RPN is still above your company’s threshold (typically 100-200), you haven’t finished D7.

## Key Commands / Configuration / Code

Below is a practical example of how I document FMEA updates in a structured YAML format (used by many PLM tools) and the corresponding Control Plan update.

### FMEA Update (YAML snippet for a BMS voltage sense line)

```yaml
# fmea_update_bms_vsense.yaml
# Original failure mode: Voltage sense line open due to ESD damage
# Corrective action: Add bidirectional TVS diode (SMCJ5.0A) and series 100Ω resistor

failure_mode:
  id: FM-0042
  function: "Measure cell voltage via sense line"
  failure_mode: "Sense line open circuit"
  effect: "BMS reports incorrect cell voltage -> overcharge risk"
  cause: "ESD discharge > 15kV through unprotected PCB trace"

# Original RPN (before D7)
original_rpn:
  severity: 9    # Safety-critical: overcharge can cause fire
  occurrence: 4  # ESD events during assembly: ~1 per 1000 units
  detection: 6   # Only caught during final functional test
  rpn: 216       # 9 * 4 * 6 = 216 (above threshold of 150)

# Updated RPN (after corrective action)
updated_rpn:
  severity: 9    # Still safety-critical (unchanged)
  occurrence: 1  # TVS clamps ESD to < 10V, resistor limits current
  detection: 2   # New 100% hipot test catches missing TVS
  rpn: 18        # 9 * 1 * 2 = 18 (well below threshold)

# New prevention controls
prevention_controls:
  - "TVS diode SMCJ5.0A installed per IPC-A-610 Class 3"
  - "Series resistor 100Ω ±1% installed adjacent to TVS"

# New detection controls
detection_controls:
  - "100% hipot test: 1500V DC, leakage < 10µA (test fixture step 7)"
  - "Automated optical inspection (AOI) verifies TVS polarity"
```

### Control Plan Update (excerpt for production test fixture)

```text
# Control Plan: BMS Production Test Fixture v2.1
# Updated: 2026-07-20 by [Engineer Name]
# Change: Added hipot test for TVS diode verification

| Process Step | Control Method | Specification | Sample Size | Reaction Plan |
|---|---|---|---|---|
| Solder paste inspection | SPI (3D) | Volume > 80% pad | 100% | Reflow rework |
| TVS placement | Pick-and-place + AOI | Polarity correct | 100% | Reject, rework |
| Reflow | Profile verification | Peak 245°C ±5°C | 1 per shift | Recalibrate oven |
| **Hipot test (NEW)** | **HiPot tester** | **1500V DC, leakage < 10µA** | **100%** | **Fail: scrap unit, inspect TVS** |
| Functional test | BMS test jig | All voltages ±1% | 100% | Fail: debug per D6 |

# Note: Hipot test added per FMEA FM-0042 corrective action.
# Test duration: 500ms per unit. Fixture cycle time impact: +1.2s.
```

### Verification Script (Python for automated FMEA RPN check)

```python
# check_rpn_threshold.py
# Verifies all FMEA items are below threshold after D7 update

import yaml

RPN_THRESHOLD = 150

with open('fmea_update_bms_vsense.yaml', 'r') as f:
    data = yaml.safe_load(f)

original = data['original_rpn']
updated = data['updated_rpn']

orig_rpn = original['severity'] * original['occurrence'] * original['detection']
new_rpn = updated['severity'] * updated['occurrence'] * updated['detection']

print(f"Original RPN: {orig_rpn}")
print(f"Updated RPN:  {new_rpn}")

if new_rpn > RPN_THRESHOLD:
    print("FAIL: RPN still above threshold. Additional controls needed.")
    exit(1)
else:
    print("PASS: RPN below threshold. D7 complete for this failure mode.")
    exit(0)
```

## Common Pitfalls & Gotchas

1. **Updating only one document.** I’ve seen teams update the FMEA but forget the Control Plan, or vice versa. The Control Plan must reference the new detection method *by name and step number*. If the hipot test isn’t in the Control Plan, production won’t run it.

2. **Not re-scoring Occurrence after a design change.** Adding a TVS diode reduces the likelihood of ESD damage, but if you keep the Occurrence score at 4, your RPN stays inflated. Be honest: the corrective action *should* drop Occurrence to 1 or 2. If it doesn’t, your fix isn’t robust enough.

3. **Ignoring the “Reaction Plan” column.** The Control Plan must specify what happens when the new detection method fails. If the hipot test fails, do you rework the TVS? Scrap the unit? Inspect the entire batch? Leaving this blank means your production line has no guidance when the new test catches a defect.

## Try It Yourself

1. **Re-score an existing FMEA.** Take one failure mode from your current project. Apply a corrective action you’ve already implemented. Re-calculate the RPN with honest new scores for Occurrence and Detection. Is it below your threshold? If not, identify what additional control you need.

2. **Map a Control Plan step to an FMEA detection control.** Write a one-line addition to your Control Plan that directly references a detection method from your FMEA. Include the specification (e.g., voltage, duration, pass/fail criteria) and a reaction plan.

3. **Run the RPN check script.** Copy the YAML example above, replace with your own failure mode data, and run the Python script. Modify it to output a list of all failure modes that still exceed the threshold.

## Next Up

Tomorrow is D8: Closure & Team Recognition — the step that formally closes the 8D, archives the documentation, and (most importantly) celebrates the team’s effort. Because if you don’t recognize the people who solved the problem, you’ll have no one willing to solve the next one.
