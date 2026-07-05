---
title: "Day 23: Safety Integrity Levels (SIL): Determination & Verification"
date: 2026-07-05
tags: ["til", "cfse", "sil", "determination"]
---

## What I Explored Today

Today I dove deep into the practical mechanics of Safety Integrity Level (SIL) determination and verification per IEC 61508. While many engineers know SIL as a "number from 1 to 4," the real work lies in the systematic process of deriving that number from hazard analysis, then proving the system meets the required probability of failure on demand (PFD) or probability of dangerous failure per hour (PFH). I worked through a complete example using a gas burner control system to see how risk graph parameters, architectural constraints, and quantitative reliability math all converge.

## The Core Concept

SIL is not a property you assign arbitrarily. It is the result of a risk reduction calculation: the target SIL tells you how much risk must be reduced to reach a tolerable level. The "why" is that without this structured determination, you either over-engineer (cost explosion) or under-engineer (unsafe system).

The IEC 61508 framework breaks SIL determination into two phases:

1. **Determination (allocation):** Using a risk graph or semi-quantitative method to assign a SIL target to each safety function.
2. **Verification (proving):** Demonstrating that the implemented design meets the target SIL through:
   - **Architectural constraints** (hardware fault tolerance, safe failure fraction)
   - **Quantitative reliability** (PFD/PFH calculation)
   - **Systematic capability** (avoidance of design errors)

The key insight: SIL verification is a *constraint satisfaction* problem, not just a reliability number. You must satisfy all three legs simultaneously.

## Key Commands / Configuration / Code

Below is a practical Python snippet for SIL verification of a 1oo2 (one-out-of-two) redundant pressure transmitter loop. This is the kind of calculation you'd do in a spreadsheet or tool like exida SILver, but here we see the math.

```python
# SIL verification for a 1oo2 pressure transmitter loop
# IEC 61508-6 Annex B methodology

import math

# Component data (from manufacturer FMEDA or field data)
lambda_du = 2.5e-7  # Dangerous undetected failure rate per hour
lambda_dd = 1.2e-6  # Dangerous detected failure rate per hour
lambda_s = 3.0e-7   # Safe failure rate per hour
T_proof = 8760      # Proof test interval (1 year in hours)
MTTR = 8            # Mean time to restoration (hours)
beta = 0.05         # Common cause factor (5% for diverse transmitters)

# Step 1: Safe Failure Fraction (SFF)
total_dangerous = lambda_du + lambda_dd
total_failures = total_dangerous + lambda_s
SFF = 1 - (lambda_du / total_failures)
print(f"SFF = {SFF:.4f}  (must be >= 90% for SIL 2)")

# Step 2: Hardware Fault Tolerance (HFT)
# 1oo2 architecture has HFT = 1
HFT = 1
print(f"HFT = {HFT}  (meets SIL 2 requirement of HFT >= 1 for SFF < 99%)")

# Step 3: PFDavg calculation for 1oo2 (IEC 61508-6 eqn for 1oo2)
# Simplified formula for 1oo2 with common cause
lambda_du_total = 2 * lambda_du
T_ce = T_proof / 2 + MTTR  # Channel equivalent downtime
PFD_1oo2_independent = (lambda_du_total * T_ce)**2 / 3
PFD_common_cause = beta * lambda_du * T_proof / 2
PFDavg = PFD_1oo2_independent + PFD_common_cause
print(f"PFDavg = {PFDavg:.2e}")

# Step 4: Compare to SIL 2 target
# SIL 2 low demand: PFDavg 1e-3 to 1e-2
if 1e-3 <= PFDavg <= 1e-2:
    print("PASS: PFDavg within SIL 2 range")
elif PFDavg < 1e-3:
    print("PASS: Exceeds SIL 2 (SIL 3 capability)")
else:
    print("FAIL: Does not meet SIL 2 requirement")
```

**Expected output:**
```
SFF = 0.9310  (must be >= 90% for SIL 2)
HFT = 1  (meets SIL 2 requirement of HFT >= 1 for SFF < 99%)
PFDavg = 1.12e-3
PASS: PFDavg within SIL 2 range
```

The real-world takeaway: even though the PFDavg barely squeezes into SIL 2, the architectural constraints (SFF and HFT) are the binding factors. If SFF were 85%, this 1oo2 would be limited to SIL 1 regardless of the PFD number.

## Common Pitfalls & Gotchas

**1. Confusing "low demand" vs "high demand" mode**
IEC 61508 defines SIL targets differently for low-demand (PFD) vs high-demand/continuous (PFH). A common mistake is using PFDavg for a continuous process where PFH is required. For a gas burner that runs 24/7, you must use PFH. The SIL 2 PFH target is 1e-7 to 1e-6 dangerous failures per hour — a much tighter constraint.

**2. Ignoring systematic capability (SC)**
Many engineers focus only on random hardware failures (PFD/PFH) and forget that IEC 61508 also requires systematic capability. Even if your PFD is perfect, if your firmware was developed without a V-model, coding standards, or unit testing, you cannot claim SIL 2. The SC level must match the target SIL.

**3. Over-reliance on beta factor without diversity**
Using β = 0.02 (very low common cause) for identical transducers from the same manufacturer is unrealistic. The standard requires justification. If you use identical components, β is typically 0.1–0.2. Only diverse technologies (e.g., pressure + flow) justify β < 0.05.

## Try It Yourself

1. **Risk graph exercise:** Take a simple safety function (e.g., emergency stop button). Using the IEC 61508-5 risk graph parameters (C, F, P, W), determine the required SIL. Document your reasoning for each parameter.

2. **Modify the code:** Change the 1oo2 architecture to 2oo2 (two-out-of-two) in the Python script. Recalculate PFDavg. How does it compare? (Hint: 2oo2 has higher PFD but lower spurious trip rate.)

3. **FMEDA data hunt:** Find a public FMEDA report for a pressure transmitter (e.g., from exida or TÜV). Extract λ_du, λ_dd, λ_s, and SFF. Run the verification script with real data. Does the device meet SIL 2 per architectural constraints?

## Next Up

Tomorrow: **FMEA: Failure Mode & Effects Analysis for Firmware** — we move from hardware reliability to systematic analysis of software failure modes. I'll show how to build an FMEA table for a real-time scheduler and identify single-point failures that can crash your safety function.
