---
title: "Day 01: Why Formal Verification? Safety Standards & Cost of Bugs"
date: 2026-06-13
tags: ["til", "formal-verification", "safety"]
---

## What I Explored Today

I dove into the foundational question that every embedded engineer eventually faces: why should I care about formal verification when my code compiles and runs fine on the bench? Today's exploration focused on the economic and regulatory drivers—specifically how safety standards like ISO 26262 (automotive) and DO-178C (aviation) mandate formal methods at the highest integrity levels, and how the cost of a single bug in deployed firmware can eclipse the entire verification budget of a project.

## The Core Concept

Formal verification is not about finding bugs—it's about proving their absence. Unlike testing, which samples a tiny fraction of possible states, formal methods exhaustively explore all reachable states of a model. For embedded systems, this is critical because:

1. **Safety standards require it.** At ASIL D (ISO 26262) or DAL A (DO-178C), the standard demands that certain classes of errors be *proven* impossible, not just "tested enough." Static analysis and formal verification are the only accepted techniques for achieving this.

2. **The cost curve is exponential.** A bug caught during requirements costs ~$100 to fix. During integration, ~$1,000. In production field returns, ~$10,000+. For safety-critical systems, a recall or liability event can cost millions. Formal verification front-loads the cost but eliminates entire classes of bugs before a single line of C is compiled.

3. **Testing is incomplete.** Even 100% code coverage only exercises a tiny fraction of possible input combinations and state sequences. For a system with 10 boolean inputs and 5 state bits, there are 2^15 = 32,768 possible states. Testing might cover 100. Formal verification covers all of them.

The key insight: formal verification is a *design activity*, not a testing activity. You write specifications (properties) that describe what the system must *never* do, and the tool proves that the implementation cannot violate them.

## Key Commands / Configuration / Code

Let's look at a concrete example using CBMC (C Bounded Model Checker), a popular open-source formal verification tool for C code. We'll verify a simple watchdog timer implementation.

```c
// watchdog.c
#include <assert.h>
#include <stdint.h>

#define WDT_TIMEOUT_MS 1000
#define WDT_MAX_COUNT  100

static uint32_t wdt_counter = 0;
static uint8_t  wdt_enabled = 0;

void wdt_init(void) {
    wdt_counter = 0;
    wdt_enabled = 1;
}

void wdt_feed(void) {
    wdt_counter = 0;  // Reset counter on feed
}

void wdt_tick(uint32_t elapsed_ms) {
    if (!wdt_enabled) return;
    wdt_counter += elapsed_ms;
    // Assertion: counter must never exceed timeout
    assert(wdt_counter <= WDT_TIMEOUT_MS);
}

// Property to verify: after feed, counter stays within bounds
void wdt_property_feed_resets(void) {
    wdt_init();
    wdt_feed();
    __CPROVER_assume(wdt_counter == 0);  // CBMC assumption
    wdt_tick(500);
    assert(wdt_counter <= WDT_TIMEOUT_MS);  // Should hold
}
```

Now run CBMC to verify:

```bash
# Install CBMC (Ubuntu/Debian)
sudo apt-get install cbmc

# Verify the watchdog module with 10 loop unwinds
cbmc watchdog.c --function wdt_property_feed_resets --unwind 10

# Expected output: "VERIFICATION SUCCESSFUL"
# If we had a bug (e.g., overflow), CBMC would produce a counterexample trace
```

CBMC unrolls all loops and explores all possible execution paths. For this simple case, it proves the assertion holds for any sequence of `wdt_tick` calls up to 10 iterations. Real-world usage would increase the unwind bound or use k-induction for unbounded proofs.

## Common Pitfalls & Gotchas

1. **False confidence from bounded verification.** CBMC and similar tools check up to a user-specified bound (loop iterations, recursion depth). If you set `--unwind 10` but the bug only manifests at iteration 11, you'll get a false "VERIFICATION SUCCESSFUL." Always justify your bound—or use unbounded techniques (k-induction, invariant inference) for safety-critical code.

2. **Property specification is the hard part.** Writing the wrong property is worse than writing no property. A common mistake: asserting that a variable is *always* in a range, when the specification only requires it *after initialization*. The tool will flag a violation, and you'll waste hours debugging a non-issue. Always model the system's full lifecycle in your properties.

3. **Tool-specific semantics.** CBMC treats `volatile` variables as nondeterministic inputs (good for hardware registers), but other tools may not. Always check how your tool handles concurrency, interrupts, and volatile memory. A property that passes in CBMC may fail in a model checker that assumes sequential consistency.

## Try It Yourself

1. **Install CBMC** and run it on the watchdog example above. Change `WDT_TIMEOUT_MS` to 100 and `wdt_tick(500)` to `wdt_tick(150)`. Does CBMC still prove the property? Why or why not?

2. **Introduce a subtle bug:** Remove the `wdt_counter = 0;` line from `wdt_feed()`. Re-run CBMC. What counterexample trace does it produce? Examine the trace to understand the state sequence that leads to the assertion failure.

3. **Write a property for a real module.** Take a simple state machine from your current project (e.g., a UART receiver FSM). Write an assertion that a particular state transition is impossible. Run CBMC on it. If it passes, try to prove the *opposite* property (that the transition *is* possible) to verify your model is correct.

## Next Up

Tomorrow: **Static vs Dynamic Analysis: The Verification Spectrum** — we'll compare formal verification with traditional static analysis (MISRA checkers, Clang Static Analyzer) and dynamic testing (unit tests, fuzzing). You'll learn when to use each technique and how to build a layered verification strategy that doesn't break your build budget.
