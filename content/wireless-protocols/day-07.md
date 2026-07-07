---
title: "Day 07: IEEE 802.15.4: The Radio Layer Under Thread & Zigbee"
date: 2026-07-07
tags: ["til", "wireless-protocols", "802-15-4"]
---

## What I Explored Today

Today I dug into the physical (PHY) and medium access control (MAC) layers defined by IEEE 802.15.4 — the radio foundation that both Thread and Zigbee sit on. While most of us interact with higher-level APIs (OpenThread, ZCL, etc.), the real-world behavior of your mesh network — range, throughput, latency, and coexistence — is determined by what happens at 2.4 GHz in the 802.15.4 radio. I spent the morning reading the standard (IEEE 802.15.4-2020), then validated my understanding by configuring a Nordic nRF52840 DK as a raw 802.15.4 sniffer and inspecting frames.

## The Core Concept

Why does 802.15.4 matter if you're building a Thread or Zigbee product? Because every packet your application sends is first wrapped in an 802.15.4 MAC frame before it hits the air. The standard defines:

- **PHY layer**: O-QPSK modulation at 250 kbps (2.4 GHz band), channel spacing of 5 MHz, and a maximum packet size of 127 bytes (including MAC headers).
- **MAC layer**: CSMA/CA channel access, acknowledgment frames, beacon-enabled or non-beacon mode, and optional security (AES-128-CCM*).

The critical constraint: **127 bytes per frame**. After MAC headers (9–25 bytes) and security overhead (up to 21 bytes), your application payload is often 80–100 bytes. This is why Thread and Zigbee both fragment larger messages — and why you must design your application payloads to fit.

The other key detail: **CSMA/CA is not deterministic**. Before transmitting, the radio listens for a clear channel. If the channel is busy, it backs off for a random number of symbol periods. In dense deployments, this backoff can cause latency spikes — something you'll see in production but not in a lab with two nodes.

## Key Commands / Configuration / Code

### 1. Scanning for 802.15.4 Channels (nRF52840 + nRF Sniffer)

The most practical thing you can do is see which channels are actually in use. Using the nRF Sniffer for 802.15.4 (Wireshark plugin):

```bash
# Install the nRF Sniffer for 802.15.4 (not BLE)
# Connect nRF52840 DK, flash the sniffer firmware:
nrfjprog --program sniffer_802154.hex --chiperase --reset

# In Wireshark, select the correct serial interface
# Set channel filter, e.g., channel 11 (2405 MHz):
wireshark -i /dev/ttyACM0 -k -Y "wpan.src64 == 00:12:4b:00:12:34:56:78"
```

You'll see beacon frames, data frames, and ACKs. Pay attention to the **Frame Control Field** — it tells you if security is enabled, if ACK is requested, and the addressing mode (short 16-bit vs. extended 64-bit).

### 2. Raw 802.15.4 Frame Construction (C, using TI CC13xx driverlib)

Here's how you'd manually construct a data frame for a Thread-like network:

```c
// IEEE 802.15.4 MAC frame for data transmission
// Assumes non-beacon, no security, short addressing

typedef struct {
    uint8_t  fcf[2];       // Frame Control Field
    uint8_t  seq;          // Data Sequence Number
    uint16_t dest_pan;     // Destination PAN ID
    uint16_t dest_addr;    // Destination short address
    uint16_t src_pan;      // Source PAN ID (often same)
    uint16_t src_addr;     // Source short address
    uint8_t  payload[100]; // Max 100 bytes after headers
    uint8_t  fcs[2];       // Frame Check Sequence (CRC)
} __attribute__((packed)) mac_frame_t;

void build_data_frame(mac_frame_t *frame, uint16_t dest, 
                      uint8_t *data, uint8_t len) {
    // FCF: Frame Type=Data (0b001), ACK requested, No security
    frame->fcf[0] = 0x61;  // 0110 0001
    frame->fcf[1] = 0x88;  // 1000 1000 (short src/dst, intra-PAN)
    frame->seq = 0;        // Increment per frame
    frame->dest_pan = 0xFFFF; // Broadcast PAN for discovery
    frame->dest_addr = dest;
    frame->src_pan = 0x0001;
    frame->src_addr = 0x0001;
    memcpy(frame->payload, data, len);
    // FCS is computed by radio hardware on transmit
}
```

