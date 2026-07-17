---
title: "Day 17: Multi-Image Updates: Bootloader, App & Peripheral Firmware Together"
date: 2026-07-17
tags: ["til", "secure-ota", "multi-image"]
---

## What I Explored Today

Today I dug into the mechanics of multi-image OTA updates—where a single update package contains the bootloader, main application, and peripheral firmware (like a BLE radio or sensor hub coprocessor) that must all be flashed atomically. I focused on how the MCUboot and Zephyr image manager handle this, what the image manifest looks like when you have three interdependent images, and how to structure the update slot logic so you don't brick a device when only one of the three images fails verification.

## The Core Concept

The reason we need multi-image updates is simple: modern embedded systems are rarely single-CPU. You might have a Cortex-M4 running the main application, a Cortex-M0+ handling BLE, and a separate flash region for the bootloader. If you update the main app to a version that expects a newer peripheral firmware ABI, but you don't update the peripheral, the system breaks. Worse, if you update the bootloader and it introduces a new image header format, the app images must match.

The key insight is **atomicity across images**. You cannot treat each image as an independent OTA. Instead, you define a *multi-image update group* where all images in the group must pass validation before any of them are committed. If the bootloader update fails CRC, you must roll back *all* images, not just the bootloader. This is different from the simple single-image swap logic we covered on Day 9.

In practice, this means your image manifest carries a dependency list: each image declares its required version range for other images. The bootloader (or update agent) reads this manifest, downloads all images to scratch or staging slots, validates every hash and signature, and only then performs the swap/confirm for the entire group.

## Key Commands / Configuration / Code

### 1. Zephyr Multi-Image Image Manager Configuration

In Zephyr, you enable multi-image support in your board's `Kconfig`:

```kconfig
# Enable multi-image update support
CONFIG_IMG_MANAGER=y
CONFIG_MCUBOOT_IMG_MANAGER=y
CONFIG_MCUBOOT_BOOTLOADER_MODE_OVERWRITE_ONLY=y

# Define the number of images managed by MCUboot
CONFIG_MCUBOOT_IMAGE_NUMBER=3

# Slot sizes must be defined per image in the DTS
# Example: flash partitions for image-0 (app), image-1 (ble), image-2 (bootloader)
```

### 2. Device Tree Partitioning (DTS snippet)

You need dedicated slots for each image. Here's a typical layout for a dual-core SoC:

```dts
&flash0 {
    partitions {
        compatible = "fixed-partitions";
        #address-cells = <1>;
        #size-cells = <1>;

        /* Bootloader slot (single, no swap) */
        boot_partition: partition@0 {
            label = "mcuboot";
            reg = <0x00000000 0x00020000>; /* 128KB */
        };

        /* Application image slots (slot0 + slot1 for swap) */
        slot0_partition: partition@20000 {
            label = "image-0";
            reg = <0x00020000 0x000C0000>; /* 768KB */
        };
        slot1_partition: partition@E0000 {
            label = "image-0-secondary";
            reg = <0x000E0000 0x000C0000>;
        };

        /* BLE coprocessor firmware slots */
        slot2_partition: partition@1A0000 {
            label = "image-1";
            reg = <0x001A0000 0x00040000>; /* 256KB */
        };
        slot3_partition: partition@1E0000 {
            label = "image-1-secondary";
            reg = <0x001E0000 0x00040000>;
        };

        /* Scratch partition for multi-image staging */
        scratch_partition: partition@220000 {
            label = "image-scratch";
            reg = <0x00220000 0x00020000>; /* 128KB */
        };
    };
};
```

### 3. Multi-Image Manifest (JSON for update server)

When generating the update package, the manifest lists dependencies. Here's a real example using `imgtool`:

```json
{
  "images": [
    {
      "image_index": 0,
      "file": "app_update.bin",
      "version": "2.1.0",
      "dependencies": [
        {"image": 1, "min_version": "1.5.0"},
        {"image": 2, "min_version": "1.0.0"}
      ]
    },
    {
      "image_index": 1,
      "file": "ble_fw_update.bin",
      "version": "1.5.0",
      "dependencies": [
        {"image": 0, "min_version": "2.0.0"}
      ]
    },
    {
      "image_index": 2,
      "file": "bootloader_update.bin",
      "version": "1.0.0",
      "dependencies": []
    }
  ],
  "atomic_group": true
}
```

