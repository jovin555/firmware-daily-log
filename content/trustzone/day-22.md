---
title: "Day 22: ARM Security Architecture: TrustZone for Cortex-A & Cortex-M"
date: 2026-07-04
tags: ["til", "trustzone", "arm", "security"]
---

## What I Explored Today

Today I dug into the ARM TrustZone architecture across both Cortex-A (application) and Cortex-M (microcontroller) profiles. While TrustZone is often discussed as a single feature, the implementation differs significantly between these two families. On Cortex-A, TrustZone provides a full-blown virtualization of the core, memory, and peripherals into Secure and Non-Secure worlds. On Cortex-M, it’s a lighter-weight extension called TrustZone-M that partitions the system at the memory and interrupt level without the overhead of a full hypervisor. Understanding these differences is critical when designing a secure boot chain or isolating trusted execution environments.

## The Core Concept

TrustZone is not a software library or a cryptographic primitive — it’s a hardware-enforced isolation mechanism baked into the ARM architecture. The core idea is simple: the processor can operate in one of two worlds at any time — Secure World or Non-Secure World. The hardware prevents Non-Secure code from accessing Secure resources, even if it runs at the highest privilege level (EL3 on Cortex-A, or privileged mode on Cortex-M).

Why does this matter for secure boot? Because the boot ROM and initial bootloader can execute entirely in Secure World, setting up the chain of trust before handing off to the OS in Non-Secure World. The OS never sees the Secure World’s memory, keys, or cryptographic operations. This is the foundation for measured boot, trusted execution environments (TEEs), and DRM.

On Cortex-A, TrustZone is implemented via:
- **Monitor mode** (EL3) — the gatekeeper that switches between worlds.
- **NS bit** in the Secure Configuration Register (SCR) — controls world state.
- **TZASC** (TrustZone Address Space Controller) — partitions DRAM into secure/non-secure regions.
- **TZPC** (TrustZone Protection Controller) — controls peripheral access.

On Cortex-M, TrustZone-M uses:
- **SAU** (Security Attribution Unit) — defines secure/non-secure memory regions.
- **IDAU** (Implementation Defined Attribution Unit) — hardwired by the chip vendor.
- **Secure and Non-Secure stacks** — separate stack pointers for each world.
- **SG (Secure Gateway) instructions** — entry points for calling secure functions from non-secure code.

## Key Commands / Configuration / Code

### Cortex-A: Switching to Secure Monitor Mode (ARMv8-A)

```asm
// Enter EL3 (Secure Monitor) from EL1 (Non-Secure OS)
// Assumes you're already in EL1 Non-Secure
SMC #0          // Secure Monitor Call — traps to EL3

// In EL3 handler, check the SCR.NS bit
MRS x0, SCR_EL3 // Read Secure Configuration Register
AND x0, x0, #1  // Check NS bit (bit 0)
// If NS==1, we came from Non-Secure world
// If NS==0, we came from Secure world
```

### Cortex-A: Configuring TZASC for DRAM Partitioning

```c
// Example for ARM CoreLink TZC-400 (TrustZone Address Space Controller)
// Partition DRAM: lower 256MB secure, rest non-secure

#define TZC_BASE 0x2A4A0000
#define REGION_ATTRIBUTES_SECURE 0xF // Secure read/write, no non-secure access

void tzc_init(void) {
    // Disable all regions first
    *(volatile uint32_t*)(TZC_BASE + 0x000) = 0; // TZC_REGION_ACCESS_CTRL
    
    // Region 0: 0x80000000 - 0x8FFFFFFF (256MB) Secure only
    *(volatile uint32_t*)(TZC_BASE + 0x100) = 0x80000000; // Region base address
    *(volatile uint32_t*)(TZC_BASE + 0x104) = 0x8FFFFFFF; // Region top address
    *(volatile uint32_t*)(TZC_BASE + 0x108) = REGION_ATTRIBUTES_SECURE; // Attributes
    
    // Enable filtering
    *(volatile uint32_t*)(TZC_BASE + 0x000) = 1; // Enable region 0
}
```

### Cortex-M: SAU Configuration (ARMv8-M)

```c
// Configure SAU to mark 0x10000000-0x1000FFFF as Secure
// All other memory defaults to Non-Secure

void sau_init(void) {
    // Disable SAU during configuration
    SAU->CTRL = 0;
    
    // Region 0: Secure region for trusted firmware
    SAU->RNR  = 0;          // Select region 0
    SAU->RBAR = 0x10000000; // Base address
    SAU->RLAR = (0x1000FFFF & ~0x1F) | 1; // Limit address + enable bit (bit 0)
    
    // Enable SAU
    SAU->CTRL = 1;
    
    // Set NS flag for current stack pointer (if needed)
    __set_CONTROL(__get_CONTROL() & ~(1 << 1)); // Ensure non-secure stack
}
```

### Calling a Secure Function from Non-Secure World (Cortex-M)

```c
// Non-secure caller
// The secure function must be at a Secure Gateway (SG) entry point
typedef int (*secure_func_t)(int arg) __attribute__((cmse_nonsecure_call));

int main(void) {
    // Address of secure entry point (must be in secure memory)
    secure_func_t secure_add = (secure_func_t)0x10000000;
    
    // This triggers a transition to Secure World via SG instruction
    int result = secure_add(42);
    
    return result;
}
```

## Common Pitfalls & Gotchas

1. **Forgetting to configure the SAU before enabling interrupts on Cortex-M.** If the SAU is not set up, all memory defaults to Non-Secure. A secure interrupt handler that tries to access secure memory will fault. Always initialize the SAU in the very first boot code, before enabling any interrupts.

2. **Assuming TZASC regions are aligned to 4KB on Cortex-A.** The TZC-400 requires region base and top addresses to be aligned to the region size. A misaligned address will silently disable the region. Always check the TRM for alignment constraints — some implementations require 64KB or even 1MB alignment.

3. **Mixing up world transitions on Cortex-A vs Cortex-M.** On Cortex-A, you use the `SMC` instruction to trap to EL3. On Cortex-M, you use the `SG` instruction (or a function call to an SG entry point). Using `SMC` on Cortex-M will cause an undefined instruction exception. The calling conventions are completely different.

## Try It Yourself

1. **SAU region walk on Cortex-M:** Write a small bare-metal program for an ARMv8-M MCU (e.g., NXP LPC55S69) that configures two SAU regions — one for your secure code (0x10000000-0x10000FFF) and one for secure data (0x20000000-0x20000FFF). Verify that a non-secure access to these regions causes a SecureFault.

2. **TZASC partition on Cortex-A emulation:** Using QEMU with the `-machine virt` and `-cpu cortex-a72` flags, write a minimal EL3 monitor that partitions 512MB of DRAM into a 64MB secure region at the top. Use `SMC` calls from a non-secure EL1 payload to test access.

3. **Secure function call round-trip:** On a Cortex-M board, implement a secure function that increments a counter in secure SRAM. Call it from non-secure code 100 times, then try to read the counter directly from non-secure code (it should fail). Measure the overhead of each world switch using a GPIO toggle.

## Next Up

Tomorrow we dive into **Secure Boot Concepts: Chain of Trust, Keys & Attestation** — how the hardware we configured today is used to cryptographically verify each stage of boot, from ROM to the OS, and how attestation proves the system state to a remote verifier.
