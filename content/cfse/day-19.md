---
title: "Day 19: CFSE Exam Prep: Key Topics, Structure & Mock Questions"
date: 2026-07-01
tags: ["til", "cfse", "cfse", "exam-prep"]
---

## What I Explored Today

Today I shifted from tooling and implementation to exam strategy. The Certified Functional Safety Expert (CFSE) exam is the gold standard for demonstrating competence in IEC 61511 and IEC 61508. I spent the morning dissecting the exam blueprint, then worked through a set of mock questions covering Safety Integrity Level (SIL) determination, Probability of Failure on Demand (PFD) calculation, and architectural constraints. The key takeaway: the exam tests *application* of standards, not rote memorization. You need to know where to find the table for hardware fault tolerance (HFT) in IEC 61508-2, but you also need to justify why you chose a 1oo2 architecture over a 2oo3 for a specific burner management system.

## The Core Concept

The CFSE exam (and its companion, the CFSP for practitioners) is built around three domains: **Management of Functional Safety**, **Risk Reduction & SIL Determination**, and **Safety Lifecycle Implementation**. The exam is 4 hours, 100 multiple-choice questions, and a passing score of 70%. But the real challenge is the *application* layer. You won't be asked "What is the definition of a dangerous undetected failure?" You'll be asked: "Given a pressure transmitter with a failure rate of 500 FIT, 60% dangerous, 40% safe, with a diagnostic coverage of 90%, and a proof test interval of 1 year, what is the PFDavg for a 1oo1 architecture?" That requires you to recall the formula, apply the beta factor model, and interpret the result against the SIL 2 target (PFDavg between 10⁻² and 10⁻³).

The exam also heavily weights **architectural constraints**. You must understand the relationship between Safe Failure Fraction (SFF), Hardware Fault Tolerance (HFT), and the resulting SIL capability from IEC 61508-2, Table 2 and Table 3. For example, a Type A device with SFF < 60% and HFT = 0 can only claim SIL 1. But if you add a second channel (HFT = 1), you can claim SIL 2. This is not optional knowledge—it's the backbone of the exam.

## Key Commands / Configuration / Code

While the CFSE exam is paper-based, you should be comfortable with the following calculations. Here's a Python snippet I use for PFDavg estimation (simplified, assumes no common cause):

```python
# PFDavg calculation for 1oo1 architecture (IEC 61508-6, Annex B)
# Assumes: constant failure rate, proof test reveals all DU failures

lambda_du = 500e-9 * 0.6 * (1 - 0.9)  # 500 FIT, 60% dangerous, 90% DC
# lambda_du = 30e-9 failures/hour

T_proof = 8760  # 1 year in hours

# 1oo1 PFDavg formula: (lambda_du * T_proof) / 2
pfdavg_1oo1 = (lambda_du * T_proof) / 2
print(f"PFDavg (1oo1): {pfdavg_1oo1:.2e}")  # Output: 1.31e-4

# Check against SIL 2 target (1e-3 to 1e-2)
# 1.31e-4 is below 1e-3 -> SIL 2 is achievable, but check architectural constraints

# For 1oo2 architecture (simplified, no beta factor)
# PFDavg_1oo2 = (lambda_du * T_proof)^2 / 3
pfdavg_1oo2 = (lambda_du * T_proof)**2 / 3
print(f"PFDavg (1oo2): {pfdavg_1oo2:.2e}")  # Output: 5.73e-9 (very low)
```

**Key exam tip**: Always check architectural constraints *after* PFDavg. A 1oo1 with PFDavg of 1.31e-4 might pass SIL 2 numerically, but if the SFF is 90% and HFT=0, Table 2 says Type A device can only claim SIL 2 if SFF ≥ 90% *and* HFT=0. That works here. But if the device were Type B (e.g., a microprocessor-based transmitter), SFF=90% with HFT=0 only allows SIL 2 *if* SFF ≥ 90% *and* HFT=0—same result, but you must know the table.

## Common Pitfalls & Gotchas

1. **Confusing PFDavg with PFH**: The exam will mix low-demand (PFDavg) and high-demand (PFH) modes. A fire alarm system is low-demand (demand rate < 1/year). A continuous burner control loop is high-demand. Use PFDavg for the former, PFH for the latter. The formulas are different: PFH = λ_du for 1oo1, not λ_du * T/2.

2. **Forgetting the Beta Factor**: In redundant architectures (1oo2, 2oo3), common cause failures dominate. The exam expects you to use the β factor model from IEC 61508-6, Annex D. A typical β=0.02 (2%) for diverse channels. Without it, your PFDavg for 1oo2 looks unrealistically low (like 5.73e-9 above). The real value is closer to β * λ_du * T/2, which would be 0.02 * 1.31e-4 = 2.62e-6—still good, but not astronomically low.

3. **Misapplying Architectural Constraints**: The tables in IEC 61508-2 are for *subsystems*, not the whole system. You must decompose the safety function into sensors, logic solver, and final elements. Each gets its own SFF and HFT assessment. A common mistake is to apply the SIL 3 constraint to the entire loop when the actuator is only SIL 2 capable.

## Try It Yourself

1. **Calculate PFDavg for a 2oo3 architecture**: Use the same sensor data (500 FIT, 60% dangerous, 90% DC, T_proof=8760h). Assume β=0.02. Use the formula from IEC 61508-6: PFDavg_2oo3 ≈ (λ_du * T)^3 / 4 + β * λ_du * T / 2. Compare to the 1oo2 result above.

2. **Determine SIL capability from architectural constraints**: A Type B logic solver has SFF=95% and HFT=1. What is the maximum SIL it can claim per IEC 61508-2, Table 3? Now, if you add a second identical channel (HFT=2), does the SIL increase? Why or why not?

3. **Mock exam question**: A safety function uses a 1oo1 pressure switch (Type A, SFF=60%, λ_du=100 FIT) with a proof test every 6 months. The demand rate is once every 5 years. Calculate the PFDavg. Is SIL 2 achievable? If not, propose one architectural change (e.g., add a second switch) and recalculate.

## Next Up

Tomorrow: **Full Review: Safety Case for a Zephyr-Based Medical Device** — I'll walk through building a complete safety case argument (GSN notation) for a Zephyr RTOS-based infusion pump, including hazard logs, SIL allocation, and verification evidence. Bring your standards.
