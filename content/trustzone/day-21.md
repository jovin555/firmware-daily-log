---
title: "Day 21: Full Review & Project: Secure Boot Chain on nRF9160"
date: 2026-07-03
tags: ["til", "trustzone", "review", "project", "secure-boot"]
---

## What I Explored Today

Today I pulled together everything from the past three weeks into a single, working secure boot chain implementation on the nRF9160 SiP. I built a complete reference project that chains the immutable boot ROM, the TF-M secure bootloader (MCUboot), and a signed non-secure application image, all verified through the Arm TrustZone hardware boundary. The goal was to prove the full trust chain from cold reset to application execution, with no software-only bypass possible. I used the nRF9160 DK (PCA10090) with nRF Connect SDK v2.6.1, and validated each stage using the debugger and UART logs.

## The Core Concept

A secure boot chain is not just about checking signatures; it's about establishing a **root of trust** that is physically immutable and then propagating that trust through every subsequent stage. On the nRF9160, the root is the boot ROM, which is mask-programmed at the factory and cannot be altered. It loads and verifies the first-stage bootloader (the TF-M Secure Bootloader, which is MCUboot compiled with TrustZone support) from the beginning of the external flash. That bootloader then verifies the signed application image before jumping to it.

The "why" is critical: without this chain, an attacker who gains physical access or exploits a firmware update vulnerability can replace your application with malicious code. The chain ensures that even if the application flash is corrupted, the device will either refuse to boot or fall back to a known-good image. The TrustZone hardware enforces that the secure bootloader runs in the Secure World, and the application runs in the Non-Secure World, with memory and peripheral access strictly partitioned. The boot ROM's public key hash is stored in the **UICR** (User Information Configuration Registers), which are one-time-programmable (OTP) on production devices.

## Key Commands / Configuration / Code

### 1. Building the Secure Bootloader (TF-M with MCUboot)

The secure bootloader is built as a child image of the application project. In your `prj.conf` for the application, you must enable MCUboot and configure the image slot layout:

```kconfig
# Application prj.conf
CONFIG_BOOTLOADER_MCUBOOT=y
CONFIG_MCUBOOT_IMAGE_VERSION="1.0.0"
CONFIG_BOOTLOADER_MCUBOOT_IMG_MANAGER=y
CONFIG_IMG_MANAGER=y

# Slot layout: primary slot at 0x10000, secondary at 0x80000
CONFIG_PM_PARTITION_SIZE_MCUBOOT=0x10000
CONFIG_PM_PARTITION_SIZE_APP_PRIMARY=0x70000
CONFIG_PM_PARTITION_SIZE_APP_SECONDARY=0x70000
```

Build the bootloader separately:

```bash
# From the nRF Connect SDK root
west build -b nrf9160dk_nrf9160_ns -d build_mcuboot \
  -p always bootloader/mcuboot/boot/nrf/mcuboot_sha256 \
  -- -DCONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y \
     -DCONFIG_BOOT_UPGRADE_ONLY=y
```

### 2. Signing the Application Image

After building the non-secure application, sign it with the private key that corresponds to the public key hash in UICR:

```bash
# Sign using mcuboot's imgtool
imgtool sign \
  --key bootloader/mcuboot/root-ec-p256.pem \
  --align 8 \
  --version 1.0.0 \
  --slot-size 0x70000 \
  --max-sectors 128 \
  --header-size 0x200 \
  build/zephyr/zephyr.signed.bin \
  build/zephyr/app_signed.bin
```

### 3. Flashing the Complete Chain

Flash the bootloader, then the signed application. The bootloader must be placed at the start of external flash (0x10000 after the boot ROM area):

```bash
# Flash bootloader to external flash (QSPI)
nrfjprog --program build_mcuboot/zephyr/mcuboot.hex \
  --sectorerase -f nrf91 --qspi

# Flash signed application to primary slot
nrfjprog --program build/zephyr/app_signed.bin \
  --sectorerase -f nrf91 --qspi \
  --mem 0x100000
```

### 4. Verifying the Chain in UART Logs

After reset, the boot ROM prints a single character, then MCUboot logs:

```
*** Booting MCUboot v2.0.0 ***
[INF] Image 0: magic=good, swap_type=0, copy_done=0, image_ok=1
[INF] Image index: 0, swap type: none
[INF] Bootloader chainload address: 0x00010000
[INF] Jumping to non-secure image...
```

If the signature is invalid, you'll see:

```
[ERR] Image 0: signature check failed
[ERR] Unable to find a bootable image
```

## Common Pitfalls & Gotchas

1. **UICR public key hash mismatch**: The boot ROM compares the SHA-256 hash of the bootloader's public key against the hash stored in UICR. If you change the signing key without updating UICR, the boot ROM will refuse to load the bootloader. On development boards, UICR is reprogrammable, but on production devices it's OTP. Always test with the final key before locking.

2. **Slot layout alignment**: The nRF9160's external flash (MX25R64) has 4 KB sectors. MCUboot requires that image slots start on a sector boundary. If you set `CONFIG_PM_PARTITION_SIZE_APP_PRIMARY` to a value not aligned to 0x1000, the bootloader will fail to erase or write images. Always use multiples of 0x1000.

3. **Non-secure application vector table**: After the bootloader jumps to the application, the CPU is in Non-Secure state. The application's vector table must be placed at the start of the Non-Secure image (typically 0x10000) and the VTOR register must be set to that address. If you forget to set `CONFIG_ARM_NONSECURE_PREEMPTIBLE=y` in the application, interrupts will not work correctly.

## Try It Yourself

1. **Build and flash the full chain**: Using the commands above, build MCUboot and a simple blinky application. Sign the application with the provided ECDSA P-256 key. Verify that the boot ROM loads MCUboot and MCUboot loads the application. Break the signature (e.g., sign with a different key) and confirm the device refuses to boot.

2. **Implement a fallback image**: Configure a secondary slot and enable swap mode in MCUboot (`CONFIG_BOOT_SWAP_USING_MOVE=y`). Flash a known-good image in the primary slot and a corrupted image in the secondary slot. Verify that MCUboot detects the bad image and boots the primary.

3. **Lock the UICR**: Program a custom public key hash into UICR using `nrfjprog --memwr 0x00FF8100 <hash>` and then set the lock bit (`CONFIG_BOOT_UICR_LOCK=y` in MCUboot). Rebuild and flash. Confirm that the boot ROM now only accepts bootloaders signed with that specific key. Attempt to flash a different bootloader and observe the failure.

## Next Up

Tomorrow is **Day 22: Full Review & Project: Secure Boot Chain on nRF9160** — we'll do a comprehensive review of the entire TrustZone and Secure Boot series, including a checklist for production deployment, common security audit findings, and a final project that ties together secure boot, TrustZone isolation, and secure firmware update over-the-air.
