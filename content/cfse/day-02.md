---
title: "Day 02: IEC 61508: Structure, SIL Levels & Scope"
date: 2026-06-14
tags: ["til", "cfse", "iec61508", "sil", "e-e-e"]
---

## What I Explored Today

Today I dug into the foundational standard that underpins nearly every functional safety certification I’ll ever encounter: **IEC 61508**. This is the umbrella standard for electrical/electronic/programmable electronic (E/E/PE) safety-related systems. I focused on its overall structure (Parts 1–7), the concept of Safety Integrity Levels (SIL 1–4), and the scope of what it actually covers—and what it doesn’t. If you’ve ever wondered why a SIL 2 pressure transmitter costs three times as much as a non-rated one, the answer lives in this standard’s risk-reduction math.

## The Core Concept

IEC 61508 isn’t a product standard—it’s a *framework* for managing functional safety across the entire system lifecycle. The core idea is brutally simple: **every safety function must reduce risk to a tolerable level**, and that reduction is quantified by a Safety Integrity Level (SIL). SIL 1 is the lowest (one order of magnitude risk reduction), SIL 4 is the highest (ten thousand-fold reduction).

Why does this matter? Because without a common language, a “safe” system in automotive (ISO 26262) would be incomparable to one in process industries (IEC 61511). IEC 61508 provides that common language. It defines:

- **Part 1**: General requirements (the “what” and “how” of lifecycle management)
- **Part 2**: Requirements for E/E/PE safety-related systems (hardware + software)
- **Part 3**: Software requirements (the most painful part for embedded engineers)
- **Parts 4–7**: Definitions, examples, and guidelines

The standard forces you to answer three questions for every safety function:
1. What is the tolerable risk? (Target SIL)
2. How do we achieve it? (Architecture, diagnostics, fault tolerance)
3. How do we prove we achieved it? (Verification, validation, evidence)

## Key Commands / Configuration / Code

Let’s make this concrete. Suppose you’re designing a safety relay that must achieve **SIL 2** for a “safe stop” function. You need to calculate the **Probability of Dangerous Failure per Hour (PFH)**. Here’s a Python snippet that models the required failure rate for a 1oo1 (one-out-of-one) architecture:

```python
# SIL 2 PFH target: >= 10^-7 to < 10^-6 failures/hour
# For a 1oo1 architecture with diagnostic coverage (DC) = 90%

lambda_du = 1e-6  # Dangerous undetected failure rate (failures/hour)
DC = 0.90         # Diagnostic coverage (90%)
T1 = 8760         # Proof test interval (1 year in hours)

# PFH for 1oo1 with periodic proof test
PFH = lambda_du * (1 - DC) * (T1 / 2)
# Result: PFH = 1e-6 * 0.10 * 4380 = 4.38e-4 → WAY too high for SIL 2

print(f"PFH = {PFH:.2e} failures/hour")
# Output: PFH = 4.38e-04 failures/hour

# To hit SIL 2 (PFH < 1e-6), we need either:
# - Higher DC (e.g., 99%)
# - Shorter proof test interval (e.g., T1 = 876 hours)
# - Redundant architecture (e.g., 1oo2)
```

Now, a real-world configuration snippet for a safety PLC (e.g., Siemens S7-1500F) to enforce a SIL 2-rated emergency stop:

```iecst
// Structured Text (IEC 61131-3) for a SIL 2 E-Stop
// Assumes dual-channel input with discrepancy time monitoring

FUNCTION_BLOCK FB_EStop_SIL2
VAR_INPUT
    Ch1 : BOOL;  // Channel 1 (NC contact)
    Ch2 : BOOL;  // Channel 2 (NC contact)
END_VAR
VAR_OUTPUT
    SafeState : BOOL;  // TRUE = safe (outputs off)
    DiagFault : BOOL;  // TRUE = discrepancy detected
END_VAR
VAR
    DiscrepancyTimer : TON;
    DiscrepancyTime : TIME := T#100ms;  // Max 100ms mismatch
END_VAR

// Both channels must agree within 100ms
IF Ch1 <> Ch2 THEN
    DiscrepancyTimer(IN := TRUE, PT := DiscrepancyTime);
    IF DiscrepancyTimer.Q THEN
        DiagFault := TRUE;  // Permanent fault
        SafeState := TRUE;  // Force safe state
    END_IF
ELSE
    DiscrepancyTimer(IN := FALSE);
    DiagFault := FALSE;
    // Both NC contacts closed = safe (outputs off)
    SafeState := (Ch1 = FALSE) AND (Ch2 = FALSE);
END_IF
```

## Common Pitfalls & Gotchas

1. **Confusing SIL with “safety”**  
   A SIL 3 component doesn’t mean it’s “three times safer” than SIL 1. It means the *probability* of a dangerous failure is lower by a specific factor. I’ve seen engineers slap a SIL 3 label on a sensor without doing the PFH math—that’s a certification audit fail waiting to happen.

2. **Ignoring systematic failures**  
   IEC 61508 distinguishes between random hardware failures (you can model them) and systematic failures (design bugs, spec errors). Many teams nail the hardware PFH calculation but forget that software must also be developed per Part 3 (e.g., using a certified toolchain, avoiding dynamic memory allocation). Your SIL 2 hardware is useless if the firmware has a race condition.

3. **Misapplying the scope**  
   IEC 61508 covers *E/E/PE systems*—not mechanical brakes, not pneumatic valves, not human operators. If your safety function relies on a mechanical relay, that part isn’t covered by the standard. You need a separate risk analysis for non-E/E/PE elements. I’ve seen projects fail audits because they assumed the standard covered the entire safety loop.

## Try It Yourself

1. **PFH calculation for your own system**  
   Take a safety function you’ve worked on (e.g., a motor stop). Estimate λ_du from a component datasheet (e.g., 10 FIT = 1e-8 failures/hour). Assume DC = 95% and T1 = 4380 hours (6 months). Compute the PFH. Which SIL does it meet? (Hint: SIL 2 requires PFH < 1e-6.)

2. **Read Part 4 definitions**  
   Open IEC 61508-4 (free preview often available via IEC webstore). Find the definitions for “safe state,” “dangerous failure,” and “diagnostic coverage.” Write a one-paragraph summary in your own words—this is the vocabulary you’ll use in every safety case.

3. **Architecture comparison**  
   Model a 1oo2 (one-out-of-two) architecture in Python. Assume the same λ_du = 1e-6, DC = 90%, T1 = 8760 hours. Use the formula:  
   PFH_1oo2 ≈ (λ_du * (1 - DC))² * T1  
   Compare with the 1oo1 result above. How much does redundancy buy you?

## Next Up

Tomorrow, I’ll tackle **Safety Integrity Levels (SIL): Determination & Verification**—specifically, how to go from a hazard analysis to a target SIL using risk graphs and Layer of Protection Analysis (LOPA), and then how to verify you actually hit that SIL with hardware metrics like SFF and DC.
