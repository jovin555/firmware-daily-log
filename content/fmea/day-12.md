---
title: "Day 12: PFMEA Deep Dive: Process Flow Diagrams & Process Steps"
date: 2026-07-21
tags: ["til", "fmea", "pfmea", "process-flow"]
---

## What I Explored Today

Today I dug into the foundational layer of any PFMEA: the Process Flow Diagram (PFD) and its associated Process Steps. Without a precise, well-structured PFD, the PFMEA is built on sand. I spent the morning mapping a real-world SMT (Surface-Mount Technology) assembly line into a hierarchical process flow, then decomposing each block into discrete, measurable process steps. The key insight: a process step in PFMEA must be a single operation that adds or transforms value—not a zone, not a machine group, not a material movement. I also learned how to handle parallel flows, rework loops, and inspection points without breaking the FMEA structure.

## The Core Concept

The Process Flow Diagram is the single source of truth for the PFMEA scope. It answers: *What are we analyzing?* Every failure mode, effect, cause, and control must trace back to a specific process step. If the flow is wrong, the entire PFMEA is wrong.

**Why this matters:** Engineers often skip the PFD or treat it as a high-level block diagram. They jump straight to failure modes. This is a trap. A PFMEA with a vague flow will have vague failure modes—and vague controls. The PFD forces you to define the process boundaries, inputs, outputs, and interfaces before you ever write a failure mode.

**The decomposition rule:** A process step should be atomic—one action, one parameter, one output. For example, "Solder Paste Printing" is too broad. Break it into: "Stencil Alignment" → "Paste Application" → "Paste Inspection (SPI)". Each of these becomes a row in the PFMEA. This granularity is what makes the analysis actionable.

**Parallel vs. serial flows:** When two operations happen simultaneously (e.g., dual-lane pick-and-place), you must decide: treat them as one step with two identical risk profiles, or split into two steps. The PFMEA standard (AIAG & VDA) recommends treating them as separate steps only if they have different failure modes (e.g., different component types on each lane). Otherwise, combine and note the parallel nature in the process description.

## Key Commands / Configuration / Code

Below is a structured approach to documenting a process step in a PFMEA spreadsheet or database. I use a Python script to validate the flow before importing into our FMEA tool. The script checks for missing step IDs, duplicate descriptions, and orphaned rework loops.

```python
# process_flow_validator.py
# Validates PFMEA process flow structure before analysis

import csv
import sys

def validate_flow(csv_path):
    steps = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            steps.append(row)
    
    # Check 1: Every step must have a unique ID
    ids = [s['step_id'] for s in steps]
    if len(ids) != len(set(ids)):
        print("ERROR: Duplicate step IDs found")
        sys.exit(1)
    
    # Check 2: Every step must have a predecessor (except step 1)
    for s in steps[1:]:
        if not s.get('predecessor_id'):
            print(f"ERROR: Step {s['step_id']} has no predecessor")
            sys.exit(1)
    
    # Check 3: Rework loops must have explicit return step
    for s in steps:
        if s.get('is_rework', '').lower() == 'yes':
            if not s.get('return_to_step'):
                print(f"WARNING: Rework step {s['step_id']} missing return_to_step")
    
    # Check 4: Inspection steps must have a decision point
    for s in steps:
        if s.get('step_type') == 'inspection':
            if not s.get('decision_criteria'):
                print(f"WARNING: Inspection step {s['step_id']} missing decision criteria")
    
    print("Flow validation passed")
    return True

# Example usage:
# validate_flow('smt_pfmea_flow.csv')
```

**CSV structure for the flow:**

```csv
step_id,step_name,step_type,predecessor_id,is_rework,return_to_step,decision_criteria
P01,Stencil Alignment,setup,None,no,,,
P02,Paste Application,operation,P01,no,,,
P03,SPI (Solder Paste Inspection),inspection,P02,no,,paste_height > 80% stencil thickness
P04,Component Placement (Top),operation,P03,no,,,
P05,Component Placement (Bottom),operation,P04,no,,,
P06,Pre-reflow Inspection,inspection,P05,no,,all components present
P07,Rework - Component Replacement,rework,P06,yes,P06,replace missing/misaligned
P08,Reflow Soldering,operation,P06,no,,,
P09,AOI (Automated Optical Inspection),inspection,P08,no,,solder joint fillet > 75%
```

## Common Pitfalls & Gotchas

**1. Confusing process steps with process zones.** I’ve seen teams list "SMT Line" as a single step. That’s a zone, not a step. A step must have a single operator action or machine cycle. "SMT Line" contains 10+ steps. Break it down until each step has one primary function and one measurable output.

**2. Forgetting rework loops.** In production, rework is a real process step with its own failure modes (e.g., "component damage during desoldering"). If you don’t model the rework loop explicitly, you miss the risks. Always add a rework step with a `return_to_step` pointer. The PFMEA must account for the increased risk of reworked units.

**3. Skipping the "decision criteria" for inspection steps.** An inspection step without defined pass/fail criteria is meaningless. In the PFMEA, the decision criteria become the detection controls. If you write "Visual Inspection" as a step but don’t define what you’re looking for, the severity/occurrence/detection ratings are guesses. Always specify the measurable threshold (e.g., "solder paste height > 80% of stencil thickness").

## Try It Yourself

1. **Map your own process:** Take a simple assembly process you know (e.g., manual soldering a through-hole component). Write a process flow with at least 5 atomic steps. Include one inspection step with explicit decision criteria. Validate it using the Python script above.

2. **Decompose a "zone" step:** Find a process flow that has a step like "PCB Assembly" or "Final Test". Break it into at least 3 sub-steps. For each sub-step, identify one potential failure mode that would be invisible at the zone level.

3. **Add a rework loop:** Take the flow from task 1 and add a rework step after the inspection. Define the return step. Then write one failure mode for the rework step itself (e.g., "component pad lifted during desoldering").

## Next Up

Tomorrow: **PFMEA for PCB Assembly: SMT, Reflow & Inspection Failure Modes** — we’ll take the process flow from today and populate it with real failure modes for solder paste printing, pick-and-place, reflow profiling, and AOI. Expect specific severity/occurrence/detection ratings and control strategies for each.
