---
title: "Day 06: Severity Rating: AIAG-VDA Scales & Customer Impact"
date: 2026-07-15
tags: ["til", "fmea", "severity", "rating"]
---

## What I Explored Today

Today I dug into the AIAG & VDA FMEA Handbook's severity rating tables—specifically how they differ from the legacy AIAG 4th Edition scales. The 2021 harmonized standard introduces a 1-to-10 scale with explicit customer-facing criteria, including separate tables for Design FMEA (DFMEA) and Process FMEA (PFMEA). The key shift is that severity is now evaluated strictly on the *effect* of a failure, independent of any detection or occurrence controls. I spent the afternoon mapping real-world failure modes from a motor controller project to the new scale, and the clarity is a significant improvement—but only if you apply the criteria literally.

## The Core Concept

Severity is a ranking of the seriousness of a failure mode's effect on the customer (end user, next operation, or regulatory body). It is the "S" in RPN (Risk Priority Number) and AP (Action Priority). In the AIAG-VDA framework, severity is assigned *before* considering any controls—this is a hard rule. The scale is not symmetric: a rating of 9 or 10 is reserved for safety or regulatory non-compliance, while 7-8 covers loss of primary function, and 5-6 covers degraded performance or comfort.

Why does this matter? Because severity drives the entire risk assessment. If you mis-rank a failure that causes a vehicle fire (severity 10) as a mere annoyance (severity 5), your RPN/AP will be artificially low, and you'll miss critical mitigation actions. Conversely, inflating a cosmetic defect to severity 8 wastes resources on unnecessary design changes. The AIAG-VDA scale forces you to be explicit about the *customer impact*—where "customer" includes downstream manufacturing, end users, and regulatory agencies.

The DFMEA severity table uses criteria like "Loss of vehicle control" (10), "Loss of primary function" (8), "Degraded performance" (6), and "No effect" (1). The PFMEA table mirrors this but adds "Safety of operator" (9-10) and "Line stoppage > 1 hour" (8). The critical nuance: if a failure mode has multiple effects, you use the *highest* severity rating across all effects.

## Key Commands / Configuration / Code

Below is a Python snippet I use to automate severity assignment from a lookup table. This is not a replacement for engineering judgment—it's a consistency checker.

```python
# severity_lookup.py — AIAG-VDA DFMEA Severity Table (v1.0)
# Usage: python severity_lookup.py --effect "Loss of primary function"

import argparse

# DFMEA severity table from AIAG-VDA Handbook (2021)
# Keys: effect description (lowercase), value: (rating, criteria)
DFMEA_SEVERITY = {
    "safety: regulatory non-compliance": (10, "Failure results in potential safety issue or non-compliance with regulation without warning"),
    "safety: regulatory non-compliance with warning": (9, "Failure results in potential safety issue or non-compliance with regulation with warning"),
    "loss of primary function": (8, "Vehicle/item inoperable; loss of primary function"),
    "degradation of primary function": (7, "Primary function degraded but still operable"),
    "loss of secondary function": (6, "Secondary function inoperable; comfort/convenience loss"),
    "degradation of secondary function": (5, "Secondary function degraded; reduced comfort"),
    "annoyance": (4, "Customer notices defect; audible noise, vibration, harshness (NVH)"),
    "minor defect": (3, "Defect noticed by most customers; no performance loss"),
    "very minor defect": (2, "Defect noticed by discriminating customers; no performance loss"),
    "no effect": (1, "No discernible effect"),
}

def lookup_severity(effect: str) -> tuple:
    """Return (rating, criteria) for a given effect string."""
    effect_lower = effect.strip().lower()
    if effect_lower in DFMEA_SEVERITY:
        return DFMEA_SEVERITY[effect_lower]
    # Fuzzy match: find closest key containing the input
    for key, (rating, criteria) in DFMEA_SEVERITY.items():
        if effect_lower in key or key in effect_lower:
            return (rating, criteria)
    raise ValueError(f"Effect '{effect}' not found in severity table.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIAG-VDA DFMEA Severity Lookup")
    parser.add_argument("--effect", required=True, help="Failure effect description")
    args = parser.parse_args()
    rating, criteria = lookup_severity(args.effect)
    print(f"Severity Rating: {rating}")
    print(f"Criteria: {criteria}")
```

**Example run:**
```bash
$ python severity_lookup.py --effect "Loss of primary function"
Severity Rating: 8
Criteria: Vehicle/item inoperable; loss of primary function
```

This script is part of a CI pipeline that validates FMEA worksheets—if an engineer assigns a severity 6 to "loss of primary function," the pipeline flags it.

## Common Pitfalls & Gotchas

1. **Confusing severity with occurrence.** I've seen teams assign severity 9 to a failure that happens frequently (e.g., "connector misalignment every 10th unit"). The frequency is *occurrence*, not severity. Severity is the *consequence* if the failure occurs—even if it's rare. A battery thermal runaway is severity 10 regardless of whether it happens once in a million units.

2. **Using the wrong table for the FMEA type.** The DFMEA severity table uses "vehicle" language; the PFMEA table uses "operator/line" language. Applying DFMEA criteria to a process failure (e.g., "operator injury" rated as severity 8 instead of 9/10) is a common error. Always check the table header.

3. **Rating based on current controls.** The AIAG-VDA handbook explicitly states: "Severity is assigned without consideration of current controls." If you have a redundant brake circuit that prevents loss of braking, the severity of "brake failure" is still 10—the control reduces *detection* or *occurrence*, not severity. I've had to correct FMEAs where engineers lowered severity because "we have a backup sensor." That's a detection control, not a severity reducer.

## Try It Yourself

1. **Map three failure modes from your current project** to the AIAG-VDA DFMEA severity table. For each, write the effect description exactly as it would appear in the table (e.g., "degradation of primary function"). Then assign the rating. Compare with your team's existing FMEA—any discrepancies?

2. **Write a test case** for the Python script above. Add a new effect like "loss of steering assist" and verify it returns the correct severity (should be 8 if it's a primary function). Then modify the script to handle multi-word effects with fuzzy matching.

3. **Audit an existing PFMEA** from a past project. For each failure mode, check if severity was assigned based on *effect* alone, or if controls were implicitly considered. Flag any rows where severity seems artificially low (e.g., "operator cut" rated as 6 when the PFMEA table says 9-10 for safety).

## Next Up

Tomorrow, I'll tackle **Occurrence Rating: Historical Data & Detection Controls**—how to use field return data, production test yields, and process capability indices (Cpk) to assign the "O" rating. We'll also cover the AIAG-VDA occurrence tables for both DFMEA and PFMEA, and why "we've never seen it fail" is not a valid occurrence rating.
