---
title: "Day 01: FMEA Fundamentals: Purpose, History & the AIAG-VDA Handbook"
date: 2026-07-10
tags: ["til", "fmea", "aiag-vda", "handbook"]
---

## What I Explored Today

Today I dug into the bedrock of reliability engineering: Failure Mode and Effects Analysis (FMEA). Specifically, I focused on the unified methodology defined by the AIAG & VDA FMEA Handbook (1st Edition, 2019). This handbook replaces the previous, often conflicting, AIAG (4th Edition) and VDA (4th Edition) standards. The goal was to understand *why* FMEA exists, how it evolved from a military safety tool into a core product development process, and how the new handbook forces a disciplined, seven-step approach that every embedded systems engineer should internalize before writing a single line of firmware.

## The Core Concept

FMEA is not a checklist; it is a **risk discovery and mitigation engine**. Its purpose is to systematically identify every plausible way a system, design, or process can fail, quantify the risk of that failure, and then prioritize actions to reduce that risk *before* the failure reaches a customer. The "why" is simple: a failure caught in simulation costs $100; a failure caught in production costs $10,000; a failure caught in the field costs $1,000,000 and your reputation.

The history is instructive. FMEA was formalized by the US military in MIL-P-1629 (1949) for system safety. It migrated to aerospace (NASA Apollo program) and then to automotive (Ford in the 1970s after the Pinto disaster). The problem was fragmentation: AIAG (American) and VDA (German) standards had different severity scales, different RPN (Risk Priority Number) calculation methods, and different documentation formats. The 2019 AIAG-VDA handbook harmonized these into a single, rigorous framework. The key shift: **Action Priority (AP) replaces RPN**. RPN was a simple product of Severity (S), Occurrence (O), and Detection (D). AP uses a decision matrix to prioritize actions based on the combination of S, O, and D, preventing engineers from gaming the numbers (e.g., lowering D to get a "safe" RPN).

For an embedded engineer, this means your firmware is not just code—it is a design element with failure modes (e.g., stack overflow, race condition, sensor drift compensation error). Every function you write has an S, O, and D rating that must be defensible.

## Key Commands / Configuration / Code

There is no "code" for FMEA, but there is a structured workflow. Below is a Python snippet that models the new Action Priority logic from the AIAG-VDA handbook. This is what you would use to automate the prioritization of failure modes in a database.

```python
# action_priority.py
# Implements the AIAG-VDA Action Priority (AP) logic for a given failure mode.
# Based on Table 1.1 in the handbook (High, Medium, Low priority).

def get_action_priority(severity: int, occurrence: int, detection: int) -> str:
    """
    Determine Action Priority based on S, O, D ratings (1-10).
    Returns 'H' (High), 'M' (Medium), or 'L' (Low).
    This is a simplified version; the full matrix has ~1000 rules.
    """
    # High priority: any combination where S >= 9 and O >= 5
    if severity >= 9 and occurrence >= 5:
        return 'H'
    # High priority: S >= 8 and O >= 7
    if severity >= 8 and occurrence >= 7:
        return 'H'
    # Medium priority: S >= 7 and O >= 5 and D >= 6
    if severity >= 7 and occurrence >= 5 and detection >= 6:
        return 'M'
    # Low priority: everything else (still requires action, but lower urgency)
    return 'L'

# Example: A watchdog timeout failure mode
# S=9 (system crash), O=6 (frequent), D=3 (easily caught by test)
print(get_action_priority(9, 6, 3))  # Output: H

# Example: A cosmetic LED blink timing error
# S=2 (minor annoyance), O=8 (common), D=9 (hard to see)
print(get_action_priority(2, 8, 9))  # Output: L
```

**Real-world note**: In practice, you don't write this from scratch. You use FMEA software (e.g., Siemens Polarion, PTC Windchill, or even a well-structured Excel sheet with conditional formatting). The key is understanding the *logic* so you can challenge the software's output.

## Common Pitfalls & Gotchas

1.  **Confusing "Detection" with "Occurrence"**: Detection is the rating of your *current* controls (e.g., "We have a unit test for this"). Occurrence is the likelihood the failure *will happen* given those controls. A common error: "We have a good test, so occurrence is low." Wrong. Occurrence is about the failure cause, not the test. Detection is about the test's ability to catch it. Keep them separate.

2.  **Using the Old RPN to Prioritize**: The AIAG-VDA handbook explicitly deprecates the RPN threshold method (e.g., "RPN > 100 needs action"). The Action Priority matrix is now the standard. If your company still uses RPN thresholds, you are likely missing high-severity, low-RPN failure modes (e.g., S=9, O=2, D=10 gives RPN=180, but AP might be Medium because O is low).

3.  **Treating FMEA as a Documentation Exercise**: The most dangerous pitfall. FMEA is a *thinking tool*. If you fill out the spreadsheet after the design is done, you have wasted the effort. The seven-step process demands that Step 1 (Planning & Preparation) happens *before* design, and Step 4 (Failure Analysis) happens *during* design. Your firmware architecture should change based on FMEA findings.

## Try It Yourself

1.  **Map a Failure Mode**: Take one function from your current project (e.g., a CAN message parser). Write down three failure modes (e.g., buffer overflow, invalid CRC, message timeout). For each, assign S, O, and D using the AIAG-VDA 1-10 scales (look up the standard definitions). Then use the Python function above to get the AP. Does the result surprise you?

2.  **Audit an Old FMEA**: Find an FMEA from a previous project. Identify three entries where the old RPN was low (e.g., < 100) but the new AP would be High (S>=9, O>=5). What actions would you have taken if you used AP?

3.  **Build a Simple AP Matrix in Excel**: Create a 10x10 grid for a fixed Detection value (e.g., D=5). Use conditional formatting to color cells High (red), Medium (yellow), Low (green) based on the AP logic. This visual will help you internalize the priority zones.

## Next Up

Tomorrow, we will dissect the three FMEA types: **DFMEA vs PFMEA vs FMEA-MSR**. You will learn exactly when to use each, how they feed into each other, and why FMEA-MSR (Monitoring & System Response) is critical for modern embedded systems with over-the-air updates and autonomous features.
