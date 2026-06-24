---
title: "Day 12: Architectural Design for Safety: Fault Isolation"
date: 2026-06-24
tags: ["til", "iec62304", "safety-architecture"]
---

## What I Explored Today

Today I dug into the architectural pattern of fault isolation as required by IEC 62304 §5.3.4 — specifically, how to partition a medical device software system so that a failure in one module cannot propagate to corrupt safety-critical functions. I focused on hardware-enforced memory protection (MPU/MMU), software-based partitioning via static analysis, and the runtime checks needed to prove that isolation actually holds under all conditions.

## The Core Concept

Fault isolation is not just "good software engineering" — it's a regulatory requirement for any medical device with a Software Safety Classification of B or C. The standard demands that the architecture must prevent a fault in a non-safety module (e.g., a logging service, a UI animation thread) from corrupting the state of a safety-critical module (e.g., the infusion pump rate controller, the defibrillator charge logic).

The *why* is straightforward: in a single-address-space embedded system (which most RTOS-based devices are), a wild pointer in a low-criticality task can silently overwrite the code or data of a high-criticality task. Without isolation, you cannot claim that your safety functions are dependable — because any other module's bug becomes your safety module's bug.

The practical approach is a **layered isolation model**:

1. **Hardware isolation** (MPU/MMU) — prevents unauthorized memory access at the CPU level.
2. **Software partitioning** — uses static analysis and coding standards to ensure modules cannot directly reference each other's private data.
3. **Runtime integrity checks** — periodic CRC/checksum verification of safety-critical code and data regions.

IEC 62304 does not mandate *which* isolation technique you use, but it does require that you document the mechanism and verify it works. Most auditors expect to see evidence that a fault injection in a non-safety module cannot corrupt a safety module's memory.

## Key Commands / Configuration / Code

### 1. ARM Cortex-M MPU Configuration (CMSIS-Core)

This configures a 32 KB region for the safety-critical task stack, with no-execute and read-only for non-safety tasks.

```c
// mpu_config.c — ARM Cortex-M4 MPU region setup
// Region 0: Safety-critical task stack (0x20000000, 32 KB)
MPU->RNR  = 0;                      // Region number
MPU->RBAR = 0x20000000              // Base address
           | MPU_RBAR_VALID_Msk     // Region valid
           | (0 << 0);              // Region number (redundant)
MPU->RASR = (0x1A << 1)             // AP: read-only by privileged, no access by unprivileged
           | (0x04 << 16)           // Size: 2^(4+1) = 32 KB
           | MPU_RASR_ENABLE_Msk;   // Enable region

// Region 1: Non-safety heap (0x20008000, 16 KB) — no-execute
MPU->RNR  = 1;
MPU->RBAR = 0x20008000 | MPU_RBAR_VALID_Msk | (1 << 0);
MPU->RASR = (0x03 << 1)             // AP: full access
           | (0x03 << 16)           // Size: 2^(3+1) = 16 KB
           | (1 << 28)              // XN: execute never
           | MPU_RASR_ENABLE_Msk;
```

### 2. Static Partitioning with `__attribute__((section))`

Use linker sections to physically separate safety-critical and non-safety data. The linker script then places them in different MPU regions.

```c
// partition.h — enforce module boundaries at compile time
#define SAFE_RAM   __attribute__((section(".safety_data")))
#define UNSAFE_RAM __attribute__((section(".non_safety_data")))

// Safety-critical module — cannot be accessed by non-safety code
SAFE_RAM volatile uint32_t infusion_rate_ml_per_hour;
SAFE_RAM uint8_t safety_task_stack[4096] __attribute__((aligned(32)));

// Non-safety module — can be corrupted, but cannot touch safety data
UNSAFE_RAM char log_buffer[1024];
UNSAFE_RAM uint32_t ui_animation_frame_counter;
```

### 3. Runtime Memory Integrity Check (CRC-32)

Periodically verify that safety-critical regions have not been corrupted. This catches MPU misconfigurations or transient faults.

```c
// integrity_check.c — run from safety-critical task every 100 ms
#include "stm32f4xx_hal.h"  // hardware CRC peripheral

#define SAFE_REGION_START  ((uint32_t)0x20000000)
#define SAFE_REGION_SIZE   (32 * 1024)  // 32 KB

uint32_t expected_crc = 0xA5B6C7D8;  // computed at build time

bool check_safety_region_integrity(void) {
    uint32_t actual_crc = HAL_CRC_Calculate(&hcrc, 
                                            (uint32_t*)SAFE_REGION_START, 
                                            SAFE_REGION_SIZE / 4);
    if (actual_crc != expected_crc) {
        // Fault detected — enter safe state
        safety_shutdown(SHUTDOWN_REASON_MEMORY_CORRUPTION);
        return false;
    }
    return true;
}
```

## Common Pitfalls & Gotchas

### 1. MPU Region Alignment Requirements
ARM Cortex-M MPU regions **must** be aligned to their size. A 32 KB region must start at an address that is a multiple of 32 KB. If you try to place a safety stack at `0x20001000` with size 32 KB, the MPU will silently round down the base address to `0x20000000`, potentially exposing adjacent memory. Always use `__attribute__((aligned(N)))` where N is the region size.

### 2. Interrupts Bypass MPU Protection
On Cortex-M, interrupt handlers run in privileged mode and can access all memory, regardless of MPU settings. If a non-safety module triggers an interrupt that writes to a safety-critical buffer, isolation is broken. You must either:
- Route all interrupts through a safety-critical dispatcher that validates the data, or
- Use a dual-stack architecture where interrupt handlers only touch pre-validated memory.

### 3. Static Analysis False Negatives
`__attribute__((section))` does not prevent a non-safety `.c` file from `extern`-ing a safety variable. The compiler will happily link them. You need a **build-time check** — I use a Python script that parses the linker map and flags any non-safety object file that references a `.safety_data` symbol. Add this to your CI pipeline.

## Try It Yourself

1. **Configure an MPU region for your RTOS task stack** — Pick a safety-critical task (e.g., the one controlling a motor). Set up an MPU region that makes its stack read-only for all other tasks. Trigger a deliberate write from a lower-priority task and observe the MemManage fault handler.

2. **Write a build-time symbol checker** — Create a script that reads your ELF file's symbol table and reports any non-safety object file that references a symbol in the `.safety_data` section. Integrate it into your Makefile or CMake build.

3. **Implement a periodic CRC check** — Add a 100 ms timer that computes a CRC-32 over your safety-critical data region. If the CRC mismatches, log the fault and enter a safe state (e.g., disable outputs and blink an error LED). Measure the overhead — it should be < 1% CPU on a 100 MHz Cortex-M4.

## Next Up

Tomorrow: **MISRA C for Medical: Compliant Coding Guidelines** — I'll walk through the mandatory MISRA C:2012 rules that IEC 62304 auditors actually check, with real examples of rule violations that caused recall-level bugs.
