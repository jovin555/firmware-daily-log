---
title: "Day 03: AEAD: Authenticated Encryption with ChaCha20-Poly1305"
date: 2026-07-03
tags: ["til", "embedded-crypto", "aead", "chacha20"]
---

## What I Explored Today

I dove into Authenticated Encryption with Associated Data (AEAD) using the ChaCha20-Poly1305 construction. After yesterday's deep dive on AES-GCM, I wanted to understand the alternative that's become the gold standard for embedded systems—especially on microcontrollers without hardware AES acceleration. ChaCha20-Poly1305 is the AEAD used in TLS 1.3, WireGuard, and SSH, and today I learned why it's so well-suited for resource-constrained environments.

## The Core Concept

AEAD solves a critical problem: encryption alone doesn't guarantee integrity. If an attacker flips bits in a ciphertext block, decryption will produce garbage—but you won't know it's garbage unless you have a way to verify authenticity. AEAD combines confidentiality (encryption) with integrity (authentication) in a single, secure operation.

ChaCha20 is a stream cipher that generates a keystream using a 256-bit key and a 96-bit nonce. It's fast in software because it operates on 32-bit words with simple addition, XOR, and rotation operations—no S-boxes or lookup tables. Poly1305 is a polynomial-evaluation MAC that produces a 128-bit authentication tag. Together, they form an AEAD that's both fast and side-channel resistant by design.

The "Associated Data" part is what makes AEAD powerful: you can authenticate metadata (like packet headers, sequence numbers, or protocol fields) without encrypting it. The receiver can verify that this associated data hasn't been tampered with, even though it's sent in the clear.

## Key Commands / Configuration / Code

Here's how to use ChaCha20-Poly1305 with the Linux kernel's crypto API (via AF_ALG) and with libsodium, which is the most common library for embedded Linux and bare-metal projects.

### Using libsodium (Recommended for Embedded)

```c
#include <sodium.h>

// Encrypt and authenticate a message
int crypto_aead_chacha20poly1305_encrypt(
    unsigned char *ciphertext,
    unsigned long long *ciphertext_len,
    const unsigned char *plaintext,
    unsigned long long plaintext_len,
    const unsigned char *ad,          // Associated data (e.g., packet header)
    unsigned long long ad_len,
    const unsigned char *nsec,        // Always NULL for this construction
    const unsigned char *nonce,       // 96-bit nonce, must be unique per key
    const unsigned char *key          // 256-bit key
);

// Example usage
unsigned char key[crypto_aead_chacha20poly1305_KEYBYTES];  // 32 bytes
unsigned char nonce[crypto_aead_chacha20poly1305_NPUBBYTES]; // 12 bytes
unsigned char plaintext[] = "Hello, embedded world!";
unsigned char ciphertext[sizeof(plaintext) + crypto_aead_chacha20poly1305_ABYTES];
unsigned long long ciphertext_len;

// Generate a random key and nonce
randombytes_buf(key, sizeof(key));
randombytes_buf(nonce, sizeof(nonce));

// Encrypt (nonce is prepended to ciphertext by convention)
crypto_aead_chacha20poly1305_encrypt(
    ciphertext, &ciphertext_len,
    plaintext, sizeof(plaintext),
    NULL, 0,           // No associated data in this example
    NULL,              // nsec is always NULL
    nonce, key
);
```

### Using Linux Kernel Crypto API (AF_ALG)

```bash
# Set up a ChaCha20-Poly1305 AEAD socket
modprobe algif_aead

# Create a socket for the AEAD cipher
salg=$(keyctl newring chacha_test @u)
dd if=/dev/urandom bs=32 count=1 | keyctl padd logon chacha:key $salg

# Encrypt using openssl (user-space convenience)
echo -n "Hello, embedded world!" | \
openssl enc -chacha20-poly1305 \
  -K "$(xxd -p -l 32 /dev/urandom)" \
  -iv "$(xxd -p -l 12 /dev/urandom)" \
  -out ciphertext.bin
```

### Nonce Generation (Critical!)

```c
// NEVER use a static nonce! Use a counter or random nonce.
// For embedded systems, a 64-bit counter + 32-bit random is common:
uint64_t packet_counter = 0;
uint8_t nonce[12];

// Store counter in first 8 bytes, random in last 4
memcpy(nonce, &packet_counter, 8);
randombytes_buf(nonce + 8, 4);
packet_counter++;
```

## Common Pitfalls & Gotchas

1. **Nonce reuse is catastrophic.** Unlike AES-GCM where nonce reuse leaks the GHASH key, ChaCha20-Poly1305 nonce reuse leaks the keystream directly. An attacker can XOR two ciphertexts encrypted with the same nonce to recover the XOR of the plaintexts. In embedded systems with long-lived devices, use a monotonic counter (e.g., from a hardware RTC or flash-wear-leveled counter) combined with a random suffix.

2. **Poly1305 requires constant-time verification.** Never compare the authentication tag with `memcmp()`. Use `sodium_memcmp()` or `crypto_verify_16()`. Timing attacks on tag verification allow attackers to forge messages byte-by-byte. libsodium's `crypto_aead_chacha20poly1305_decrypt()` handles this correctly—always use the library function, don't roll your own.

3. **Associated data length must be consistent.** If your protocol includes optional fields in the associated data, the receiver must know exactly which bytes were authenticated. A common mistake is to authenticate a variable-length header without encoding the length. Always include length fields or use a fixed-size structure for associated data.

## Try It Yourself

1. **Implement a secure packet protocol.** Write a function that takes a plaintext payload and a 4-byte packet type (as associated data), encrypts with ChaCha20-Poly1305, and returns the ciphertext + tag. On the receiver side, verify the tag before decrypting. Test with a modified packet type to confirm authentication fails.

2. **Benchmark against AES-GCM.** On your target embedded platform (e.g., Raspberry Pi Pico, STM32, or ESP32), encrypt 1KB of data 1000 times with ChaCha20-Poly1305 and AES-GCM. Compare cycle counts. You'll likely see ChaCha20-Poly1305 win on Cortex-M0/M3 without crypto extensions.

3. **Simulate a nonce reuse attack.** Create two plaintexts, encrypt both with the same nonce and key, then XOR the ciphertexts. Observe that the result equals the XOR of the plaintexts. This is why your nonce management must be bulletproof.

## Next Up

Tomorrow we'll explore **Stream Ciphers & Why ECB Mode Is a Trap**. We'll look at how stream ciphers work under the hood, why ECB mode leaks your data like a sieve, and how to recognize when you're about to make a catastrophic mode-of-operation mistake. Bring your CTR mode knowledge—we're going deeper.