### 4. Command to Sign and Package Multi-Image

Using `imgtool` from MCUboot:

```bash
# Sign each image with its own key (or shared key)
imgtool sign --key app_priv.pem --version 2.1.0 --slot-size 0xC0000 --header-size 0x200 app.bin app_signed.bin

imgtool sign --key ble_priv.pem --version 1.5.0 --slot-size 0x40000 --header-size 0x200 ble_fw.bin ble_fw_signed.bin

imgtool sign --key boot_priv.pem --version 1.0.0 --slot-size 0x20000 --header-size 0x200 bootloader.bin boot_signed.bin

# Create the multi-image update package (Zephyr uses a custom archive)
# The update agent on the device will parse the manifest and validate all images
```

### 5. Bootloader Validation Logic (pseudo-code)

This is what runs on the device during the update:

```c
/* In mcuboot's boot_go() or custom update agent */
int update_multi_image_group(void) {
    struct image_header *hdr;
    int rc;

    /* Step 1: Download all images to staging slots */
    for (int i = 0; i < NUM_IMAGES; i++) {
        rc = download_image_to_slot(i, staging_slot[i]);
        if (rc != 0) {
            erase_all_staging_slots();
            return -1;
        }
    }

    /* Step 2: Validate each image's hash and signature */
    for (int i = 0; i < NUM_IMAGES; i++) {
        rc = validate_image_signature(staging_slot[i]);
        if (rc != 0) {
            erase_all_staging_slots();
            return -2;
        }
    }

    /* Step 3: Check cross-image dependencies from manifest */
    rc = check_dependency_versions(staging_slot);
    if (rc != 0) {
        erase_all_staging_slots();
        return -3;
    }

    /* Step 4: Atomic swap — only commit if ALL pass */
    for (int i = 0; i < NUM_IMAGES; i++) {
        rc = swap_images(i, staging_slot[i], active_slot[i]);
        if (rc != 0) {
            /* Critical: roll back all already-swapped images */
            rollback_all_swapped_images(i);
            return -4;
        }
    }

    /* Step 5: Confirm all images as permanent */
    for (int i = 0; i < NUM_IMAGES; i++) {
        set_image_confirmed(i);
    }
    return 0;
}
```

## Common Pitfalls & Gotchas

1. **Partial swap disaster**: If you swap image 0 (app) successfully but image 1 (BLE) fails, your app now expects BLE firmware v1.5.0 but the BLE is still v1.4.0. The system must roll back image 0 *before* it boots. This requires a rollback mechanism that can undo a swap—only possible if you keep the old image in slot1 until all swaps succeed. Many implementations use a "pending" flag per image and a single "group commit" flag.

2. **Bootloader update brick risk**: Updating the bootloader itself is the most dangerous. If the new bootloader has a bug, you lose the ability to perform any future updates. The safest pattern is to use a *two-stage bootloader*: a tiny, immutable first-stage (ROM or write-protected flash) that can recover the main bootloader. Never update the bootloader unless you have a hardware recovery mechanism (e.g., USB DFU button).

3. **Dependency version hell**: If image A requires image B >= 1.5.0, but image B requires image A >= 2.0.0, you have a circular dependency. The manifest must be acyclic. Always test the dependency graph offline before generating the update package. Use a tool to validate that the combined version set is satisfiable.

## Try It Yourself

1. **Define a multi-image partition layout** for your target board in DTS. Include at least two application slots (app + coprocessor) and a scratch partition. Verify the total flash fits within your chip's memory map.

2. **Generate a multi-image manifest** with two images and a dependency constraint (e.g., app v2.0.0 requires peripheral v1.5.0). Use `imgtool` to sign both images, then write a script that validates the dependency graph before packaging.

3. **Implement a rollback function** in C that, given a swap index, can undo all swaps up to that index. Test it by simulating a failure on the second image swap and verifying the first image is restored to its original slot.

## Next Up

Tomorrow, we move from flash-level logistics to the wireless transport layer: **OTA Over BLE: GATT-Based DFU & Throughput Constraints**. We'll look at how to chunk large multi-image packages over BLE's 20-byte MTU, handle connection interruptions, and calculate realistic throughput for a 1MB update over BLE 5.0.
