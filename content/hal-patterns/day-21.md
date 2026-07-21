---
title: "Day 21: Interrupt Abstraction: ISR Registration Patterns Across Vendors"
date: 2026-07-21
tags: ["til", "hal-patterns", "isr", "interrupts"]
---

## What I Explored Today

Today I dug into how different MCU vendors handle ISR registration in their HAL layers, and more importantly, how to abstract that into a portable, vendor-agnostic interrupt manager. I compared STM32's HAL, NXP's SDK, and Microchip's Harmony frameworks, then built a thin abstraction layer that lets application code register interrupt callbacks without caring whether the underlying hardware uses a vector table, NVIC, or PLIC. The key insight: every vendor has a different way to map interrupt sources to handler functions, but the pattern of "register a callback with a context pointer" is universal—it's just buried under different API names and initialization rituals.

## The Core Concept

Interrupt abstraction isn't about hiding the hardware—it's about isolating the *registration mechanism* so your application logic doesn't depend on whether you're writing to a VTOR register, calling `HAL_NVIC_SetPriority()`, or configuring a PLIC context. The real problem is that every vendor's HAL assumes *you* will write the interrupt handler in a specific file (like `stm32f4xx_it.c`), which couples your application code to the startup assembly and vector table layout.

A proper interrupt abstraction layer does three things:
1. Provides a single `register_isr(irq_id, callback, context)` function that works across all supported MCUs
2. Handles the critical section and priority mapping transparently
3. Manages the "trampoline" ISR that the vector table calls, which then dispatches to the registered callback

The pattern is simple: a fixed set of weak default handlers in the vector table point to a dispatcher function. The dispatcher looks up the registered callback in a table indexed by IRQ number. Your application never touches the vector table directly.

## Key Commands / Configuration / Code

Here's a portable interrupt manager that works across STM32 (Cortex-M) and NXP i.MX RT (Cortex-M with different NVIC layout). The key is the `irq_dispatcher` trampoline.

```c
// irq_manager.h — vendor-agnostic ISR registration
#ifndef IRQ_MANAGER_H
#define IRQ_MANAGER_H

#include <stdint.h>

typedef void (*irq_callback_t)(void *context);

typedef struct {
    irq_callback_t callback;
    void *context;
} irq_entry_t;

// Register a callback for a given IRQ number.
// Returns 0 on success, -1 if IRQ number is out of range.
int irq_register(uint32_t irq_num, irq_callback_t cb, void *ctx);

// Enable the interrupt in the NVIC (or equivalent).
void irq_enable(uint32_t irq_num);

// Disable the interrupt.
void irq_disable(uint32_t irq_num);

#endif
```

```c
// irq_manager.c — implementation with STM32 HAL backend
#include "irq_manager.h"
#include "stm32f4xx_hal.h"  // vendor-specific, isolated here

#define MAX_IRQS 256  // Cortex-M supports up to 256 external IRQs

static irq_entry_t irq_table[MAX_IRQS] = {0};

int irq_register(uint32_t irq_num, irq_callback_t cb, void *ctx) {
    if (irq_num >= MAX_IRQS) return -1;
    
    // Critical section: disable interrupts while modifying table
    __disable_irq();
    irq_table[irq_num].callback = cb;
    irq_table[irq_num].context = ctx;
    __enable_irq();
    
    return 0;
}

void irq_enable(uint32_t irq_num) {
    HAL_NVIC_SetPriority((IRQn_Type)irq_num, 0, 0);  // map priority
    HAL_NVIC_EnableIRQ((IRQn_Type)irq_num);
}

void irq_disable(uint32_t irq_num) {
    HAL_NVIC_DisableIRQ((IRQn_Type)irq_num);
}

// The dispatcher — called from vector table trampolines
void irq_dispatcher(uint32_t irq_num) {
    irq_entry_t *entry = &irq_table[irq_num];
    if (entry->callback) {
        entry->callback(entry->context);
    }
}
```

Now, in your vector table (or startup file), replace the default handlers with trampolines:

```c
// In stm32f4xx_it.c or a custom vector table override
void TIM2_IRQHandler(void) __attribute__((weak, alias("irq_dispatcher_trampoline_28")));

void irq_dispatcher_trampoline_28(void) {
    irq_dispatcher(28);  // TIM2 IRQ number
}
```

For NXP i.MX RT, the same `irq_manager.c` changes only the enable/disable functions:

```c
// NXP backend variant
#include "fsl_common.h"

void irq_enable(uint32_t irq_num) {
    NVIC_SetPriority((IRQn_Type)irq_num, 0);
    EnableIRQ((IRQn_Type)irq_num);
}

void irq_disable(uint32_t irq_num) {
    DisableIRQ((IRQn_Type)irq_num);
}
```

The application code stays identical:

```c
// app_timer.c — never touches NVIC or vector table directly
static void timer_callback(void *ctx) {
    // handle timer interrupt
    uint32_t *count = (uint32_t *)ctx;
    (*count)++;
}

void app_timer_init(void) {
    static uint32_t tick_count = 0;
    irq_register(28, timer_callback, &tick_count);  // TIM2 on STM32
    irq_enable(28);
}
```

## Common Pitfalls & Gotchas

1. **IRQ number mismatches across vendors.** STM32's `TIM2_IRQn` is 28, but on NXP's LPC series, the same timer might be IRQ 22. Your abstraction must either use a vendor-specific mapping header or require the caller to know the target's IRQ numbering. I've seen teams waste days debugging "interrupts not firing" because they assumed IRQ numbers were portable. Solution: define an enum in a platform header that maps logical names (e.g., `IRQ_TIMER2`) to physical numbers per target.

2. **Priority grouping differences.** Cortex-M0+ has only 4 priority levels (2 bits), while Cortex-M4 has 16 (4 bits). If your abstraction sets priority to 0 (highest) unconditionally, you may break lower-priority interrupts on M0+ that expect more granularity. Always query the hardware's priority bit width or use a platform-specific priority macro.

3. **Trampoline function overhead.** Each trampoline ISR adds a function call and a table lookup. On high-frequency interrupts (e.g., 1 MHz timer), this overhead can eat 50-100 cycles. Profile your worst-case ISR latency. For ultra-low-latency paths, consider a "fast path" registration that writes the callback address directly into the vector table (bypassing the dispatcher), but document it clearly.

## Try It Yourself

1. **Port the irq_manager to a new MCU.** Pick a Microchip SAM D21 (Cortex-M0+) and implement `irq_enable`/`irq_disable` using the `NVIC_EnableIRQ()` from the CMSIS-Core header. Verify that `irq_register` works with the SAM's IRQ numbering (check the datasheet's interrupt vector table).

2. **Add a priority parameter.** Extend `irq_register` to accept a `uint32_t priority` argument. In the STM32 backend, call `HAL_NVIC_SetPriority()` with it. In the NXP backend, use `NVIC_SetPriority()`. Test with a high-priority button interrupt and a low-priority UART interrupt to confirm preemption works.

3. **Measure trampoline overhead.** On your dev board, toggle a GPIO in the dispatcher and measure the time from interrupt assertion to callback execution using a logic analyzer. Compare against a direct ISR that calls the callback inline. Document the cycle count difference in your project's performance notes.

## Next Up

Tomorrow: **Migrating a Product Line to a New MCU: A HAL Case Study** — I'll walk through a real migration from STM32F4 to NXP i.MX RT, showing exactly how the interrupt abstraction layer saved us from rewriting 15,000 lines of application code. We'll cover the gotchas in peripheral mapping, clock tree differences, and the one DMA bug that took three weeks to find.
