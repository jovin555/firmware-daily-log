---
title: "Day 08: MCUboot Image Signing: Keys, imgtool & Verification"
date: 2026-06-22
tags: ["til", "trustzone", "mcuboot", "signing", "imgtool"]
---

## What I Explored Today

Today I went deep into MCUboot's image signing pipeline — the cryptographic backbone that ensures only authorized firmware runs on the target. I generated RSA-3072 and ECDSA-P256 key pairs, signed a Zephyr application binary with `imgtool`, and walked through the boot-time verification flow in the MCUboot source. The goal was to understand exactly how a raw `.bin` becomes a trusted, signed, and versioned image that MCUboot will accept.

## The Core Concept

MCUboot uses a **chain of trust** rooted in a public key embedded at build time. The private key never leaves the developer's machine. When you sign an image, `imgtool` appends a **trailer** containing:

- The **image hash** (SHA-256 of the firmware)
- The **digital signature** (RSA or ECDSA, over the hash)
- **Metadata** (version, boot flags, slot info)

At boot, MCUboot's first-stage loader:

1. Reads the image header and trailer from the primary slot
2. Computes the SHA-256 hash of the image data
3. Verifies the signature using the embedded public key
4. Only boots if verification passes

This prevents execution of tampered or unsigned firmware. The key insight: **signing is not encryption**. The image remains readable; the signature only proves integrity and authenticity.

## Key Commands / Configuration / Code

### 1. Generating Keys with imgtool

`imgtool` is Python-based, installed via `pip`:

```bash
# Install imgtool (part of mcuboot repo)
pip install --user imgtool

# Generate RSA-3072 key pair (private + public PEM)
imgtool keygen -k signing-rsa-3072.pem -t rsa-3072

# Generate ECDSA-P256 key pair (smaller, faster verification)
imgtool keygen -k signing-ecdsa-p256.pem -t ecdsa-p256

# Extract the public key in C header format for MCUboot
imgtool getpub -k signing-ecdsa-p256.pem > pubkey.h
```

The `pubkey.h` file contains a `const uint8_t` array that MCUboot compiles in. You must regenerate this header every time you change keys.

### 2. Signing a Firmware Image

```bash
# Sign a Zephyr binary with version 1.2.3, slot size 0x80000
imgtool sign \
  --key signing-ecdsa-p256.pem \
  --version 1.2.3 \
  --header-size 0x200 \
  --align 8 \
  --slot-size 0x80000 \
  --pad-header \
  build/zephyr/zephyr.bin \
  signed_firmware.bin
```

Key flags explained:
- `--header-size`: Must match the image header size configured in MCUboot (usually 0x200)
- `--align`: Flash write alignment (8 for most modern MCUs)
- `--slot-size`: Size of each image slot (primary + secondary)
- `--pad-header`: Ensures the image starts at a flash-aligned offset after the header

### 3. Verification in MCUboot Source

The core verification logic lives in `boot/bootutil/src/image_validate.c`:

```c
// Simplified verification flow
int boot_image_validate(struct boot_loader_state *state, struct boot_status *bs) {
    struct image_header *hdr;
    uint32_t img_size;
    int rc;

    // 1. Read image header from flash
    hdr = (struct image_header *)boot_img_hdr(state, 0);

    // 2. Get total image size (header + payload + trailer)
    img_size = boot_img_size(hdr);

    // 3. Compute SHA-256 hash of the image payload
    rc = bootutil_img_hash(hdr, state, img_size, hash);
    if (rc != 0) return -1;

    // 4. Verify signature using embedded public key
    rc = bootutil_verify_sig(hash, sizeof(hash), 
                             &hdr->ih_hash_size, 
                             &bootutil_keys[0]);  // Key from pubkey.h
    if (rc != 0) {
        BOOT_LOG_ERR("Image signature verification FAILED");
        return -1;
    }

    BOOT_LOG_INF("Image signature verified OK");
    return 0;
}
```

The public key array `bootutil_keys[]` is auto-generated from `pubkey.h` during the MCUboot build. You configure which key index to use via `MCUBOOT_HW_KEY` or `BOOTUTIL_PUBLIC_KEY` Kconfig options.

## Common Pitfalls & Gotchas

### 1. Key Mismatch Between Build and Signing
The most frequent failure: you compile MCUboot with one public key, then sign the image with a different private key. The bootloader will reject the image silently (or log "Signature verification FAILED"). Always verify that `pubkey.h` was regenerated after key changes.

### 2. Header Size and Alignment Mismatch
If `--header-size` in `imgtool sign` doesn't match `CONFIG_BOOT_IMAGE_HEADER_SIZE` in MCUboot, the bootloader will misparse the image. Symptoms: boot loops, magic number errors, or corrupted image detection. Double-check both values match exactly.

### 3. Slot Size Too Small for Trailer
MCUboot requires space for the trailer (signature + metadata) at the end of each slot. If `--slot-size` is exactly the image size, there's no room for the trailer. The rule: `slot_size >= image_size + trailer_size`. A safe heuristic is to set slot size 4-8 KB larger than the maximum expected image.

## Try It Yourself

1. **Generate a key pair and sign a test binary**: Use `imgtool keygen` to create an ECDSA-P256 key, then sign any small `.bin` file (even a 1 KB dummy). Verify the output file is larger than the input (trailer appended).

2. **Inspect the signed image trailer**: Run `hexdump -C signed_firmware.bin | tail -20` to see the magic number (`0x6907`), image version, and signature bytes. Cross-reference with MCUboot's `image_trailer` struct definition.

3. **Simulate a tampered image**: Modify one byte in the signed binary (e.g., `printf '\x00' | dd of=signed_firmware.bin bs=1 seek=100 conv=notrunc`), then attempt to boot it on your dev board. Observe the bootloader log rejecting the image.

## Next Up

Tomorrow: **MCUboot DFU: USB, BLE & Serial Upgrade Modes** — we'll explore how to deliver those signed images to the device over real-world transports, including the MCUboot serial recovery protocol, USB DFU class, and BLE OTA with the SMP (Simple Management Protocol) server.
