---
title: "Day 09: Frama-C WP Plugin: Deductive Verification"
date: 2026-06-22
tags: ["til", "formal-verification", "wp", "deductive", "coq"]
---

## What I Explored Today

Today I dove into Frama-C's WP (Weakest Precondition) plugin, which performs deductive verification of C code against ACSL (ANSI/ISO C Specification Language) contracts. Unlike dynamic analysis or testing, WP mathematically proves that a function's implementation satisfies its specification for *all* possible inputs. I ran through several examples, from simple integer contracts to pointer-based memory safety proofs, and exported verification conditions to Coq for interactive proof when the automatic SMT solvers couldn't close a goal.

## The Core Concept

Deductive verification with WP works by transforming a C function and its ACSL contract into a set of logical formulas called verification conditions (VCs). The WP plugin computes the weakest precondition: given a postcondition `Q`, it calculates the minimal precondition `P` such that if `P` holds before execution, `Q` holds after. The SMT solvers (Alt-Ergo, Z3, CVC4) then attempt to prove these VCs automatically.

The key insight is that WP reasons about the *semantics* of the code, not just its syntax. This catches bugs that static analyzers miss—like integer overflow that only occurs on specific execution paths, or buffer overruns that depend on complex pointer arithmetic. For embedded systems, this is critical: we can prove that a function never divides by zero, never overflows, and always respects its postconditions, regardless of compiler optimizations or input values.

## Key Commands / Configuration / Code

Let's start with a simple function that computes the absolute difference between two integers:

```c
/* diff.c */
#include <limits.h>

/*@
  requires \valid_read(a) && \valid_read(b);
  requires INT_MIN < *a - *b < INT_MAX;  // no overflow
  ensures \result == (*a >= *b ? *a - *b : *b - *a);
  assigns \nothing;
*/
int abs_diff(const int *a, const int *b) {
    if (*a >= *b) {
        return *a - *b;
    } else {
        return *b - *a;
    }
}
```

Run WP with the default SMT solver (Alt-Ergo):

```bash
frama-c -wp -wp-rte diff.c
```

The `-wp-rte` flag inserts runtime error annotations for division by zero, overflow, and out-of-bounds access. WP will try to prove these annotations as well.

For more complex proofs, we can use `-wp-prover` to select a different solver:

```bash
frama-c -wp -wp-prover z3 -wp-timeout 30 diff.c
```

Now a more realistic example—a bounded buffer copy with memory safety:

```c
/* buffer_copy.c */
/*@
  requires \valid(dst + (0..len-1));
  requires \valid_read(src + (0..len-1));
  requires \separated(dst + (0..len-1), src + (0..len-1));
  ensures  \forall integer i; 0 <= i < len ==> dst[i] == \old(src[i]);
  assigns  dst[0..len-1];
*/
void buffer_copy(int *dst, const int *src, unsigned len) {
    /*@ loop invariant 0 <= i <= len;
        loop invariant \forall integer j; 0 <= j < i ==> dst[j] == \old(src[j]);
        loop assigns i, dst[0..len-1];
        loop variant len - i;
    */
    for (unsigned i = 0; i < len; ++i) {
        dst[i] = src[i];
    }
}
```

Run with memory model support:

```bash
frama-c -wp -wp-model Typed+Cast buffer_copy.c
```

The `-wp-model Typed+Cast` enables reasoning about pointer aliasing and casts. Without it, WP assumes all pointers are distinct, which is unsafe for real code.

When WP can't prove a VC automatically, export to Coq:

```bash
frama-c -wp -wp-proof coq -wp-out proof/ diff.c
```

This generates Coq files in `proof/`. You can then open them in CoqIDE or Proof General:

```coq
(* proof/abs_diff_Why.v snippet *)
Require Import ZArith.
(* ... generated goals ... *)
```

## Common Pitfalls & Gotchas

**1. Missing loop invariants are the #1 reason WP fails.** WP cannot automatically infer loop invariants for anything beyond trivial loops. If you omit them, WP will report "unable to prove" for any property that depends on loop behavior. Always provide `loop invariant`, `loop assigns`, and `loop variant` (for termination).

**2. Integer overflow assumptions differ between C and SMT solvers.** C has undefined behavior on signed overflow, but SMT solvers treat integers as mathematical integers (unbounded). Use `-wp-rte` to insert explicit overflow checks, or use `unsigned` types where possible. Without RTE, WP might prove properties that rely on wraparound behavior that C doesn't guarantee.

**3. Pointer aliasing kills automatic proofs.** WP's default memory model assumes no aliasing unless you use `\separated` or the `Typed` model. If two pointers might alias, add `\separated` clauses or use `-wp-model Typed+Cast`. Otherwise, WP will prove things that aren't true in the actual program.

## Try It Yourself

1. **Prove a division function**: Write a function `int safe_div(int a, int b)` that returns `a/b` but only if `b != 0` and the division doesn't overflow (i.e., `a != INT_MIN || b != -1`). Add ACSL contracts and prove all RTE annotations with WP.

2. **Fix a failing proof**: Take the `buffer_copy` example above and remove the `\separated` requirement. Run WP—it will fail on the `assigns` clause. Add the correct `\separated` annotation and re-run until all VCs are proved.

3. **Export to Coq**: Write a function that computes `x * 2` using bit shifts. Add a contract that proves the result equals `x * 2` for all non-negative `x`. Run WP with `-wp-proof coq` and inspect the generated Coq file. Try to understand the goal structure.

## Next Up

Tomorrow, we'll switch gears to **Frama-C Eva Plugin: Abstract Interpretation for C**. While WP proves properties for all inputs via symbolic reasoning, Eva uses abstract interpretation to compute over-approximations of possible program states—scaling to larger codebases without requiring manual annotations. We'll compare the two approaches and see when to use each.
