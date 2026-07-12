---
title: "Day 30: MCUboot: Secure Bootloader & DFU"
date: 2026-07-12
tags: ["til", "zephyr", "mcuboot", "bootloader"]
---

## What I Explored Today

Today I integrated MCUboot into a Zephyr project targeting an nRF52840 DK. MCUboot is the de facto secure bootloader for Zephyr, handling image validation, multi-image boot chains, and firmware-over-the-air (FOTA) updates. I walked through configuring the bootloader slot layout, signing production images, and triggering a swap-based DFU from the application. The goal was to understand not just how to enable `CONFIG_BOOTLOADER_MCUBOOT`, but how the image management subsystem (`img_mgmt`) interacts with MCUboot's swap logic at runtime.

## The Core Concept

MCUboot solves a fundamental problem: how do you safely update firmware on an embedded device without bricking it? The answer is a two-slot image architecture. Slot 0 (primary) holds the running application. Slot 1 (secondary) holds the update candidate. MCUboot validates the candidate's signature and hash before swapping or overwriting the primary slot.

The "why" here is trust and atomicity. Without a secure bootloader, a corrupted or malicious image can permanently disable a device. MCUboot enforces cryptographic image verification (RSA-2048 or EC256) and supports three update modes: overwrite-only (simplest, no rollback), swap (atomic with rollback), and direct-xip (run-in-place from secondary slot). For production, you almost always want swap mode: it preserves the ability to revert to the previous image if the new one fails to boot.

MCUboot also integrates with Zephyr's Device Firmware Update (DFU) subsystem. The `img_mgmt` MCUmgr group lets you upload, test, and confirm images over BLE, UART, or HTTP. The flow is: upload image to slot 1 → mark as "pending" → reboot → MCUboot swaps → application boots from slot 0 (now the new image) → application calls `boot_write_img_confirmed()` to make the swap permanent.

## Key Commands / Configuration / Code

### 1. Enabling MCUboot in your Zephyr project

In your application's `prj.conf`:

```kconfig
# Enable MCUboot as the bootloader
CONFIG_BOOTLOADER_MCUBOOT=y

# Image management for DFU
CONFIG_MCUMGR=y
CONFIG_MCUMGR_CMD_IMG_MGMT=y
CONFIG_MCUMGR_CMD_OS_MGMT=y

# Enable swap mode (requires flash partition of 2x image size)
CONFIG_MCUBOOT_SWAP_USING_MOVE=y

# Signature verification (EC256)
CONFIG_MCUBOOT_SIGNATURE_KEY_FILE="bootloader/mcuboot/root-ec-p256.pem"
```

### 2. Partition layout in `app.overlay`

```dts
/ {
	chosen {
		zephyr,code-partition = &slot0_partition;
	};
};

&flash0 {
	partitions {
		compatible = "fixed-partitions";
		#address-cells = <1>;
		#size-cells = <1>;

		boot_partition: partition@0 {
			label = "mcuboot";
			reg = <0x0 0x10000>;        /* 64 kB for MCUboot itself */
		};
		slot0_partition: partition@10000 {
			label = "image-0";
			reg = <0x10000 0x70000>;    /* 448 kB primary slot */
		};
		slot1_partition: partition@80000 {
			label = "image-1";
			reg = <0x80000 0x70000>;    /* 448 kB secondary slot */
		};
		scratch_partition: partition@f0000 {
			label = "image-scratch";
			reg = <0xf0000 0x10000>;    /* 64 kB scratch for swap */
		};
	};
};
```

### 3. Signing a production image

After building your application, sign the binary with `imgtool`:

```bash
# Build the application (produces build/zephyr/zephyr.signed.bin if configured)
west build -b nrf52840dk_nrf52840 -t mcuboot

# Or sign manually:
imgtool sign \
  --key bootloader/mcuboot/root-ec-p256.pem \
  --align 8 \
  --version 1.0.0 \
  --slot-size 0x70000 \
  --header-size 0x200 \
  build/zephyr/zephyr.bin \
  signed_image.bin
```

### 4. Triggering a DFU update from the application

```c
#include <mgmt/mcumgr/smp_bt.h>
#include <img_mgmt/img_mgmt.h>

void start_dfu_service(void)
{
    /* Initialize Bluetooth SMP transport */
    smp_bt_register();

    /* Register image management group */
    img_mgmt_register_group();

    printk("DFU over BLE ready. Use mcumgr CLI to upload.\n");
}

/* After receiving new image, mark it for swap on next boot */
void confirm_and_swap(void)
{
    int rc = boot_request_upgrade(BOOT_UPGRADE_PERMANENT);
    if (rc == 0) {
        printk("Swap pending on next reset\n");
        sys_reboot(0);
    }
}
```

### 5. Using `mcumgr` CLI to push an update

```bash
# From host machine, upload signed image over BLE
mcumgr --conntype ble --connstring "peer_name=MyDevice" image upload signed_image.bin

# List images on device
mcumgr --conntype ble --connstring "peer_name=MyDevice" image list

# Test the image (boots once, then reverts unless confirmed)
mcumgr --conntype ble --connstring "peer_name=MyDevice" image test <hash>

# Confirm the image permanently
mcumgr --conntype ble --connstring "peer_name=MyDevice" image confirm
```

## Common Pitfalls & Gotchas

1. **Slot size mismatch between MCUboot and application**  
   If your `slot-size` in `imgtool sign` doesn't match the partition size in your DTS, MCUboot will reject the image with a "magic not found" error. Always verify: `west build -t partition_manager` prints the actual layout.

2. **Forgetting to call `boot_write_img_confirmed()`**  
   In swap mode, the new image boots once in "trial" state. If you don't confirm it (via `img_mgmt` or direct API call), MCUboot reverts to the old image on the next reset. This is by design, but many engineers miss it and wonder why their update "didn't stick."

3. **Overlapping flash regions when using external flash**  
   If your secondary slot is on external QSPI flash, ensure the flash driver is initialized before MCUboot runs. This requires configuring `CONFIG_MCUBOOT_FLASH_BYPASS=y` and manually setting up the flash map. Otherwise, MCUboot will hang trying to read an uninitialized bus.

## Try It Yourself

1. **Build MCUboot + application for your board**  
   Use `west build -b <your_board> -t mcuboot` to build both the bootloader and your app. Flash the combined hex (`build/zephyr/zephyr.hex`) and verify the device boots with "MCUboot" in the boot banner.

2. **Sign and upload a version increment**  
   Change your application version in `prj.conf` (`CONFIG_MCUBOOT_IMAGE_VERSION="1.0.1"`), rebuild, sign, and upload via `mcumgr image upload`. Use `image list` to confirm both slots are populated.

3. **Test rollback behavior**  
   Upload a test image with `mcumgr image test <hash>` (not `confirm`). Reboot twice. Verify the device reverts to the original image. Then repeat with `image confirm` and confirm the swap is permanent.

## Next Up

Tomorrow, we dive into **TF-M: Trusted Firmware-M & Secure Services**. We'll explore how to partition a Cortex-M33 into secure and non-secure worlds, leverage PSA APIs for cryptography and attestation, and integrate TF-M with Zephyr's build system. Bring your ARMv8-M board.
