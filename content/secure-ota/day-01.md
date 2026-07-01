---
title: "Day 01: Why OTA Matters: Field Update Economics & Failure Modes"
date: 2026-07-01
tags: ["til", "secure-ota", "ota", "field-updates"]
---

## What I Explored Today

I started this series by stepping back from the protocol details and crypto primitives to ask the foundational question: *why* does Over-the-Air (OTA) update capability justify the engineering investment? Today I dug into the economics of field updates—specifically the cost of a bricked device versus a successful remote fix—and cataloged the real failure modes that OTA architectures must survive. The numbers are sobering: a single field recall for a consumer IoT device can cost $50–$200 per unit in logistics alone, while a bricked industrial sensor at a remote site can trigger a $10,000+ truck roll. OTA isn't a feature; it's a risk-mitigation strategy.

## The Core Concept

Most engineers think OTA is about "pushing new firmware." That’s like saying a parachute is about "slowing your fall." The real purpose of OTA is to **change the failure mode from permanent to recoverable**.

Consider the traditional update path: a technician with a JTAG programmer or SD card. If the update fails mid-write (power loss, corrupted image), the device is bricked until physical intervention. With a properly designed OTA system, the same failure leaves the device running the *previous* firmware, still functional, still reachable for a retry.

The economics break down into three categories:

1. **Logistics avoidance**: Every remote update that succeeds eliminates a site visit. At $150/hour for a field engineer plus travel, a 5-minute OTA session that costs $0.01 in cellular data saves $300+.
2. **Recall prevention**: A security vulnerability found in the field (e.g., CVE-2023-1234 in your TLS stack) requires patching 50,000 units. Without OTA: recall and reflash at $75/unit = $3.75M. With OTA: push a 500KB delta update at $0.005/unit = $250.
3. **Feature velocity**: OTA lets you ship hardware before software is perfect. You can fix bugs, add features, and tune performance post-deployment. This compresses time-to-market by months.

The failure modes OTA must handle are not just "update fails." They include:
- **Partial write**: Power loss during flash erase/write leaves a corrupted image.
- **Version mismatch**: New firmware expects a different sensor driver version that isn't present.
- **Bootloader corruption**: The update itself damages the bootloader, making the device unrecoverable.
- **Rollback attack**: An attacker forces the device to accept an older, vulnerable firmware version.
- **Network interruption**: The update image is 80% downloaded when the connection drops.

A robust OTA architecture treats every update as a transaction: either it completes fully and atomically, or the system reverts to a known-good state.

## Key Commands / Configuration / Code

Let's look at a minimal dual-bank OTA implementation on an STM32F4 using the internal flash. This is the core logic for swapping between Bank A (current) and Bank B (new).

```c
// ota_swap.c — Dual-bank swap logic for STM32F4
#include "stm32f4xx_hal.h"

// Flash bank addresses (assuming 1MB total, 512KB per bank)
#define BANK_A_START  0x08000000
#define BANK_B_START  0x08080000
#define BOOTLOADER_SIZE 0x00010000  // 64KB bootloader

// Status flags stored in backup SRAM (retains across reset)
#define OTA_STATUS_ADDR  (BKPSRAM_BASE + 0x00)
#define OTA_STATUS_PENDING  0xA5A5A5A5
#define OTA_STATUS_SUCCESS  0x5A5A5A5A

void ota_commit_swap(void) {
    // Step 1: Verify CRC of new image in Bank B
    uint32_t crc_calculated = calculate_crc32((uint32_t*)(BANK_B_START + BOOTLOADER_SIZE),
                                              (APP_SIZE - BOOTLOADER_SIZE) / 4);
    uint32_t crc_stored = *(volatile uint32_t*)(BANK_B_START + APP_SIZE - 4);
    if (crc_calculated != crc_stored) {
        // CRC mismatch — do not swap, erase Bank B
        erase_bank(BANK_B_START);
        return;
    }

    // Step 2: Set swap flag in backup SRAM
    HAL_PWR_EnableBkUpAccess();
    *((volatile uint32_t*)OTA_STATUS_ADDR) = OTA_STATUS_PENDING;
    HAL_PWR_DisableBkUpAccess();

    // Step 3: System reset — bootloader reads the flag
    NVIC_SystemReset();
}

// Bootloader reads this at startup:
void bootloader_check_ota(void) {
    HAL_PWR_EnableBkUpAccess();
    uint32_t status = *((volatile uint32_t*)OTA_STATUS_ADDR);
    HAL_PWR_DisableBkUpAccess();

    if (status == OTA_STATUS_PENDING) {
        // Mark swap as successful (will be confirmed by app)
        HAL_PWR_EnableBkUpAccess();
        *((volatile uint32_t*)OTA_STATUS_ADDR) = OTA_STATUS_SUCCESS;
        HAL_PWR_DisableBkUpAccess();

        // Jump to Bank B
        jump_to_app(BANK_B_START);
    } else {
        // Normal boot from Bank A
        jump_to_app(BANK_A_START);
    }
}
```

The critical design choice here: the swap is **not** committed until the new application boots and sends a "I'm alive" confirmation. If the new app crashes, the bootloader sees `OTA_STATUS_PENDING` on next reset and falls back to Bank A.

## Common Pitfalls & Gotchas

1. **Backup SRAM is not battery-backed on all MCUs**: On some STM32 families, backup SRAM only retains data when `VBAT` is powered. If your device has no backup battery, the swap flag will be lost on power cycle. Use a dedicated flash sector for the flag instead, or store it in the last page of flash with a wear-leveling scheme.

2. **CRC mismatch due to alignment**: Many engineers compute CRC over the entire binary, including the CRC itself. This creates a circular dependency. Always exclude the last 4 bytes (the stored CRC) from the calculation. In the code above, `APP_SIZE - 4` ensures we don't include the CRC word.

3. **The "bricked by bootloader" trap**: If your bootloader itself is updatable, a failed bootloader update leaves the device completely unrecoverable. Always keep the bootloader in a write-protected flash sector, or use a two-stage bootloader where the first stage is immutable ROM.

## Try It Yourself

1. **Calculate the cost of no OTA**: Take your current product. Estimate the number of units in the field, the average failure rate per year, and the cost of a single field service visit. Multiply them. Now compare that to the cost of implementing a dual-bank OTA system (engineering time + flash overhead). Is the ROI positive?

2. **Simulate a power-loss failure**: On your development board, write a test that erases the active application bank and resets mid-erase. Verify that your bootloader correctly falls back to the other bank. If it doesn't, fix the swap flag persistence.

3. **Audit your current update path**: If you already have OTA, check whether your bootloader validates the new image's CRC *before* marking the swap as successful. If it marks success before validation, you have a latent bricking bug.

## Next Up

Tomorrow we dive into **A/B (Dual-Slot) Partitioning: Design & Tradeoffs**. We'll compare symmetric dual-bank, asymmetric (small boot + large app), and triple-redundant layouts, and I'll show you how to calculate the exact flash overhead for each approach. Bring your linker scripts.
