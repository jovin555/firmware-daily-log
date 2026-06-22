---
title: "Day 08: ACSL Annotations: Preconditions, Postconditions & Invariants"
date: 2026-06-22
tags: ["til", "formal-verification", "acsl", "contracts", "annotations"]
---

## What I Explored Today

Today I dove into the heart of Frama-C's specification language: ACSL (ANSI/ISO C Specification Language). After spending the past week getting toolchains installed and running basic analyses, I finally wrote my first real contracts. The power of attaching formal preconditions, postconditions, and loop invariants directly to C code is transformative — it turns a function from a black box into a mathematically specified component. I verified a binary search implementation and a simple bounded queue, and the experience of watching Frama-C prove (or disprove) my assumptions in real time was genuinely addictive.

## The Core Concept

Most engineers write comments like `/* n must be > 0 */` and hope for the best. ACSL makes those comments executable — the analyzer can check them statically. The why is simple: without contracts, every function is a trust boundary. With contracts, you get:

- **Preconditions** (`requires`): What the caller must guarantee before calling.
- **Postconditions** (`ensures`): What the callee guarantees after returning.
- **Loop invariants** (`loop invariant`): What remains true before, during, and after each loop iteration.

These three annotations form the backbone of deductive verification. The magic happens when Frama-C's WP (Weakest Precondition) plugin proves that if the precondition holds, the postcondition must hold — for *all* possible inputs. No unit test suite can match that coverage.

## Key Commands / Configuration / Code

Let's start with a binary search function annotated with ACSL contracts. Save this as `binary_search.c`:

```c
/*@
  requires n > 0;
  requires \valid_read(arr + (0 .. n-1));
  requires \forall integer i, j; 0 <= i <= j < n ==> arr[i] <= arr[j];
  
  assigns \nothing;
  
  behavior found:
    assumes \exists integer i; 0 <= i < n && arr[i] == target;
    ensures \result >= 0 && \result < n && arr[\result] == target;
  
  behavior not_found:
    assumes \forall integer i; 0 <= i < n ==> arr[i] != target;
    ensures \result == -1;
  
  complete behaviors;
  disjoint behaviors;
*/
int binary_search(int arr[], int n, int target) {
    int left = 0;
    int right = n - 1;
    
    /*@
      loop invariant 0 <= left <= right + 1 <= n;
      loop invariant \forall integer i; 0 <= i < n && arr[i] == target ==>
                        left <= i <= right;
      loop assigns left, right;
      loop variant (right - left + 1);
    */
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] == target)
            return mid;
        else if (arr[mid] < target)
            left = mid + 1;
        else
            right = mid - 1;
    }
    return -1;
}
```

Key annotations explained:
- `\valid_read(arr + (0 .. n-1))` — the array is readable for all n elements.
- `\forall integer i, j; ...` — the array is sorted (a quantifier over integers).
- `assigns \nothing` — no side effects on global state.
- `behavior found/not_found` — separates proof obligations for each case.
- `complete behaviors; disjoint behaviors;` — tells Frama-C these cover all possibilities without overlap.
- `loop invariant` — critical: the search range always stays within bounds.
- `loop variant` — proves termination (the range shrinks each iteration).

Run the verification with:

```bash
frama-c -wp -wp-rte binary_search.c
```

The `-wp-rte` flag adds runtime error checks (division by zero, out-of-bounds access). If all annotations are correct, you'll see:

```
[wp] Proved goals: 18 / 18
```

Now, a bounded queue example to show invariants on structs:

```c
#define QUEUE_SIZE 10

typedef struct {
    int data[QUEUE_SIZE];
    int head;
    int tail;
    int count;
} Queue;

/*@
  predicate is_valid_queue(Queue *q) =
    \valid(q) &&
    0 <= q->head < QUEUE_SIZE &&
    0 <= q->tail < QUEUE_SIZE &&
    0 <= q->count <= QUEUE_SIZE &&
    (q->count == 0 || \valid_read(&q->data[q->head]));
*/

/*@
  requires \valid(q) && is_valid_queue(q);
  requires q->count < QUEUE_SIZE;
  assigns q->data[q->tail], q->tail, q->count;
  ensures q->count == \old(q->count) + 1;
  ensures q->data[\old(q->tail)] == value;
  ensures is_valid_queue(q);
*/
void enqueue(Queue *q, int value) {
    q->data[q->tail] = value;
    q->tail = (q->tail + 1) % QUEUE_SIZE;
    q->count++;
}
```

The `is_valid_queue` predicate encapsulates the invariant — any function that modifies the queue must preserve it. This is the essence of data structure verification.

## Common Pitfalls & Gotchas

1. **Forgetting `\valid` for pointer parameters.** Frama-C assumes nothing about pointers. If you pass a pointer without `\valid(p)`, the prover will flag every dereference as potentially invalid. Always annotate pointer inputs.

2. **Over-specifying loop invariants.** Newcomers often write invariants that are too weak (the loop can't be proven) or too strong (the invariant itself can't be proven). The sweet spot: the invariant should be just strong enough to imply the postcondition, and weak enough to be established by the loop body. Start with bounds and work up to data relationships.

3. **Ignoring `loop assigns`.** Without `loop assigns`, Frama-C assumes the loop modifies *everything* reachable through pointers, which kills precision. Always list exactly which variables the loop modifies. For the binary search, `loop assigns left, right;` is correct — `mid` is local and reinitialized each iteration.

4. **Quantifiers on unbounded types.** `\forall integer i;` is fine because ACSL integers are mathematical (unbounded). But avoid `\forall unsigned int i;` — the prover may struggle with the finite wrap-around semantics. Stick to `integer` in specifications.

## Try It Yourself

1. **Add overflow protection:** Take the binary search example and add a precondition that `left + right` does not overflow (hint: use `\forall` with the actual integer bounds). Then change `mid = left + (right - left) / 2` to `mid = (left + right) / 2` and see if Frama-C catches the potential overflow.

2. **Prove a swap function:** Write a `swap(int *a, int *b)` with ACSL contracts. The postcondition should state that `*a == \old(*b)` and `*b == \old(*a)`. Use `\old()` to refer to pre-call values. Verify with `-wp`.

3. **Fix a broken invariant:** Take the queue example, remove the `q->count == 0 || \valid_read(...)` clause from the predicate, and run verification. Observe which proof fails. Then add it back and confirm all goals pass.

## Next Up

Tomorrow we go deeper: **Frama-C WP Plugin: Deductive Verification**. We'll move from writing contracts to understanding how the Weakest Precondition calculus actually proves them — including how to read WP's proof tree output, handle non-linear arithmetic, and use lemma functions to break down complex proofs. Bring your own buggy sorting algorithm.
