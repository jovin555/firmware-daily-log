---
title: "Day 19: DTLS for Constrained UDP-Based IoT Communication"
date: 2026-07-19
tags: ["til", "embedded-crypto", "dtls", "udp"]
---

## What I Explored Today

I spent the day diving into Datagram Transport Layer Security (DTLS) for constrained IoT devices that communicate over UDP. While TLS over TCP is the standard for web traffic, many IoT protocols like CoAP, MQTT-SN, and LwM2M run on UDP to avoid the overhead of connection-oriented transport. DTLS 1.2 (RFC 6347) and the newer DTLS 1.3 (RFC 9147) provide the same cryptographic guarantees as TLS—confidentiality, integrity, and authentication—but adapted for unreliable, out-of-order datagrams. I implemented a minimal DTLS handshake on an ESP32 using mbedTLS, and confirmed that the overhead is roughly 13–25 bytes per record, which is manageable even on 802.15.4 links with 127-byte MTU.

## The Core Concept

The fundamental challenge DTLS solves is that UDP doesn't guarantee delivery or ordering. TLS assumes a reliable byte stream, so it uses sequence numbers and MACs that depend on in-order arrival. DTLS adds explicit epoch and sequence number fields to every record, and it handles retransmission of handshake messages at the DTLS layer (not the transport layer). The handshake is identical to TLS conceptually, but each flight of messages must be individually acknowledged, and the client/server maintain a retransmit timer (typically 1 second initial, doubling up to 60 seconds).

For constrained devices, the critical trade-off is between security and memory. A full DTLS handshake with certificate-based authentication can consume 10–20 KB of heap for certificate parsing and key exchange. Pre-shared key (PSK) modes reduce this dramatically—mbedTLS with PSK can run in under 8 KB of RAM. The DTLS 1.3 connection ID (CID) feature is a game-changer for mobile IoT: it allows the receiver to identify a session even if the source IP/port changes, which is essential for devices that roam between networks.

## Key Commands / Configuration / Code

Below is a minimal DTLS 1.2 server using mbedTLS on a Linux host, compiled with `-DMBEDTLS_CONFIG_FILE=<mbedtls/mbedtls_config.h>`. This is the same API used on ESP32, STM32, and other MCUs.

```c
#include <mbedtls/ssl.h>
#include <mbedtls/entropy.h>
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/error.h>
#include <sys/socket.h>
#include <netinet/in.h>

// Error handling omitted for brevity — always check return codes in production

int main() {
    mbedtls_ssl_context ssl;
    mbedtls_ssl_config conf;
    mbedtls_entropy_context entropy;
    mbedtls_ctr_drbg_context ctr_drbg;

    // 1. Initialize RNG
    mbedtls_entropy_init(&entropy);
    mbedtls_ctr_drbg_init(&ctr_drbg);
    mbedtls_ctr_drbg_seed(&ctr_drbg, mbedtls_entropy_func, &entropy, NULL, 0);

    // 2. Configure DTLS — use MBEDTLS_SSL_TRANSPORT_DATAGRAM
    mbedtls_ssl_config_init(&conf);
    mbedtls_ssl_config_defaults(&conf,
        MBEDTLS_SSL_IS_SERVER,
        MBEDTLS_SSL_TRANSPORT_DATAGRAM,
        MBEDTLS_SSL_PRESET_DEFAULT);
    mbedtls_ssl_conf_rng(&conf, mbedtls_ctr_drbg_random, &ctr_drbg);

    // 3. Set PSK (pre-shared key) — 16 bytes hex, identity "client1"
    // For constrained devices, PSK avoids certificate overhead
    const unsigned char psk[] = {0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
                                 0x09,0x0A,0x0B,0x0C,0x0D,0x0E,0x0F,0x10};
    mbedtls_ssl_conf_psk(&conf, psk, sizeof(psk),
                         (const unsigned char*)"client1", 7);

    // 4. Set retransmit timeout — default is 1s, double on failure
    mbedtls_ssl_conf_handshake_timeout(&conf, 1000, 60000);

    // 5. Create UDP socket and bind
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in addr = { .sin_family = AF_INET,
                                .sin_port = htons(5684),
                                .sin_addr = { htonl(INADDR_ANY) } };
    bind(sock, (struct sockaddr*)&addr, sizeof(addr));

    // 6. Associate SSL context with socket via custom BIO
    mbedtls_ssl_init(&ssl);
    mbedtls_ssl_setup(&ssl, &conf);
    mbedtls_ssl_set_bio(&ssl, &sock,
                        dtls_send,    // custom send function
                        dtls_recv,    // custom recv function
                        NULL);        // no separate recv timeout

    // 7. Perform handshake — mbedTLS handles retransmission internally
    int ret;
    while ((ret = mbedtls_ssl_handshake(&ssl)) != 0) {
        if (ret != MBEDTLS_ERR_SSL_WANT_READ &&
            ret != MBEDTLS_ERR_SSL_WANT_WRITE) {
            // Real error — log and exit
            break;
        }
        // WANT_READ/WANT_WRITE means we need to wait for more data
        // In production, use poll()/select() with timeout
    }

    // 8. Application data exchange
    unsigned char buf[256];
    size_t len;
    mbedtls_ssl_read(&ssl, buf, sizeof(buf));  // blocks until datagram received
    mbedtls_ssl_write(&ssl, (const unsigned char*)"ACK", 3);

    // Cleanup
    mbedtls_ssl_free(&ssl);
    mbedtls_ssl_config_free(&conf);
    close(sock);
    return 0;
}
```

