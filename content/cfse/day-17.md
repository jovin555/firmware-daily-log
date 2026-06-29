---
title: "Day 17: Testing for Functional Safety: Coverage & Independence"
date: 2026-06-29
tags: ["til", "cfse", "testing", "coverage", "independence"]
---

## What I Explored Today

Today I dug into the testing requirements for functional safety under ISO 26262, specifically the twin pillars of **structural coverage** and **test independence**. These aren't abstract quality metrics — they're hard pass/fail criteria for ASIL levels. I spent the morning running MC/DC analysis on a brake-by-wire state machine and the afternoon arguing with a test manager about why a developer can't sign off their own module's unit tests. The standard is brutally specific: for ASIL D, you need 100% modified condition/decision coverage (MC/DC) at the unit level, and the test author must be from a different team than the implementation author. Here's what that actually looks like on the bench.

## The Core Concept

The "why" behind coverage and independence is deceptively simple: **you cannot prove absence of dangerous faults if the same person who wrote the code also designs the tests**. Cognitive bias means you'll unconsciously test the paths you already know work, and miss the edge cases that kill people. Independence forces a fresh pair of eyes.

Coverage, on the other hand, answers a quantitative question: "Did we actually exercise every logical path that could hide a fault?" Statement coverage (every line executed) is the bare minimum. Branch coverage (every true/false taken) is better. But for ASIL C/D, you need **MC/DC** — every condition in a decision must independently affect the decision's outcome. This catches faults like a shorted sensor input that always reads true, which statement coverage would miss because the line still "executed."

The standard (ISO 26262-6, Table 12) maps coverage methods to ASIL levels:
- ASIL A: Statement coverage
- ASIL B: Branch coverage
- ASIL C: MC/DC (or enhanced branch coverage with analysis)
- ASIL D: MC/DC

Independence follows a similar escalation: for ASIL A, the tester can be from the same team. For ASIL D, the tester must be from a **different organization** (e.g., a separate test group or external partner).

## Key Commands / Configuration / Code

I used **Tessy** (a common embedded unit test tool) with **LDRA** for coverage instrumentation, but the principles apply to any toolchain. Here's a real MC/DC analysis on a safety-critical airbag deployment condition:

```c
// airbag_control.c — simplified deployment logic
bool deploy_airbag(uint8_t crash_impact, bool seat_occupied, bool ignition_on) {
    // Decision: deploy if (high impact AND seat occupied AND ignition on)
    if (crash_impact > 100 && seat_occupied && ignition_on) {
        fire_squib();
        return true;
    }
    return false;
}
```

To achieve 100% MC/DC on this three-condition decision, I need test cases where each condition toggles the outcome independently:

```c
// Test cases for MC/DC — each condition must independently flip the result
// Condition A: crash_impact > 100
// Condition B: seat_occupied
// Condition C: ignition_on

// Test 1: All true — decision true
// (A=T, B=T, C=T) → outcome = true

// Test 2: A false, B true, C true — decision false (A flips outcome)
// (A=F, B=T, C=T) → outcome = false

// Test 3: A true, B false, C true — decision false (B flips outcome)
// (A=T, B=F, C=T) → outcome = false

// Test 4: A true, B true, C false — decision false (C flips outcome)
// (A=T, B=T, C=F) → outcome = false
```

Running LDRA coverage analysis on the compiled binary:

```bash
# Instrument the binary for coverage
ldra tbvision -instrument -mc-dc -o airbag_instr.elf airbag.elf

# Run test harness with coverage collection
./airbag_test_runner --coverage-file coverage.dat

# Generate MC/DC report
ldra tbvision -report -mc-dc coverage.dat -o mc_dc_report.html
```

The report should show each condition pair (e.g., A-T vs A-F with B,C fixed) and confirm the decision flipped. If any condition pair shows the same outcome, you have a coverage gap.

For independence verification, I use a simple script to check that the test author's ID differs from the code author's ID in our version control:

```bash
#!/bin/bash
# verify_independence.sh — checks author ≠ tester for ASIL D modules
MODULE=$1
CODE_AUTHOR=$(git log --format='%an' -1 -- "$MODULE.c")
TEST_AUTHOR=$(git log --format='%an' -1 -- "tests/${MODULE}_test.c")

if [ "$CODE_AUTHOR" == "$TEST_AUTHOR" ]; then
    echo "FAIL: $MODULE — same author for code and tests"
    exit 1
else
    echo "PASS: $MODULE — authors differ"
fi
```

## Common Pitfalls & Gotchas

1. **MC/DC on short-circuit operators**: C's `&&` and `||` short-circuit. If you write `if (A && B && C)`, and A is false, B and C never execute. Your coverage tool may report them as "not exercised" even though the decision is correct. You must write test cases that force evaluation of all conditions — meaning A must be true to reach B, etc. Many teams miss this and claim 100% MC/DC when they only have branch coverage.

2. **Independence ≠ separation of concerns**: I've seen teams put two engineers in the same cubicle and call it "independent testing." ISO 26262 defines independence by reporting lines, not physical location. If the test engineer reports to the same manager as the developer, that's not independent for ASIL D. You need separate organizational chains, ideally with different budget owners.

3. **Coverage on dead code**: Safety standards require you to justify every line of unreachable code. If your MC/DC analysis shows a condition pair that can never occur (e.g., `ignition_on` is always true when the engine is running), you must either add an assertion or document why it's unreachable. Simply ignoring it is a non-conformance.

## Try It Yourself

1. **MC/DC exercise**: Take a three-condition decision from your own code (e.g., `if (temp > THRESHOLD && pressure_ok && valve_open)`). Write the minimum set of test cases to achieve 100% MC/DC. Verify by hand that each condition independently flips the outcome.

2. **Independence audit**: In your project's version control, run the independence check script above on your last five safety-critical modules. How many pass? For any failures, document the organizational separation (or lack thereof) and propose a fix.

3. **Coverage gap analysis**: Run your current unit test suite with a coverage tool (gcov, LDRA, or Tessy). Generate a branch coverage report. Identify one function with less than 100% branch coverage and write the missing test cases. Then check if those missing branches could hide a dangerous fault.

## Next Up

Tomorrow, we cross domains into **IEC 62443: Industrial Cybersecurity & Safety Convergence** — how to handle the tension between safety (always fail-safe) and security (prevent unauthorized access) when a safety-critical controller is also network-connected. Bring your firewall rules and your hazard analysis.
