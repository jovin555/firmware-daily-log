---
title: "Day 07: MCUboot: Bootloader Architecture & Image Slots"
date: 2026-06-19
tags: ["til", "trustzone", "mcuboot", "bootloader", "slots"]
---

## What I Explored Today

Today I dove into MCUboot's core architecture—specifically how it manages firmware images across flash memory slots. MCUboot is the de facto open-source bootloader for constrained devices, used everywhere from Zephyr RTOS to Apache NuttX and TF-M. I focused on understanding the primary and secondary slot layout, the swap strategies, and how the bootloader decides which image to run. I also traced through the boot flow in the source code to see how slot metadata is read and validated.

## The Core Concept

MCUboot's architecture revolves around a simple but powerful idea: **always have a recoverable, known-good firmware image in a reserved flash region**. This is achieved by partitioning flash into at least two image slots:

- **Primary Slot (Slot 0):** The active image region. The bootloader jumps here after validation.
- **Secondary Slot (Slot 1):** The update staging area. New firmware is written here by an update agent (e.g., an OTA service).

The bootloader never modifies the primary slot during normal operation. Instead, it either swaps the secondary image into the primary slot, or it runs the secondary image in-place (if the hardware supports it). This design guarantees that even if a power loss occurs mid-swap, the device can fall back to the primary slot's image.

MCUboot supports three swap modes:
- **Swap-move (legacy):** Moves sectors, erases, and writes. Slow, but works on any flash.
- **Swap-using-scratch:** Uses a small scratch area to swap sector-by-sector. More efficient.
- **Direct-XIP (eXecute-In-Place):** No swap—just validates the secondary slot and runs it directly. Fastest, but requires the MCU to support XIP from both slots.

The decision logic is stored in an **image trailer** appended to each slot. The trailer contains a hash of the image, a signature (if signed), and a **swap status** area that tracks progress during a swap operation. This status area is what makes the bootloader crash-safe: it can resume a partial swap after a reset.

## Key Commands / Configuration / Code

### 1. Flash Partition Layout (Zephyr Device Tree Example)

MCUboot requires strict alignment. Here's a typical partition layout for an nRF52840:

```dts
/ {
    chosen {
        zephyr,code-partition = &slot0_partition;
    };

    partitions {
        compatible = "fixed-partitions";
        #address-cells = <1>;
        #size-cells = <1>;

        boot_partition: partition@0 {
            label = "mcuboot";
            reg = <0x00000000 0x0000C000>;  /* 48KB for bootloader */
        };

        slot0_partition: partition@c000 {
            label = "image-0";
            reg = <0x0000C000 0x00067000>;  /* 412KB primary slot */
        };

        slot1_partition: partition@73000 {
            label = "image-1";
            reg = <0x00073000 0x00067000>;  /* 412KB secondary slot */
        };

        scratch_partition: partition@da000 {
            label = "image-scratch";
            reg = <0x000DA000 0x00002000>;  /* 8KB scratch area */
        };
    };
};
```

**Key constraint:** Slots must be aligned to the flash's erase sector size (often 4KB for internal flash, but can be 64KB for external QSPI flash).

### 2. MCUboot Configuration (Kconfig)

```kconfig
# Enable swap-using-scratch (recommended for most MCUs)
CONFIG_BOOT_SWAP_USING_SCRATCH=y

# Set the scratch sector size (must match flash erase size)
CONFIG_BOOT_SCRATCH_SIZE=0x2000

# Enable image validation
CONFIG_BOOT_VALIDATE_SLOT0=y
CONFIG_BOOT_VALIDATE_SLOT1=y

# Maximum number of swap sectors (for crash recovery)
CONFIG_BOOT_MAX_IMG_SECTORS=256

# Enable logging for debugging
CONFIG_BOOT_LOG_LEVEL_INF=y
```

### 3. Boot Flow Pseudocode (from `boot/bootutil/src/bootutil_misc.c`)

```c
int boot_go(struct boot_rsp *rsp) {
    struct boot_status bs;
    int rc;

    // Step 1: Read image trailers from both slots
    rc = boot_read_image_headers(&bs, 0);  // primary slot
    if (rc) return rc;
    rc = boot_read_image_headers(&bs, 1);  // secondary slot
    if (rc) return rc;

    // Step 2: Check if a swap is in progress (crash recovery)
    if (boot_swap_in_progress()) {
        rc = boot_swap_resume(&bs);  // resume partial swap
        if (rc) return rc;
    }

    // Step 3: Determine if we need to swap
    if (boot_need_swap(&bs)) {
        rc = boot_swap_run(&bs);  // perform the swap
        if (rc) return rc;
    }

    // Step 4: Validate the image in the primary slot
    rc = boot_validate_image(0, &bs);
    if (rc) {
        // Fallback: try secondary slot
        rc = boot_validate_image(1, &bs);
        if (rc) return BOOT_EBADIMAGE;
        // Boot from secondary slot directly (if XIP)
        rsp->br_flash_dev_id = bs.flash_dev_id;
        rsp->br_image_off = secondary_slot_offset;
    } else {
        rsp->br_flash_dev_id = bs.flash_dev_id;
        rsp->br_image_off = primary_slot_offset;
    }

    return 0;
}
```

## Common Pitfalls & Gotchas

1. **Slot alignment mismatch with flash erase size:** If your slot offset isn't a multiple of the flash erase sector size (e.g., 0x1000 for internal flash), MCUboot will fail to erase or write. Always check `FLASH_ERASE_SIZE` in your MCU's datasheet. For external QSPI flash, this can be 64KB—a common trap.

2. **Scratch area too small for swap:** The scratch area must be at least as large as the largest flash sector. If you set `CONFIG_BOOT_SCRATCH_SIZE` to 0x1000 but your flash has 0x2000 sectors, the swap will silently corrupt data. MCUboot does not validate this at compile time.

3. **Forgetting to reserve space for the image trailer:** Each slot must have an extra 2KB (minimum) at the end for the trailer. If your partition size is exactly the image size, the trailer will overwrite the last sector of the image. Always add `CONFIG_BOOT_TRAILER_SIZE` (default 2048 bytes) to your slot size.

## Try It Yourself

1. **Inspect your flash layout:** Run `west build -t flash` with `CONFIG_BOOT_LOG_LEVEL_DBG=y` and look for the "Image slot layout" log lines. Verify that slot offsets are aligned to your flash's erase sector size.

2. **Simulate a partial swap:** Flash a known-good image to slot 0, then a different image to slot 1. Trigger a swap, then cut power at the exact moment the swap starts (use a debugger breakpoint in `boot_swap_run`). Reboot and check if MCUboot resumes correctly—you should see "Swap: resume" in the logs.

3. **Calculate your slot sizes:** Given a 1MB flash, a 48KB bootloader, and 4KB erase sectors, calculate the optimal slot sizes for swap-using-scratch. Assume each slot needs a 2KB trailer. Verify your math by configuring the partitions and building.

## Next Up

Tomorrow, I'll tackle **MCUboot Image Signing: Keys, imgtool & Verification**—how to generate RSA/EC keys, sign firmware images with `imgtool.py`, and configure MCUboot to reject unsigned or tampered images. We'll also look at the image trailer's hash and signature fields in detail.
