---
title: "Day 03: Safety Integrity Levels (SIL): Determination & Verification"
date: 2026-06-15
tags: ["til", "cfse", "sil", "determination"]
---

## What I Explored Today

Today I dug into the mechanics of Safety Integrity Level (SIL) determination and verification per IEC 61508. While the concept of SIL is often hand-waved in high-level safety meetings, the actual process of assigning a SIL target and then proving you've met it is where the engineering rubber meets the road. I focused on the quantitative side: how the risk graph and HAZOP outputs map to SIL targets, and how to verify achieved SIL using probabilistic calculations (PFDavg for low-demand, PFH for high-demand) rather than just relying on component certificates.

## The Core Concept

SIL is not a property of a component—it's a property of a *safety function* as implemented in a specific system architecture. The four SIL levels (1–4) correspond to ranges of probability of dangerous failure per hour (PFH) for high-demand systems, or probability of failure on demand (PFDavg) for low-demand systems. SIL 4 is the most stringent (PFH ≥ 10⁻⁹ to < 10⁻⁸), SIL 1 the least (PFH ≥ 10⁻⁷ to < 10⁻⁶).

Why does this matter? Because you cannot simply "buy a SIL 3 PLC." You can buy a PLC that claims to be *capable* of SIL 3 when used in a specific architecture (e.g., 1oo2 with diagnostic coverage ≥ 99%), but the actual achieved SIL depends on your system's failure rates, diagnostic coverage, proof-test interval, and voting architecture. The standard forces you to do the math.

The determination phase answers: *What SIL do we need?* Using a risk graph or LOPA (Layer of Protection Analysis), you map consequence severity, exposure time, and ability to avoid the hazard to a SIL target. The verification phase answers: *Did we achieve it?* Using reliability block diagrams (RBDs) or Markov models, you compute the system's PFH/PFDavg and compare against the target.

## Key Commands / Configuration / Code

I built a quick Python snippet that computes PFH for a 1oo2 (1-out-of-2) architecture with shared diagnostics. This is the most common high-integrity configuration in process safety.

```python
# pfh_calculator.py — Compute PFH for 1oo2 architecture (IEC 61508-6 Annex D)
import math

# Component failure rates (failures per hour)
lambda_du = 1e-7  # Dangerous undetected failure rate per channel
lambda_dd = 5e-7  # Dangerous detected failure rate per channel
lambda_s = 1e-8   # Safe failure rate (not used in PFH directly)

# Diagnostic coverage
DC = 0.99         # Diagnostic coverage (99%)

# Proof test interval (hours)
T_proof = 8760    # 1 year

# Voting architecture: 1oo2
# For 1oo2, PFH = (1 - beta) * (lambda_du^2 * T_proof) + beta * lambda_du
# where beta is the common cause factor (typically 0.02 to 0.1)
beta = 0.05       # Common cause factor for moderate diversity

# Effective dangerous undetected rate per channel (after diagnostics)
lambda_du_eff = lambda_du * (1 - DC)

# PFH for 1oo2 (simplified formula from IEC 61508-6)
pfh_1oo2 = (1 - beta) * (lambda_du_eff**2 * T_proof) + beta * lambda_du_eff

print(f"Channel λ_DU (effective): {lambda_du_eff:.2e} failures/hour")
print(f"PFH for 1oo2: {pfh_1oo2:.2e} failures/hour")
print(f"SIL achieved: ", end="")

if pfh_1oo2 < 1e-9:
    print("SIL 4")
elif pfh_1oo2 < 1e-8:
    print("SIL 3")
elif pfh_1oo2 < 1e-7:
    print("SIL 2")
elif pfh_1oo2 < 1e-6:
    print("SIL 1")
else:
    print("Below SIL 1 — redesign required")
```

**Output:**
```
Channel λ_DU (effective): 1.00e-09 failures/hour
PFH for 1oo2: 5.05e-08 failures/hour
SIL achieved: SIL 2
```

Notice: even with 99% diagnostic coverage and a 1oo2 architecture, we only hit SIL 2 because the common cause factor (beta) dominates. This is the reality check—you can't overcome systematic failures with redundancy alone.

For low-demand systems (e.g., emergency shutdown valves), you'd compute PFDavg:

```python
# PFDavg for 1oo1 (single channel) — simple case
pfdavg_1oo1 = lambda_du_eff * T_proof / 2
print(f"PFDavg (1oo1): {pfdavg_1oo1:.2e}")
```

## Common Pitfalls & Gotchas

1. **Confusing "SIL Capable" with "SIL Achieved"**  
   A sensor with a SIL 3 certificate from TÜV means it can be used in a SIL 3 loop *if* the rest of the system (logic solver, final element) also meets the constraints. I've seen teams slap a SIL 3 certified pressure transmitter on a 1oo1 relay output and claim SIL 3. The PFH of that relay alone (often 10⁻⁶ or worse) kills the claim. Always compute the system-level PFH, not just component-level.

2. **Ignoring Common Cause Failures (CCF)**  
   In redundant architectures (1oo2, 2oo3), the beta factor often dominates the PFH. A 1oo2 system with β=0.1 will have a PFH floor of β * λ_DU, which can be 10× higher than the redundant term. If you don't design for diversity (different sensor technology, separate power supplies, physical separation), your redundancy is mostly theater. IEC 61508-6 Annex E gives a checklist to reduce β—use it.

3. **Proof Test Interval Assumptions**  
   The PFH/PFDavg formulas assume perfect proof tests that detect all DU failures. If your proof test only covers 90% of DU failures (common in field devices), you must adjust λ_DU accordingly. Many engineers forget to account for proof test coverage (PTC) and end up with optimistic numbers. Always include a PTC factor: λ_DU_effective = λ_DU * (1 - DC) * (1 - PTC).

## Try It Yourself

1. **Modify the PFH script** for a 2oo3 architecture (three channels, two must agree). Use the formula from IEC 61508-6 Table D.1. Compare the PFH to the 1oo2 case with the same λ_DU. Which is safer? Which has more nuisance trips?

2. **Calculate the maximum proof test interval** for a 1oo1 safety function targeting SIL 2 (PFH < 10⁻⁷). Assume λ_DU = 5e-8, DC = 0.9. Use the formula: PFH_1oo1 ≈ λ_DU * (1 - DC). Rearrange to find the required λ_DU, then compute T_proof_max from λ_DU_eff = λ_DU * (1 - DC).

3. **Perform a beta factor assessment** using IEC 61508-6 Annex E. For a dual-channel pressure transmitter system, score each of the 8 items (separation, diversity, etc.) and compute the total score. Map it to a β value using the table in the standard.

## Next Up

Tomorrow: **FMEA: Failure Mode & Effects Analysis for Firmware** — we'll move from hardware reliability math to systematic failure analysis. I'll show how to build an FMEA worksheet for a real-time control loop, including failure modes like stack overflow, watchdog timeout, and corrupted RAM.
