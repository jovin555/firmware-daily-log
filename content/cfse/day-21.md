---
title: "Day 21: Functional Safety Overview: What It Is & Why It Matters"
date: 2026-07-03
tags: ["til", "cfse", "functional-safety", "iec61508"]
---

## What I Explored Today

Today I stepped back from the implementation weeds to build a solid mental model of functional safety as a discipline. I’ve been writing safety-critical firmware for years, but I never formally mapped the landscape: what functional safety *is*, why it exists as a separate engineering domain, and how standards like IEC 61508 structure the work. I walked through the core definitions, the risk-based philosophy, and the concrete difference between “safe” and “reliable.” This is the foundation everything else—SIL levels, hazard analysis, safety functions—rests on.

## The Core Concept

Functional safety is not about making a system never fail. It’s about making a system *fail safely*. That distinction matters because in the real world, components fail. Wires corrode. RAM flips bits. A microcontroller’s program counter jumps to an uninitialized address. Functional safety engineering assumes these events will happen and designs the system so that when they do, the system either continues to operate correctly (fault tolerance) or transitions to a safe state (fault reaction).

The “why” is straightforward: without functional safety, a single undetected hardware fault can lead to a catastrophic event—a car that doesn’t brake, a robotic arm that crushes a person, a medical infusion pump that delivers a lethal dose. Standards like IEC 61508 exist to provide a systematic, auditable framework for reducing residual risk to an acceptable level. They force you to ask: *What can go wrong? How bad is it? How likely is it? And what must we do to make it unlikely enough?*

A common misconception is that functional safety equals high reliability (MTBF). It doesn’t. A system can be highly reliable but unsafe—imagine a brake-by-wire system that never fails but, when it does, locks the wheels. Conversely, a system can be less reliable but safe—a brake system that fails to a “brakes applied” state. Functional safety is about *controlling* failures, not eliminating them.

## Key Commands / Configuration / Code

Let’s ground this in something you can run today. A simple watchdog timer (WDT) is the most basic functional safety mechanism. Here’s a real configuration for an STM32G4 using the hardware independent watchdog (IWDG) with a timeout of ~1.6 seconds:

```c
// stm32g4_iwdg_config.c
#include "stm32g4xx_hal.h"

void Safety_WDT_Init(void)
{
    // Enable LSI oscillator (32 kHz typical)
    // IWDG runs from LSI, independent of main clock
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_LSI;
    RCC_OscInitStruct.LSIState = RCC_LSI_ON;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
    {
        // Fault: LSI failed to start — enter safe state
        Safety_EnterSafeState();
    }

    // Configure IWDG: prescaler = 32, reload = 625
    // Timeout = (32 * 625) / 32000 ≈ 0.625 seconds
    // But we want ~1.6s: prescaler = 64, reload = 800
    // Timeout = (64 * 800) / 32000 = 1.6 seconds
    IWDG_HandleTypeDef hiwdg = {0};
    hiwdg.Instance = IWDG;
    hiwdg.Init.Prescaler = IWDG_PRESCALER_64;   // 64 prescaler
    hiwdg.Init.Reload    = 800;                  // 800 counter reload
    hiwdg.Init.Window    = 0xFFF;                // Window disabled (0xFFF)
    if (HAL_IWDG_Init(&hiwdg) != HAL_OK)
    {
        // Fault: IWDG init failed — enter safe state
        Safety_EnterSafeState();
    }
}

void Safety_WDT_Refresh(void)
{
    // Must be called before the counter reaches zero
    // In a safety-critical loop, call this exactly once per cycle
    HAL_IWDG_Refresh(&hiwdg);
}
```

This is not just a “keep alive” tickle. In a functional safety context, the WDT is a *safety function*: it detects if the main control loop hangs or crashes. The refresh must happen at a deterministic point in the cycle, not scattered randomly. If the WDT expires, the hardware resets the MCU—a transition to a safe state (assuming the reset brings the system to a known, safe configuration).

## Common Pitfalls & Gotchas

1. **Confusing reliability with safety.** I’ve seen teams pour effort into increasing MTBF while ignoring failure modes that lead to hazardous states. A power supply with 99.999% uptime is great, but if its single failure mode is “output goes to 48V on a 3.3V rail,” you have a safety problem. Always analyze failure modes, not just failure rates.

2. **Treating the watchdog as a “tickle me” timer.** The most common mistake is refreshing the WDT in an interrupt service routine (ISR) or a high-priority task, masking a main-loop hang. The WDT must monitor the *safety-critical control flow*, not just the interrupt handler. Refresh it only after you’ve verified that all safety checks passed in the main loop.

3. **Ignoring common-cause failures.** A single fault can disable multiple safety mechanisms simultaneously. For example, a voltage spike that kills both the primary MCU and the watchdog’s LSI oscillator. Standards require you to consider *independent* channels—separate power domains, separate clocks, separate silicon—to achieve higher SIL levels.

## Try It Yourself

1. **Map your current project’s failure modes.** Take one safety-critical function (e.g., motor stop, valve close). List every single-point failure that could prevent it from working. For each, ask: “Does the system detect this? What safe state does it enter?” You’ll likely find gaps.

2. **Implement a watchdog with a deterministic refresh point.** On your dev board, configure the IWDG (or external watchdog) with a 1-second timeout. Write your main loop so that the refresh happens *only* after all safety checks (e.g., CRC of critical data, sensor plausibility) pass. If a check fails, don’t refresh—let the watchdog reset.

3. **Calculate the residual risk for a simple system.** Pick a component (e.g., a relay). Look up its failure rate (λ) in FITs. Assume a dangerous failure mode fraction (e.g., 20% of failures are “stuck closed”). Compute the probability of dangerous failure per hour (PFH). Compare that to the SIL 2 target (PFH < 10⁻⁷). This exercise makes the numbers real.

## Next Up

Tomorrow, I’ll dive into the backbone standard: **IEC 61508**. We’ll break down its seven parts, the concept of Safety Integrity Levels (SIL 1–4), and how the standard scopes the entire safety lifecycle—from hazard analysis to decommissioning. If you’ve ever wondered how a SIL 3 system differs from SIL 2 in practice, that’s where we’re headed.
