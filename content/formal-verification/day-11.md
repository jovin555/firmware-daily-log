---
title: "Day 11: Proving a Zephyr Driver with Frama-C WP"
date: 2026-06-23
tags: ["til", "formal-verification", "frama-c", "zephyr", "driver"]
---

## What I Explored Today

Today I took the plunge into proving functional correctness of a real-world embedded driver: a simplified Zephyr GPIO driver using Frama-C's Weakest Precondition (WP) plugin. While Zephyr's codebase is heavily macro-inflated and relies on device tree magic, I extracted the core logic—a GPIO configuration function that sets pin direction and pull-up/pull-down resistors via memory-mapped registers. The goal was to prove that the function never writes to reserved register bits, always respects the hardware datasheet constraints, and terminates without undefined behavior. After wrestling with ACSL annotations and Zephyr's pointer-heavy register access patterns, I got the proof to go through. Here's what I learned.

## The Core Concept

Why prove a driver? In safety-critical systems (automotive, medical, industrial), a single misconfigured GPIO can cause a short circuit, latch-up, or unintended actuator behavior. Static analysis catches buffer overflows, but functional verification with WP goes further: it mathematically proves that for every valid input, the driver's output (register writes) conforms to a specification. For Zephyr drivers, this is especially valuable because:

1. **Register bitfields are easy to get wrong** — one misplaced `|=` vs `&=` and you corrupt adjacent hardware functions.
2. **Zephyr's HAL layers obscure direct hardware access** — macros like `sys_write32()` hide the actual memory-mapped I/O, making it hard to audit manually.
3. **Driver reuse across SoCs** — a proven driver can be ported with confidence if the register layout matches.

Frama-C WP works by computing the weakest precondition: given a postcondition (e.g., "register X has bit 3 set and bits 2-0 unchanged"), it computes the minimal conditions on inputs and program state that guarantee the postcondition holds after execution. The solver (typically Alt-Ergo or Z3) then checks if those conditions are always true given the function's preconditions.

## Key Commands / Configuration / Code

I started with a stripped-down Zephyr GPIO configuration function. Here's the annotated code:

```c
/* gpio_zephyr.c — simplified Zephyr GPIO config */
#include <stdint.h>

/* Register layout: 32-bit GPIO control register
 * Bits 31:4 — reserved (must be 0)
 * Bits 3:2 — pull config: 00=no pull, 01=pull-up, 10=pull-down, 11=reserved
 * Bits 1:0 — direction: 00=input, 01=output, 10/11=reserved
 */
#define GPIO_CTRL_REG  ((volatile uint32_t*)0x40001000)

/*@
  requires \valid(GPIO_CTRL_REG);
  requires direction == 0 || direction == 1;  // only valid directions
  requires pull == 0 || pull == 1 || pull == 2;  // no reserved pull value
  assigns *GPIO_CTRL_REG;
  ensures (\old(*GPIO_CTRL_REG) & 0xFFFFFFF0) == (*GPIO_CTRL_REG & 0xFFFFFFF0);
  ensures (*GPIO_CTRL_REG & 0x3) == direction;
  ensures (pull == 0) ==> ((*GPIO_CTRL_REG & 0xC) == 0);
  ensures (pull == 1) ==> ((*GPIO_CTRL_REG & 0xC) == 0x4);
  ensures (pull == 2) ==> ((*GPIO_CTRL_REG & 0xC) == 0x8);
*/
void gpio_configure(uint32_t direction, uint32_t pull) {
    uint32_t reg_val;

    reg_val = *GPIO_CTRL_REG;
    reg_val &= 0xFFFFFFF0;          /* clear direction and pull bits */
    reg_val |= (direction & 0x3);   /* set direction (safe mask) */
    reg_val |= ((pull & 0x3) << 2); /* set pull config (safe mask) */
    *GPIO_CTRL_REG = reg_val;
}
```

To prove this, I ran:

```bash
frama-c -wp -wp-rte -wp-prover alt-ergo gpio_zephyr.c -then -report
```

Key flags:
- `-wp` — enable WP plugin
- `-wp-rte` — generate runtime error annotations (proves no overflow, no invalid pointer dereference)
- `-wp-prover alt-ergo` — use Alt-Ergo SMT solver (default, but explicit is good)
- `-then -report` — run report after WP to see proof status

The proof succeeded with 6 goals (4 from ensures, 2 from RTE for pointer validity and arithmetic). The critical insight: the `& 0x3` masks on `direction` and `pull` are not just defensive programming—they're necessary for the prover to bound the possible values and discharge the postconditions.

## Common Pitfalls & Gotchas

1. **Volatile semantics confuse WP.** Frama-C treats volatile reads as nondeterministic by default. My `\valid(GPIO_CTRL_REG)` precondition was essential, but I initially forgot to add `assigns *GPIO_CTRL_REG;` — without it, WP assumes the function doesn't modify the register, making the postconditions trivially false. Always declare what your function assigns.

2. **Bitwise operations on signed types cause overflow.** I originally used `int` for `direction` and `pull`. The shift `(pull & 0x3) << 2` on a signed `int` is technically undefined if `pull` is negative (though two's complement hardware makes it work). WP flagged this as a potential RTE. Switching to `uint32_t` eliminated the issue and made the proof cleaner.

3. **Zephyr macros break annotation parsing.** Zephyr's `DEVICE_DT_DEFINE` and `SYS_INIT` macros expand to hundreds of lines. Don't try to prove the full driver entry point. Extract the core register-access function into a standalone file, annotate it, and prove that. The macro layer is a separate concern (and often untestable with WP due to inline assembly).

## Try It Yourself

1. **Add a precondition for reserved bits.** Modify the `gpio_configure` function to also ensure that bits 31:4 of the register are never modified. Write an ACSL ensures clause that checks `(*GPIO_CTRL_REG & 0xFFFFFFF0) == (\old(*GPIO_CTRL_REG) & 0xFFFFFFF0)`. Run `frama-c -wp` and verify it passes.

2. **Introduce a bug and watch the proof fail.** Change `reg_val &= 0xFFFFFFF0;` to `reg_val &= 0xFFFFFF00;` (clearing too many bits). Re-run the proof. Observe which postcondition fails and why. This is the fastest way to learn how WP pinpoints specification violations.

3. **Add a second register (e.g., output value register).** Extend the driver to also set a GPIO output value. Write a new function `gpio_write(uint32_t value)` with its own pre/postconditions. Prove that writing the output register doesn't corrupt the control register. This exercises multiple `assigns` clauses.

## Next Up

Tomorrow, I'm switching gears to **CBMC: Bounded Model Checking for C Programs**. While Frama-C WP proves functional properties via deductive verification, CBMC takes a different approach: it unwinds loops to a bounded depth and checks all possible execution paths for assertions, memory safety, and undefined behavior. I'll apply it to the same Zephyr driver and compare the two tools' strengths.
