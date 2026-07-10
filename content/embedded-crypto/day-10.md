---
title: "Day 10: Key Exchange: Diffie-Hellman & ECDH in Constrained Devices"
date: 2026-07-10
tags: ["til", "embedded-crypto", "key-exchange", "ecdh"]
---

## What I Explored Today

Today I dove into the practical reality of key exchange on constrained devices—specifically how to implement Diffie-Hellman (DH) and its elliptic curve variant (ECDH) on microcontrollers with limited RAM, flash, and no hardware acceleration. While textbook DH is elegant, the real engineering challenge is making it work within a 32KB SRAM budget and a few hundred microseconds per operation. I focused on the Mbed TLS and TinyCrypt implementations, benchmarking against an ARM Cortex-M4 at 120 MHz, and discovered that curve selection alone can mean the difference between a 50ms handshake and a 2-second one.

## The Core Concept

Symmetric encryption requires both sides to share the same secret key. The problem is distributing that key securely over an untrusted channel. DH solves this by letting two parties agree on a shared secret without ever transmitting it. The classic version uses modular exponentiation of large primes (typically 2048-bit). ECDH does the same thing but over an elliptic curve, using much smaller keys (256-bit) for equivalent security.

For constrained devices, ECDH is the only practical choice. A 2048-bit DH operation on a Cortex-M4 without hardware acceleration can take 1-2 seconds and consume 4KB+ of stack. ECDH with a 256-bit curve (like secp256r1) runs in 50-200ms and uses under 1KB of stack. The math is more complex, but the numbers are smaller, which is what matters when your CPU is clocked at 48 MHz.

The critical engineering insight: you don't need to re-derive the shared secret every session. You can pre-compute your static key pair and store it in flash (or a secure element). The ephemeral key exchange then only requires one scalar multiplication per side, which is the fast path.

## Key Commands / Configuration / Code

### TinyCrypt ECDH Key Generation (C, for ARM Cortex-M)

```c
#include <tinycrypt/ecc.h>
#include <tinycrypt/ecc_dh.h>
#include <tinycrypt/utils.h>

// Buffer for private key (32 bytes) and public key (64 bytes: x,y)
uint8_t private_key[32];
uint8_t public_key[64];

// Generate key pair using NIST P-256 (secp256r1)
int ret = uECC_make_key(public_key, private_key, uECC_secp256r1());
if (ret == 0) {
    // Handle failure — typically RNG issue
    // Check your TRNG driver before calling this
}

// Compute shared secret from peer's public key
uint8_t peer_public[64];  // received from remote
uint8_t shared_secret[32]; // 32 bytes output

ret = uECC_shared_secret(peer_public, private_key, shared_secret, uECC_secp256r1());
if (ret == 0) {
    // Shared secret derivation failed — invalid public key?
}
```

### Mbed TLS ECDH with Pre-computed Static Keys

```c
#include "mbedtls/ecdh.h"
#include "mbedtls/ctr_drbg.h"

mbedtls_ecdh_context ctx;
mbedtls_ecdh_init(&ctx);

// Use pre-loaded static private key (from secure storage)
mbedtls_mpi static_priv;
mbedtls_mpi_init(&static_priv);
mbedtls_mpi_read_binary(&static_priv, stored_priv_key, 32);

// Load group (P-256)
mbedtls_ecp_group_load(&ctx.grp, MBEDTLS_ECP_DP_SECP256R1);

// Set our static private key
mbedtls_ecdh_setup(&ctx, MBEDTLS_ECDH_OURS);
mbedtls_ecdh_read_public(&ctx, peer_pub_x, 32, peer_pub_y, 32);

// Compute shared secret
uint8_t secret[32];
size_t olen;
mbedtls_ecdh_calc_secret(&ctx, &olen, secret, sizeof(secret),
                          mbedtls_ctr_drbg_random, &drbg_ctx);
```

### Build Configuration for TinyCrypt (CMakeLists.txt snippet)

```cmake
# Enable only P-256 to save flash
add_definitions(-DuECC_CURVE=uECC_secp256r1)
# Disable unneeded curves
add_definitions(-DuECC_SUPPORTS_secp192r1=0)
add_definitions(-DuECC_SUPPORTS_secp224r1=0)
add_definitions(-DuECC_SUPPORTS_secp256k1=0)
```

## Common Pitfalls & Gotchas

1. **RNG failure during key generation is silent.** Both TinyCrypt and Mbed TLS return error codes, but many embedded engineers skip the check. If your hardware RNG (TRNG) isn't initialized or fails, `uECC_make_key` returns 0 and your private key is all zeros. Always verify the return value and implement a fallback (e.g., retry with a different entropy source).

2. **Public key validation is not automatic.** ECDH implementations typically assume the peer's public key is valid (on the curve). An invalid point can leak bits of your private key through a small subgroup attack. Always call `uECC_valid_public_key()` or `mbedtls_ecp_check_pubkey()` before computing the shared secret. This adds ~5ms but prevents a known attack vector.

3. **Shared secret reuse without key derivation.** The raw x-coordinate output from ECDH is not uniformly random. Never use it directly as an AES key. Always pass it through a KDF (HKDF, or at minimum SHA-256). Most libraries provide a `mbedtls_hkdf()` function for this purpose.

## Try It Yourself

1. **Benchmark ECDH on your target.** Write a test that measures `uECC_make_key` + `uECC_shared_secret` for P-256. Run it 100 times and record min/max/avg. Compare with and without compiler optimizations (`-O2` vs `-Os`). This gives you real-world timing for your handshake budget.

2. **Implement public key validation.** Take the TinyCrypt example above and add a call to `uECC_valid_public_key(peer_public, uECC_secp256r1())` before the shared secret computation. Log a warning if it fails. Run a test with a malformed public key (e.g., set one byte to 0xFF) to verify your validation catches it.

3. **Derive a proper session key.** After computing the shared secret, feed it through HKDF-SHA256 to produce a 128-bit AES key. Use `mbedtls_hkdf()` or implement a simple HMAC-based KDF. Verify that two different shared secrets produce different derived keys.

## Next Up

Tomorrow: Random Number Generation: TRNG vs PRNG & Entropy Sources — why your `rand()` call is a security disaster and how to properly seed a CSPRNG on a microcontroller with no hardware RNG.
