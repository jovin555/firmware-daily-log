---
title: "Day 06: TF-M Secure Storage & Attestation Services"
date: 2026-06-18
tags: ["til", "trustzone", "secure-storage", "attestation"]
---

## What I Explored Today

Today I dove into two of TF-M's most critical services: Secure Storage (PS/ITS) and Initial Attestation. These are the services that turn a bare-metal secure enclave into something you can actually trust with secrets and identity. I built a test application that stores a symmetric key in the Protected Storage (PS) partition, then retrieves it during an attestation token generation flow. The integration between these services is where the real power lies—your device can prove it holds a secret without ever exposing the secret itself.

## The Core Concept

Secure storage in TF-M isn't just "flash with access control." It's a full cryptographic object store. Every blob you write is authenticated and optionally encrypted using a device-unique key derived from the Hardware Unique Key (HUK). The Protected Storage (PS) service is for larger, persistent objects (like certificates or firmware update keys), while Internal Trusted Storage (ITS) is for small, critical data (like attestation keys or boot counters). Both enforce access control based on the calling partition's ID—no Secure Partition can read another's data unless explicitly granted.

Attestation is the mechanism by which your device proves its identity and integrity to a remote verifier. TF-M's Initial Attestation service generates a signed token (typically a CWT or JWT) containing claims about the device's boot state, firmware version, and the caller's identity. The token is signed with a device-unique attestation key provisioned during manufacturing. Critically, the attestation service can include hash measurements of secure storage objects in the token, allowing a verifier to confirm that the device holds specific secrets at the time of attestation.

Why does this matter? Without attestation, a compromised device could lie about its state. Without secure storage, attestation keys are just data in flash. Together, they form the foundation for remote device management, secure firmware update verification, and multi-factor authentication in IoT deployments.

## Key Commands / Configuration / Code

### 1. Configuring Secure Storage Partitions

In your TF-M build configuration (`config/ConfigCore.cmake`), enable the services:

```cmake
# Enable Protected Storage (PS) and Internal Trusted Storage (ITS)
set(TFM_PARTITION_PROTECTED_STORAGE ON CACHE BOOL "Enable PS")
set(TFM_PARTITION_INTERNAL_TRUSTED_STORAGE ON CACHE BOOL "Enable ITS")

# Set storage backend (FLASH or RAM)
set(PS_BACKEND_FLASH ON CACHE BOOL "Use flash for PS")
set(ITS_BACKEND_FLASH ON CACHE BOOL "Use flash for ITS")

# Set encryption (requires CRYPTO partition)
set(PS_ENCRYPTION ON CACHE BOOL "Encrypt PS objects")
```

### 2. Writing and Reading a Protected Storage Object

Here's a real code snippet from a Secure Partition that stores a 256-bit key:

```c
#include "psa/protected_storage.h"
#include "psa/crypto.h"

// Store a symmetric key in Protected Storage
psa_status_t store_symmetric_key(uint8_t *key_data, size_t key_len) {
    psa_storage_uid_t uid = 0x1001;  // Unique ID for this object
    psa_storage_create_flags_t flags = PSA_STORAGE_FLAG_WRITE_ONCE |
                                       PSA_STORAGE_FLAG_NO_CONFIDENTIALITY;

    // Create the object. Encryption is handled by TF-M if PS_ENCRYPTION=ON
    psa_status_t status = psa_ps_create(uid, key_len, flags);
    if (status != PSA_SUCCESS) {
        return status;
    }

    // Write the data
    status = psa_ps_set(uid, key_len, key_data, 0);
    if (status != PSA_SUCCESS) {
        psa_ps_remove(uid);  // Clean up on failure
        return status;
    }

    return PSA_SUCCESS;
}

// Retrieve the key later
psa_status_t load_symmetric_key(uint8_t *buffer, size_t *key_len) {
    psa_storage_uid_t uid = 0x1001;
    size_t data_len = 0;

    // Get the object size first
    psa_status_t status = psa_ps_get_info(uid, NULL, &data_len);
    if (status != PSA_SUCCESS) return status;

    // Read the object
    status = psa_ps_get(uid, 0, data_len, buffer, key_len);
    return status;
}
```

### 3. Generating an Attestation Token

The attestation service requires a challenge from the verifier (typically 32 or 64 bytes):

```c
#include "psa/initial_attestation.h"

#define CHALLENGE_SIZE 32
#define TOKEN_BUFFER_SIZE 1024

psa_status_t get_attestation_token(uint8_t *challenge, uint8_t *token,
                                    size_t *token_len) {
    // The challenge must be exactly 32 or 64 bytes
    psa_status_t status = psa_initial_attest_get_token(
        challenge, CHALLENGE_SIZE,
        token, TOKEN_BUFFER_SIZE,
        token_len
    );
    return status;
}

// Example: include a hash of a stored object in the token
psa_status_t attest_with_storage_hash(uint8_t *challenge, uint8_t *token,
                                       size_t *token_len) {
    // First, compute hash of the stored key object
    uint8_t key_hash[32];
    psa_status_t status = psa_ps_get(0x1001, 0, 32, key_hash, &(size_t){32});
    if (status != PSA_SUCCESS) return status;

    // Hash the key data (simplified - use psa_hash_compute in practice)
    // Then include the hash as a claim in the attestation token
    // TF-M's attestation service supports custom claims via
    // psa_attestation_register_claim()

    return psa_initial_attest_get_token(challenge, CHALLENGE_SIZE,
                                        token, TOKEN_BUFFER_SIZE, token_len);
}
```

## Common Pitfalls & Gotchas

1. **Storage UID collisions across partitions**: Each Secure Partition has its own UID namespace. If two partitions use the same UID, they will overwrite each other's data silently. Always prefix UIDs with a partition-specific base (e.g., `0x1000 + partition_id * 0x100`). TF-M does NOT enforce UID uniqueness across partitions.

2. **Attestation token size limits**: The default token buffer in TF-M is 1024 bytes. If you add many custom claims or have a large certificate chain, the token generation will fail with `PSA_ERROR_BUFFER_TOO_SMALL`. Always check the actual token size from `psa_initial_attest_get_token_size()` before allocating.

3. **Write-once flags are irreversible**: Once you set `PSA_STORAGE_FLAG_WRITE_ONCE` on an object, you cannot modify or delete it—even from the same partition. This is great for provisioning root certificates, but a mistake means you need to wipe the entire storage area (often requiring a full flash erase). Test with the flag off first.

## Try It Yourself

1. **Build a secure counter**: Create a Secure Partition that stores an incrementing counter in ITS. Each time the counter is read, increment it and write it back. Verify that the counter persists across reboots and cannot be tampered with from the Non-Secure world.

2. **Attestation with custom claims**: Extend the attestation token to include the SHA-256 hash of a stored PS object. Use `psa_hash_compute()` from the Crypto partition, then register the hash as a custom claim using `psa_attestation_register_claim()`. Verify the token structure using a CBOR decoder.

3. **Multi-partition access control**: Create two Secure Partitions: one that writes a secret to PS with `PSA_STORAGE_FLAG_NO_READ`, and another that attempts to read it. Observe the error. Then modify the manifest to grant read access via the `psa_ps_access` attribute in the partition's manifest file.

## Next Up

Tomorrow we move to the boot chain: **MCUboot: Bootloader Architecture & Image Slots**. We'll examine how MCUboot validates signed firmware images, manages multiple image slots for fail-safe updates, and hands off to TF-M for runtime security. If you've ever wondered how a device recovers from a botched firmware update, this is the session you don't want to miss.
