---
title: "Day 09: MCUboot DFU: USB, BLE & Serial Upgrade Modes"
date: 2026-06-22
tags: ["til", "trustzone", "dfu", "ble", "usb"]
---

## What I Explored Today

Today I wired up three real-world DFU (Device Firmware Upgrade) transport modes for MCUboot: USB, BLE, and serial. While MCUboot itself is transport-agnostic—it only cares about image slots, headers, and trailers—the bootloader's `mcumgr` management protocol requires a reliable transport layer to push new images. I got all three working on an nRF52840 DK, and the differences in latency, reliability, and configuration complexity were stark.

## The Core Concept

MCUboot's DFU architecture separates *image management* from *image transport*. The bootloader itself doesn't know or care whether the new firmware arrives over USB, BLE, or UART. It only validates the image in the secondary slot and swaps or overwrites the primary slot on the next reset.

The transport layer is implemented by the application firmware (or a standalone recovery image) using the `mcumgr` protocol—a lightweight command/response framework built on CBOR serialization. The application receives image chunks, writes them to the secondary slot, and signals MCUboot to perform the swap on reboot.

Why this matters: You can deploy the same MCUboot image to products with different connectivity. A sensor node might use BLE DFU, while a wired gateway uses USB DFU. The bootloader configuration is identical; only the transport code in the application changes.

## Key Commands / Configuration / Code

### 1. Serial DFU (UART) — Simplest Path

Serial DFU uses the `mcumgr` SMP (Simple Management Protocol) over a UART connection. This is the lowest-overhead transport and works with any MCU with a UART.

**Application-side initialization (Zephyr):**
```c
// prj.conf — enable serial transport
CONFIG_MCUMGR=y
CONFIG_MCUMGR_SMP_UART=y
CONFIG_MCUMGR_CMD_IMG_MGMT=y
CONFIG_MCUMGR_CMD_OS_MGMT=y

// main.c — transport is auto-initialized by Zephyr
// No additional code needed; mcumgr registers the UART transport.
```

**Host-side command to push an image:**
```bash
# Build the signed image
imgtool sign --key root-rsa-2048.pem --align 8 --version 1.2.3 \
    --slot-size 0x100000 --header-size 0x200 build/app/zephyr/zephyr.bin \
    signed_update.bin

# Push via serial (baud 115200, device /dev/ttyACM0)
mcumgr --conntype serial --connstring /dev/ttyACM0,115200 \
    image upload signed_update.bin
```

### 2. USB DFU — Higher Throughput

USB DFU uses the USB CDC ACM class (virtual serial) or a dedicated USB DFU class. The `mcumgr` SMP protocol runs on top of the USB endpoint. This gives ~1 MB/s throughput vs ~115 KB/s for UART.

**Application configuration (Zephyr):**
```c
// prj.conf — USB device stack + mcumgr over USB
CONFIG_USB_DEVICE_STACK=y
CONFIG_USB_CDC_ACM=y
CONFIG_MCUMGR=y
CONFIG_MCUMGR_SMP_UART=y          // Reuses CDC ACM as UART transport
CONFIG_MCUMGR_CMD_IMG_MGMT=y

// main.c — enable USB
#include <usb/usb_device.h>

void main(void) {
    usb_enable(NULL);  // Enables CDC ACM endpoint
    // mcumgr transport binds automatically to the CDC ACM UART
}
```

**Host-side command (same syntax, different connection string):**
```bash
# Find the USB CDC ACM device (typically /dev/ttyACM0 on Linux)
mcumgr --conntype serial --connstring /dev/ttyACM0,115200 \
    image upload signed_update.bin
```

**Performance note:** USB DFU on nRF52840 achieves ~800 Kbps actual throughput. A 128 KB image uploads in ~1.5 seconds.

### 3. BLE DFU — Wireless, But Slower

BLE DFU uses the Nordic UART Service (NUS) or a custom SMP BLE service. The `mcumgr` protocol is tunneled through BLE notifications and writes.

**Application configuration (Zephyr):**
```c
// prj.conf — BLE + mcumgr SMP over BLE
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_DEVICE_NAME="MyDevice-DFU"
CONFIG_MCUMGR=y
CONFIG_MCUMGR_SMP_BT=y           // BLE transport
CONFIG_MCUMGR_CMD_IMG_MGMT=y
CONFIG_MCUMGR_CMD_OS_MGMT=y

// main.c — start BLE advertising
#include <bluetooth/bluetooth.h>
#include <mgmt/mcumgr/smp_bt.h>

void main(void) {
    bt_enable(NULL);
    smp_bt_register();            // Register SMP BLE service
    bt_le_adv_start(...);         // Start advertising
}
```

**Host-side command (requires Bluetooth adapter):**
```bash
# Scan for device
mcumgr --conntype ble --connstring "peer_name=MyDevice-DFU" \
    image upload signed_update.bin
```

**Performance note:** BLE DFU on nRF52840 achieves ~30-50 Kbps. A 128 KB image takes 25-40 seconds. Connection interval and MTU size dramatically affect speed.

## Common Pitfalls & Gotchas

### 1. Transport Initialization Order
If you initialize the transport (USB or BLE) *after* the mcumgr subsystem, the SMP service won't find the transport and will silently fail. Always initialize hardware first, then mcumgr. In Zephyr, this means calling `usb_enable()` or `bt_enable()` before any mcumgr API calls.

### 2. Image Size Mismatch
MCUboot validates the image header's `image_size` field against the secondary slot size. If your signed image is larger than the slot, the upload succeeds but the swap fails silently. Always verify slot sizes in your device tree:
```dts
&slot0_partition { reg = <0x00000 0x100000>; };  // 1 MB primary
&slot1_partition { reg = <0x100000 0x100000>; };  // 1 MB secondary
```

### 3. BLE Connection Parameters
Default BLE connection intervals (50-100 ms) give terrible DFU throughput. Optimize by requesting a 7.5 ms connection interval and maximum MTU (247 bytes) after connection:
```c
// Request optimal connection parameters
struct bt_le_conn_param *param = BT_LE_CONN_PARAM(6, 6, 0, 400);
bt_conn_le_param_update(conn, param);
```

## Try It Yourself

1. **Serial DFU baseline:** Flash a signed MCUboot image to your board, then use `mcumgr --conntype serial` to upload a new image. Time the upload and verify the swap on reboot.

2. **USB DFU migration:** Enable USB CDC ACM on your board and repeat the upload. Compare throughput. You'll need to add `CONFIG_USB_DEVICE_STACK=y` and handle USB enumeration in your main loop.

3. **BLE DFU with optimization:** Enable BLE SMP transport and upload an image wirelessly. Then modify the connection parameters to use a 7.5 ms interval and measure the speed improvement. Watch for disconnections if your BLE stack can't sustain that rate.

## Next Up

Tomorrow we dive into **MCUboot Rollback Protection & Anti-Rollback Counters** — how to prevent downgrade attacks and enforce firmware version monotonicity using hardware-backed security features in TrustZone-M. We'll implement a secure counter that persists across reboots and survives image swaps.
