---
title: "Day 16: Flash & NVS: Non-Volatile Storage in Zephyr"
date: 2026-06-28
tags: ["til", "zephyr", "flash", "nvs"]
---

## What I Explored Today

Today I dug into Zephyr's Non-Volatile Storage (NVS) subsystem — a lightweight, flash-friendly key-value store designed for embedded systems. Unlike a full filesystem, NVS provides atomic writes, wear leveling, and crash recovery on raw flash partitions. I integrated it into a sensor logging application, storing calibration data and device configuration across reboots. The API is deceptively simple, but the underlying flash constraints (erase-before-write, sector alignment) demand careful attention.

## The Core Concept

Flash memory has a fundamental limitation: you can write to a page only after erasing it, and erases happen in large blocks (typically 4KB or more). NVS solves this by treating the flash partition as a circular log. Each write appends a new record (key + value + metadata) to the current write position. When the partition fills, NVS performs garbage collection: it reads valid records, writes them to a fresh area, then erases the old sector.

Why not just use a filesystem like FAT or LittleFS? For many embedded use cases, NVS is lighter (no directory structures, no fragmentation), faster for small writes, and inherently wear-leveled. It’s ideal for storing device parameters, network credentials, sensor calibration offsets, or boot counters — data that changes infrequently but must survive power loss.

Zephyr’s NVS implementation (`subsys/fs/nvs`) sits on top of the Flash Map API, which abstracts the physical flash layout. You define a partition in the devicetree, then open an NVS handle on it. The API provides `nvs_write()`, `nvs_read()`, and `nvs_delete()` — all operating on 32-bit keys and variable-length binary data.

## Key Commands / Configuration / Code

### 1. Devicetree Partition Definition

First, carve out a flash partition for NVS. In your board’s devicetree overlay (e.g., `boards/arm/nrf52840dk_nrf52840.overlay`):

```dts
/ {
    chosen {
        zephyr,flash = &flash0;
    };
};

&flash0 {
    partitions {
        compatible = "fixed-partitions";
        #address-cells = <1>;
        #size-cells = <1>;

        storage_partition: partition@0x7A000 {
            label = "storage";
            reg = <0x0007A000 0x00006000>;  /* 24KB at offset 0x7A000 */
        };
    };
};
```

This reserves 24KB starting at offset 0x7A000. Adjust the address and size based on your flash layout (check the SoC’s flash size and existing partitions).

### 2. Kconfig Configuration

Enable NVS in `prj.conf`:

```kconfig
CONFIG_NVS=y
CONFIG_FLASH=y
CONFIG_FLASH_MAP=y
CONFIG_FLASH_PAGE_LAYOUT=y
```

For debugging, add:
```kconfig
CONFIG_NVS_LOG_LEVEL_DBG=y
```

### 3. Application Code

Here’s a complete example that stores and retrieves a calibration structure:

```c
#include <zephyr/kernel.h>
#include <zephyr/fs/nvs.h>
#include <zephyr/storage/flash_map.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(nvs_demo, LOG_LEVEL_INF);

#define NVS_PARTITION      storage_partition
#define NVS_SECTOR_SIZE    4096  /* Match your flash erase size */

struct cal_data {
    float offset_x;
    float offset_y;
    uint32_t timestamp;
};

static struct nvs_fs fs;

void main(void)
{
    int rc;
    struct cal_data cal = { .offset_x = 1.5f, .offset_y = -2.3f, .timestamp = 1000 };

    /* Initialize NVS on the flash partition */
    fs.offset = FIXED_PARTITION_OFFSET(NVS_PARTITION);
    fs.sector_size = NVS_SECTOR_SIZE;
    fs.sector_count = FIXED_PARTITION_SIZE(NVS_PARTITION) / NVS_SECTOR_SIZE;

    rc = nvs_init(&fs, NVS_PARTITION);
    if (rc) {
        LOG_ERR("NVS init failed: %d", rc);
        return;
    }

    /* Write calibration data with key 0x01 */
    rc = nvs_write(&fs, 0x01, &cal, sizeof(cal));
    if (rc < 0) {
        LOG_ERR("Write failed: %d", rc);
    } else {
        LOG_INF("Wrote %d bytes", rc);
    }

    /* Read it back */
    struct cal_data read_cal;
    rc = nvs_read(&fs, 0x01, &read_cal, sizeof(read_cal));
    if (rc > 0) {
        LOG_INF("Read: offset_x=%.2f, offset_y=%.2f, ts=%u",
                read_cal.offset_x, read_cal.offset_y, read_cal.timestamp);
    } else if (rc == -ENOENT) {
        LOG_WRN("Key not found");
    } else {
        LOG_ERR("Read failed: %d", rc);
    }

    /* Delete the key */
    nvs_delete(&fs, 0x01);
}
```

**Key points:**
- `nvs_init()` must be called once before any read/write.
- Keys are 32-bit values. Use an enum or `#define` to avoid collisions.
- `nvs_write()` returns the number of bytes written (positive) or negative error.
- `nvs_read()` returns bytes read on success, `-ENOENT` if key doesn’t exist.

## Common Pitfalls & Gotchas

### 1. Sector Size Mismatch
NVS assumes all sectors in the partition are the same size. If your flash has mixed sector sizes (e.g., some 4KB, some 64KB), you must set `fs.sector_size` to the smallest erase size. Using a larger value will cause writes to fail silently or corrupt data. Always verify with `FLASH_PAGE_LAYOUT` API.

### 2. Key Collisions and Deletion
NVS does not enforce unique keys across writes. Writing the same key twice creates a duplicate record; the latest one is returned on read. However, `nvs_delete()` marks all records with that key as invalid — but garbage collection may not reclaim space immediately. If you write and delete rapidly, you can exhaust the partition. Use `nvs_clear()` to wipe everything, or design your key lifecycle carefully.

### 3. Power-Loss During Write
NVS writes are atomic at the record level (CRC-protected). However, if power fails during garbage collection, you may lose the entire sector being compacted. For critical data, consider using two separate NVS instances (primary and backup) or implement a simple transaction log on top. Zephyr’s NVS does not provide multi-record transactions.

## Try It Yourself

1. **Persist a boot counter**: Write a counter that increments on each boot. Use `nvs_read()` to get the previous value, increment, then `nvs_write()` it back. Verify the count survives a reset.

2. **Store a string configuration**: Write a function that saves a WiFi SSID (max 32 bytes) to NVS with key `0x10`. Then read it back and log it. Handle the case where the key doesn’t exist (first boot).

3. **Measure write endurance**: Write a loop that writes a 16-byte record 1000 times, then read back the final value. Use `nvs_calc_free_space()` to see how much space remains. Compare with the partition size to understand overhead.

## Next Up

Tomorrow, we’ll leave the flash behind and dive into the **Networking Stack: BSD Sockets & TCP/IP**. I’ll show you how to open a socket, connect to a remote server, and exchange data — all within Zephyr’s POSIX-like API. Bring your Ethernet or Wi-Fi shield.
