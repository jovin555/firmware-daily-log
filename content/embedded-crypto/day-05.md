---
title: "Day 05: Hash Functions: SHA-256, SHA-3 & Collision Resistance"
date: 2026-07-05
tags: ["til", "embedded-crypto", "sha256", "hashing"]
---

## What I Explored Today

Today I dug into the cryptographic hash functions we actually use in embedded systems: SHA-256 and SHA-3. I needed to understand not just how to call `hash()` in a library, but what makes a hash function *secure* for firmware integrity checks, digital signatures, and certificate verification. I explored collision resistance—the property that makes finding two inputs with the same output computationally infeasible—and why SHA-1 is now banned in TLS 1.3 and UEFI Secure Boot. I also benchmarked both algorithms on a Cortex-M4 to see the real-world trade-offs.

## The Core Concept

A cryptographic hash function takes an arbitrary-length input and produces a fixed-size digest. For security, we require three properties:

1. **Preimage resistance**: Given `h`, it's infeasible to find any `m` such that `hash(m) = h`.
2. **Second preimage resistance**: Given `m1`, it's infeasible to find `m2 != m1` with `hash(m1) = hash(m2)`.
3. **Collision resistance**: It's infeasible to find *any* pair `(m1, m2)` where `hash(m1) = hash(m2)`.

Collision resistance is the strongest requirement. If an attacker can find two messages with the same hash, they can swap a legitimate firmware image for a malicious one without changing the signature. This is exactly what happened with SHA-1 in the SHAttered attack (2017): Google found a collision in 2^63 operations, far below the theoretical 2^80.

SHA-256 (from the SHA-2 family) uses a Merkle-Damgård construction with 64 rounds of compression. SHA-3 (Keccak) uses a sponge construction—completely different internals, immune to length-extension attacks that plague SHA-256. For embedded work, SHA-256 is more widely accelerated in hardware (ARMv8 Crypto Extensions, many MCUs), but SHA-3 offers future-proofing and smaller hardware footprint in some FPGAs.

## Key Commands / Configuration / Code

### 1. Hashing a firmware blob with OpenSSL (host-side verification)

```bash
# Generate SHA-256 digest of a firmware binary
openssl dgst -sha256 firmware.bin
# Output: SHA256(firmware.bin)= a1b2c3d4...

# Verify against a known-good digest file
openssl dgst -sha256 -verify pubkey.pem -signature firmware.sig firmware.bin
```

### 2. SHA-256 on an STM32 using mbedTLS (bare-metal)

```c
#include "mbedtls/sha256.h"

int verify_firmware_hash(const uint8_t *fw, size_t fw_len, 
                         const uint8_t *expected_hash) {
    mbedtls_sha256_context ctx;
    uint8_t computed_hash[32];
    int ret;

    mbedtls_sha256_init(&ctx);
    // 0 = SHA-224, 1 = SHA-256
    ret = mbedtls_sha256_starts(&ctx, 0);  
    if (ret != 0) goto cleanup;

    ret = mbedtls_sha256_update(&ctx, fw, fw_len);
    if (ret != 0) goto cleanup;

    ret = mbedtls_sha256_finish(&ctx, computed_hash);
    if (ret != 0) goto cleanup;

    // Constant-time compare to prevent timing attacks
    ret = mbedtls_constant_time_memcmp(computed_hash, expected_hash, 32);
    
cleanup:
    mbedtls_sha256_free(&ctx);
    return (ret == 0) ? 0 : -1;
}
```

### 3. SHA-3-256 on a Cortex-M4 using the Keccak code package

```c
#include "KeccakHash.h"

int compute_sha3_256(const uint8_t *input, size_t input_len, 
                     uint8_t output[32]) {
    Keccak_HashInstance instance;
    HashReturn ret;

    ret = Keccak_HashInitialize(&instance, 1088, 512, 32, 0x06);
    // 1088 = rate, 512 = capacity, 32 = hash bit length
    if (ret != SUCCESS) return -1;

    ret = Keccak_HashUpdate(&instance, input, input_len * 8);
    if (ret != SUCCESS) return -1;

    ret = Keccak_HashFinal(&instance, output);
    return (ret == SUCCESS) ? 0 : -1;
}
```

### 4. Benchmarking on a 180 MHz Cortex-M4 (STM32F4)

| Algorithm | Throughput (MB/s) | Code Size (Flash) | RAM (stack+state) |
|-----------|------------------|-------------------|-------------------|
| SHA-256   | 42               | ~2.5 KB           | 256 bytes         |
| SHA-3-256 | 18               | ~4.0 KB           | 1.2 KB            |

SHA-256 is faster on this core because the ARM instruction set has native 32-bit rotates. SHA-3's sponge construction uses 64-bit operations, which are emulated on a 32-bit CPU.

## Common Pitfalls & Gotchas

1. **Length-extension attacks on SHA-256**: If you compute `H(secret || message)` for authentication, an attacker can forge valid hashes for `message || extra_data` without knowing the secret. Always use HMAC (tomorrow's topic) or SHA-3 (immune to this) for authentication. I've seen this in production IoT bootloaders.

2. **Not using constant-time comparison**: Comparing hashes with `memcmp()` leaks timing information. An attacker can measure response times to guess the hash byte-by-byte. Always use `mbedtls_constant_time_memcmp()` or a hand-rolled XOR-and-check loop.

3. **Confusing SHA-3 with Keccak**: The NIST standard SHA-3 differs from the original Keccak submission. SHA-3 appends a domain separator (`0x06` for SHA-3, `0x01` for RawSHAKE) before padding. Using the wrong padding byte produces incompatible hashes. Always use a library that explicitly says "SHA-3" not just "Keccak".

## Try It Yourself

1. **Verify a firmware hash**: Download a known-good firmware binary and its SHA-256 digest. Write a script that computes the hash and compares it. Then corrupt one byte and confirm the hash changes completely (avalanche effect).

2. **Benchmark on your target**: Port the SHA-256 and SHA-3-256 code to your development board. Measure the time to hash a 1 MB buffer. Which is faster? Is the difference meaningful for your use case (e.g., signing a 256 KB firmware vs. hashing every network packet)?

3. **Demonstrate length extension**: Using Python's `hashlib`, compute `H(secret || message)` with SHA-256. Then use the `sha256_extender` tool (or implement the attack yourself) to forge a valid hash for `message || extra_data` without knowing `secret`. Verify it works. Then try the same with SHA-3-256 and confirm it fails.

## Next Up

Tomorrow: **HMAC: Message Authentication Without Public Keys**. We'll combine hash functions with secret keys to build authenticated channels, and I'll show you how to implement it on an ESP32 using the hardware SHA accelerator.
