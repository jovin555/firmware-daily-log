---
title: "Day 13: Key Storage: Secure Elements, TPMs & OTP Fuses"
date: 2026-07-13
tags: ["til", "embedded-crypto", "secure-element", "tpm"]
---

## What I Explored Today

Today I dug into the hardware-level options for storing cryptographic keys in embedded systems. I’ve been relying on software keyrings and flash-based storage for years, but after a recent audit flagged our key material as extractable via JTAG, I needed real hardware protection. I explored three tiers: Secure Elements (dedicated crypto chips), TPMs (trusted platform modules with full PKI stacks), and OTP fuses (one-time programmable memory in MCUs). Each has distinct trade-offs in cost, security, and integration complexity.

## The Core Concept

The fundamental problem with key storage is that any persistent memory readable by the CPU is also readable by an attacker with physical access. Flash, EEPROM, and even internal SRAM can be dumped via debug interfaces, voltage glitching, or focused ion beam (FIB) attacks. The solution is to store keys in a physically isolated boundary where they never leave as plaintext—operations are performed inside the boundary, and only results (signatures, decrypted data) are exposed.

**Secure Elements** are tiny, tamper-resistant microcontrollers with their own CPU, memory, and crypto accelerators. They communicate over I2C or SPI and are designed to resist side-channel and physical attacks. Think of them as a vault that hands you the contents of a box without ever showing you the key.

**TPMs** are a superset of secure elements, standardized by the TCG. They add platform-level features: PCR (Platform Configuration Registers) for measured boot, monotonic counters, and attestation. They are mandatory in many enterprise PCs but are increasingly available for embedded Linux systems.

**OTP fuses** are one-time programmable bits inside the MCU itself. They are cheap and fast, but once blown, they cannot be changed. They are ideal for device-unique secrets like a root key or a serial number that must survive a full flash erase.

The key insight: **never store a key where the CPU can read it directly**. Use a secure boundary that exposes only an API for crypto operations.

## Key Commands / Configuration / Code

### 1. Using a Secure Element (Microchip ATECC608A) with I2C

```c
// Initialize the ATECC608A over I2C
#include "atecc608a.h"

// Configuration zone must be locked before use
// This is done once at manufacturing
uint8_t config_zone[128] = {0};
// Set slot 0 for ECDSA P256 private key storage
config_zone[20] = 0x02; // SlotConfig: ECDSA private key, external signature
config_zone[96] = 0x55; // LockValue: lock config zone

// Lock the configuration (irreversible)
if (atecc_write_config_zone(config_zone) != ATECC_SUCCESS) {
    // Handle error
}
if (atecc_lock_config_zone() != ATECC_SUCCESS) {
    // Handle error
}

// Generate a key inside slot 0 (never leaves the chip)
uint8_t public_key[64];
if (atecc_genkey(0, public_key) != ATECC_SUCCESS) {
    // Handle error
}
// public_key is the only key material we ever see
```

### 2. Using a TPM (Infineon SLB9670) via Linux `tpm2-tools`

```bash
# Create a primary key under the TPM's storage hierarchy
# The key is bound to the TPM and cannot be extracted
tpm2_createprimary -c primary.ctx -P "str:my_secret" -g sha256 -G rsa2048

# Create a child signing key, also non-exportable
tpm2_create -C primary.ctx -G rsa2048 -g sha256 -u key.pub -r key.priv -a "sign"

# Load the key into the TPM
tpm2_load -C primary.ctx -u key.pub -r key.priv -c key.ctx

# Sign a hash (the TPM does the operation, we only get the signature)
echo "data_to_sign" | openssl dgst -sha256 -binary | \
    tpm2_sign -c key.ctx -g sha256 -o signature.bin
```

### 3. Blowing OTP Fuses on an STM32H7

```c
// STM32H7 OTP is organized as 16 bytes per word, 64 words total
// OTP lock register (OTP_LOCK) prevents further writes

#define OTP_BASE_ADDR 0x1FF0F000
#define OTP_LOCK_ADDR 0x1FF0F800

// Write a 64-bit root key to OTP word 0
volatile uint32_t *otp_word0 = (uint32_t *)OTP_BASE_ADDR;
uint32_t key_low = 0xDEADBEEF;
uint32_t key_high = 0xCAFEBABE;

// Write key (only works if OTP is not yet locked)
*otp_word0 = key_low;
*(otp_word0 + 1) = key_high;

// Lock OTP to prevent any further writes
volatile uint32_t *otp_lock = (uint32_t *)OTP_LOCK_ADDR;
*otp_lock = 0x00000001; // Lock word 0 only

// After locking, reads still work but writes are ignored
// The key is now permanent and survives JTAG erase
```

## Common Pitfalls & Gotchas

1. **OTP fuses are not tamper-proof against voltage glitching.** If an attacker can glitch the power rail during a write, they may skip the lock step. Always verify the lock register after programming, and consider using a hardware watchdog to abort if the lock sequence takes too long.

2. **TPM keys can be duplicated if you use the wrong policy.** The default `tpm2_create` with no policy allows the key to be duplicated under certain hierarchies. Always set `-a "fixedtpm|fixedparent|sign"` to bind the key to the specific TPM and prevent migration.

3. **Secure Elements require careful I2C bus isolation.** If the attacker can probe the I2C lines, they can replay commands or inject faults. Use a dedicated I2C bus with pull-ups only on the secure element side, and consider adding a bus switch that is disabled during debug modes.

## Try It Yourself

1. **Read the datasheet for your MCU’s OTP.** Find the OTP base address and lock register. Write a test program that stores a dummy key and then attempts to overwrite it. Verify that the lock works as expected.

2. **Set up a Microchip ATECC608A on a breakout board.** Use the Microchip CryptoAuth Library to generate an ECDSA key pair inside slot 0. Sign a test message and verify the signature using the public key you retrieved.

3. **If you have a Linux system with a TPM 2.0**, run `tpm2_getcap handles-persistent` to see existing keys. Then create a primary key with a policy that prevents duplication, and sign a file. Use `tpm2_verifysignature` to confirm the signature is valid.

## Next Up

Tomorrow: **Key Provisioning: Factory Injection & Per-Device Keys**. We’ll cover how to securely inject unique keys into thousands of devices on a production line, including HSM-backed provisioning, key diversification, and avoiding the “one key fits all” disaster.
