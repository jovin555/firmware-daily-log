---
title: "Day 16: Hardware Crypto Accelerators: CryptoCell, SE05x & ATECC608"
date: 2026-07-16
tags: ["til", "embedded-crypto", "crypto-accelerator", "atecc608"]
---

## What I Explored Today

Today I dove into three hardware crypto accelerators that dominate the embedded landscape: Arm CryptoCell (integrated into Cortex-M33/A35 SoCs), NXP SE05x (a dedicated secure element family), and Microchip ATECC608 (a low-cost authentication IC). I focused on how each offloads cryptographic operations from the main CPU, manages key material in tamper-resistant storage, and integrates into real firmware stacks. I wrote test harnesses for each, measured throughput on ECDSA signing, and discovered why you can't treat them as drop-in replacements for software crypto.

## The Core Concept

Hardware crypto accelerators exist because software cryptography on a general-purpose MCU is both slow and insecure for key storage. A Cortex-M4 doing ECDSA P-256 sign in software takes roughly 200-400 ms; the ATECC608 does it in under 100 ms while keeping the private key in a slot that physically resists probing. But the real win isn't speed—it's isolation. CryptoCell, SE05x, and ATECC608 all implement a "key never leaves the hardware" policy. The host CPU sends data to be signed or encrypted, and the accelerator returns the result, never exposing the private key material to system memory or the debug interface.

The architectural difference matters: CryptoCell is a peripheral block on the same die as the CPU, sharing memory and bus fabric. SE05x is a separate chip communicating over I2C, with its own microcontroller and certified firmware (Common Criteria EAL 6+). ATECC608 is a simpler, cheaper chip that speaks a custom command set over I2C or SWI. Your choice depends on threat model: do you need to resist side-channel attacks (CryptoCell), certified secure boot with lifecycle management (SE05x), or just protect a few keys in a $0.50 BOM (ATECC608)?

## Key Commands / Configuration / Code

### ATECC608: ECDSA Sign via I2C (using Microchip CryptoAuthLib)

```c
#include "cryptoauthlib.h"

// Initialize the ATECC608 on I2C bus 1, address 0xC0
ATCAIfaceCfg cfg = {
    .iface_type = ATCA_I2C_IFACE,
    .devtype = ATECC608,
    .atcai2c.slave_address = 0xC0,
    .atcai2c.bus = 1,
    .atcai2c.baud = 100000,
    .wake_delay = 1500,
    .rx_retries = 20
};

ATCA_STATUS status = atcab_init(&cfg);
if (status != ATCA_SUCCESS) {
    // handle error: check I2C pull-ups, device presence
    return -1;
}

uint8_t message_hash[32]; // SHA-256 hash of your data
uint8_t signature[64];    // R||S format

// Slot 0 must be configured for ECDSA P-256 private key
status = atcab_sign(0, message_hash, signature);
if (status == ATCA_SUCCESS) {
    // signature is valid; send over UART or store
}
```

**Key insight**: `atcab_sign` internally handles the nonce generation, random number sourcing from the internal TRNG, and the ECC point multiplication. The private key in slot 0 is never readable—even by the host.

### SE05x: Secure Channel Establishment (using NXP Plug & Trust Middleware)

```c
#include "se05x_APDU.h"
#include "smCom.h"

// Open a secure channel to SE05x over I2C
smStatus_t smStatus;
SE05x_Session_t session;
uint8_t context[] = "my_device_01";

smStatus = Se05x_API_SessionOpen(
    &session,
    context, sizeof(context),
    kSE05x_SymmetricKey_Type_AES128,
    NULL, 0  // no external symmetric key; use pre-provisioned
);
if (smStatus != SM_OK) {
    // likely I2C communication failure or SE in locked state
    return;
}

// Generate ECDSA key pair inside SE05x, never exposed
SE05x_ECKeyPair_t keyPair;
smStatus = Se05x_API_GenerateECKeyPair(
    &session,
    kSE05x_ECCurve_P256,
    &keyPair,
    kSE05x_KeyObjectID_UserID_First
);
// keyPair.pubKey is returned; private key stays in SE05x
```

