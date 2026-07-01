---
title: "Day 19: Compiler Optimizations: What -O2 Does to Your Driver"
date: 2026-07-01
tags: ["til", "cpp-embedded", "optimization", "compiler", "asm"]
---

## What I Explored Today

I spent the morning with `arm-none-eabi-objdump` disassembling the same driver compiled at `-O0` and `-O2`. The difference was staggering: a 12-line ISR at `-O0` ballooned to 47 instructions with stack frame pushes and spills everywhere, while `-O2` reduced it to 19 instructions with zero stack usage. But I also found a `volatile` access that the optimizer had completely elided—my carefully placed status-polling loop was gone. Today’s deep dive: what `-O2` actually does to your embedded C++ driver, and how to keep it from breaking your hardware assumptions.

## The Core Concept

Compiler optimizations are not magic—they are a set of provably safe transformations applied to your source code. At `-O2`, GCC enables all standard optimizations that don’t involve a space-speed tradeoff (that’s `-Os`) or aggressive loop unrolling (that’s `-O3`). For embedded drivers, the critical transformations are:

- **Dead Store Elimination**: If you write to a variable and never read it before the next write, the first write is removed.
- **Common Subexpression Elimination**: Repeated calculations (like `base + offset`) are computed once and reused.
- **Function Inlining**: Small functions are expanded at the call site, eliminating call/return overhead.
- **Loop Invariant Code Motion**: Calculations that don’t change inside a loop are hoisted outside.
- **Instruction Scheduling**: Instructions are reordered to avoid pipeline stalls.

The problem? These transformations assume your code follows the C++ abstract machine rules. Hardware registers and memory-mapped I/O do not. If you forget `volatile`, the optimizer sees your register write as a dead store and removes it. If you use a non-atomic flag for inter-core communication, the optimizer may reorder or cache it in a register.

## Key Commands / Configuration / Code

### 1. Checking What the Compiler Did

```bash
# Compile with -O2 and keep assembly
arm-none-eabi-g++ -O2 -S -mcpu=cortex-m4 -mthumb driver.cpp -o driver_O2.s

# Compare with -O0
arm-none-eabi-g++ -O0 -S -mcpu=cortex-m4 -mthumb driver.cpp -o driver_O0.s

# Diff the two
diff -u driver_O0.s driver_O2.s | less
```

### 2. A Driver Function Before and After

```cpp
// driver.cpp - UART transmit with status polling
#include <cstdint>

#define UART_BASE 0x40004000
#define UART_SR   (*(volatile uint32_t*)(UART_BASE + 0x00))
#define UART_DR   (*(volatile uint32_t*)(UART_BASE + 0x04))
#define TX_EMPTY  (1 << 7)

void uart_send_byte(char c) {
    // Wait until TX buffer empty
    while (!(UART_SR & TX_EMPTY)) {
        // spin
    }
    UART_DR = c;
}
```

**At `-O0`**: The while loop loads `UART_SR` from memory each iteration, checks the bit, and branches. Stack frame is 8 bytes.

**At `-O2`**: The compiler sees `UART_SR` is `volatile`, so it must reload each iteration. But it also notices the loop body is empty—it can’t optimize the loop away because `volatile` accesses are side effects. The resulting assembly is tight:

```asm
uart_send_byte:
    ldr     r3, [pc, #8]    ; load address of UART_SR
    ldr     r2, [pc, #8]    ; load address of UART_DR
.L2:
    ldr     r1, [r3, #0]    ; volatile load
    tst     r1, #128        ; check TX_EMPTY bit
    beq     .L2             ; loop if not set
    strb    r0, [r2, #0]    ; volatile store
    bx      lr
```

### 3. The Bug That -O2 Exposes

```cpp
// BUGGY: missing volatile
uint32_t* uart_sr = (uint32_t*)(UART_BASE + 0x00);

void uart_send_byte_buggy(char c) {
    while (!(*uart_sr & TX_EMPTY)) {}  // Optimizer: infinite loop or removed!
    UART_DR = c;
}
```

At `-O2`, the compiler loads `*uart_sr` once into a register, then loops forever checking the register (which never changes). The hardware register may have updated, but the compiler doesn’t know that—it’s not `volatile`.

## Common Pitfalls & Gotchas

### 1. `volatile` Is Not Atomic
`volatile` prevents the optimizer from eliding or reordering accesses, but it does **not** guarantee atomicity. On a Cortex-M4, a 32-bit `volatile` read is naturally atomic, but a 64-bit `volatile` read may be split into two 32-bit reads. If an ISR modifies the upper half between reads, you get a torn value. Use `std::atomic` with `memory_order_relaxed` for lock-free inter-core or ISR communication.

### 2. `-O2` Can Reorder Non-Volatile Accesses
Even with `volatile` for your registers, the compiler can reorder non-volatile memory accesses around them. This is fine for most drivers, but if you have a sequence like:
```cpp
REG_CTRL = START_CONVERSION;  // volatile
result = sensor_data;          // non-volatile
```
The compiler may move the `sensor_data` read before the `START_CONVERSION` write. Use a `std::atomic_thread_fence(std::memory_order_release)` or a compiler barrier (`asm volatile("" ::: "memory")`) to enforce ordering.

### 3. `-O2` Inlines Everything It Can
Your carefully layered HAL with virtual functions? At `-O2`, if the compiler can determine the dynamic type at compile time, it will devirtualize and inline the entire call chain. This is great for performance but terrible for code size. If you need a stable ABI or small binary, mark critical functions with `__attribute__((noinline))`.

## Try It Yourself

1. **Disassemble your own driver**: Take any peripheral driver you’ve written (GPIO, SPI, I2C). Compile it with `-O0` and `-O2`, then diff the assembly. Count the instruction reduction. Identify any `volatile` accesses that survived optimization.

2. **Break your driver**: Remove `volatile` from one register access in your driver. Recompile with `-O2` and observe the behavior (ideally on a simulator or with a logic analyzer). Confirm the loop disappears or becomes infinite.

3. **Add a compiler barrier**: In a critical sequence (e.g., enable peripheral, then read status), insert `asm volatile("" ::: "memory")` between the two operations. Disassemble and verify the ordering is preserved even at `-O2`.

## Next Up

Tomorrow is **Day 20: Full Review & Project: C++ HAL for a Sensor Driver**. We’ll take everything from the past 19 days—placement new, constexpr, volatile, atomics, and optimization—and build a complete, production-quality HAL for an I2C temperature sensor. You’ll write the driver, compile it at `-O2`, and verify the assembly is exactly what you expect. See you then.
