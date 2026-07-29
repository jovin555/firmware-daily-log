---
title: "Day 18: OTA/DFU on nRF54LM20: MCUboot Integration with Rust Apps"
date: 2026-07-29
tags: ["til", "rust-zephyr-nrf54", "mcuboot", "dfu"]
---

## What I Explored Today

Today I integrated MCUboot into our Rust + Zephyr firmware for the nRF54LM20, enabling over-the-air (OTA) firmware updates via the Device Firmware Upgrade (DFU) mechanism. I configured MCUboot as a second-stage bootloader, partitioned flash for primary and secondary slots, and built a Rust application that can receive, validate, and swap firmware images over BLE. The result: a fully functional OTA pipeline that lets us push updates without a debug probe.

## The Core Concept

MCUboot is the de facto standard bootloader for Zephyr-based devices. It handles image validation, cryptographic signing, and swap-based updates. The key insight is that MCUboot operates on a **two-slot** flash layout: a primary slot (where the running image lives) and a secondary slot (where the new image is staged). On boot, MCUboot checks if a valid image exists in the secondary slot; if so, it performs a swap (or a direct overwrite) and boots the new image. This design ensures atomicity—if the new image fails, MCUboot can revert to the previous one.

For our Rust application, integration means three things:
1. **Partitioning flash** correctly so MCUboot knows where slots live.
2. **Signing the Rust binary** with MCUboot’s `imgtool` so the bootloader trusts it.
3. **Implementing a DFU service** in Rust that receives the new image over BLE and writes it to the secondary slot.

The nRF54LM20 has 1 MB of flash, which we split into: MCUboot (64 KB), primary slot (448 KB), secondary slot (448 KB), and a scratch partition (64 KB). This leaves room for the swap algorithm.

## Key Commands / Configuration / Code

### 1. Zephyr Configuration for MCUboot

In your `prj.conf` for the MCUboot image (separate from your Rust app):

```kconfig
# Enable MCUboot as a bootloader
CONFIG_BOOTLOADER_MCUBOOT=y
CONFIG_MCUBOOT=y

# Swap mode: use swap-move for reliability
CONFIG_MCUBOOT_SWAP_USING_MOVE=y

# Image validation
CONFIG_MCUBOOT_SIGN_EC256=y
CONFIG_MCUBOOT_VALIDATE_SLOT0_ONCE=y

# Flash layout
CONFIG_FLASH_SIZE=0x100000  # 1 MB
CONFIG_MCUBOOT_SLOT0_SIZE=0x70000  # 448 KB
CONFIG_MCUBOOT_SLOT1_SIZE=0x70000
CONFIG_MCUBOOT_SCRATCH_SIZE=0x10000  # 64 KB
```

### 2. Device Tree Overlay for Flash Partitions

Add this to your `boards/arm/nrf54lm20_nrf54lm20.dts` overlay:

```dts
/ {
	chosen {
		zephyr,code-partition = &slot0_partition;
	};

	soc {
		flash-controller@39000 {
			flash@0 {
				partitions {
					compatible = "fixed-partitions";
					#address-cells = <1>;
					#size-cells = <1>;

					boot_partition: partition@0 {
						label = "mcuboot";
						reg = <0x0 0x10000>;  /* 64 KB */
					};
					slot0_partition: partition@10000 {
						label = "image-0";
						reg = <0x10000 0x70000>;  /* 448 KB */
					};
					slot1_partition: partition@80000 {
						label = "image-1";
						reg = <0x80000 0x70000>;  /* 448 KB */
					};
					scratch_partition: partition@F0000 {
						label = "image-scratch";
						reg = <0xF0000 0x10000>;  /* 64 KB */
					};
				};
			};
		};
	};
};
```

### 3. Signing the Rust Binary

After building your Rust app with `cargo build --release`, convert to a Zephyr-compatible binary and sign it:

