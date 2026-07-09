---
title: "Day 09: Matter Protocol: Application Layer Over Thread & Wi-Fi"
date: 2026-07-09
tags: ["til", "wireless-protocols", "matter"]
---

## What I Explored Today

Today I dug into the Matter protocol stack—specifically how it operates as an application-layer standard that abstracts away the underlying transport (Thread or Wi-Fi). Matter isn't a new PHY or MAC; it's a unified application profile that runs on top of IPv6, using either Thread (for low-power, mesh) or Wi-Fi (for higher bandwidth). I focused on the interaction model, data model (ZCL-derived clusters), and how a single device can be commissioned and controlled identically regardless of which transport it uses.

## The Core Concept

The fundamental insight behind Matter is that the smart home industry was fractured by siloed application protocols—Zigbee, Z-Wave, and proprietary Wi-Fi stacks all spoke different languages. Matter solves this by defining a common application layer over IPv6. The key architectural decisions:

- **IPv6 mandatory**: Every Matter node has a globally routable IPv6 address (even on Thread, via 6LoWPAN compression).
- **Borrows from Zigbee Cluster Library (ZCL)**: Clusters (e.g., On/Off, Level Control, Color Control) define device behavior. But instead of APS frames, they're mapped to Interaction Model commands over TCP (for commissioning) or UDP (for operational messages).
- **Data Model tree**: Each endpoint has clusters (server or client). A light bulb is endpoint 1 with an On/Off server cluster and a Level Control server cluster.
- **Interaction Model verbs**: Invoke, Read, Write, Subscribe, and Report. These are the only operations. No custom RPCs.

Why this matters for engineers: you write one application handler (e.g., `OnOffCluster::HandleCommand()`) and it works over Thread or Wi-Fi without transport-specific code. The Matter stack handles the binding and routing.

## Key Commands / Configuration / Code

### 1. Cluster Definition (ZAP XML snippet)

Matter uses ZAP (Zigbee Cluster Configurator) to generate cluster code. Here's a minimal On/Off cluster definition:

```xml
<cluster>
  <code>0x0006</code>
  <name>On/Off</name>
  <server>
    <attribute side="server" code="0x0000" type="boolean" writable="false">OnOff</attribute>
    <command source="client" code="0x00" name="Off" optional="false"/>
    <command source="client" code="0x01" name="On" optional="false"/>
    <command source="client" code="0x02" name="Toggle" optional="false"/>
  </server>
</cluster>
```

### 2. Application Callback (C++ in the Matter SDK)

When a client sends an `On` command, the stack calls this handler:

```cpp
// app/OnOffServer.cpp (simplified from CHIP SDK)
class OnOffServer : public chip::app::Clusters::OnOff::Delegate {
public:
    chip::Protocols::InteractionModel::Status
    HandleOnOffCommand(chip::app::CommandHandler *commandHandler,
                       const chip::app::ConcreteCommandPath &commandPath,
                       bool onOff) override {
        // This runs on any transport—Thread or Wi-Fi
        if (onOff) {
            SetLED(HIGH);
            ChipLogProgress(Zcl, "Light ON");
        } else {
            SetLED(LOW);
            ChipLogProgress(Zcl, "Light OFF");
        }
        // Send status response back to client
        commandHandler->AddStatus(commandPath,
            chip::Protocols::InteractionModel::Status::Success);
        return chip::Protocols::InteractionModel::Status::Success;
    }
};
```

### 3. Commissioning via Bluetooth LE (BLE)

Before Matter works over Thread/Wi-Fi, the device must be commissioned. This happens over BLE (or NFC):

```bash
# Using chip-tool (Matter's CLI test harness)
# Step 1: Scan for uncommissioned devices
chip-tool pairing ble-wifi 1234 SSID PASSWORD 20202021 3840

# Step 2: After commissioning, control over Thread/Wi-Fi
chip-tool onoff on 1234 1
```

The `20202021` is the setup PIN code (default), and `3840` is the discriminator (identifies the device during BLE scanning).

### 4. Operational Discovery (DNS-SD)

Once on the network, Matter nodes advertise themselves via mDNS:

```bash
# On a Linux controller, you can see Matter services
avahi-browse -r _matter._tcp
# Output example:
# = enp0s3 IPv4 1234-ABCD (MatterLight)         _matter._tcp local
#    hostname = [matter-light.local]
#    address = [fd00::1:2:3:4]
#    port = [5540]
#    txt = ["VP=1234+32768" "DT=1" "PI=" "SII=5000" "T=1"]
```

The TXT records encode vendor ID (`VP`), device type (`DT`), and session idle interval (`SII`).

## Common Pitfalls & Gotchas

1. **Thread vs. Wi-Fi MTU differences bite you**: Matter's Interaction Model assumes a maximum APDU size of 1200 bytes (for Thread's 6LoWPAN fragmentation). If you send a large Write Attributes request over Wi-Fi, it works. Over Thread, it gets silently fragmented or dropped. Always test with `chip-tool` over Thread with `--paa-trust-store` to force the smaller path.

2. **Fabric credentials mismatch**: Each Matter device belongs to exactly one "fabric" (a logical network). If you commission a device with one controller, then try to control it from another controller on a different fabric, you'll get `Status::UnsupportedAccess`. The fix: use `chip-tool pairing unbind` before re-commissioning.

3. **Cluster revision versioning**: Matter clusters have a `clusterRevision` attribute. If your device implements revision 2 but the controller expects revision 3, commands may silently fail. Always check `chip-tool readattribute 1234 1 0x0006 0xFFFD` to verify the revision.

## Try It Yourself

1. **Commission a Matter light bulb over Thread**: Use a Nordic nRF52840 DK with the Matter lighting-app example. Flash it, then run `chip-tool pairing ble-thread 1234 hex:0e080000...` (replace with your Thread network dataset). Verify you can toggle the LED with `chip-tool onoff toggle 1234 1`.

2. **Capture and inspect Matter messages**: On a Raspberry Pi running as a Thread border router, use `tcpdump -i wpan0 -s 0 -w matter.pcap` while sending commands. Open in Wireshark with the Matter dissector enabled. Look for the Interaction Model header (opcode 0x01 for Invoke).

3. **Write a custom cluster handler**: Modify the ESP32 Matter light example to add a "Blink" command (cluster 0x0006, command ID 0x03). Implement it to toggle the LED 3 times. Use `chip-tool onoff invoke 1234 1 0x03` to test.

## Next Up

Tomorrow: **Matter Commissioning: Device Onboarding & Fabric Membership**—we'll walk through the full commissioning flow (PASE, CASE, and fabric synchronization), including the cryptographic handshake and how the device gets its operational certificate.
