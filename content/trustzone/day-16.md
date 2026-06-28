---
title: "Day 16: Secure Boot on Embedded Linux: U-Boot Verified Boot"
date: 2026-06-28
tags: ["til", "trustzone", "uboot", "verified-boot"]
---

## What I Explored Today

Today I dug into U-Boot's Verified Boot mechanism—the practical implementation of secure boot on embedded Linux systems that don't have a full Trusted Execution Environment (TEE) or ARM TrustZone firmware. While TrustZone provides hardware isolation for the boot process, many production systems rely on U-Boot's Verified Boot as the first software-level integrity check. I walked through generating keys, signing FIT images, and configuring U-Boot to enforce signature verification before loading any kernel or device tree blob.

## The Core Concept

The fundamental problem Verified Boot solves is simple: how does the bootloader know the kernel it's about to execute hasn't been tampered with? In an embedded Linux system, the boot chain typically goes: ROM bootloader → SPL → U-Boot proper → kernel. If an attacker can modify the kernel image on the storage medium (eMMC, NAND, SD card), they can gain arbitrary code execution.

U-Boot's Verified Boot uses asymmetric cryptography. You generate a public/private key pair. The private key stays on your build server—never on the device. The public key is compiled into U-Boot itself. When you build a FIT image (Flattened Image Tree), you sign it with the private key. At boot time, U-Boot verifies the signature against the embedded public key before loading anything.

The "why" here is critical: this prevents offline attacks on the root filesystem or kernel partition. Even if an attacker has physical access and can rewrite the storage, they cannot boot a modified kernel without the private key. Combined with hardware-backed key storage (like OTP fuses or a TPM), this becomes a robust root of trust.

## Key Commands / Configuration / Code

### 1. Generate signing keys

```bash
# Generate RSA key pair for signing FIT images
# Use 2048-bit keys for embedded systems (4096 is overkill on slow CPUs)
openssl genrsa -F4 -out dev.key 2048
openssl rsa -in dev.key -pubout -out dev.pubkey

# Extract the public key in U-Boot's required DER format
# This is what gets compiled into U-Boot
openssl rsa -in dev.key -pubout -outform DER -out dev.pubkey.der
```

### 2. Configure U-Boot to use Verified Boot

In your board's `defconfig` (e.g., `configs/myboard_defconfig`):

```makefile
# Enable Verified Boot support
CONFIG_FIT=y
CONFIG_FIT_SIGNATURE=y
CONFIG_RSA=y
CONFIG_SPL_FIT_SIGNATURE=y  # If using SPL verified boot

# Specify the public key to embed
CONFIG_FIT_SIGNATURE_STRICT=y  # Reject unsigned images

# For key storage in U-Boot device tree
CONFIG_SPL_LOAD_FIT=y
```

### 3. Create and sign a FIT image

Create `kernel.its` (Image Tree Source):

```dts
/dts-v1/;

/ {
    description = "Linux kernel with DTB";
    #address-cells = <1>;

    images {
        kernel-1 {
            description = "Linux kernel";
            data = /incbin/("./zImage");
            type = "kernel";
            arch = "arm";
            os = "linux";
            compression = "none";
            load = <0x80008000>;
            entry = <0x80008000>;
            hash-1 {
                algo = "sha256";
            };
        };
        fdt-1 {
            description = "Device Tree";
            data = /incbin/("./myboard.dtb");
            type = "flat_dt";
            arch = "arm";
            compression = "none";
            hash-1 {
                algo = "sha256";
            };
        };
    };
    configurations {
        default = "conf-1";
        conf-1 {
            description = "Boot Linux kernel with FDT";
            kernel = "kernel-1";
            fdt = "fdt-1";
            signature-1 {
                algo = "sha256,rsa2048";
                key-name-hint = "dev";
                sign-images = "kernel", "fdt";
            };
        };
    };
};
```

Build and sign:

```bash
# Build the FIT image (unsigned)
mkimage -f kernel.its kernel.itb

# Sign the FIT image with your private key
# -k specifies the key directory, -r adds the public key to the image
mkimage -F -k ./keys -r kernel.itb

# Verify the signature locally
mkimage -l kernel.itb
# Look for: "Signature verified OK" in the output
```

### 4. Embed public key into U-Boot device tree

Create `pubkey.dtsi`:

```dts
/ {
    signature {
        key-dev {
            required = "conf";  # Required for configuration nodes
            algo = "sha256,rsa2048";
            key-name-hint = "dev";
            # Include the public key binary
            key-dev = /incbin/("./dev.pubkey.der");
        };
    };
};
```

Compile into U-Boot:

```bash
# In U-Boot source tree
cat arch/arm/dts/myboard.dts pubkey.dtsi > myboard_with_key.dts
make myboard_with_key.dtb
# Then rebuild U-Boot with this DTB
```

## Common Pitfalls & Gotchas

1. **Hash algorithm mismatch between signing and verification.** If you sign with `sha256,rsa2048` but U-Boot expects `sha1,rsa2048`, verification silently fails. Always check `CONFIG_FIT_HASH_ALGO` matches your signing parameters. The error message is cryptic—usually just "Bad Data CRC" or a hang.

2. **Key-name-hint must match exactly.** The `key-name-hint` in your FIT image's signature node must match the `key-name-hint` in the U-Boot device tree. Case-sensitive. I've wasted hours because of a typo between "dev" and "DEV". U-Boot won't tell you it couldn't find the key—it just fails verification.

3. **SPL vs U-Boot proper key storage.** If you enable `CONFIG_SPL_FIT_SIGNATURE`, the public key must be embedded in the SPL binary, not U-Boot proper. This means rebuilding SPL with the key. Many engineers forget this and wonder why SPL-stage verification fails while U-Boot-stage works fine.

4. **FIT image size limits.** Some older U-Boot versions have a hard limit on FIT image size (often 64MB). If your kernel + DTB + initramfs exceeds this, the image won't load. Check `CONFIG_FIT_MAX_SIZE` in your config.

## Try It Yourself

1. **Generate a key pair and sign a minimal FIT image.** Use a simple kernel and DTB from your build system. Verify the signature with `mkimage -l` and confirm it shows "Signature verified OK". Then corrupt one byte in the kernel section with `dd` and watch U-Boot refuse to boot.

2. **Add Verified Boot to an existing board config.** Take any ARM board you have (Raspberry Pi, BeagleBone, i.MX). Enable `CONFIG_FIT_SIGNATURE` and `CONFIG_FIT_SIGNATURE_STRICT` in its defconfig. Rebuild U-Boot and test that unsigned FIT images are rejected.

3. **Implement rollback protection.** Add a version number to your FIT image configuration node. In U-Boot, store the last-booted version in an environment variable (e.g., `fit_version`). Before booting, compare versions and refuse to boot an older image. This prevents downgrade attacks.

## Next Up

Tomorrow: **FIT Images: Kernel + DTB + Initramfs Signing** — We'll dive deeper into multi-component FIT images, signing individual payloads versus configurations, and how to handle initramfs in the verified boot flow.
