---
title: "Day 04: Image Metadata & Manifests: Versioning, Hashes & Signatures"
date: 2026-07-04
tags: ["til", "secure-ota", "manifest", "versioning"]
---

## What I Explored Today

Today I dug into the metadata layer that sits between the OTA orchestrator and the raw firmware binary. Without a well-structured manifest, you're flying blind — you can't verify what you're about to flash, you can't roll back safely, and you certainly can't prove to a fleet manager that every device is running the intended payload. I spent the day building a minimal manifest schema, signing it with ECDSA, and validating it on the target side. The key insight: the manifest is the single source of truth for *what*, *when*, and *who* — and it must be tamper-evident.

## The Core Concept

A firmware image is just bytes. A manifest is a structured document that describes those bytes: version, hash, signature, target hardware, dependencies, and metadata like release date or build ID. The manifest is what you sign, not the image itself. This decoupling matters because:

- **Versioning**: You need monotonic version numbers to enforce rollback protection. Semantic versioning (e.g., `2.1.0`) is insufficient for embedded — you need a monotonically increasing integer that the bootloader can compare without parsing strings.
- **Hashes**: The manifest contains a SHA-256 (or SHA-512) hash of the firmware image. The bootloader reads the manifest, computes the hash of the downloaded image, and compares. If they mismatch, the update is rejected before any flash write occurs.
- **Signatures**: The manifest is signed with a private key (e.g., ECDSA P-256). The bootloader holds the corresponding public key in read-only memory. This proves the manifest (and by extension the image) came from a trusted source.

The critical chain: **trust the public key → verify manifest signature → trust manifest hash → verify image integrity**. Break any link and the system is compromised.

## Key Commands / Configuration / Code

### 1. Manifest Schema (JSON)

```json
{
  "manifest_version": 1,
  "firmware_version": 42,          // monotonic integer, not semver
  "hardware_id": "stm32h743-v2",
  "image_size": 524288,            // bytes
  "image_hash_algorithm": "sha256",
  "image_hash": "a1b2c3d4...",    // hex-encoded SHA-256
  "timestamp": 1688496000,         // Unix epoch
  "dependencies": {
    "min_bootloader_version": 5,
    "required_config_version": 3
  },
  "signature": "..."               // ECDSA P-256 signature over all above fields
}
```

### 2. Signing the Manifest (Python with `cryptography`)

```python
from cryptography.hazmat.primitives import hashes, asymmetric
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import json, hashlib

def sign_manifest(manifest_dict: dict, private_key_path: str) -> dict:
    # Load ECDSA P-256 private key
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    
    # Canonicalize: sort keys, no whitespace
    manifest_bytes = json.dumps(manifest_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
    
    # Sign the canonical bytes
    signature = private_key.sign(
        manifest_bytes,
        ec.ECDSA(hashes.SHA256())
    )
    
    manifest_dict["signature"] = signature.hex()
    return manifest_dict

# Usage
manifest = {
    "firmware_version": 42,
    "hardware_id": "stm32h743-v2",
    "image_hash": hashlib.sha256(open("firmware.bin", "rb").read()).hexdigest(),
    # ... other fields
}
signed_manifest = sign_manifest(manifest, "ota_private.pem")
with open("manifest.json", "w") as f:
    json.dump(signed_manifest, f, indent=2)
```

### 3. Bootloader-Side Verification (C with Mbed TLS)

```c
#include <mbedtls/pk.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/sha256.h>
#include <cJSON.h>

bool verify_manifest(const uint8_t *manifest_raw, size_t manifest_len,
                     const uint8_t *public_key_der, size_t key_len) {
    // Parse JSON
    cJSON *root = cJSON_ParseWithLength((char*)manifest_raw, manifest_len);
    if (!root) return false;
    
    // Extract signature
    const char *sig_hex = cJSON_GetObjectItem(root, "signature")->valuestring;
    uint8_t sig_buf[64]; // P-256 signature is 64 bytes
    hex_decode(sig_hex, sig_buf, 64);
    
    // Remove signature field from JSON for verification
    cJSON_DeleteItemFromObject(root, "signature");
    char *canonical = cJSON_PrintUnformatted(root);
    
    // Compute hash of canonical manifest
    uint8_t hash[32];
    mbedtls_sha256((uint8_t*)canonical, strlen(canonical), hash, 0);
    
    // Verify with public key
    mbedtls_pk_context pk;
    mbedtls_pk_init(&pk);
    mbedtls_pk_parse_public_key(&pk, public_key_der, key_len);
    
    int ret = mbedtls_pk_verify(&pk, MBEDTLS_MD_SHA256, hash, 32, sig_buf, 64);
    
    mbedtls_pk_free(&pk);
    cJSON_Delete(root);
    free(canonical);
    
    return ret == 0;
}
```

## Common Pitfalls & Gotchas

1. **Canonicalization Mismatch**: If the signing tool and the bootloader serialize JSON differently (e.g., key order, whitespace), the signature will fail. Always use the same serialization library with `sort_keys=True` and no whitespace on both sides. I wasted two hours on this because Python's `json.dumps` defaulted to alphabetically sorted keys but my C parser used insertion order.

2. **Hash Algorithm Agility**: Don't hardcode SHA-256 in the bootloader. Put the algorithm identifier in the manifest. When SHA-256 inevitably gets deprecated, you can migrate without firmware updates on every device. I now include `image_hash_algorithm` as a field and maintain a lookup table in the bootloader.

3. **Signature Size Assumptions**: ECDSA P-256 signatures are 64 bytes (r + s, each 32 bytes). But DER-encoded signatures can be 70-72 bytes. If you're storing the signature in a fixed-size field, use raw 64-byte format (r||s) to avoid buffer overflows. My first prototype used DER and caused a stack smash on the bootloader.

## Try It Yourself

1. **Generate a key pair and sign a manifest**: Use OpenSSL to create an ECDSA P-256 key (`openssl ecparam -genkey -name prime256v1 -out ota_private.pem`). Write a Python script that loads a firmware binary, computes its SHA-256, constructs a manifest JSON, and signs it. Verify the signature with `openssl dgst -sha256 -verify ota_public.pem -signature sig.bin manifest.bin`.

2. **Implement manifest version monotonicity**: Add a check in your bootloader that rejects any manifest with `firmware_version <= current_version`. Store the current version in a one-time programmable (OTP) region or a dedicated flash sector. Test with a downgrade attempt.

3. **Cross-verify with a different toolchain**: Sign a manifest with your Python script, then verify it using a C program with Mbed TLS or WolfSSL. Ensure the canonical JSON bytes match exactly by comparing hex dumps. Fix any serialization differences you find.

## Next Up

Tomorrow: **Anti-Rollback Policies: Manifest Versioning & Fleet-Wide Enforcement** — how to design a version counter that survives factory resets, handle fleet-wide minimum version floors, and what happens when a device with version 3 tries to install version 2 (spoiler: it doesn't).
