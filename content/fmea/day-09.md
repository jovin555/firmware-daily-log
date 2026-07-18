---
title: "Day 09: RPN vs Action Priority (AP): Old vs New AIAG-VDA Approach"
date: 2026-07-18
tags: ["til", "fmea", "rpn", "action-priority"]
---

## What I Explored Today

Today I dug into the single most controversial change in the 2019 AIAG & VDA FMEA Handbook: the replacement of the traditional Risk Priority Number (RPN) with the Action Priority (AP) matrix. For years, teams have been using the product of Severity (S), Occurrence (O), and Detection (D) to decide which failure modes need action. The new standard argues that RPN is mathematically and logically flawed, and introduces AP as a more deterministic, threshold-based system. I spent the afternoon mapping our existing PFMEA data into AP tables and comparing the outcomes. The results were sobering—several high-RPN items dropped to Medium or Low AP, while some moderate-RPN items shot up to High AP. This changes how we allocate engineering resources.

## The Core Concept

The old RPN = S × O × D is deceptively simple, but it has three fundamental problems:

1. **Non-linear scaling**: An RPN of 100 can come from (S=10, O=10, D=1) or (S=5, O=5, D=4). The first scenario is a catastrophic failure that is nearly impossible to prevent but easily detected. The second is a moderate failure that happens occasionally and is hard to detect. RPN treats them identically, but the engineering response is completely different.

2. **False precision**: Multiplying ordinal rankings (1-10) produces a number from 1 to 1000, implying a precision that doesn't exist. Is an RPN of 256 really worse than 243? The difference is meaningless.

3. **Severity blindness**: RPN allows high-severity failures (S=9 or 10) to be "averaged down" by low O or D values. The AIAG & VDA handbook explicitly states: *"If Severity is 9-10, the Action Priority is always High, regardless of Occurrence or Detection."* RPN would never enforce this.

The AP system uses a 10×10×10 lookup table (yes, 1000 cells) that maps every combination of S, O, and D to one of three levels: **High (H)**, **Medium (M)**, or **Low (L)**. The logic is:
- **High AP**: Action is *required*. Must reduce S, O, or D.
- **Medium AP**: Action is *recommended*. Evaluate cost-benefit.
- **Low AP**: Action is *optional*. Acceptable as-is.

The table is not symmetric. For example, (S=9, O=2, D=1) is High AP because S=9 overrides everything. (S=5, O=8, D=8) might be Medium AP because while detection is poor, severity is moderate.

## Key Commands / Configuration / Code

Here's a Python snippet to implement the AP lookup logic. This is what I use to batch-convert legacy RPN data.

```python
# action_priority.py — AIAG & VDA Action Priority Lookup
# Usage: python action_priority.py --severity 9 --occurrence 5 --detection 3

import argparse

def get_action_priority(s, o, d):
    """
    Returns 'H', 'M', or 'L' based on AIAG & VDA 1st Edition AP matrix.
    This is a simplified subset — full table has 1000 entries.
    """
    # Rule 1: Severity 9-10 is always High
    if s >= 9:
        return 'H'
    
    # Rule 2: Severity 8 with high occurrence or poor detection
    if s == 8:
        if o >= 5 or d >= 5:
            return 'H'
        else:
            return 'M'
    
    # Rule 3: Severity 5-7 — medium range
    if 5 <= s <= 7:
        if o >= 6 and d >= 6:
            return 'H'
        elif o >= 4 or d >= 4:
            return 'M'
        else:
            return 'L'
    
    # Rule 4: Severity 2-4 — low severity
    if 2 <= s <= 4:
        if o >= 7 and d >= 7:
            return 'M'
        else:
            return 'L'
    
    # Severity 1 — always Low
    return 'L'

def main():
    parser = argparse.ArgumentParser(description='AP Lookup Tool')
    parser.add_argument('--severity', type=int, required=True, help='Severity (1-10)')
    parser.add_argument('--occurrence', type=int, required=True, help='Occurrence (1-10)')
    parser.add_argument('--detection', type=int, required=True, help='Detection (1-10)')
    args = parser.parse_args()
    
    ap = get_action_priority(args.severity, args.occurrence, args.detection)
    print(f"AP: {ap}")

if __name__ == '__main__':
    main()
```

To use it in a batch conversion of an existing FMEA spreadsheet (CSV format):

```bash
# Convert legacy RPN data to AP
cat legacy_fmea.csv | awk -F',' '{print $2, $3, $4}' | while read s o d; do
    python action_priority.py --severity $s --occurrence $o --detection $d
done
```

## Common Pitfalls & Gotchas

1. **Don't try to "average" AP across multiple failure modes.** AP is per failure mode per cause. A single failure mode with multiple causes can have different AP values for each cause. I've seen teams try to roll up AP to the function level—don't. The AP table is designed for the cause-effect chain.

2. **The AP table is not a replacement for engineering judgment.** If your team has historical data showing that a Medium AP failure caused a recall, you still act on it. The AP system is a *starting point* for prioritization, not a final verdict. The handbook says: *"The AP levels are intended to guide the team, not to replace their expertise."*

3. **Beware of "AP inflation" when migrating from RPN.** Teams accustomed to RPN thresholds (e.g., RPN > 200 = action required) may panic when they see many items become High AP. This is normal. The AP system is more conservative on high-severity items. Conversely, some legacy "critical" RPN items may drop to Low AP if severity was low. This is correct behavior—don't artificially inflate ratings to keep them "actionable."

## Try It Yourself

1. **Map your top 10 legacy RPN items to AP.** Take your current PFMEA or DFMEA, pick the 10 highest-RPN failure modes, and manually look up their AP using the AIAG & VDA table (available in the handbook or online). Note how many change priority level. Which ones surprised you?

2. **Write a simple AP calculator for your team.** Use the Python snippet above as a starting point, but extend it to read a CSV with columns `S, O, D` and output a new column `AP`. Run it on your entire FMEA database. Compare the distribution of H/M/L vs your old RPN thresholds.

3. **Debate a "borderline" case with a colleague.** Find a combination like (S=7, O=5, D=5). According to the simplified rules above, this is Medium AP. Discuss: would you still allocate resources to reduce detection (D) from 5 to 3? What if the part is a brake caliper? The goal is to internalize that AP is a guide, not a rule.

## Next Up

Tomorrow: **DFMEA Deep Dive: Design Interfaces & Boundary Diagrams**. We'll move from risk prioritization to the foundational tool for understanding system interactions—boundary diagrams. I'll show you how to map physical, energy, and information flows between components, and how missing an interface is the #1 cause of late-stage DFMEA failures.
