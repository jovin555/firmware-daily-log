---
title: "Day 27: Frama-C WP Plugin: Deductive Verification"
date: 2026-07-09
tags: ["til", "formal-verification", "wp", "deductive", "coq"]
---

## What I Explored Today

Today I dove into Frama-C's WP (Weakest Precondition) plugin, which performs deductive verification of C code. Unlike dynamic analysis or even symbolic execution, WP proves functional correctness by generating verification conditions (VCs) that, if proven, guarantee the code satisfies its specification for *all* possible inputs. I walked through annotating a small C function with ACSL contracts, running WP to generate proof obligations, and discharging them with the built-in SMT solver (Alt-Ergo) and the interactive theorem prover Coq. The key takeaway: WP is the tool you reach for when you need mathematical certainty about critical functions—not just "no crashes" but "this algorithm is correct."

## The Core Concept

Deductive verification works by transforming a program and its specification into a set of logical formulas. If every formula is provable, the program is correct. WP does this by computing the weakest precondition: given a postcondition (what must hold after execution), WP calculates the weakest condition on the initial state that guarantees the postcondition holds.

Why does this matter? Because testing can only cover finitely many inputs. Even fuzzing or symbolic execution with path exploration can miss corner cases. Deductive verification closes that gap—it's a proof, not a test. In practice, you use WP for functions where failure is catastrophic: cryptographic primitives, memory allocators, flight control laws, or any function with a precise mathematical specification.

The trade-off is effort. Writing ACSL annotations is manual work, and some VCs require interactive proof in Coq or Why3. But for a small, critical function, the payoff is absolute confidence.

## Key Commands / Configuration / Code

Let's walk through a concrete example. I wrote a simple function that computes the maximum of two integers, with a full ACSL contract.

```c
/* max.c */
/*@
  requires \valid(a) && \valid(b);
  assigns *a, *b;
  ensures *a >= *b;
  ensures *a == \old(*a) || *a == \old(*b);
  ensures *b == \old(*a) || *b == \old(*b);
  ensures (*a >= *b) && (*b <= *a);
*/
void max_swap(int *a, int *b) {
    int tmp;
    if (*a < *b) {
        tmp = *a;
        *a = *b;
        *b = tmp;
    }
}
```

Now run WP with Alt-Ergo:

```bash
# Generate VCs and attempt automatic proof
frama-c -wp -wp-rte -wp-prover alt-ergo max.c
```

Output:
```
[kernel] Parsing FRAMAC_SHARE/libc/__fc_builtin_for_normalization.i
[wp] Running WP plugin...
[wp] Collecting axiomatic usage
[wp] 7 goals scheduled
[wp] [Alt-Ergo] Goal typed_max_swap_assigns_part1 : Valid (4ms)
[wp] [Alt-Ergo] Goal typed_max_swap_assigns_part2 : Valid (3ms)
[wp] [Alt-Ergo] Goal typed_max_swap_postcondition_1 : Valid (2ms)
[wp] [Alt-Ergo] Goal typed_max_swap_postcondition_2 : Valid (2ms)
[wp] [Alt-Ergo] Goal typed_max_swap_postcondition_3 : Valid (3ms)
[wp] [Alt-Ergo] Goal typed_max_swap_postcondition_4 : Valid (2ms)
[wp] [Alt-Ergo] Goal typed_max_swap_rte_mem_access_1 : Valid (2ms)
[wp] [Alt-Ergo] Goal typed_max_swap_rte_mem_access_2 : Valid (2ms)
[wp] Proved goals: 7/7
```

All 7 VCs proved automatically. The `-wp-rte` flag adds runtime error checks (null pointer dereference, overflow) as additional proof obligations.

Now let's try something that requires interactive proof. A function with a loop:

```c
/* sum.c */
/*@
  requires n >= 0;
  requires \valid(arr + (0 .. n-1));
  assigns \nothing;
  ensures \result == \sum(0, n-1, arr);
*/
int array_sum(int *arr, int n) {
    int sum = 0;
    /*@
      loop invariant 0 <= i <= n;
      loop invariant sum == \sum(0, i-1, arr);
      loop assigns i, sum;
      loop variant n - i;
    */
    for (int i = 0; i < n; i++) {
        sum += arr[i];
    }
    return sum;
}
```

Running WP:

```bash
frama-c -wp -wp-rte sum.c
```

This time, Alt-Ergo might fail on the loop invariant involving `\sum`. You'll see:

```
[wp] [Alt-Ergo] Goal typed_array_sum_loop_inv_2 : Unknown (timeout)
```

Now you need to inspect the VC and prove it interactively. Generate Coq files:

```bash
frama-c -wp -wp-rte -wp-gen sum.c -then -wp-out ./wp_output
```

Open `wp_output/typed_array_sum_loop_inv_2_Coq.v` in CoqIDE or Proof General. The goal will be something like:

```
forall (arr:Z -> Z) (n:Z) (i:Z) (sum:Z),
  0 <= i <= n ->
  sum = sum_0_to_i_minus_1(arr, i) ->
  sum + arr[i] = sum_0_to_i(arr, i+1)
```

You'll need to write a lemma about `\sum` and apply induction. This is where the "deductive" part gets real.

## Common Pitfalls & Gotchas

1. **Missing loop invariants are the #1 cause of proof failure.** WP cannot automatically infer loop invariants. If you omit them, WP will generate unprovable VCs for the loop body. Always specify `loop invariant`, `loop assigns`, and `loop variant` (for termination).

2. **`\valid` is not transitive.** `\valid(p)` only checks that `p` points to a valid memory location of the declared type. If you have a pointer to a struct, `\valid(p)` does *not* imply `\valid(&p->field)`. You need explicit `\valid(&p->field)` or use `\valid_read` for read-only accesses.

3. **Integer overflow is real.** Without `-wp-rte`, WP assumes mathematical integers (unbounded). With `-wp-rte`, overflow becomes a proof obligation. If your code relies on wrapping behavior (e.g., `uint32_t` arithmetic), you must add `//@ assert` or use the `\wrapping` axiomatic. Otherwise, WP will flag overflow as a potential error.

## Try It Yourself

1. **Annotate a binary search function.** Write ACSL contracts for a `int binary_search(int *arr, int n, int key)` that returns the index or -1. Include loop invariants for the `while` loop. Run WP with Alt-Ergo. How many VCs are generated? How many are proved automatically?

2. **Force an interactive proof.** Take the `array_sum` example above. Remove the `loop assigns` clause and run WP. Observe the unprovable VC. Then add it back and try to prove the `\sum` invariant using Coq. (Hint: you'll need to define `\sum` recursively in Coq.)

3. **Prove a swap function without pointers.** Write `void swap(int *a, int *b)` that swaps two integers. Add a postcondition that the values are exchanged. Run WP. Then modify the function to use XOR swap (`*a ^= *b; *b ^= *a; *a ^= *b;`). Does WP still prove it? Why or why not?

## Next Up

Tomorrow, we'll switch gears to Frama-C's Eva plugin, which uses abstract interpretation to soundly approximate all possible program states. Where WP gives you proofs, Eva gives you alarms—and it scales to much larger codebases without annotations. We'll compare the two approaches and see when to use each.
