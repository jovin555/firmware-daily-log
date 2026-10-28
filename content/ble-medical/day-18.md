---
title: "Day 18: Application-Layer Security for Medical Data on Top of BLE"
date: 2026-10-28
tags: ["til", "ble-medical", "app-layer-security", "encryption"]
---

# Day 18: Application-Layer Security for Medical Data on Top of BLE

## What I Explored Today

Today I dug into why BLE link-layer security (LE Secure Connections, bonding, encryption) is necessary but *not sufficient* for medical devices, and what an application-layer security envelope actually looks like in practice. I prototyped an authenticated, encrypted payload format for a blood-pressure cuff characteristic using AES-128-GCM with per-message nonces and a monotonic counter to defeat replay attacks, then wired it into a Zephyr peripheral and a Python test client. The key takeaway: BLE protects the *pipe*, but medical data needs protection at the *payload* level because of the threat model — a bonded-but-compromised phone, a replayed GATT write, or a malicious central that legitimately pairs.

## The Core Concept

BLE's built-in security gives you three things: confidentiality (AES-CCM on the link), integrity (MIC per PDU), and authentication (via pairing/LE Secure Connections). What it does *not* give you:

1. **End-to-end protection past the radio.** Once a central decrypts a notification, the plaintext sits in the phone's GATT callback. A malicious app on a rooted phone, or a compromised gateway, sees everything. For PHI (protected health information) under HIPAA/GDPR, that's a problem.
2. **Replay resistance at the application level.** A bonded central can capture a valid encrypted write and replay it later. The link layer will happily re-encrypt and deliver it. If that write was "set insulin dose = 5 units," you have a safety issue.
3. **Non-repudiation / auditability.** You often need to prove *which* device sent *what* and *when*, independent of the BLE session.

So the pattern is: **BLE link security for the transport, plus an application-layer envelope for the data.** The envelope is typically AEAD (AES-GCM or ChaCha20-Poly1305) with:
- A **per-device symmetric key** provisioned out-of-band (during pairing, or via a secure element / ATECC608).
- A **monotonic counter** included in the AAD (additional authenticated data) to prevent replay.
- A **key derivation** step so the session key isn't the long-term key.

This is the same idea as TLS inside a VPN — defense in depth. It costs you ~16 bytes of tag + 12 bytes of nonce + 4 bytes of counter per message, which for a 20-byte BP reading is fine.

## Key Commands / Configuration / Code

Here's the envelope format I settled on. Each characteristic payload is:

```
[ counter:4 ][ nonce:12 ][ ciphertext:N ][ tag:16 ]
```

The counter is also fed into the AAD so it can't be stripped or reordered. On the peripheral (Zephyr, using `psa_crypto`):

```c
#include <psa/crypto.h>

#define APP_KEY_LEN   16
#define NONCE_LEN     12
#define TAG_LEN       16
#define AAD_LEN       4   /* just the counter */

static uint8_t app_key[APP_KEY_LEN];   /* provisioned out-of-band */
static uint32_t tx_counter;            /* persisted in NVS, monotonic */

int seal_medical_payload(const uint8_t *plain, size_t plain_len,
                         uint8_t *out, size_t out_cap)
{
    if (out_cap < 4 + NONCE_LEN + plain_len + TAG_LEN) return -ENOSPC;

    /* 1. counter (big-endian) goes first and into AAD */
    uint32_t ctr = tx_counter++;
    out[0] = ctr >> 24; out[1] = ctr >> 16; out[2] = ctr >> 8; out[3] = ctr;

    /* 2. random nonce — must never repeat under the same key */
    uint8_t *nonce = &out[4];
    psa_crypto_init();
    psa_generate_random(nonce, NONCE_LEN);

    /* 3. AES-128-GCM encrypt+authenticate */
    psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_ENCRYPT);
    psa_set_key_algorithm(&attr, PSA_ALG_GCM);
    psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attr, 128);

    psa_key_id_t key;
    psa_import_key(&attr, app_key, APP_KEY_LEN, &key);

    size_t olen;
    psa_aead_operation_t op = PSA_AEAD_OPERATION_INIT;
    psa_aead_encrypt_setup(&op, key, PSA_ALG_GCM);
    psa_aead_set_nonce(&op, nonce, NONCE_LEN);
    psa_aead_update_ad(&op, out, AAD_LEN);           /* counter as AAD */
    psa_aead_update(&op, plain, plain_len, &out[4 + NONCE_LEN], out_cap - 4 - NONCE_LEN, &olen);
    psa_aead_finish(&op, &out[4 + NONCE_LEN + olen], TAG_LEN, &olen, NULL, 0);
    psa_destroy_key(key);
    return 4 + NONCE_LEN + plain_len + TAG_LEN;
}
```

On the central side (Python, `cryptography` lib), verify and reject stale counters:

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

last_counter = -1

def open_medical_payload(blob: bytes, key: bytes) -> bytes:
    global last_counter
    ctr = int.from_bytes(blob[0:4], "big")
    nonce = blob[4:16]
    ct_and_tag = blob[16:]
    if ctr <= last_counter:
        raise ValueError("replay detected")
    plain = AESGCM(key).decrypt(nonce, ct_and_tag, blob[0:4])  # AAD = counter
    last_counter = ctr
    return plain
```

Note the AAD binding: the counter is authenticated but not encrypted, so a tamperer can't change it without invalidating the tag. That's what makes the replay check trustworthy.

## Common Pitfalls & Gotchas

- **Nonce reuse is catastrophic for GCM.** If you derive the nonce from a counter that resets on reboot (e.g., you forgot to persist `tx_counter` in NVS), you'll reuse a nonce under the same key and leak the authentication key. Always persist the counter, or use a random 96-bit nonce from a real CSPRNG — never a timestamp with low resolution.
- **Counter overflow / wrap.** A 32-bit counter at 1 Hz lasts 136 years, but if you're sending at 100 Hz it's ~1.3 years. Size the counter to your message rate and rotate the key before wrap. Document the rotation policy.
- **Confusing link-layer bonding with app-layer trust.** A device can be bonded (link-encrypted) and still be a malicious central. Don't skip the app-layer envelope just because `BT_SECURITY_L4` is set — they defend against different attackers. Also: the app key must be provisioned *out-of-band*, not sent over the BLE link during pairing, or you've defeated the purpose.

## Try It Yourself

1. **Break the replay check.** Take the Python `open_medical_payload` above, capture two valid blobs, and replay the first one after the second. Confirm it raises `ValueError`. Then remove the `ctr <= last_counter` check and confirm the forged replay is accepted — that's the vulnerability you're defending against.
2. **Persist the counter.** In the Zephyr code, add NVS (`nvs_write`/`nvs_read`) around `tx_counter` so it survives reboot. Reboot the device mid-stream and verify the central doesn't see a counter regression.
3. **Measure the overhead.** Send a 20-byte BP reading through the envelope and count the actual GATT payload size (4 + 12 + 20 + 16 = 52 bytes). Decide whether that fits your connection interval / MTU budget, and if not, consider a shorter nonce or counter.

## Next Up

Tomorrow: **Implementing a BLE Peripheral in Zephyr / nRF Connect SDK** — we'll take the security envelope from today and drop it into a real GATT service using the Zephyr Bluetooth stack, with `bt_gatt_service_register`, custom 128-bit UUIDs, and notification flow control. Bring your nRF52 DK.
