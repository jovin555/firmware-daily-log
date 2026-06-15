---
title: "Day 03: Software Safety Classification: Class A, B & C"
date: 2026-06-15
tags: ["til", "iec62304", "safety-class", "classification"]
---

## What I Explored Today

Today I dug into the most critical decision point in any IEC 62304 project: determining the software safety classification (Class A, B, or C). This isn't just paperwork — the classification dictates your entire development process, from documentation depth to testing rigor. I traced how the standard maps harm severity to software classes, and more importantly, how to make this determination when your software is part of a larger system (which it almost always is).

## The Core Concept

The fundamental insight of IEC 62304's classification system is that **not all software failures are equally dangerous**. The standard defines three classes based on the *consequences* of a software failure, not on the complexity of the code or the technology used.

The hierarchy works like this:
- **Class A**: No injury or damage to health. Think: patient entertainment systems, data logging that doesn't affect therapy.
- **Class B**: Non-serious injury. Reversible or minor harm. Example: a drug infusion pump that alarms incorrectly but doesn't cause overdose.
- **Class C**: Death or serious injury. Irreversible harm. Example: a ventilator that stops delivering breaths.

The critical nuance: **classification applies to the software item, not the entire device**. A single medical device can contain software of different classes. For example, a defibrillator's shock-delivery algorithm is Class C, while its battery status display might be Class B.

Why this matters: Class C requires the most rigorous development (all 5 software development process activities, plus detailed risk management traceability). Class A requires only the software maintenance process (Section 12). Class B sits in between. Misclassifying can mean either dangerous under-engineering or wasteful over-engineering.

The standard provides a decision tree in Annex A (informative), but the real engineering work happens when you must determine: "Is this failure sequence reasonably probable, and what's the resulting harm?"

## Key Commands / Configuration / Code

While classification isn't a code decision, here's how you document it in practice. I use a YAML-based safety case file that lives in the repo:

```yaml
# safety_classification.yaml
# Each software item gets its own classification record

software_items:
  - id: "SW-001"
    name: "Ventilator Breath Delivery Controller"
    description: "Controls piston position, valve timing, and pressure regulation"
    hazard_analysis_ref: "HAZ-003"
    worst_case_harm: "Hypoxic brain injury or death due to apnea"
    severity: "Serious injury or death"
    classification: "C"
    rationale: >
      Failure to deliver prescribed tidal volume or rate can cause
      irreversible hypoxia. No secondary mitigation exists in hardware
      (mechanical backup valve only covers overpressure, not under-ventilation).

  - id: "SW-002"
    name: "User Interface Display Driver"
    description: "Renders patient vitals on LCD screen"
    hazard_analysis_ref: "HAZ-012"
    worst_case_harm: "Delayed clinician response due to missing data"
    severity: "Non-serious injury (reversible)"
    classification: "B"
    rationale: >
      Loss of display does not directly affect ventilation. Clinician
      can observe patient directly or use secondary monitor.
      However, delayed recognition of deteriorating status could
      cause reversible harm.

  - id: "SW-003"
    name: "Ambient Light Sensor"
    description: "Adjusts screen brightness based on room light"
    hazard_analysis_ref: "HAZ-045"
    worst_case_harm: "No injury (cosmetic only)"
    severity: "No injury"
    classification: "A"
    rationale: >
      Failure of auto-brightness only affects user comfort.
      No impact on therapy delivery or patient safety.
```

For traceability, I link this to the risk management file (ISO 14971):

```python
# validate_classification.py
# Simple script to check classification consistency

def validate_classification(harm_severity: str, classification: str) -> bool:
    """
    Validate that classification matches harm severity per IEC 62304:2006 Table A.1
    
    Args:
        harm_severity: One of "death", "serious injury", "non-serious injury", "no injury"
        classification: "A", "B", or "C"
    
    Returns:
        True if valid, False otherwise
    """
    mapping = {
        "death": "C",
        "serious injury": "C",
        "non-serious injury": "B",
        "no injury": "A"
    }
    
    expected = mapping.get(harm_severity.lower())
    if expected is None:
        raise ValueError(f"Unknown severity: {harm_severity}")
    
    if classification != expected:
        print(f"ERROR: Severity '{harm_severity}' requires Class {expected}, "
              f"but got Class {classification}")
        return False
    
    print(f"OK: Severity '{harm_severity}' -> Class {classification}")
    return True

# Example checks
validate_classification("death", "C")           # OK
validate_classification("non-serious injury", "B")  # OK
validate_classification("no injury", "A")        # OK
validate_classification("serious injury", "B")   # ERROR - should be C
```

## Common Pitfalls & Gotchas

1. **Classifying the whole device instead of software items.** I've seen teams label an entire insulin pump as "Class C" because the delivery algorithm is critical. Meanwhile, the Bluetooth pairing module is Class A. This over-classification forces unnecessary rigor on low-risk components, bloating the development timeline. Always decompose.

2. **Ignoring hardware mitigations.** If a hardware watchdog timer independently shuts down a motor before the software failure causes harm, that software item might drop from Class C to Class B. The standard explicitly allows considering hardware safety mechanisms (Section 4.3). Document these mitigations in your hazard analysis.

3. **Confusing "serious injury" with "non-serious."** The standard doesn't give a bright line. A common mistake: assuming any reversible injury is "non-serious." Wrong — a reversible but permanent injury (like nerve damage from a mis-positioned needle) is serious. Use ISO 14971's severity definitions, not your intuition.

## Try It Yourself

1. **Decompose a device you know.** Take a simple infusion pump. List 5 software items (e.g., flow rate calculation, occlusion detection, keypad input, alarm generation, battery monitoring). For each, identify the worst-case harm and assign a preliminary class. Compare with your colleagues — you'll likely disagree on at least one.

2. **Write a classification rationale.** For one of the items above, write a 3-5 sentence rationale justifying why it's Class B vs. Class C. Include what hardware mitigations exist and why they're sufficient (or not). This is exactly what auditors will ask for.

3. **Audit an existing project.** If you have a medical device project, pull the safety classification document. Check if any software item classified as "B" could actually cause death (common error). If you find one, flag it — you just prevented a regulatory finding.

## Next Up

Tomorrow: **Risk Management Primer: ISO 14971 & FMEA**. We'll connect the dots between hazard identification, risk estimation, and how those risk control measures feed back into your software safety classification. Bring your FMEA worksheets — we're going practical.
