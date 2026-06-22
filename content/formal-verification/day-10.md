---
title: "Day 10: Frama-C Eva Plugin: Abstract Interpretation for C"
date: 2026-06-22
tags: ["til", "formal-verification", "eva", "abstract-interpretation"]
---

## What I Explored Today

Today I dove into Frama-C's Eva plugin — a value analysis engine that uses abstract interpretation to automatically discover runtime properties of C programs without executing them. Unlike the WP plugin we touched on earlier, Eva doesn't require manual annotations to get started; it runs a fixed-point computation over an abstract domain (intervals, congruences, or octagons) to over-approximate all possible program states. I spent the morning running Eva on a small sensor driver and was genuinely impressed at how quickly it found a potential buffer underflow that had been hiding in plain sight.

## The Core Concept

Abstract interpretation is the theory behind Eva, but the practical payoff is this: Eva gives you a sound over-approximation of every variable's possible values at every program point. "Sound" means if Eva says `x` is always in `[0, 100]`, then no concrete execution will ever produce `x = -1` or `x = 101`. The trade-off is that the analysis may be imprecise (it might say `x ∈ [0, 200]` when the real range is `[0, 100]`), but it will never lie.

Why does this matter for embedded engineers? Because C code for microcontrollers is full of pointer arithmetic, bitwise operations, and volatile accesses — exactly the kind of code where off-by-one errors or uninitialized reads cause field failures. Eva can prove the absence of buffer overflows, null pointer dereferences, and division-by-zero automatically. You don't write proofs; you write C and let Eva exhaustively explore all paths.

The engine works by iterating through your program's control flow graph, merging abstract states at join points (e.g., after an if-else), and widening when loops might cause infinite growth. The result is a set of "alarms" — potential issues that Eva cannot rule out. Your job is to inspect each alarm and either fix the code or add an assertion to guide Eva toward a tighter bound.

## Key Commands / Configuration / Code

Let's analyze a realistic snippet — a circular buffer write function that could easily hide a bug:

```c
// circ_buf.c
#include <stdint.h>
#define BUF_SIZE 64

static uint8_t buffer[BUF_SIZE];
static uint16_t head = 0;
static uint16_t tail = 0;

int circ_buf_write(uint8_t data) {
    uint16_t next = (head + 1) % BUF_SIZE;
    if (next == tail) {
        return -1; // buffer full
    }
    buffer[head] = data;
    head = next;
    return 0;
}
```

Run Eva with the most useful configuration for embedded code:

```bash
frama-c -eva -eva-precision 2 \
        -eva-slevel 20 \
        -eva-warn-undefined-pointer-comparison \
        -then -report \
        circ_buf.c
```

**What each flag does:**
- `-eva-precision 2`: Increases loop unrolling and widening threshold. Default is 0; for embedded code with small loops, 2 is a sweet spot.
- `-eva-slevel 20`: Semantic level — controls how many paths Eva keeps separate before merging. Higher values reduce false alarms but increase analysis time.
- `-eva-warn-undefined-pointer-comparison`: Catches comparisons between pointers to different objects (undefined behavior in C).
- `-then -report`: After Eva finishes, generate a human-readable report.

To see the inferred ranges for every variable at every line, add:

```bash
frama-c -eva -eva-precision 2 circ_buf.c -then -print -ocode annotated.c
```

This produces `annotated.c` with ACSL assertions showing what Eva proved. For our buffer, you'd see something like:

```c
//@ assert head ∈ {0..63};
//@ assert tail ∈ {0..63};
```

If you want to prove the absence of overflow on the `(head + 1) % BUF_SIZE` line, add an assertion:

```c
//@ assert head < 65535;  // head is uint16_t, so max is 65535
uint16_t next = (head + 1) % BUF_SIZE;
```

Then run with `-eva` to see if Eva can verify it. If it can't, you may need to add a loop invariant or widen the analysis.

## Common Pitfalls & Gotchas

1. **Volatile variables kill precision.** Eva treats volatile reads as returning any value in the type's range. If you have `volatile uint8_t sensor_val;`, Eva will assume it can be 0–255. Use `-eva-volatile-domain` to specify a custom range, or wrap volatile accesses in functions with explicit contracts.

2. **Pointer aliasing confuses Eva.** If two pointers may point to the same memory, Eva merges their abstract states. This can cause massive over-approximation. Use `-eva-aliasing` options (like `-eva-aliasing every` or `-eva-aliasing typed`) to control the aliasing model. For most embedded code, `typed` (assumes pointers only alias if types match) is safe and more precise.

3. **Recursion and function pointers are hard.** Eva can handle direct recursion with limits, but indirect recursion through function pointers often causes the analysis to bail out with "invalid memory access." If you use function pointer tables (common in drivers), annotate them with `//@ assigns \nothing;` or refactor to a switch statement for analysis.

## Try It Yourself

1. **Find a hidden overflow:** Take the circular buffer above and change `head` and `tail` to `uint8_t`. Run Eva with default precision. Notice that Eva now warns about potential overflow on `head + 1` because `uint8_t` wraps at 255. Add an assertion to prove it's safe given `BUF_SIZE = 64`.

2. **Analyze a real driver stub:** Write a minimal I2C read function that takes a device address, register, and buffer length. Use `-eva` to check for null pointer dereference on the buffer pointer. Then add a precondition `//@ requires \valid(buffer + (0 .. len-1));` and see if Eva's alarms disappear.

3. **Tune precision for a loop:** Create a function that sums an array of 100 elements. Run Eva with `-eva-precision 0` and note the number of alarms. Re-run with `-eva-precision 2` and compare the precision of the inferred loop invariant (check the annotated output). Observe how widening affects the result.

## Next Up

Tomorrow, we'll take everything we've learned about Eva and apply it to a real Zephyr RTOS driver — a GPIO interrupt handler. Then we'll switch gears and use the WP plugin to *prove* functional correctness of the same driver with ACSL contracts. You'll see how Eva finds bugs fast, and WP proves they're gone for good.
