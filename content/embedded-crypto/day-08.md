---
title: "Day 08: Elliptic Curve Cryptography: ECDSA & ECDH Explained"
date: 2026-07-08
tags: ["til", "embedded-crypto", "ecc", "ecdsa"]
---

## What I Explored Today

Today I dove into Elliptic Curve Cryptography (ECC) — specifically the two workhorse algorithms built on it: ECDSA for digital signatures and ECDH for key agreement. After weeks of RSA and Diffie-Hellman over prime fields, ECC feels like a breath of fresh air. The core insight is that ECC gives you equivalent security to RSA with significantly smaller key sizes — a 256-bit ECC key offers comparable security to a 3072-bit RSA key. For embedded systems where flash, RAM, and CPU cycles are precious, this is a game-changer. I spent the day generating keys, signing messages, and establishing shared secrets using OpenSSL and a lightweight C library, focusing on the NIST P-256 curve (secp256r1) which is the de facto standard for most embedded targets.

## The Core Concept

ECC is not magic — it’s just a different mathematical playground. Instead of working with prime fields and modular exponentiation (RSA/DH), ECC works over points on an elliptic curve defined by the equation `y² = x³ + ax + b`. The magic is in the "group law": you can add two points on the curve to get a third point, and multiplying a point by an integer (scalar multiplication) is computationally easy, but finding the integer given the starting point and result (the discrete log problem) is computationally infeasible.

Why does this matter for embedded? Because the security comes from the elliptic curve discrete logarithm problem (ECDLP), which is harder per bit than the integer factorization or finite-field discrete log problems used by RSA and classic DH. This means smaller keys, faster operations, and lower power consumption. ECDSA uses this to create signatures: you sign with your private key, anyone with your public key can verify. ECDH uses it for key agreement: two parties exchange public points and independently compute the same shared secret — no pre-shared key needed.

The critical practical detail: you must use a standardized curve. Rolling your own curve parameters is a catastrophic security failure. Stick with NIST P-256, Curve25519, or secp256k1.

## Key Commands / Configuration / Code

Let's get hands-on. I'll use OpenSSL and a minimal embedded C example with the Mbed TLS library.

### 1. Generate an ECC key pair (P-256) with OpenSSL

```bash
# Generate private key in PEM format
openssl ecparam -genkey -name prime256v1 -out private.pem

# Extract the public key
openssl ec -in private.pem -pubout -out public.pem

# Inspect the key details
openssl ec -in private.pem -text -noout
# Output includes: private key (hex), public key (uncompressed point), curve name
```

### 2. Sign and verify with ECDSA using OpenSSL

```bash
# Create a message to sign
echo "firmware_v2.1.0" > message.txt

# Sign with private key (output in DER format)
openssl dgst -sha256 -sign private.pem -out signature.der message.txt

# Verify with public key
openssl dgst -sha256 -verify public.pem -signature signature.der message.txt
# Output: Verified OK
```

### 3. ECDH key agreement with OpenSSL

```bash
# Generate two key pairs (Alice and Bob)
openssl ecparam -genkey -name prime256v1 -out alice_private.pem
openssl ecparam -genkey -name prime256v1 -out bob_private.pem

# Extract public keys
openssl ec -in alice_private.pem -pubout -out alice_public.pem
openssl ec -in bob_private.pem -pubout -out bob_public.pem

# Derive shared secret from Alice's perspective
openssl pkeyutl -derive -inkey alice_private.pem -peerkey bob_public.pem -out shared_secret_alice.bin

# Derive from Bob's perspective (should match)
openssl pkeyutl -derive -inkey bob_private.pem -peerkey alice_public.pem -out shared_secret_bob.bin

# Verify they match
xxd shared_secret_alice.bin
xxd shared_secret_bob.bin
# Both hex dumps should be identical
```

### 4. Embedded C example using Mbed TLS (pseudo-code)

```c
#include <mbedtls/ecdsa.h>
#include <mbedtls/ecdh.h>
#include <mbedtls/ctr_drbg.h>

// ECDSA sign a hash
mbedtls_ecdsa_context ctx;
mbedtls_ecdsa_init(&ctx);
mbedtls_ecp_group_load(&ctx.grp, MBEDTLS_ECP_DP_SECP256R1);

// Load private key (from secure storage, not hardcoded!)
mbedtls_mpi_read_string(&ctx.d, 16, private_key_hex);

// Sign a 32-byte SHA-256 hash
uint8_t hash[32] = { /* ... */ };
uint8_t sig[64]; // r || s
size_t sig_len;
mbedtls_ecdsa_write_signature(&ctx, MBEDTLS_MD_SHA256,
    hash, sizeof(hash), sig, &sig_len, NULL, NULL);
// sig now contains the ECDSA signature (r, s)

// ECDH shared secret
mbedtls_ecdh_context ecdh;
mbedtls_ecdh_init(&ecdh);
mbedtls_ecp_group_load(&ecdh.grp, MBEDTLS_ECP_DP_SECP256R1);

// Load our private key and peer's public point
mbedtls_ecdh_read_key(&ecdh, our_private_key, key_len);
mbedtls_ecdh_read_public(&ecdh, peer_public_point, point_len);

uint8_t shared_secret[32];
size_t olen;
mbedtls_ecdh_calc_secret(&ecdh, &olen, shared_secret, sizeof(shared_secret),
    NULL, NULL);
// shared_secret now contains the raw x-coordinate (32 bytes)
// WARNING: Always hash this through a KDF before use!
```

## Common Pitfalls & Gotchas

1. **Using the raw shared secret from ECDH directly.** The output of ECDH is the x-coordinate of the shared point. This is not uniformly random and may have biases. Always pass it through a Key Derivation Function (KDF) like HKDF or at least SHA-256 before using it as an encryption key. I learned this the hard way when my AES-GCM nonce reuse vulnerability appeared.

2. **Forgetting to validate public keys.** In ECDH, if you don't verify that the peer's public point is actually on the curve (and not the point at infinity), an attacker can send a low-order point and force the shared secret to a small, guessable set. Mbed TLS does this automatically if you use `mbedtls_ecdh_read_public()`, but raw point parsing without validation is a common bug.

3. **Side-channel leakage from scalar multiplication.** The private key `d` is used in scalar multiplication (`d * G`). If your implementation doesn't use constant-time operations, timing or power analysis can leak the private key bit by bit. On embedded MCUs, use hardware accelerators or libraries like Mbed TLS with `MBEDTLS_ECP_FIXED_POINT_OPTIM` disabled and constant-time enabled.

## Try It Yourself

1. **Generate an ECDSA key pair on the secp256r1 curve using OpenSSL.** Sign a short message (e.g., "bootloader_v3"), then verify the signature. Now tamper with the message (change one byte) and verify again — observe the failure.

2. **Implement a simple ECDH key exchange between two virtual devices.** Use OpenSSL to generate two key pairs, derive the shared secret from both sides, and confirm they match. Then hash the shared secret with SHA-256 and use the first 16 bytes as an AES-128 key to encrypt a test message.

3. **On an embedded target (or emulator), benchmark ECDSA signing vs. verification.** Use Mbed TLS or TinyCrypt. Measure cycles for a P-256 sign operation and a verify operation. You'll find verification is typically 2-3x faster than signing — useful knowledge for firmware update design where the device only verifies.

## Next Up

Tomorrow: **Digital Signatures: Signing & Verifying Firmware Images** — we'll take ECDSA from theory to practice, building a complete firmware signing pipeline with hash-then-sign, handling large binaries, and implementing secure boot verification on a Cortex-M4 target.
