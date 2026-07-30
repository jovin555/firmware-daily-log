---
title: "Day 19: Common FMEA Mistakes & Avoiding Generic Failure Modes"
date: 2026-07-30
tags: ["til", "fmea", "best-practices", "pitfalls"]
---

## What I Explored Today

After weeks of building DFMEAs and PFMEAs for embedded systems, I hit a wall reviewing a colleague's FMEA for a CAN bus transceiver module. Every failure mode read like a generic template: "Component fails," "Communication lost," "Signal degraded." None of it was actionable. Today I dug into why generic failure modes are the #1 killer of FMEA value, and how to replace them with specific, physically-rooted descriptions that actually drive design changes.

## The Core Concept

A generic failure mode is a placeholder, not an analysis. When you write "Resistor fails open," you've described a symptom, not a failure mechanism. The FMEA becomes a checklist exercise, not a design tool. The real power comes when you describe *how* the failure occurs in terms of the physics, environment, or interaction that causes it.

For embedded systems, the most common trap is treating the FMEA like a component datasheet. Instead, think in terms of **functions** and **interfaces**. A resistor doesn't "fail open" in isolation—it fails because of a specific stressor: overcurrent exceeding its power rating, thermal cycling cracking the solder joint, or ESD punch-through in a high-impedance node.

The rule I now enforce: every failure mode must answer "What specific physical or electrical condition causes this?" If you can't describe the mechanism, you don't understand the risk.

## Key Commands / Configuration / Code

Here's a practical checklist I use to audit failure modes. I run this against every FMEA line item before review.

```python
# fmea_audit.py — Check failure mode specificity
# Run against your FMEA spreadsheet exported as CSV

import csv
import re

GENERIC_PATTERNS = [
    r'\bfails?\b',           # "fails", "failure"
    r'\bdegrades?\b',        # "degrades", "degradation"
    r'\blost\b',             # "lost communication"
    r'\bintermittent\b',     # "intermittent connection"
    r'\bno\s+output\b',      # "no output"
    r'\bopen\b',             # "open circuit" (without mechanism)
    r'\bshort\b',            # "short circuit" (without mechanism)
]

def is_generic(failure_mode):
    """Returns True if failure mode matches generic patterns."""
    for pattern in GENERIC_PATTERNS:
        if re.search(pattern, failure_mode, re.IGNORECASE):
            return True
    return False

def audit_fmea(csv_path):
    """Audit an FMEA CSV for generic failure modes."""
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        issues = []
        for row_num, row in enumerate(reader, start=2):
            fm = row.get('Failure Mode', '')
            if is_generic(fm):
                issues.append((row_num, fm))
        return issues

# Example usage
issues = audit_fmea('can_transceiver_fmea.csv')
for row, fm in issues:
    print(f"Row {row}: Generic failure mode — '{fm}'")
```

**Configuration tip**: Add this to your CI pipeline. When engineers commit FMEA updates, run the audit and block merges if generic patterns exceed 10% of line items.

## Common Pitfalls & Gotchas

**1. Confusing failure mode with failure effect**
I see this constantly: "Failure mode: System does not boot." That's an effect. The failure mode is the *cause* at the component or interface level. For a boot failure on an STM32, the mode might be: "POR capacitor (C12) ESR > 10Ω due to electrolyte dry-out, causing VDD ramp rate < 0.5V/ms, below the BOR threshold." Now you can act: specify low-ESR tantalum or increase capacitance margin.

**2. Using "open" and "short" as complete descriptions**
"Resistor opens" tells me nothing. Is it a current-sense resistor seeing 10x rated power? A pull-up on a high-voltage line? A 0402 package cracking from PCB flex? Write: "Resistor R4 (10Ω, 0603) fails open due to peak inrush current exceeding 2A for >100μs during hot-plug, exceeding its 0.125W rating." Now you know to add an inrush limiter or uprate the resistor.

**3. Ignoring environmental coupling**
Embedded systems fail at interfaces. A common generic mode: "Moisture ingress." Specific: "Humidity >85% RH at 60°C causes condensation on uncoated header pins J3, creating leakage path >1MΩ between VBAT and GND, pulling RTC backup below 2.0V." That tells you to specify conformal coating or select a sealed connector.

## Try It Yourself

1. **Audit your last FMEA**: Export your most recent DFMEA or PFMEA to CSV. Run the Python script above. For every flagged generic failure mode, rewrite it using the format: "[Component/Interface] fails [specific mechanism] due to [stressor], causing [measurable electrical/mechanical change]."

2. **Pick one high-severity item**: Find a failure mode with Severity ≥ 8. If the description is generic, rewrite it with a root-cause mechanism. Then ask: "Does this description suggest a new design control or prevention measure I missed?" Add it.

3. **Create a "generic mode" blacklist**: In your team's FMEA template, add a column "Mechanism Description." Make it mandatory. If the mechanism field is empty or contains only generic text, flag it for review before the FMEA is approved.

## Next Up: Full Review & Project: DFMEA/PFMEA for an Embedded Sensor Module

Tomorrow we tie everything together. I'll walk through a complete DFMEA and PFMEA for a real embedded sensor module—a BME280 environmental sensor on I2C with an STM32. We'll apply every technique from the past 19 days: functional decomposition, interface analysis, severity/occurrence/detection scoring, and action prioritization. You'll see how the pieces fit into a single, coherent risk analysis. Bring your own project files—we're going to do a live review.