**Critical detail**: The SE05x requires a "secure channel" before any cryptographic operation. This is a session key derived from a pre-shared secret (provisioned at manufacturing). Without it, the SE05x refuses all commands—a common gotcha when prototyping with evaluation boards that come pre-provisioned.

### CryptoCell: Accelerated AES-GCM via TF-M (Trusted Firmware-M)

```c
// CryptoCell is accessed through the PSA Crypto API in TF-M
psa_status_t status;
psa_key_attributes_t attributes = PSA_KEY_ATTRIBUTES_INIT;
psa_key_id_t key_id;

// Set key type to AES-128 for GCM
psa_set_key_usage_flags(&attributes, PSA_KEY_USAGE_ENCRYPT);
psa_set_key_algorithm(&attributes, PSA_ALG_GCM);
psa_set_key_type(&attributes, PSA_KEY_TYPE_AES);
psa_set_key_bits(&attributes, 128);

uint8_t key_data[16] = {0x2b, 0x7e, 0x15, 0x16, ...};
status = psa_import_key(&attributes, key_data, sizeof(key_data), &key_id);
// CryptoCell stores key in its dedicated key RAM, not system memory

uint8_t plaintext[] = "Hello CryptoCell";
uint8_t iv[12] = {0};
uint8_t ciphertext[64];
uint8_t tag[16];
size_t ciphertext_len, tag_len;

status = psa_aead_encrypt(
    key_id, PSA_ALG_GCM,
    iv, sizeof(iv),
    NULL, 0,           // no additional data
    plaintext, sizeof(plaintext),
    ciphertext, sizeof(ciphertext), &ciphertext_len,
    tag, sizeof(tag), &tag_len
);
// AES-GCM runs entirely in CryptoCell hardware at ~200 MB/s
```

## Common Pitfalls & Gotchas

1. **ATECC608: Slot configuration is permanent.** Once you set a slot to "nonvolatile" or "require authorization," you cannot change it without erasing the entire chip (which destroys all keys). Always prototype slot configs on a dev board with `atcab_write_config_zone()` before production.

2. **SE05x: Secure channel timeout.** The SE05x drops the secure channel after 5 seconds of inactivity by default. If your main loop takes longer between crypto operations, you must re-establish the session. Many engineers waste hours debugging "random" failures that are just timeout-induced session drops.

3. **CryptoCell: DMA buffer alignment.** CryptoCell's DMA engine requires buffers to be aligned to 32 bytes and in non-cacheable memory. Passing a stack-allocated buffer without proper alignment causes silent data corruption. Always use `pSA_ALIGNED` or allocate from a dedicated memory pool.

## Try It Yourself

1. **ATECC608 key generation and sign**: Wire an ATECC608 to an STM32 or ESP32 over I2C. Use `atcab_genkey()` to create a new ECDSA key pair in slot 2, then sign a known hash and verify it using `atcab_verify_extern()` with the public key you exported. Measure the signing time with a GPIO toggle.

2. **SE05x secure channel stress test**: Write a loop that opens a secure channel, performs one ECDSA sign, then waits 7 seconds before the next sign. Observe the session drop and implement automatic reconnection. Log the number of successful consecutive operations before failure.

3. **CryptoCell AES-GCM throughput benchmark**: On a Cortex-M33 board with CryptoCell (e.g., NXP LPC55S69), encrypt a 1 MB buffer using PSA Crypto's `psa_aead_encrypt()`. Compare the wall-clock time against a software AES-GCM implementation (e.g., mbedTLS without hardware acceleration). Report the speedup factor.

## Next Up

Tomorrow we'll tear down the internals of mbedTLS and wolfSSL—how these embedded TLS stacks handle handshake state machines, certificate parsing, and hardware accelerator integration. We'll look at the `mbedtls_ssl_handshake()` call flow and where you plug in your ATECC608 or CryptoCell for private key operations.
