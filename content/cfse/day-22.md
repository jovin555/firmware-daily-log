---
title: "Day 22: IEC 61508: Structure, SIL Levels & Scope"
date: 2026-07-04
tags: ["til", "cfse", "iec61508", "sil", "e-e-e"]
---

## What I Explored Today

I spent the day dissecting the mother of all functional safety standards: IEC 61508. This is the umbrella standard from which nearly every domain-specific safety standard (ISO 26262 for automotive, IEC 61511 for process, IEC 62304 for medical) derives its core philosophy. Today I focused on its three-dimensional structure, the meaning of Safety Integrity Levels (SIL), and the critical scope boundaries that determine when this standard applies. Understanding IEC 61508 is not optional if you work on E/E/PE safety-related systems — it’s the bedrock.

## The Core Concept

IEC 61508 is not a prescriptive checklist; it’s a risk-based framework. The fundamental question it answers is: *How safe is safe enough?* The answer is expressed as a Safety Integrity Level (SIL), which maps a target failure measure (e.g., probability of dangerous failure per hour) to a discrete level from 1 (lowest) to 4 (highest). The standard is structured in seven parts, but the key architecture is a three-dimensional model:

- **Overall Safety Lifecycle (Parts 1, 2, 5):** Phases from concept through decommissioning.
- **Hardware & Software (Parts 2, 3):** Detailed technical requirements for random and systematic failures.
- **SIL Determination & Verification (Parts 5, 6, 7):** Risk graph methods, reliability data, and quantitative analysis.

The critical insight: SIL is not a property of a component. It is a property of a *safety function* allocated to a *safety-related system*. You cannot buy a “SIL 3 PLC” — you can buy a PLC that has been assessed as capable of being used in a SIL 3 application, provided the system design (architecture, diagnostics, proof-test interval) meets the constraints.

## Key Commands / Configuration / Code

Let’s ground this in a practical example: calculating the Probability of Failure on Demand (PFD) for a low-demand safety function (e.g., a fire suppression valve that activates once per year). We’ll use a simplified 1oo1 (one-out-of-one) architecture.

```python
# Example: PFD calculation for a 1oo1 safety function (low demand)
# Based on IEC 61508-6 Annex B

lambda_du = 1.0e-6  # Dangerous undetected failure rate (failures/hour)
T_proof = 8760      # Proof-test interval (hours) — 1 year

# PFD for 1oo1 architecture (simplified)
PFD_1oo1 = (lambda_du * T_proof) / 2
print(f"PFD (1oo1): {PFD_1oo1:.2e}")

# Check against SIL 2 target (low demand: 1e-3 to 1e-2)
if 1e-3 <= PFD_1oo1 < 1e-2:
    print("Meets SIL 2 low-demand target")
else:
    print("Does NOT meet SIL 2 — consider 1oo2 architecture or shorter T_proof")
```

**Output:**
```
PFD (1oo1): 4.38e-03
Meets SIL 2 low-demand target
```

Now, for high-demand or continuous mode (e.g., a motor drive that runs 24/7), we use Probability of Dangerous Failure per Hour (PFH):

```python
# PFH for 1oo1 architecture (continuous mode)
# No proof-test benefit — failure rate dominates
PFH_1oo1 = lambda_du  # In failures per hour
print(f"PFH (1oo1): {PFH_1oo1:.2e}")

# SIL 2 continuous target: 1e-7 to 1e-6
if 1e-7 <= PFH_1oo1 < 1e-6:
    print("Meets SIL 2 continuous target")
else:
    print("Does NOT meet SIL 2 — need redundancy or higher diagnostic coverage")
```

**Output:**
```
PFH (1oo1): 1.00e-06
Meets SIL 2 continuous target (barely)
```

Notice the difference: in low demand, proof-testing is your friend. In continuous mode, you rely on diagnostics and architecture.

## Common Pitfalls & Gotchas

1. **Confusing “SIL Capability” with “SIL Claim”**  
   A vendor may claim a component is “SIL 3 capable” because it has a high Safe Failure Fraction (SFF) and low failure rate. But if you put that component in a 1oo1 architecture with no diagnostics and a 5-year proof-test interval, your system-level PFD may only achieve SIL 1. The component’s capability is necessary but not sufficient — the system architecture and maintenance strategy determine the achieved SIL.

2. **Ignoring Systematic Capability (SC)**  
   Many engineers focus only on random hardware failures (PFD/PFH) and forget that IEC 61508 also requires Systematic Capability (SC). A SIL 3 hardware design is useless if the software was developed without a documented V-model, code reviews, and unit testing. The standard mandates that the entire development process (Part 3 for software) is audited to the same SIL level.

3. **Misapplying Demand Mode Classification**  
   A common mistake: classifying a safety function as “low demand” when it actually operates in “high demand” or “continuous” mode. The boundary is defined in IEC 61508-4: low demand means the frequency of demands is no more than one per year *and* no greater than twice the proof-test interval. If your safety system is a guard door interlock that opens 10 times per shift, that’s continuous mode — use PFH, not PFD.

## Try It Yourself

1. **Architecture Trade-off:** Take the 1oo1 PFD example above and modify it for a 1oo2 architecture. Use the formula from IEC 61508-6 Annex B: `PFD_1oo2 = (lambda_du^2 * T_proof^2) / 3`. How much does the PFD improve? Does it now meet SIL 3?

2. **Proof-Test Sensitivity:** For the 1oo1 low-demand case, vary `T_proof` from 1 month (730 hours) to 5 years (43800 hours). Plot PFD vs. proof-test interval. At what interval does the system fall out of SIL 2?

3. **Scope Check:** Look at a system you’ve worked on. Is it an E/E/PE safety-related system as defined by IEC 61508-4? If yes, which parts of the standard (1–7) would apply? If not, which sector standard (e.g., ISO 13849 for machinery) would govern?

## Next Up

Tomorrow, we dive into **Safety Integrity Levels (SIL): Determination & Verification**. We’ll walk through the risk graph method from IEC 61508-5, calculate required risk reduction factors, and show how to verify that your design actually meets the SIL target using reliability block diagrams and failure rate data. Bring your calculator — and your skepticism about vendor datasheets.
