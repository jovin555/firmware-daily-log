---
title: "Day 16: Memory Protection Unit (MPU): Spatial Isolation"
date: 2026-06-28
tags: ["til", "cfse", "mpu", "spatial", "isolation"]
---

## What I Explored Today

Today I dove into the Memory Protection Unit (MPU) as a hardware mechanism for enforcing spatial isolation between software components in a safety-critical system. Unlike the MMU which handles virtual-to-physical address translation, the MPU is a simpler, deterministic unit that partitions physical memory into regions with access permissions. I implemented a basic MPU configuration on an ARM Cortex-M4 (STM32F4) to isolate a safety-critical control task from a non-critical logging task, ensuring that a stack overflow or wild pointer in the logger cannot corrupt the controller's state. The key takeaway: MPU-based spatial isolation is a foundational building block for Freedom From Interference (FFI) per ISO 26262-6, and getting the region attributes right is where most engineers stumble.

## The Core Concept

Spatial isolation answers a simple question: *How do we guarantee that Task A cannot read or write memory belonging to Task B?* In functional safety, this is not a "nice to have"—it's a requirement for ASIL decomposition and for proving that software elements do not interfere with each other.

The MPU provides this by defining a set of memory regions, each with:
- A base address and size (aligned to power-of-two boundaries)
- Access permissions (read, write, execute, no access)
- Sub-region disable bits (for finer granularity)
- An enable bit per region

When the CPU accesses memory, the MPU checks the address against all enabled regions. If the address falls outside any region, or if the access violates the region's permissions, the MPU raises a MemManage fault (on ARM Cortex-M) or a similar exception. This is a *hardware-enforced* boundary—no amount of software trickery can bypass it unless the MPU configuration itself is corrupted.

For functional safety, the critical insight is that the MPU must be configured *before* the tasks run, typically in the startup code or the RTOS kernel's initialization. Once set, the MPU operates in parallel with the CPU pipeline, adding zero cycle overhead for hits (accesses that fall within a defined region). Only a miss or violation triggers an exception, which is deterministic and takes a fixed number of cycles.

## Key Commands / Configuration / Code

Below is a practical example for an ARM Cortex-M4. I'm using the CMSIS-Core register definitions directly—no HAL abstractions, because in safety-critical work you want to know exactly what the hardware sees.

```c
#include "cmsis_armv7m.h"  // For ARM_MPU_* macros

/* Memory region definitions for a dual-task system */
#define REGION_0_BASE   0x20000000U  /* Start of SRAM */
#define REGION_0_SIZE   0x00008000U  /* 32 KB for safety task stack + data */
#define REGION_1_BASE   0x20008000U  /* Start of non-safety region */
#define REGION_1_SIZE   0x00008000U  /* 32 KB for logging task */

void MPU_Init(void) {
    /* Disable MPU before configuration (required by ARM spec) */
    ARM_MPU_Disable();

    /* Region 0: Safety-critical task memory — full access */
    ARM_MPU_SetRegion(
        0,                                          /* Region number */
        ARM_MPU_RBAR(REGION_0_BASE,                 /* Base address */
                     ARM_MPU_SH_NON_SHAREABLE),     /* Shareability: non-shareable */
        ARM_MPU_RASR(0,                             /* Execute Never: 0 = executable */
                     ARM_MPU_AP_PRIVILEGED_RW,      /* Access permission: privileged R/W only */
                     0,                             /* Sub-region disable: none */
                     ARM_MPU_REGION_SIZE_32KB,      /* Region size */
                     true)                          /* Enable region */
    );

    /* Region 1: Non-critical logging task — read-only for safety task */
    ARM_MPU_SetRegion(
        1,
        ARM_MPU_RBAR(REGION_1_BASE,
                     ARM_MPU_SH_NON_SHAREABLE),
        ARM_MPU_RASR(0,                             /* Execute Never: no code execution here */
                     ARM_MPU_AP_READONLY,           /* Access permission: read-only for privileged */
                     0,
                     ARM_MPU_REGION_SIZE_32KB,
                     true)
    );

    /* Enable MPU with default memory map for background regions */
    ARM_MPU_Enable(ARM_MPU_CTRL_PRIVDEFENA_Msk);
}
```

**Key points in the code:**
- `ARM_MPU_Disable()` must be called first—the MPU ignores writes to region registers while enabled.
- `ARM_MPU_SH_NON_SHAREABLE` is correct for single-core systems; multi-core would need shareable.
- `ARM_MPU_AP_PRIVILEGED_RW` means only privileged code (kernel, ISRs) can access Region 0. Unprivileged tasks will fault.
- `ARM_MPU_CTRL_PRIVDEFENA_Msk` enables the "default memory map" for privileged accesses—without this, privileged code also gets MPU-checked, which can break interrupt handlers.

**Runtime fault handling (simplified):**
```c
void MemManage_Handler(void) {
    uint32_t fault_addr;
    uint32_t fault_status;

    fault_addr   = SCB->MMFAR;    /* MemManage Fault Address Register */
    fault_status = SCB->CFSR;     /* Configurable Fault Status Register */

    /* Log fault info, then enter safe state */
    if (fault_status & (1U << 7)) {  /* MMARVALID bit */
        /* Address that caused the fault is valid */
        safe_state_enter(fault_addr);
    } else {
        /* Stacking error or other — enter safe state immediately */
        safe_state_enter(0);
    }
}
```

## Common Pitfalls & Gotchas

**1. Region alignment is strict—size must be a power of two, base must be aligned to size.**
If you try to define a 48 KB region starting at 0x20004000, the MPU will silently misalign it. The ARM architecture requires that the base address be a multiple of the region size. Always use `ARM_MPU_REGION_SIZE_*` macros and verify alignment in a unit test.

**2. The background region (PRIVDEFENA) is a double-edged sword.**
Enabling the default privileged region (`PRIVDEFENA`) allows privileged code to access any address not covered by an MPU region. This is convenient for kernel code, but it means a bug in a privileged ISR can still corrupt memory. For ASIL D, you may want to disable PRIVDEFENA and explicitly define regions for all memory, including peripherals and the vector table.

**3. Sub-region disable bits are tricky to get right.**
Each MPU region can be split into 8 equal sub-regions. Disabling a sub-region creates a "hole" in the region. This is useful for protecting a small data structure inside a larger buffer, but the sub-region size is `region_size / 8`. If your region is 64 KB, each sub-region is 8 KB—too coarse for fine-grained protection. Many engineers try to use sub-regions for stack guard pages and get the alignment wrong. Prefer separate small regions for guard pages instead.

## Try It Yourself

1. **Configure an MPU region for a stack guard page.** On your target MCU, set up a 4 KB region at the end of the safety task's stack with `ARM_MPU_AP_NO_ACCESS`. Verify that a stack overflow triggers a MemManage fault. Measure the fault latency with a logic analyzer.

2. **Implement unprivileged task switching.** Modify your RTOS (or a simple scheduler) to set the CONTROL register's nPRIV bit before entering a non-safety task. Ensure the task cannot access the MPU configuration registers (they are privileged-only). Confirm that a deliberate illegal access in the task causes a fault.

3. **Test region overlap behavior.** Configure two overlapping MPU regions with different permissions. On ARM Cortex-M, the higher-numbered region takes priority. Write a test that accesses the overlapping address and verify which permission set applies. Document this behavior in your project's safety manual.

## Next Up

Tomorrow, I'll tackle **Testing for Functional Safety: Coverage & Independence**—how to prove that your MPU configuration actually works, including structural coverage analysis (MC/DC) on the fault handler and independence arguments for the test environment.
