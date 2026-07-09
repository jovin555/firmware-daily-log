---
title: "Day 27: ISO 26262: Automotive Functional Safety & ASIL Levels"
date: 2026-07-09
tags: ["til", "cfse", "iso26262", "asil", "automotive"]
---

## What I Explored Today

Today I dug into the core of ISO 26262: the ASIL (Automotive Safety Integrity Level) classification system. While I've worked with safety-critical systems before (DO-178C in avionics, IEC 61508 in industrial controls), automotive functional safety has its own unique risk assessment mechanics. I focused on understanding how ASIL levels are determined via the three parameters—Severity, Exposure, and Controllability—and how those translate into concrete hardware and software development requirements. I also walked through the actual hazard analysis and risk assessment (HARA) process using a real steering system example.

## The Core Concept

ISO 26262 isn't just a checklist; it's a risk-based framework. The entire standard revolves around answering one question: *How bad could it get, how often does it happen, and can the driver save themselves?*

The answer yields an ASIL rating: **A, B, C, or D** (plus QM for no safety relevance). ASIL D is the most stringent (e.g., airbag deployment, braking systems). ASIL A is the least stringent (e.g., interior lighting).

The three parameters are:

- **Severity (S0–S3)**: How severe are the injuries? S0 = no injuries, S3 = life-threatening or fatal.
- **Exposure (E0–E4)**: How often does the vehicle operate in the hazardous situation? E0 = incredibly rare, E4 = happens on nearly every drive.
- **Controllability (C0–C3)**: Can the driver (or other road users) intervene to prevent harm? C0 = easily controllable, C3 = uncontrollable.

The ASIL is derived from the tuple (S, E, C). For example, (S3, E4, C3) yields ASIL D. (S1, E2, C1) yields ASIL A. If any parameter is S0, E0, or C0, the item is QM (no safety requirement).

The real engineering work begins *after* the ASIL is assigned. Each ASIL level dictates:
- **Hardware metrics**: Single-point fault metric (SPFM), latent fault metric (LFM), probabilistic metric for random hardware failures (PMHF).
- **Software requirements**: Degree of independence between software elements, depth of testing, coverage criteria for structural coverage (statement, branch, MC/DC).
- **Process rigor**: Amount of documentation, review independence, tool qualification level (TCL).

## Key Commands / Configuration / Code

Let's make this concrete. Below is a snippet from a **HARA worksheet** (typically done in Excel or a requirements tool like Polarion or Jama). I'll show the logic in Python for reproducibility.

```python
# HARA classification helper — for educational use, not production safety analysis
def assign_asil(severity, exposure, controllability):
    """
    ISO 26262-3:2018 Table 1 logic.
    severity: 0-3, exposure: 0-4, controllability: 0-3
    Returns: 'QM', 'A', 'B', 'C', 'D'
    """
    # If any parameter is 0, it's QM
    if severity == 0 or exposure == 0 or controllability == 0:
        return 'QM'
    
    # Lookup table based on standard
    asil_table = {
        (1, 1, 1): 'QM', (1, 1, 2): 'QM', (1, 1, 3): 'A',
        (1, 2, 1): 'QM', (1, 2, 2): 'A',   (1, 2, 3): 'B',
        (1, 3, 1): 'A',   (1, 3, 2): 'B',   (1, 3, 3): 'C',
        (1, 4, 1): 'B',   (1, 4, 2): 'C',   (1, 4, 3): 'D',
        (2, 1, 1): 'QM', (2, 1, 2): 'A',   (2, 1, 3): 'B',
        (2, 2, 1): 'A',   (2, 2, 2): 'B',   (2, 2, 3): 'C',
        (2, 3, 1): 'B',   (2, 3, 2): 'C',   (2, 3, 3): 'D',
        (2, 4, 1): 'C',   (2, 4, 2): 'D',   (2, 4, 3): 'D',
        (3, 1, 1): 'A',   (3, 1, 2): 'B',   (3, 1, 3): 'C',
        (3, 2, 1): 'B',   (3, 2, 2): 'C',   (3, 2, 3): 'D',
        (3, 3, 1): 'C',   (3, 3, 2): 'D',   (3, 3, 3): 'D',
        (3, 4, 1): 'D',   (3, 4, 2): 'D',   (3, 4, 3): 'D',
    }
    return asil_table.get((severity, exposure, controllability), 'QM')

# Example: Electric Power Steering (EPS) loss of assist
# Scenario: Highway driving, sudden loss of steering assist at 100 km/h
# Severity: S3 (high-speed crash likely fatal)
# Exposure: E4 (highway driving happens every trip)
# Controllability: C3 (driver cannot reasonably compensate for sudden torque loss)
asil_eps = assign_asil(3, 4, 3)
print(f"EPS loss of assist → ASIL {asil_eps}")  # Output: ASIL D
```

Now, here's a real-world **ASIL decomposition** example in a requirements format (e.g., for a system like an ADAS camera):

```
Requirement ID: SAF-REQ-0421
Title: Lane Keep Assist shall detect lane departure within 100ms
ASIL: D (original)
Decomposed into:
  - SAF-REQ-0421a: Lane detection algorithm (ASIL B)
  - SAF-REQ-0421b: Actuator control path (ASIL B)
Rationale: Sufficient independence between algorithm and actuation per ISO 26262-9:2018 Clause 5
```

## Common Pitfalls & Gotchas

1. **Confusing ASIL with SIL**: ASIL is *not* SIL (Safety Integrity Level from IEC 61508). ASIL D is roughly equivalent to SIL 3, but the metrics (SPFM, LFM, PMHF) are different. Never map directly.

2. **Ignoring dependent failures in decomposition**: You cannot decompose ASIL D into two ASIL B subsystems if they share a common power supply, clock, or software library. The decomposition requires *proven independence* — you must show that a single fault cannot affect both channels. This is the most common audit finding I've seen.

3. **Over-engineering QM items**: If your HARA yields QM, do not apply ASIL-level processes. I've seen teams waste months adding redundant hardware and MC/DC coverage to a QM interior light controller. QM means "use your normal quality process" — not "do nothing," but also not "do ASIL D."

## Try It Yourself

1. **Run the HARA classifier**: Take the Python snippet above and run it. Then change the parameters for a different hazard — say, "brake pedal position sensor fails to zero" on a city street. Assign S, E, C values and see the ASIL. Does it match your intuition?

2. **Read a real HARA**: Find the public ISO 26262 example from the standard (Part 3, Annex B) or an open-source HARA template. Pick one hazard and trace how the ASIL was derived. Note the assumptions about controllability — they're often the most debated.

3. **Sketch a decomposition**: Take an ASIL C requirement (e.g., "airbag deployment decision within 10ms"). Try to decompose it into two ASIL A subsystems. List at least three independence criteria you would need to prove (e.g., separate power domains, separate software stacks, separate sensors).

## Next Up

Tomorrow: **ASIL Decomposition: Splitting Safety Requirements** — we'll dive into the math behind decomposition, the independence requirements, and how to avoid the "false independence" trap that fails audits.
