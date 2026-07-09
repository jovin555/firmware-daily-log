---
title: "Day 09: Digital Signatures: Signing & Verifying Firmware Images"
date: 2026-07-09
tags: ["til", "embedded-crypto", "digital-signature"]
---

## What I Explored Today

Today I integrated digital signature verification into a firmware update pipeline for an STM32H7 target. The goal: ensure that only firmware signed with a trusted private key can be flashed to the device. I used ECDSA with the NIST P-256 curve (secp256r1), implemented via the Mbed TLS library. The signing happens on a build server (OpenSSL CLI), and the verification runs on the microcontroller during bootloader execution. This is the standard pattern for secure boot in production embedded systems.

## The Core Concept

A digital signature provides three guarantees: authenticity (the firmware came from a trusted source), integrity (it hasn't been modified in transit), and non-repudiation (the signer cannot deny signing it). Unlike a MAC (Message Authentication Code), which uses a shared secret, a digital signature uses asymmetric cryptography: a private key to sign, a public key to verify.

Why not just use a hash? A hash alone tells you the firmware hasn't changed, but it doesn't tell you *who* produced it. An attacker could replace both the firmware and its hash. With a signature, the public key is embedded in the bootloader (or stored in OTP fuses), so only the holder of the corresponding private key can produce a valid signature.

For constrained devices, ECDSA is preferred over RSA because ECDSA signatures are shorter (64 bytes for P-256 vs. 256 bytes for RSA-2048) and verification is faster with smaller key sizes. The trade-off: ECDSA requires a cryptographically secure random number generator during signing (but not during verification, which is critical for embedded targets).

## Key Commands / Configuration / Code

### Step 1: Generate the key pair (build server)

```bash
# Generate ECDSA P-256 private key
openssl ecparam -genkey -name prime256v1 -out firmware_priv.pem

# Extract the public key in raw uncompressed format (65 bytes: 0x04 + 32-byte X + 32-byte Y)
openssl ec -in firmware_priv.pem -pubout -outform DER | tail -c 65 > firmware_pub.raw

# Display the public key hex for embedding
xxd -p firmware_pub.raw
```

### Step 2: Sign the firmware image (build server)

```bash
# Hash the firmware binary with SHA-256, then sign with ECDSA
openssl dgst -sha256 -sign firmware_priv.pem -out firmware.sig firmware.bin

# The signature is DER-encoded. For embedded use, extract raw r||s (64 bytes)
openssl asn1parse -in firmware.sig -inform DER
# Then use a script to extract the 32-byte r and 32-byte s values
```

Alternatively, use a single command to produce raw 64-byte signature:

```bash
# Hash and sign, output raw 64-byte signature
openssl pkeyutl -sign -inkey firmware_priv.pem -in <(openssl dgst -sha256 -binary firmware.bin) -out firmware.sig.raw
```

### Step 3: Embed the public key in the bootloader (C code)

```c
// firmware_pub_key.h
#ifndef FIRMWARE_PUB_KEY_H
#define FIRMWARE_PUB_KEY_H

#include <stdint.h>

// Uncompressed P-256 public key (0x04 || X || Y)
static const uint8_t firmware_pub_key[65] = {
    0x04,
    0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0,  // X coordinate (32 bytes)
    0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
    0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff, 0x00,
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0xab, 0xcd, 0xef, 0x01, 0x23, 0x45, 0x67, 0x89,  // Y coordinate (32 bytes)
    0xfe, 0xdc, 0xba, 0x98, 0x76, 0x54, 0x32, 0x10,
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
    0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff
};

#endif // FIRMWARE_PUB_KEY_H
```

### Step 4: Verify signature in the bootloader (Mbed TLS)

```c
#include <mbedtls/ecdsa.h>
#include <mbedtls/sha256.h>
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/entropy.h>
#include "firmware_pub_key.h"

int verify_firmware(const uint8_t *fw_image, size_t fw_size,
                    const uint8_t *signature) {
    int ret;
    mbedtls_ecdsa_context ctx;
    mbedtls_sha256_context sha_ctx;
    mbedtls_ctr_drbg_context ctr_drbg;
    mbedtls_entropy_context entropy;
    uint8_t hash[32];

    // 1. Initialize RNG (needed for key parsing, not for verification itself)
    mbedtls_ctr_drbg_init(&ctr_drbg);
    mbedtls_entropy_init(&entropy);
    mbedtls_ctr_drbg_seed(&ctr_drbg, mbedtls_entropy_func, &entropy, NULL, 0);

    // 2. Compute SHA-256 hash of firmware
    mbedtls_sha256_init(&sha_ctx);
    mbedtls_sha256_starts(&sha_ctx, 0);  // 0 = SHA-256, not SHA-224
    mbedtls_sha256_update(&sha_ctx, fw_image, fw_size);
    mbedtls_sha256_finish(&sha_ctx, hash);
    mbedtls_sha256_free(&sha_ctx);

    // 3. Load the public key
    mbedtls_ecdsa_init(&ctx);
    ret = mbedtls_ecp_read_key(MBEDTLS_ECP_DP_SECP256R1, &ctx.grp,
                                &ctx.Q, firmware_pub_key, sizeof(firmware_pub_key));
    if (ret != 0) goto cleanup;

    // 4. Verify the signature (raw 64-byte r||s format)
    ret = mbedtls_ecdsa_read_signature(&ctx, hash, sizeof(hash),
                                        signature, 64);
    // ret == 0 means valid signature

cleanup:
    mbedtls_ecdsa_free(&ctx);
    mbedtls_ctr_drbg_free(&ctr_drbg);
    mbedtls_entropy_free(&entropy);
    return ret;
}
```

## Common Pitfalls & Gotchas

1. **Endianness mismatch between OpenSSL and Mbed TLS.** OpenSSL outputs big-endian coordinates by default. Mbed TLS expects big-endian as well, but if you use a different library (e.g., MicroECC), it may expect little-endian. Always verify with a known test vector before trusting the first signature.

2. **Signature malleability.** ECDSA signatures are not unique — for a given message and key, there are two valid signatures (r, s) and (r, n-s). Some libraries normalize to the lower-s form. If your signing and verification libraries disagree on normalization, verification will fail. Mbed TLS accepts both forms by default, but be aware if you use a stricter parser.

3. **Public key storage in OTP/flash.** If the public key is stored in flash, an attacker with physical access could modify it. For production, store the public key hash in OTP fuses and verify the key against that hash at boot. Better yet, use a hardware security module (HSM) or secure element to store the verification key.

## Try It Yourself

1. **Generate a P-256 key pair and sign a test binary.** Use the OpenSSL commands above. Then write a small Python script using `cryptography` library to verify the signature. Confirm that modifying even one byte of the binary causes verification to fail.

2. **Port the Mbed TLS verification code to your target MCU.** Set up a minimal bootloader that reads a firmware image from external flash, computes SHA-256, and verifies the ECDSA signature. Measure the verification time (expect ~50-200ms on a Cortex-M4 at 200 MHz).

3. **Implement a rollback protection mechanism.** Embed a version number in the firmware header, and include it in the signed data (hash the header + firmware body). In the bootloader, check that the new version is greater than the current version before accepting the update.

## Next Up

Tomorrow: **Key Exchange: Diffie-Hellman & ECDH in Constrained Devices** — how two devices with no prior shared secret can establish a secure channel over an untrusted network, and why ECDH is the preferred choice for IoT sensor networks.
