---
title: "Day 27: TF-M Secure Storage & Attestation Services"
date: 2026-07-09
tags: ["til", "trustzone", "secure-storage", "attestation"]
---

## What I Explored Today

Today I dug into two of TF-M’s most critical Secure Partition services: **Secure Storage** and **Initial Attestation**. These are the building blocks for any real-world TrustZone application that needs to persist secrets or prove its identity to a remote server. I focused on the PSA Certified API implementations inside TF-M, how to configure them via the manifest system, and what actually happens under the hood when you call `psa_its_set()` or `psa_attest_get_token()`.

## The Core Concept

Secure Storage in TF-M isn’t just encrypted flash—it’s a full key-value store with integrity protection, atomic updates, and rollback prevention. The PSA Internal Trusted Storage (ITS) API provides a simple `set/get/remove` interface, but the implementation layers on top of a dedicated flash partition (usually in the Secure Enclave’s private region) and uses a replay-protected monotonic counter (RPMC) to prevent attackers from restoring old, compromised data.

Attestation, on the other hand, is about proving to a verifier that your device is running genuine firmware in a secure environment. TF-M’s Initial Attestation service generates a signed token containing the platform’s identity (the Instance ID), the software components (hashes of loaded images), and a freshness nonce. The token is signed with a device-unique key derived from the Hardware Unique Key (HUK) during boot. Without this service, you can’t do secure onboarding or remote device authentication.

The key insight: these two services are tightly coupled. Secure Storage holds the attestation keys and certificates; Attestation proves the integrity of the system that holds those keys. Break one, and the other becomes meaningless.

## Key Commands / Configuration / Code

### 1. Enabling Secure Storage in TF-M Build

In your `CMakeLists.txt` or build config, you must explicitly enable the partition:

```cmake
# Enable the Internal Trusted Storage partition
set(TFM_PARTITION_INTERNAL_TRUSTED_STORAGE ON CACHE BOOL "" FORCE)

# Choose the backend: FLASH (default) or RAM-backed for testing
set(TFM_ITS_BACKEND "FLASH" CACHE STRING "")

# Set the flash area (device-specific, e.g., for MPS2 AN521)
set(TFM_ITS_FLASH_AREA_ID 3 CACHE STRING "")
```

### 2. Using the PSA ITS API in a Secure Partition

Here’s a minimal example of writing and reading a secret inside a Trusted Firmware Secure Partition:

```c
#include "psa/internal_trusted_storage.h"
#include "psa/error.h"

#define SECRET_KEY_ID 0x10000001
#define SECRET_SIZE    32

psa_status_t store_secret(const uint8_t *secret, size_t len) {
    // psa_its_set() atomically writes data with optional UID-based access control
    psa_status_t status = psa_its_set(SECRET_KEY_ID, len, secret, 0);
    if (status != PSA_SUCCESS) {
        // Handle error: PSA_ERROR_NOT_SUPPORTED, PSA_ERROR_INSUFFICIENT_STORAGE, etc.
        return status;
    }
    return PSA_SUCCESS;
}

psa_status_t load_secret(uint8_t *buf, size_t *len) {
    // psa_its_get() reads back the data; caller must check length
    psa_status_t status = psa_its_get(SECRET_KEY_ID, 0, *len, buf, len);
    if (status == PSA_ERROR_DOES_NOT_EXIST) {
        // No secret stored yet
    }
    return status;
}
```

### 3. Requesting an Attestation Token

The attestation service is called from the Non-Secure Processing Environment (NSPE) via the PSA Client API:

```c
#include "psa/initial_attestation.h"

uint8_t token[1024];
size_t token_len;

psa_status_t get_attestation_token(const uint8_t *challenge, size_t challenge_len) {
    // The challenge is a nonce from the verifier (e.g., server random)
    psa_status_t status = psa_initial_attestation_get_token(
        challenge,
        challenge_len,
        token,
        sizeof(token),
        &token_len
    );
    if (status != PSA_SUCCESS) {
        // Common failure: PSA_ERROR_INSUFFICIENT_MEMORY if token buffer too small
        return status;
    }
    // token now contains a COSE-signed structure (CWT)
    return PSA_SUCCESS;
}
```

### 4. Verifying the Token (Off-Device)

The token is a CBOR Web Token (CWT) signed with the device’s attestation key. You can verify it using `psa_attest_verify()` on a trusted verifier (e.g., a cloud server):

```bash
# Using the PSA Attestation Verifier tool (part of TF-M test suite)
./tools/psa_attest_verify --token token.bin --challenge challenge.bin --key iak.pub
```

## Common Pitfalls & Gotchas

1. **Flash wear and atomicity assumptions**: `psa_its_set()` is atomic only if the underlying flash driver supports it. On many Cortex-M MCUs, flash writes require erase cycles. If you call `psa_its_set()` in a tight loop (e.g., logging sensor data), you’ll wear out the flash in minutes. Always use a dedicated flash area with wear-leveling, or switch to the PSA Protected Storage (PS) API which adds encryption and versioning.

2. **Attestation token size underestimation**: The token can easily exceed 512 bytes depending on the number of software components and claims. If you allocate a small buffer, `psa_initial_attestation_get_token()` returns `PSA_ERROR_INSUFFICIENT_MEMORY`. Always query the required size first using `psa_initial_attestation_get_token_size()`.

3. **Instance ID mismatch**: The attestation token’s Instance ID is derived from the HUK. If you change the HUK (e.g., by erasing the OTP fuses during development), the token becomes unverifiable against your stored public key. Always provision the attestation key pair *after* finalizing the HUK.

## Try It Yourself

1. **Write a secure boot counter**: Use `psa_its_set()` to store a monotonic boot counter. Increment it in your Secure Partition’s `tfm_secure_boot()` callback. Verify that rollback (restoring an old flash image) fails because the counter doesn’t match.

2. **Generate and verify an attestation token**: On your dev board (e.g., STM32L562E-DK), call `psa_initial_attestation_get_token()` with a fixed challenge. Dump the token to UART, then use the Python `cbor` library to decode the CWT and inspect the claims.

3. **Stress-test secure storage**: Write a loop that calls `psa_its_set()` 1000 times with different UIDs. Measure the time per operation. Then try the same with `psa_ps_set()` (Protected Storage) and compare the latency and flash usage.

## Next Up

Tomorrow we shift focus to the boot chain itself: **MCUboot: Bootloader Architecture & Image Slots**. We’ll break down the image slot layout, swap strategies, and how MCUboot validates image signatures before jumping to TF-M.