The custom `dtls_send` and `dtls_recv` functions wrap `sendto()` and `recvfrom()` with the socket descriptor stored in the `bio` context. The key detail: `recvfrom()` must return `MBEDTLS_ERR_SSL_WANT_READ` on `EAGAIN`/`EWOULDBLOCK` so mbedTLS can manage its retransmit timer.

## Common Pitfalls & Gotchas

**1. MTU fragmentation kills handshakes.** DTLS handshake messages (especially Certificate messages) can exceed the UDP payload limit. On 6LoWPAN networks with 127-byte MTU, a single handshake flight may need fragmentation at the DTLS layer. mbedTLS supports `MBEDTLS_SSL_DTLS_MAX_CONTENT_LEN` to limit record size, but you must also set `MBEDTLS_SSL_DTLS_MTU` to the path MTU. If you don't, the handshake will silently fail with `MBEDTLS_ERR_SSL_BUFFER_TOO_SMALL`. Always test with `ping -M do -s <size>` to find the real MTU.

**2. Cookie exchange is mandatory for servers.** DTLS includes a stateless cookie mechanism to prevent amplification attacks. If you skip it (by not setting `mbedtls_ssl_conf_dtls_cookies`), your server becomes a DDoS amplifier. On constrained servers, implement a lightweight cookie callback that uses a secret key and HMAC, not a full database lookup. mbedTLS provides `mbedtls_ssl_cookie_*` functions for this.

**3. Timer resolution matters on MCUs.** The retransmit timer uses `mbedtls_timing_delay_context`, which on bare-metal systems often relies on a 1 ms tick. If your RTOS tick is 10 ms, the initial 1-second timeout will jitter by 10%. Worse, if you don't call `mbedtls_ssl_handshake()` frequently enough (at least every 100 ms), the retransmit logic won't fire and the handshake will hang. Use a dedicated task or timer callback to pump the SSL context.

## Try It Yourself

1. **Measure DTLS overhead on a real link.** Set up two ESP32s with mbedTLS DTLS 1.2 using PSK. Use Wireshark to capture the handshake (filter `udp.port == 5684`). Count the bytes in each flight: how many records, what's the epoch/sequence overhead? Compare to a TLS 1.2 handshake over TCP.

2. **Implement a cookie callback.** Modify the server above to use `mbedtls_ssl_cookie_setup()` with a random key. Then send a handshake from a client without the cookie (e.g., by sending a ClientHello directly). Observe that the server sends a HelloVerifyRequest with a cookie, and the client must retransmit with the cookie included. This is the anti-amplification mechanism in action.

3. **Test MTU handling.** Set `MBEDTLS_SSL_DTLS_MTU` to 100 bytes on both client and server. Use a certificate chain instead of PSK (certificates are larger). The handshake will likely fail with `MBEDTLS_ERR_SSL_BUFFER_TOO_SMALL`. Fix it by enabling `MBEDTLS_SSL_DTLS_HELLO_VERIFY` and reducing the certificate size, or switch to raw public keys (RPK) which are smaller.

## Next Up

Tomorrow, I'll tackle **Certificate Chains & X.509 for Device Identity** — how to parse, validate, and store certificate chains on devices with 256 KB of flash, and why you should never hardcode root CA certificates in firmware.
