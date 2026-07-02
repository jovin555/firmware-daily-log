---
title: "Day 02: A/B (Dual-Slot) Partitioning: Design & Tradeoffs"
date: 2026-07-02
tags: ["til", "secure-ota", "ab-update", "partitioning"]
---

## What I Explored Today

Today I dove deep into A/B (dual-slot) partitioning—the gold standard for fault-tolerant OTA updates in embedded systems. I studied how this design eliminates the "bricked device" problem by maintaining two complete, independent firmware images (slot A and slot B), and I implemented a minimal bootloader state machine to manage slot selection. The key takeaway: A/B partitioning trades flash storage for reliability, and the engineering challenge lies in managing the state transitions correctly.

## The Core Concept

Why dual slots? Because single-slot updates are inherently risky. If power fails mid-write, or the new image is corrupted, the device has no fallback. A/B partitioning solves this by keeping the *known-good* image in one slot while writing the update to the other. The bootloader then selects the active slot based on a persistent state variable.

The design pattern is straightforward:
- **Slot A**: Active (running) image
- **Slot B**: Inactive (update target)
- **Bootloader**: Reads a metadata structure (stored in a dedicated partition or at a fixed offset) to decide which slot to boot.

The critical state machine has four states:
1. **`SLOT_A_ACTIVE`** — Boot from A, update target is B
2. **`SLOT_B_ACTIVE`** — Boot from B, update target is A
3. **`SLOT_A_UPDATE_PENDING`** — Written to B, but not yet verified
4. **`SLOT_B_UPDATE_PENDING`** — Written to A, but not yet verified

The bootloader *must* verify the pending slot before marking it active. If verification fails, it falls back to the known-good slot. This is where most engineers get it wrong—they skip the verification step or don't handle the "update pending" state correctly.

## Key Commands / Configuration / Code

Here's a minimal bootloader state machine in C, assuming a system with two 1MB flash slots and a 64-byte metadata partition at offset 0x1FC000 (end of flash).

```c
#include <stdint.h>
#include <stdbool.h>

// Flash geometry (example: STM32H7 with 2MB flash)
#define SLOT_A_START  0x08000000
#define SLOT_A_SIZE   0x00100000  // 1MB
#define SLOT_B_START  0x08100000
#define SLOT_B_SIZE   0x00100000
#define META_OFFSET   0x081FC000  // 128KB before end of flash

// Metadata structure (must be 64 bytes for flash alignment)
typedef struct __attribute__((packed)) {
    uint32_t magic;          // 0xDEADBEEF
    uint32_t version;        // monotonic counter
    uint32_t active_slot;    // 0 = A, 1 = B
    uint32_t update_pending; // 0 = none, 1 = slot A pending, 2 = slot B pending
    uint32_t boot_attempts;  // incremented each boot
    uint32_t crc32;          // CRC of this struct (excluding crc32 field)
    uint8_t  reserved[40];   // future use
} slot_metadata_t;

// Bootloader entry point
void bootloader_main(void) {
    slot_metadata_t meta;
    bool slot_a_valid, slot_b_valid;
    
    // 1. Read metadata from flash
    flash_read(META_OFFSET, &meta, sizeof(meta));
    
    // 2. Validate CRC of metadata
    if (meta.magic != 0xDEADBEEF || !verify_crc(&meta)) {
        // Metadata corrupted — fall back to slot A
        meta.active_slot = 0;
        meta.update_pending = 0;
        flash_erase(META_OFFSET, sizeof(meta));
        flash_write(META_OFFSET, &meta, sizeof(meta));
    }
    
    // 3. Check if an update is pending
    if (meta.update_pending != 0) {
        uint32_t pending_slot = (meta.update_pending == 1) ? SLOT_A_START : SLOT_B_START;
        
        // Verify the pending image's integrity (e.g., SHA-256 hash stored in image header)
        if (verify_image_integrity(pending_slot)) {
            // Mark the pending slot as active
            meta.active_slot = (meta.update_pending == 1) ? 0 : 1;
            meta.update_pending = 0;
            meta.boot_attempts = 0;
            flash_erase(META_OFFSET, sizeof(meta));
            flash_write(META_OFFSET, &meta, sizeof(meta));
        } else {
            // Image verification failed — clear pending flag, keep current slot
            meta.update_pending = 0;
            flash_erase(META_OFFSET, sizeof(meta));
            flash_write(META_OFFSET, &meta, sizeof(meta));
            // Fall through to boot current active slot
        }
    }
    
    // 4. Boot the active slot
    uint32_t boot_addr = (meta.active_slot == 0) ? SLOT_A_START : SLOT_B_START;
    jump_to_image(boot_addr);
}
```

**Configuration example** (for MCUboot, a popular open-source bootloader):

```yaml
# mcuboot.conf — dual-slot configuration for Zephyr
CONFIG_BOOTLOADER_MCUBOOT=y
CONFIG_MCUBOOT_IMAGE_SIZE=0x100000
CONFIG_MCUBOOT_SLOT_SIZE=0x100000
CONFIG_MCUBOOT_SCRATCH_SIZE=0x20000
CONFIG_MCUBOOT_SWAP_USING_MOVE=y  # Use move-based swap (safer than scratch)
CONFIG_MCUBOOT_VALIDATE_SLOT0=y   # Always validate active slot on boot
CONFIG_MCUBOOT_UPGRADE_ONLY=y     # Don't allow downgrade
```

## Common Pitfalls & Gotchas

1. **Forgetting to handle the "update pending" state on power loss.** If power fails after writing the image but before the metadata is updated, the bootloader must detect this and either retry the verification or fall back. I've seen devices bricked because the bootloader assumed metadata was always consistent. Always check: is the image in the target slot complete and valid, even if the metadata says "no pending update"?

2. **Not accounting for flash wear on the metadata partition.** Metadata gets written on every update cycle. If you're using NOR flash with 100K erase cycles, and you update daily, that's 36,500 cycles in a year—fine. But if you're using NAND with 10K cycles, you'll wear out the metadata block in months. Solution: use a log-structured metadata scheme or wear-leveling.

3. **Assuming slot sizes are equal.** In many MCUs, flash is organized in sectors of different sizes. Slot A might be 512KB, Slot B 1MB. Your bootloader must handle this gracefully. Always read the actual flash geometry from the hardware, don't hardcode sizes.

## Try It Yourself

1. **Implement a metadata CRC check in your bootloader.** Use a simple CRC-32 (e.g., `libscrc` or hardware CRC peripheral). Test what happens when you corrupt the metadata partition (e.g., write random data to it) and verify the bootloader falls back to a known-good slot.

2. **Add a "boot attempt counter" to your metadata.** Increment it on each boot. If the counter exceeds 3, mark the slot as bad and switch to the other slot. This catches images that boot but crash after the bootloader hands off control.

3. **Simulate a power failure during an update.** Write half of the new image to the inactive slot, then power cycle. Verify your bootloader detects the incomplete image (e.g., by checking the image header CRC or size field) and boots the old slot.

## Next Up

Tomorrow, I'll compare **Single-Slot vs Recovery-Partition Update Schemes**. We'll look at the "recovery mode" approach (used in many consumer routers) where a small, immutable recovery image lives in a protected partition, and the main application slot is updated in place. The tradeoff: you save flash space but lose the ability to roll back to a previous application version.
