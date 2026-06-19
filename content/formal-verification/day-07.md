---
title: "Day 07: Frama-C Architecture: Plugins, ACSL & Value Analysis"
date: 2026-06-19
tags: ["til", "formal-verification", "frama-c", "acsl", "value-analysis"]
---

## What I Explored Today

Today I dug into Frama-C's plugin architecture and how it uses ACSL (ANSI/ISO C Specification Language) to drive analysis. The key insight is that Frama-C is not a single tool—it's a modular platform where plugins like Eva (the value analysis plugin) consume ACSL-annotated C code to produce sound over-approximations of program behavior. I walked through installing Frama-C, writing a simple annotated function, and running Eva to see what it actually computes.

## The Core Concept

Frama-C's architecture is built around a shared kernel that parses C code and ACSL annotations into an AST. Plugins register to analyze or transform this AST. The most practical plugin for embedded engineers is **Eva** (formerly "Value Analysis"), which performs abstract interpretation to compute possible ranges for every variable at every program point.

Why does this matter? Because C code in embedded systems is full of undefined behavior—signed integer overflow, out-of-bounds array access, null pointer dereference. Eva doesn't just find bugs; it proves their absence (or reports a definitive counterexample). The "sound over-approximation" means Eva may report false positives (it's conservative), but it will never miss a real bug.

ACSL is the glue. Without annotations, Eva can only infer very loose bounds. With preconditions (`requires`), postconditions (`ensures`), and loop invariants (`loop invariant`), you constrain the analysis to your actual domain. For example, if a function parameter is always between 0 and 100, you write `requires 0 <= x <= 100;` and Eva uses that to narrow its analysis.

## Key Commands / Configuration / Code

First, install Frama-C (I used the Opam package manager on Ubuntu 22.04):

```bash
# Install Frama-C with Eva plugin
opam install frama-c
# Verify installation
frama-c --version
# Should output something like: 28.0 (Niobium)
```

Now, a concrete example. Consider a function that computes the average of an array:

```c
/* average.c */
#include <stddef.h>

/*@
  requires n > 0;
  requires \valid(arr + (0 .. n-1));
  assigns \nothing;
  ensures \result == \sum(0, n-1, \lambda integer i; arr[i]) / n;
*/
int average(int *arr, size_t n) {
    int sum = 0;
    /*@
      loop invariant 0 <= i <= n;
      loop invariant sum == \sum(0, i-1, \lambda integer j; arr[j]);
      loop assigns i, sum;
      loop variant n - i;
    */
    for (size_t i = 0; i < n; i++) {
        sum += arr[i];
    }
    return sum / (int)n;
}
```

Run Eva with the following command:

```bash
frama-c -eva -eva-precision 2 average.c -then -report
```

Breakdown of flags:
- `-eva` : invoke the Eva plugin (value analysis)
- `-eva-precision 2` : set analysis precision (0-11, higher = more precise but slower)
- `-then` : chain another analysis (here, the report plugin)
- `-report` : print a summary of proved/unproved properties

Expected output (abbreviated):

```
[kernel] Parsing average.c (with preprocessing)
[eva] Analyzing a complete application starting at main
[eva] Computing initial state
[eva] Done for function average
[report] Summary:
  - 3 properties proved (preconditions, loop invariants, postcondition)
  - 0 properties remaining to be proved
```

If you remove the `requires n > 0` annotation and run again, Eva will warn that `n` could be zero, causing division by zero. Try it:

```bash
# Remove the requires line, then:
frama-c -eva average.c -then -report
# Eva will report: "division by zero" at the return statement
```

## Common Pitfalls & Gotchas

1. **Eva needs a `main` function by default.** If you analyze a library function without a caller, Eva assumes all inputs are fully unconstrained (e.g., `int` can be any 32-bit value). Use `-eva-entry` to specify an entry point, or write a small test harness that calls your function with constrained inputs.

2. **Loop invariants must be inductive.** A common mistake is writing a loop invariant that holds at loop entry but doesn't propagate. For example, `loop invariant sum == \sum(0, i-1, arr);` is correct only if you also assert that `i` doesn't overflow. Always include bounds on the loop counter.

3. **ACSL `\valid` requires pointer + offset range.** Writing `\valid(arr)` only checks that `arr` itself is a valid pointer (non-null, aligned). To check an array of `n` elements, you must write `\valid(arr + (0 .. n-1))`. Forgetting the range leads to false positives on array accesses.

## Try It Yourself

1. **Add a precondition to prevent overflow.** Modify the `average` function to include `requires \forall integer i; 0 <= i < n ==> arr[i] >= 0;` and `requires \forall integer i; 0 <= i < n ==> arr[i] <= 100;`. Re-run Eva and observe that the sum overflow check passes.

2. **Analyze a function with an off-by-one error.** Write a function that copies `n` bytes from `src` to `dst` but uses `for (i = 0; i <= n; i++)`. Add proper ACSL annotations and run Eva. It should report an out-of-bounds write.

3. **Use `-eva-slevel` to increase unrolling.** For a small loop (e.g., `for (i=0; i<5; i++)`), run Eva with `-eva-slevel 10` and compare the precision of the results versus the default. Check the `[eva]` log for "unrolling" messages.

## Next Up

Tomorrow we dive into **ACSL Annotations: Preconditions, Postconditions & Invariants**—the bread and butter of specifying function contracts. We'll cover how to write contracts that Eva can prove automatically, and how to debug when it can't.
