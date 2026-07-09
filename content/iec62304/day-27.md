---
title: "Day 27: Software Safety Classification: Class A, B & C"
date: 2026-07-09
tags: ["til", "iec62304", "safety-class", "classification"]
---

## What I Explored Today

Today I dug into the IEC 62304 software safety classification system — the three-tiered hierarchy (Class A, B, C) that determines how much process rigor your medical device software must endure. This isn't just bureaucratic busywork; the classification directly dictates which software development activities, documentation requirements, and risk control measures are mandatory. I traced the decision logic from ISO 14971 risk management outputs through to the classification assignment, and mapped the concrete differences in required effort between classes.

## The Core Concept

The safety classification in IEC 62304 is fundamentally about *consequence severity*, not code complexity or feature count. The standard defines three classes based on what happens if the software fails or contains a latent defect:

- **Class A**: No injury or damage to health is possible. Example: a patient entertainment system in a hospital bed that displays TV channels. If it crashes, the patient is annoyed but not harmed.
- **Class B**: Non-serious injury is possible. Example: an infusion pump that delivers a slightly inaccurate flow rate, causing discomfort but not permanent harm. The injury is recoverable.
- **Class C**: Death or serious injury is possible. Example: a ventilator that fails to deliver breaths, or a radiation therapy system that delivers a lethal dose.

The critical insight: classification is *not* a property of the software itself — it's a property of the *hazardous situations* the software can contribute to. A single software system can have multiple safety classes assigned to different software items within it. For instance, a dialysis machine might have a Class C blood pump control module and a Class A display backlight controller.

The practical consequence: Class C requires the most rigorous development process (all 5 software development process activities, plus detailed risk management traceability, plus unit testing with modified condition/decision coverage). Class B requires a subset (all activities except some detailed verification). Class A requires only the basic software development plan and maintenance plan — no detailed design documentation or unit testing required.

## Key Commands / Configuration / Code

There's no CLI command for safety classification, but here's a practical decision tree you can implement as a Python script to automate the classification logic based on your risk management outputs:

```python
# safety_classifier.py — IEC 62304 classification decision helper
# Assumes you have a list of hazardous situations from ISO 14971 FMEA

from enum import Enum

class SafetyClass(Enum):
    A = "Class A — No injury possible"
    B = "Class B — Non-serious injury possible"
    C = "Class C — Death or serious injury possible"

def classify_software_item(hazardous_situations: list) -> SafetyClass:
    """
    Classify a software item based on the worst-case hazardous situation
    it can contribute to.
    
    Args:
        hazardous_situations: List of dicts with 'severity' key:
            'none', 'non_serious', 'serious', 'death'
    
    Returns:
        SafetyClass enum
    """
    severity_map = {
        'death': SafetyClass.C,
        'serious': SafetyClass.C,
        'non_serious': SafetyClass.B,
        'none': SafetyClass.A
    }
    
    # Worst-case classification determines the class
    worst = SafetyClass.A
    for hs in hazardous_situations:
        sev = hs.get('severity', 'none')
        current = severity_map.get(sev, SafetyClass.A)
        # Class C > Class B > Class A
        if current.value > worst.value:
            worst = current
    
    return worst

# Example usage
hazards = [
    {'id': 'H-001', 'description': 'Over-infusion of medication', 'severity': 'serious'},
    {'id': 'H-002', 'description': 'Display shows wrong units', 'severity': 'non_serious'},
]

result = classify_software_item(hazards)
print(f"Software item classification: {result.value}")
# Output: Software item classification: Class C — Death or serious injury possible
```

For traceability in your documentation, here's a typical table structure you'd maintain in a requirements management tool (or a YAML file):

```yaml
# safety_classification_trace.yaml
software_items:
  - id: SW-001
    name: "Blood pump controller"
    classification: "Class C"
    rationale: "Failure can cause exsanguination (death)"
    linked_hazards: ["H-001", "H-003"]
    risk_control_measures: ["RCM-001", "RCM-004", "RCM-007"]
    
  - id: SW-002
    name: "User interface display"
    classification: "Class B"
    rationale: "Misleading display can cause non-serious dosing error"
    linked_hazards: ["H-002"]
    risk_control_measures: ["RCM-002"]
    
  - id: SW-003
    name: "Backlight PWM driver"
    classification: "Class A"
    rationale: "No injury from backlight failure"
    linked_hazards: []
    risk_control_measures: []
```

## Common Pitfalls & Gotchas

1. **Classifying the entire system instead of individual software items.** I've seen teams slap a "Class C" label on the whole device because one module controls a lethal actuator. This is wasteful — the entertainment UI doesn't need Class C rigor. Decompose your software into items based on *which hazardous situations they can influence*, then classify each item independently. The standard explicitly allows this (IEC 62304:2006+AMD1:2015, 4.3).

2. **Confusing "severity of harm" with "probability of occurrence."** Classification is based solely on the *severity* of the potential harm, not how likely it is. Even if a failure is extremely improbable (e.g., a watchdog timer failing in a specific pattern), if the consequence is death, it's Class C. Probability is handled later in risk control and residual risk evaluation.

3. **Assuming Class A means "no process required."** Class A still requires a software development plan (Clause 5) and a software maintenance plan (Clause 6). You can't skip all documentation. The difference is that Class A doesn't require detailed design, unit testing, or integration testing — but you still need to plan and maintain the software.

## Try It Yourself

1. **Decompose a real device**: Take a simple medical device (e.g., a pulse oximeter) and list its software items. For each item, identify the worst-case hazardous situation it could contribute to, then assign a safety class. Document your rationale.

2. **Audit your current project**: If you're working on a medical device, check whether your current safety classification is applied at the software item level or the system level. If it's system-level, decompose into items and see if you can downgrade some modules to Class B or A — this can save significant documentation effort.

3. **Write a classification decision script**: Extend the Python script above to read from a CSV file of hazards and output a classification report. Add a function that checks for consistency (e.g., no missing severity fields, no contradictory classifications).

## Next Up

Tomorrow we tackle **Risk Management Primer: ISO 14971 & FMEA** — the foundational framework that feeds into safety classification. We'll walk through the hazard identification process, severity vs. probability matrices, and how to connect FMEA outputs directly to your software safety classification decisions.
