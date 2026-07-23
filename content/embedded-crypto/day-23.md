---
title: "Day 23: Post-Quantum Cryptography: What Embedded Engineers Need to Know Now"
date: 2026-07-23
tags: ["til", "embedded-crypto", "post-quantum", "pqc"]
---

## What I Explored Today

Today I dove into the practical implications of Post-Quantum Cryptography (PQC) for embedded systems. With NIST’s finalized standards for CRYSTALS-Kyber (key encapsulation) and CRYSTALS-Dilithium (digital signatures) now published as FIPS 203 and FIPS 204, the transition is no longer theoretical. I focused on how these algorithms behave on resource-constrained devices—specifically ARM Cortex-M4 and ESP32 targets—examining stack usage, signature sizes, and integration paths alongside existing classical crypto like ECDH and ECDSA.

## The Core Concept

The threat is simple: a sufficiently large quantum computer running Shor’s algorithm can break RSA and ECC in polynomial time. For embedded devices with long lifespans—think smart meters, automotive ECUs, or medical implants—keys generated today could be harvested now and decrypted later (“harvest now, decrypt later”). PQC replaces the number-theoretic hardness of factoring or discrete logs with lattice-based problems (e.g., Learning With Errors) that are believed to be quantum-resistant.

Why should you care *now*? Because the migration is not a drop-in replacement. PQC public keys and signatures are 10–100× larger than their classical counterparts. A Kyber-512 public key is 800 bytes vs. 32 bytes for X25519. Dilithium-2 signatures are 2,420 bytes vs. 64 bytes for Ed25519. On a device with 256 KB of flash and 64 KB of RAM, that changes your memory budget, packet sizes, and flash wear. You need to start auditing your key storage, bootloader update sizes, and TLS handshake buffers today.

## Key Commands / Configuration / Code

I used the **liboqs** library (version 0.10.0) compiled for an ARM Cortex-M4 target. Below is a minimal example of Kyber key generation and encapsulation, with memory usage annotations.

```c
#include <oqs/oqs.h>
#include <string.h>
#include <stdio.h>

// Stack budget: Kyber-512 uses ~3.2 KB for internal state
#define KYBER_ALGORITHM OQS_KEM_alg_kyber_512

void pqc_demo(void) {
    OQS_KEM *kem = NULL;
    uint8_t public_key[OQS_KEM_kyber_512_length_public_key];   // 800 bytes
    uint8_t secret_key[OQS_KEM_kyber_512_length_secret_key];   // 1632 bytes
    uint8_t ciphertext[OQS_KEM_kyber_512_length_ciphertext];   // 768 bytes
    uint8_t shared_secret_e[OQS_KEM_kyber_512_length_shared_secret]; // 32 bytes
    uint8_t shared_secret_d[OQS_KEM_kyber_512_length_shared_secret];

    // Initialize KEM — returns NULL if algorithm not available
    kem = OQS_KEM_new(KYBER_ALGORITHM);
    if (kem == NULL) {
        printf("ERROR: Kyber-512 not supported on this build\n");
        return;
    }

    // Key generation — typically ~1.5M cycles on Cortex-M4 at 120 MHz
    if (OQS_KEM_keypair(kem, public_key, secret_key) != OQS_SUCCESS) {
        printf("ERROR: Key generation failed\n");
        OQS_KEM_free(kem);
        return;
    }

    // Encapsulate: generate ciphertext and shared secret
    // This is the "encrypt" side (e.g., server)
    if (OQS_KEM_encaps(kem, ciphertext, shared_secret_e, public_key) != OQS_SUCCESS) {
        printf("ERROR: Encapsulation failed\n");
        OQS_KEM_free(kem);
        return;
    }

    // Decapsulate: recover shared secret (e.g., client)
    if (OQS_KEM_decaps(kem, shared_secret_d, ciphertext, secret_key) != OQS_SUCCESS) {
        printf("ERROR: Decapsulation failed\n");
        OQS_KEM_free(kem);
        return;
    }

    // Verify shared secrets match
    if (memcmp(shared_secret_e, shared_secret_d, 
               OQS_KEM_kyber_512_length_shared_secret) == 0) {
        printf("PQC key exchange successful! 32-byte shared secret established.\n");
    } else {
        printf("ERROR: Shared secrets do not match\n");
    }

    OQS_KEM_free(kem);
}
```

For a hybrid approach (recommended for transition), combine with classical ECDH:

```c
// Hybrid: combine Kyber-512 shared secret with X25519 shared secret
// Use SHA-256 to produce a single 32-byte output
uint8_t hybrid_secret[32];
SHA256_CTX ctx;
sha256_init(&ctx);
sha256_update(&ctx, kyber_ss, 32);   // Kyber shared secret
sha256_update(&ctx, x25519_ss, 32);  // X25519 shared secret
sha256_final(&ctx, hybrid_secret);
// hybrid_secret is now quantum-safe AND backward-compatible
```

## Common Pitfalls & Gotchas

1. **Stack overflow from large internal buffers.** Kyber-1024’s internal state can exceed 5 KB. On an RTOS task with a default 2 KB stack, this silently corrupts memory. Always measure peak stack usage with `-fstack-usage` in GCC or use a stack watermarking tool. I recommend starting with Kyber-512 (Level 1 security) for constrained devices.

2. **Fragmented flash wear from large key storage.** Writing a 1.6 KB secret key every time you rotate (vs. 32 bytes for ECC) can wear out flash pages 50× faster. Use external SPI flash or FRAM for key storage, or implement wear-leveling in your key management layer.

3. **TLS handshake buffer overflow.** A Kyber-512 key exchange adds ~1.6 KB to the ClientHello and ServerHello messages. If your mbedTLS or WolfSSL buffer is set to the default 4 KB, you will see `MBEDTLS_ERR_SSL_BUFFER_TOO_SMALL`. Increase `MBEDTLS_SSL_IN_CONTENT_LEN` and `MBEDTLS_SSL_OUT_CONTENT_LEN` to at least 8 KB.

## Try It Yourself

1. **Port the liboqs example above to your dev board** (e.g., STM32F4 Discovery or ESP32-C3). Compile with `-D OQS_ENABLE_KEM_KYBER_512` and measure the time for key generation using a GPIO toggle and an oscilloscope. Compare to ECDH P-256.

2. **Implement a hybrid key exchange** using mbedTLS: configure both `MBEDTLS_KEM_KYBER` and `MBEDTLS_ECDH_C`. In your TLS callback, perform both Kyber-512 and X25519, then combine with SHA-256. Verify interoperability with `openssl s_client` using the OQS-OpenSSL provider.

3. **Audit your current key storage.** Calculate the flash budget if you replaced all ECC P-256 keys with Kyber-512 and all ECDSA signatures with Dilithium-2. How many device certificates can you still store? If the answer is less than your production needs, plan for external secure element storage.

## Next Up

Tomorrow is **Day 24: Full Review & Project: Provisioning Per-Device Keys with ATECC608**. We’ll build a complete provisioning workflow using Microchip’s ATECC608 secure element, covering I2C bus setup, slot configuration, and host-side certificate generation. Bring your logic analyzer.
