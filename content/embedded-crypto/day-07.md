---
title: "Day 07: Asymmetric Crypto: RSA Fundamentals & Key Sizes"
date: 2026-07-07
tags: ["til", "embedded-crypto", "rsa"]
---

## What I Explored Today

Today I dove into RSA — the most widely deployed asymmetric cryptosystem in embedded systems. I focused on understanding the mathematical primitives at a practical level, key generation workflows, and the critical trade-offs between key size, security margin, and performance on resource-constrained devices. I generated keys, inspected their structure, and benchmarked operations across 2048-bit and 4096-bit keys on a Cortex-M4 target.

## The Core Concept

RSA's security rests on the practical difficulty of factoring the product of two large primes. The public key is `(n, e)` where `n = p * q` and `e` is a public exponent (typically 65537). The private key is `(n, d)` where `d` is the modular inverse of `e` modulo `(p-1)(q-1)`. Encryption: `c = m^e mod n`. Decryption: `m = c^d mod n`.

Why does this matter for embedded? Because asymmetric crypto solves the key distribution problem that plagues symmetric-only systems. In a sensor network, you can't pre-share a secret AES key with every node. With RSA, each node generates its own key pair, publishes the public key, and keeps the private key in secure storage. No shared secrets ever cross the wire.

The critical engineering decision is key size. NIST SP 800-57 recommends 2048-bit RSA through 2030. Larger keys (4096-bit) provide a wider security margin but cost 4-8x more in computation and 2x in storage. On a typical Cortex-M4 running at 120 MHz, a 2048-bit RSA sign operation takes ~200 ms; 4096-bit takes ~1.5 seconds. For many IoT applications, that latency is unacceptable, pushing designers toward elliptic curve alternatives — but RSA remains dominant in legacy systems, secure boot chains, and PKI infrastructure.

## Key Commands / Configuration / Code

### Generating an RSA key pair with OpenSSL (for host-side provisioning)

```bash
# Generate a 2048-bit RSA private key, encrypted with AES-256-CBC
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -aes-256-cbc -out private_key.pem

# Extract the public key
openssl pkey -in private_key.pem -pubout -out public_key.pem

# Inspect key structure (modulus size, exponents)
openssl rsa -in private_key.pem -text -noout | head -20
```

### Embedded key generation using Mbed TLS (on-device)

```c
#include <mbedtls/pk.h>
#include <mbedtls/entropy.h>
#include <mbedtls/ctr_drbg.h>

int generate_rsa_keypair(mbedtls_pk_context *key, unsigned int bits) {
    mbedtls_entropy_context entropy;
    mbedtls_ctr_drbg_context ctr_drbg;
    const char *pers = "rsa_keygen";

    mbedtls_entropy_init(&entropy);
    mbedtls_ctr_drbg_init(&ctr_drbg);
    mbedtls_ctr_drbg_seed(&ctr_drbg, mbedtls_entropy_func, &entropy,
                          (const unsigned char *)pers, strlen(pers));

    mbedtls_pk_init(key);
    int ret = mbedtls_pk_setup(key, mbedtls_pk_info_from_type(MBEDTLS_PK_RSA));
    if (ret != 0) return ret;

    // Generate key — this blocks for seconds on embedded targets
    ret = mbedtls_rsa_gen_key(mbedtls_pk_rsa(*key),
                              mbedtls_ctr_drbg_random, &ctr_drbg,
                              bits, 65537); // e = 0x10001
    mbedtls_ctr_drbg_free(&ctr_drbg);
    mbedtls_entropy_free(&entropy);
    return ret;
}
```

### Benchmarking RSA operations on target

```c
// Measure sign time (PKCS#1 v1.5 SHA-256)
uint32_t start = DWT->CYCCNT;
mbedtls_rsa_rsassa_pkcs1_v15_sign(&rsa_ctx, NULL, NULL,
    MBEDTLS_MD_SHA256, hash_len, hash, signature);
uint32_t cycles = DWT->CYCCNT - start;
// On 120 MHz Cortex-M4: ~24 million cycles for 2048-bit sign
```

## Common Pitfalls & Gotchas

**1. Using e=3 for performance.** The exponent 3 reduces public-key operation time but is vulnerable to Coppersmith's attack and related-message attacks. Always use e=65537 (0x10001). It has only two 1-bits in binary, making modular exponentiation efficient, and it's large enough to prevent low-exponent attacks.

**2. Ignoring side-channel resistance.** RSA private key operations (decryption, signing) involve the secret exponent `d`. Without constant-time implementations, timing analysis can recover `d` bit by bit. Mbed TLS and WolfSSL provide constant-time RSA by default; ensure you're not disabling it with `MBEDTLS_RSA_NO_CRT` or by using a non-constant-time bignum backend.

**3. Reusing keys across environments.** An RSA key generated on a host PC and then flashed to an embedded device exposes the private key during transport. Generate keys on the device itself using a hardware TRNG, or use a secure provisioning service (e.g., HSM-based key injection) if on-device generation is too slow.

## Try It Yourself

1. **Generate and inspect keys:** Use OpenSSL to create a 2048-bit RSA key. Run `openssl rsa -text -noout` and identify the modulus, public exponent, private exponent, and the two primes. Verify the modulus is exactly 2048 bits.

2. **Benchmark on target:** Port the Mbed TLS RSA sign benchmark to your dev board. Measure sign and verify times for 2048-bit and 4096-bit keys. Calculate the maximum signatures per second your device can sustain.

3. **Constant-time test:** Write a test that signs the same message 1000 times and checks if the execution time varies by more than 1%. If it does, investigate whether your RSA implementation is using constant-time exponentiation.

## Next Up

Tomorrow: **Elliptic Curve Cryptography: ECDSA & ECDH Explained** — we'll explore why ECC is replacing RSA in modern embedded systems, how 256-bit ECC keys provide equivalent security to 3072-bit RSA, and walk through real ECDSA signing and ECDH key agreement on a Cortex-M0.
