---
title: "Day 15: Watchdog Timers: Hardware & Software WDT Strategies"
date: 2026-06-27
tags: ["til", "cfse", "watchdog", "wdt", "safety"]
---

## What I Explored Today

Today I dug into the practical implementation of watchdog timers (WDT) for functional safety systems. I focused on the distinction between hardware-independent windowed watchdogs and software-based supervisory watchdogs, and how to configure them on a real Cortex-M4 MCU (STM32F4 series). I also implemented a multi-layer watchdog strategy that prevents a single-point fault from disabling the entire safety mechanism.

## The Core Concept

A watchdog timer is the last line of defense against software runaway. But the *way* you kick it matters enormously. The naive approach — a single `HAL_WDG_Refresh()` in the main loop — is dangerous because a fault that keeps the main loop running (e.g., an infinite loop in an ISR that doesn't block the main loop) will still kick the watchdog. The system is alive but functionally dead.

The key insight from IEC 61508 and ISO 26262 is that a watchdog must detect *functional* correctness, not just *execution* presence. This leads to two complementary strategies:

1. **Hardware Windowed WDT** — The MCU's internal watchdog enforces a strict time window: you must kick it *after* a minimum time and *before* a maximum time. If you kick too early (e.g., stuck in a fast loop) or too late (e.g., stuck in a blocking call), it resets the system.

2. **Software Supervisory WDT** — An external watchdog IC (like the TPS3823 or MAX6369) is fed by a dedicated safety task that checks multiple health signals (task execution counters, stack margin, critical variable integrity) before toggling the WDI pin. This catches faults the internal WDT cannot see.

The real-world strategy is a **layered approach**: internal WDT for immediate MCU-level faults, external WDT for system-level faults, and a software health monitor that validates application logic before either watchdog gets kicked.

## Key Commands / Configuration / Code

### 1. Hardware Windowed WDT on STM32F4 (IWDG with Window)

```c
// Configure IWDG with window option
// LSI = 32 kHz, prescaler = 64 => 2 kHz counter
// Window = 0x7FF (upper limit), Reload = 0xFFF (lower limit)
// Kick must occur between 1.6s and 3.2s

void IWDG_Config(void) {
    // Enable write access to IWDG registers
    IWDG->KR = 0x5555;
    
    // Set prescaler to 64 (div by 64)
    IWDG->PR = 0x03;  // PR[2:0] = 011 => 64
    
    // Set reload value: 0xFFF => 4095 ticks
    // At 2 kHz, 4095 ticks = 2.0475 seconds (lower bound)
    IWDG->RLR = 0xFFF;
    
    // Set window value: 0x7FF => 2047 ticks
    // At 2 kHz, 2047 ticks = 1.0235 seconds (upper bound)
    IWDG->WINR = 0x7FF;
    
    // Start watchdog (write 0xCCCC to KR)
    IWDG->KR = 0xCCCC;
    
    // Lock registers
    IWDG->KR = 0x0000;
}

// Kick function — must be called in the window
void IWDG_Refresh(void) {
    // Write 0xAAAA to KR to reload counter
    IWDG->KR = 0xAAAA;
}
```

**Critical**: The window is *inverted* from intuition. `WINR` is the *maximum* counter value allowed for a kick. If the counter is above `WINR` (i.e., too much time has passed), the kick is rejected. If the counter is below `RLR` (i.e., too little time has passed), the kick is also rejected. The kick must happen when `WINR < counter < RLR`.

### 2. External Supervisory WDT with Health Monitor

```c
// Pseudocode for a safety task that feeds external WDT
// Runs at 100 Hz (10 ms period)

static uint32_t task_exec_counters[NUM_TASKS];
static uint32_t crc_checksum;

void SafetyMonitor_Task(void) {
    // 1. Check all task execution counters
    for (int i = 0; i < NUM_TASKS; i++) {
        if (task_exec_counters[i] < EXPECTED_MIN[i] ||
            task_exec_counters[i] > EXPECTED_MAX[i]) {
            // Task i is misbehaving — don't kick WDT
            Safety_ErrorHandler(SAFETY_ERR_TASK_MISS, i);
            return;
        }
        // Reset counter for next period
        task_exec_counters[i] = 0;
    }
    
    // 2. Validate critical data integrity
    uint32_t computed_crc = CRC_Calculate(&safety_critical_data, 
                                           sizeof(safety_critical_data));
    if (computed_crc != crc_checksum) {
        Safety_ErrorHandler(SAFETY_ERR_CRC_MISMATCH, 0);
        return;
    }
    
    // 3. Check stack margin (measure stack pointer vs limit)
    uint32_t current_sp = __get_MSP();
    if (current_sp < STACK_LIMIT_SAFE) {
        Safety_ErrorHandler(SAFETY_ERR_STACK_OVERFLOW, 0);
        return;
    }
    
    // 4. All checks passed — toggle WDI pin for external WDT
    HAL_GPIO_TogglePin(WDI_GPIO_Port, WDI_Pin);
}
```

### 3. Multi-Layer Kick Sequence

```c
void System_Health_Kick(void) {
    // Layer 1: Software health check (runs every 100 ms)
    if (SafetyMonitor_AllChecksPass()) {
        // Layer 2: Kick external WDT (100 ms period)
        HAL_GPIO_WritePin(WDI_GPIO_Port, WDI_Pin, GPIO_PIN_SET);
        delay_us(10);
        HAL_GPIO_WritePin(WDI_GPIO_Port, WDI_Pin, GPIO_PIN_RESET);
        
        // Layer 3: Kick internal windowed WDT (must be in 1.0-2.0s window)
        // Only kick if we're in the correct time window
        if (IWDG_IsInWindow()) {
            IWDG_Refresh();
        }
    }
}
```

## Common Pitfalls & Gotchas

### 1. Kicking the WDT in an ISR
The most common mistake. If you kick the watchdog inside a periodic timer ISR, the main application can hang completely while the ISR keeps the watchdog happy. **Never** kick a safety-critical WDT from an interrupt context. Always kick from a task that validates application-level health.

### 2. Windowed WDT Configuration Order
On STM32, you must configure the window *before* starting the watchdog. If you start the IWDG first (write 0xCCCC), then try to set `WINR`, the write is ignored because the registers are locked. The correct order is: unlock → set PR → set RLR → set WINR → start → lock. I've seen production boards bricked because the window was never actually set.

### 3. External WDT Glitch Filtering
External watchdog ICs often have a glitch filter on the WDI pin. If your toggle pulse is too short (e.g., a single GPIO toggle without a delay), the IC may not see it and will time out. Always ensure the WDI pulse width exceeds the IC's minimum specification (typically 1 µs for the TPS3823, but check the datasheet).

## Try It Yourself

1. **Implement a windowed IWDG on an STM32F4**: Configure the IWDG with a 1.0-2.0 second window. Write a test that kicks it at 500 ms (too early) and verify the reset occurs. Then kick at 1.5 seconds and verify normal operation.

2. **Build a software health monitor**: Create three periodic tasks (100 Hz, 50 Hz, 10 Hz). Each task increments a counter. Write a safety monitor that checks all counters are within ±10% of expected and only then toggles an external WDT pin. Intentionally stop one task and observe the WDT timeout.

3. **Multi-layer kick with fault injection**: Combine the internal windowed WDT with an external WDT. Inject a fault that corrupts a critical variable (e.g., set a CRC to zero). Verify that the internal WDT is *not* kicked (because the health check fails), but the external WDT is also *not* kicked. Both watchdogs should fire.

## Next Up

Tomorrow: **Memory Protection Unit (MPU): Spatial Isolation** — How to configure the MPU to prevent stack overflow from corrupting critical data, and how to set up background regions that catch wild pointer accesses before they corrupt safety variables.
