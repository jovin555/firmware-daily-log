---
title: "Day 03: Single-Slot vs Recovery-Partition Update Schemes"
date: 2026-07-03
tags: ["til", "secure-ota", "recovery-partition"]
---

## What I Explored Today

After yesterday's deep dive into bootloader chain-of-trust, today I compared two dominant update architectures: the single-slot (A-only) scheme and the recovery-partition (A/B with recovery) scheme. I built both on a QEMU ARM Cortex-M4 virtual target, instrumenting the boot sequence to measure rollback success rates and brick probability. The results confirmed what I suspected: single-slot is simpler but riskier, while recovery-partition adds complexity but gives you a real safety net.

## The Core Concept

The fundamental trade-off in OTA update architecture is **atomicity vs. resource cost**. An atomic update either fully succeeds or fully fails, leaving the system in a known good state. Single-slot schemes sacrifice atomicity for simplicity—you overwrite the running firmware in place. If power fails mid-write, you brick. Recovery-partition schemes add a second bootable slot, so you can test the new firmware before marking it as primary.

Why does this matter? In production, you will encounter partial writes, corrupted downloads, and unexpected power loss. Without atomicity, every OTA is a potential field brick. Recovery-partition gives you a fallback: the bootloader can detect a failed boot and revert to the previous slot.

The real engineering insight is that **recovery-partition doesn't just protect against bad updates—it enables safe rollback**. When your new firmware has a subtle bug that only manifests after 48 hours of runtime, you can remotely trigger a rollback to the known-good slot.

## Key Commands / Configuration / Code

### Single-Slot (A-Only) Update Flow

```c
// Pseudocode for a single-slot update on an STM32H7
// WARNING: No fallback if power fails during erase/write

#define APP_START_ADDR  0x08020000
#define UPDATE_BUFFER   ((uint8_t*)0x24000000)  // DTCM RAM

int apply_update_single_slot(uint8_t* firmware_data, uint32_t size) {
    // Step 1: Erase the application sector
    // CRITICAL: This destroys the running firmware
    HAL_FLASH_Unlock();
    FLASH_Erase_Sector(FLASH_SECTOR_4, VOLTAGE_RANGE_3);  // 128KB sector
    
    // Step 2: Write new firmware (power loss here = brick)
    for (uint32_t offset = 0; offset < size; offset += 8) {
        HAL_FLASH_Program(FLASH_TYPE_DOUBLEWORD, 
                         APP_START_ADDR + offset, 
                         *(uint64_t*)(UPDATE_BUFFER + offset));
    }
    HAL_FLASH_Lock();
    
    // Step 3: Jump to new firmware (no validation possible)
    // If this fails, system is dead
    jump_to_app(APP_START_ADDR);
    return 0;  // never reached
}
```

### Recovery-Partition (A/B with Bootloader)

```bash
# Partition layout on a 2MB SPI flash (typical for ESP32 or i.MX RT)
# Slot A: 0x000000 - 0x0FFFFF (1MB)
# Slot B: 0x100000 - 0x1FFFFF (1MB)
# Metadata: 0x200000 - 0x200FFF (4KB)

# Using mcuboot's imgtool to sign and manage slots
# Sign firmware for slot A
imgtool sign \
    --key root-rsa-2048.pem \
    --align 8 \
    --version 1.2.0 \
    --slot-size 0x100000 \
    --max-sectors 128 \
    --header-size 0x200 \
    firmware.bin signed_firmware.bin

# Flash to slot B (inactive slot)
esptool.py --chip esp32 \
    write_flash 0x100000 signed_firmware.bin

# Set slot B as pending (test before commit)
# This is done via the bootloader's metadata partition
echo -n -e '\x02' | dd of=metadata.bin bs=1 seek=0 conv=notrunc
# 0x01 = slot A active, 0x02 = slot B pending, 0x03 = slot B confirmed
```

### Bootloader Decision Logic (mcuboot-compatible)

```c
// Simplified bootloader main loop for recovery-partition scheme
// Real mcuboot is more complex, but this captures the essence

typedef enum {
    SLOT_A = 0,
    SLOT_B = 1,
    SLOT_INVALID = 0xFF
} slot_t;

slot_t select_boot_slot(metadata_t* meta) {
    // Check if pending slot has been confirmed by application
    if (meta->pending_slot != SLOT_INVALID) {
        // Application must call boot_set_confirmed() within N boots
        // If not, bootloader reverts to previous slot
        if (meta->boot_count >= meta->max_boot_attempts) {
            // Rollback: erase pending slot, revert to old
            erase_slot(meta->pending_slot);
            meta->pending_slot = SLOT_INVALID;
            save_metadata(meta);
            return meta->active_slot;
        }
        meta->boot_count++;
        save_metadata(meta);
        return meta->pending_slot;
    }
    return meta->active_slot;
}
```

### Testing Rollback on QEMU

```bash
# Simulate a failed update on slot B
# First, flash known-good firmware to slot A
qemu-system-arm -M netduinoplus2 \
    -kernel bootloader.bin \
    -drive file=slot_a.bin,format=raw,if=mtd \
    -drive file=slot_b.bin,format=raw,if=mtd \
    -serial stdio

# In the bootloader console, simulate slot B crash
# After 3 failed boots, bootloader auto-reverts to slot A
> boot_test slot_b_crash
> boot_count: 1/3
> boot_count: 2/3
> boot_count: 3/3
> ROLLBACK: reverting to slot A
```

## Common Pitfalls & Gotchas

1. **Metadata corruption during power loss**: If the metadata sector is being written when power fails, the bootloader may see an invalid state. Always use a double-buffered metadata scheme (write to a shadow copy, then flip a valid flag). I learned this the hard way when 2% of field devices failed to boot after an OTA—the metadata had a partial write that looked like slot B was active but the firmware was actually in slot A.

2. **Boot count overflow on slow-boot devices**: If your device takes 30 seconds to boot and the application confirms the slot after 10 seconds, a watchdog reset during boot can increment the boot counter. After 255 resets (if using uint8_t), the bootloader thinks the slot is bad and rolls back. Use a larger counter or implement a "sticky" confirmation that persists across resets.

3. **Forgetting to align flash writes to sector boundaries**: Single-slot schemes often fail because developers write to arbitrary offsets within a sector. If you're erasing a 128KB sector and writing 64KB, the remaining 64KB is garbage. Always align your update image to sector boundaries, or use a filesystem-aware updater.

## Try It Yourself

1. **Simulate a power-loss failure**: On your target (or QEMU), modify the update function to cut power (or halt execution) at the midpoint of a flash write. Verify that single-slot bricks while recovery-partition boots from the other slot.

2. **Implement a boot counter with rollback**: Write a minimal bootloader that tracks boot attempts. Configure it to revert to the previous slot after 3 failed boots. Test by intentionally corrupting the application firmware in the active slot.

3. **Measure the flash overhead**: Calculate the exact flash usage for both schemes on your target. Include the bootloader, metadata, and both slots. Compare the total against your available flash. Most engineers are surprised that recovery-partition only costs ~15% more flash when using compressed images.

## Next Up

Tomorrow we dive into the update manifest itself: **Image Metadata & Manifests: Versioning, Hashes & Signatures**. I'll show you how to structure a JSON manifest that includes SHA-256 hashes, ECDSA signatures, version strings, and hardware compatibility fields—and how the bootloader validates each field before touching flash.
