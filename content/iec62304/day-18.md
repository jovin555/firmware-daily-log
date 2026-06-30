---
title: "Day 18: Verification vs Validation: The V&V Distinction"
date: 2026-06-30
tags: ["til", "iec62304", "verification", "validation"]
---

## What I Explored Today

Today I dug into the Verification and Validation (V&V) distinction under IEC 62304, specifically how the standard formalizes these activities across software safety classes. While the terms are often used interchangeably in casual conversation, the standard draws a sharp line: verification asks "did we build the thing right?" while validation asks "did we build the right thing?" I worked through concrete examples of each, from unit test execution to clinical simulation, and mapped them to the required deliverables for Class B and C devices.

## The Core Concept

The confusion between verification and validation is legendary in medical device engineering. I've seen teams mark a requirements review as "validation" because they checked that the requirements matched the user needs. That's verification. Validation is proving the final device actually works in the intended clinical environment.

IEC 62304 §5 and §6 lay this out explicitly. Verification is a continuous activity throughout development—reviewing documents, running tests, checking code against requirements. Validation is a summative activity that happens after integration, where you demonstrate the software meets the intended use under real or simulated conditions. The distinction matters because the evidence differs: verification produces checklists, test reports, and trace matrices; validation produces clinical evidence, usability studies, and risk-benefit analyses.

For Class B and C software, the standard requires documented verification of every software unit (§5.5.3) and integration testing (§6.2). Validation (§6.3) is mandatory for all classes but scales in rigor. A Class A device might validate with a simple functional test; a Class C infusion pump requires clinical simulation with worst-case scenarios.

The key insight: verification catches bugs, validation catches design errors. A perfectly verified device that treats the wrong condition is a validation failure. Both are required, but they serve different risk control purposes.

## Key Commands / Configuration / Code

Here's a practical example using a Python-based medical device controller. We'll show verification (unit test) vs validation (integration test with simulated patient).

```python
# verification_test.py — Unit test for dose calculation logic
# This verifies the function meets its specification

import unittest
from infusion_pump import calculate_dose_rate

class TestDoseCalculation(unittest.TestCase):
    def test_weight_based_dose(self):
        # Verify: does the function return correct rate for given inputs?
        result = calculate_dose_rate(
            drug_concentration=50.0,  # mg/mL
            patient_weight=70.0,      # kg
            dose_per_kg=5.0           # mg/kg/hr
        )
        # Expected: (70 * 5) / 50 = 7.0 mL/hr
        self.assertAlmostEqual(result, 7.0, places=2)
    
    def test_zero_weight_raises_error(self):
        # Verify: edge case handling per spec
        with self.assertRaises(ValueError):
            calculate_dose_rate(50.0, 0.0, 5.0)

if __name__ == '__main__':
    unittest.main()
```

```python
# validation_test.py — Simulated clinical validation
# This validates the system works in an intended-use scenario

import time
from infusion_pump import InfusionPump
from patient_simulator import PatientSimulator

def validate_weight_based_dosing():
    """
    Validation test: Simulate a 70kg patient receiving 5 mg/kg/hr
    of a 50 mg/mL drug. The pump must deliver 7.0 mL/hr ±5%
    over a 1-hour period, and alarm if occlusion occurs.
    """
    pump = InfusionPump(device_id="VAL-001")
    patient = PatientSimulator(weight=70.0, condition="stable")
    
    # Configure per clinical protocol
    pump.set_drug("Heparin", concentration=50.0)
    pump.set_dose(weight_based=True, dose_per_kg=5.0)
    
    # Start infusion
    pump.start()
    delivered_volume = 0.0
    start_time = time.time()
    
    # Simulate 1-hour clinical use
    while time.time() - start_time < 3600:
        patient.vitals_check()
        delivered_volume = pump.volume_delivered()
        # Validation criterion: flow rate within spec
        current_rate = pump.current_rate()
        assert 6.65 <= current_rate <= 7.35, \
            f"Rate {current_rate} outside ±5% tolerance"
        time.sleep(1)
    
    # Final validation check
    assert 6.65 * 1.0 <= delivered_volume <= 7.35 * 1.0, \
        f"Total volume {delivered_volume} out of range"
    pump.stop()
    print("Validation PASSED: Dose delivery within clinical tolerance")
```

```bash
# CI pipeline showing V&V separation
# .gitlab-ci.yml excerpt

stages:
  - verification
  - validation

unit-tests:
  stage: verification
  script:
    - python -m pytest verification_test.py --junitxml=report.xml
  artifacts:
    reports:
      junit: report.xml

integration-validation:
  stage: validation
  script:
    - python validation_test.py --simulation-time 3600
  only:
    - main  # Only run on release candidates
  artifacts:
    paths:
      - validation_report.pdf
```

## Common Pitfalls & Gotchas

1. **Calling code reviews "validation"** — I've seen audit findings where a team labeled peer reviews as validation activities. Code reviews are verification (checking against requirements). Validation requires demonstrating the device in a clinical context. Mixing them up creates a gap in your evidence package that auditors will flag.

2. **Skipping validation for "simple" changes** — A bug fix to a Class C device might seem trivial, but if it changes how the device responds to an alarm condition, you need re-validation. IEC 62304 §6.3 requires validation of the complete software system. Partial validation is only acceptable if you can prove the change has no impact on clinical use—a high bar.

3. **Using the same test cases for both** — Verification tests are white-box, structural, and exhaustive. Validation tests are black-box, scenario-based, and representative. If your validation test suite looks like your unit tests, you're not validating. Validation must include realistic workflows, user errors, and environmental stressors (e.g., network latency, power dips).

## Try It Yourself

1. **Audit your last release** — Pull the V&V artifacts for your most recent software release. Count how many activities are labeled "verification" vs "validation." If the ratio is >10:1, you likely have a validation gap. Write a plan to add at least one clinical scenario test.

2. **Write a validation test for a critical function** — Take one safety-critical function from your device (e.g., alarm threshold, dose limit). Write a validation test that simulates a realistic clinical scenario, including user interaction and environmental noise. Run it against your current build and document any failures.

3. **Trace a requirement through V&V** — Pick one software requirement. Find its verification evidence (unit test, review) and its validation evidence (clinical test, usability study). If you can't find the validation link, that requirement is not validated. Create a trace matrix to close the gap.

## Next Up

Tomorrow we explore **Usability Engineering: IEC 62366 Integration**—how to merge human factors engineering with IEC 62304's software lifecycle to prevent use errors that kill. We'll cover formative vs summative usability tests and how to trace user interface requirements through to validation.
