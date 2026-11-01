---
title: "Day 22: BLE Firmware Updates: MCUmgr/SMP DFU over BLE"
date: 2026-11-01
tags: ["til", "ble-medical", "dfu", "mcumgr"]
---

# Day 22: BLE Firmware Updates: MCUmgr/SMP DFU over BLE

## What I Explored Today

Today I wired up over-the-air firmware updates for a nRF52840 medical sensor node using MCUmgr over BLE, which is the SMP (Simple Management Protocol) transport that Zephyr and Nordic's nRF Connect SDK ship out of the box. The goal was to push a new application image from a Linux host to a battery-powered device over a single BLE connection, with image validation and rollback safety. I spent most of the day fighting MTU negotiation and the difference between the legacy DFU and the newer MCUmgr path, but the end result is a working `mcumgr` CLI workflow that I can script into CI.

## The Core Concept

MCUmgr is a management protocol layered on top of SMP, which is a simple request/response framing (8-byte header + CBOR payload) that can ride over UART, UDP, or BLE. Over BLE, SMP uses a GATT service with two characteristics: one for writing commands (write-without-response preferred) and one for receiving responses (notify). Because BLE packets are small, the SMP layer fragments large messages across multiple GATT writes, and the receiver reassembles them.

The reason this matters for medical devices: you cannot afford a half-flashed image on a device that dispenses insulin or reports SpO2. MCUmgr's DFU path uses **image slots** (primary/secondary) with a **bootloader** (MCUboot) that verifies a SHA-256 hash and signature before swapping. If the new image fails validation, MCUboot reverts to the previous slot on the next boot. That "test then confirm" flow is the whole point — the device boots the new image in a *test* state, the application calls `boot_write_img_confirmed()` once it's healthy, and only then is the swap made permanent.

The BLE transport is just plumbing: SMP frames go into GATT writes, responses come back as notifications, and the host library (`mcumgr` CLI or `smpclient`) handles fragmentation, retries, and the CBOR encoding of `image upload` / `image test` / `image confirm` commands.

## Key Commands / Configuration / Code

**Zephyr / nRF Connect SDK `prj.conf`** — enable MCUmgr, SMP over BLE, and MCUboot:

```conf
# MCUboot + image management
CONFIG_BOOTLOADER_MCUBOOT=y
CONFIG_MCUMGR=y
CONFIG_MCUMGR_GRP_IMG=y
CONFIG_MCUMGR_GRP_OS=y

# SMP transport over BLE
CONFIG_MCUMGR_TRANSPORT_BT=y
CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW=y
CONFIG_MCUMGR_TRANSPORT_BT_CONN_PARAM_CONTROL=y

# Image group needs a large enough buffer for chunked uploads
CONFIG_MCUMGR_GRP_IMG_UPLOAD_HASH_TO_TLV=y
CONFIG_MCUMGR_BUF_SIZE=2048

# BLE GATT: request a larger ATT MTU for throughput
CONFIG_BT_L2CAP_TX_MTU=247
CONFIG_BT_BUF_ACL_RX_SIZE=251
CONFIG_BT_CTLR_DATA_LENGTH_MAX=251
```

**Signing the image** (host side, using `imgtool` from MCUboot):

```bash
# Generate a key pair once (keep the private key offline in production)
imgtool keygen -k root-rsa-2048.pem -t rsa-2048

# Sign the built zephyr.bin into a flashable, MCUmgr-uploadable image
imgtool sign \
  --key root-rsa-2048.pem \
  --align 4 \
  --version 1.2.3+0 \
  --header-size 0x200 \
  --slot-size 0x70000 \
  --pad-header \
  zephyr.bin zephyr.signed.bin
```

**Uploading over BLE with the `mcumgr` CLI** (from `mcumgr-cli` / `golioth` tooling):

```bash
# Discover the device's SMP service UUID (usually 8D53DC1D-...)
mcumgr --conntype ble --connstring peer_name=MedSensor conn_params='mtu=247' \
  image list

# Upload the signed image to slot 1 (secondary)
mcumgr --conntype ble --connstring peer_name=MedSensor \
  image upload zephyr.signed.bin

# Mark it for test-boot on next reset
mcumgr --conntype ble --connstring peer_name=MedSensor \
  image test <hash-from-image-list>

# After reboot, the app calls boot_write_img_confirmed(); verify:
mcumgr --conntype ble --connstring peer_name=MedSensor \
  image confirm <hash>
```

**Application-side confirmation** (Zephyr):

```c
#include <dfu/mcuboot.h>

void app_main(void)
{
    /* Only confirm after self-test passes (sensor init, BLE adv, etc.) */
    if (self_test_passed()) {
        int rc = boot_write_img_confirmed();
        if (rc == 0) {
            LOG_INF("Image confirmed; rollback disabled");
        }
    }
}
```

## Common Pitfalls & Gotchas

1. **MTU and fragmentation timeouts.** With the default 23-byte ATT MTU, a 500 KB image takes forever and often trips the SMP response timeout. Negotiate 247+ and set `CONFIG_MCUMGR_BUF_SIZE` large enough to hold a full SMP frame. Also raise the BLE connection interval tolerance — a sleepy peripheral that misses notifications will stall the upload.

2. **Forgetting to confirm.** If the app never calls `boot_write_img_confirmed()`, MCUboot will revert on the *next* reset — which looks like a random brick in the field. Wire confirmation to a real health check, not just "main() started."

3. **Slot size mismatch.** `--slot-size` in `imgtool` must match the actual flash partition in `pm_static.yml` / devicetree. A too-small slot silently truncates or fails signing; a too-large one overlaps the scratch area and corrupts the swap. Always cross-check `image list` output against your partition map.

## Try It Yourself

1. Build a Zephyr sample (`smp_svr`) for your nRF52/nRF53 board, sign it with `imgtool`, and upload it over BLE using `mcumgr image upload`. Confirm the hash changes in `image list`.
2. Deliberately break the confirmation: comment out `boot_write_img_confirmed()`, flash a new image, reset twice, and watch MCUboot revert. Verify with `image list` that the active slot rolled back.
3. Measure throughput at MTU 23 vs. 247 using `mcumgr image upload` and a stopwatch — calculate effective bytes/sec and decide whether your OTA window fits your battery budget.

## Next Up

Tomorrow I'm switching sides of the link: **Android BLE — Scanning, Connecting, GATT Operations & Bonding**. We'll build a minimal Kotlin client that connects to the same medical sensor, walks the GATT tree, and handles the bonding quirks (Just Works vs. passkey) that trip up every first-time Android BLE developer.
