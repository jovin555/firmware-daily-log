---
title: "Day 24: Secure Boot: Verified Boot Chain on Embedded Linux"
date: 2026-07-06
tags: ["til", "embedded-linux", "secure-boot", "signing"]
---

## What I Explored Today

Today I dove into the verified boot chain for embedded Linux — the mechanism that ensures every piece of code running on the device, from the first instruction in ROM to the kernel and rootfs, is cryptographically signed and verified before execution. I set up a complete secure boot flow using U-Boot with FIT image signing, dm-verity for rootfs integrity, and a hardware-backed key store on a BeagleBone Black. The goal was to understand not just how to enable it, but what actually happens when a signature check fails at each stage.

## The Core Concept

Secure boot on embedded Linux isn't a single feature — it's a chain of trust. The chain starts in immutable hardware (Boot ROM) that validates the first-stage bootloader. That bootloader validates the next stage (typically U-Boot SPL), which validates U-Boot proper, which validates the kernel and device tree, and finally the kernel validates the root filesystem before mounting it. If any link in this chain breaks, the boot process stops.

Why does this matter? In production, an attacker who gains physical access to a device can replace your kernel with a malicious one, or modify the rootfs to exfiltrate data. Without verified boot, the device will happily boot whatever is on the flash. With verified boot, any tampering is detected, and the device either refuses to boot or falls back to a known-good recovery partition.

The key insight is that verification must be **cryptographic**, not just checksum-based. An attacker can recompute a SHA256 hash after modifying a file. But without the private key, they cannot produce a valid RSA signature. The public key is embedded in the verifying stage (e.g., U-Boot), and the private key lives on a secure build server — never on the device.

## Key Commands / Configuration / Code

### 1. Generating signing keys for U-Boot FIT images

```bash
# Generate RSA 4096-bit key pair for signing kernel, DTB, and initramfs
# The private key stays on the build machine; the public key goes into U-Boot
openssl genrsa -F4 -out dev.key 4096
openssl rsa -in dev.key -pubout -out dev.pubkey

# Create a certificate for U-Boot's key directory
# This embeds the public key hash into U-Boot binary
mkimage -r -f keyname -K u-boot.dtb -k keys/ -o sha256,rsa4096 dev.pubkey
```

### 2. Signing a FIT image (kernel + DTB + initramfs)

```bash
# Create a FIT image source file (kernel.itb) with signature node
# The signature is appended to the FIT image after building
mkimage -f kernel.its kernel.itb

# Sign the FIT image with the private key
# This adds a 'signature' subnode under each image and config
mkimage -F -k keys/ -K u-boot.dtb -r kernel.itb -o sha256,rsa4096 dev.key
```

### 3. U-Boot configuration for verified boot (in `include/configs/myboard.h`)

```c
/* Enable verified boot support */
#define CONFIG_FIT_SIGNATURE
#define CONFIG_RSA
#define CONFIG_LEGACY_IMAGE_FORMAT

/* Require signature verification — boot fails if signature missing */
#define CONFIG_FIT_SIGNATURE_STRICT

/* Set the key directory in the device tree */
#define CONFIG_FIT_CIPHER
```

### 4. Kernel command-line for dm-verity on rootfs

```bash
# After building rootfs with veritysetup, append to kernel cmdline:
root=/dev/dm-0 dm-mod.create="verity,,,ro,0 rootdev /dev/mmcblk0p2 hashdev /dev/mmcblk0p3 hashstart 0 alg sha256 root_hash <expected_hash>"
```

### 5. Verifying the boot chain manually (debugging)

```bash
# From U-Boot shell, check if the FIT image is signed
=> fit_check_sign fit#conf@1 keys/ dev.pubkey

# Check the hash of the loaded kernel before booting
=> hash sha256 $kernel_addr_r $filesize
```

## Common Pitfalls & Gotchas

**1. The public key must be compiled into U-Boot before signing.**  
If you sign a FIT image with a key, then later compile U-Boot with that key's hash, the verification will fail because the signature was created with a key that U-Boot doesn't know about. Always embed the public key hash into U-Boot *first*, then sign images with the corresponding private key. I wasted three hours on this — the error message "Bad hash value for signature" is misleading.

**2. dm-verity root hash must match exactly between build and device.**  
If you regenerate the rootfs but forget to update the kernel command line with the new root hash, the device will panic on boot with a "dm-verity corruption detected" message. Automate this in your build system — I use a Makefile target that extracts the root hash from `veritysetup format` output and writes it into the kernel FIT image's configuration node.

**3. U-Boot's environment can bypass verified boot if not locked.**  
Even with FIT signing enabled, if an attacker can modify U-Boot's environment variables (e.g., via `saveenv`), they can change `bootcmd` to load an unsigned kernel from a different memory address. Always set `CONFIG_ENV_IS_NOWHERE` or use hardware write-protect on the environment storage. On production devices, I disable the U-Boot console entirely.

## Try It Yourself

1. **Set up U-Boot FIT signing on a QEMU ARM target.** Generate a 2048-bit RSA key pair, sign a minimal FIT image containing a kernel and DTB, and configure U-Boot to reject unsigned images. Verify that booting an unsigned image fails with a clear error.

2. **Implement dm-verity on a Raspberry Pi rootfs.** Create a second partition for the hash tree, use `veritysetup format` to generate the root hash, and modify the kernel command line to mount the rootfs as a verity device. Trigger a corruption by writing random data to the rootfs partition and observe the kernel panic.

3. **Build a two-stage boot chain with SPL verification.** On a BeagleBone Black, configure U-Boot SPL to verify the FIT image containing U-Boot proper, then have U-Boot proper verify the kernel. Use different keys for each stage and test that a tampered U-Boot proper is rejected by SPL.

## Next Up

Tomorrow we tackle **OTA Updates: SWUpdate, RAUC & A/B Partitions** — how to deliver signed updates to devices in the field without bricking them, with atomic rollback and dual-copy redundancy.
