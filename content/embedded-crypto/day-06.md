---
title: "Day 06: HMAC: Message Authentication Without Public Keys"
date: 2026-07-06
tags: ["til", "embedded-crypto", "hmac", "mac"]
---

## What I Explored Today

Today I dove into HMAC (Hash-based Message Authentication Code), the workhorse of symmetric authentication in embedded systems. I've used it before in TLS handshakes and firmware update verification, but I wanted to understand exactly why it's designed the way it is and how to implement it correctly on constrained devices. The key insight: HMAC lets two parties with a shared secret verify that a message hasn't been tampered with, without needing expensive asymmetric cryptography.

## The Core Concept

The fundamental problem HMAC solves is simple: how do you know a message came from who you think it did, and that it wasn't modified in transit? Digital signatures (RSA, ECDSA) solve this with public-key cryptography, but they're computationally expensive and require certificate infrastructure. For many embedded scenarios—sensor-to-gateway communication, bootloader authentication, secure firmware updates—you already have a shared secret (provisioned at manufacturing time). HMAC leverages that secret with a hash function to produce a fixed-size authentication tag.

Why not just hash the message with the secret prepended? Because naive constructions like `H(secret || message)` are vulnerable to length-extension attacks on Merkle-Damgård hash functions (SHA-256, SHA-1). An attacker who knows `H(secret || message)` can compute `H(secret || message || padding || extra_data)` without knowing the secret. HMAC's two-pass construction—`H((key ⊕ opad) || H((key ⊕ ipad) || message))`—defeats this attack by using the key in both the inner and outer hash.

The beauty of HMAC is its provable security: if the underlying hash function is collision-resistant, HMAC is a secure MAC. This means you can swap hash functions (SHA-256, SHA-3, BLAKE2) without changing the HMAC construction itself.

## Key Commands / Configuration / Code

### HMAC with OpenSSL (command line)
```bash
# Generate an HMAC-SHA256 tag for a firmware blob
echo -n "my_secret_key_32bytes" | \
  openssl dgst -sha256 -hmac "$(cat /dev/urandom | head -c 32 | base64)" \
  -binary firmware.bin > firmware.hmac

# Verify (recompute and compare)
openssl dgst -sha256 -hmac "$(cat secret.key)" firmware.bin
# Output: HMAC-SHA256(firmware.bin)= <expected_hex>
```

### HMAC in C using mbedTLS (common on ARM Cortex-M)
```c
#include <mbedtls/md.h>

// Returns 0 on success, nonzero on failure
int compute_hmac_sha256(const uint8_t *key, size_t key_len,
                        const uint8_t *msg, size_t msg_len,
                        uint8_t output[32]) {
    mbedtls_md_context_t ctx;
    const mbedtls_md_info_t *md_info;

    mbedtls_md_init(&ctx);
    md_info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    
    // Step 1: Set up HMAC context with key
    if (mbedtls_md_setup(&ctx, md_info, 1) != 0) { // 1 = use HMAC
        mbedtls_md_free(&ctx);
        return -1;
    }
    mbedtls_md_hmac_starts(&ctx, key, key_len);
    
    // Step 2: Feed message in chunks (useful for streaming)
    mbedtls_md_hmac_update(&ctx, msg, msg_len);
    
    // Step 3: Finalize and get tag
    mbedtls_md_hmac_finish(&ctx, output);
    
    mbedtls_md_free(&ctx);
    return 0;
}
```

### Constant-time comparison (critical for embedded)
```c
// DON'T use memcmp() for HMAC verification — it's not constant-time
// and leaks timing information about where the tag differs.
int constant_time_memcmp(const uint8_t *a, const uint8_t *b, size_t len) {
    uint8_t diff = 0;
    for (size_t i = 0; i < len; i++) {
        diff |= a[i] ^ b[i];
    }
    return diff; // 0 if equal, nonzero otherwise
}
```

## Common Pitfalls & Gotchas

**1. Key reuse across different domains.** I've seen designs where the same HMAC key is used for both message authentication and encryption key derivation. This is dangerous because an attacker who sees many HMAC tags can potentially recover information about the key. Always use separate keys for authentication (HMAC) and encryption (AES). Derive them from a master key using a KDF like HKDF.

**2. Using weak hash functions.** HMAC-MD5 and HMAC-SHA1 are still technically secure as MACs (no practical collision attacks on the HMAC construction itself), but many standards bodies have deprecated them. On embedded systems with hardware SHA-256 accelerators, there's no reason to use anything weaker. For new designs, prefer HMAC-SHA256 or HMAC-SHA3-256.

**3. Variable-length key handling.** HMAC can accept any key length, but if your key is longer than the hash block size (64 bytes for SHA-256), it gets hashed first. This means a 128-byte key is effectively reduced to 32 bytes. Worse, if you accidentally pass a key that's exactly 64 bytes, it's used directly—creating a subtle inconsistency. Always use keys that are exactly the hash output length (32 bytes for SHA-256) to avoid this ambiguity.

## Try It Yourself

1. **Implement HMAC verification on a microcontroller.** Using mbedTLS or TinyCrypt, write a function that takes a key, message, and expected HMAC tag, and returns success/failure. Ensure your comparison is constant-time. Test with both correct and tampered messages.

2. **Measure the performance cost.** On your target hardware (e.g., STM32F4, ESP32), time how long HMAC-SHA256 takes for a 1KB message. Compare it to a raw SHA-256 hash. The overhead should be roughly 2× the hash time. If it's significantly more, check if you're re-initializing the HMAC context unnecessarily.

3. **Break a naive MAC.** Write a Python script that demonstrates the length-extension attack on `SHA256(secret || message)`. Then show that HMAC-SHA256 is immune to the same attack. This will cement why HMAC's two-pass construction is necessary.

## Next Up

Tomorrow we leave the symmetric world and enter asymmetric cryptography: **RSA Fundamentals & Key Sizes**. We'll cover how prime factorization enables public-key encryption, why 2048-bit RSA is the minimum for embedded systems, and the performance tradeoffs you must consider when implementing RSA on resource-constrained devices.
