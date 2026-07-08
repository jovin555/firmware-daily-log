---
title: "Day 26: TF-M PSA Crypto API: Key Management & Crypto Ops"
date: 2026-07-08
tags: ["til", "trustzone", "psa-crypto", "keys", "tfm"]
---

## What I Explored Today

Today I dove into the PSA Crypto API as exposed by TF-M, specifically focusing on key management and cryptographic operations from the secure domain. The PSA Crypto API is the standard interface for all cryptographic operations in Arm's Platform Security Architecture, and TF-M implements it as a set of secure services callable from the Non-Secure Processing Environment (NSPE) or internally from Secure Partitions. I spent the day understanding how to generate, import, export, and use keys with persistent identities, and how to perform symmetric and asymmetric operations without ever exposing key material to the normal world.

## The Core Concept

The fundamental insight of PSA Crypto is **key isolation**. Unlike traditional crypto libraries where you handle key bytes as plaintext buffers, PSA Crypto assigns each key a numeric identifier (`psa_key_id_t`) and stores the key material inside the secure enclave. The normal world never sees the key bytes—it only passes the key ID to the PSA Crypto secure service. This means even if an attacker compromises the rich OS (Linux, RTOS), they cannot extract key material; they can only request operations using the key, subject to the usage policy set at key creation time.

The API is structured around three concepts:
- **Key attributes** (`psa_key_attributes_t`): define the key type, algorithm, usage flags (export, encrypt, sign, etc.), and persistence policy (volatile or persistent).
- **Key identifiers** (`psa_key_id_t`): a handle returned by `psa_import_key` or `psa_generate_key`. Persistent keys survive reboots.
- **Operation contexts**: stateful objects for multi-part operations (e.g., `psa_hash_operation_t`, `psa_cipher_operation_t`).

The key policy is critical—you must set `psa_key_usage_flags_t` to exactly what you need. A key created with `PSA_KEY_USAGE_SIGN_HASH` cannot be used for encryption, even by the secure domain itself.

## Key Commands / Configuration / Code

### Generating a Persistent ECC Key for Signing

```c
#include "psa/crypto.h"

psa_status_t status;
psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
psa_key_id_t key_id;

// Set key type: NIST P-256 ECC key pair
psa_set_key_type(&attr, PSA_KEY_TYPE_ECC_KEY_PAIR(PSA_ECC_FAMILY_SECP_R1));
psa_set_key_bits(&attr, 256);

// Set usage: only signing, never exportable
psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_SIGN_HASH | PSA_KEY_USAGE_VERIFY_HASH);

// Set algorithm: ECDSA with SHA-256
psa_set_key_algorithm(&attr, PSA_ALG_ECDSA(PSA_ALG_SHA_256));

// Make it persistent with identifier 42 (must be > PSA_KEY_ID_USER_MIN)
psa_set_key_id(&attr, 42);
psa_set_key_lifetime(&attr, PSA_KEY_LIFETIME_PERSISTENT);

// Generate the key inside the secure element
status = psa_generate_key(&attr, &key_id);
if (status != PSA_SUCCESS) {
    // handle error — likely policy violation or entropy failure
}
// key_id == 42, key material never leaves secure domain
```

### Signing a Hash with the Persistent Key

```c
uint8_t hash[32];  // SHA-256 hash of message
uint8_t signature[64]; // ECDSA signature (r||s for P-256)
size_t sig_len;

status = psa_sign_hash(key_id,
                       PSA_ALG_ECDSA(PSA_ALG_SHA_256),
                       hash, sizeof(hash),
                       signature, sizeof(signature),
                       &sig_len);
// sig_len is typically 64 for P-256
```

### Importing a Symmetric Key for AES-GCM Encryption

```c
psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
psa_key_id_t aes_key_id;
uint8_t key_bytes[16] = {0x00, 0x01, 0x02, ...}; // from provisioning

psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
psa_set_key_bits(&attr, 128);
psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_ENCRYPT | PSA_KEY_USAGE_DECRYPT);
psa_set_key_algorithm(&attr, PSA_ALG_GCM);

// Volatile key — lost on reset
status = psa_import_key(&attr, key_bytes, sizeof(key_bytes), &aes_key_id);
// Immediately zero the plaintext key buffer
memset_s(key_bytes, sizeof(key_bytes), 0, sizeof(key_bytes));
```

### Multi-Part Hash (SHA-256) Using the One-Shot API

```c
uint8_t input[] = "Hello, TrustZone!";
uint8_t hash[32];
size_t hash_len;

status = psa_hash_compute(PSA_ALG_SHA_256,
                          input, sizeof(input) - 1,
                          hash, sizeof(hash),
                          &hash_len);
// hash_len == 32
```

## Common Pitfalls & Gotchas

1. **Persistent key IDs must be in the correct range.** TF-M reserves key IDs 0–0x7FFF for internal use. User persistent keys must use IDs >= `PSA_KEY_ID_USER_MIN` (typically 0x8000). Using an ID below this threshold will cause `psa_generate_key` to return `PSA_ERROR_INVALID_ARGUMENT`. Always check the TF-M configuration for `PSA_KEY_ID_USER_MIN` in your platform's `tfm_hal_defs.h`.

2. **Usage flags are enforced server-side, not just by the client library.** You cannot bypass the policy by calling the API from a Secure Partition with higher privileges. If you set `PSA_KEY_USAGE_SIGN_HASH` but then call `psa_encrypt()` with that key, the secure service will return `PSA_ERROR_NOT_PERMITTED`. Plan your key policies before deployment—you cannot change them after creation.

3. **Key destruction is asynchronous for persistent keys.** Calling `psa_destroy_key()` marks the key for deletion, but the actual zeroization may be deferred until the next power cycle or garbage collection. If you need immediate zeroization (e.g., for key rotation), use volatile keys or call `psa_purge_key()` after destruction. Also, never assume `psa_destroy_key()` returns `PSA_SUCCESS` immediately—check the status and retry if needed.

## Try It Yourself

1. **Generate a persistent HMAC-SHA256 key** with ID 0x9000, usage flags set to `PSA_KEY_USAGE_SIGN_HASH | PSA_KEY_USAGE_VERIFY_HASH`, and algorithm `PSA_ALG_HMAC(PSA_ALG_SHA_256)`. Then compute an HMAC over a test message and verify it. Confirm the key survives a TF-M reset.

2. **Implement a secure key provisioning flow**: import an AES-128 key from a hardcoded buffer, encrypt a plaintext using `psa_aead_encrypt()` with AES-GCM, then immediately zero the plaintext key buffer. Verify that `psa_export_key()` on that key returns `PSA_ERROR_NOT_PERMITTED` because you omitted `PSA_KEY_USAGE_EXPORT`.

3. **Stress-test key policy enforcement**: create an ECC key with only `PSA_KEY_USAGE_SIGN_HASH`. Attempt to call `psa_sign_message()` (which uses the full message, not a pre-hash) and `psa_export_public_key()`. Observe which operations succeed and which return `PSA_ERROR_NOT_PERMITTED`. Document the exact error codes.

## Next Up

Tomorrow, we move from crypto primitives to **TF-M Secure Storage & Attestation Services**. I'll cover how to store sensitive data (keys, certificates, logs) using the PSA Protected Storage API, and how to generate signed attestation tokens that prove the device's identity and firmware integrity to a remote verifier. We'll also look at the `tfm_attestation_get_token()` call and how to integrate it with a cloud IoT onboarding flow.
