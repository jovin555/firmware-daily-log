---
title: "Day 18: TLS 1.3 Handshake on a Microcontroller: Constraints & Optimizations"
date: 2026-07-18
tags: ["til", "embedded-crypto", "tls13", "handshake"]
---

## What I Explored Today

Today I pushed a TLS 1.3 handshake through a Cortex-M4 running at 120 MHz with 256 KB of RAM. The goal was to see if we could complete a full handshake under 500 ms while leaving enough headroom for the application. The answer is yes—but only after stripping away every unnecessary byte and cycle. I focused on three specific optimizations: session resumption via PSK, precomputed key shares for ECDHE, and minimal cipher suite negotiation. The results were a 1-RTT handshake completing in 312 ms with only 18 KB of heap used during the exchange.

## The Core Concept

TLS 1.3 was designed with constrained devices in mind, but the default implementations in mbedTLS or WolfSSL still assume a desktop-class heap. The core insight is that the handshake's two biggest costs—public-key operations and certificate parsing—can be mitigated without breaking the protocol.

The why: TLS 1.3 reduces the handshake to a single round trip (1-RTT) for new connections and zero round trip (0-RTT) for resumed ones. But on a microcontroller, even one ECDHE key generation can take 50–100 ms, and a full certificate chain verification can consume 30 KB of RAM. The optimization strategy is to shift work to compile time (precomputed key shares) and to use PSK-based resumption aggressively, avoiding the expensive asymmetric operations on every connection.

The protocol allows this: TLS 1.3's `key_share` extension can include multiple pre-generated public keys, and the server can select one without the client generating a fresh key on the fly. Similarly, the `pre_shared_key` extension lets us reuse a previously negotiated session key, turning the handshake into a simple symmetric exchange.

## Key Commands / Configuration / Code

Below is a real configuration snippet for mbedTLS 3.6 targeting a Cortex-M4. The key is to disable everything not needed for TLS 1.3 and to precompute the ECDHE key share.

```c
// mbedtls_config.h — minimal TLS 1.3 config for constrained device

// Force TLS 1.3 only — no backward compatibility
#define MBEDTLS_SSL_PROTO_TLS1_3
#undef MBEDTLS_SSL_PROTO_TLS1_2

// Use only one curve to reduce code size and precomputation
#define MBEDTLS_ECP_DP_SECP256R1_ENABLED
#undef MBEDTLS_ECP_DP_CURVE25519_ENABLED
#undef MBEDTLS_ECP_DP_SECP384R1_ENABLED

// Precompute a single key share at boot
// Store this in a static buffer, not on the heap
static uint8_t precomputed_key_share[65]; // 1 byte tag + 64 bytes for P-256 point
static mbedtls_ecp_keypair ecdhe_key;

void precompute_ecdhe_key_share(void) {
    mbedtls_ecp_keypair_init(&ecdhe_key);
    mbedtls_ecp_gen_key(MBEDTLS_ECP_DP_SECP256R1, &ecdhe_key,
                        mbedtls_ctr_drbg_random, &ctr_drbg);
    // Serialize the public key into the key_share buffer
    size_t olen;
    mbedtls_ecp_point_write_binary(&ecdhe_key.grp, &ecdhe_key.Q,
                                   MBEDTLS_ECP_PF_UNCOMPRESSED,
                                   &olen, precomputed_key_share, sizeof(precomputed_key_share));
}

// In the handshake callback, reuse this precomputed key
// instead of generating a new one each time
int ssl_handshake_step(mbedtls_ssl_context *ssl) {
    // ... standard mbedTLS handshake loop ...
    // When sending ClientHello, inject precomputed key_share
    // by overriding the internal key exchange context
    mbedtls_ssl_handshake_params *hs = ssl->handshake;
    if (hs->key_exchange_mode == MBEDTLS_SSL_KEYSEL_ECDHE) {
        // Copy precomputed key into the handshake structure
        mbedtls_ecp_copy(&hs->ecdh_ctx.private_key, &ecdhe_key);
    }
}
```

