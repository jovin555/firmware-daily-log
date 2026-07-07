---
title: "Day 25: Frama-C Architecture: Plugins, ACSL & Value Analysis"
date: 2026-07-07
tags: ["til", "formal-verification", "frama-c", "acsl", "value-analysis"]
---

## What I Explored Today

After weeks of building up theory around static analysis and formal methods, I finally got my hands dirty with Frama-C — the open-source static analysis framework for C code. Today’s deep dive focused on understanding Frama-C’s plugin-based architecture, how ACSL (ANSI/ISO C Specification Language) drives verification contracts, and what the Value Analysis plugin actually does under the hood. I ran real analyses on a small embedded controller to see how these pieces fit together.

## The Core Concept

Frama-C isn’t a single tool — it’s a platform. Think of it as an operating system for C code analysis, where each plugin is a specialized application. The kernel provides the shared AST (Abstract Syntax Tree) and analysis infrastructure, while plugins like E-ACSL, WP, and Value Analysis operate on that common representation.

Why does this matter? Because in embedded systems, you rarely need just one analysis. You might want to:
- Check for runtime errors (Value Analysis)
- Verify functional correctness (WP with ACSL)
- Detect memory leaks (E-ACSL)
- Measure code coverage (LCOV plugin)

The plugin architecture means you can chain analyses without re-parsing the code. ACSL is the glue — it’s the annotation language that lets you specify what the code should do, and plugins use those annotations as contracts or as targets for verification.

The Value Analysis plugin is particularly useful for embedded engineers. It performs an abstract interpretation of your code, tracking possible values for each variable at every program point. It doesn’t execute the code — it computes a sound over-approximation of all possible states. If it says a variable is in [0, 100], you can trust that no execution will produce a value outside that range. This is how you prove absence of runtime errors like buffer overflows or division by zero.

## Key Commands / Configuration / Code

Let’s start with a real embedded example — a temperature sensor reading function with a potential overflow bug:

```c
/* temp_sensor.c */
#include <stdint.h>

#define ADC_MAX 4095
#define TEMP_OFFSET 50

/*@
  requires 0 <= adc_value <= 4095;
  assigns \nothing;
  ensures \result == (adc_value * 100) / 4095 - TEMP_OFFSET;
*/
int16_t adc_to_temp(uint16_t adc_value) {
    return (adc_value * 100) / 4095 - TEMP_OFFSET;
}

int main(void) {
    int16_t temp;
    uint16_t raw = 2048;  /* mid-scale ADC reading */
    
    temp = adc_to_temp(raw);
    
    /* potential overflow: raw * 100 can exceed 16-bit range */
    return 0;
}
```

Run the Value Analysis plugin:

```bash
# Basic value analysis with default settings
frama-c -val temp_sensor.c

# More useful: show results in GUI
frama-c-gui -val temp_sensor.c

# With ACSL verification enabled
frama-c -wp -wp-rte temp_sensor.c
```

The `-val` flag invokes the Value Analysis plugin. The `-wp` flag runs the Weakest Precondition plugin, which uses ACSL annotations to prove functional properties. `-wp-rte` automatically generates runtime error annotations (division by zero, overflow, etc.).

Let’s see what happens with the overflow. The expression `adc_value * 100` — if `adc_value` is 4095, the product is 409500, which overflows a 16-bit signed integer. The Value Analysis plugin catches this:

```bash
frama-c -val -slevel 100 temp_sensor.c
```

The `-slevel` parameter controls how many program states the analyzer merges. Higher values give more precision but slower analysis. For this small example, it will report:

```
[kernel] warning: signed overflow in adc_to_temp (adc_value * 100)
```

To fix it, we need to use a wider intermediate type:

```c
/*@
  requires 0 <= adc_value <= 4095;
  assigns \nothing;
  ensures \result == (int16_t)(((int32_t)adc_value * 100) / 4095 - TEMP_OFFSET);
*/
int16_t adc_to_temp(uint16_t adc_value) {
    return (int16_t)(((int32_t)adc_value * 100) / 4095 - TEMP_OFFSET);
}
```

Now re-run the analysis — no overflow warnings.

## Common Pitfalls & Gotchas

**1. Forgetting to specify analysis precision.** The default `-val` analysis is conservative. If you don’t set `-slevel` high enough, the analyzer merges states too aggressively and reports false positives. For loops, you almost always need `-slevel N` where N is at least the loop bound.

**2. ACSL annotations that don’t match the code.** Frama-C doesn’t check that your ACSL contracts are correct — it checks that the code satisfies them. If you write a postcondition that says `\result == 0` but the function returns 1, the analysis will fail. But if you write a precondition that’s too weak (e.g., `requires adc_value >= 0` without an upper bound), the analyzer might miss real bugs.

**3. Ignoring the `-then` separator.** When chaining plugins, you must use `-then` to separate analysis stages. For example: `frama-c -val file.c -then -wp` runs value analysis first, then WP on the same AST. Without `-then`, the second plugin might re-parse the file and lose the first analysis results.

## Try It Yourself

**Task 1: Find the buffer overflow**
Write a small C function that copies a string into a fixed-size buffer. Add an ACSL `requires` that the source string length is less than the buffer size. Run `frama-c -val -wp-rte` and see if it catches the overflow when you violate the precondition.

**Task 2: Prove a loop invariant**
Write a function that sums an array of 10 elements. Add an ACSL loop invariant that tracks the partial sum. Use `frama-c -wp` to prove the invariant holds. Hint: you’ll need `loop invariant` and `loop assigns` annotations.

**Task 3: Analyze a real embedded snippet**
Take a UART interrupt handler from your own codebase (or a simple one from the web). Run `frama-c -val` with `-slevel 50` and look for any integer overflow or division-by-zero warnings. Fix any issues you find and re-verify.

## Next Up: ACSL Annotations: Preconditions, Postconditions & Invariants

Tomorrow, we’ll dive deep into ACSL itself — how to write precise preconditions that catch caller bugs, postconditions that guarantee correct results, and loop invariants that make induction proofs possible. We’ll also cover ghost variables and logic functions for complex specifications.
