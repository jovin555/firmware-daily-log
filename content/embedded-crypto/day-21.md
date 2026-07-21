---
title: "Day 21: PSA Crypto API: Vendor-Neutral Crypto Abstraction"
date: 2026-07-21
tags: ["til", "embedded-crypto", "psa-crypto"]
---

## What I Explored Today

Today I dug into the Platform Security Architecture (PSA) Crypto API, ARM's vendor-neutral abstraction layer for cryptographic operations on embedded devices. The PSA Crypto specification defines a standard C API that works across hardware secure elements, TrustZone-M trusted firmware, software implementations (like Mbed TLS), and custom hardware accelerators. I focused on how to write portable crypto code that runs identically on an NXP LPC55S69 with its on-chip PUF-based crypto engine, an STM32L5 with hardware AES, and a plain Cortex-M4 using software-only Mbed TLS — all through the same `psa_*` function calls.

## The Core Concept

The PSA Crypto API solves a fundamental pain point in embedded systems: hardware crypto accelerators are powerful but completely vendor-locked. Every silicon vendor exposes their crypto block differently — NXP has the CASPER engine, ST has CRYP, Microchip has the CCL. Porting crypto code between them historically meant rewriting entire driver stacks.

PSA Crypto abstracts this by defining a set of key types, algorithms, and operation handles. The key insight is that the API treats keys as opaque objects (identified by `psa_key_id_t`) rather than raw byte buffers. This lets the underlying implementation decide where to store and process the key — in on-chip secure RAM, in a dedicated crypto co-processor, or in a TrustZone secure partition — without the application code knowing or caring.

The API is divided into three abstraction levels:
- **Key management**: `psa_import_key`, `psa_generate_key`, `psa_export_public_key`
- **One-shot operations**: `psa_hash_compute`, `psa_cipher_encrypt`, `psa_asymmetric_sign`
- **Multi-part operations**: `psa_hash_setup`, `psa_hash_update`, `psa_hash_finish` for streaming

Critically, the API enforces key usage policies at the API level. When you create a key, you specify `psa_key_policy_t` that restricts whether the key can be used for signing, encryption, or export. The implementation enforces these policies, even against the application itself.

## Key Commands / Configuration / Code

Here's a portable AES-GCM encryption example using PSA Crypto. This code compiles and runs identically on any PSA-compliant implementation:

```c
#include <psa/crypto.h>

// Application-level error handler
static void check_status(psa_status_t status, const char *op) {
    if (status != PSA_SUCCESS) {
        // In production: log, reset, or enter safe state
        while(1);
    }
}

void encrypt_payload(const uint8_t *plaintext, size_t plaintext_len,
                     uint8_t *ciphertext, size_t *ciphertext_len,
                     uint8_t *tag, size_t tag_size) {
    psa_status_t status;
    psa_key_id_t key_id;
    uint8_t iv[12];  // 96-bit IV for GCM

    // 1. Initialize the PSA Crypto subsystem
    //    This may power up hardware crypto, initialize TRNG, etc.
    status = psa_crypto_init();
    check_status(status, "psa_crypto_init");

    // 2. Define key policy: only AES-GCM encryption, never exportable
    psa_key_policy_t policy = PSA_KEY_POLICY_INIT;
    policy.usage = PSA_KEY_USAGE_ENCRYPT;
    policy.alg = PSA_ALG_GCM;

    // 3. Define key attributes (type, size, policy)
    psa_key_attributes_t attributes = PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_usage_flags(&attributes, policy.usage);
    psa_set_key_algorithm(&attributes, policy.alg);
    psa_set_key_type(&attributes, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attributes, 128);

    // 4. Import a 128-bit AES key
    //    The implementation stores this in the most secure location available
    uint8_t key_bytes[16] = {0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
                             0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c};
    status = psa_import_key(&attributes, key_bytes, sizeof(key_bytes), &key_id);
    check_status(status, "psa_import_key");

    // 5. Generate random IV using the platform's TRNG
    status = psa_generate_random(iv, sizeof(iv));
    check_status(status, "psa_generate_random");

    // 6. Perform AES-GCM encryption in a single call
    //    Output: ciphertext + authentication tag appended
    size_t output_len;
    status = psa_aead_encrypt(key_id, PSA_ALG_GCM,
                              iv, sizeof(iv),          // nonce
                              NULL, 0,                 // additional data (none)
                              plaintext, plaintext_len, // input
                              ciphertext, &output_len,  // output buffer
                              *ciphertext_len);
    check_status(status, "psa_aead_encrypt");
    *ciphertext_len = output_len;

    // 7. Extract the tag (last 16 bytes of output for GCM)
    memcpy(tag, ciphertext + plaintext_len, tag_size);

    // 8. Clean up: destroy the key from secure storage
    psa_destroy_key(key_id);
}
```

**Configuration note**: To select the backend, you typically set compile-time defines. For Mbed TLS software:
```makefile
# In CMake or Makefile
-DMBEDTLS_PSA_CRYPTO_C=1
```

For hardware-backed on NXP LPC55S69:
```makefile
# Enables the PUF-based key store and hardware AES
-DPSA_CRYPTO_ACCELERATOR_NXP=1
-DMBEDTLS_PSA_CRYPTO_C=1
```

## Common Pitfalls & Gotchas

1. **Key lifetime confusion**: The `psa_key_lifetime_t` parameter defaults to `PSA_KEY_LIFETIME_VOLATILE` (key exists only while the application runs). If you want persistent keys that survive reset, you must explicitly set `PSA_KEY_LIFETIME_PERSISTENT` and provide a unique key ID. Forgetting this means keys vanish on reboot, which breaks secure boot chains or session resumption.

2. **Buffer size assumptions**: `psa_aead_encrypt` and `psa_asymmetric_sign` write the output directly into your buffer. The required output size for asymmetric operations (like ECDSA signatures) varies by curve and implementation. Always query the expected size with `psa_sign_hash` using `NULL` output first, or use `PSA_SIGN_OUTPUT_SIZE(curve_bits, hash_bits)` macro. Under-allocating causes `PSA_ERROR_BUFFER_TOO_SMALL`.

3. **Hardware accelerator initialization order**: `psa_crypto_init()` must be called before any other PSA function. On hardware-backed implementations, this often involves powering up the crypto block, which may fail if the clock is not configured. I've seen this on STM32L5 where the hardware AES requires the AHB clock to be enabled before `psa_crypto_init()`. Check your BSP initialization order.

## Try It Yourself

1. **Port your existing AES-CBC code**: Take an existing project that uses direct hardware register writes for AES-CBC encryption. Replace it with `psa_cipher_encrypt()` using `PSA_ALG_CBC_PKCS7`. Verify the ciphertext matches your original implementation.

2. **Key policy enforcement test**: Create a key with `PSA_KEY_USAGE_ENCRYPT` only, then attempt `psa_asymmetric_sign()` with that key. Confirm the API returns `PSA_ERROR_NOT_PERMITTED`. This validates that your implementation enforces policies correctly.

3. **Multi-platform build**: Set up two build configurations for your project — one using Mbed TLS software backend, one using your MCU's hardware accelerator (e.g., `-DMBEDTLS_PSA_CRYPTO_C=1` vs vendor-specific flags). Run the same test vector through both and compare execution time using a GPIO toggle.

## Next Up

Tomorrow: **Side-Channel Resistance: Constant-Time Crypto Implementations** — how to write AES and RSA code that doesn't leak secrets through timing variations, cache behavior, or power analysis.
