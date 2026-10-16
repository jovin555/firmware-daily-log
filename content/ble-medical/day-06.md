---
title: "Day 06: Connection Parameters: Interval, Peripheral Latency & Supervision Timeout"
date: 2026-10-16
tags: ["til", "ble-medical", "connection-parameters", "power"]
---

# Day 06: Connection Parameters: Interval, Peripheral Latency & Supervision Timeout

## What I Explored Today

Today I dug into the three numbers that quietly govern every BLE connection: **Connection Interval**, **Peripheral Latency**, and **Supervision Timeout**. These are negotiated during the GAP connection establishment and re-negotiated at runtime via the Link Layer's `LL_CONNECTION_UPDATE_IND` (or the GAP `Connection Parameter Update Request` on older stacks). For a medical wearable, these parameters are the single biggest lever between "battery lasts a week" and "battery lasts a day" — and they also determine how fast an alert can reach the phone. I spent the afternoon measuring current draw on a Nordic nRF52840 dev kit while sweeping interval and latency values, and I finally internalized why the 3.75 ms minimum interval exists and why Apple's Accessory Design Guidelines are so opinionated about these numbers.

## The Core Concept

A BLE connection is not a stream — it's a **series of scheduled rendezvous points**. Every `connInterval` milliseconds, the central and peripheral wake up, exchange at most one packet each direction, and go back to sleep. That's the whole model. Everything else follows from it.

- **Connection Interval** (7.5 ms – 4 s, in 1.25 ms steps): how often the two sides meet. Shorter = lower latency, higher power. Longer = lower power, higher latency.
- **Peripheral Latency** (0 – 499, unitless): how many consecutive connection events the peripheral is allowed to *skip* if it has nothing to send. The central must still wake every interval. This is the peripheral's power-saving dial.
- **Supervision Timeout** (100 ms – 32 s, in 10 ms steps): how long the link is considered alive without a successful packet before both sides declare it lost. Must satisfy: `timeout > (1 + latency) × interval × 2`.

The "why" is a power/latency tradeoff. A heart-rate monitor streaming ECG needs a 7.5–15 ms interval. A glucose sensor that reports every 5 minutes can use a 1 s interval with latency 4 — the peripheral wakes once every 5 s, but the link stays alive because the central keeps pinging. The central's radio cost is unchanged, which is why Apple caps latency at 30 and requires intervals ≥ 15 ms for most accessories: the phone is the one paying the radio bill.

## Key Commands / Configuration / Code

**On the peripheral (Zephyr / nRF Connect SDK):** request parameters after connection, and re-request if the central pushes back.

```c
// Request 30 ms interval, latency 4, 6 s timeout.
// timeout must be > (1 + latency) * interval * 2 = (5 * 30ms * 2) = 300 ms. OK.
static struct bt_le_conn_param conn_param = {
    .interval_min = BT_GAP_MS_TO_CONN_INTERVAL(30),  // 24 units of 1.25ms
    .interval_max = BT_GAP_MS_TO_CONN_INTERVAL(50),  // 40 units
    .latency      = 4,
    .timeout      = BT_GAP_MS_TO_SUPERVISION_TIMEOUT(6000), // 600 units of 10ms
};

// Call from the connected callback, or later to renegotiate.
int err = bt_conn_le_param_update(conn, &conn_param);
if (err) {
    LOG_ERR("Param update failed: %d", err);
}
```

**On the central (BlueZ / `bluetoothctl`):** inspect and force parameters.

```bash
# Show current connection parameters for a connected device
bluetoothctl info AA:BB:CC:DD:EE:FF
# Look for: "Connection interval", "Peripheral latency", "Supervision timeout"

# Force a specific interval from the kernel side (requires root, debugfs)
echo "AA:BB:CC:DD:EE:FF 0x0006 0x0008 0 0x00c8" | \
  sudo tee /sys/kernel/debug/bluetooth/hci0/conn_min_interval 2>/dev/null
# Format: <bdaddr> <min_interval> <max_interval> <latency> <timeout>
# 0x0006 = 7.5ms, 0x0008 = 10ms, 0x00c8 = 2s
```

**On Android (Kotlin):** request high-priority parameters for a streaming characteristic.

```kotlin
// API 26+: request a fast connection for a critical characteristic.
gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
// HIGH  -> ~11.25 ms interval, latency 0
// BALANCED -> ~30 ms interval, latency 0
// LOW_POWER -> ~100-125 ms interval, latency 2
```

**On iOS:** you don't get to set parameters directly. You influence them via the `NSBluetoothAlwaysUsageDescription` and by how you use the link — iOS grants faster intervals to apps that read characteristics frequently. The `CBCentralManager` will honor `peripheral.maximumWriteValueLength` and the accessory's requested parameters only if they fit Apple's guidelines.

## Common Pitfalls & Gotchas

1. **Ignoring the timeout inequality.** `timeout > (1 + latency) × interval × 2` is not a suggestion — the controller will reject the update with `HCI_ERROR_INVALID_LL_PARAMS` (0x1E). A common bug: latency 4, interval 30 ms, timeout 300 ms. That's exactly equal, not greater. Bump to 320 ms.

2. **Apple's guidelines are stricter than the spec.** Apple requires interval ≥ 15 ms, latency ≤ 30, and timeout ≥ 2 s for most accessories. If you request 7.5 ms / latency 0 / 1 s timeout, iOS will silently reject and keep its defaults — and your "low latency" feature will mysteriously be slow on iPhones but fine on Android.

3. **Latency doesn't help if the peripheral has data.** If your sensor pushes a notification every connection event, latency is ignored — the peripheral wakes every interval anyway. Latency only saves power when the peripheral is genuinely idle. Don't set latency 4 and then notify every 100 ms; you've just made the link fragile for no benefit.

## Try It Yourself

1. **Measure the cost.** On an nRF52840 DK running the peripheral UART sample, use the Nordic Power Profiler Kit II to measure average current at interval 7.5 ms / latency 0 vs. interval 1 s / latency 4. You should see roughly a 10–20× difference in idle current.

2. **Break the timeout.** Deliberately set `timeout = (1 + latency) * interval * 2` (exactly equal) and observe the `bt_conn_le_param_update` return code and the HCI error. Then fix it by adding 100 ms.

3. **Cross-platform reality check.** Connect the same peripheral to an Android phone and an iPhone. Use `bluetoothctl info` on Linux as a control, then compare the negotiated parameters reported by `nRF Connect` on each phone. Note how iOS overrides your request.

## Next Up

Tomorrow we leave the Link Layer and enter the ATT protocol: **Attributes, Handles, UUIDs, and the MTU Exchange**. This is where "what can I actually read and write?" gets answered — and where the 23-byte default MTU bites you on every notification.
