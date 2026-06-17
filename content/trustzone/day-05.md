---
title: "Day 05: TF-M PSA Crypto API: Key Management & Crypto Ops"
date: 2026-06-17
tags: ["til", "trustzone", "psa-crypto", "keys", "tfm"]
---

## What I Explored Today

Today I dove into the PSA Crypto API as implemented by TF-M, specifically focusing on key management and cryptographic operations from the Secure Partition (SP) side. While the PSA Crypto API is standardized, TF-M's implementation has critical nuances around key lifecycle, persistent key storage, and the mandatory use of key identifiers (key IDs) rather than raw key material. I wrote a test SP that generates an ECC P-256 key pair, exports the public key, signs a message, and verifies the signature—all through the PSA API.

## The Core Concept

The PSA Crypto API is designed around a fundamental principle: **the Secure World never exposes private key material to the Normal World**. Instead, keys are referenced by opaque handles (psa_key_id_t) and stored in a dedicated secure storage area managed by TF-M's Protected Storage service. This is not just a software abstraction—it's a hardware-backed isolation boundary.

Why does this matter? In a TrustZone system, even the Secure World's memory can be vulnerable to physical attacks (glitching, probing) or software vulnerabilities in other SPs. By keeping key material in a dedicated storage partition that is only accessible through the PSA Crypto service, TF-M reduces the attack surface. The API forces you to think in terms of key policies (usage flags, algorithms, lifetimes) rather than raw bytes.

The key lifecycle in TF-M is:
1. **Generate or Import** → returns a `psa_key_id_t`
2. **Use** → sign, verify, encrypt, decrypt, derive
3. **Destroy** → `psa_destroy_key()`

You never call `psa_export_key()` on a private key unless you explicitly set the `PSA_KEY_USAGE_EXPORT` flag in the policy—and even then, you should only do it during provisioning.

## Key Commands / Configuration / Code

Here's a minimal Secure Partition that generates an ECC P-256 key pair and uses it for signing and verification. This runs inside an SP's `tfm_crypto_init()` or a dedicated thread.

```c
#include "psa/crypto.h"
#include "tfm_crypto_defs.h"

psa_status_t crypto_demo(void) {
    psa_status_t status;
    psa_key_id_t key_id;
    psa_key_attributes_t attributes = PSA_KEY_ATTRIBUTES_INIT;

    // 1. Set key policy: only sign & verify, no export
    psa_set_key_usage_flags(&attributes, PSA_KEY_USAGE_SIGN_HASH | PSA_KEY_USAGE_VERIFY_HASH);
    psa_set_key_algorithm(&attributes, PSA_ALG_ECDSA(PSA_ALG_SHA_256));
    psa_set_key_type(&attributes, PSA_KEY_TYPE_ECC_KEY_PAIR(PSA_ECC_FAMILY_SECP_R1));
    psa_set_key_bits(&attributes, 256);

    // 2. Generate key pair in persistent storage (lifetime = PSA_KEY_LIFETIME_PERSISTENT)
    //    The key ID must be in the SP's reserved range (0x7000_0000 - 0x7FFF_FFFF for TF-M)
    psa_set_key_id(&attributes, 0x70000001);
    psa_set_key_lifetime(&attributes, PSA_KEY_LIFETIME_PERSISTENT);

    status = psa_generate_key(&attributes, &key_id);
    if (status != PSA_SUCCESS) {
        return status; // Handle error
    }

    // 3. Export public key for verification (allowed because it's the public part)
    uint8_t pub_key[65]; // Uncompressed P-256 public key
    size_t pub_key_len;
    status = psa_export_public_key(key_id, pub_key, sizeof(pub_key), &pub_key_len);
    if (status != PSA_SUCCESS) {
        psa_destroy_key(key_id);
        return status;
    }

    // 4. Sign a hash (in real code, hash the message first)
    uint8_t hash[32] = {0x01, 0x02, 0x03}; // Example SHA-256 hash
    uint8_t signature[64]; // ECDSA signature is 64 bytes for P-256
    size_t sig_len;
    status = psa_sign_hash(key_id, PSA_ALG_ECDSA(PSA_ALG_SHA_256),
                           hash, sizeof(hash),
                           signature, sizeof(signature), &sig_len);
    if (status != PSA_SUCCESS) {
        psa_destroy_key(key_id);
        return status;
    }

    // 5. Verify using the exported public key (imported as a volatile key)
    psa_key_id_t pub_key_id;
    psa_key_attributes_t pub_attr = PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_usage_flags(&pub_attr, PSA_KEY_USAGE_VERIFY_HASH);
    psa_set_key_algorithm(&pub_attr, PSA_ALG_ECDSA(PSA_ALG_SHA_256));
    psa_set_key_type(&pub_attr, PSA_KEY_TYPE_ECC_PUBLIC_KEY(PSA_ECC_FAMILY_SECP_R1));

    status = psa_import_key(&pub_attr, pub_key, pub_key_len, &pub_key_id);
    if (status != PSA_SUCCESS) {
        psa_destroy_key(key_id);
        return status;
    }

    status = psa_verify_hash(pub_key_id, PSA_ALG_ECDSA(PSA_ALG_SHA_256),
                             hash, sizeof(hash),
                             signature, sig_len);
    if (status != PSA_SUCCESS) {
        // Signature verification failed
    }

    // Cleanup
    psa_destroy_key(pub_key_id);
    psa_destroy_key(key_id);
    return status;
}
```