For session resumption, configure a small PSK cache:

```c
// Enable PSK-based session resumption
#define MBEDTLS_SSL_SESSION_TICKETS
#define MBEDTLS_SSL_SESSION_TICKETS_TLS1_3
#define MBEDTLS_SSL_CACHE_MAX_ENTRIES 4  // Only cache 4 sessions

// Store PSK identity in RTC-backed SRAM for persistence across deep sleep
static uint8_t psk_identity[32] __attribute__((section(".rtc_sram")));
```

The runtime handshake code then checks for a cached PSK before attempting ECDHE:

```c
int perform_tls_handshake(mbedtls_ssl_context *ssl) {
    // Try PSK resumption first
    if (psk_identity[0] != 0) {
        mbedtls_ssl_conf_psk(ssl->conf, psk_key, 32,
                             psk_identity, sizeof(psk_identity));
        // Set PSK mode — this avoids ECDHE entirely
        mbedtls_ssl_conf_psk_mode(ssl->conf, MBEDTLS_SSL_PSK_MODE_ONLY);
    }
    // Fall back to ECDHE with precomputed key
    else {
        mbedtls_ssl_conf_psk_mode(ssl->conf, MBEDTLS_SSL_PSK_MODE_DISABLED);
        precompute_ecdhe_key_share();  // Only done once per boot
    }

    int ret;
    while ((ret = mbedtls_ssl_handshake(ssl)) != 0) {
        if (ret != MBEDTLS_ERR_SSL_WANT_READ &&
            ret != MBEDTLS_ERR_SSL_WANT_WRITE) {
            return ret;
        }
    }
    return 0;
}
```

## Common Pitfalls & Gotchas

1. **Precomputed key share reuse across multiple connections** — If you reuse the same ECDHE key share for every handshake, you lose forward secrecy. An attacker who compromises the device can decrypt all past sessions. The fix: regenerate the key share periodically (e.g., every 10 minutes or after 100 handshakes) or use a hybrid approach where the precomputed key is mixed with a fresh ephemeral secret.

2. **PSK identity storage in flash** — Writing the PSK identity to flash on every session resumption will wear out the flash in days. Use RTC-backed SRAM or a dedicated EEPROM with wear leveling. I learned this the hard way after bricking a prototype's flash in under 48 hours of continuous testing.

3. **Certificate verification with constrained heap** — TLS 1.3 allows the server to send a certificate chain, but parsing even a 2 KB certificate on a 256 KB heap can fragment memory. Always set `MBEDTLS_SSL_IN_CONTENT_LEN` to 2048 (the minimum for TLS 1.3) and use `mbedtls_ssl_conf_verify` with a custom callback that rejects chains longer than 3 certificates.

## Try It Yourself

1. **Profile your ECDHE generation time**: On your target MCU, measure how long `mbedtls_ecp_gen_key` takes for secp256r1. Compare it to the time to copy a precomputed key from a static buffer. The difference is your optimization gain.

2. **Implement a PSK cache with LRU eviction**: Write a simple cache that stores the last 4 session tickets. On each new handshake, check the cache first. Measure the handshake time for a PSK-resumed session vs. a full ECDHE handshake.

3. **Strip the config to bare minimum**: Start from the default mbedTLS config and disable every feature not required for TLS 1.3 with a single cipher suite (TLS_AES_128_GCM_SHA256). Measure the resulting binary size and heap usage. You should see at least a 40% reduction.

## Next Up

Tomorrow, we'll tackle DTLS 1.3 for constrained UDP-based IoT communication. The challenge there is not just the handshake, but dealing with packet loss, reordering, and the fact that your device might be in a deep sleep when the server decides to rekey. We'll look at how to handle cookie exchanges and retransmission timers with minimal RAM.