```bash
# Convert ELF to raw binary
arm-none-eabi-objcopy -O binary target/thumbv8m.main-none-eabi/release/my_app my_app.bin

# Sign with MCUboot's imgtool (using EC256 key)
imgtool sign \
    --key ~/mcuboot/root-ec-p256.pem \
    --align 8 \
    --version 1.0.0 \
    --slot-size 0x70000 \
    --header-size 0x200 \
    --pad-header \
    my_app.bin \
    my_app_signed.bin
```

The `--header-size 0x200` matches MCUboot’s default image header. The `--pad-header` ensures the image starts at a flash-aligned offset.

### 4. Rust DFU Service (BLE-based)

Here’s a simplified snippet of the Rust side, using `zephyr::sys` bindings to write to the secondary slot:

```rust
use zephyr::sys::*;
use core::ptr;

// Flash device handle (from Zephyr device tree)
const FLASH_DEV: *const device = unsafe { DEVICE_DT_GET(DT_NODELABEL(flash_controller)) };

// Write a chunk of the new firmware to the secondary slot
fn write_secondary_slot(offset: u32, data: &[u8]) -> Result<(), i32> {
    // Unlock flash
    let ret = unsafe { flash_unlock(FLASH_DEV) };
    if ret != 0 {
        return Err(ret);
    }

    // Erase the page (must be page-aligned)
    let page_addr = SLOT1_OFFSET + offset;
    let ret = unsafe { flash_erase(FLASH_DEV, page_addr, data.len() as u32) };
    if ret != 0 {
        return Err(ret);
    }

    // Write data
    let ret = unsafe {
        flash_write(FLASH_DEV, page_addr, data.as_ptr() as *const c_void, data.len() as u32)
    };
    if ret != 0 {
        return Err(ret);
    }

    // Lock flash
    unsafe { flash_lock(FLASH_DEV) };
    Ok(())
}

// After receiving the complete image, request a reboot
fn request_update() {
    // Set a flag in retained RAM or use sys_reboot
    unsafe { sys_reboot(SYS_REBOOT_COLD) };
}
```

On reboot, MCUboot detects the image in slot 1, validates its signature, swaps it to slot 0, and boots it.

## Common Pitfalls & Gotchas

1. **Flash alignment and erase size**: The nRF54LM20’s flash has a minimum erase size of 4 KB (one page). Writing a single byte requires erasing the whole page first. Always align your write offsets to page boundaries, or you’ll get `-EINVAL`. I wasted an afternoon debugging this.

2. **Image header size mismatch**: MCUboot expects a 0x200-byte header by default. If you omit `--header-size 0x200` or `--pad-header` during signing, the bootloader will reject the image with a `BOOT_EBADIMAGE` error. Double-check your `imgtool` invocation.

3. **BLE MTU and fragmentation**: The nRF54LM20’s BLE stack has a default MTU of 23 bytes. Sending a 448 KB firmware image requires many packets. Implement a reliable transport (e.g., with sequence numbers and CRC) to handle packet loss. I use a simple sliding-window protocol with 20-byte payloads per packet.

## Try It Yourself

1. **Set up MCUboot**: Clone the MCUboot repo, generate an EC256 key pair, and build the bootloader for the nRF54LM20 using `west build -b nrf54lm20_nrf54lm20 -d build_mcuboot bootloader/mcuboot/boot/zephyr/`. Flash it to offset 0x0.

2. **Sign and flash a Rust app**: Build a minimal Rust app that blinks an LED, sign it with `imgtool`, and flash it to the primary slot (offset 0x10000). Verify it boots correctly.

3. **Implement a DFU client**: Write a Python script (using `bleak`) that connects to your device over BLE, reads a signed firmware file, and sends it chunk-by-chunk to a custom DFU characteristic. Test an OTA update by flashing a new version.

## Next Up

Tomorrow, we dive into **Security Features: TrustZone-M & Rust on nRF54LM20**. We’ll configure the ARM TrustZone-M to isolate secure and non-secure worlds, run Rust in the secure enclave, and protect cryptographic keys used for image signing. This is critical for production-grade OTA where you must prevent rollback attacks and secure the DFU channel.
