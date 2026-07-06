---
title: "Day 24: ARM Cortex-M Security: SAU, IDAU & TrustZone-M"
date: 2026-07-06
tags: ["til", "trustzone", "trustzone-m", "sau", "idau"]
---

## What I Explored Today

Today I dug into the hardware-level memory partitioning that makes TrustZone-M tick on Cortex-M33, M23, M35P, and M55 cores. While the high-level concept of "secure world vs. non-secure world" is straightforward, the actual enforcement happens through two tightly coupled hardware units: the Security Attribution Unit (SAU) and the Implementation Defined Attribution Unit (IDAU). Understanding how these interact—and how to configure them correctly—is the difference between a working secure boot chain and a bricked device.

## The Core Concept

The SAU and IDAU form a two-stage memory access control system. Think of the IDAU as the hardware's "hardwired" security map—it's fixed at chip design time by the silicon vendor and defines which memory regions are always Secure, always Non-Secure, or configurable. The SAU is the programmable overlay that lets your firmware (running in Secure state) refine those regions at runtime.

Why two units? Because you need a root of trust that cannot be overridden by software. The IDAU provides that immutable baseline. Even if an attacker corrupts the SAU registers, the IDAU's hardwired regions remain enforced. The SAU can only further restrict access—it can never make an IDAU-marked Secure region accessible to Non-Secure code.

The actual security check works like this: every memory access on the bus is tagged with a security attribute (Secure or Non-Secure). The bus matrix compares this against the combined SAU+IDAU map. If a Non-Secure access hits a Secure region, the bus raises a fault. The CPU never sees the data—it's blocked at the hardware level.

## Key Commands / Configuration / Code

Here's a practical SAU configuration for a typical Cortex-M33 secure boot scenario. We'll configure the SAU to carve out a secure region for the boot ROM and a shared region for Non-Secure callable (NSC) functions.

```c
// sau_config.h - SAU setup for Cortex-M33
#include "cmsis_compiler.h"

void SAU_Init(void) {
    // Step 1: Enable SAU and clear all regions
    SAU->CTRL = 0;                    // Disable SAU during configuration
    SAU->RNR  = 0;                    // Start at region 0
    SAU->RLAR = 0;                    // Clear all region limit registers
    
    // Step 2: Define Secure region for boot ROM (0x10000000 - 0x1001FFFF)
    SAU->RNR  = 0;                    // Region 0
    SAU->RBAR = 0x10000000U;          // Base address (must be aligned to region size)
    SAU->RLAR = (0x10020000U - 1) |   // Limit address (inclusive, must be aligned)
                (1U << 0);            // Bit 0: NSC=0 (Secure, not Non-Secure Callable)
    
    // Step 3: Define NSC region for gateway veneers (0x10020000 - 0x10020FFF)
    SAU->RNR  = 1;                    // Region 1
    SAU->RBAR = 0x10020000U;
    SAU->RLAR = (0x10021000U - 1) | 
                (1U << 0) |           // NSC=1 (Non-Secure Callable)
                (1U << 1);            // Enable bit
    
    // Step 4: Define Non-Secure region for application (0x20000000 - 0x2001FFFF)
    SAU->RNR  = 2;                    // Region 2
    SAU->RBAR = 0x20000000U;
    SAU->RLAR = (0x20020000U - 1) | 
                (0U << 0) |           // NSC=0
                (1U << 1);            // Enable bit
    
    // Step 5: Enable SAU
    SAU->CTRL = SAU_CTRL_ENABLE_Msk;  // Enable SAU with default Non-Secure
}
```

To verify the configuration at runtime, read back the SAU registers:

```bash
# GDB commands to inspect SAU state on a Cortex-M33 target
(gdb) p/x *(uint32_t*)0xE000EDD0  # SAU_CTRL
(gdb) p/x *(uint32_t*)0xE000EDD4  # SAU_TYPE (number of regions)
(gdb) p/x *(uint32_t*)0xE000EDD8  # SAU_RNR
(gdb) p/x *(uint32_t*)0xE000EDDC  # SAU_RBAR
(gdb) p/x *(uint32_t*)0xE000EDE0  # SAU_RLAR
```

The IDAU is typically read-only from software. On NXP LPC55xx parts, you can query the IDAU configuration via a vendor-specific register:

```c
// NXP LPC55xx IDAU status register (example)
uint32_t idau_cfg = *(volatile uint32_t*)0x400A4000;
// Bits [3:0] indicate number of IDAU regions implemented
```

## Common Pitfalls & Gotchas

**1. SAU region alignment is brutal.** The SAU requires that region base and limit addresses are aligned to the region size. If you try to define a 4KB region starting at 0x10001000, the SAU will silently misbehave. Always use `(size - 1)` as the limit and ensure the base is a multiple of the size. I've spent hours debugging a "non-functional" SAU that was actually working—just misaligned.

**2. NSC regions must contain only function entry points.** The Non-Secure Callable region is not a general-purpose shared memory. Every byte in an NSC region is treated as a potential gateway. If you put data there, the CPU will attempt to execute it as code when a Non-Secure function call targets that address. Always place only your veneer table (SG instructions) in NSC regions.

**3. The IDAU can override your SAU silently.** If the silicon vendor marked a memory region as "always Secure" in the IDAU, your SAU configuration cannot make it Non-Secure. This is by design, but it means you must consult the chip reference manual's IDAU map before designing your memory layout. On some MCUs, the first 32KB of flash is hardwired Secure—your bootloader must live there.

## Try It Yourself

1. **SAU register dump exercise:** On your Cortex-M33 development board, write a small Secure firmware that reads and prints all SAU registers (CTRL, TYPE, RNR, RBAR, RLAR for each region). Compare the output against your linker script. Verify that the SAU_TYPE register matches the number of regions you configured.

2. **Fault injection test:** Configure an SAU region as Secure, then have Non-Secure code attempt to read from that address. Observe the SecureFault exception. Modify the SAU region to be Non-Secure Callable and verify that the same access now succeeds (but triggers a precise bus fault if you try to execute data).

3. **IDAU discovery:** Look up your MCU's reference manual for the IDAU memory map. Write a test that attempts to access an IDAU-marked "always Secure" region from Non-Secure state. Confirm that even with the SAU disabled, the access fails. This proves the IDAU's hardware enforcement.

## Next up

Tomorrow we'll move up the stack to **TF-M: Trusted Firmware-M Architecture & Secure Services**—the reference implementation that turns these SAU/IDAU primitives into a real secure OS with isolated partitions, secure storage, and cryptography services. We'll walk through the partition manager, the secure function call mechanism, and how TF-M abstracts the hardware details we covered today.
