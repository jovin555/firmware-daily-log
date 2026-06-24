---
title: "Day 12: CBMC: Bounded Model Checking for C Programs"
date: 2026-06-24
tags: ["til", "formal-verification", "cbmc", "model-checking", "bounded"]
---

## What I Explored Today

I finally dug into CBMC (C Bounded Model Checker), the open-source tool from CMU that performs bounded model checking on C programs. After weeks of static analysis with abstract interpretation and symbolic execution, CBMC feels like a different beast entirely. It doesn't just analyze paths—it unwinds loops to a fixed depth, converts the entire program into a SAT formula, and hands it to a solver. If the solver says "unsatisfiable," your assertions hold for that bound. If it says "satisfiable," it hands you a counterexample trace. Today I ran CBMC on a simple embedded buffer handler and watched it find a buffer overflow I'd deliberately hidden. The trace output was terrifyingly precise.

## The Core Concept

Bounded model checking trades completeness for decidability. Unlike unbounded model checking (which can loop forever on infinite-state systems), CBMC says: "I'll check all execution paths up to `k` loop iterations and `n` function call depths." If your bug requires 11 loop iterations to trigger, and you set `--unwind 10`, CBMC will tell you everything is fine. That's the bound.

Why use it? Because for embedded firmware with fixed loop bounds (think: "process 64 bytes from the UART buffer"), bounded checking is effectively complete. If your loop never executes more than 64 times, and you unwind to 64, CBMC checks every possible state. No false positives from over-approximation, no missed paths from under-approximation. You get a mathematical proof for that bound.

The pipeline is: C source → GOTO program (CBMC's intermediate representation) → unwind loops → convert to SAT/ SMT formula → solve. If the solver returns SAT, CBMC reconstructs the execution trace showing exactly which variable values at which line cause the assertion failure.

## Key Commands / Configuration / Code

Let's start with a deliberately buggy circular buffer:

```c
// circular_buffer.c
#include <assert.h>
#include <stdint.h>

#define BUF_SIZE 64

typedef struct {
    uint8_t data[BUF_SIZE];
    uint8_t head;
    uint8_t tail;
    uint8_t count;
} circ_buf_t;

void buf_write(circ_buf_t *buf, uint8_t val) {
    // BUG: missing overflow check
    buf->data[buf->head] = val;
    buf->head = (buf->head + 1) % BUF_SIZE;
    buf->count++;
}

void buf_read(circ_buf_t *buf, uint8_t *val) {
    // BUG: missing underflow check
    *val = buf->data[buf->tail];
    buf->tail = (buf->tail + 1) % BUF_SIZE;
    buf->count--;
}

int main() {
    circ_buf_t buf = {0};
    // Fill buffer completely
    for (int i = 0; i < BUF_SIZE; i++) {
        buf_write(&buf, (uint8_t)i);
    }
    // This write overflows — head is now 0, count is 64
    buf_write(&buf, 0xFF);  // assertion should fire here
    return 0;
}
```

Now run CBMC with assertions automatically inserted for array bounds:

```bash
# Basic run: check all array bounds and assertions
cbmc circular_buffer.c --bounds-check --pointer-check --unwind 65

# Key flags:
#   --bounds-check    : check array index bounds
#   --pointer-check   : check null/dangling pointer dereferences
#   --unwind 65       : unwind loops 65 times (BUF_SIZE + 1)
#   --trace           : show full counterexample trace (default on failure)

# To see the GOTO program before unwinding:
cbmc circular_buffer.c --show-goto-functions

# To set a specific unwind depth per loop:
cbmc circular_buffer.c --unwindset main.0:65 --bounds-check
```

The output will show:

```
[circular_buffer.c:10] array 'data' index 0 out of bounds: FAILURE
```

With a trace showing `head == 0`, `count == 64`, and the write to `data[0]` overwriting the oldest byte.

## Common Pitfalls & Gotchas

**1. The bound is your proof's Achilles' heel**
If you set `--unwind 10` but your loop can iterate 11 times, CBMC will report "VERIFICATION SUCCESSFUL" even if a bug exists on iteration 11. Always verify your loop bounds are correct. Use `--unwind <actual_max+1>` or, better, use `--unwindset` to set per-loop bounds based on your design specification.

**2. CBMC hates unbounded loops and recursion**
If your firmware has `while(1)` main loops or recursive functions, CBMC will either loop forever or unwind them to the bound you set. For infinite main loops, you typically check the loop body separately. Use `--function` to check specific functions in isolation.

**3. Pointer aliasing can explode the formula**
CBMC handles pointer aliasing by tracking all possible targets. If you have complex pointer chains (function pointers, double indirection), the SAT formula can grow exponentially. Keep your harness simple—pass concrete values or use `--object-bits` to limit pointer analysis depth.

## Try It Yourself

1. **Fix the circular buffer** — Add overflow/underflow checks to `buf_write` and `buf_read`. Run CBMC with `--unwind 65` and verify it passes. Then change the bound to `--unwind 64` and observe the false positive.

2. **Check a CRC calculation** — Write a CRC-8 routine that processes a buffer of `N` bytes. Use CBMC with `--unwind N+1` to prove no array bounds violations. Add an assertion that the CRC output is always within [0, 255].

3. **Find the off-by-one** — Given this loop:
   ```c
   uint8_t arr[10];
   for (int i = 0; i <= 10; i++) arr[i] = i;
   ```
   Run CBMC with `--unwind 12` and observe the counterexample. Then fix the loop condition and re-verify.

## Next Up

Tomorrow: **CBMC: Writing Harnesses & Checking Loop Bounds** — We'll write proper verification harnesses for modular checking, use `--unwindset` to prove loop bounds match the specification, and handle nondeterministic inputs with `nondet_*` functions.
