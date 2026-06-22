---
title: "Day 10: Documenting Safety Requirements from Risk Analysis"
date: 2026-06-22
tags: ["til", "iec62304", "safety-requirements", "risk"]
---

## What I Explored Today

Today I dug into the critical bridge between risk analysis and requirements engineering in IEC 62304. The standard mandates that every identified hazard with unacceptable risk must be mitigated by one or more **Safety Requirements** (SRs). These aren't just functional requirements with a "safety" label — they are traceable, verifiable statements that directly reduce risk to an acceptable level. I worked through the process of extracting SRs from a risk analysis table, linking them to specific hazards, and structuring them in a requirements management tool (I used DOORS, but the pattern applies to any tool).

## The Core Concept

The "why" here is straightforward: risk analysis produces a list of hazards, causes, and risk control measures. But without formal safety requirements, those measures are just ideas. IEC 62304 §7.1 requires that the software safety classification (A, B, or C) drives the rigor of the safety requirements documentation. For Class B and C devices, every safety requirement must be:

- **Uniquely identified** (e.g., SR-001)
- **Traceable** to a specific hazard and risk control measure
- **Verifiable** (testable by inspection, analysis, or test)
- **Allocated** to a software item or system component

The key insight: a safety requirement is not the same as a risk control measure. A risk control measure might be "add a watchdog timer." The safety requirement is: "The watchdog timer shall reset the microcontroller within 250 ms if the main loop fails to toggle the watchdog output within 200 ms." The difference is precision and verifiability.

## Key Commands / Configuration / Code

Here's a practical example of how I document safety requirements using a YAML-based requirements file (works with tools like reqif, or you can parse it with Python). I keep this in version control alongside the risk analysis.

```yaml
# safety_requirements.yaml
# Each SR links to a hazard ID from risk_analysis.yaml
safety_requirements:
  - id: "SR-001"
    description: >
      The infusion pump shall limit the maximum flow rate to 500 mL/hr
      under all operating conditions, including single-fault conditions.
    hazard_id: "HZ-003"  # Overinfusion hazard
    risk_control_measure: "RCM-002"  # Flow rate limiter
    verification_method: "test"  # Integration test with flow sensor
    allocated_to: "SW-INFUSION-CONTROL"
    risk_acceptance: "ALARP"  # As Low As Reasonably Practicable

  - id: "SR-002"
    description: >
      The watchdog timer shall generate a system reset within 250 ms
      of the main loop failing to toggle the watchdog output pin.
    hazard_id: "HZ-007"  # Software lockup hazard
    risk_control_measure: "RCM-005"
    verification_method: "analysis"  # Timing analysis + oscilloscope
    allocated_to: "SW-WATCHDOG"
    risk_acceptance: "ALARP"
```

To verify traceability, I run a simple Python script that checks every hazard with unacceptable risk has at least one SR:

```python
# check_traceability.py
import yaml

with open('risk_analysis.yaml') as f:
    risks = yaml.safe_load(f)

with open('safety_requirements.yaml') as f:
    reqs = yaml.safe_load(f)

# Build set of covered hazard IDs
covered_hazards = {sr['hazard_id'] for sr in reqs['safety_requirements']}

# Check each hazard with unacceptable risk
for hazard in risks['hazards']:
    if hazard['risk_level'] in ['unacceptable', 'high']:
        if hazard['id'] not in covered_hazards:
            print(f"ERROR: Hazard {hazard['id']} has no safety requirement!")
        else:
            print(f"OK: Hazard {hazard['id']} covered by SR(s)")
```

Output for a well-formed project:
```
OK: Hazard HZ-003 covered by SR(s)
OK: Hazard HZ-007 covered by SR(s)
OK: Hazard HZ-012 covered by SR(s)
```

## Common Pitfalls & Gotchas

**1. Writing requirements that are not verifiable.** I see this constantly: "The system shall be safe." That's not a requirement — it's a goal. A verifiable safety requirement must have a clear pass/fail criterion. "The system shall shut down within 100 ms of detecting an overcurrent condition" is verifiable (measure the time). If you can't write a test case for it, it's not a safety requirement.

**2. Forgetting to update SRs when risk analysis changes.** Risk analysis is a living document. When you add a new hazard or modify a risk control measure, you must create or update the corresponding safety requirement. I've seen audits fail because the risk analysis said "watchdog timer" but the requirements never mentioned it. Keep a traceability matrix — even a spreadsheet — and update it in the same sprint.

**3. Mixing safety requirements with functional requirements.** Safety requirements have a different lifecycle. They require independent review (for Class B/C), specific verification, and often need to be approved by a safety officer. If you bury them in a 500-item functional requirements document, you'll miss the special handling. I keep them in a separate section or a separate file, clearly tagged.

## Try It Yourself

1. **Extract SRs from your own risk analysis.** Take your most recent risk analysis document. For each hazard with unacceptable or high risk, write a verifiable safety requirement. Use the YAML format above. Ensure each SR has a unique ID, hazard link, and verification method.

2. **Run the traceability check.** Create a minimal `risk_analysis.yaml` with 3-4 hazards (some acceptable, some not). Write corresponding SRs. Run the Python script above. Intentionally leave one hazard uncovered and confirm the script catches it.

3. **Review an existing SR for verifiability.** Find a safety requirement in your current project (or write one). Ask: "Can I write a test case for this?" If the answer is no, rewrite it with a measurable criterion (time, voltage, flow rate, etc.). Share the before/after with a colleague.

## Next Up

Tomorrow: **Software Architectural Design: Decomposition**. We'll take those safety requirements and allocate them to software units, define interfaces, and handle the dreaded "how do I decompose a monolithic safety-critical system?" We'll cover architectural patterns (layered, client-server, pipe-and-filter) and how IEC 62304 §7.2 expects you to document the decomposition. Bring your block diagrams.
