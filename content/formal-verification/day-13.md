---
title: "Day 13: CBMC: Writing Harnesses & Checking Loop Bounds"
date: 2026-06-25
tags: ["til", "formal-verification", "cbmc", "harness", "bounds"]
---

## What I Explored Today

Today I dug into the practical art of writing CBMC harnesses—the test-like entry points that tell the model checker what to verify—and specifically how to handle loops. Loops are the single biggest source of false positives and timeouts in bounded model checking. Without proper loop unwinding bounds, CBMC either spins forever or misses real bugs. I worked through real firmware patterns: bounded loops with fixed iteration counts, loops over variable-length buffers, and the dreaded `while(1)` polling loops that dominate embedded firmware. The key insight: you must tell CBMC exactly how many times to unroll each loop, and you must prove those bounds are sufficient.

## The Core Concept

CBMC works by converting your C program into a Boolean formula and feeding it to a SAT solver. Loops are problematic because they represent potentially infinite paths. CBMC handles this by *unwinding* loops—replicating the loop body N times and then cutting off. If you don't specify N, CBMC uses a default (often 1 or 2), which is almost always wrong.

The "why" is critical: you are not testing the loop; you are proving properties *through* the loop. A harness is your contract with CBMC. It sets up nondeterministic inputs (using `nondet_*` functions), calls the function under test, and asserts postconditions. For loops, you must also provide an unwinding bound via `--unwind <loop_id> <N>` or the global `--unwind <N>`. If the actual loop can iterate more than N times, CBMC will report a false *unwinding assertion failure*—it's telling you "I stopped unwinding, so I can't guarantee anything beyond this point." That's not a bug in your code; it's a signal to increase the bound or refactor the loop.

The real engineering challenge: choosing N. Too small, and you get false positives. Too large, and the SAT formula explodes (exponential in N for many loops). The sweet spot is to prove that your loop has a *known maximum iteration count* and set N to that count plus one (to catch off-by-one errors).

## Key Commands / Configuration / Code

Here's a typical harness for a buffer-copy function with a bounded loop:

```c
// harness_buffer_copy.c
#include <stdlib.h>
#include <assert.h>

// Function under test: copies up to 'size' bytes from src to dst
// Returns number of bytes actually copied (stops at first null)
int bounded_strcpy(char *dst, const char *src, unsigned int size) {
    unsigned int i;
    for (i = 0; i < size; i++) {
        dst[i] = src[i];
        if (src[i] == '\0') break;
    }
    return i;
}

// CBMC harness
void harness() {
    unsigned int size;
    char *src, *dst;

    // Nondeterministic inputs
    __CPROVER_assume(size > 0 && size <= 100);
    src = malloc(size);
    dst = malloc(size);
    __CPROVER_assume(src != NULL && dst != NULL);

    // Nondeterministic content for src (including possible null terminator)
    for (unsigned int j = 0; j < size; j++) {
        src[j] = nondet_char();
    }

    // Call the function
    int copied = bounded_strcpy(dst, src, size);

    // Postcondition: we never write past size bytes
    __CPROVER_assert(copied <= (int)size,
                     "copied bytes never exceed buffer size");

    // Postcondition: if src had a null within first size bytes, dst is null-terminated
    // (We'll check a simpler property: no buffer overflow on write)
    for (unsigned int k = 0; k < size; k++) {
        __CPROVER_assert(dst[k] == src[k] || src[k] == '\0',
                         "dst matches src until null terminator");
    }

    free(src);
    free(dst);
}
```

Run it with:

```bash
# Unwind the loop in bounded_strcpy up to 101 times (size max 100 + 1 for safety)
cbmc harness_buffer_copy.c --function harness --unwind 101 --bounds-check --pointer-check
```

Key flags:
- `--function harness` — entry point
- `--unwind 101` — global unwinding bound (applies to all loops)
- `--bounds-check` — array bounds violations
- `--pointer-check` — null/dangling pointer checks

For loops with known fixed bounds, use loop-specific unwinding:

```bash
# Unwind only the loop in bounded_strcpy, not other loops
cbmc harness.c --function harness --unwindset "bounded_strcpy.0:101"
```

The `.0` refers to the first loop in the function (CBMC numbers loops per function starting at 0).

## Common Pitfalls & Gotchas

**Pitfall 1: Forgetting to unwind polling loops.** Firmware often has `while(1)` loops that wait for hardware flags. CBMC will try to unwind these forever. Always add `__CPROVER_assume(0)` or `break` after a bounded number of iterations in your harness to cut the loop. Alternatively, use `--unwind 1` on that specific loop and accept that you're only checking one iteration.

**Pitfall 2: Unwinding too little and missing bugs.** If your loop can iterate 50 times but you unwind to 10, CBMC will report "UNWINDING ASSERTION FAILED" and *not* check paths beyond iteration 10. You might miss a buffer overflow that only occurs on iteration 42. Always set the bound to the *maximum possible* iterations, then add 1. If the bound is too large (e.g., 10,000), refactor the code to use a smaller, provable bound.

**Pitfall 3: Nondeterministic loop counters without assumptions.** If your loop uses a variable `count` that is nondeterministic, CBMC will try all possible values. If `count` can be 1,000,000, the unwinding explodes. Always constrain nondeterministic values with `__CPROVER_assume(count <= MAX_ITER)` to keep the problem tractable.

## Try It Yourself

1. **Write a harness for a circular buffer.** Implement a simple fixed-size circular buffer (say 16 bytes) with `put` and `get` functions. Write a CBMC harness that nondeterministically calls `put` and `get` up to 32 times, and assert that you never read uninitialized data. Use `--unwind 32` and `--bounds-check`.

2. **Find the off-by-one.** Take a function that copies a string with `for(i = 0; i <= len; i++)` (note the `<=`). Write a harness that calls it with a nondeterministic length up to 100. Run CBMC with `--unwind 101` and `--bounds-check`. Observe the counterexample that shows the off-by-one overflow.

3. **Handle an infinite polling loop.** Write a harness for a function that spins on a hardware register (`while(!(HW_REG & READY_BIT))`). Use `__CPROVER_assume` to limit the loop to 5 iterations. Assert that after the loop, the ready bit is set. Run with `--unwind 5` and see that CBMC proves the property only for those 5 iterations.

## Next Up

Tomorrow, we switch gears from formal verification to dynamic analysis: **AFL++: Coverage-Guided Fuzzing for Firmware**. We'll set up AFL++ to fuzz a firmware binary, instrument it for coverage, and find crashes that static analysis might miss. Bring your cross-compiler and a target binary.
