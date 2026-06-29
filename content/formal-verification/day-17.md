---
title: "Day 17: Safety Case Documentation: GSN & CAE Notation"
date: 2026-06-29
tags: ["til", "formal-verification", "safety-case", "gsn", "cae"]
---

## What I Explored Today

Today I tackled the documentation side of formal verification: how to structure a safety case using Goal Structuring Notation (GSN) and Claims-Arguments-Evidence (CAE). While CBMC and static analyzers produce raw results, safety-critical standards like DO-178C, ISO 26262, and IEC 61508 demand a clear, auditable argument linking verification evidence to top-level safety goals. I worked through building a GSN diagram for a simple fuel pump controller, then mapped it to CAE for a regulator submission package.

## The Core Concept

A safety case is a structured argument, supported by evidence, that a system is acceptably safe for a given context. Without a documented argument, verification results are just data—they don't prove safety. GSN and CAE are complementary notations for making that argument explicit.

**GSN** uses graphical nodes: goals (rectangles), strategies (parallelograms), solutions/evidence (circles), and context (ovals). Arrows show decomposition: "Goal A is achieved by Strategy B, supported by Solution C." It's hierarchical and easy to review.

**CAE** is a simpler textual form: "Claim: The system never enters unsafe state X. Argument: Formal verification of state machine invariants. Evidence: CBMC output proving invariant holds for all inputs." CAE is often used in regulatory submissions because it's compact and maps directly to traceability matrices.

The key insight: formal verification tools produce *evidence*, not arguments. You must connect that evidence to a top-level claim through an explicit reasoning chain. A CBMC proof that `assert(!overflow)` passes is not a safety case—it's a piece of evidence. The safety case explains *why* that assertion matters for system safety.

## Key Commands / Configuration / Code

I used the open-source **GSN Editor** (gsneditor.org) and a simple Python script to generate a CAE table. Here's the workflow:

### 1. GSN Goal Structure (textual representation)

```
G1: Fuel pump controller never delivers fuel when engine is off
  C1: Context: Engine state is determined by ignition sensor
  S1: Argument over all operational modes
    G2: Pump output is disabled when ignition sensor reads OFF
      Sn1: Evidence: CBMC verification of pump_control.c
    G3: Ignition sensor failure does not cause unsafe pump activation
      Sn2: Evidence: Fault injection test results (ISTQB-2024-045)
```

### 2. CAE Table Generation (Python)

```python
# safety_case_table.py
import csv

claims = [
    {
        "claim": "Pump output disabled when ignition OFF",
        "argument": "Formal verification of state machine invariants using CBMC",
        "evidence": "cbmc_output/pump_control_off_assertion_pass.txt",
        "context": "Ignition sensor reading valid (0-5V range)"
    },
    {
        "claim": "No overflow in pump duty cycle calculation",
        "argument": "Bounded model check for all 16-bit duty cycle values",
        "evidence": "cbmc_output/duty_overflow_check_pass.txt",
        "context": "Duty cycle stored as uint16_t, max 1000"
    }
]

with open('safety_case_table.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['claim', 'argument', 'evidence', 'context'])
    writer.writeheader()
    writer.writerows(claims)
```

### 3. Linking CBMC Output to Evidence

```bash
# Run CBMC with --trace to produce audit trail
cbmc pump_control.c --function check_pump_state --bounds-check --trace \
    > cbmc_output/pump_control_off_assertion_pass.txt 2>&1

# Verify the output contains "VERIFICATION SUCCESSFUL"
grep -q "VERIFICATION SUCCESSFUL" cbmc_output/pump_control_off_assertion_pass.txt && \
    echo "Evidence ready for GSN node Sn1"
```

## Common Pitfalls & Gotchas

**1. Confusing "argument" with "evidence"**
I've seen engineers write "CBMC proved it" as the entire safety case. That's like saying "the test passed" without explaining what was tested or why it matters. Always separate the reasoning (argument) from the tool output (evidence). In GSN, each solution node must reference a specific evidence artifact.

**2. Missing context nodes in GSN**
A goal like "System is safe" is meaningless without context. What assumptions about the environment? What failure modes are considered? What's the acceptable risk level? I forgot to add context nodes for sensor failure rates on my first diagram, and the reviewer immediately flagged it. Every goal should have at least one context node clarifying scope.

**3. Over-engineering the notation**
GSN can become a sprawling mess if you decompose every leaf goal to atomic level. For a fuel pump controller, I had 47 nodes before I realized I was documenting the implementation, not the safety argument. Keep the GSN at the architectural level—leave detailed code verification to the evidence artifacts. A good rule: if a goal node requires more than one paragraph to explain, it's too detailed for the top-level safety case.

## Try It Yourself

1. **Build a GSN diagram for a simple system**: Take a 3-state traffic light controller (red → green → yellow → red). Create a top-level goal "No conflicting green signals." Decompose it into at least 3 sub-goals with context nodes. Use gsneditor.org or draw.io with the GSN template.

2. **Convert CBMC output to CAE**: Run CBMC on a function that checks for buffer overflow in a 10-element array. Capture the output. Write a CAE entry with claim ("No out-of-bounds access"), argument ("Bounded model check for all array indices 0-9"), and evidence (the CBMC output file path).

3. **Review a colleague's safety case**: Find a GSN diagram online (or create one with intentional flaws). Identify at least two missing context nodes and one instance where evidence is presented as argument. Write a review comment explaining the fix.

## Next Up

Tomorrow is the full review and project day: we'll verify a state machine with CBMC from start to finish—specification, modeling, property checking, and safety case documentation. You'll build a complete verification package for a simple elevator controller, including GSN and CAE artifacts ready for a regulatory audit.
