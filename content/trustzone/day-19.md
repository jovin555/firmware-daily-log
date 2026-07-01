---
title: "Day 19: Firmware Encryption: Confidentiality for IP Protection"
date: 2026-07-01
tags: ["til", "trustzone", "encryption", "ip-protection"]
---

## What I Explored Today

Today I dug into firmware encryption as a confidentiality mechanism for protecting intellectual property (IP) in TrustZone-enabled systems. While Secure Boot ensures *integrity* (the firmware hasn't been tampered with), it does nothing to prevent an attacker from reading the firmware binary off the flash chip, reverse-engineering proprietary algorithms, or extracting hardcoded credentials. I explored how to implement AES-128-CTR encryption of firmware images at rest, using a hardware-bound key stored in the TrustZone secure world, and how the bootROM decrypts the image before authentication. I also tested the practical overhead: on a Cortex-M33 at 200 MHz, decryption of a 256 KB image takes roughly 12 ms with hardware crypto acceleration—negligible for most use cases.

## The Core Concept

The fundamental problem is that flash memory is external and readable. Even with Secure Boot, an attacker can desolder the flash chip, dump its contents via a programmer, and analyze the binary offline. This exposes your proprietary algorithms, license keys, cryptographic secrets, and any "security through obscurity" assumptions.

Firmware encryption solves this by ensuring the firmware image is stored in ciphertext form. Only the bootROM—executing in the most privileged, immutable secure world—holds the decryption key. The key is typically derived from a physically unclonable function (PUF) or fused into eFuses during manufacturing, and is never exposed to the outside world.

The encryption must be done *before* authentication. The standard flow is: decrypt → authenticate → execute. If you authenticate first, the plaintext is exposed in memory before integrity is checked, creating a window for fault injection attacks. The counter mode (CTR) is preferred over CBC because it allows parallel decryption and doesn't require padding, which simplifies the boot flow.

Critically, the encryption key must be bound to the device. If you use a single global key, compromising one device compromises all devices. Hardware unique keys (HUK) derived from PUF or OTP fuses ensure that even if an attacker extracts the key from one chip, it's useless for decrypting firmware from another chip.

## Key Commands / Configuration / Code

### 1. Encrypting Firmware with OpenSSL (Host Side)

```bash
# Generate a 128-bit AES key (must match hardware key slot)
openssl rand -hex 16 > firmware_key.hex

# Encrypt the raw firmware binary using AES-128-CTR
# Nonce: 12 bytes random, counter: 4 bytes starting at 0x00000001
openssl enc -aes-128-ctr \
  -K $(cat firmware_key.hex) \
  -iv 000102030405060708090a0b00000001 \
  -in firmware.bin \
  -out firmware_encrypted.bin

# Append the nonce (first 12 bytes of IV) to the image for bootROM
# BootROM will reconstruct IV as nonce || counter_start
head -c 12 /dev/zero > nonce.bin  # In practice, use actual random nonce
cat nonce.bin firmware_encrypted.bin > firmware_encrypted_with_nonce.bin
```

### 2. BootROM Decryption Pseudocode (Secure World)

```c
// BootROM runs in secure mode, has access to hardware crypto engine
#define AES_KEY_SLOT 0  // eFuse bank 0, programmed at manufacturing
#define NONCE_SIZE 12
#define COUNTER_START 0x00000001

int decrypt_firmware(uint8_t *ciphertext, uint32_t len, uint8_t *plaintext) {
    // Step 1: Extract nonce from first 12 bytes of image
    uint8_t nonce[NONCE_SIZE];
    memcpy(nonce, ciphertext, NONCE_SIZE);
    ciphertext += NONCE_SIZE;
    len -= NONCE_SIZE;

    // Step 2: Configure hardware crypto with device-unique key
    // This key is read from eFuses, never exposed to CPU registers
    hw_crypto_set_key(AES_KEY_SLOT, KEY_TYPE_DEVICE_UNIQUE);

    // Step 3: Set up CTR mode with nonce and initial counter
    hw_crypto_set_mode(AES_CTR);
    hw_crypto_set_iv(nonce, COUNTER_START);  // 12+4 byte IV

    // Step 4: Decrypt in-place (or to separate buffer)
    // Hardware engine handles counter incrementing
    hw_crypto_decrypt(ciphertext, plaintext, len);

    // Step 5: Now authenticate the plaintext (e.g., RSA signature verify)
    return verify_signature(plaintext, len);
}
```

### 3. Device-Specific Key Provisioning (Manufacturing Script)

```bash
# On the manufacturing line, program each device with unique key
# Using JTAG/SWD with debug authentication
# This example uses OpenOCD with a custom TCL script

openocd -f interface/jlink.cfg -f target/stm32h7x.cfg \
  -c "init" \
  -c "halt" \
  -c "stm32h7x otp write 0 0x08 $(cat device_key_1234.hex)" \
  -c "stm32h7x otp lock 0" \
  -c "reset" \
  -c "exit"
```

## Common Pitfalls & Gotchas

1. **Encrypting after signing (wrong order):** If you sign the plaintext and then encrypt, the bootROM must decrypt first, then verify the signature on the decrypted data. This is correct. But if you encrypt first and then sign the ciphertext, the bootROM must verify the signature on ciphertext (which is fine), but then decrypt—and the decrypted plaintext is never authenticated. An attacker can replace the ciphertext with garbage that passes signature verification (since the signature is on the ciphertext, not the plaintext). Always: encrypt → sign the ciphertext, or sign the plaintext → encrypt the signed image.

2. **Reusing nonce across updates:** CTR mode with a fixed key and reused nonce allows trivial XOR-based decryption. If two firmware images are encrypted with the same key and nonce, an attacker can XOR the ciphertexts to cancel the keystream and recover the XOR of the plaintexts. Always generate a fresh random nonce per firmware build, and store it in the image header (not in the key storage).

3. **Key extraction via debug interface:** If your device leaves JTAG/SWD open after manufacturing, an attacker can read the eFuse key directly. Always blow debug authentication fuses or use a debug lock mechanism that requires the same device-unique key to authenticate. On STM32H7, this is the "Debug Authentication" feature using a certificate chain.

## Try It Yourself

1. **Encrypt a test firmware image:** Use OpenSSL to encrypt a 64 KB binary with AES-128-CTR. Write a Python script that prepends a random 12-byte nonce. Verify that decrypting with the same key and nonce recovers the original binary.

2. **Measure decryption overhead:** On your target platform (e.g., STM32H7, i.MX RT), benchmark the hardware crypto engine by decrypting a 256 KB buffer 100 times. Compare with software-only AES. Calculate the percentage of boot time consumed by decryption.

3. **Implement a nonce management scheme:** Design a firmware header format that includes: magic number, version, nonce (12 bytes), encrypted payload length, and signature. Write a host-side tool that builds this header and encrypts the payload. On the target, implement the bootROM parsing and decryption logic.

## Next Up

Tomorrow: **Side-Channel Attacks: Timing & Power Analysis Basics** — We'll break out the oscilloscope and analyze how AES key bits leak through execution time and power consumption, and why constant-time implementations are non-negotiable in TrustZone firmware.
