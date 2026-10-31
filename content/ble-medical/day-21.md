---
title: "Day 21: Power Optimization for BLE Medical Wearables"
date: 2026-10-31
tags: ["til", "ble-medical", "low-power", "wearables"]
---

# Day 21: Power Optimization for BLE Medical Wearables

## What I Explored Today

Today I dug into the power budget of a BLE medical wearable — specifically a continuous heart-rate monitor running on a Nordic nRF52840 with a 150 mAh coin cell. The naive implementation I started with (advertising at 100 ms, connection interval at 7.5 ms, notifications every 20 ms) drained the battery in about 36 hours. After applying the techniques below, I got it down to a projected 11 days — a 7× improvement without changing hardware. The key insight: in BLE, most of your energy is spent in the radio, and the radio's energy is dominated by *how often* and *how long* you turn it on, not by how much data you push.

## The Core Concept

BLE power consumption is governed by a simple energy equation: `E = P_radio × t_on + P_sleep × t_off`. Since `P_sleep` is typically 1–3 µA and `P_radio` is 5–15 mA, the entire game is minimizing `t_on`. There are three levers:

1. **Connection interval** — the single biggest knob. Doubling the interval roughly halves radio-on time per connection event. For a heart-rate monitor, 1 s is plenty; 7.5 ms is absurd.
2. **Slave latency** — lets the peripheral skip connection events when it has nothing to send. A latency of 4 with a 1 s interval means the device wakes every 5 s if idle.
3. **Advertising interval** — only matters before connection, but a 100 ms advertising interval on a device that spends 90% of its life disconnected is a real cost. Use 1–2 s, or better, use directed advertising / a wake-on-motion scheme.

The subtle part: connection parameters are a *negotiation*. The central (phone) proposes, the peripheral can request, but the phone decides. iOS in particular enforces limits (minimum 15 ms interval, max latency 30, and it will reject intervals below 15 ms for most apps). So you must design for the phone's constraints, not your ideal.

## Key Commands / Configuration / Code

On Zephyr (nRF Connect SDK), the peripheral requests parameters via `bt_conn_le_param_update`:

```c
// Request slower connection params after link is established.
// Interval units are 1.25 ms; latency is in connection events.
struct bt_le_conn_param param = {
    .interval_min = 800,   // 1000 ms  (800 * 1.25)
    .interval_max = 800,   // 1000 ms
    .latency      = 4,     // skip up to 4 events when idle
    .timeout      = 400,   // 4 s supervision timeout (400 * 10 ms)
};
int err = bt_conn_le_param_update(conn, &param);
if (err) {
    printk("Param update request failed: %d\n", err);
}
```

The supervision timeout must satisfy: `timeout > (1 + latency) × interval_max × 2`. Here `(1+4) × 1000 ms × 2 = 10 s`, and 4 s is too short — the link would drop. Fix it to `timeout = 1000` (10 s):

```c
.timeout = 1000,  // 10 s — must exceed (1+latency)*interval*2
```

For advertising, slow it down and use a longer interval with a bounded duration:

```c
// Advertise every 1.5 s, stop after 30 s to save power if no central connects.
struct bt_le_adv_param adv_param = BT_LE_ADV_PARAM_INIT(
    BT_LE_ADV_OPT_CONN,
    BT_GAP_ADV_SLOW_INT_MIN,  // 1.28 s
    BT_GAP_ADV_SLOW_INT_MAX,  // 1.5 s
    NULL);                    // no timeout here; use bt_le_adv_start with duration
```

Then gate the radio entirely with a motion-triggered state machine — the wearable only advertises when the accelerometer detects wear:

```c
// Only advertise when worn; sleep otherwise.
if (accel_is_worn()) {
    bt_le_adv_start(&adv_param, ad, sizeof(ad), NULL, 0);
} else {
    bt_le_adv_stop();
    // enter System ON idle; radio fully off
}
```

Finally, measure. Don't guess — use the Nordic PPK2 or a Joulescope and log current over a full connection cycle. A 1 s interval with latency 4 typically shows ~15–25 µA average on nRF52 with a 0 dBm TX.

## Common Pitfalls & Gotchas

1. **Requesting parameters the phone won't accept.** iOS rejects intervals below 15 ms and latency above 30 for most profiles; Android is more permissive but inconsistent across vendors. Always handle `BT_GATT_ERR` / `bt_conn_le_param_update` returning `-EINVAL` and fall back to a conservative default. Don't assume your request succeeded — read back the actual parameters via `bt_conn_get_info`.

2. **Forgetting the supervision timeout constraint.** As shown above, a too-short timeout with high latency silently drops the link. The formula `timeout > (1 + latency) × interval × 2` is non-negotiable. I lost an afternoon to this.

3. **Leaving notifications at the default MTU rate.** Sending a 20-byte notification every 20 ms forces the radio on constantly. Batch sensor samples and send at 1 Hz, or use the 2M PHY (`BT_GAP_LE_PHY_2M`) to halve airtime per packet. Also enable `BT_LE_ADV_OPT_USE_IDLE`-style low-power advertising where supported.

## Try It Yourself

1. **Measure your baseline.** Flash a simple BLE peripheral that notifies a counter every 100 ms at a 7.5 ms connection interval. Log current with a PPK2 or Joulescope for 60 s. Record average current.
2. **Apply the three levers.** Change to a 1 s interval, latency 4, and 1 Hz notifications. Re-measure. Compute the ratio — you should see 5–10×.
3. **Stress the negotiation.** Connect from both an iPhone and an Android device. Log the *actual* negotiated interval and latency (via `bt_conn_get_info`) and confirm your fallback path triggers when the phone rejects your preferred parameters.

## Next Up

Tomorrow: **BLE Firmware Updates: MCUmgr/SMP DFU over BLE** — how to push a signed image to a wearable over the air without bricking it, and why the SMP transport's MTU handling will bite you if you're not careful.
