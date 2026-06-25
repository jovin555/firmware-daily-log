---
title: "Day 13: Safe State & Fail-Safe Design Patterns for Firmware"
date: 2026-06-25
tags: ["til", "cfse", "fail-safe", "safe-state"]
---

## What I Explored Today

Today I dug into the practical implementation of safe states and fail-safe patterns in embedded firmware. While most engineers understand the high-level concept—"when something breaks, go to a safe condition"—the devil is in the details: how do you detect the fault, how do you transition cleanly, and how do you ensure the system *stays* safe even when the main controller is compromised? I worked through three concrete patterns: the watchdog-backed safe state, the hardware override latch, and the degraded-mode state machine. Each solves a different failure scenario, and none of them rely on the main application logic being correct.

## The Core Concept

A safe state is not just "turn everything off." For a motor controller, the safe state might be "coast" (remove drive current), but for a braking system, it might be "full apply." The safe state is defined by the hazard analysis—specifically, which system condition minimizes risk when a fault is detected.

The critical insight is that **the firmware must assume it cannot trust itself** when entering a safe state. If a stack overflow corrupts your control loop, you cannot rely on that same control loop to execute a graceful shutdown. This is why fail-safe patterns always involve a *hardware-independent* path to the safe state. The firmware's job is to detect the fault and trigger that path, not to execute the safety action itself.

Three principles govern every fail-safe design:
1. **Deterministic entry**: The path to safe state must be known and bounded in time.
2. **Latching behavior**: Once entered, the system must not spontaneously leave the safe state without explicit, verified recovery.
3. **Independence**: The detection mechanism must be separate from the execution mechanism.

## Key Commands / Configuration / Code

### Pattern 1: Watchdog-Backed Safe State with I/O Latch

This pattern uses a hardware watchdog timer (WDT) and a GPIO-controlled latch. If the firmware fails to pet the watchdog, the WDT reset triggers a bootloader that drives the safety-critical outputs to a known state.

```c
// safe_state_wdt.c — STM32G4 example with independent watchdog (IWDG)

#include "stm32g4xx_hal.h"

// Safety-critical output: motor enable line, active LOW for safe state
#define SAFE_OUTPUT_PIN    GPIO_PIN_0
#define SAFE_OUTPUT_PORT   GPIOA
#define SAFE_STATE_ACTIVE  GPIO_PIN_RESET  // LOW = motor disabled

// Latch enable: once set, only power cycle clears it
#define LATCH_PIN          GPIO_PIN_1
#define LATCH_PORT         GPIOA

void Safety_Init(void) {
    // Configure safe output as push-pull, initially safe
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = SAFE_OUTPUT_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(SAFE_OUTPUT_PORT, &gpio);
    HAL_GPIO_WritePin(SAFE_OUTPUT_PORT, SAFE_OUTPUT_PIN, SAFE_STATE_ACTIVE);

    // Configure latch pin as output, initially inactive
    gpio.Pin = LATCH_PIN;
    HAL_GPIO_Init(LATCH_PORT, &gpio);
    HAL_GPIO_WritePin(LATCH_PORT, LATCH_PIN, GPIO_PIN_RESET);

    // Start independent watchdog with 100ms timeout
    // IWDG runs from LSI (32 kHz), prescaler = 32 => 1 kHz tick
    // Reload = 100 => 100 ms timeout
    IWDG_HandleTypeDef hiwdg = {0};
    hiwdg.Instance = IWDG;
    hiwdg.Init.Prescaler = IWDG_PRESCALER_32;
    hiwdg.Init.Reload = 100;
    hiwdg.Init.Window = 0xFFF;  // no window
    HAL_IWDG_Init(&hiwdg);
}

void Safety_EnterSafeState(void) {
    // Step 1: Drive output to safe state (redundant, in case it drifted)
    HAL_GPIO_WritePin(SAFE_OUTPUT_PORT, SAFE_OUTPUT_PIN, SAFE_STATE_ACTIVE);

    // Step 2: Assert latch — this holds safe state even after WDT reset
    HAL_GPIO_WritePin(LATCH_PORT, LATCH_PIN, GPIO_PIN_SET);

    // Step 3: Stop petting watchdog — system will reset in 100ms
    // On reset, bootloader checks latch and keeps outputs safe
    while(1) {
        __WFI();  // Wait for interrupt, never pet watchdog
    }
}

// Called from main loop at > 100 Hz
void Safety_PetWatchdog(void) {
    // Only pet if latch is NOT asserted (system is healthy)
    if(HAL_GPIO_ReadPin(LATCH_PORT, LATCH_PIN) == GPIO_PIN_RESET) {
        HAL_IWDG_Refresh(&hiwdg);
    }
}
```

