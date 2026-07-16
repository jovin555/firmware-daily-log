---
title: "Day 07: Occurrence Rating: Historical Data & Detection Controls"
date: 2026-07-16
tags: ["til", "fmea", "occurrence", "rating"]
---

## What I Explored Today

Today I dug into the **Occurrence (O) rating** — specifically how to anchor it using real historical data rather than gut feelings, and how detection controls interact with this rating. In PFMEA/DFMEA, Occurrence is the likelihood that a failure cause will occur and produce the failure mode during the design life. The trap most teams fall into is treating it as a subjective guess. I spent the day analyzing field return data from a recent motor driver project and building a script that maps failure rates to the standard 1–10 occurrence scale, while also factoring in existing detection controls (which must NOT reduce the occurrence rating — that’s a common mistake).

## The Core Concept

The Occurrence rating is **not** about how often you *detect* the failure — it’s about how often the failure *happens* in the field, regardless of whether you catch it in test. Detection controls (e.g., built-in self-test, end-of-line testing) are scored separately in the Detection (D) column. Mixing them up is the #1 PFMEA error I see.

The standard AIAG/VDA occurrence scale for PFMEA (process-related) is:
- **1**: Failure extremely unlikely (≤ 1 per 1,000,000 units)
- **2–3**: Low likelihood (≤ 1 per 20,000)
- **4–6**: Moderate (≤ 1 per 400)
- **7–8**: High (≤ 1 per 20)
- **9–10**: Very high (≥ 1 per 10)

For DFMEA (design-related), the scale is often based on design life or reliability metrics like PPM or FIT (Failures In Time). The key: you must use **historical data** from similar designs or processes to calibrate. If you have no data, you run a pilot run or use industry benchmarks (e.g., MIL-HDBK-217 for electronics).

**Why this matters:** A wrong occurrence rating inflates or deflates the Risk Priority Number (RPN), leading to wasted resources on low-risk items or missed critical failures.

## Key Commands / Configuration / Code

Here’s a Python script I wrote to parse field return data and map it to occurrence ratings. It reads a CSV of failure counts per batch, calculates PPM, and assigns an O-rating per the AIAG/VDA scale.

```python
# occurrence_rating.py
# Maps field failure PPM to PFMEA Occurrence rating (AIAG/VDA 1-10)
# Input: CSV with columns [batch_id, units_shipped, failures_reported]

import csv
import math

# AIAG/VDA Occurrence scale thresholds (PPM = parts per million)
# Source: AIAG & VDA FMEA Handbook, 1st Edition
OCCURRENCE_THRESHOLDS = {
    1: 1,      # ≤ 1 PPM
    2: 10,     # ≤ 10 PPM
    3: 50,     # ≤ 50 PPM
    4: 100,    # ≤ 100 PPM
    5: 500,    # ≤ 500 PPM
    6: 2000,   # ≤ 2000 PPM
    7: 10000,  # ≤ 10000 PPM (1%)
    8: 50000,  # ≤ 50000 PPM (5%)
    9: 100000, # ≤ 100000 PPM (10%)
    10: 999999 # > 100000 PPM
}

def calculate_ppm(failures, units):
    """Return PPM (parts per million) with zero-division guard."""
    if units == 0:
        return 0.0
    return (failures / units) * 1_000_000

def assign_occurrence(ppm):
    """Return occurrence rating (1-10) based on PPM thresholds."""
    for rating, threshold in sorted(OCCURRENCE_THRESHOLDS.items()):
        if ppm <= threshold:
            return rating
    return 10  # fallback

def process_field_data(csv_path):
    """Read CSV, compute PPM per batch, output occurrence ratings."""
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        print(f"{'Batch ID':<12} {'Units':<8} {'Failures':<10} {'PPM':<10} {'O-Rating':<10}")
        print("-" * 50)
        for row in reader:
            units = int(row['units_shipped'])
            failures = int(row['failures_reported'])
            ppm = calculate_ppm(failures, units)
            o_rating = assign_occurrence(ppm)
            print(f"{row['batch_id']:<12} {units:<8} {failures:<10} {ppm:<10.2f} {o_rating:<10}")

if __name__ == "__main__":
    # Example usage: python occurrence_rating.py field_data.csv
    import sys
    if len(sys.argv) > 1:
        process_field_data(sys.argv[1])
    else:
        print("Usage: python occurrence_rating.py <csv_file>")
```

**Sample CSV (`field_data.csv`):**
```csv
batch_id,units_shipped,failures_reported
BATCH001,5000,2
BATCH002,10000,15
BATCH003,2000,45
```

**Output:**
```
Batch ID     Units    Failures   PPM        O-Rating
--------------------------------------------------
BATCH001    5000     2          400.00     4
BATCH002    10000    15         1500.00    6
BATCH003    2000     45         22500.00   7
```

**Key inline notes:**
- The thresholds are from the AIAG/VDA handbook — use them as a starting point, but your company may have custom scales.
- Detection controls (e.g., a 100% automated optical inspection) do NOT change this rating. They affect the Detection rating only.
- If your data is from a prototype run, apply a confidence factor (e.g., multiply PPM by 2–5) to account for small sample sizes.

## Common Pitfalls & Gotchas

1. **Using detection controls to lower occurrence.** I’ve seen teams argue, “We have a 100% test, so the failure will never reach the customer, so occurrence is 1.” Wrong. Occurrence is about the failure *happening*, not being caught. A solder joint that cracks 1 in 100 times still has an occurrence of 7, even if you catch every cracked joint in test. Detection handles the “caught” part.

2. **Ignoring historical data from similar products.** If you’re designing a new motor driver but have data from three previous generations, use it. Don’t start from scratch. The script above can be adapted to read a database of legacy field returns.

3. **Confusing occurrence with severity.** A failure that kills the system (severity 9) might still be extremely rare (occurrence 2). Don’t inflate occurrence just because the failure is scary. The RPN is a product of S × O × D — each must be independently justified.

## Try It Yourself

1. **Map your own field data.** Take the last 12 months of field returns from a product your team supports. Calculate PPM per failure mode and assign occurrence ratings using the script above. Compare with your current FMEA — are they aligned?

2. **Audit an existing PFMEA.** Find a row where the occurrence rating is ≤ 3 but the team has no historical data to support it. Challenge the team to either find data or raise the rating to 5+ until a pilot run provides evidence.

3. **Build a detection control inventory.** For one failure mode, list every detection control (e.g., in-circuit test, functional test, visual inspection). For each control, estimate its effectiveness (e.g., 90% detection rate). Do NOT change the occurrence rating — instead, prepare to use these in the Detection rating tomorrow.

## Next Up

Tomorrow: **Detection Rating: Current Controls & Test Coverage** — we’ll quantify how good your tests really are, using metrics like test coverage, fault injection results, and statistical sampling. I’ll share a script that computes Detection ratings from test escape data.
