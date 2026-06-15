---
title: "Day 03: ARM Cortex-M Security: SAU, IDAU & TrustZone-M"
date: 2026-06-15
tags: ["til", "trustzone", "trustzone-m", "sau", "idau"]
---

## What I Explored Today

Today I dug into the hardware-level memory partitioning that makes TrustZone-M tick on Cortex-M33, M23, M55, and M85 cores. While TrustZone-A (application processors) uses the MMU to split world memory, Cortex-M takes a different approach with two dedicated units: the Implementation Defined Attribution Unit (IDAU) and the Security Attribution Unit (SAU). Understanding how these two units interact—and how to configure the SAU registers—is the difference between a secure system and one that silently leaks secrets through misattributed memory regions.

## The Core Concept

The fundamental question TrustZone-M answers is: "Is this memory address Non-Secure, Secure, or something else?" Every single transaction on the system bus carries a security attribute bit. The IDAU and SAU work together to set that bit for every address before the transaction reaches the bus.

Think of the IDAU as the hardware designer's permanent, immutable map. It's baked into the silicon—you cannot change it at runtime. The IDAU defines fixed regions like "internal flash is always Secure" or "external RAM is always Non-Secure." This is the foundation.

The SAU is your runtime configurable overlay. You can program up to 8 (or 16 on some implementations) SAU regions to override the IDAU's attribution. This is where you, the firmware engineer, define your actual security policy: "Region 0: Secure code at 0x10000000, size 0x40000" or "Region 1: Non-Secure Callable veneers at 0x10040000."

The critical insight: the SAU can only *narrow* the IDAU's Secure regions. If the IDAU says a region is Non-Secure, the SAU cannot make it Secure. This prevents a software bug from accidentally expanding Secure memory into hardware-defined Non-Secure space. The SAU can, however, carve out Non-Secure islands within a Secure region (for sharing data with the Non-Secure world) or mark specific addresses as Non-Secure Callable (NSC) for secure function entry points.

## Key Commands / Configuration / Code

The SAU is controlled through memory-mapped system registers. Here's the canonical initialization sequence for a Cortex-M33:

```c
// sau_init.c — Configure SAU for a TrustZone-M system
// Assumes: System clock running, privileged access level

#define SAU_BASE        0xE000EDD0UL
#define SAU_CTRL        (*(volatile uint32_t *)(SAU_BASE + 0x00))
#define SAU_TYPE        (*(volatile uint32_t *)(SAU_BASE + 0x04))
#define SAU_RNR         (*(volatile uint32_t *)(SAU_BASE + 0x08))
#define SAU_RBAR        (*(volatile uint32_t *)(SAU_BASE + 0x0C))
#define SAU_RLAR        (*(volatile uint32_t *)(SAU_BASE + 0x10))

// Region 0: Secure code (0x10000000 - 0x1003FFFF, 256KB)
// Region 1: NSC veneers (0x10040000 - 0x10040FFF, 4KB)
// Region 2: Non-Secure data (0x20000000 - 0x2001FFFF, 128KB)

void SAU_Init(void) {
    // Step 1: Disable SAU during configuration
    SAU_CTRL = 0;                       // ALLNS=0, ENABLE=0

    // Step 2: Configure Region 0 — Secure code
    SAU_RNR = 0;                        // Select region 0
    SAU_RBAR = 0x10000000;              // Base address (must be aligned to size)
    SAU_RLAR = (0x1003FFFF & ~0x3F)     // Limit address (lower 6 bits ignored)
              | (1 << 0)                // ENABLE bit
              | (0 << 1);               // NSC=0 → Secure, not NSC

    // Step 3: Configure Region 1 — NSC veneers
    SAU_RNR = 1;
    SAU_RBAR = 0x10040000;
    SAU_RLAR = (0x10040FFF & ~0x3F)
              | (1 << 0)                // ENABLE
              | (1 << 1);               // NSC=1 → Non-Secure Callable

    // Step 4: Configure Region 2 — Non-Secure data
    SAU_RNR = 2;
    SAU_RBAR = 0x20000000;
    SAU_RLAR = (0x2001FFFF & ~0x3F)
              | (1 << 0)                // ENABLE
              | (0 << 1);               // NSC=0 → Secure (but IDAU may override)

    // Step 5: Enable SAU
    SAU_CTRL = (1 << 0);                // ENABLE=1, ALLNS=0
}
```

To verify your configuration at runtime, read back the SAU_TYPE register to see how many regions are available:

```c
uint32_t num_regions = ((SAU_TYPE >> 8) & 0xFF) + 1;
// Returns 8 for most Cortex-M33 implementations
```

The IDAU is not programmable, but you can check its attribution by reading the IDAU registers (implementation-specific, often at 0xE000EF00). On NXP i.MX RT600, for example, the IDAU maps the first 2MB of flash as Secure and the rest as Non-Secure.

## Common Pitfalls & Gotchas

**1. SAU region alignment is brutal.** The base address and limit address must be aligned to a multiple of 32 bytes (the granularity of the SAU). Worse, the region size must be a power of 2, and the base must be aligned to that size. Trying to define a 64KB region starting at 0x10010000 will silently fail—the hardware ignores the lower 6 bits of the limit address. Always check: `(base % size == 0)` and `(size & (size-1) == 0)`.

**2. NSC regions must be exactly 32-byte aligned and contain only branch instructions.** The Non-Secure Callable attribute marks entry points that the Non-Secure world can call into Secure code. If you put data or non-branch instructions in an NSC region, the hardware will fault. Each veneer must be a single `BXNS` or `BLXNS` instruction (4 bytes), and the entire region must be word-aligned. I've seen teams waste hours debugging SecureFaults because they placed a 2-byte `NOP` in an NSC region.

**3. The IDAU can override your SAU configuration silently.** If the IDAU marks a memory region as Non-Secure, the SAU cannot make it Secure. Your SAU region will appear to be configured correctly (the registers show the right values), but transactions will still carry the Non-Secure attribute. Always check the device reference manual's IDAU memory map before designing your SAU layout. On some devices, the first 16KB of SRAM is hardwired Secure for the boot ROM—don't try to reassign it.

## Try It Yourself

1. **Read and decode SAU_TYPE:** On your TrustZone-M development board (NXP i.MX RT600, STM32L5, or similar), write a small program that reads `SAU_TYPE` and prints the number of available regions. Then read `SAU_CTRL` to confirm the SAU is enabled or disabled after reset.

2. **Configure a misaligned region intentionally:** Try to configure SAU Region 0 with base=0x10000100 and limit=0x10010100. Read back `SAU_RBAR` and `SAU_RLAR` to see how the hardware truncated the addresses. Observe that the effective region is different from what you wrote.

3. **Trigger a SecureFault by crossing world boundaries:** Set up one SAU region for Secure code and another for Non-Secure data. Write a Secure function that attempts to read from the Non-Secure region without using the proper Non-Secure access attribute. Catch the SecureFault exception and dump the fault status register (SCB->CFSR) to see the INVEP or INVTRAN bit set.

## Next Up

Tomorrow, we move from hardware configuration to the software framework that makes TrustZone-M usable: TF-M (Trusted Firmware-M). We'll explore its architecture—the Secure Partition Manager, the isolation levels, and how it exposes secure services like cryptography and trusted storage to the Non-Secure world through the PSA API. Bring your SAU configuration; we're about to put it to work.
