---
title: "Day 14: Key Provisioning: Factory Injection & Per-Device Keys"
date: 2026-07-14
tags: ["til", "embedded-crypto", "provisioning", "per-device-keys"]
---

## What I Explored Today

Today I dove into the factory-floor reality of key provisioning—specifically how to inject unique cryptographic keys into each device during manufacturing. I've been reading about HSM-backed provisioning flows, the difference between symmetric and asymmetric per-device keys, and the critical role of a secure provisioning server. The key insight: every device leaving the factory must have a unique identity that cannot be cloned, and that starts with how you inject keys at the very last step of assembly.

## The Core Concept

Most embedded security failures don't come from broken algorithms—they come from shared secrets. If every device in your fleet uses the same AES-128 key to decrypt firmware updates, one compromised unit breaks the entire fleet. Per-device keys solve this, but they introduce a provisioning problem: how do you securely inject a unique key into each device at scale, without exposing the key material to the factory floor?

The answer is a three-layer architecture:
1. **Provisioning Server** — A hardened machine (often with an HSM) that generates per-device keys and signs device certificates.
2. **Factory Tool** — A trusted application that talks to the device over a secure channel (e.g., JTAG, SWD, or a dedicated provisioning bus).
3. **Device Boot ROM** — Immutable code that accepts the key injection and locks it into OTP (one-time programmable) fuses or a secure element.

The protocol typically works like this: the device generates an ephemeral key pair, sends its public key to the provisioning server, the server encrypts the per-device key with that ephemeral public key, and the device decrypts and burns it into fuses. This way, the key material never exists in plaintext on the factory network.

## Key Commands / Configuration / Code

Here's a realistic example using OpenSSL to simulate the server-side key generation and wrapping, followed by a C snippet for the device-side injection.

**Server-side (Python with OpenSSL bindings):**
```python
import os
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives import serialization, hashes

# Generate per-device AES-256 key
device_key = os.urandom(32)  # 256-bit key

# Load device's ephemeral public key (sent during provisioning handshake)
with open("device_ephemeral_pub.pem", "rb") as f:
    device_pub = serialization.load_pem_public_key(f.read())

# Wrap the device key using ECDH + AES-KW (RFC 3394)
from cryptography.hazmat.primitives.keywrap import aes_key_wrap
shared_secret = device_pub.exchange(ec.ECDH(), server_ephemeral_priv)
wrapping_key = shared_secret[:16]  # First 16 bytes as AES-128 key
wrapped_key = aes_key_wrap(wrapping_key, device_key)

# Send wrapped_key to device over factory bus
print(f"Wrapped key (hex): {wrapped_key.hex()}")
```

**Device-side (C with hardware crypto peripheral):**
```c
#include "hal_crypto.h"  // Hardware abstraction for AES + ECC

#define OTP_FUSE_ADDR 0x1FFF7000  // Example OTP region on STM32

int provision_device(uint8_t *wrapped_key, size_t wrapped_len) {
    uint8_t shared_secret[32];
    uint8_t wrapping_key[16];
    uint8_t device_key[32];
    
    // Step 1: Perform ECDH with server's ephemeral public key
    // (server_pub_key is pre-loaded in boot ROM or sent alongside wrapped key)
    if (hal_ecdh_compute_shared(server_pub_key, &device_eph_priv, shared_secret) != 0)
        return -1;  // ECDH failed
    
    // Step 2: Derive wrapping key (first 16 bytes of shared secret)
    memcpy(wrapping_key, shared_secret, 16);
    
    // Step 3: Unwrap the device key using AES-KW
    if (hal_aes_key_unwrap(wrapping_key, wrapped_key, wrapped_len, device_key) != 0)
        return -2;  // Unwrap failed (tampered data?)
    
    // Step 4: Burn device key into OTP fuses (one-time, irreversible)
    for (int i = 0; i < 32; i++) {
        *((volatile uint8_t *)OTP_FUSE_ADDR + i) = device_key[i];
    }
    
    // Step 5: Lock OTP region to prevent re-read
    hal_otp_lock_region(OTP_FUSE_ADDR, 32);
    
    // Step 6: Zeroize temporary buffers
    memset(shared_secret, 0, 32);
    memset(wrapping_key, 0, 16);
    memset(device_key, 0, 32);
    
    return 0;  // Success
}
```

**Factory tool command (using OpenOCD for STM32):**
```bash
# Load wrapped key into RAM at 0x20000000, then trigger boot ROM provisioning
openocd -f interface/stlink.cfg -f target/stm32h7x.cfg \
  -c "init" \
  -c "halt" \
  -c "load_image wrapped_key.bin 0x20000000" \
  -c "resume 0x1FFF0000"  # Boot ROM entry point for provisioning
```

## Common Pitfalls & Gotchas

1. **OTP fuse readback after locking** — Some MCUs allow reading OTP fuses even after locking if you use a debugger in the right mode. Always verify that the lock mechanism truly disables readback (check the errata sheet). I've seen a production line where the lock bit didn't apply to the debug interface—every device's key was dumpable via SWD.

2. **Shared secret reuse across devices** — If your provisioning server uses the same ephemeral key pair for every device, an attacker who compromises one device can decrypt all future provisioning sessions. Always generate a fresh ephemeral key pair per device.

3. **Timing attacks on the unwrap step** — The AES-KW unwrap operation must be constant-time. If your hardware crypto peripheral doesn't guarantee this, an attacker on the factory bus can measure power consumption during unwrap and recover the wrapping key. Use a constant-time implementation or a dedicated secure element.

## Try It Yourself

1. **Simulate a provisioning handshake** — Use OpenSSL to generate an ephemeral ECDH key pair, then write a Python script that wraps a random 32-byte key and unwraps it. Verify the round-trip works.

2. **Check your MCU's OTP behavior** — Read the reference manual for your target MCU. Find the OTP fuse address range and the lock mechanism. Write a test firmware that burns a test pattern and attempts to read it back after locking.

3. **Audit your factory tool** — If you have access to a production line, review the provisioning script. Does it generate a new ephemeral key per device? Is the wrapped key transmitted over a physically isolated bus (not Wi-Fi or Ethernet)?

## Next Up

Tomorrow: **Key Rotation & Lifecycle Management in the Field** — how to securely update device keys after deployment without breaking the trust chain, including remote attestation and secure boot rollback protection.
