---
title: "Day 20: Static vs Dynamic Analysis: The Verification Spectrum"
date: 2026-07-02
tags: ["til", "formal-verification", "static-analysis", "dynamic"]
---

## What I Explored Today

Today I stepped back from specific tools to map the full verification landscape. Static analysis and dynamic analysis are often presented as competing approaches, but in practice they occupy different positions on a spectrum of cost, coverage, and confidence. I spent the day understanding where each technique shines, where they fail, and how to combine them for production-grade firmware verification. The key insight: neither replaces the other — they expose different classes of bugs, and the best teams use both.

## The Core Concept

The fundamental difference is simple: **static analysis examines code without executing it; dynamic analysis examines code during execution.** But the implications ripple through every engineering decision.

**Static analysis** reasons about all possible execution paths. It can prove that a null pointer dereference *can never happen* on any input, or that a buffer overflow *must occur* on line 47. This is soundness — if the tool says "no overflow," you can trust it. The cost is false positives: the tool may flag paths that are theoretically possible but unreachable in practice.

**Dynamic analysis** (valgrind, AddressSanitizer, coverage-guided fuzzing) observes actual executions. It has zero false positives for the bugs it finds — if ASan says you overflowed a buffer, you did. But it only sees the paths you exercised. Coverage is the enemy: even with 100% line coverage, you miss edge cases in state machines, interrupt timing, and concurrent access.

The spectrum looks like this:

```
Soundness (no missed bugs)          Precision (no false alarms)
       |                                     |
  Formal Verification                    Dynamic Analysis
       |                                     |
  Abstract Interpretation               Fuzzing + Sanitizers
       |                                     |
  Static Analysis (soundy)              Testing
       |                                     |
  Linters (unsound, imprecise)          Manual Review
```

For embedded systems, the sweet spot is usually a "soundy" static analyzer (like Polyspace or Astree) paired with coverage-guided fuzzing under AddressSanitizer. The static tool proves the absence of certain classes of bugs; the dynamic tool finds the rest.

## Key Commands / Configuration / Code

Let's see how this plays out with a concrete example — a circular buffer that could have an off-by-one error:

```c
// circular_buffer.c
#include <stdint.h>
#include <stdbool.h>

#define BUF_SIZE 64

typedef struct {
    uint8_t data[BUF_SIZE];
    uint16_t head;  // write index
    uint16_t tail;  // read index
    uint16_t count; // number of elements
} circ_buf_t;

bool circ_buf_push(circ_buf_t *buf, uint8_t byte) {
    if (buf->count >= BUF_SIZE) {  // BUG: should be > BUF_SIZE - 1
        return false;  // buffer full
    }
    buf->data[buf->head] = byte;
    buf->head = (buf->head + 1) % BUF_SIZE;
    buf->count++;
    return true;
}
```

**Static analysis with Frama-C (value analysis):**
```bash
# Run Frama-C Eva plugin to check for buffer overflows
frama-c -eva -eva-precision 3 circular_buffer.c \
  -then -report -then -print -then -slevel 100
```
Output will show: `circular_buffer.c:16: Warning: accessing out of bounds index. assert buf->head < 64`. The analyzer traces all possible values of `head` and finds it can reach 64 when `count == BUF_SIZE` and head wraps around.

**Dynamic analysis with AddressSanitizer:**
```bash
# Compile with ASan and run a test harness
gcc -fsanitize=address -g -O1 circular_buffer.c test_harness.c -o test_circ
./test_circ
```
ASan will only trigger if the test harness actually pushes 65 elements. If your test only pushes 63, the bug stays hidden.

**Combined approach — Frama-C with runtime assertions:**
```c
// Add runtime check that static analysis can verify
bool circ_buf_push(circ_buf_t *buf, uint8_t byte) {
    if (buf->count >= BUF_SIZE) {
        return false;
    }
    // Static analysis proves this assertion holds
    //@ assert buf->head < BUF_SIZE;
    buf->data[buf->head] = byte;
    buf->head = (buf->head + 1) % BUF_SIZE;
    buf->count++;
    return true;
}
```

## Common Pitfalls & Gotchas

**1. Assuming 100% coverage means 100% safety**
I've seen teams run valgrind with 90% line coverage and declare the code clean. Line coverage doesn't cover path coverage, interrupt interleaving, or data-dependent branches. A buffer overflow that only triggers when `count == 63` and `head == 63` simultaneously is invisible to most test suites.

**2. Ignoring the halting problem in static analysis**
Every sound static analyzer must either be incomplete (miss some bugs) or undecidable (fail to terminate on some inputs). Real tools use approximations. When Frama-C says "unknown" for a property, it doesn't mean the code is safe — it means the analysis couldn't prove it. Treat unknowns as potential bugs until manually reviewed.

**3. Static analysis on incomplete code**
Running static analysis on a single .c file without stubs for hardware registers or RTOS APIs produces garbage results. The analyzer sees uninitialized variables everywhere. Always provide abstract models for hardware dependencies, or use the tool's built-in stubs (e.g., Frama-C's `-lib-entry` for library functions).

## Try It Yourself

1. **Compare tools on the same bug**: Take the circular buffer example above. Run it through `cppcheck --enable=all circular_buffer.c` (static) and compile with ASan then run a test that pushes 65 elements (dynamic). Note which tool catches the bug first, and which gives a false positive.

2. **Measure coverage gap**: Write a test harness for the circular buffer that achieves 100% line coverage but never triggers the off-by-one. Then run `gcov` to confirm coverage, and run ASan to confirm the bug is still present. This demonstrates why coverage != correctness.

3. **Add a formal contract**: Using Frama-C ACSL annotations, write a complete contract for `circ_buf_push` that proves no buffer overflow. Start with `requires \valid(buf)` and `ensures buf->count == \old(buf->count) + 1 || \result == false`. Run `frama-c -wp` to verify.

## Next Up

Tomorrow we dive into **Cppcheck: Fast Open-Source Static Analysis** — the workhorse tool that every embedded engineer should have in their CI pipeline. We'll cover configuration for MISRA compliance, false positive suppression strategies, and how to integrate it with CMake for zero-effort static analysis on every build.
