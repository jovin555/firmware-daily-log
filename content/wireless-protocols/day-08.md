---
title: "Day 08: Thread Networking: 6LoWPAN, Mesh Routing & Border Routers"
date: 2026-07-08
tags: ["til", "wireless-protocols", "thread", "6lowpan"]
---

## What I Explored Today

Today I dove deep into Thread networking—specifically how it leverages 6LoWPAN for IPv6 adaptation, its mesh-under routing with source routing, and the critical role of Border Routers. I set up a three-node Thread network using the OpenThread CLI on nRF52840 DKs, traced packet flows with Wireshark, and watched how a Border Router bridges the Thread mesh to an IPv6 Wi-Fi network. The key insight: Thread is not Zigbee with different branding; it's a full IP network designed from the ground up for low-power, self-healing mesh topologies.

## The Core Concept

Thread solves a fundamental problem that plagues other IoT mesh protocols: **interoperability at the network layer**. Zigbee and Z-Wave use application-layer gateways that require proprietary translation. Thread, by contrast, runs IPv6 natively over 6LoWPAN. Every Thread device gets a global IPv6 address. This means you can ping a light bulb from your laptop without any protocol translation—the Border Router just routes IP packets.

The magic happens in three layers:

1. **6LoWPAN Adaptation Layer**: IEEE 802.15.4 frames are only 127 bytes. IPv6 requires a minimum MTU of 1280 bytes. 6LoWPAN handles fragmentation, header compression (removing redundant IPv6 fields), and mesh addressing. Without it, IPv6 wouldn't fit.

2. **Mesh Routing (MLE + Source Routing)**: Thread uses a hybrid approach. For local traffic, it uses Mesh Link Establishment (MLE) to discover neighbors and build a link-state topology. For long-distance routing, it uses source routing—the sender embeds the entire route in the packet header. This avoids per-hop routing table lookups, saving RAM on resource-constrained nodes.

3. **Border Router (BR)**: The BR is the single point of connectivity to external networks. It runs a DHCPv6 server for address assignment, a NAT64 gateway for IPv4 fallback, and a DNS-SD server for service discovery. Critically, the BR is not a single point of failure—Thread supports multiple BRs for redundancy.

## Key Commands / Configuration / Code

I used OpenThread's CLI on nRF52840 DKs. Here's the exact sequence to form a network, verify 6LoWPAN, and observe mesh routing.

**1. Form a Thread network on the leader node:**
```bash
# On node 1 (leader)
> dataset init new
> dataset
# Output shows Active Timestamp, Channel, PAN ID, Network Key, etc.
> dataset commit active
> ifconfig up
> thread start
# Wait 10 seconds
> state
leader
> ipaddr
fdde:ad00:beef:0:0:ff:fe00:fc00  # Mesh-Local EID
fdde:ad00:beef:0:0:ff:fe00:fc01  # Link-Local
```

**2. Attach two child nodes:**
```bash
# On node 2 (Router Eligible)
> dataset networkkey 00112233445566778899aabbccddeeff
> dataset channel 15
> dataset panid 0xabcd
> dataset commit active
> ifconfig up
> thread start
# Wait 15 seconds
> state
router
> ipaddr
fdde:ad00:beef:0:0:ff:fe00:fc02
```

**3. Verify 6LoWPAN fragmentation (Wireshark capture on BR):**
```bash
# On node 3 (End Device), send a large ICMPv6 echo
> ping fdde:ad00:beef:0:0:ff:fe00:fc01 -s 256
# Wireshark shows:
# Frame 1: 6LoWPAN Fragment (first) - Datagram Size: 280, Datagram Tag: 0x3A
# Frame 2: 6LoWPAN Fragment (subsequent) - Datagram Offset: 80
```

**4. Check source routing path:**
```bash
# On leader, view routing table
> route
# Output:
# fdde:ad00:beef:0:0:ff:fe00:fc02 via fe80::ff:fe00:fc02
# fdde:ad00:beef:0:0:ff:fe00:fc03 via fe80::ff:fe00:fc02
# The leader routes to node 3 through node 2 (router)
```

**5. Border Router configuration (on Raspberry Pi with RCP):**
```bash
# Install ot-br-posix
sudo apt install otbr-agent
# Configure BR
sudo otbr-agent -I wpan0 -B eth0 spinel+hdlc+uart:///dev/ttyACM0
# Verify prefix advertisement
sudo ot-ctl prefix add fdde:ad00:beef::/64 pof
sudo ot-ctl netdata show
# Output shows Border Router entry with prefix fdde:ad00:beef::/64
```

## Common Pitfalls & Gotchas

**1. 6LoWPAN Fragmentation Timeouts**
The default 6LoWPAN reassembly timeout is 60 seconds. If a fragment is lost (common in noisy 2.4 GHz environments), the entire datagram is dropped. I spent an hour debugging why large CoAP messages failed intermittently. Solution: Keep application payloads under 80 bytes to avoid fragmentation entirely, or increase the timeout via `ot-ctl lowpan set reassemblytimeout 120`.

**2. Router Selection and Partitioning**
Thread allows up to 32 routers, but only 23 can be active at once. If you have 24 router-eligible devices, one will remain a child. Worse, if the leader goes down and a partition occurs, devices on different partitions can't communicate until a merge happens. I accidentally triggered this by power-cycling the leader without waiting for re-election. Always monitor `state` and `rloc16` values to verify topology stability.

**3. Border Router IPv6 Prefix Conflicts**
When running multiple BRs, they must advertise the same on-mesh prefix. If one BR advertises `fdde:ad00:beef::/64` and another advertises `fdde:ad00:cafe::/64`, devices get confused about default routes. I fixed this by hardcoding the prefix in the BR configuration file and disabling automatic prefix selection.

## Try It Yourself

1. **Build a 3-node Thread mesh**: Flash OpenThread CLI firmware to three nRF52840 DKs. Form a network with one leader, one router, and one end device. Use `ping` to verify connectivity between all nodes. Then, power off the router and watch the end device find a new parent via the leader.

2. **Capture 6LoWPAN fragmentation**: On a Thread network, send a 300-byte UDP packet from an end device to the Border Router. Use Wireshark with the 6LoWPAN dissector to see the fragmentation headers. Note the Datagram Tag and Offset fields.

3. **Set up a Border Router**: Connect an nRF52840 as an RCP to a Raspberry Pi. Install `ot-br-posix` and configure it to bridge Thread to your local Ethernet. Verify that a laptop on Wi-Fi can ping a Thread end device's global IPv6 address.

## Next Up

Tomorrow, we'll explore **Matter Protocol: Application Layer Over Thread & Wi-Fi**. We'll see how Matter uses the Thread network we just built as its transport, adds application-level clusters for device control, and handles commissioning with QR codes and passcodes.