### Pattern 2: Degraded-Mode State Machine

For systems that can tolerate reduced functionality, a state machine with explicit safe transitions prevents invalid states.

```c
// safe_state_machine.h
typedef enum {
    SAFE_STATE_NORMAL,
    SAFE_STATE_DEGRADED,   // e.g., reduced speed, limited torque
    SAFE_STATE_SAFE        // full shutdown
} SafeState_t;

typedef struct {
    SafeState_t current;
    uint32_t    degraded_timeout_ms;  // max time in degraded before safe
    uint32_t    degraded_entry_tick;
    bool        latch_asserted;
} SafeStateMachine_t;

// safe_state_machine.c
void SafeStateMachine_Update(SafeStateMachine_t *sm) {
    switch(sm->current) {
        case SAFE_STATE_NORMAL:
            // If fault detected, transition to degraded
            if(FaultDetector_HasFault()) {
                sm->current = SAFE_STATE_DEGRADED;
                sm->degraded_entry_tick = HAL_GetTick();
                // Reduce output limits immediately
                Actuator_SetMaxTorque(MAX_TORQUE_DEGRADED);
            }
            break;

        case SAFE_STATE_DEGRADED:
            // If fault clears, return to normal
            if(!FaultDetector_HasFault()) {
                sm->current = SAFE_STATE_NORMAL;
                Actuator_SetMaxTorque(MAX_TORQUE_NORMAL);
                break;
            }
            // If timeout exceeded, escalate to safe
            if((HAL_GetTick() - sm->degraded_entry_tick) > sm->degraded_timeout_ms) {
                sm->current = SAFE_STATE_SAFE;
                Safety_EnterSafeState();  // uses pattern 1
            }
            break;

        case SAFE_STATE_SAFE:
            // No exit — must be power-cycled or explicitly recovered
            break;
    }
}
```

## Common Pitfalls & Gotchas

1. **Petting the watchdog in an ISR**: If your main loop hangs but interrupts still fire, a watchdog petted in an ISR will mask the fault. Always pet the watchdog from the main loop context, not from a timer interrupt. Better yet, use a *windowed* watchdog (WWDT) that requires petting within a specific time window—too early or too late both cause a reset.

2. **Safe state that depends on firmware execution**: I've seen designs where the "safe state" is entered by calling a function that writes to a register. If the CPU has crashed (e.g., hard fault, stack corruption), that function call will never execute. The safe state must be the *default* hardware state—e.g., a pull-down resistor on a MOSFET gate that keeps the load off unless the firmware actively drives it high.

3. **Recovery without verification**: After a fault, some engineers reset the latch and return to normal operation immediately. This is dangerous—the root cause may still be present. Always require a deliberate recovery sequence (e.g., power cycle, or a specific command from a verified external source) before leaving the safe state.

## Try It Yourself

1. **Audit your current project**: Identify all outputs that could cause harm if driven incorrectly. For each one, determine: is the safe state the *default* hardware state (e.g., pull-down/pull-up), or does it require firmware action? If the latter, redesign the hardware to make the safe state the default.

2. **Implement a latch-based safe state**: On your dev board, wire a GPIO to an LED (simulating a safety-critical output) and another GPIO to a second LED (simulating the latch). Write firmware that enters safe state when a button is pressed, asserts the latch, and stops petting the watchdog. Verify that after the watchdog reset, the output stays in safe state.

3. **Add a degraded mode state machine**: Take an existing control loop (e.g., a simple PID motor controller) and add a degraded state that limits output to 50% when a sensor fault is detected. Add a timeout that escalates to full safe state after 5 seconds. Test with simulated faults.

## Next Up

Tomorrow, I'll explore **Diversity & Redundancy: Hardware & Software Strategies**—how to use dissimilar computation channels, lockstep cores, and diverse compilers to detect and mask faults that a single implementation would miss. We'll look at ARM's lockstep Cortex-R cores and how to implement software diversity without doubling your codebase.