**Build integration** — ensure your SP's manifest includes the crypto service binding:
```yaml
# In sp.manifest
"psa_framework_version": 1.1
"services": [
  "TFM_CRYPTO_SERVICE"
]
```

And link against `libtfm_crypto.a` in your CMakeLists.txt.

## Common Pitfalls & Gotchas

1. **Key ID collision with other SPs** — TF-M uses a global key ID namespace. If two SPs try to use the same persistent key ID (e.g., `0x70000001`), the second `psa_generate_key` will fail with `PSA_ERROR_ALREADY_EXISTS`. Always reserve key ID ranges per SP in your partition manifest or use volatile keys (`PSA_KEY_LIFETIME_VOLATILE`) for ephemeral operations.

2. **Missing PSA_KEY_USAGE_EXPORT for public key export** — You do *not* need `PSA_KEY_USAGE_EXPORT` to call `psa_export_public_key()`. That flag is only required for `psa_export_key()` (which exports the private key). Many engineers mistakenly set the export flag on private keys, weakening security.

3. **Algorithm mismatch between sign and verify** — The algorithm passed to `psa_sign_hash()` and `psa_verify_hash()` must match exactly, including the hash algorithm. Using `PSA_ALG_ECDSA(PSA_ALG_SHA_256)` for signing but `PSA_ALG_ECDSA(PSA_ALG_SHA_384)` for verification will silently fail with `PSA_ERROR_INVALID_ARGUMENT`.

## Try It Yourself

1. **Modify the code to use a volatile key** — Change `PSA_KEY_LIFETIME_PERSISTENT` to `PSA_KEY_LIFETIME_VOLATILE` and remove the `psa_set_key_id()` call. Observe that the key is destroyed when the SP terminates.

2. **Add AES-GCM encryption** — Generate a 128-bit AES key with `PSA_KEY_TYPE_AES` and `PSA_ALG_GCM`. Encrypt a short message, then decrypt it. Note that GCM requires a nonce—use `psa_generate_random()` to create one.

3. **Stress-test key exhaustion** — Write a loop that generates 100 volatile ECC keys without destroying them. Check the return status—TF-M has a limited key slot pool (typically 8-32 depending on configuration). See what error you get when the pool is exhausted.

## Next Up

Tomorrow we move from crypto operations to **TF-M Secure Storage & Attestation Services**. I'll show you how to store keys and data in the Protected Storage partition, and how to generate a platform attestation token that proves your firmware's integrity to a remote verifier.
