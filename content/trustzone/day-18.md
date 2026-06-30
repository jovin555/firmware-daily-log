---
title: "Day 18: Key Management Infrastructure: HSM & PKCS#11"
date: 2026-06-30
tags: ["til", "trustzone", "hsm", "pkcs11", "provisioning"]
---

## What I Explored Today

Today I dug into the hardware root of trust for key management — specifically how Hardware Security Modules (HSMs) and the PKCS#11 standard work together to protect the signing keys used in TrustZone Secure Boot chains. In production, you never store private keys in plaintext on a build server. HSMs provide tamper-resistant key storage, and PKCS#11 gives a standardized API to interact with them. I spent the day setting up a SoftHSM (software HSM for testing) and using `pkcs11-tool` to generate and export RSA keys for signing boot images.

## The Core Concept

The entire Secure Boot chain — from BootROM to TrustZone firmware — relies on asymmetric signatures. If an attacker steals the private signing key, they can sign malicious firmware and bypass all boot integrity checks. This is where an HSM becomes non-negotiable.

An HSM is a dedicated hardware appliance (or chip) that generates, stores, and uses cryptographic keys *without ever exposing the private key material to the host CPU*. The key never leaves the HSM boundary. PKCS#11 (Cryptoki) is the standard API that lets software request signing operations without seeing the key. In a TrustZone provisioning pipeline, you use PKCS#11 to:

- Generate key pairs inside the HSM (C_GenerateKeyPair)
- Sign firmware hashes (C_Sign)
- Export only the public key for embedding into BootROM or fuse storage

The critical property is **key usage separation**: the HSM enforces that a key marked `CKA_SIGN` cannot be used for encryption, and `CKA_EXTRACTABLE` controls whether the private key can be exported (ideally `CK_FALSE` for production).

## Key Commands / Configuration / Code

### 1. Setting up SoftHSM for development

```bash
# Install SoftHSM2 (software HSM for testing)
sudo apt install softhsm2

# Initialize a token (slot) with a SO PIN and user PIN
softhsm2-util --init-token --slot 0 --label "TrustZoneSigning" \
  --so-pin 123456 --pin 87654321

# List available slots
pkcs11-tool --module /usr/lib/softhsm/libsofthsm2.so --list-slots
```

### 2. Generate an RSA-4096 signing key pair inside the HSM

```bash
# Generate RSA key pair with PKCS#11 attributes:
# - CKA_TOKEN=true  (key stays in HSM)
# - CKA_SIGN=true   (allowed to sign)
# - CKA_EXTRACTABLE=false (private key never exported)
pkcs11-tool --module /usr/lib/softhsm/libsofthsm2.so \
  --login --pin 87654321 \
  --keypairgen --key-type rsa:4096 \
  --id 01020304 --label "boot-signing-key" \
  --usage-sign --extractable=false
```

### 3. Sign a firmware hash using the HSM-resident key

```bash
# Compute SHA-256 hash of the firmware binary
sha256sum firmware.bin | cut -d' ' -f1 > firmware.hash

# Sign the hash using the HSM (output in PKCS#1 v1.5 format)
pkcs11-tool --module /usr/lib/softhsm/libsofthsm2.so \
  --login --pin 87654321 \
  --sign --mechanism RSA-PKCS \
  --id 01020304 \
  --input-file firmware.hash \
  --output-file firmware.sig
```

### 4. Export the public key (only public, never private)

```bash
# Extract the public key in DER format for embedding into BootROM
pkcs11-tool --module /usr/lib/softhsm/libsofthsm2.so \
  --login --pin 87654321 \
  --read-object --id 01020304 --type pubkey \
  --output-file boot_pubkey.der

# Convert to PEM for inspection
openssl rsa -pubin -inform DER -outform PEM -in boot_pubkey.der -out boot_pubkey.pem
```

### 5. PKCS#11 C code snippet (conceptual for embedded integration)

```c
#include <pkcs11.h>

CK_FUNCTION_LIST_PTR p11; // loaded via C_GetFunctionList
CK_SESSION_HANDLE session;
CK_OBJECT_HANDLE privKey;

// Open session and login
p11->C_OpenSession(slotID, CKF_SERIAL_SESSION | CKF_RW_SESSION,
                   NULL, NULL, &session);
p11->C_Login(session, CKU_USER, (CK_UTF8CHAR_PTR)"87654321", 8);

// Find the private key by label
CK_ATTRIBUTE searchTemplate[] = {
    {CKA_CLASS, &privClass, sizeof(privClass)},
    {CKA_LABEL, "boot-signing-key", 16}
};
p11->C_FindObjectsInit(session, searchTemplate, 2);
p11->C_FindObjects(session, &privKey, 1, &objCount);

// Sign the hash
CK_BYTE hash[] = {0xab, 0xcd, ...}; // 32 bytes SHA-256
CK_BYTE signature[512];
CK_ULONG sigLen = sizeof(signature);
CK_MECHANISM mech = {CKM_RSA_PKCS, NULL_PTR, 0};

p11->C_SignInit(session, &mech, privKey);
p11->C_Sign(session, hash, 32, signature, &sigLen);

// Cleanup
p11->C_FindObjectsFinal(session);
p11->C_Logout(session);
p11->C_CloseSession(session);
```

## Common Pitfalls & Gotchas

1. **SoftHSM vs. real HSM behavior**: SoftHSM stores keys in files on disk, protected only by the PIN. A production HSM (e.g., Nitrokey, YubiHSM, Thales) uses tamper-resistant hardware. Never assume SoftHSM security properties apply to production. Always test with the target HSM model.

2. **Key attribute misconfiguration**: If you forget `CKA_SIGN=true` or set `CKA_EXTRACTABLE=true` on a production HSM, you may either fail to sign or accidentally expose the private key. Always double-check attributes with `pkcs11-tool --list-objects --id <id>` after generation.

3. **PKCS#11 session management**: Many engineers forget to call `C_Logout` and `C_CloseSession`. In a production pipeline, leaving sessions open can exhaust HSM resources (most HSMs have a limited number of concurrent sessions). Always implement proper session cleanup, especially in CI/CD scripts.

## Try It Yourself

1. **Set up SoftHSM and generate a key pair** with `CKA_EXTRACTABLE=false`. Attempt to export the private key using `pkcs11-tool --read-object --type privkey`. Observe the error — this is the security property you want in production.

2. **Sign a firmware hash and verify it** using OpenSSL with the exported public key. This validates that the HSM signature is standard PKCS#1 v1.5 and can be verified by a BootROM verifier.

3. **Write a short Python script** using `python-pkcs11` (or `PyKCS11`) that generates a key pair, signs a hash, and exports the public key. Run it against SoftHSM, then modify it to use a real HSM if you have one available.

## Next Up

Tomorrow: **Firmware Encryption: Confidentiality for IP Protection** — we'll move beyond signing to encrypting firmware images so that even if the flash is dumped, the code remains secret. We'll cover AES-GCM key wrapping, TrustZone's on-the-fly decryption, and how to combine encryption with signing for authenticated confidentiality.
