---
title: "Day 02: Secure Boot Concepts: Chain of Trust, Keys & Attestation"
date: 2026-06-14
tags: ["til", "trustzone", "secure-boot", "chain-of-trust"]
---

## What I Explored Today

Today I dug into the cryptographic backbone of secure boot: how a chain of trust is constructed, the key hierarchy that makes it tamper-resistant, and the attestation mechanisms that let a device prove its boot state to a remote verifier. I focused on the practical implementation details—what keys live where, how signatures are verified at each stage, and what actually happens when a root of trust is compromised.

## The Core Concept

Secure boot isn't about preventing someone from flashing malicious firmware—it's about making unauthorized firmware execution computationally infeasible. The chain of trust solves a fundamental bootstrapping problem: how can a device with no prior knowledge verify the authenticity of code it has never seen before?

The answer is a layered key hierarchy. At the silicon level, a hardware root of trust (usually an immutable boot ROM) contains a public key hash or certificate. This ROM is the only code that is implicitly trusted. Every subsequent stage must prove its integrity before execution is allowed.

The chain works like this:
1. **Boot ROM** (immutable) verifies the first-stage bootloader (FSBL) using the SoC's public key.
2. **FSBL** verifies the next stage (e.g., U-Boot or TF-A) using a key provisioned during manufacturing.
3. **Bootloader** verifies the OS kernel or application firmware.
4. **OS/runtime** can verify signed updates or authenticated variables.

Attestation extends this: after boot completes, the device generates a signed report containing measurements (hashes) of each boot stage. A remote server can verify this report against known-good values to confirm the device booted into an expected state.

## Key Commands / Configuration / Code

### 1. Key Generation for Secure Boot (using OpenSSL)

Most SoCs require RSA-2048 or ECDSA-P256 keys. Here's how to generate a proper key pair for NXP i.MX or STM32MP1 platforms:

```bash
# Generate a 2048-bit RSA private key with PKCS#8 format
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -outform PEM -out boot_private_key.pem

# Extract the public key in DER format (what the ROM expects)
openssl rsa -pubout -in boot_private_key.pem -outform DER \
  -out boot_public_key.der

# Hash the public key for fuse programming (on i.MX)
sha256sum boot_public_key.der | cut -d' ' -f1 > pubkey_hash.txt
```

### 2. Signing a Boot Image (using Python + cryptography)

A simplified signing routine for a TF-A (Trusted Firmware-A) BL2 image:

```python
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
import struct

def sign_boot_image(image_path: str, key_path: str, output_path: str):
    # Load private key
    with open(key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(
            f.read(), password=None, backend=default_backend()
        )
    
    # Read image and compute hash
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # Hash the image (SHA-256)
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(image_data)
    image_hash = digest.finalize()
    
    # Sign the hash
    signature = private_key.sign(
        image_hash,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    
    # Write signed image: [signature (256 bytes)] [image]
    with open(output_path, "wb") as f:
        f.write(signature)
        f.write(image_data)
    
    print(f"Signed image written to {output_path}")
    print(f"Image hash: {image_hash.hex()}")

# Usage
sign_boot_image("bl2.bin", "boot_private_key.pem", "bl2_signed.bin")
```

### 3. Attestation Report Generation (simplified TPM-style)

On a device with a TPM or HSM, a remote attestation flow:

```c
// Pseudocode for generating an attestation quote
#include <tss2/tss2_esys.h>

ESYS_CONTEXT *ctx;
ESYS_TR key_handle;
TPM2B_ATTEST *quote;
TPMT_SIGNATURE *signature;

// Load attestation key (EK or AK)
Tss2_Esys_Load(ctx, ESYS_TR_RH_OWNER, ESYS_TR_PASSWORD,
               &in_private, &in_public, &key_handle, NULL);

// Generate quote over PCR values (boot measurements)
TPML_PCR_SELECTION pcr_sel = {
    .count = 1,
    .pcrSelections[0] = {
        .hash = TPM2_ALG_SHA256,
        .sizeofSelect = 3,
        .pcrSelect = {0xFF, 0x00, 0x00}  // PCRs 0-7
    }
};

Tss2_Esys_Quote(ctx, key_handle, ESYS_TR_PASSWORD,
                ESYS_TR_NONE, ESYS_TR_NONE,
                &pcr_sel, &extra_data, &quote, &signature);

// Send quote + signature to verifier
send_attestation_report(quote, signature);
```

## Common Pitfalls & Gotchas

**1. Fuse programming is irreversible.** Once you blow OTP fuses with your public key hash, there's no recovery. If you lose the private key, the device becomes a brick. Always test with development fuses (if available) or use a hardware security module (HSM) to protect production keys.

**2. Signature verification timeout in boot ROM.** Many boot ROMs have a strict timeout for signature verification (e.g., 100ms on some STM32 parts). If your signing algorithm is too slow (e.g., RSA-4096 on a Cortex-M4), the boot ROM may abort before verification completes. Profile your signing time with the actual silicon, not the emulator.

**3. Attestation freshness is often forgotten.** A replay attack on attestation reports is trivial if there's no nonce. Always include a random challenge from the verifier in the signed quote. Without it, an attacker can capture a valid attestation from a known-good boot and replay it after compromising the device.

## Try It Yourself

1. **Generate a key pair and sign a dummy boot image.** Use the OpenSSL commands above to create RSA-2048 keys. Write a 64-byte "bootloader" binary (any data), sign it, and verify the signature using the public key. Confirm that tampering with the image causes verification to fail.

2. **Extract and inspect the public key hash from a real SoC datasheet.** Download the reference manual for an STM32MP157 or i.MX8M Mini. Find the section on "Secure Boot" or "OTP Controller." Identify which fuses store the public key hash and how many bits are allocated.

3. **Simulate a chain of trust with nested signatures.** Create three stages: ROM (unsigned), BL1 (signed by ROM key), BL2 (signed by BL1 key). Write a script that verifies each stage's signature before passing control. Measure the time overhead of each verification step.

## Next Up

Tomorrow, we dive into ARM Cortex-M security extensions: how the SAU (Security Attribution Unit) and IDAU (Implementation Defined Attribution Unit) partition memory into Secure and Non-Secure worlds, and how TrustZone-M differs from its Cortex-A counterpart. We'll walk through configuring MPU regions for isolation and see why this matters for IoT firmware.