**Key insight**: The FCS (CRC) is computed by the radio peripheral, not in software. Your driver must set `len` to `sizeof(mac_frame_t) - 2` (excluding FCS) and let the radio append it.

### 3. Configuring CSMA-CA Parameters (OpenThread CLI)

In OpenThread, you can inspect and modify the CSMA/CA backoff parameters that are passed down to the 802.15.4 MAC:

```bash
# Check current CSMA parameters
> mac csl period
> mac csl timeout

# View the raw MAC counters (collisions, retries)
> mac counters

# Set the minimum backoff exponent (default 3)
# Lower = more aggressive, higher = more polite
> mac csl period 500  # microseconds
```

These parameters are exposed via the `otPlatRadio` API in the platform abstraction layer. If you're porting Thread to a new radio, you implement `otPlatRadioCsmaBackoff()`.

## Common Pitfalls & Gotchas

1. **The 127-byte limit is a hard ceiling.** I've seen engineers forget that MAC headers + security + payload must fit. If your application sends a 120-byte payload, the MAC will silently drop it. Always check `OT_MAC_FRAME_SIZE` (127) minus `OT_MAC_HEADER_SIZE` (typically 25 with security). Your max payload is ~80 bytes in a Thread network.

2. **Channel 26 is not available everywhere.** In the 2.4 GHz band, channels 11–26 are defined. But channel 26 (2480 MHz) is at the edge of the ISM band and is not allowed in some regulatory domains (e.g., Japan). Your device may scan channel 26 and find it empty, then fail certification. Always restrict channel masks to 11–25 for global compliance.

3. **CSMA/CA backoff interacts badly with beacon-enabled mode.** In non-beacon mode (which Thread uses), nodes transmit whenever they want after a random backoff. In beacon mode (used by some Zigbee implementations), nodes synchronize to a coordinator's beacon. Mixing these modes on the same channel causes collisions because beacon-mode nodes expect a periodic slot, while non-beacon nodes transmit asynchronously. This is a common coexistence issue in multi-protocol gateways.

## Try It Yourself

1. **Sniff your own Thread network.** Flash an nRF52840 DK with the 802.15.4 sniffer firmware, set Wireshark to channel 11 (default Thread channel), and observe the MLE (Mesh Link Establishment) frames. Note the 16-bit short addresses assigned by the leader.

2. **Calculate your maximum payload.** Take your Thread application's largest message. Add 25 bytes for MAC headers (with security), 21 bytes for 6LoWPAN fragmentation headers, and 4 bytes for MIC. Does it fit in 127 bytes? If not, redesign your message to fit in two fragments.

3. **Test CSMA/CA behavior.** Set up two Thread nodes 1 meter apart. Use `mac counters` in OpenThread CLI to monitor `TxErrCca` (clear channel assessment failures). Add a third node transmitting continuously on the same channel (e.g., a BLE advertisement on channel 39, which overlaps 802.15.4 channel 25). Watch the retry count climb.

## Next Up

Tomorrow: **Thread Networking: 6LoWPAN, Mesh Routing & Border Routers**. We'll move up the stack and see how Thread uses 6LoWPAN to compress IPv6 headers over 802.15.4's tiny frames, how the mesh routing protocol (MLE) maintains connectivity, and how a Border Router bridges your Thread mesh to Wi-Fi or Ethernet. Bring your OpenThread CLI — we're going to trace a packet from a sleepy end device all the way to the cloud.
