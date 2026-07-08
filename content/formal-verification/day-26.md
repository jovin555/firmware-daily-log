---
title: "Day 26: ACSL Annotations: Preconditions, Postconditions & Invariants"
date: 2026-07-08
tags: ["til", "formal-verification", "acsl", "contracts", "annotations"]
---

## What I Explored Today

Today I dug into the core of Frama-C's specification language: ACSL (ANSI/ISO C Specification Language). While yesterday we ran our first E-ACSL runtime checks, today I focused on static annotations — the contracts that let us *prove* correctness without running the code. I learned how to write preconditions (`requires`), postconditions (`ensures`), and loop invariants (`loop invariant`), and how Frama-C's `-wp` and `-rte` plugins use these to verify memory safety and functional correctness.

## The Core Concept

Annotations are not comments — they are executable specifications. When you write `//@ requires n > 0;`, you're telling Frama-C's verification tools: "Assume this holds at entry, and prove the function body is safe under that assumption." The key insight is that annotations shift the burden of proof from runtime testing to compile-time logical reasoning.

Why does this matter? Because C has no built-in contract mechanism. A function like `int pop(int* stack, int* top)` silently trusts that `stack` is non-null and `*top >= 0`. Without annotations, every caller is a potential bug. With ACSL, you make those assumptions explicit and verifiable.

The three pillars are:
- **Preconditions** (`requires`): What must be true before the function executes.
- **Postconditions** (`ensures`): What the function guarantees after it returns.
- **Loop invariants** (`loop invariant`): Properties that hold before, during, and after every loop iteration.

## Key Commands / Configuration / Code

Let's start with a simple example — a function that computes factorial, with full contracts.

```c
/*@
  requires n >= 0;
  requires n <= 12;  // avoid overflow for 32-bit int
  ensures \result == \old(n) * factorial(n-1) || n == 0;
  assigns \nothing;
*/
int factorial(int n) {
    if (n == 0) return 1;
    return n * factorial(n - 1);
}
```

But that recursive spec is circular. Let's write an iterative version with a loop invariant:

```c
/*@
  requires n >= 0 && n <= 12;
  ensures \result == \old(n) * factorial(\old(n)-1) || \old(n) == 0;
  assigns \nothing;
*/
int factorial_iter(int n) {
    int result = 1;
    int i = 1;
    
    /*@
      loop invariant 1 <= i <= n+1;
      loop invariant result == factorial(i-1);
      loop assigns i, result;
      loop variant n - i;
    */
    while (i <= n) {
        result *= i;
        i++;
    }
    return result;
}
```

To verify this with Frama-C:
```bash
# Run WP plugin with ACSL annotations
frama-c -wp -wp-rte factorial.c -then -report

# For more verbose output showing each proof step
frama-c -wp -wp-rte -wp-timeout 30 factorial.c -then -report
```

Key points about the loop invariant:
- `loop invariant 1 <= i <= n+1`: The loop counter stays in bounds.
- `loop invariant result == factorial(i-1)`: The partial result matches the mathematical factorial.
- `loop assigns i, result`: Only these variables change in the loop.
- `loop variant n - i`: This integer expression must decrease each iteration (proves termination).

Now a more practical example — a bounded buffer push:

```c
#define BUFFER_SIZE 10

typedef struct {
    int data[BUFFER_SIZE];
    int count;
} Buffer;

/*@
  requires \valid(buffer);
  requires buffer->count >= 0 && buffer->count <= BUFFER_SIZE;
  requires buffer->count < BUFFER_SIZE;  // space available
  assigns buffer->data[buffer->count], buffer->count;
  ensures buffer->count == \old(buffer->count) + 1;
  ensures buffer->data[\old(buffer->count)] == value;
*/
void buffer_push(Buffer* buffer, int value) {
    buffer->data[buffer->count] = value;
    buffer->count++;
}
```

The `\valid` predicate checks pointer validity. `\old` refers to the pre-state value. `assigns` tells the prover which memory locations may change.

## Common Pitfalls & Gotchas

1. **Over-specifying loop invariants**: Beginners often write invariants that are too weak (can't prove postcondition) or too strong (can't prove invariant itself). The invariant must be inductive — true before the loop, and preserved by one iteration. Start with the simplest invariant that captures the loop's purpose, then strengthen it.

2. **Forgetting `loop assigns`**: Without `loop assigns`, WP assumes the loop modifies *everything*, which breaks proofs. Always list exactly which variables and memory locations the loop body changes. For pointer-heavy code, use `loop assigns *p, count;` to include pointed-to memory.

3. **Integer overflow in annotations**: ACSL uses mathematical integers (unbounded), but C integers overflow. If you write `ensures \result == x + y;` and `x + y` overflows in C, the annotation is false. Use `\is_signed_overflow` or limit ranges with preconditions like `requires x + y <= INT_MAX;`.

## Try It Yourself

1. **Add contracts to a binary search function**: Write `requires` that the array is sorted and non-null, `ensures` that the result is either -1 or a valid index with the target value, and a loop invariant that maintains the search range `[low, high]`.

2. **Verify a swap function**: Write contracts for `void swap(int* a, int* b)` that guarantee `*a == \old(*b) && *b == \old(*a)`. Use `\valid` and `assigns`. Run `frama-c -wp` and see if it proves.

3. **Fix a broken invariant**: Given this buggy loop:
```c
int sum = 0;
for (int i = 0; i < 10; i++) {
    sum += i;
}
```
Write a loop invariant that correctly captures `sum == i*(i-1)/2`. Then change the loop to `i <= 10` and see why the invariant fails.

## Next Up

Tomorrow we dive into **Frama-C WP Plugin: Deductive Verification** — the heavy lifter that turns your ACSL annotations into logical proof obligations. We'll explore how WP generates verification conditions, how to interpret proof failures, and how to use `-wp-prop` to target specific properties. Bring your most complex pointer arithmetic — we're going to prove it correct.
