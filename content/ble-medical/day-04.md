---
title: "Day 04: GAP Roles: Peripheral, Central, Broadcaster & Observer"
date: 2026-10-14
tags: ["til", "ble-medical", "gap", "roles"]
---

## What I Explored Today

Today I dug into the Generic Access Profile (GAP) role model and how it maps onto real medical device topologies. My mental model had been "central = phone, peripheral = sensor," which is fine until you build a continuous glucose monitor that also needs to relay data to a bedside display, or a pulse oximeter that broadcasts to any listener without ever connecting. GAP defines four roles — Peripheral, Central, Broadcaster, Observer — and crucially, a single device can hold multiple roles simultaneously. Understanding which roles your firmware actually needs (and which the stack supports concurrently) is the difference between a clean architecture and a connection storm in a hospital ward.

## The Core Concept

GAP roles describe *link-layer behavior*, not device categories. The split exists because BLE has two fundamentally different ways to move data: connection-oriented and connectionless.

**Peripheral** and **Central** are the two ends of a connection. The Peripheral advertises (is connectable), accepts a connection, and typically becomes the GATT server. The Central scans, initiates the connection, and typically becomes the GATT client. The Central owns the connection timing — it dictates the connection interval, and the Peripheral must honor it. This asymmetry matters: a battery-powered sensor wants long intervals (low power), while a clinician's tablet streaming live ECG wants short ones (low latency). The Central wins that negotiation.

**Broadcaster** and **Observer** are connectionless. A Broadcaster only transmits advertising packets — no connection, no GATT, no acknowledgment. An Observer only receives them. This is the right model for one-to-many telemetry: a temperature patch broadcasting to every nurse station in range, or a fitness band beaconing to gym equipment. There's no pairing, no bonding, no state to maintain — but also no reliability guarantee and no back-channel.

The "why" is power and topology. Connectionless broadcast lets a coin-cell device transmit for years because it never has to stay awake to service a connection. Connection-oriented roles give you reliability, security, and bidirectional data at the cost of both peers staying synchronized.

In practice, roles are orthogonal to GATT. A Peripheral is *usually* the GATT server, but nothing stops a Central from hosting a GATT server too (this is how a phone can expose its own services to a wearable). Don't conflate the two layers.

## Key Commands / Configuration / Code

On Zephyr, roles are selected at build time via Kconfig. Here's a Broadcaster-only configuration — the leanest possible medical beacon:

```kconfig
# prj.conf — Broadcaster only, no connection support
CONFIG_BT=y
CONFIG_BT_BROADCASTER=y
CONFIG_BT_PERIPHERAL=n
CONFIG_BT_CENTRAL=n
CONFIG_BT_OBSERVER=n
# No GATT server needed for pure advertising
CONFIG_BT_GATT_SERVICE_CHANGED=n
```

A Peripheral that also observes (dual-role) — common for a hub that connects to sensors *and* listens for beacons:

```kconfig
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_CENTRAL=y
CONFIG_BT_OBSERVER=y
CONFIG_BT_BROADCASTER=n
# Each concurrent connection costs RAM; budget carefully
CONFIG_BT_MAX_CONN=4
CONFIG_BT_MAX_PAIRED=4
```

Advertising as a Broadcaster in Zephyr:

```c
#include <zephyr/bluetooth/bluetooth.h>

/* Non-connectable advertising: this device will never accept a link */
static const struct bt_le_adv_param adv_params =
    BT_LE_ADV_PARAM(BT_LE_ADV_OPT_NONE,   /* no connectable flag */
                    BT_GAP_ADV_FAST_INT_MIN_2,  /* 100 ms */
                    BT_GAP_ADV_FAST_INT_MAX_2,  /* 150 ms */
                    NULL);                       /* no directed peer */

static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_NO_BREDR),
    BT_DATA(BT_DATA_NAME_COMPLETE, "TEMP-PATCH-01", 13),
};

int start_broadcast(void)
{
    int err = bt_le_adv_start(&adv_params, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err) {
        printk("Advertising failed to start (err %d)\n", err);
    }
    return err;
}
```

On Linux with BlueZ, the role is implicit in the command. Scanning (Observer):

```bash
# Passive scan: receive advertising without sending scan requests
sudo btmgmt find -l
# Or with bluetoothctl for a cleaner view
bluetoothctl --timeout 10 scan on
```

Connecting (Central) and inspecting the resulting role:

```bash
bluetoothctl
[bluetooth]# connect AA:BB:CC:DD:EE:FF
# After connecting, this host is Central; the peer is Peripheral
```

## Common Pitfalls & Gotchas

**1. Assuming a Peripheral can initiate a connection.** It can't. If your device needs to *reach out* to a known peer, it must be a Central (or use a directed advertising trick, which is fragile). Medical gateways that need to reconnect to a bonded sensor after a dropout must run the Central role — don't design the sensor to "call home."

**2. Forgetting that Broadcaster has no feedback path.** There is no ACK, no retransmission, no RSSI-based flow control at the application layer. If a packet is lost to interference, it's gone. For anything safety-relevant, broadcast is a *supplement* to a connection, not a replacement. I've seen teams try to build alarm delivery on broadcast alone — don't.

**3. Concurrent role RAM and scheduling costs.** Every additional role and every concurrent connection consumes stack buffers and radio time slots. `CONFIG_BT_MAX_CONN=4` on a device with 64 KB RAM will fail to link. Check your controller's supported role combinations — some cheap SoCs advertise "multi-role" but only support one connection plus advertising, not two connections.

## Try It Yourself

1. **Build a Broadcaster-only firmware** on your dev board (nRF52, ESP32-C3, or similar) using the Zephyr config above. Verify with `bluetoothctl scan on` from a Linux host that the device appears but `connect` fails with "not connectable."

2. **Convert it to a Peripheral** by flipping `CONFIG_BT_BROADCASTER=n` and `CONFIG_BT_PERIPHERAL=y`, adding a minimal GATT service. Confirm the same host can now connect and read a characteristic.

3. **Run a dual-role Observer + Peripheral** and log the RSSI of nearby beacons while remaining connectable. Measure the current draw difference versus the Broadcaster-only build — this is the real cost of adding a connection role.

## Next Up

Tomorrow we go deep on the advertising payload itself: AD types, how scan response extends the 31-byte budget, and why extended advertising (up to 1650 bytes) changes what's possible for medical telemetry. Bring your packet sniffer.
