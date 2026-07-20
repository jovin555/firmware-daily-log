---
title: "Day 20: Bricking Prevention: Failsafe Bootloaders & Golden Images"
date: 2026-07-20
tags: ["til", "secure-ota", "failsafe", "golden-image"]
---

## What I Explored Today

Today I dug into the most critical safety net in any OTA system: preventing a device from becoming a permanent brick when an update goes wrong. After weeks of building signing pipelines and secure transport, I realized that even a perfectly delivered update can fail at apply time—power loss during flash, corrupted storage, or a bad bootloader patch. I spent the day implementing a dual-bank failsafe bootloader with a golden image recovery path, using real hardware (STM32H7) and production-grade patterns from the MCUboot project.

## The Core Concept

The fundamental insight is simple: **never trust that an update will succeed**. Every OTA system must assume the update can fail at any point—during download, during flash write, or during first boot. The failsafe bootloader solves this by maintaining two distinct software banks: a known-good "golden" image (Bank 0) and an update slot (Bank 1). On every boot, the bootloader checks a set of flags and image validity markers to decide which bank to execute.

The golden image is the factory-installed, immutable fallback. It should be minimal—just enough networking, crypto, and bootloader logic to recover the device. It never gets overwritten by OTA. The update slot is where new firmware lands. After a successful update, the bootloader marks the new image as "confirmed" only after the application itself reports healthy operation (a concept called "image confirmation" or "anti-rollback").

If the new image fails to boot or doesn't confirm within a timeout, the bootloader automatically rolls back to the golden image. This is the failsafe mechanism: the device always has a way home.

## Key Commands / Configuration / Code

### 1. Bootloader State Machine (Pseudo-C code for MCUboot-style logic)

```c
// Bootloader main entry - runs before application
void bootloader_main(void) {
    // Read boot flags from backup registers (battery-backed SRAM)
    uint32_t boot_flags = READ_BACKUP_REG(BOOT_FLAG_ADDR);
    
    // Check if we're in recovery mode (e.g., forced by watchdog timeout)
    if (boot_flags & BOOT_FLAG_RECOVERY) {
        CLEAR_BACKUP_REG(BOOT_FLAG_ADDR);
        jump_to_golden_image();
        // never returns
    }
    
    // Validate golden image header (CRC + magic number)
    if (!validate_image_header(GOLDEN_IMAGE_BASE)) {
        // Golden image corrupted - this is catastrophic
        enter_dead_loop(); // or blink SOS on LED
    }
    
    // Check if update slot has a pending image
    if (is_update_slot_valid()) {
        // Verify update image signature (using stored public key)
        if (verify_image_signature(UPDATE_IMAGE_BASE)) {
            // Mark update as "pending" in flash metadata
            set_boot_metadata(BOOT_METADATA_PENDING);
            
            // Jump to update image
            jump_to_image(UPDATE_IMAGE_BASE);
        } else {
            // Signature invalid - erase update slot silently
            erase_update_slot();
        }
    }
    
    // Default: boot golden image
    jump_to_golden_image();
}
```

### 2. Application-Side Confirmation (Rust on embedded)

```rust
/// Called after application init succeeds (network up, sensors working)
fn confirm_successful_boot() -> Result<(), BootError> {
    // Write confirmation flag to a dedicated flash page
    // This tells the bootloader "this image is good, don't rollback"
    let mut flash = Flash::take().unwrap();
    
    // Use a specific flash page reserved for boot metadata
    let confirm_addr = 0x0800_F000; // Example address
    let confirm_pattern: u32 = 0xCAFEBABE; // Magic confirmation value
    
    // Erase and write in one operation (page-aligned)
    flash.erase_page(confirm_addr)?;
    flash.write_word(confirm_addr, confirm_pattern)?;
    
    // Also clear any pending rollback counters
    flash.write_word(confirm_addr + 4, 0x00000000)?;
    
    Ok(())
}

/// Called if application detects fatal error during init
fn request_rollback() -> Result<(), BootError> {
    // Write a "rollback requested" flag
    let mut flash = Flash::take().unwrap();
    flash.write_word(ROLLBACK_FLAG_ADDR, 0xDEADBEEF)?;
    
    // Force a watchdog reset
    // Bootloader will see the flag and jump to golden image
    SCB::sys_reset();
}
```

### 3. Linker Script for Dual-Bank Layout (GCC LD)

```ld
MEMORY
{
    /* Bank 0: Golden image (factory, never overwritten) */
    GOLDEN_FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 512K
    
    /* Bank 1: Update slot (OTA target) */
    UPDATE_FLASH (rx)  : ORIGIN = 0x08080000, LENGTH = 512K
    
    /* Boot metadata (flags, counters) - separate page */
    BOOT_META (rw)     : ORIGIN = 0x08100000, LENGTH = 16K
    
    /* RAM */
    RAM (rwx)          : ORIGIN = 0x20000000, LENGTH = 256K
}

SECTIONS
{
    .golden_text : {
        *(.golden_init)  /* First-stage bootloader code */
        *(.text)
    } > GOLDEN_FLASH
    
    .update_text : {
        *(.update_init)
        *(.text)
    } > UPDATE_FLASH
    
    .boot_metadata : {
        KEEP(*(.boot_flags))
        KEEP(*(.image_confirm))
    } > BOOT_META
}
```

## Common Pitfalls & Gotchas

1. **Watchdog timer misconfiguration**: The most common bricking scenario is a watchdog that fires *during* the golden image boot. If your golden image takes longer to initialize than the watchdog period, the device will reset in a loop. Always set the watchdog to its maximum timeout during bootloader execution, then let the application reconfigure it. I've seen teams spend weeks debugging "random" bricking that was just a 1-second watchdog.

2. **Flash wear on metadata pages**: Boot flags and confirmation markers are written to flash on every boot. If you use the same flash page, you'll hit the erase cycle limit (typically 10k-100k writes). Use a wear-leveling scheme: write to sequential offsets within a larger metadata region, or use battery-backed SRAM for frequently-changing flags. I use a ring buffer of 256 confirmation slots per page.

3. **Golden image is too large**: Engineers often try to make the golden image "full-featured" to avoid user complaints. This is dangerous—a larger golden image means more flash to validate, more boot time, and more surface area for bugs. Keep it under 256KB if possible. The golden image should only contain: bootloader logic, minimal crypto (public key only), network stack (TLS 1.3, no MQTT), and a recovery downloader. No application logic.

## Try It Yourself

1. **Implement a dual-bank bootloader on an STM32 or ESP32**: Set up two flash regions. Write a minimal golden image that blinks an LED and waits for a serial command. Write a test update image that prints "UPDATED". Verify that booting the update image works, then corrupt the update image's signature and confirm the bootloader falls back to golden.

2. **Add a confirmation timeout**: Modify your application to call `confirm_successful_boot()` only after 30 seconds of healthy operation. If the application crashes before that, the bootloader should automatically roll back. Use a hardware timer or RTC to implement the timeout.

3. **Test power-loss resilience**: While the bootloader is writing the update image to flash, pull the power. On next boot, verify that the bootloader detects the incomplete write (check CRC or magic number) and boots the golden image. Repeat 100 times to ensure no corruption.

## Next Up

Tomorrow: **Update Telemetry: Success/Failure Reporting Back to the Fleet** — how to build a reliable reporting channel that tells your backend exactly which devices updated successfully, which rolled back, and why, without overwhelming your MQTT broker or draining batteries.
