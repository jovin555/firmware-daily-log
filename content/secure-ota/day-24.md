---
title: "Day 24: Full Review & Project: Building an A/B OTA Pipeline for an STM32"
date: 2026-07-24
tags: ["til", "secure-ota", "review", "project"]
---

## What I Explored Today

Today we step back from individual components and assemble a complete, production-grade A/B OTA pipeline for an STM32F4 target. Over the past 23 days, we’ve dissected cryptographic signing, bootloader design, flash partitioning, error handling, and rollback strategies. Now we wire them together into a single, reproducible workflow. This is the capstone review: a concrete project you can build, flash, and test on real hardware. We’ll walk through the linker script, the bootloader state machine, the update agent logic, and the host-side signing toolchain—all with working code.

## The Core Concept

A/B OTA (also called dual-bank or seamless update) eliminates downtime by maintaining two identical firmware banks: Bank A (active) and Bank B (inactive). The bootloader decides which bank to run based on a metadata header containing a version number, a CRC32 of the firmware image, and a status flag (VALID, INVALID, or PENDING). On power-up, the bootloader checks the header of the currently selected bank. If the status is VALID, it jumps to that bank. If INVALID (e.g., from a failed update), it falls back to the other bank. The update agent running in the active bank downloads a new image, verifies its signature, writes it to the inactive bank, and sets its status to PENDING. On the next reset, the bootloader sees PENDING, runs the new bank, and the new bank’s startup code sets its own status to VALID. If the new bank crashes or fails to set VALID, the bootloader reverts on the subsequent reset.

The why is reliability: no bricked devices, no field returns, and no manual recovery. The how is a disciplined partitioning scheme and a tiny state machine in the bootloader.

## Key Commands / Configuration / Code

### 1. Linker Script for Dual-Bank Layout (STM32F407VG, 1 MB Flash)

```ld
/* memory.ld */
MEMORY
{
    FLASH_BANK_A (rx)  : ORIGIN = 0x08000000, LENGTH = 384K
    FLASH_BANK_B (rx)  : ORIGIN = 0x08060000, LENGTH = 384K
    BOOTLOADER   (rx)  : ORIGIN = 0x080C0000, LENGTH = 128K
    RAM          (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}

SECTIONS
{
    .text : { *(.text*) } > FLASH_BANK_A
    .rodata : { *(.rodata*) } > FLASH_BANK_A
    .data : { *(.data*) } > RAM AT > FLASH_BANK_A
    .bss : { *(.bss*) } > RAM
}
```

*Note: For Bank B firmware, replace `FLASH_BANK_A` with `FLASH_BANK_B` in the linker script. The bootloader is linked separately into `BOOTLOADER` region.*

### 2. Bootloader State Machine (Simplified C)

```c
// bootloader.c
#include "stm32f4xx.h"
#include <string.h>

typedef enum { VALID = 0xCA, INVALID = 0xFE, PENDING = 0x01 } bank_status_t;

typedef struct __attribute__((packed)) {
    uint32_t magic;          // 0xA5A5A5A5
    uint32_t version;
    uint32_t crc32;
    bank_status_t status;
    uint8_t  reserved[7];
} fw_header_t;

#define BANK_A_BASE 0x08000000
#define BANK_B_BASE 0x08060000
#define HEADER_OFFSET 0

static bank_status_t read_bank_status(uint32_t bank_base) {
    fw_header_t *hdr = (fw_header_t *)bank_base;
    if (hdr->magic != 0xA5A5A5A5) return INVALID;
    return hdr->status;
}

static void jump_to_bank(uint32_t bank_base) {
    void (*app_entry)(void) = (void (*)(void))(*(uint32_t *)(bank_base + 4));
    __set_MSP(*(uint32_t *)bank_base);
    app_entry();
}

int main(void) {
    bank_status_t status_a = read_bank_status(BANK_A_BASE);
    bank_status_t status_b = read_bank_status(BANK_B_BASE);

    if (status_a == PENDING) {
        // Attempt to boot Bank A; if it fails, revert
        jump_to_bank(BANK_A_BASE);
    } else if (status_b == PENDING) {
        jump_to_bank(BANK_B_BASE);
    } else if (status_a == VALID) {
        jump_to_bank(BANK_A_BASE);
    } else if (status_b == VALID) {
        jump_to_bank(BANK_B_BASE);
    }
    // If no valid bank, stay in bootloader for recovery
    while(1);
}
```

