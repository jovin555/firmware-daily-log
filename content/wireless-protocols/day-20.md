---
title: "Day 20: 6LoWPAN & IPv6 Header Compression for Constrained Links"
date: 2026-07-20
tags: ["til", "wireless-protocols", "6lowpan", "ipv6"]
---

## What I Explored Today

Today I dug into the 6LoWPAN adaptation layer and its IPv6 header compression (IPHC) mechanism. While IPv6 gives us a massive address space and end-to-end connectivity, its 40-byte base header is a non-starter for IEEE 802.15.4 frames that max out at 127 bytes—leaving only ~80 bytes for payload after link-layer overhead. 6LoWPAN's header compression is what makes IPv6 actually viable on constrained, low-power mesh networks. I focused on the real-world compression patterns, the dispatch byte encoding, and how to verify compression is working in a production network.

## The Core Concept

The fundamental problem is simple: an IPv6 header (40 bytes) plus a UDP header (8 bytes) consumes 48 bytes. On a 127-byte 802.15.4 frame, after MAC (9 bytes) and security (up to 21 bytes), you're left with ~50 bytes for application data. Without compression, you lose 96% of your payload to headers.

6LoWPAN solves this by exploiting redundancy in the IPv6 header fields across a constrained network. The key insight: within a single LoWPAN, many header fields are either:
- **Elided entirely** (e.g., Version, Traffic Class, Flow Label—always the same)
- **Inferred from link-layer data** (e.g., source/destination addresses from the 802.15.4 MAC addresses)
- **Compressed to 1-2 bytes** (e.g., UDP ports, Hop Limit)

The IPHC encoding (RFC 6282) uses a 2-byte dispatch header that encodes which fields are compressed and how. The most aggressive compression—called "NHC" for Next Header Compression—can squeeze a full IPv6+UDP header down to just 6 bytes (2 for IPHC dispatch, 2 for UDP ports, 2 for UDP length/checksum). That's an 87.5% reduction.

## Key Commands / Configuration / Code

### 1. Enabling 6LoWPAN Compression on a Linux Border Router

Using the Linux kernel's built-in 6LoWPAN module (CONFIG_6LOWPAN):

```bash
# Load the 6LoWPAN module
sudo modprobe bluetooth_6lowpan

# Attach 6LoWPAN to a Bluetooth LE interface (hci0)
sudo echo 1 > /sys/kernel/debug/bluetooth/6lowpan

# For IEEE 802.15.4 (e.g., CC2538), use wpan-tools
sudo ip link set wpan0 up
sudo iwpan dev wpan0 set pan_id 0xabcd
sudo ip link add link wpan0 name lowpan0 type lowpan
sudo ip link set lowpan0 up
sudo ip addr add fd00::1/64 dev lowpan0
```

### 2. Inspecting Compressed Headers with Wireshark

After capturing a 6LoWPAN packet, filter for compressed frames:

```bash
# tshark filter to show only 6LoWPAN compressed frames
tshark -r capture.pcap -Y "lowpan.dispatch == 0x41" -T fields \
  -e frame.number -e lowpan.dispatch -e lowpan.nhc -e ipv6.src -e ipv6.dst
```

The dispatch byte `0x41` means:
- `0x40` = IPHC dispatch (bit 7 set)
- `0x01` = TF (Traffic Flow) field compressed to 1 byte

### 3. Contiki-NG Configuration for Max Compression

In `project-conf.h`, force the most aggressive compression:

```c
/* Enable 6LoWPAN with full IPHC compression */
#define NETSTACK_CONF_RDC     nullrdc_driver
#define NETSTACK_CONF_MAC     csma_driver
#define NETSTACK_CONF_FRAMER  framer_802154
#define NETSTACK_CONF_RADIO   cc2538_rf_driver

/* Force HC06 compression (RFC 6282) */
#define UIP_CONF_IPV6         1
#define UIP_CONF_IPV6_RPL     1
#define UIP_CONF_6LOWPAN      1
#define UIP_CONF_COMPRESS_IPV6_HDR 1
#define UIP_CONF_COMPRESS_UDP 1

/* Disable link-local context for smaller headers */
#define UIP_CONF_LLH_LEN      0
```

### 4. Manual Compression Verification with Python

A quick script to verify your compression ratio:

```python
import struct

# Simulated uncompressed IPv6+UDP header (48 bytes)
uncompressed = bytearray(48)

# 6LoWPAN compressed header: IPHC dispatch (2) + NHC UDP (2) + ports (2) + checksum (2)
# Assuming context-based compression with link-local addresses
compressed = bytearray([
    0x41, 0x00,  # IPHC dispatch: TF=01, NH=1, HLIM=0, CID=0, SAC=0, SAM=00, M=0, DAC=0, DAM=00
    0xF0, 0x01,  # NHC: UDP, port compression enabled
    0x00, 0x35,  # Source port (12345 -> 0x3039, but compressed to 0x0035 for well-known)
    0x00, 0x00   # UDP checksum (elided in many cases)
])

ratio = (1 - len(compressed) / len(uncompressed)) * 100
print(f"Compression ratio: {ratio:.1f}%")
print(f"Header size: {len(uncompressed)}B -> {len(compressed)}B")
```

## Common Pitfalls & Gotchas

**1. Context-Based Compression Requires State Synchronization**
The most aggressive compression uses "context identifiers" (CIDs) that map to full IPv6 prefixes. If the border router and node have mismatched context tables, packets get decompressed into garbage. Always verify context synchronization with `ip -6 neigh show` on the border router and check for "context mismatch" errors in node logs.

**2. UDP Checksum Elision Breaks NAT64 and Firewalls**
RFC 6282 allows eliding the UDP checksum for UDP/IPv6 (setting it to 0x0000). This is fine inside a trusted LoWPAN, but if your traffic traverses a NAT64 gateway or enterprise firewall, those devices will drop packets with zero checksums. Always enable UDP checksums (`UDP_CONF_CHECKSUM=1` in Contiki) if your traffic leaves the PAN.

**3. Mesh-Under vs. Route-Over Confusion**
6LoWPAN compression assumes a "mesh-under" topology where the link-layer handles forwarding. If you're using RPL (route-over), the mesh header adds 2-4 bytes that can push you over the 127-byte limit. Always account for the mesh header when calculating your maximum payload: `MTU = 127 - MAC_hdr - SEC_hdr - MESH_hdr - COMPR_hdr`.

## Try It Yourself

1. **Capture and decode a 6LoWPAN packet**: Use a CC2538 or nRF52840 with Contiki-NG, run the `udp-sender` example, and capture the air traffic with a second radio. Use Wireshark's "6LoWPAN" dissector to expand the compressed header and identify which fields were elided.

2. **Measure compression ratio across topologies**: Deploy three nodes—one as a border router, one as a direct child, one as a 2-hop RPL child. Capture packets from each and compute the average header size. Compare how compression degrades as hop count increases (due to mesh headers).

3. **Break compression intentionally**: On a border router, manually set an incorrect context prefix (e.g., `ip -6 addr add fd01::1/64 dev lowpan0` when nodes expect `fd00::`). Observe the decompression errors in Wireshark as "malformed packet" or "context mismatch" warnings.

## Next Up

Tomorrow: **Network Selection Strategy: Choosing a Protocol for Your Product** — We'll build a decision framework for picking between Thread, Zigbee, BLE Mesh, or proprietary 6LoWPAN stacks based on latency, throughput, battery life, and interoperability requirements.
