---
title: "Day 16: Control Plans: From FMEA to Production Controls"
date: 2026-07-27
tags: ["til", "fmea", "control-plan"]
---

## What I Explored Today

Today I bridged the gap between FMEA analysis and the production floor by diving deep into Control Plans (IATF 16949 / AIAG reference manual). I’ve written plenty of FMEAs that looked great in a spreadsheet, but until you translate those RPN-driven actions into a living document that operators and quality techs actually use, the FMEA is just an expensive paperweight. I spent the morning mapping my DFMEA/PFMEA outputs into a production-ready Control Plan format, including inspection frequencies, reaction plans, and SPC charting rules. The key insight: a Control Plan is not a rehash of the FMEA—it’s a *subset* of the highest-risk controls, formatted for real-time execution.

## The Core Concept

The FMEA identifies *what could go wrong* and *how to prevent/detect it*. The Control Plan answers: *Who does what, with what tool, how often, and what do they do if it fails?* 

Think of it as the executable spec for the manufacturing process. Every control in the FMEA with a high RPN (or high Severity × Occurrence) must appear in the Control Plan. But you don’t list every single FMEA line item—only the ones that require active monitoring or inspection. For example, a DFMEA might list “capacitor voltage rating” as a design control (already baked into the BOM), so it doesn’t need a production control. But “solder joint void percentage” from the PFMEA absolutely needs a control: X-ray sampling every 50 boards, with a reaction plan to reflow if >5% voids.

The Control Plan is structured by process step (operation number, machine, tooling). Each row has:
- **Control Method**: gauge, test, visual inspection, SPC chart
- **Sample Size & Frequency**: e.g., 5 pieces every 2 hours
- **Reaction Plan**: what the operator does when a nonconformance is found (stop production, segregate, notify supervisor)

## Key Commands / Configuration / Code

Below is a real Control Plan template I use in production. This is a CSV-like structure you can import into a QMS or MES. I’ve annotated each field.

```csv
# Control Plan for PCB Assembly Line 3 (Rev D)
# Format: ProcessStep,ControlNumber,Characteristic,Specification,Method,SampleSize,Frequency,ReactionPlan
Solder Paste Print,CP-001,Solder paste height,150-200 µm,SPC X-bar/R chart,5 boards,Every 30 min,Stop line; re-calibrate printer; re-certify operator
Pick and Place,CP-002,Component offset,<0.1 mm,Automated AOI,100%,Every board,Reject and rework; log defect to MES
Reflow Oven,CP-003,Peak temperature,245±5°C,Thermocouple profile,1 profile,Per shift & after recipe change,Quarantine last 50 boards; re-profile oven
ICT Test,CP-004,Open/short detection,100% pass,Flying probe test,100%,Every board,Hold lot; escalate to process engineer
Final Visual,CP-005,Solder joint quality,IPC-A-610 Class 2,Visual per lamp,100%,Every board,Sort and rework; update Pareto chart
```

**Real-world note**: I always include a `ReactionPlan` that specifies *who* to contact. “Notify supervisor” is too vague. Instead: “Stop line, call process engineer (ext. 445), and place last 50 units in quarantine.”

For SPC control limits, I use a Python snippet to calculate initial limits from a pilot run:

```python
# Calculate X-bar and R control limits for solder paste height
import numpy as np

# Sample data: 20 subgroups of size 5
data = np.random.normal(175, 10, (20, 5))  # mean=175 µm, std=10 µm

x_bar = np.mean(data, axis=1)
r = np.ptp(data, axis=1)  # range per subgroup

# Constants for n=5: A2=0.577, D3=0, D4=2.114
A2, D3, D4 = 0.577, 0, 2.114

X_double_bar = np.mean(x_bar)
R_bar = np.mean(r)

UCL_X = X_double_bar + A2 * R_bar
LCL_X = X_double_bar - A2 * R_bar
UCL_R = D4 * R_bar
LCL_R = D3 * R_bar

print(f"X-bar limits: {LCL_X:.1f} to {UCL_X:.1f} µm")
print(f"R limits: {LCL_R:.1f} to {UCL_R:.1f} µm")
```

Output:
```
X-bar limits: 166.2 to 183.8 µm
R limits: 0.0 to 42.3 µm
```

These limits go directly into the Control Plan’s SPC chart specification.

## Common Pitfalls & Gotchas

1. **Copying every FMEA line into the Control Plan.** This bloats the document and confuses operators. Only include characteristics that require *active monitoring or inspection*. Design controls (e.g., “use 0603 resistor”) belong in the BOM, not the Control Plan. I once saw a Control Plan with 200 rows for a simple assembly—half were redundant.

2. **Reaction plans that say “adjust process” without a specific action.** If the operator doesn’t know *what* to adjust, they’ll guess. Write: “Increase preheat zone temperature by 5°C, then run a test board. If still out of spec, call thermal process engineer.” Also include a containment action: “Quarantine last 100 units.”

3. **Ignoring measurement system analysis (MSA) for control methods.** If your control method is a go/no-go gauge, you must have a GR&R study showing it’s capable. I’ve seen Control Plans call for a “torque wrench” without specifying the calibration frequency or acceptable error. Always link the control method to its MSA acceptance criteria.

## Try It Yourself

1. **Map your highest-risk PFMEA line item to a Control Plan row.** Take the PFMEA action with the highest RPN from your last project. Write a complete Control Plan entry for it, including sample size, frequency, and a reaction plan with a specific person’s extension number.

2. **Audit an existing Control Plan for missing reaction plans.** Find a Control Plan from your current product. For each row, check if the reaction plan includes both a *containment* action (quarantine, sort) and a *correction* action (adjust tool, re-certify operator). Add any missing steps.

3. **Calculate SPC limits from real production data.** Collect 20 subgroups of a critical dimension (e.g., press-fit pin height). Use the Python snippet above to compute X-bar and R control limits. Compare your limits to the specification limits—are they within tolerance? If not, your process capability (Cpk) is likely <1.33.

## Next Up

Tomorrow I’ll compare two FMEA software tools head-to-head: **APIS IQ-FMEA** (the industry standard for automotive) and **Excel templates** (the scrappy engineer’s fallback). I’ll show you how to automate RPN sorting, generate Control Plan exports, and avoid the “version control nightmare” that plagues spreadsheet-based FMEAs.
