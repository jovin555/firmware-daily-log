---
title: "Day 19: Why Formal Verification? Safety Standards & Cost of Bugs"
date: 2026-07-01
tags: ["til", "formal-verification", "formal-verification", "safety"]
---

## What I Explored Today

Today I dug into the economic and regulatory drivers that make formal verification a necessity rather than a luxury in safety-critical embedded systems. I traced the cost curve of bugs from discovery in development ($100) to discovery in the field ($10M+), and mapped how safety standards like ISO 26262 (automotive) and DO-178C (aviation) explicitly require formal methods at the highest integrity levels. The key insight: formal verification isn't about proving code is perfect—it's about proving the absence of specific classes of bugs that testing can never guarantee to find.

## The Core Concept

**Formal verification mathematically proves that a system satisfies a given specification for all possible inputs and states.** Unlike testing, which samples a finite set of behaviors, formal verification exhaustively explores every reachable state. This is critical when a single untested edge case can cause catastrophic failure.

Why does this matter in practice? Consider the cost of bugs:

| Discovery Phase | Typical Cost |
|----------------|--------------|
| Development (unit test) | $100 - $1,000 |
| Integration test | $1,000 - $10,000 |
| System validation | $10,000 - $100,000 |
| Production / Field | $1M - $10M+ |

For a safety-critical system with ASIL D (ISO 26262) or DAL A (DO-178C) requirements, the cost of a field failure includes recalls, liability, and human life. Formal verification shifts bug discovery left—into the design phase—where fixes cost pennies compared to post-deployment patches.

Safety standards explicitly mandate formal methods at the highest integrity levels:
- **ISO 26262-6:2018** (Table 12) recommends formal verification for ASIL C and D at the software unit level
- **DO-178C** (Section 12.3) defines formal methods as an alternative to testing for Level A software
- **IEC 61508** (Part 3, Table B.6) lists formal proof as a "highly recommended" technique for SIL 3 and 4

The practical takeaway: if you're shipping code that can kill someone, you need formal verification—not because testing is bad, but because testing is incomplete.

## Key Commands / Configuration / Code

Here's a minimal example using **CBMC** (C Bounded Model Checker) to formally verify a safety property in C code. CBMC is a mature, open-source tool widely used in automotive and industrial control.

```c
// example.c — A simple fuel pump controller with a safety property
#include <assert.h>

// Safety property: fuel_pump must never be ON when engine_speed == 0
// (prevents dry-running the pump)
int fuel_pump_control(int engine_speed, int ignition_key) {
    int pump_state = 0; // 0 = OFF, 1 = ON
    
    // Only enable pump if engine is running AND key is in ON position
    if (engine_speed > 0 && ignition_key == 1) {
        pump_state = 1;
    } else {
        pump_state = 0;
    }
    
    // Safety assertion: pump must be OFF when engine is stopped
    assert(!(pump_state == 1 && engine_speed == 0));
    
    return pump_state;
}
```

Now run CBMC to verify the assertion holds for *all* possible inputs:

```bash
# Install CBMC (Ubuntu/Debian)
sudo apt-get install cbmc

# Verify the safety property
cbmc example.c --function fuel_pump_control --bounds-check --assertion-check

# Expected output:
# ** Results:
# [fuel_pump_control.assertion.1] assertion !(pump_state == 1 && engine_speed == 0): SUCCESS
# ** 0 of 1 failed
# VERIFICATION SUCCESSFUL
```

CBMC unrolls all loops (bounded) and explores every combination of `engine_speed` (0 to 2^32-1) and `ignition_key` (0 or 1). If the assertion holds for every path, verification succeeds. If not, it produces a counterexample trace.

For a more realistic workflow, integrate with CMake:

```cmake
# CMakeLists.txt snippet for formal verification target
find_program(CBMC cbmc)
if(CBMC)
    add_custom_target(verify_fuel_pump
        COMMAND ${CBMC} src/fuel_pump.c
            --function fuel_pump_control
            --assertion-check
            --unwind 10
        COMMENT "Running formal verification on fuel pump controller"
    )
endif()
```

## Common Pitfalls & Gotchas

1. **Bounded vs. Unbounded Verification**  
   CBMC is *bounded*—it unrolls loops up to a limit (`--unwind N`). If your loop can iterate more than N times, CBMC may miss bugs. For safety-critical code, either prove the loop bound is sufficient, or use an *unbounded* tool like CPAchecker or a deductive verifier (e.g., Frama-C with WP plugin). Always document your unwind bound and why it's safe.

2. **False Positives from Uninitialized Variables**  
   Formal tools treat uninitialized variables as *any possible value*. If you forget to initialize a variable, the tool may flag a "bug" that can't actually occur in practice. Example: `int x; if (cond) x = 5; else x = 10; use(x);` is fine, but `int x; if (cond) x = 5; use(x);` is a real bug. Always initialize variables or add assumptions (`__CPROVER_assume`) to constrain the state space.

3. **Specification Drift**  
   The most common failure mode in formal verification is not the tool—it's the specification. Engineers write assertions that match the implementation, not the requirements. A formally verified system that satisfies the wrong specification is still wrong. Always cross-reference assertions with your safety requirements document (e.g., ISO 26262 safety goals).

## Try It Yourself

1. **Verify a simple state machine**  
   Write a C function implementing a traffic light controller with a safety property: "red and green lights must never be on simultaneously." Use CBMC to verify the assertion. Intentionally introduce a bug (e.g., remove a guard condition) and observe the counterexample trace.

2. **Bound your loops**  
   Take a function with a `for` loop that processes an array of size `N`. Add an assertion that array indices stay within bounds. Run CBMC with `--unwind N` and verify. Then reduce the unwind bound to `N-1` and see what happens.

3. **Integrate into CI**  
   Add a CBMC verification step to your CI pipeline (GitHub Actions or GitLab CI). Use `--cover` to measure how much of the state space your verification covers. Aim for 100% assertion coverage on safety-critical functions.

## Next Up

Tomorrow: **Static vs Dynamic Analysis: The Verification Spectrum** — We'll compare formal verification with traditional static analysis (e.g., MISRA checkers) and dynamic testing, and build a decision matrix for when to use each technique in your embedded projects.
