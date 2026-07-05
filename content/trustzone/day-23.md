---
title: "Day 23: Secure Boot Concepts: Chain of Trust, Keys & Attestation"
date: 2026-07-05
tags: ["til", "trustzone", "secure-boot", "chain-of-trust"]
---

## What I Explored Today

Today I dug into the foundational mechanics of secure boot—specifically how the chain of trust is constructed, how key material is managed across boot stages, and what attestation actually proves. I’ve implemented secure boot on Cortex-M and Cortex-A platforms before, but I wanted to formalize my understanding of the cryptographic handoffs between boot ROM, bootloader, and OS loader. The key insight: secure boot isn’t about preventing code from being read; it’s about preventing *unauthenticated* code from executing. Attestation then proves that this authentication happened correctly to a remote verifier.

## The Core Concept

Secure boot solves a simple but critical problem: how does the device know that the code it’s about to run is the code the manufacturer intended? The answer is a **chain of trust**—a sequence of cryptographic verifications where each stage measures and validates the next stage before handing over control.

The chain starts in immutable hardware: the **Boot ROM** (sometimes called ROM bootloader or RBL). This code is burned into silicon and cannot be modified. The Boot ROM contains a public key (or a hash of it) that it uses to verify the first-stage bootloader (FSBL). The FSBL then verifies the next stage (e.g., U-Boot or TF-A), which verifies the OS kernel, and so on. Each link in the chain is a signature verification using asymmetric cryptography (typically RSA or ECDSA).

**Why asymmetric?** Because the private key used to sign firmware images can be kept offline, secure in a hardware security module (HSM) during manufacturing. The public key lives on the device. Even if an attacker dumps the flash, they only get the public key, which can’t be used to sign malicious images.

**Attestation** is the proof that this chain completed successfully. It typically works by having the boot stages record measurements (hashes of code and configuration) into tamper-resistant registers (like TrustZone’s TZASC or a dedicated TPM). A remote server can then request a signed quote of these measurements. If the quote matches the expected golden values, the server knows the device booted the intended software stack.

## Key Commands / Configuration / Code

Below is a practical example of how a Boot ROM might verify an FSBL using RSA-2048 PKCS#1 v1.5 signature verification. This is representative of what you’d see in a real ROM implementation (e.g., i.MX, STM32MP1, or TI Sitara).

```c
// Simplified Boot ROM FSBL verification (pseudocode, but based on real implementations)
#include "rom_api.h"  // Provided by silicon vendor

// The Boot ROM's embedded public key (burned in OTP or eFuses)
// In practice, this is stored as a hash of the key, not the full key,
// to save space. The full key is passed in the image header.
#define ROM_PUB_KEY_HASH {0xA1, 0xB2, 0xC3, 0xD4, ...}  // SHA-256 of DER-encoded public key

typedef struct {
    uint32_t image_size;          // Size of the FSBL binary
    uint8_t  signature[256];      // RSA-2048 signature (256 bytes)
    uint8_t  public_key[294];     // DER-encoded RSA public key (294 bytes for 2048-bit)
    uint8_t  pub_key_hash[32];    // SHA-256 of the public key, for match against ROM
    uint32_t version;             // Anti-rollback version number
} fsbl_header_t;

int boot_rom_verify_fsbl(uint32_t fsbl_base_addr) {
    fsbl_header_t *hdr = (fsbl_header_t *)fsbl_base_addr;
    uint8_t *fsbl_binary = (uint8_t *)(fsbl_base_addr + sizeof(fsbl_header_t));

    // Step 1: Verify the public key matches the ROM's root of trust
    uint8_t computed_hash[32];
    sha256_compute(hdr->public_key, sizeof(hdr->public_key), computed_hash);
    if (memcmp(computed_hash, ROM_PUB_KEY_HASH, 32) != 0) {
        return ERR_KEY_MISMATCH;  // Public key not authorized by ROM
    }

    // Step 2: Verify the signature over the FSBL binary
    // The signature covers: image_size || version || fsbl_binary
    uint8_t *message = build_message(hdr->image_size, hdr->version, fsbl_binary);
    uint32_t msg_len = sizeof(hdr->image_size) + sizeof(hdr->version) + hdr->image_size;

    if (rsa_pkcs1_v15_verify(hdr->public_key, hdr->signature, message, msg_len) != 0) {
        return ERR_SIG_INVALID;   // Image tampered or wrong key
    }

    // Step 3: Check anti-rollback version (against OTP fuses)
    if (hdr->version < read_otp_min_version()) {
        return ERR_VERSION_ROLLBACK;
    }

    // Success: hash the public key into a measurement register for attestation
    tpm_extend(TPM_PCR_0, computed_hash, 32);

    // Jump to FSBL entry point
    jump_to(fsbl_base_addr + sizeof(fsbl_header_t));
    return 0;  // Never reached
}
```

**Key details:**
- The public key is stored *in the image header*, not in ROM. ROM only stores a hash of the authorized key. This allows key rotation without changing silicon.
- The signature covers the image content *and* the version number, preventing rollback attacks.
- The `tpm_extend()` call records the measurement into a Platform Configuration Register (PCR). This is how attestation works: the PCR accumulates hashes of every boot stage.

For attestation, a remote verifier would later request a signed PCR quote:

```bash
# Example using a TPM2 tool on a running Linux system
# The TPM signs the current PCR values with its Attestation Identity Key (AIK)
tpm2_quote -c 0x81000001 -l sha256:0,1,2 -q "nonce_from_server" -m quote.msg -s quote.sig

# The server verifies:
# 1. The signature is valid under the device's AIK certificate
# 2. The quoted PCR values match the expected golden measurements
# 3. The nonce prevents replay attacks
```

## Common Pitfalls & Gotchas

1. **Public key hash vs. full key in ROM.** I’ve seen teams burn the full RSA public key into OTP fuses. This wastes fuses (294 bytes for RSA-2048) and makes key rotation impossible. Always store a hash (32 bytes for SHA-256) and put the full key in the image header. The hash is your root of trust.

2. **Signature verification before anti-rollback check.** If you check the version number *before* verifying the signature, an attacker can feed you a validly-signed older image with a high version number. Always verify the signature first, then check the version. The version must be part of the signed data, not a separate field.

3. **Attestation without a nonce.** If your attestation protocol doesn’t include a fresh random nonce from the verifier, an attacker can replay an old attestation quote from a compromised device. The TPM quote command above includes `-q "nonce_from_server"` for exactly this reason.

## Try It Yourself

1. **Simulate a chain of trust with OpenSSL.** Generate an RSA-2048 key pair. Create a small binary (e.g., a "hello world" ELF). Sign it with `openssl dgst -sha256 -sign private.pem -out sig.bin binary.bin`. Then write a Python script that verifies the signature using the public key. This is exactly what a Boot ROM does.

2. **Extend the code example above** to add a second stage. After the FSBL runs, have it verify a kernel image using the same public key (or a different key stored in the FSBL). Print "Chain OK" if all signatures pass. This will teach you how measurement registers accumulate.

3. **Set up a TPM quote/verify loop** using a software TPM (swtpm) on a Linux VM. Write a script that extends a PCR with a known hash, quotes it with a nonce, and verifies the quote against the public key. This is the exact flow used in remote attestation (e.g., Android Verified Boot, Azure Sphere).

## Next up

Tomorrow, we’ll drop down to the hardware level: **ARM Cortex-M Security: SAU, IDAU & TrustZone-M**. We’ll look at how the Security Attribution Unit and Implementation Defined Attribution Unit partition memory into Secure and Non-Secure worlds, and how this interacts with the secure boot chain we just built. Bring your reference manual.
