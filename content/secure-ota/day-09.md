---
title: "Day 09: Update Verification: Signature Checks Before Boot Commit"
date: 2026-07-09
tags: ["til", "secure-ota", "signature-verification"]
---

## What I Explored Today

Today I wired up the cryptographic signature verification step that runs *after* the update image lands on the secondary slot but *before* the bootloader commits to swapping it into the active slot. This is the gatekeeper that prevents a compromised or corrupted image from ever executing. I implemented an ECDSA P-256 signature check using `mbedTLS` on a Zephyr-based MCU, validating the image header's signature against a public key baked into the bootloader's read-only region. The key insight: verification must happen in the bootloader context, not in the running firmware, because once you boot into the new image, you've already lost trust.

## The Core Concept

Signature verification is not about preventing an attacker from writing to flash—they can always do that if they have physical access or a compromised update server. It's about ensuring that only firmware signed by a trusted private key can execute. The bootloader is the root of trust: it holds the public key, it runs first, and it refuses to boot an unsigned or mismatched image.

The critical architectural decision is *when* to verify. Many engineers make the mistake of verifying the signature inside the running application (e.g., after a reboot, in the main firmware). That's too late—the bootloader has already committed to the slot swap. If the signature check fails there, you're already running untrusted code. The correct flow is:

1. Bootloader loads the candidate image header from the secondary slot.
2. Bootloader computes a hash of the image payload (not the header, which includes the signature itself).
3. Bootloader uses the public key to verify the signature over that hash.
4. Only if verification passes does the bootloader mark the slot as "ready to boot" and perform the swap.

This is sometimes called "verify before commit" and is the pattern used by MCUboot, TF-M, and most production secure boot implementations.

## Key Commands / Configuration / Code

Below is the core verification routine I integrated into the bootloader's slot validation path. This uses `mbedTLS` 3.x with ECDSA P-256 (secp256r1).

```c
// boot_verify.c — called from bootloader's main() before slot swap
#include <mbedtls/pk.h>
#include <mbedtls/sha256.h>
#include <mbedtls/ecdsa.h>

// Public key baked into bootloader .rodata (generated offline)
// This is a DER-encoded SubjectPublicKeyInfo for ECDSA P-256
static const uint8_t boot_pubkey_der[] = {
    0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01,
    0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07, 0x03, 0x42, 0x00,
    0x04, /* ... 64 bytes of uncompressed point ... */
};

int verify_image_signature(const struct image_header *hdr,
                           const uint8_t *payload,
                           size_t payload_len)
{
    mbedtls_pk_context pk;
    mbedtls_sha256_context sha;
    uint8_t hash[32];
    int ret;

    // 1. Parse the public key
    mbedtls_pk_init(&pk);
    ret = mbedtls_pk_parse_public_key(&pk, boot_pubkey_der, sizeof(boot_pubkey_der));
    if (ret != 0) {
        // Bootloader panic — public key itself is corrupted
        return -1;
    }

    // 2. Hash the payload (NOT the header, which contains the signature)
    mbedtls_sha256_init(&sha);
    mbedtls_sha256_starts(&sha, 0); // SHA-256, not SHA-224
    mbedtls_sha256_update(&sha, payload, payload_len);
    mbedtls_sha256_finish(&sha, hash);
    mbedtls_sha256_free(&sha);

    // 3. Verify ECDSA signature (r||s, 64 bytes total)
    //    Signature is stored at a fixed offset in the image header
    ret = mbedtls_pk_verify(&pk, MBEDTLS_MD_SHA256,
                            hash, sizeof(hash),
                            hdr->signature, sizeof(hdr->signature));
    mbedtls_pk_free(&pk);

    return (ret == 0) ? 0 : -1;
}
```

**CMakeLists.txt snippet** (Zephyr module integration):
```cmake
# Ensure mbedTLS is compiled with ECDSA support
set(CONFIG_MBEDTLS_BUILD_TYPE "minimal" CACHE STRING "")
set(CONFIG_MBEDTLS_PK_PARSE_C y)
set(CONFIG_MBEDTLS_ECDSA_C y)
set(CONFIG_MBEDTLS_ECP_DP_SECP256R1_ENABLED y)
```

**Key generation command** (run on host, offline):
```bash
# Generate ECDSA P-256 private key
openssl ecparam -genkey -name prime256v1 -out firmware_priv.pem

# Extract public key in DER format
openssl ec -in firmware_priv.pem -pubout -outform DER -out firmware_pub.der

# Convert to C array for embedding (use xxd or a custom script)
xxd -i firmware_pub.der > firmware_pub_key.c
```

## Common Pitfalls & Gotchas

1. **Hashing the header along with the payload.** The signature is part of the header. If you hash the entire header, you're including the signature itself in the hash input, creating a circular dependency. Always hash only the payload (or a header field that explicitly excludes the signature bytes). MCUboot handles this by defining a `image_header` struct with a `sig_len` field and a variable-length signature at the end.

2. **Using the wrong hash algorithm in the verify call.** `mbedtls_pk_verify` takes a `md_alg` parameter. If you hash with SHA-256 but pass `MBEDTLS_MD_SHA1`, the verification will fail silently (or worse, succeed with a crafted signature). Always double-check that the hash algorithm used during signing matches the one in the bootloader. I've burned two hours on this mismatch.

3. **Public key stored in writable flash.** If the bootloader's public key is in a region that can be modified (e.g., a config partition), an attacker can overwrite it with their own public key and sign arbitrary firmware. The public key must reside in read-only memory—typically the bootloader's own flash region, which is locked via hardware protection bits (e.g., STM32 RDP Level 2, NXP HAB, or MCU-specific OTP fuses).

## Try It Yourself

1. **Generate a test key pair and sign a dummy image.** Use `openssl` to create an ECDSA P-256 key, then write a small Python script that hashes a 1 KB binary and signs it with `cryptography` library. Verify the signature using `mbedtls_pk_verify` on your dev board.

2. **Inject a corrupted signature and observe the bootloader's behavior.** Modify the signature bytes in flash (via a debugger or a small test application) and confirm that the bootloader refuses to boot the slot. Log the error code from `mbedtls_pk_verify` to distinguish between "invalid signature" and "key parse failure."

3. **Measure the verification time.** Add a GPIO toggle around the `verify_image_signature()` call and capture it with a logic analyzer. On a Cortex-M4 at 120 MHz, expect ~50–150 ms for ECDSA P-256 verification. If it's over 500 ms, check if you're accidentally using software math instead of the hardware crypto accelerator.

## Next Up

Tomorrow: **Boot Confirmation & Health Checks: Marking an Update "Good"** — we'll implement the "boot OK" flag that tells the bootloader the new firmware actually runs correctly, and we'll handle the rollback logic when the image fails its health check within the first N seconds.
