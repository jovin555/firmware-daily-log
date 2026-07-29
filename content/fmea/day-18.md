---
title: "Day 18: Integrating FMEA with ISO 26262 / IEC 61508 Hazard Analysis"
date: 2026-07-29
tags: ["til", "fmea", "iso26262", "iec61508"]
---

## What I Explored Today

Today I tackled the practical bridge between FMEA and functional safety standards—specifically how to align a Design FMEA (DFMEA) with the hazard analysis and risk assessment (HARA) required by ISO 26262 (automotive) and IEC 61508 (general industrial). The key insight: FMEA provides the systematic failure mode discovery, while HARA provides the risk classification and safety goal derivation. They are complementary, not redundant, but integrating them poorly wastes effort and can miss critical safety mechanisms.

## The Core Concept

Why integrate? Because standalone FMEA often treats all failures as equally important, while functional safety standards demand a risk-based priority. A DFMEA might list 200 failure modes, but only a subset have safety implications severe enough to require a safety mechanism (ASIL B/C/D or SIL 2/3). Conversely, a HARA might identify hazards without tracing them to specific component failures. Integration closes this gap.

The standard workflow I now follow:

1. **Start with the HARA** — Identify hazards, hazardous events, and derive safety goals (e.g., "The system shall prevent unintended acceleration above 5 m/s²").
2. **Map safety goals to functions** — Each safety goal decomposes into functional safety requirements (FSRs).
3. **Perform DFMEA on the design** — For each function, list failure modes that could violate an FSR.
4. **Cross-reference** — Tag each DFMEA line item with the corresponding safety goal ID. If a failure mode cannot be linked to any safety goal, it’s either a non-safety issue (handled by quality FMEA) or a gap in your HARA.
5. **Use ASIL/SIL in FMEA action priority** — High-severity failure modes (ASIL C/D) demand detection ratings of 6+ or prevention controls with proven effectiveness.

The real engineering value: when you later do FMEDA (Failure Modes, Effects, and Diagnostic Analysis) for safety metrics, your DFMEA becomes the source of truth for failure rate distribution and diagnostic coverage assumptions.

## Key Commands / Configuration / Code

Below is a practical Python snippet I use to cross-reference DFMEA entries with HARA safety goals. This runs as a post-processing step after exporting FMEA data from a spreadsheet or PLM tool.

```python
# cross_ref_fmea_hara.py
# Usage: python cross_ref_fmea_hara.py --fmea fmea_export.csv --hara hara_export.csv

import csv
import sys
import argparse

def load_hara(hara_path):
    """Load HARA safety goals: {goal_id: description}"""
    goals = {}
    with open(hara_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            goals[row['Goal_ID']] = row['Description']
    return goals

def cross_reference(fmea_path, hara_goals):
    """Tag each FMEA row with safety goal info and flag gaps."""
    flagged = []
    with open(fmea_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Expect a column 'Safety_Goal_ID' in FMEA export
            sg_id = row.get('Safety_Goal_ID', '').strip()
            if sg_id and sg_id in hara_goals:
                row['HARA_Status'] = 'Mapped'
                row['Goal_Description'] = hara_goals[sg_id]
            elif sg_id and sg_id not in hara_goals:
                row['HARA_Status'] = 'Orphan'  # Goal ID doesn't exist in HARA
                row['Goal_Description'] = 'UNKNOWN'
            else:
                row['HARA_Status'] = 'No_Safety_Goal'
                row['Goal_Description'] = ''
            flagged.append(row)
    return flagged

def write_output(rows, output_path):
    """Write enriched FMEA to CSV."""
    if not rows:
        return
    fieldnames = rows[0].keys()
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fmea', required=True)
    parser.add_argument('--hara', required=True)
    parser.add_argument('--output', default='fmea_cross_ref.csv')
    args = parser.parse_args()

    hara_goals = load_hara(args.hara)
    enriched = cross_reference(args.fmea, hara_goals)
    write_output(enriched, args.output)
    print(f"Written {len(enriched)} rows to {args.output}")
    orphans = [r for r in enriched if r['HARA_Status'] == 'Orphan']
    if orphans:
        print(f"WARNING: {len(orphans)} orphan safety goal IDs found.")
```

**Expected CSV input format:**

| Function | Failure_Mode | Effect | Severity | Safety_Goal_ID |
|----------|--------------|--------|----------|----------------|
| Accelerator pedal sensing | Sensor stuck at 0V | No throttle response | 8 | SG_ACC_001 |
| Brake light activation | Short to battery | Brake lights always on | 6 | SG_BRK_002 |

## Common Pitfalls & Gotchas

1. **Treating FMEA and HARA as separate silos** — I’ve seen teams complete a full DFMEA, then later do a HARA, and never reconcile them. The result: safety goals that have no traceable failure modes, or failure modes with ASIL ratings that don’t match the HARA severity. Always iterate: HARA → FMEA → update HARA → update FMEA.

2. **Misapplying ASIL decomposition in FMEA** — Engineers sometimes lower the severity rating in FMEA because they plan to use ASIL decomposition (e.g., split an ASIL D requirement into two ASIL B(D) paths). This is wrong. FMEA severity should reflect the *unmitigated* effect. Decomposition is a safety architecture decision, not a FMEA input.

3. **Ignoring systematic failures in FMEA for safety** — ISO 26262 Part 5 requires analysis of systematic failures (e.g., software bugs, requirements errors). A typical DFMEA focuses on random hardware failures. If your DFMEA only lists "resistor opens" and "capacitor shorts," you’re missing systematic failure modes that safety standards demand you address.

## Try It Yourself

1. **Map your existing DFMEA to HARA** — Take your last DFMEA and add a column "Safety_Goal_ID". For each failure mode with Severity ≥ 8, write the corresponding safety goal from your HARA. If you can’t find one, create a new safety goal or flag the failure mode as non-safety.

2. **Run the cross-reference script** — Export your FMEA and HARA as CSVs with the columns shown above. Run the Python script and examine the "Orphan" rows. Investigate why those safety goal IDs exist in FMEA but not in HARA—likely a copy-paste error or a missing hazard.

3. **Audit for systematic failures** — Review your DFMEA and count how many failure modes are systematic (e.g., "algorithm overflow," "state machine deadlock," "timing violation"). If that count is zero, add at least three systematic failure modes to your next revision and assign detection controls (e.g., code review, static analysis).

## Next Up

Tomorrow: **Common FMEA Mistakes & Avoiding Generic Failure Modes** — We’ll dissect the most frequent errors I see in real FMEAs, from "failure mode = component failure" to "detection = we test it eventually," and how to write failure modes that actually drive design changes.
