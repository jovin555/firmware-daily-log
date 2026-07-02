---
title: "Day 02: Symmetric Encryption: AES Modes (ECB, CBC, CTR, GCM)"
date: 2026-07-02
tags: ["til", "embedded-crypto", "aes", "block-cipher"]
---

## What I Explored Today

Today I dug into the four most common AES block cipher modes of operation: ECB, CBC, CTR, and GCM. While the AES core algorithm is standardized and fixed, the mode you choose determines whether your encryption is secure, parallelizable, or provides integrity guarantees. I focused on what actually matters when deploying these on constrained embedded targets—memory overhead, initialization vector handling, and the critical difference between confidentiality-only and authenticated encryption.

## The Core Concept

AES encrypts exactly 16 bytes at a time—that's the block size. If your plaintext is longer than 16 bytes, you need a *mode of operation* to chain blocks together. The mode defines how each block's encryption depends on the previous one (or doesn't).

**ECB (Electronic Codebook)** is the naive approach: encrypt each 16-byte block independently. This is deterministic and parallelizable, but it leaks patterns. Encrypt the same plaintext block twice, get the same ciphertext block. On an embedded device sending sensor data like temperature readings that repeat, an attacker can visually identify patterns. Never use ECB for anything except maybe encrypting a single block key.

**CBC (Cipher Block Chaining)** XORs each plaintext block with the previous ciphertext block before encryption. This removes patterns, but it's serial—you cannot encrypt block 2 until block 1 is done. Decryption *is* parallelizable. CBC requires an unpredictable IV (initialization vector), which must be unique per message but need not be secret.

**CTR (Counter)** turns AES into a stream cipher. You encrypt successive counter values (IV + counter) and XOR the output with plaintext. This is fully parallelizable for both encryption and decryption, and you can seek to any byte offset. The critical constraint: never reuse the same (key, IV) pair. Doing so reveals the XOR of two plaintexts.

**GCM (Galois/Counter Mode)** combines CTR mode encryption with a GHASH authentication tag. It provides both confidentiality and integrity (authenticated encryption). The tag detects tampering. GCM is the gold standard for embedded TLS and secure boot, but it requires careful IV management—96-bit IVs are optimal, and using a nonce-based construction is mandatory.

## Key Commands / Configuration / Code

Here's how to test each mode using OpenSSL on a development host, then implement CBC and CTR on a Cortex-M4 using mbedTLS.

### OpenSSL Quick Tests (on your dev machine)

```bash
# Generate a 128-bit key (16 bytes)
openssl rand -hex 16 > aes_key.hex

# ECB encryption (demonstrates pattern leakage)
echo -n "AAAAAAAAAAAAAAAA" | openssl enc -aes-128-ecb -K $(cat aes_key.hex) -nosalt | xxd
# Output: same block repeated — pattern visible

# CBC encryption (requires IV)
openssl rand -hex 16 > iv.hex
echo -n "AAAAAAAAAAAAAAAA" | openssl enc -aes-128-cbc -K $(cat aes_key.hex) -iv $(cat iv.hex) -nosalt | xxd
# Output: different ciphertext blocks — pattern hidden

# CTR encryption (same key+IV reuse = disaster)
echo -n "Hello, World!!!" | openssl enc -aes-128-ctr -K $(cat aes_key.hex) -iv $(cat iv.hex) -nosalt | base64
```

### mbedTLS Implementation (Cortex-M4)

```c
#include "mbedtls/aes.h"

// AES-128-CBC encryption on embedded target
void aes_cbc_encrypt(uint8_t *plaintext, size_t len, 
                     uint8_t *key, uint8_t *iv) {
    mbedtls_aes_context ctx;
    uint8_t working_iv[16];
    
    // Copy IV because mbedtls modifies it in-place
    memcpy(working_iv, iv, 16);
    
    mbedtls_aes_init(&ctx);
    mbedtls_aes_setkey_enc(&ctx, key, 128);
    
    // len must be multiple of 16 (PKCS#7 padding handled elsewhere)
    mbedtls_aes_crypt_cbc(&ctx, MBEDTLS_AES_ENCRYPT, 
                          len, working_iv, plaintext, plaintext);
    
    mbedtls_aes_free(&ctx);
}

// AES-128-CTR encryption (parallelizable, no padding needed)
void aes_ctr_encrypt(uint8_t *plaintext, size_t len,
                     uint8_t *key, uint8_t *nonce) {
    mbedtls_aes_context ctx;
    uint8_t stream_block[16];
    size_t nc_off = 0;
    uint8_t nonce_counter[16] = {0};
    
    // Copy nonce into first 12 bytes, last 4 bytes are counter
    memcpy(nonce_counter, nonce, 12);
    
    mbedtls_aes_init(&ctx);
    mbedtls_aes_setkey_enc(&ctx, key, 128);
    
    mbedtls_aes_crypt_ctr(&ctx, len, &nc_off, 
                          nonce_counter, stream_block, 
                          plaintext, plaintext);
    
    mbedtls_aes_free(&ctx);
}
```

### GCM with mbedTLS (Authenticated Encryption)

```c
#include "mbedtls/gcm.h"

// AES-128-GCM encrypt and produce authentication tag
void aes_gcm_encrypt(uint8_t *plaintext, size_t plen,
                     uint8_t *aad, size_t aad_len,
                     uint8_t *key, uint8_t *iv, size_t iv_len,
                     uint8_t *tag, size_t tag_len) {
    mbedtls_gcm_context ctx;
    
    mbedtls_gcm_init(&ctx);
    mbedtls_gcm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, key, 128);
    
    mbedtls_gcm_crypt_and_tag(&ctx, MBEDTLS_GCM_ENCRYPT,
                              plen, iv, iv_len,
                              aad, aad_len,
                              plaintext, plaintext,
                              tag, tag_len);
    
    mbedtls_gcm_free(&ctx);
}
```

## Common Pitfalls & Gotchas

1. **Reusing IVs in CTR/GCM is catastrophic.** If you encrypt two messages with the same key and IV in CTR mode, an attacker can XOR the ciphertexts to recover the XOR of the plaintexts. On embedded devices with weak entropy sources, always use a monotonic counter as part of the IV to guarantee uniqueness.

2. **CBC requires unpredictable IVs, not just unique ones.** If an attacker can predict the next IV, they can mount a chosen-plaintext attack. On constrained devices, derive the IV from a hardware RNG or a monotonic counter encrypted with the same key.

3. **GCM's 96-bit IV is optimal, but watch the tag length.** Using a 96-bit IV avoids internal GHASH computations. For the tag, 128 bits is standard, but many embedded TLS stacks default to 64 bits for bandwidth savings—this halves the security margin against forgery.

## Try It Yourself

1. **Verify ECB pattern leakage:** Encrypt a 32-byte plaintext of all zeros using AES-128-ECB with OpenSSL. Observe that the two 16-byte ciphertext blocks are identical. Now do the same with CBC—they differ.

2. **Implement a monotonic IV counter for CTR:** On your dev board, write a function that increments a 64-bit counter stored in RTC backup registers. Use this as the lower half of your CTR nonce. Encrypt two messages and verify that the ciphertexts reveal no pattern.

3. **Test GCM integrity:** Encrypt a message with AES-128-GCM, then deliberately flip one bit in the ciphertext. Attempt to decrypt and verify the tag. The decryption should fail with `MBEDTLS_ERR_GCM_AUTH_FAILED`.

## Next Up

Tomorrow I'm diving into **AEAD: Authenticated Encryption with ChaCha20-Poly1305**—the modern alternative to AES-GCM that's faster on microcontrollers without AES hardware acceleration, and immune to timing side-channels in software implementations.
