---
title: "Day 26: IEC 62304 Structure: Clauses, Scope & ISO 14971"
date: 2026-07-08
tags: ["til", "iec62304", "iec62304", "overview"]
---

## What I Explored Today

Today I mapped the skeleton of IEC 62304 — its clause structure, scope boundaries, and the critical handshake with ISO 14971. This standard isn't a monolith; it's a layered document with five main clauses (5–9) that define the software development lifecycle, plus normative annexes that clarify risk management integration. I traced how the standard explicitly excludes certain software (like firmware on FPGAs or legacy code) and how every safety-related software item must trace back to a hazard from ISO 14971. The key insight: Clause 4 (General Requirements) and Clause 7 (Risk Management Process) are where the rubber meets the road for engineers.

## The Core Concept

IEC 62304 is structured to be *process-oriented*, not product-oriented. The standard doesn't tell you what your software should do — it tells you how to prove you did it safely. The clauses are:

- **Clause 4: General Requirements** — QMS integration, documentation, and the infamous "software item" definition.
- **Clause 5: Software Development Planning** — Plan the lifecycle model, deliverables, and standards.
- **Clause 6: Software Requirements Analysis** — Functional and safety requirements, traceable to hazards.
- **Clause 7: Software Architectural Design** — Decompose into software units, assign safety classes.
- **Clause 8: Software Detailed Design & Unit Implementation** — Coding standards, unit testing.
- **Clause 9: Software Integration & Testing** — Integration testing, regression testing, verification.
- **Clause 10: Software System Testing** — System-level validation against requirements.
- **Clause 11: Software Release** — Final review, known anomalies, installation instructions.

The scope is narrower than you think: IEC 62304 covers **software as a medical device** (SaMD) and **software in a medical device** (SiMD). It explicitly excludes:
- Firmware implemented in programmable logic (FPGAs, CPLDs) — those fall under IEC 61508 or ISO 13849.
- Software that is not part of the medical device (e.g., manufacturing test scripts).
- Legacy software (pre-1998) — but you must still document risk management.

The ISO 14971 handshake is mandatory: Clause 7 of IEC 62304 requires that every software item's risk control measures be documented in the ISO 14971 risk management file. You cannot do one without the other.

## Key Commands / Configuration / Code

Here's a practical way to map your project's clauses to a traceability matrix. I use a YAML-based document that feeds into a verification script.

```yaml
# traceability_matrix.yaml
# Maps IEC 62304 clauses to project artifacts and ISO 14971 hazards
project:
  name: "Infusion Pump Control v2.1"
  software_safety_class: "B"

clauses:
  - id: "5.2.1"
    title: "Software Development Plan"
    artifact: "SDP-001"
    risk_controls: []  # No direct hazard link, but required by QMS

  - id: "6.1"
    title: "Software Requirements Specification"
    artifact: "SRS-001"
    risk_controls:
      - "RAC-003: Flow rate limits enforced in software"
      - "RAC-007: Occlusion detection timeout"

  - id: "7.1"
    title: "Software Architecture Design"
    artifact: "SAD-001"
    risk_controls:
      - "RAC-003: Flow rate limits enforced in software"
      - "RAC-007: Occlusion detection timeout"

  - id: "8.1.1"
    title: "Detailed Design & Unit Implementation"
    artifact: "SDD-001"
    risk_controls:
      - "RAC-003: Flow rate limits enforced in software"
```

Now, a Python script to validate that every risk control from ISO 14971 is mapped to at least one software clause:

```python
# validate_traceability.py
import yaml
import sys

def validate_traceability(yaml_file):
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f)
    
    # Collect all risk controls from clauses
    mapped_controls = set()
    for clause in data['clauses']:
        for rc in clause['risk_controls']:
            mapped_controls.add(rc)
    
    # Simulate loading ISO 14971 risk controls (in practice, load from RM file)
    risk_controls_from_14971 = {
        "RAC-003: Flow rate limits enforced in software",
        "RAC-007: Occlusion detection timeout",
        "RAC-012: Battery low warning"
    }
    
    missing = risk_controls_from_14971 - mapped_controls
    if missing:
        print(f"ERROR: Missing risk controls in traceability: {missing}")
        sys.exit(1)
    else:
        print("All risk controls are traced to software clauses.")
        sys.exit(0)

if __name__ == "__main__":
    validate_traceability("traceability_matrix.yaml")
```

Run it:
```bash
python validate_traceability.py
# Output: ERROR: Missing risk controls in traceability: {'RAC-012: Battery low warning'}
```

This catches the gap before audit.

## Common Pitfalls & Gotchas

1. **Assuming Clause 7 (Risk Management) is optional for Class A software.** Wrong. Clause 4.1 requires a risk management process per ISO 14971 for *all* safety classes. Class A just has fewer software-specific risk control activities, but the hazard analysis is mandatory.

2. **Mixing up "software item" and "software unit."** A *software item* is any identifiable part of the software (could be a whole subsystem). A *software unit* is the smallest testable element (a function, a module). Clause 7 (Architecture) decomposes into software items; Clause 8 (Detailed Design) decomposes items into units. Auditors will check you understand this hierarchy.

3. **Ignoring the scope exclusion for firmware on FPGAs.** If your design uses an FPGA to implement a safety-critical logic block (e.g., watchdog timer), that block is *not* covered by IEC 62304. You must justify its safety under IEC 61508 or ISO 13849. I've seen auditors reject a submission because the team claimed "all software follows IEC 62304" while the FPGA bitstream was unaddressed.

## Try It Yourself

1. **Map your current project's clauses.** Take your project's software requirements specification (SRS) and list which IEC 62304 clauses each requirement satisfies. Create a YAML file like the one above. Run the validation script to see if any risk controls are missing.

2. **Identify scope exclusions.** Review your system's firmware. Is there any code running on an FPGA, CPLD, or a legacy processor (pre-1998)? Document why it's excluded from IEC 62304 scope and which standard (if any) covers it.

3. **Trace a hazard to code.** Pick one hazard from your ISO 14971 file (e.g., "over-infusion due to software timing error"). Write a trace from the hazard → risk control measure → software requirement → architecture component → unit test. This is exactly what auditors will ask for.

## Next Up

Tomorrow: **Software Safety Classification: Class A, B & C** — how to determine your class, what each class demands, and the common mistake of over-classifying (or under-classifying) your software.
