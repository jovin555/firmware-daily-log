---
title: "Day 13: DFMEA: Wireless Link Failure Modes (BLE Dropouts, Data Loss, Latency)"
date: 2026-10-23
tags: ["til", "medical-iot-dfmea", "ble", "wireless"]
---

## What I Explored Today

Today I moved the DFMEA from the power subsystem into the connectivity block, specifically the BLE link between our wearable pulse-ox patch and the bedside gateway. The failure modes here are deceptively subtle: a dropped connection is obvious, but a link that stays "connected" while silently losing notifications or stretching latency past the clinical alarm threshold is far more dangerous. I spent the day mapping three failure modes — connection dropouts, data loss (packet/notification loss), and latency excursions — against severity, occurrence, and detection, then instrumented the firmware to actually measure them instead of guessing.

## The Core Concept

The reason BLE link failures deserve their own DFMEA line items is that the protocol hides most of its failure modes behind a "connected" state. A GATT connection can persist while the peripheral's notifications are being dropped by the controller's TX buffer, while the connection interval has drifted to 2 seconds, or while the phone/gateway is doing a background scan that starves the radio. In a medical device, the failure effect isn't "user annoyed" — it's "SpO₂ alarm delayed 8 seconds" or "trend data gap of 30 samples."

DFMEA forces you to separate *detection* from *effect*. For a BLE dropout, detection is usually the link-supervision timeout (or your own heartbeat). For data loss, detection requires a sequence number or a monotonic counter in the payload — the stack won't tell you a notification was dropped. For latency, detection requires timestamping at the sensor and comparing at the gateway. Each of these detection mechanisms is itself a design control you can assign an occurrence and detection rating to.

The other key insight: BLE parameters are a *trade space*, not a setting. Shorter connection intervals reduce latency but raise current draw and collision probability; longer supervision timeouts survive dropouts but delay reconnection detection. Your DFMEA severity ranking should drive which side of that trade you land on.

## Key Commands / Configuration / Code

**1. Tighten and document the connection parameters (nRF Connect SDK / Zephyr).** The defaults are too loose for a 1 Hz vitals stream.

```c
/* prj.conf — Zephyr BLE peripheral */
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_CTLR_TX_PWR_PLUS_4=y      /* max TX power; verify against RF exposure budget */
CONFIG_BT_L2CAP_TX_MTU=247          /* larger MTU = fewer packets per sample batch */
CONFIG_BT_BUF_ACL_TX_COUNT=8        /* headroom so notifications don't silently drop */
```

```c
/* Request a 15–30 ms interval, 0 latency, 4 s supervision timeout.
 * Supervision timeout MUST satisfy: timeout > (1 + latency) * interval * 2
 * 4000 ms > (1+0) * 30 ms * 2 = 60 ms  ✓  */
static struct bt_le_conn_param conn_params = {
    .interval_min = BT_GAP_MS_TO_CONN_INTERVAL(15),
    .interval_max = BT_GAP_MS_TO_CONN_INTERVAL(30),
    .latency      = 0,
    .timeout      = BT_GAP_MS_TO_SUPERVISION_TIMEOUT(4000),
};
bt_conn_le_param_update(conn, &conn_params);
```

**2. Detect data loss with a sequence counter — the stack won't do it for you.**

```c
static uint32_t seq = 0;

struct __attribute__((packed)) vitals_pkt {
    uint32_t seq;        /* gateway checks for gaps */
    uint32_t uptime_ms;  /* latency = gateway_rx_time - uptime_ms */
    uint16_t spo2;
    uint16_t hr;
};

int send_vitals(uint16_t spo2, uint16_t hr) {
    struct vitals_pkt p = {
        .seq = seq++,
        .uptime_ms = k_uptime_get_32(),
        .spo2 = spo2, .hr = hr,
    };
    /* bt_gatt_notify returns -ENOMEM if TX buffers are full — treat as a
     * DFMEA-detectable event, not a silent drop. */
    int err = bt_gatt_notify(NULL, &vitals_svc.attrs[1], &p, sizeof(p));
    if (err) { LOG_WRN("notify failed: %d (seq %u)", err, p.seq); }
    return err;
}
```

**3. Measure latency and loss on the gateway side (BlueZ / Python).**

```python
# gateway.py — gap detection + latency histogram
last_seq = None
latencies = []
def on_notify(_, data):
    global last_seq
    seq, uptime_ms, spo2, hr = struct.unpack("<IIHH", data)
    if last_seq is not None and seq != last_seq + 1:
        print(f"LOSS: expected {last_seq+1}, got {seq}")   # DFMEA detection hook
    last_seq = seq
    latencies.append(time.monotonic()*1000 - uptime_ms)     # clock-sync caveat below
```

**4. Capture the over-the-air truth when you suspect the controller is the culprit.**

```bash
# nRF Sniffer + Wireshark: filter to your device, watch for empty PDUs and retries
tshark -i /dev/ttyACM0 -Y "btle" -T fields \
  -e btle.control_opcode -e btle.data_header.llid -e btle.crc
```

## Common Pitfalls & Gotchas

- **`bt_gatt_notify()` returning 0 does not mean the peer received it.** It means the packet was queued to the controller. If `CONFIG_BT_BUF_ACL_TX_COUNT` is exhausted, you get `-ENOMEM`; if the controller retransmits past its limit, the packet is dropped with no callback. Always carry a sequence number and let the application layer detect loss.
- **Supervision timeout math is a hard constraint, not a suggestion.** If `timeout ≤ (1 + latency) × interval × 2`, the controller rejects the parameter update with `BT_HCI_ERR_INVALID_LL_PARAMS` and silently keeps the old values. Log the actual negotiated interval after `bt_conn_le_param_update` — the peer can (and will) pick anything in your min/max range.
- **Latency measurement across two unsynchronized clocks is garbage.** My first `uptime_ms` subtraction showed 40-second latencies because the gateway's `time.monotonic()` and the patch's `k_uptime_get_32()` share no epoch. Either timestamp at the gateway on RX and measure inter-arrival jitter, or sync clocks (BLE has no native time service; use a periodic offset calibration).

## Try It Yourself

1. **Break the link on purpose.** Set `CONFIG_BT_BUF_ACL_TX_COUNT=2` and stream at 10 Hz. Confirm you see `-ENOMEM` from `bt_gatt_notify` and that your sequence-gap detector on the gateway catches the loss. Record the occurrence rating this justifies in your DFMEA.
2. **Sweep the connection interval.** Run the link at 15 ms, 100 ms, and 500 ms intervals and log p50/p95 latency and current draw for each. Plot the trade curve — this is your design-control evidence for the latency failure mode.
3. **Force a supervision timeout.** Walk the peripheral out of range (or use an RF shield box) and measure the time from last good packet to `BT_HCI_EVT_DISCONNECTED` on the gateway. Compare against your 4 s timeout and your clinical alarm budget.

## Next Up

Tomorrow: **DFMEA: Firmware & Software Failure Modes and IEC 62304 Linkage** — how to map software failure modes (watchdog resets, state-machine deadlocks, OTA corruption) to IEC 62304 software safety classes, and why your DFMEA and your software hazard analysis must agree on severity ratings.
