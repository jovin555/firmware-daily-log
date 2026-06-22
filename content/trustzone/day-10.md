---
title: "Day 10: MCUboot Rollback Protection & Anti-Rollback Counters"
date: 2026-06-22
tags: ["til", "trustzone", "rollback", "security"]
---

## What I Explored Today

Today I dug into MCUboot's anti-rollback mechanism — specifically how it uses monotonic counters to prevent an attacker from flashing a known-vulnerable older firmware version. I'd previously treated rollback protection as a "nice to have," but after tracing through the MCUboot source and testing with real hardware, I now see it as a mandatory security primitive. Without it, all other Secure Boot guarantees are worthless: an attacker can simply downgrade to a version with a known exploit.

## The Core Concept

Secure Boot ensures only signed firmware runs, but it doesn't care *which* signed firmware. If version 1.0 has a buffer overflow and version 2.0 fixes it, an attacker can flash 1.0 (it's still signed with the same key) and re-exploit the old vulnerability. Rollback protection closes this gap.

MCUboot implements this using an **anti-rollback counter** — a monotonic integer stored in a persistent, one-time-incrementable area (typically a dedicated flash partition or OTP fuses). The counter is embedded in the firmware image's metadata (the image trailer or TLV area). During the boot sequence, MCUboot compares the image's counter against the stored counter:

- If `image_counter >= stored_counter` → boot proceeds, and the stored counter is updated to match.
- If `image_counter < stored_counter` → boot is rejected as a rollback attempt.

The key insight: the counter can *only* increase. Even if you flash an older image, the hardware counter won't decrement. On MCUs with OTP (one-time programmable) fuses, this is physically enforced.

## Key Commands / Configuration / Code

### 1. Enabling Rollback Protection in MCUboot

In your `mcuboot_config.h` or via CMake:

```c
// Enable the anti-rollback feature
#define MCUBOOT_USE_ROLLBACK_PROTECTION 1

// Define the flash area for the security counter
// Typically a dedicated partition in the flash layout
#define MCUBOOT_ROLLBACK_COUNTER_AREA_ID FLASH_AREA_IMAGE_SECONDARY
```

### 2. Embedding the Counter in the Image

When building your firmware, you must include the counter in the image TLV. Using `imgtool`:

```bash
# Create a signed image with rollback counter version 5
imgtool sign \
    --key mykey.pem \
    --header-size 0x200 \
    --align 8 \
    --version 1.2.3 \
    --slot-size 0x80000 \
    --max-sectors 128 \
    --security-counter 5 \
    --pad-header \
    firmware.bin signed_firmware.bin
```

The `--security-counter` value is independent of the semantic version. You can increment it on every release, even for patch versions.

### 3. MCUboot Boot Logic (Simplified)

From `bootutil/bootutil.c` (v1.10+):

```c
int boot_check_rollback(struct boot_status *bs) {
    uint32_t stored_counter;
    uint32_t image_counter;

    // Read the persistent counter from the designated flash area
    boot_read_security_counter(&stored_counter);

    // Extract the counter from the image TLV
    image_counter = bs->security_counter;

    // The critical check
    if (image_counter < stored_counter) {
        // Rollback detected! Reject the image.
        BOOT_LOG_ERR("Rollback attempt: image=%u, stored=%u",
                     image_counter, stored_counter);
        return BOOT_EBADIMAGE;
    }

    // Update stored counter if image is newer
    if (image_counter > stored_counter) {
        boot_write_security_counter(image_counter);
    }

    return 0;
}
```

### 4. Hardware Counter (OTP Example on nRF5340)

For truly tamper-proof counters, use OTP fuses. On Nordic nRF53:

```c
// In your board-specific MCUboot port
#include <hal/nrf_ficr.h>

int boot_read_security_counter(uint32_t *counter) {
    // Read from OTP area (one-time programmable)
    *counter = NRF_FICR->SECURITY_COUNTER;
    return 0;
}

int boot_write_security_counter(uint32_t counter) {
    // OTP write is irreversible — only works if current < new
    nrf_ficr_security_counter_set(counter);
    return 0;
}
```

**Warning**: Writing to OTP is permanent. Test thoroughly in development with emulated flash counters first.

## Common Pitfalls & Gotchas

### 1. Counter Overflow
The counter is typically a 32-bit unsigned integer. If you increment by 1 per release, you have ~4 billion versions. But if you use a scheme like `(major << 16 | minor << 8 | patch)`, you can overflow quickly. I've seen teams hit this at version 256.0.0. **Always use a flat monotonic counter**, not a packed version number.

### 2. Forgetting to Increment the Counter
It's easy to rebuild a firmware with the same counter value. MCUboot will treat it as a valid upgrade (since `image_counter >= stored_counter`), but you lose the rollback protection for that specific version. **Automate counter increments in your CI/CD pipeline** — never rely on manual updates.

### 3. OTP Programming Failures
If your OTP write fails mid-operation (power loss, glitch), the counter may be corrupted. Some MCUs have hardware safeguards, but many don't. **Always verify the write** by reading back, and consider using a redundant counter scheme (two OTP slots, write to both, compare on boot).

## Try It Yourself

1. **Enable rollback protection in your MCUboot build**: Set `MCUBOOT_USE_ROLLBACK_PROTECTION=1` and configure a flash partition for the counter. Flash two images with different counters and verify that downgrading is blocked.

2. **Write a test that attempts a rollback**: Use `imgtool` to sign an image with `--security-counter 1`, flash it, then try to flash an image with `--security-counter 0`. Confirm MCUboot rejects it and logs the error.

3. **Implement a software fallback counter**: If your MCU lacks OTP, implement the counter in a dedicated flash page with wear-leveling. Write a small driver that reads/writes the counter and handles flash erase cycles.

## Next Up

Tomorrow, we move from MCUboot to the big leagues: **Trusted Firmware-A (TF-A): Architecture & Boot Stages**. We'll explore how TF-A implements the Arm Trusted Board Boot (TBB) specification, the BL1/BL2/BL31 boot flow, and how it integrates with Secure Boot and TrustZone on application-class processors.
