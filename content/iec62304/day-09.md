---
title: "Day 09: Software Requirements Specification (SRS)"
date: 2026-06-22
tags: ["til", "iec62304", "srs", "requirements"]
---

## What I Explored Today

Today I dug into the Software Requirements Specification (SRS) as mandated by IEC 62304 Clause 5.2. The standard doesn't prescribe a template, but it demands traceability, unambiguity, and verifiability. I spent the morning refactoring a legacy SRS that was essentially a wishlist of features into a structured document with unique identifiers, risk-linked requirements, and acceptance criteria. The key insight: the SRS isn't just for developers—it's the contract between the software team, the risk management process, and the regulatory auditor.

## The Core Concept

IEC 62304 requires that every software item (from the SOUP up to the complete system) has a documented set of functional and performance requirements. But the "why" behind this is critical: the SRS is the single source of truth for what the software must do to achieve its intended use without causing unacceptable harm. Without it, you cannot demonstrate that your design and testing are complete.

The standard explicitly requires that the SRS:
- Be documented and controlled (change management applies)
- Include requirements derived from the system-level risk analysis (Clause 7.1)
- Be traceable to the software architecture, detailed design, and unit tests
- Be unambiguous enough that a single interpretation exists

In practice, this means every requirement must be atomic, testable, and linked to a risk control measure or a functional need. I use a simple numbering scheme: `SRS-REQ-{nnnn}` for functional requirements and `SRS-SAF-{nnnn}` for safety-related requirements. Each requirement gets a status field (Proposed, Approved, Implemented, Verified) and a link to the risk analysis document.

## Key Commands / Configuration / Code

I manage SRS as YAML files in a Git repository for version control and automated traceability. Here's a real snippet from my current project (a patient monitoring system's alarm handler):

```yaml
# srs_alarm_handler.yaml
metadata:
  document_id: "SRS-ALM-001"
  revision: "2.1"
  date: "2026-06-22"
  software_item: "Alarm Handler Module"
  classification: "Class B"

requirements:
  - id: "SRS-REQ-0001"
    title: "Alarm Priority Assignment"
    description: >
      The software shall assign a priority level (HIGH, MEDIUM, LOW) to each
      alarm event based on the physiological parameter and its deviation from
      configured thresholds.
    rationale: "Ensures clinical staff can triage alarms effectively."
    risk_control: "RCM-ALM-003"  # Links to risk control measure
    verification_method: "TEST"
    acceptance_criteria: "All alarm types in Table A-1 map to correct priority per Table A-2."
    status: "Approved"

  - id: "SRS-SAF-0001"
    title: "Alarm Latency Limit"
    description: >
      The software shall generate an audible alarm within 500 milliseconds
      of detecting a parameter exceeding a HIGH priority threshold.
    rationale: "Derived from risk analysis: delayed alarm could cause patient harm."
    risk_control: "RCM-ALM-007"
    verification_method: "ANALYSIS"
    acceptance_criteria: "Measured latency < 500 ms for 99.9% of events under nominal load."
    status: "Approved"
```

To generate a traceability matrix, I use a simple Python script that parses the YAML and outputs a Markdown table:

```python
#!/usr/bin/env python3
# generate_traceability.py
import yaml, sys, os

def build_matrix(yaml_file):
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f)
    
    print("| Requirement ID | Title | Risk Control | Verification | Status |")
    print("|----------------|-------|--------------|--------------|--------|")
    for req in data['requirements']:
        rid = req['id']
        title = req['title'][:40]  # truncate for readability
        rcm = req.get('risk_control', 'N/A')
        ver = req.get('verification_method', 'N/A')
        status = req.get('status', 'Draft')
        print(f"| {rid} | {title} | {rcm} | {ver} | {status} |")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: generate_traceability.py <srs_yaml_file>")
        sys.exit(1)
    build_matrix(sys.argv[1])
```

Run it with:
```bash
python3 generate_traceability.py srs_alarm_handler.yaml
```

## Common Pitfalls & Gotchas

**1. Writing requirements that are really design specifications.** I've seen SRS documents that say "the software shall use a PID controller with Kp=2.0, Ki=0.5." That's a design decision, not a requirement. The SRS should say "the software shall maintain blood pressure within ±5 mmHg of the setpoint." Let the design team decide how. IEC 62304 is about *what*, not *how*.

**2. Forgetting to link every safety requirement to a risk control measure.** The auditor will ask: "Show me which risk analysis output drove this requirement." If you can't trace `SRS-SAF-0001` back to a specific hazard and its control measure in the risk management file, that requirement is unsubstantiated. I use the `risk_control` field in my YAML to make this explicit.

**3. Ambiguous acceptance criteria.** "The system shall respond quickly" is not verifiable. "The system shall respond within 500 ms under 95th percentile load" is. Every requirement must have a pass/fail criterion that can be objectively measured or analyzed. If you can't write a test for it, it's not a requirement.

## Try It Yourself

1. **Audit your current SRS**: Pick one module and check every requirement against the "SMART" criteria (Specific, Measurable, Achievable, Relevant, Time-bound). Rewrite any requirement that fails. Count how many are actually testable.

2. **Build a traceability matrix**: Export your SRS to YAML (or CSV) and write a script (Python, awk, or even Excel formulas) to generate a table linking each requirement to its risk control measure and verification method. Ensure no requirement is orphaned.

3. **Create a safety requirement from a hazard**: Take one hazard from your risk analysis (e.g., "over-infusion due to pump runaway"). Write a derived safety requirement that directly mitigates it. Include the risk control ID, a measurable acceptance criterion, and the verification method (test, analysis, or review).

## Next Up

Tomorrow, I'll tackle **Documenting Safety Requirements from Risk Analysis**—how to systematically extract software safety requirements from the IEC 62304 risk management process (Clause 7.1) and ensure they're properly allocated to the software architecture. We'll cover hazard logs, risk control measures, and the dreaded "residual risk" statement.
