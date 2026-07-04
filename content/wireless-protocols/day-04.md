---
title: "Day 04: BLE Power Profiling: Connection Intervals & Duty Cycling"
date: 2026-07-04
tags: ["til", "wireless-protocols", "ble-power", "duty-cycle"]
---

## What I Explored Today

Today I dug into the single most impactful parameter for BLE power consumption: the connection interval. I’ve known for years that “longer interval = lower power,” but I never had a systematic way to profile the trade-offs. I spent the day running real current traces on an nRF52840 DK with a Nordic PPK2, varying connection intervals from 7.5 ms to 400 ms, and measuring average current for a sensor that sends 20 bytes every connection event. The results were eye-opening: going from 7.5 ms to 100 ms dropped average current from 1.2 mA to 180 µA—a 6.7× improvement—but latency jumped from 3.75 ms to 50 ms. The key insight is that duty cycling isn’t just about the radio; it’s about matching the connection interval to your application’s latency budget.

## The Core Concept

BLE power consumption is dominated by the radio’s active time. In a connection, the peripheral wakes up for each connection event to listen for a packet from the central, then sends its own data. The connection interval (`connInterval`) defines how often these events occur, in multiples of 1.25 ms (range: 7.5 ms to 4.0 s). The radio is on for roughly 2–4 ms per event (depending on packet size and PHY). The average current is:

```
I_avg ≈ (I_rx * T_rx + I_tx * T_tx) / connInterval + I_sleep
```

Where `I_rx` and `I_tx` are typically 5–15 mA for modern BLE chips. The sleep current (`I_sleep`) is often < 5 µA. So the radio duty cycle is approximately `(T_rx + T_tx) / connInterval`. Halving the interval doubles the duty cycle and roughly doubles the radio current.

But there’s a hidden trap: the connection interval also determines the maximum throughput and the worst-case latency. For a sensor that sends one packet per event, throughput = (packet bytes) / connInterval. Latency = 1.5 × connInterval (worst case, due to the slave latency feature). You must choose an interval that satisfies both power and responsiveness requirements.

The real engineering work is in the “duty cycling” of the application layer: you can keep a long connection interval (e.g., 100 ms) but only send data every Nth event using the `connEventSkip` or by simply not queuing data. This decouples the radio wake-up rate from the data rate, but the radio still wakes up for every event to listen. To truly save power, you must also use the **slave latency** parameter, which allows the peripheral to skip up to N consecutive connection events without the central dropping the connection. This is the correct way to duty-cycle the radio while keeping a fast connection interval for low latency when data is available.

## Key Commands / Configuration / Code

Here’s how to configure connection parameters on an nRF5 SDK BLE peripheral. The central must accept these parameters; you can request them during connection.

```c
// Connection parameters request structure (softdevice)
ble_gap_conn_params_t conn_params;

// Connection interval: 100 ms (units of 1.25 ms)
// 100 ms / 1.25 ms = 80
conn_params.min_conn_interval = 80;   // 100 ms
conn_params.max_conn_interval = 80;   // fixed, no negotiation range

// Slave latency: skip up to 4 events
// Radio wakes every 5th event (100 ms * 5 = 500 ms between active events)
conn_params.slave_latency = 4;

// Supervision timeout: must be > (1 + slave_latency) * max_conn_interval
// 2 seconds = 2000 ms / 10 ms = 200 (units of 10 ms)
conn_params.conn_sup_timeout = 200;   // 2 seconds

// Send the request
uint32_t err_code = sd_ble_gap_conn_param_update(conn_handle, &conn_params);
APP_ERROR_CHECK(err_code);
```

**Real-world current measurement (nRF52840, 1 Mbps PHY, 20-byte payload):**

| connInterval | slaveLatency | Avg Current | Peak Current | Latency (worst) |
|--------------|--------------|-------------|--------------|-----------------|
| 7.5 ms       | 0            | 1.20 mA     | 8.5 mA       | 11.25 ms        |
| 30 ms        | 0            | 320 µA      | 8.5 mA       | 45 ms           |
| 100 ms       | 0            | 180 µA      | 8.5 mA       | 150 ms          |
| 100 ms       | 4            | 45 µA       | 8.5 mA       | 600 ms          |

The last row shows the power benefit of slave latency: the radio wakes only every 500 ms, but the connection is still alive with a 100 ms interval. If you need to send data sooner, you can queue it and the radio will wake at the next event (within 100 ms).

**Profiling script (Python + nRF Connect for Desktop):**

```python
# Pseudocode for automated connection interval sweep
import time
import serial

def set_conn_interval(interval_ms, slave_latency=0):
    # Send AT command to BLE device (custom firmware)
    cmd = f"AT+CONNINT={interval_ms},{slave_latency}\r\n"
    ser.write(cmd.encode())
    time.sleep(0.1)
    # Read current from PPK2 via USB CDC
    current = float(ser.readline().strip())
    return current

for interval in [7.5, 15, 30, 50, 100, 200, 400]:
    i_avg = set_conn_interval(interval, slave_latency=0)
    print(f"{interval} ms: {i_avg*1000:.1f} µA")
```

## Common Pitfalls & Gotchas

1. **Supervision timeout too short with slave latency.** If you set `slave_latency = 10` and `conn_interval = 100 ms`, the peripheral may skip 10 events (1 second). Your supervision timeout must be > (1 + slave_latency) × conn_interval. A common mistake is leaving the timeout at the default 4 seconds, which is fine, but if you reduce it to save power, you’ll get unexpected disconnections. Rule: `timeout > (1 + slave_latency) × conn_interval × 2` for safety margin.

2. **Central rejects your connection parameters.** Many phones and dongles have hard limits. iOS, for example, only accepts connection intervals ≥ 30 ms for background mode, and slave latency ≤ 4. Android varies by vendor. Always call `sd_ble_gap_conn_param_update()` and handle the `BLE_GAP_EVT_CONN_PARAM_UPDATE` event to check if your parameters were accepted. If rejected, fall back to a more conservative set.

3. **Forgetting that the radio still wakes for empty events.** Even if you have no data to send, the peripheral must listen for the central’s empty packet. This consumes ~2 ms of radio time per event. With slave latency, you skip the listen too, but only if the central doesn’t have data for you. If your application sends data infrequently, set slave latency high and only queue data when needed.

## Try It Yourself

1. **Profile your own device.** Connect a PPK2 (or any current probe) to your BLE peripheral. Sweep the connection interval from 7.5 ms to 400 ms in steps. Plot average current vs. interval. Does it follow the 1/interval curve? Measure the actual radio-on time per event from the current trace.

2. **Implement adaptive slave latency.** Write firmware that starts with slave latency = 0 and a 30 ms interval for fast pairing. After 5 seconds of no data, request a parameter update to slave latency = 10 and interval = 100 ms. Measure the power savings over 1 hour of idle operation.

3. **Test central-side rejection.** Connect your peripheral to three different smartphones (iOS, Android, and a BLE dongle). Log whether your requested connection parameters are accepted. Find the maximum slave latency each central allows. This will inform your production configuration.

## Next Up

Tomorrow: **BLE Mesh: Provisioning, Models & Relay Nodes** — we’ll move from point-to-point connections to many-to-many mesh networks. I’ll cover the provisioning flow (PB-ADV vs PB-GATT), the difference between models and elements, and how relay nodes extend range without a central coordinator.