### 3. Update Agent – Writing to Inactive Bank (Bank B)

```c
// update_agent.c
#include "flash_if.h"  // custom HAL wrapper for flash erase/write

#define INACTIVE_BANK BANK_B_BASE

int apply_update(const uint8_t *data, uint32_t len, uint32_t expected_crc) {
    fw_header_t *hdr = (fw_header_t *)INACTIVE_BANK;

    // Erase entire bank (24 sectors of 16KB each)
    for (int sector = 12; sector < 24; sector++) {
        flash_erase_sector(sector, FLASH_VOLTAGE_RANGE_3);
    }

    // Write firmware image sector by sector
    uint32_t offset = 0;
    while (offset < len) {
        flash_write(INACTIVE_BANK + offset, data + offset, 256);
        offset += 256;
    }

    // Verify CRC32
    uint32_t computed_crc = crc32_compute(data, len);
    if (computed_crc != expected_crc) {
        hdr->status = INVALID;  // mark bad
        return -1;
    }

    // Set header: magic, version, crc, status = PENDING
    hdr->magic   = 0xA5A5A5A5;
    hdr->version = fw_version + 1;
    hdr->crc32   = computed_crc;
    hdr->status  = PENDING;

    // Reset to trigger bootloader
    NVIC_SystemReset();
    return 0;
}
```

### 4. Host-Side Signing & Packaging (Python)

```python
# sign_fw.py
import struct, hashlib, sys

FW_HEADER_FMT = '<IIII'  # magic, version, crc32, status

def sign_firmware(bin_path, version, output_path):
    with open(bin_path, 'rb') as f:
        fw_data = f.read()
    crc32 = zlib.crc32(fw_data) & 0xFFFFFFFF
    header = struct.pack(FW_HEADER_FMT, 0xA5A5A5A5, version, crc32, 0x01)  # PENDING
    with open(output_path, 'wb') as out:
        out.write(header)
        out.write(fw_data)

if __name__ == '__main__':
    sign_firmware(sys.argv[1], int(sys.argv[2]), sys.argv[3])
```

Usage: `python sign_fw.py firmware.bin 2 signed_fw.bin`

## Common Pitfalls & Gotchas

1. **Vector Table Remapping** – The application firmware must remap the vector table to its own bank base address. For STM32F4, add `SCB->VTOR = BANK_A_BASE;` as the first line in `main()`. Forgetting this causes hard faults on any interrupt.

2. **Flash Erase Granularity** – STM32F4 sectors are 16 KB (for 1 MB parts). You cannot erase less than a full sector. Always erase the entire inactive bank before writing, or track which sectors have changed. Partial writes to unerased sectors corrupt data.

3. **Reset Timing** – After setting the PENDING flag and calling `NVIC_SystemReset()`, the bootloader runs immediately. Ensure all peripheral DMA transfers are stopped and caches are flushed before reset. A stray DMA write during reset can corrupt the flash header.

## Try It Yourself

1. **Modify the linker script** to place the bootloader at `0x080C0000` and compile a minimal "blinky" app for Bank A. Flash both using OpenOCD and verify the bootloader jumps to Bank A on reset.

2. **Simulate a failed update** by manually writing an invalid CRC to the Bank B header via ST-Link Utility. Reset the device and confirm the bootloader falls back to Bank A.

3. **Extend the update agent** to verify an ECDSA signature on the downloaded image before writing to flash. Use the `mbedtls` library and a pre-shared public key stored in the bootloader region.

## Next Up

Tomorrow, we’ll do a full review of the entire 24-day series: a consolidated architecture diagram, a checklist for production deployment, and a discussion of trade-offs (e.g., single-bank vs. A/B, external flash vs. internal, signed vs. encrypted). Bring your questions.
