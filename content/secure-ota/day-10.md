---
title: "Day 10: Boot Confirmation & Health Checks: Marking an Update 'Good'"
date: 2026-07-10
tags: ["til", "secure-ota", "boot-confirmation", "health-check"]
---

## What I Explored Today

Today I dug into the critical handshake between the bootloader and the newly updated application: boot confirmation. Without a mechanism to explicitly mark an update as "good," a device that boots successfully once but crashes on the second boot will keep rolling back incorrectly—or worse, never roll back at all. I implemented a two-phase health check system that uses a monotonic boot counter and application-level health signals to decide when an update is truly stable.

## The Core Concept

The fundamental problem is simple: a device can boot successfully into a new firmware image, run for 30 seconds, then crash due to a latent bug. If the bootloader only checks that the image *started* (e.g., a single boot flag), it will consider the update successful and never attempt recovery. The device is now bricked until manual intervention.

The solution is a **boot confirmation protocol** with two distinct phases:

1. **Trial Boot Phase**: The bootloader boots the new image but marks it as "pending confirmation." The application is responsible for running a self-test and, if it passes, writing a confirmation flag to persistent storage (e.g., a dedicated partition in flash or a retained register in RTC backup memory).

2. **Health Check Phase**: On every subsequent boot, the application increments a monotonic boot counter and checks that critical subsystems (watchdog, filesystem, network stack) are functional. Only after a configurable number of successful boots (e.g., 3) does the application mark the update as permanently "good."

This prevents a single successful boot from locking in a bad update. It also handles the edge case where a device boots, confirms, then crashes on the next boot due to a non-deterministic fault—the boot counter won't increment, and the bootloader can detect the stall.

## Key Commands / Configuration / Code

I'm using a Zephyr-based system with MCUboot as the bootloader. The confirmation logic lives in the application, not the bootloader. Here's the core implementation:

```c
// include/ota_health.h
#define BOOT_CONFIRMATION_MAGIC  0xDEADBEEF
#define HEALTH_CHECK_THRESHOLD   3   // Number of clean boots to confirm

typedef struct {
    uint32_t magic;
    uint32_t boot_count;
    uint32_t health_flags;   // Bitmask: bit0=watchdog, bit1=fs, bit2=net
    uint32_t crc32;
} __attribute__((packed)) ota_health_t;
```

```c
// src/ota_health.c
#include <zephyr/storage/flash_map.h>
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(ota_health, LOG_LEVEL_INF);

static ota_health_t health_data;
static const off_t health_offset = DT_REG_ADDR(DT_NODELABEL(storage_partition));

// Write health data to the dedicated storage partition
static int write_health_data(void) {
    health_data.crc32 = crc32_le(0, (uint8_t*)&health_data,
                                 sizeof(health_data) - sizeof(uint32_t));
    int ret = flash_area_write(health_area, health_offset,
                               &health_data, sizeof(health_data));
    if (ret) {
        LOG_ERR("Failed to write health data: %d", ret);
    }
    return ret;
}

// Called once per boot after critical subsystems initialize
int ota_health_check(void) {
    // 1. Read current health data from flash
    int ret = flash_area_read(health_area, health_offset,
                              &health_data, sizeof(health_data));
    if (ret || health_data.magic != BOOT_CONFIRMATION_MAGIC) {
        // First boot or corrupted data — initialize
        memset(&health_data, 0, sizeof(health_data));
        health_data.magic = BOOT_CONFIRMATION_MAGIC;
        health_data.boot_count = 1;
        LOG_INF("Health data initialized, boot count = 1");
        return write_health_data();
    }

    // 2. Validate CRC to detect flash corruption
    uint32_t stored_crc = health_data.crc32;
    health_data.crc32 = 0;
    uint32_t calc_crc = crc32_le(0, (uint8_t*)&health_data, sizeof(health_data));
    if (calc_crc != stored_crc) {
        LOG_ERR("Health data CRC mismatch — resetting");
        memset(&health_data, 0, sizeof(health_data));
        health_data.magic = BOOT_CONFIRMATION_MAGIC;
        health_data.boot_count = 1;
        return write_health_data();
    }

    // 3. Increment boot counter
    health_data.boot_count++;

    // 4. Run subsystem health checks (simplified)
    health_data.health_flags = 0;
    if (watchdog_is_running()) health_data.health_flags |= BIT(0);
    if (fs_is_mounted())      health_data.health_flags |= BIT(1);
    if (net_is_connected())   health_data.health_flags |= BIT(2);

    // 5. If we've hit the threshold and all health checks pass, confirm the update
    if (health_data.boot_count >= HEALTH_CHECK_THRESHOLD &&
        health_data.health_flags == 0x07) {
        LOG_INF("Update confirmed good after %d clean boots", health_data.boot_count);
        ret = boot_write_img_confirmed();  // MCUboot API — marks image permanent
        if (ret) {
            LOG_ERR("Failed to confirm image: %d", ret);
        }
        // Reset boot counter to avoid re-confirming on every boot
        health_data.boot_count = 0;
    }

    return write_health_data();
}
```

The bootloader side (MCUboot) is configured to boot the new image once, then revert to the old image if the application doesn't call `boot_write_img_confirmed()` within a timeout:

```c
// prj.conf (application)
CONFIG_MCUBOOT=y
CONFIG_BOOTLOADER_MCUBOOT=y
CONFIG_IMG_MANAGER=y
CONFIG_BOOT_UPGRADE_ONLY=y       // Don't auto-confirm on boot
```

## Common Pitfalls & Gotchas

1. **Flash wear on the health partition**: Writing health data on every boot (especially during development) can wear out the flash sector. Mitigate by using a RAM cache and only writing when the boot count changes, or use a dedicated small partition with wear-leveling. I also added a CRC check to detect partial writes from power loss.

2. **Confirmation before health checks complete**: A common mistake is calling `boot_write_img_confirmed()` immediately after boot, before running any self-tests. This defeats the entire purpose of the trial boot phase. Always defer confirmation until after the health check threshold is met.

3. **The "infinite boot loop" trap**: If the health check itself crashes (e.g., a bug in the health check code), the device will keep rebooting and never increment the boot counter. I handle this by using a hardware watchdog that resets the health data if the device fails to reach the health check function within a timeout. This prevents the device from being stuck in a boot loop.

## Try It Yourself

1. **Implement a trial boot counter**: Modify the code above to store the boot count in a retained register (e.g., RTC backup register on STM32) instead of flash. Compare the performance and wear characteristics.

2. **Add a health check for your specific hardware**: Extend the `health_flags` bitmask to include a check for an external sensor or peripheral that must be responsive. For example, check that an I2C temperature sensor returns valid data before confirming the update.

3. **Simulate a crash after confirmation**: Write a test firmware that calls `boot_write_img_confirmed()` immediately, then deliberately crashes after 5 seconds. Observe that the bootloader does *not* roll back because the image was marked permanent. Then modify the code to require 3 clean boots before confirmation and repeat the test.

## Next Up

Tomorrow, I'll tackle **Automatic Rollback on Boot Failure & Watchdog-Triggered Recovery** — how to detect a bricked update without human intervention and use the watchdog as a safety net to force a rollback when the application fails to boot or crashes repeatedly.
