---
title: "Day 03: Link Layer: States, Advertising Channels & Connection Events"
date: 2026-10-13
tags: ["til", "ble-medical", "link-layer", "connection-events"]
---

# Day 03: Link Layer: States, Advertising Channels & Connection Events

## What I Explored Today

Today I dug into the Link Layer (LL) — the layer that actually owns the radio. After two days of staring at GATT tables and attribute handles, it was refreshing to drop down to the part of the stack that decides *when* the radio turns on, *which* of the 40 channels it uses, and *how* two devices stay synchronized once they've found each other. For a medical device, this matters more than most people realize: the LL is where connection interval, latency, and supervision timeout live, and those three parameters directly determine whether your pulse-ox streaming looks smooth or choppy on the clinician's tablet.

## The Core Concept

The Link Layer is a state machine. A BLE radio is, at any instant, in exactly one of five states: **Standby, Advertising, Scanning, Initiating, or Connection**. The first four are "unconnected" states; the last is where all your GATT traffic actually flows.

The reason this matters is that BLE was designed to be cheap and battery-friendly, and the LL is where that design pays off. Instead of a device listening continuously, BLE splits the 2.4 GHz band into **40 channels of 2 MHz each**. Three of them — **37 (2402 MHz), 38 (2426 MHz), and 39 (2480 MHz)** — are *advertising channels*, deliberately placed between Wi-Fi's chunky 20 MHz channels to reduce collisions. The other 37 are *data channels*, used only after a connection is established.

An advertiser hops between 37, 38, and 39 on every advertising event (typically every 20 ms to 10.24 s). A scanner listens on one channel at a time, cycling through them. When a scanner wants to connect, it enters the **Initiating** state, sends a `CONNECT_IND` PDU on the channel where it heard the advertiser, and both sides jump to a data channel to begin the **Connection** state.

Once connected, the two devices don't stay on one channel. They use a **channel map** (a 37-bit bitmap of allowed data channels) and a hop increment to pseudo-randomly hop channels on every connection event. A **connection event** is a scheduled rendezvous: the central transmits first, the peripheral replies within 150 µs, and they exchange as many packets as fit before the event closes. The gap between events is the **connection interval** (7.5 ms to 4 s in 1.25 ms steps). This is the single most important knob for medical telemetry — it trades latency against power.

## Key Commands / Configuration / Code

On Linux with BlueZ, you can watch the LL do its thing with `btmon` while a peripheral advertises:

```bash
# Terminal 1: capture HCI traffic (needs root)
sudo btmon

# Terminal 2: start advertising on hci0
sudo hciconfig hci0 up
sudo hcitool -i hci0 cmd 0x08 0x0008 1E 02 01 06 1A FF 4C 00 02 15 \
  E2 C5 6D B5 DF FB 48 D2 B0 60 D0 F5 A7 10 96 E0 00 00 00 00 C5 00
# 0x08 0x0008 = LE Set Advertising Data
# 1E = length, 02 01 06 = flags, 1A FF ... = manufacturer-specific data

sudo hcitool -i hci0 cmd 0x08 0x0006 A0 00 A0 00 00 00 00 00 00 00 00 00 00 07 00
# 0x08 0x0006 = LE Set Advertising Parameters
# A0 00 = min interval 0x00A0 * 0.625ms = 100ms
# A0 00 = max interval 100ms
# 07 = advertising type (ADV_IND, connectable undirected)

sudo hcitool -i hci0 cmd 0x08 0x000A 01
# 0x08 0x000A = LE Set Advertising Enable
```

In `btmon` you'll see `LE Advertising Report` events with the RSSI and channel. On the peripheral side, `LE Connection Complete` shows the negotiated interval:

```
> HCI Event: LE Meta Event (0x3e) plen 19
      LE Connection Complete (0x01)
        Status: Success (0x00)
        Handle: 64
        Role: Peripheral (0x01)
        Peer address type: Public
        Connection interval: 30.00 msec (0x0018)
        Peripheral latency: 0
        Supervision timeout: 2000 msec (0x00c8)
```

For a medical wearable, a common profile is **interval 30–50 ms, latency 0, supervision timeout 2–6 s**. Latency 0 means the peripheral must answer every event; latency N lets it skip N events, saving power but adding up to N × interval of latency.

## Common Pitfalls & Gotchas

1. **Advertising on only one channel.** Some cheap stacks default to channel 37 only. You'll get far worse discovery reliability in a Wi-Fi-dense hospital ward. Always advertise on all three (37, 38, 39) unless you have a specific reason not to.

2. **Confusing connection interval with throughput.** A 7.5 ms interval sounds fast, but if your peripheral only sends one 20-byte notification per event, you're capped at ~2.6 kB/s. Throughput is interval × packets-per-event × payload. For ECG at 250 Hz × 3 bytes, you need to pack multiple samples per notification.

3. **Ignoring the supervision timeout.** If the central misses the peripheral for longer than the supervision timeout, the link drops. In a medical device, a 2 s timeout with a 30 ms interval means ~66 missed events before disconnect — usually fine, but if you set latency to 4 and interval to 100 ms, you're at 500 ms of silence before the timer even starts counting. Tune both together.

## Try It Yourself

1. **Watch the channel hop.** Run `sudo btmon` while connecting a phone to a BLE peripheral. Look for `LE Connection Complete`, then observe the `Number of completed packets` events. Note the connection interval and try changing it from the central side (Android's `requestConnectionPriority`, iOS's `CBPeripheralManager` doesn't expose it — use an nRF52 dongle with `btmon` instead).

2. **Force a supervision timeout.** Connect two dev boards, then power off the peripheral. Time how long until the central reports `Disconnection Complete` with reason `0x08` (Connection Timeout). Compare against the negotiated supervision timeout.

3. **Measure advertising interval impact.** Set your peripheral's advertising interval to 20 ms, then 1000 ms, then 10.24 s. Use a phone scanner app and time how long discovery takes in each case. You'll see the power/latency tradeoff in the flesh.

## Next Up

Tomorrow we leave the radio behind and climb one layer up: **GAP Roles — Peripheral, Central, Broadcaster & Observer**. The LL states map almost 1:1 onto GAP roles, but GAP is where you decide what your device *is* on the network — and where most medical device interoperability bugs actually live.
