---
title: "Day 17: FIT Images: Kernel + DTB + Initramfs Signing"
date: 2026-06-29
tags: ["til", "trustzone", "fit-image", "signing"]
---

## What I Explored Today

Today I dug into the practical mechanics of signing Flattened Image Tree (FIT) images for a verified boot chain. While U-Boot's verified boot has been around for years, the exact workflow for signing a combined kernel + device tree + initramfs payload—and validating it in a TrustZone-secured environment—is where most engineers hit friction. I walked through the full `mkimage` signing pipeline, hash tree generation, and the public key injection into U-Boot's device tree, then validated the chain on a i.MX8M Plus board with OP-TEE handling the signature verification.

## The Core Concept

FIT images replace the old `uImage` + separate DTB approach with a single container that holds multiple binaries, each with its own hash and optional signature. The signing model works like this: you create an image tree source (`.its`) that describes the kernel, DTB, and initramfs as sub-images, then `mkimage` generates a binary FIT (`.itb`) with hash values for each component. When you sign, you compute a signature over the entire configuration node (which includes pointers to the sub-images and their hashes), preventing any component from being swapped or modified without detection.

The critical insight is that U-Boot's verified boot doesn't sign the raw binaries—it signs the *configuration*. This means an attacker can't replace the kernel with a different version that still passes hash checks, because the configuration signature binds the kernel hash, DTB hash, and initramfs hash together. In a TrustZone context, the signature verification can be delegated to a secure world application via OP-TEE, keeping the public key and verification logic out of the normal world entirely.

## Key Commands / Configuration / Code

### 1. Creating the Image Tree Source (kernel_fdt.its)

```dts
/dts-v1/;

/ {
    description = "Signed kernel + DTB + initramfs";
    #address-cells = <1>;

    images {
        kernel@1 {
            description = "Linux kernel";
            data = /incbin/("./Image");
            type = "kernel";
            arch = "arm64";
            os = "linux";
            compression = "none";
            load = <0x40480000>;
            entry = <0x40480000>;
            hash@1 {
                algo = "sha256";
            };
        };
        fdt@1 {
            description = "Device tree";
            data = /incbin/("./board.dtb");
            type = "flat_dt";
            arch = "arm64";
            compression = "none";
            hash@1 {
                algo = "sha256";
            };
        };
        ramdisk@1 {
            description = "Initramfs";
            data = /incbin/("./initramfs.cpio.gz");
            type = "ramdisk";
            arch = "arm64";
            os = "linux";
            compression = "gzip";
            hash@1 {
                algo = "sha256";
            };
        };
    };

    configurations {
        default = "config@1";
        config@1 {
            description = "Boot configuration";
            kernel = "kernel@1";
            fdt = "fdt@1";
            ramdisk = "ramdisk@1";
            signature@1 {
                algo = "sha256,rsa2048";
                key-name-hint = "dev-key";
                sign-images = "kernel", "fdt", "ramdisk";
            };
        };
    };
};
```

### 2. Generating Keys and Signing the FIT

```bash
# Generate RSA key pair (private key + public key in DER format)
openssl genpkey -algorithm RSA -out dev-key.pem -pkeyopt rsa_keygen_bits:2048
openssl rsa -in dev-key.pem -pubout -out dev-key.pub

# Create the signed FIT image
mkimage -f kernel_fdt.its -k ./keys -r signed_fit.itb

# The -k flag points to directory containing dev-key.pem
# The -r flag tells mkimage to require signature verification
```

### 3. Injecting Public Key into U-Boot DTB

```bash
# Extract the public key in the format U-Boot expects
# This creates a .dtb with the public key node under /signature
mkimage -F -k ./keys -K u-boot.dtb -r signed_fit.itb

# Verify the key was injected
fdtget u-boot.dtb /signature key-dev-key
# Should output: rsa2040
```

### 4. U-Boot Verified Boot Configuration (board.cfg)

```c
// In board config header (e.g., include/configs/myboard.h)
#define CONFIG_FIT_SIGNATURE
#define CONFIG_FIT_VERBOSE          1
#define CONFIG_LEGACY_IMAGE_FORMAT  0   // Disable legacy uImage
#define CONFIG_IMAGE_FORMAT_ELF     0

// For OP-TEE-backed verification
#define CONFIG_FIT_SIGNATURE_OPTEE  1
#define CONFIG_OPTEE_TA_UUID        "a4c3d2e1-..."
```

### 5. Verification in U-Boot Shell

```bash
# Load FIT image from storage
load mmc 2:1 0x42000000 signed_fit.itb

# Verify and boot (U-Boot checks signature automatically)
bootm 0x42000000#config@1

# Manual signature check
fdt addr 0x42000000
fdt list /configurations/config@1/signature@1
```

## Common Pitfalls & Gotchas

**1. Hash algorithm mismatch between .its and key generation.** If your `.its` specifies `sha256` for the hash but you generate an RSA key with a different digest algorithm (e.g., SHA-1), `mkimage` will silently produce a signed image that fails verification at boot. Always use `sha256,rsa2048` consistently in both the signature node and the key generation command.

**2. Forgetting the `-r` flag during mkimage.** Without `-r`, the signature is included but not required—U-Boot will boot the image even if the signature is missing or invalid. This defeats the entire purpose of verified boot. Always use `-r` in production builds, and test that boot fails when you corrupt a byte in the FIT.

**3. Public key injection into the wrong DTB.** If you have multiple device trees (one for U-Boot, one for Linux), injecting the key into the Linux DTB does nothing. The public key must be in the U-Boot control DTB (the one U-Boot uses for itself), typically `u-boot.dtb` or the one embedded in the U-Boot binary. Double-check with `fdtget` after injection.

## Try It Yourself

1. **Build a minimal FIT with two configurations.** Create an `.its` file with two `config@1` and `config@2` nodes, each pointing to the same kernel but different DTBs. Sign only `config@1`. Verify that U-Boot refuses to boot `config@2` (because it has no valid signature), and confirm the error message includes "bad hash" or "signature verification failed".

2. **Corrupt the initramfs inside a signed FIT.** Use `dd` to overwrite a single byte in the initramfs region of the `.itb` file (you can find the offset with `fdtget` or `hexdump`). Attempt to boot the corrupted image. Observe that U-Boot detects the hash mismatch before even attempting to load the ramdisk, and the boot fails gracefully.

3. **Switch to OP-TEE-backed verification.** If you have a board with OP-TEE (like i.MX8M or STM32MP1), compile U-Boot with `CONFIG_FIT_SIGNATURE_OPTEE` and load a Trusted Application that performs RSA verification. Compare boot time and security properties against the in-tree U-Boot verification. Measure the difference in boot latency (expect 50-200ms overhead for the secure world call).

## Next Up

Tomorrow we tackle **Key Management Infrastructure: HSM & PKCS#11**—how to move from plain file-based keys to hardware security modules, the PKCS#11 interface for signing FIT images without exposing private keys, and integrating with Yubico or Nitrokey HSM for production signing pipelines.
