---
title: "Day 01: ARM Security Architecture: TrustZone for Cortex-A & Cortex-M"
date: 2026-06-13
tags: ["til", "trustzone", "trustzone", "arm", "security"]
---

## What I Explored Today

I finally dug into the hardware-level separation that makes TrustZone tick across ARM's two major processor families. While the marketing materials all say "hardware-enforced isolation," the actual implementation differs significantly between Cortex-A (application processors running Linux/Android) and Cortex-M (microcontrollers running bare-metal or RTOS). Today I traced the memory bus signals, examined the security state machine, and wrote my first test harness to toggle between Secure and Non-Secure worlds on a Cortex-M33.

## The Core Concept

TrustZone isn't a hypervisor or a software sandbox — it's a hardware partitioning scheme embedded into the ARM bus fabric. The fundamental insight is that every transaction on the system bus carries an extra bit: the Non-Secure (NS) bit. This bit propagates through every memory controller, DMA engine, and peripheral bridge. If a Non-Secure master tries to access a Secure-only region, the bus fabric returns an error before the access even reaches the target.

On Cortex-A, this manifests as two virtual processors: the "Normal World" (Non-Secure, NS=1) and the "Secure World" (Secure, NS=0). The monitor mode (a special processor mode) handles the context switch via the `SMC` instruction. On Cortex-M, the architecture is simpler: the processor has a unified pipeline but maintains separate stack pointers and memory protection configurations per security state. The key difference is that Cortex-M uses a banked set of registers rather than a full context switch — the transition is faster but less flexible.

The "why" is critical: without TrustZone, a kernel compromise means total system compromise. With TrustZone, even if the rich OS (Linux, FreeRTOS) is fully owned by an attacker, the Secure world's DRM keys, biometric templates, and boot credentials remain isolated. The Secure world can also act as a "security monitor" that validates every transition.

## Key Commands / Configuration / Code

### 1. Checking TrustZone Support on Cortex-M (via CMSIS-Core)

```c
#include "arm_cmse.h"   // Cortex-M Security Extensions

void check_tz_support(void) {
    // Read the Security Extension feature register
    uint32_t sctlr = __get_SCTLR();
    if (sctlr & (1U << 0)) {   // Bit 0: M profile Security Extension
        printf("TrustZone is ENABLED on this core\n");
    } else {
        printf("TrustZone NOT available\n");
    }
}
```

### 2. Configuring a Secure Memory Region (SAU)

The Security Attribution Unit (SAU) defines which address ranges are Secure, Non-Secure, or Non-Secure Callable (NSC — allows entry points from NS to S).

```c
// Configure SAU region 0: 0x20000000-0x2000FFFF as Secure
SAU->RNR  = 0;                    // Select region 0
SAU->RBAR = 0x20000000 & SAU_RBAR_BADDR_Msk;  // Base address
SAU->RLAR = (0x2000FFFF & SAU_RLAR_LADDR_Msk) | SAU_RLAR_ENABLE_Msk;  // Limit + enable
SAU->RLAR |= (0 << 1);            // NS=0 → Secure region

// Enable SAU globally
SAU->CTRL = SAU_CTRL_ENABLE_Msk | SAU_CTRL_ALLNS_Msk;  // Enable, all not-defined = NS
```

### 3. Transitioning from Non-Secure to Secure (via SG instruction)

On Cortex-M, the Non-Secure world calls a Secure function through a Non-Secure Callable (NSC) entry point:

```asm
; Assembly stub for Secure Gateway (SG) entry
__attribute__((section(".gnu.sgstubs")))
void secure_entry_point(void) {
    __asm volatile(
        "SG            \n"   // Secure Gateway instruction
        "BL secure_fn  \n"   // Branch to actual secure function
        "BX lr         \n"   // Return to NS world
    );
}
```

The linker script must place this at an NSC-aligned address (32-byte aligned on M33):

```ld
.nsc_region : ALIGN(32) {
    KEEP(*(.gnu.sgstubs))
} > FLASH_NS
```

### 4. Verifying Security State at Runtime

```c
uint32_t get_current_security_state(void) {
    // Read CONTROL register bit 0: 0=Secure, 1=Non-Secure
    uint32_t control = __get_CONTROL();
    return (control & 1) ? 0 : 1;  // Return 1 for Secure
}
```

## Common Pitfalls & Gotchas

**1. Forgetting the SAU covers all masters, not just the CPU.**
If you mark a memory region as Secure, that includes DMA controllers. A Non-Secure DMA transfer to that region will silently fail — no interrupt, no error flag on many DMA engines. Always configure the SAU before enabling DMA, and test with a known pattern.

**2. NSC alignment is strict — 32 bytes on Cortex-M33, 128 bytes on Cortex-M55.**
If your Secure Gateway entry point isn't aligned, the processor will fault with a UsageFault (INVSTATE) when the Non-Secure world tries to call it. I wasted two hours debugging this because the linker script defaulted to 4-byte alignment.

**3. Interrupts don't cross security boundaries automatically.**
A Non-Secure interrupt handler cannot directly call Secure functions. You must route the interrupt through the NVIC's security configuration (NVIC->ITNS registers) or use a Secure-only interrupt that signals the NS world via a shared memory flag.

## Try It Yourself

1. **SAU Region Walk**: On a Cortex-M33 development board (NXP LPC55S69 or STM32L5), write a test that configures the first 4KB of SRAM as Secure. Then have the Non-Secure world attempt a store to that address. Observe the HardFault — capture the fault status register (CFSR) to confirm it's a MemManage fault with the "MSTKERR" bit set.

2. **NSC Entry Timing**: Measure the cycle count for a Non-Secure to Secure function call using the DWT cycle counter. Compare it to a regular function call. On Cortex-M33, expect ~12-15 extra cycles for the SG instruction and security state transition.

3. **DMA Attack Simulation**: Configure a DMA channel in the Non-Secure world to read from a Secure-only memory region. Check if the DMA controller returns zeros, stalls, or faults. Document the behavior for your specific SoC — it varies between vendors.

## Next Up

Tomorrow we dive into Secure Boot Concepts: Chain of Trust, Keys & Attestation. We'll trace the boot ROM through the first-stage bootloader, examine how hardware root-of-trust keys are fused, and implement a simple measured boot sequence that cryptographically chains each stage.
