---
title: "Day 27: Testing & Debugging BLE: nRF Sniffer, Wireshark & nRF Connect"
date: 2026-11-06
tags: ["til", "ble-medical", "sniffer", "wireshark"]
---

## What I Explored Today

Today I set up a proper BLE debugging workflow instead of relying on `printf` over UART and guessing why a connection dropped. The stack: an nRF52840 Dongle running the nRF Sniffer firmware, Wireshark with the Nordic BLE dissector, and nRF Connect for Mobile as the peer device. The goal was to capture a full connection lifecycle of our medical peripheral — advertising, connection establishment, service discovery, and a notify stream — and actually read the link-layer events rather than inferring them from application logs. This is the difference between "the app says it disconnected" and "here is the LL_TERMINATE_IND with error code 0x08 (connection timeout) at packet 412."

## The Core Concept

BLE debugging fails at the application layer because the application layer lies. Your GATT client sees a disconnect; the radio saw a supervision timeout. Your peripheral thinks it sent a notification; the controller may have dropped it because the connection event was already closed. The only ground truth is the over-the-air exchange, and to see it you need a sniffer that follows the connection.

The nRF Sniffer is not a promiscuous Wi-Fi-style capture. BLE uses frequency hopping across 40 channels (37 data + 3 advertising), and a connection hops according to a channel map and hop increment negotiated at connection time. The sniffer firmware captures the `CONNECT_IND` on the advertising channel, extracts the access address, CRC init, channel map, and hop increment, then follows the connection by hopping in lockstep with both peers. That's why you must start the capture *before* the connection is established — if you miss the `CONNECT_IND`, the sniffer has no parameters to follow the link and you get nothing but advertising packets.

Wireshark's role is decoding. The Nordic plugin (`ble.dll` / `ble.so`) dissects the link layer, L2CAP, ATT, and SMP. Without it you get raw bytes. With it you get `ATT_OP_HANDLE_NOTIFY`, `LL_CONNECTION_UPDATE_IND`, and the actual reason codes.

## Key Commands / Configuration / Code

**1. Flash the sniffer firmware to the nRF52840 Dongle.** The `.hex` ships with the nRF Sniffer for Bluetooth LE package. Put the dongle in DFU mode (press reset; it enumerates as a bootloader), then:

```bash
# Using nrfutil (legacy) — the dongle appears as a serial DFU target
nrfutil dfu serial -pkg sniffer_nrf52840dongle_*.zip -p /dev/ttyACM0 -b 115200

# Or with the newer nrfutil device command
nrfutil device program --firmware sniffer_nrf52840dongle_*.hex --traits jlink
```

On Windows the port is `COMx`; on macOS it's `/dev/tty.usbmodem*`.

**2. Point Wireshark at the sniffer interface.** After flashing, the dongle enumerates as a CDC-ACM serial device. In Wireshark, the interface appears as `nRF Sniffer for Bluetooth LE`. Select it, then set the capture filter to the target's address:

```
# Wireshark capture filter — restrict to one peripheral by BD_ADDR
# (public address shown here; use the random address for privacy-enabled devices)
btle.advertising_address == aa:bb:cc:dd:ee:ff
```

Better: in the Nordic toolbar, set the **device** field to your peripheral's address and the **target** to follow that specific link. This avoids drowning in other 2.4 GHz traffic.

**3. Filter the decode for the interesting events.** Once captured, use display filters:

```
# Connection lifecycle and link-layer control
btle.control_opcode || btle.advertising_header.pdu_type == 0x05

# ATT notifications only (our sensor stream)
btatt.opcode == 0x1b

# Find the disconnect reason — LL_TERMINATE_IND carries the error code
btle.control_opcode == 0x02

# Connection parameter updates (interval, latency, timeout)
btle.control_opcode == 0x00 || btle.control_opcode == 0x01
```

**4. nRF Connect for Mobile as the controlled peer.** Use it to force the conditions you want to capture: connect, trigger a GATT write to a CCCD to enable notifications, then walk out of range to force a supervision timeout. The app logs the disconnect reason it received, which you cross-check against the sniffer's `LL_TERMINATE_IND` or the absence of packets.

**5. Decode a supervision timeout from the capture.** If the last packet before silence is a `LL_...` with no response and the gap exceeds `connSupervisionTimeout`, the link died. Confirm the negotiated timeout in the `CONNECT_IND`:

```
# In the CONNECT_IND decode, check:
#   connSlaveLatency, connSupervisionTimeout (units of 10 ms)
# A 6 s timeout = 600 in the field. If your peripheral sleeps longer
# than (timeout - latency*interval), the master drops the link.
```

## Common Pitfalls & Gotchas

**Starting the capture too late.** If you hit "start" after the phone has already connected, the sniffer never saw the `CONNECT_IND` and cannot follow the hop sequence. You'll capture advertising forever and wonder why the connection is invisible. Always start capture, *then* initiate the connection.

**Sniffer dongle and target on the same host USB bus causing timing skew.** The nRF Sniffer timestamps packets on the dongle, but heavy USB traffic can cause dropped packets. For long captures, use a dedicated USB port and avoid hubs. Dropped packets show as gaps, not errors — easy to misread as a link problem.

**Confusing the ATT MTU with the LL PDU size.** A 247-byte ATT MTU does not mean 247 bytes go in one packet. The LL PDU max is 251 bytes including headers, and fragmentation across connection events is normal. When you see a notification split across multiple `LL_DATA` PDUs, that's expected — don't chase it as a bug.

**Privacy-enabled devices rotate their random address.** If your peripheral uses a resolvable private address, the sniffer's address filter stops matching after rotation. Filter on the device name in advertising data or disable address rotation during debugging.

## Try It Yourself

1. **Capture a full connection lifecycle.** Flash the sniffer, start capture in Wireshark, connect from nRF Connect, enable notifications on a characteristic, then disconnect. Apply the display filter `btle.control_opcode == 0x02` and find the `LL_TERMINATE_IND`. Note the error code — was it a clean disconnect (0x13, remote user terminated) or a timeout (0x08)?

2. **Force and diagnose a supervision timeout.** Set your peripheral's `connSupervisionTimeout` to 4 s (400), connect, then power off the peripheral abruptly. Capture the silence and confirm the master's disconnect reason is 0x08. Then repeat with a 6 s timeout and compare how long the gap lasts before termination.

3. **Verify a connection parameter update.** Trigger `ble.gap_connect` with a requested interval of 30 ms and latency 4 from your firmware, then find the `LL_CONNECTION_UPDATE_IND` in the capture. Confirm the actual negotiated interval matches what you requested, and check whether the master accepted or clamped it.

## Next Up

Tomorrow: **Compliance — Bluetooth SIG Qualification, FCC & FDA Wireless Coexistence (ANSI C63.27)**. We'll walk through what a Declaration ID actually buys you, how FCC Part 15.247 applies to a BLE medical device, and why ANSI C63.27 coexistence testing is the part everyone forgets until the FDA reviewer asks for it.
