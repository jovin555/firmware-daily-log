---
title: "Day 18: CoAP: Constrained Application Protocol Over UDP"
date: 2026-07-18
tags: ["til", "wireless-protocols", "coap"]
---

## What I Explored Today

I spent the day deep-diving into CoAP (Constrained Application Protocol), the UDP-based application-layer protocol designed by the IETF for IoT and constrained-node networks. Unlike HTTP, which assumes reliable TCP streams and relatively abundant bandwidth, CoAP runs directly over UDP with its own lightweight reliability layer. I implemented a simple sensor server on an ESP32 and a client on a Linux machine to understand the request/response model, observe discovery via the `.well-known/core` resource, and test confirmable vs. non-confirmable messaging. The results confirmed CoAP's efficiency: a typical GET response fits in under 50 bytes of payload, and the handshake overhead is essentially zero compared to TLS-over-TCP alternatives.

## The Core Concept

CoAP exists because HTTP is too heavy for 802.15.4, LoRaWAN, or even BLE-connected microcontrollers with 32 KB of RAM. HTTP headers can be hundreds of bytes; CoAP's binary header is 4 bytes. But the real genius is how CoAP maps to HTTP semantics: GET, POST, PUT, DELETE all exist, and CoAP resources are identified by URI paths just like REST APIs. This means you can proxy CoAP to HTTP transparently.

The protocol defines four message types:
- **CON** (Confirmable) — requires an ACK; provides reliability over UDP.
- **NON** (Non-confirmable) — fire-and-forget; no ACK expected.
- **ACK** (Acknowledgement) — confirms receipt of a CON.
- **RST** (Reset) — indicates the message was received but cannot be processed.

CoAP also supports **Observe** (RFC 7641) for publish/subscribe patterns and **Block-Wise Transfer** (RFC 7959) for payloads larger than a single UDP datagram (typically 64–1280 bytes). For constrained devices, the key takeaway is that CoAP gives you REST semantics without the TCP overhead, and with built-in multicast support for service discovery.

## Key Commands / Configuration / Code

I used the **libcoap** library (v4.3.1) on both the ESP32 (ESP-IDF) and Linux. Here's a minimal CoAP server that exposes a temperature resource:

```c
// coap_server.c — ESP32 / Linux
#include <coap3/coap.h>

static void
get_temp_handler(coap_resource_t *resource,
                 coap_session_t *session,
                 const coap_pdu_t *request,
                 const coap_string_t *query,
                 coap_pdu_t *response) {
    // Simulated sensor reading
    unsigned char buf[16];
    int len = snprintf((char *)buf, sizeof(buf), "%.1f", 24.7 + ((float)rand() / RAND_MAX) * 2.0);
    coap_pdu_set_code(response, COAP_RESPONSE_CODE_CONTENT);
    coap_add_data_blocked_response(resource, session, request, response,
                                   buf, len,
                                   COAP_MEDIATYPE_TEXT_PLAIN, 0);
}

void app_main(void) {
    coap_context_t *ctx = coap_new_context(NULL);
    coap_address_t addr;
    coap_address_init(&addr);
    addr.addr.sin.sin_family = AF_INET;
    addr.addr.sin.sin_port = htons(5683);
    addr.addr.sin.sin_addr.s_addr = INADDR_ANY;

    coap_endpoint_t *ep = coap_new_endpoint(ctx, &addr, COAP_PROTO_UDP);
    coap_resource_t *res = coap_resource_init(coap_make_str_const("temperature"), 0);
    coap_register_handler(res, COAP_REQUEST_GET, get_temp_handler);
    coap_add_resource(ctx, res);

    while (1) {
        coap_io_process(ctx, COAP_IO_WAIT);
    }
}
```

On the client side, a simple `coap-client` command (from libcoap-tools) fetches the resource:

```bash
# Discover available resources
coap-client -m get coap://192.168.1.100/.well-known/core

# Expected output:
# </temperature>;if="sensor",</.well-known/core>

# Fetch temperature with confirmable request (default)
coap-client -m get coap://192.168.1.100/temperature

# Response:
# 24.9
# (2.05 Content)

# Non-confirmable request (fire-and-forget)
coap-client -m get -N coap://192.168.1.100/temperature
```

For observing a resource (publish/subscribe):

```bash
# Subscribe to temperature changes (observe)
coap-client -m get -s 0 coap://192.168.1.100/temperature
# The client will print updates until Ctrl+C
```

## Common Pitfalls & Gotchas

1. **UDP fragmentation and MTU mismatches** — CoAP assumes a single datagram fits in the path MTU (typically 1280 bytes for IPv6, 576 for IPv4). If your payload exceeds this, you *must* use Block-Wise Transfer (Block1/Block2 options). Without it, the packet will be silently dropped or cause ICMP Fragmentation Needed errors. Always check `coap_pdu_get_max_size()` before sending.

2. **Confirmable vs. Non-confirmable confusion** — Many developers use NON for everything to save ACK overhead, but this breaks reliability. For critical state changes (e.g., "door unlocked"), always use CON. For periodic sensor readings where loss is acceptable (e.g., temperature every 60 seconds), NON is fine. Mixing them incorrectly leads to either unnecessary retransmissions or silent data loss.

3. **Resource discovery timing** — The `.well-known/core` resource is not automatically populated; you must register each resource with `coap_add_resource()` or manually implement the handler. If your device joins a network and immediately expects a client to discover it, the client may get an empty response if the server hasn't finished initialization. Add a 1–2 second startup delay before accepting requests.

## Try It Yourself

1. **Set up a CoAP server on an ESP32** — Flash the code above using ESP-IDF. Use `coap-client` on your Linux machine to GET `/temperature`. Then modify the server to add a `/led` resource that accepts PUT requests with payload "on" or "off" to toggle an onboard LED.

2. **Implement Observe** — Extend your server to notify observers every 5 seconds with a new temperature reading. On the client, use `coap-client -m get -s 0` and verify you receive updates without polling. Check the packet capture with `tcpdump -i any port 5683` to see the NON or CON messages.

3. **Test Block-Wise Transfer** — Create a resource that returns a 2 KB string (e.g., a configuration file). Fetch it with `coap-client -m get -B 64` (block size 64 bytes). Verify in Wireshark that multiple `2.05 Content` responses arrive with Block2 options. Then try without `-B` and observe the failure.

## Next Up

Tomorrow, we tackle **MQTT & MQTT-SN for Constrained Networks** — the pub/sub workhorses of IoT. We'll compare MQTT 3.1.1's TCP overhead with MQTT-SN's UDP-based gateway model, implement a broker on a Raspberry Pi, and connect an ESP32 publishing sensor data with a 2-byte topic ID. If you thought CoAP was lightweight, wait until you see MQTT-SN's 4-byte fixed header.
