---
title: "Day 10: Matter Commissioning: Device Onboarding & Fabric Membership"
date: 2026-07-10
tags: ["til", "wireless-protocols", "matter", "commissioning"]
---

## What I Explored Today

Today I dug into the Matter commissioning flow—the process that turns a factory-fresh device into a trusted member of a Matter fabric. I walked through the six-phase commissioning sequence, from initial discovery via DNS-SD to the final operational certificate installation. I also set up a real commissioning session using the `chip-tool` against a simulated device, and examined the `CASE` (Certificate Authenticated Session Establishment) handshake that secures fabric membership. The key takeaway: commissioning is not just about pairing; it's about establishing a cryptographic chain of trust that persists across power cycles and network changes.

## The Core Concept

Why does Matter need such a heavyweight commissioning process? Because a Matter fabric is a distributed access-control domain. Every device in your home—light bulbs, locks, sensors—shares a single root-of-trust: the Matter Fabric Root CA. When you commission a new bulb, you're not just giving it Wi-Fi credentials; you're issuing it a Node Operational Certificate (NOC) signed by that root. This NOC is what allows the bulb to authenticate itself to other devices, and to prove it belongs to *your* fabric, not a neighbor's.

The "why" is about preventing replay attacks, rogue device injection, and cross-fabric interference. Without this, any device with the right network key could claim to be a light switch and start toggling your lights. The commissioning flow enforces that only a device that physically demonstrates possession of a secret (via the Passcode or QR code) can join. After that, all communication uses CASE, which is a mutual TLS-like handshake that verifies both devices hold valid NOCs from the same fabric root.

## Key Commands / Configuration / Code

I used the official Matter SDK's `chip-tool` to simulate a commissioner (controller) and a device. Below is the actual commissioning flow, broken into phases.

### Phase 1: Discovery (DNS-SD)
The commissioner discovers the uncommissioned device via mDNS. The device advertises `_matterc._udp` (commissionable) or `_matterd._udp` (operational). On the device side, you'd see:
```bash
# Device advertises itself (simulated via chip-all-clusters-app)
./out/debug/chip-all-clusters-app --discriminator 3840 --passcode 20202021
```
The discriminator (a 12-bit value) and passcode are encoded in the QR code.

### Phase 2: PASE (Password Authenticated Session Establishment)
The commissioner establishes a secure session using the passcode. This uses SPAKE2+ (a PAKE protocol). In `chip-tool`:
```bash
# Commissioner pairs with device using its discriminator and passcode
./out/debug/chip-tool pairing code 0x1234 MT:-24J0AFN00KA0648G00
```
The `MT:` string is the manual pairing code (from the QR). The `0x1234` is the node ID we're assigning.

### Phase 3: NOC (Node Operational Certificate) Installation
Once the PASE session is live, the commissioner sends a `AddNOC` command with the device's new operational certificate. The device must have a Certificate Signing Request (CSR) ready. On the device console, you'd see:
```
[CSR] Generating CSR with key pair...
[CSR] CSR: 3081... (DER-encoded)
```
The commissioner signs this CSR with the Fabric Root CA and sends back the NOC. The device stores it in its secure element (e.g., NXP SE050 or Infineon OPTIGA).

### Phase 4: Operational Discovery & CASE
After NOC installation, the device restarts mDNS as an operational node (`_matterd._udp`). The commissioner now does a CASE handshake:
```bash
# Verify the device is reachable with its new operational identity
./out/debug/chip-tool discover 0x1234
```
If successful, the device is now a full fabric member.

### Full Commissioning Script (for automation)
```bash
#!/bin/bash
# Commission a device with node ID 0x1234, using manual code
# Requires chip-tool built with --chip_tool
./chip-tool pairing code 0x1234 MT:-24J0AFN00KA0648G00

# After commissioning, send a simple on/off command
./chip-tool onoff on 0x1234 1
```

## Common Pitfalls & Gotchas

1. **Passcode vs. QR Code Mismatch**  
   The passcode embedded in the QR code must match the device's `--passcode` argument. If you generate a QR code with one passcode but the device uses another, the SPAKE2+ handshake will fail with a "PASE error: crypto failure". Always verify the passcode via the device's serial console or factory data.

2. **Fabric Index Collisions**  
   A commissioner can manage multiple fabrics (e.g., one for home, one for office). If you commission a device without specifying a fabric index, it defaults to fabric 1. If you later try to commission the same device into fabric 2, the device will reject because it's already a member of fabric 1. Use `--fabric-index 2` on the commissioner to avoid this.

3. **Thread Network Credentials Not Persisted**  
   When commissioning a Thread device, the commissioner sends the Thread network credentials (Active Operational Dataset) during the PASE session. If the device loses power before storing these, it will reboot into uncommissioned mode. Always check the device logs for "OperationalDataset stored" before power-cycling. On `chip-all-clusters-app`, you can force a store with the `storage-commit` command.

## Try It Yourself

1. **Simulate a full commissioning**  
   Build the Matter SDK, run `chip-all-clusters-app` with a known passcode (e.g., 20202021), then use `chip-tool pairing code` to commission it. After success, send a `onoff on` command and verify the device logs show the command was received.

2. **Inspect the NOC**  
   After commissioning, dump the device's operational certificate using `chip-tool operationalcredentials read noc 0x1234 1`. Decode the DER blob with `openssl x509 -inform DER -text -noout` and examine the subject DN—it should contain the Fabric ID and Node ID.

3. **Test re-commissioning with a different fabric**  
   Commission the device into fabric 1, then try to commission it again into fabric 2 without factory resetting. Observe the error. Then factory reset the device (via `chip-tool devicecontroller factoryreset 0x1234`) and re-commission into fabric 2 successfully.

## Next Up

Tomorrow, I'll compare **Zigbee vs Thread vs Matter**—three mesh stacks that often get lumped together but have fundamentally different design philosophies. I'll break down when to use each, their security models, and the real-world tradeoffs in latency, power, and interoperability.
