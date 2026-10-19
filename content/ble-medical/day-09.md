---
title: "Day 09: Notifications vs Indications & Throughput Tuning (DLE, 2M PHY)"
date: 2026-10-19
tags: ["til", "ble-medical", "notifications", "throughput"]
---

## What I Explored Today

Today I dug into the two ways a GATT server can push data to a client — notifications and indications — and why the choice matters far more for medical devices than the spec's one-line summary suggests. I also spent time on the plumbing that actually determines whether a notification stream is useful: Data Length Extension (DLE), the 2M PHY, and how connection interval and MTU interact to set the real ceiling on throughput. For a continuous ECG or SpO2 stream, "just use notifications" is the starting point, not the answer — you have to tune the link or you'll bottleneck at a fraction of what the radio can do.

## The Core Concept

Both notifications and indications are server-initiated ATT PDUs that carry a handle and a value. The difference is acknowledgment semantics:

- **Notification** (`ATT_HANDLE_VALUE_NTF`, opcode `0x1B`): fire-and-forget. The server sends it and moves on. No ATT-level confirmation. Fast, but lossy at the application layer — if the link drops the packet, the client never knows.
- **Indication** (`ATT_HANDLE_VALUE_IND`, opcode `0x1D`): the client must respond with `ATT_HANDLE_VALUE_CFM` (`0x1E`) before the server may send the next indication. This gives you guaranteed delivery and ordering, but it serializes the link: exactly one indication in flight at a time.

For medical telemetry the trade-off is concrete. A 500 Hz ECG stream cannot tolerate the round-trip stall of indications — each one waits a full connection interval (or more) for the confirm, capping you at roughly one sample per interval. Notifications let you pack multiple samples per interval. But for an alarm event, a bolus-complete flag, or a configuration acknowledgment, an indication is exactly right: you want the client to confirm receipt, and the low rate makes the serialization irrelevant.

The throughput side is where people get surprised. A notification's payload is bounded by `ATT_MTU - 3` (the 3-byte ATT header). With the default MTU of 23, that's 20 bytes per packet. The number of packets per connection event is bounded by what fits in the event, which depends on **Data Length Extension** (payload up to 251 bytes per LL packet) and the **PHY** (1M vs 2M symbols/sec). Tuning all three — MTU, DLE, PHY — is what turns a 20-byte trickle into a real stream.

## Key Commands / Configuration / Code

Negotiating a larger MTU (client side, BlueZ via `bluetoothctl` or a GATT library). Most stacks expose an exchange-MTU call:

```c
// ESP-IDF (NimBLE / Bluedroid) — client requests a larger ATT MTU
// Must be called after connection established, before subscribing.
esp_ble_gattc_send_mtu_req(gattc_if, conn_id);
// Result arrives in ESP_GATTC_CFG_MTU_EVT; check mtu field.
// Effective notification payload = mtu - 3.
```

Requesting DLE and 2M PHY (ESP-IDF, server or client after connect):

```c
// Ask the controller for 251-byte LL payloads (max TX octets).
esp_ble_gap_set_pkt_data_len(remote_bda, 251);

// Prefer 2M PHY for higher symbol rate; falls back to 1M if peer can't.
esp_ble_gap_set_prefered_phy(remote_bda,
    ESP_BLE_GAP_PHY_2M_PREF_MASK,
    ESP_BLE_GAP_PHY_2M_PREF_MASK,
    ESP_BLE_GAP_PHY_OPTIONS_NO_PREF);
// Confirm actual PHY in ESP_GAP_BLE_UPDATE_PHY_COMPLETE_EVT (tx_phy/rx_phy).
```

Subscribing on the client — write the CCCD (Client Characteristic Configuration Descriptor, `0x2902`) to enable notifications (`0x0001`) or indications (`0x0002`):

```c
// Enable notifications on a characteristic's CCCD.
uint8_t cccd_val[2] = {0x01, 0x00}; // little-endian: notify bit set
esp_ble_gattc_write_char_descr(gattc_if, conn_id,
    cccd_handle, sizeof(cccd_val), cccd_val,
    ESP_GATT_WRITE_TYPE_RSP, ESP_GATT_AUTH_REQ_NONE);
// For indications use {0x02, 0x00}; the stack then auto-sends the CFM
// on each ESP_GATTC_..._IND event once your handler returns.
```

Sending a notification from the server (NimBLE host):

```c
// ble_gatts_notify_custom sends ATT_HANDLE_VALUE_NTF.
// om is the mbuf chain holding the value; length <= (mtu - 3).
ble_gatts_notify_custom(conn_handle, val_handle, om);
```

A quick sanity check on the ceiling: with MTU 247 (244-byte payload), DLE on, 2M PHY, and a 15 ms connection interval, you can realistically push several hundred kbit/s — versus ~20 bytes × a few packets per event on defaults. Measure, don't assume; the controller's event-length limits often bite before the math says they should.

## Common Pitfalls & Gotchas

1. **Enabling both notify and indicate bits on one CCCD.** The spec allows only one to be active at a time for a given client. Writing `0x03` is invalid; pick one per characteristic. If you need both semantics, use two characteristics.
2. **Assuming MTU negotiation succeeded.** The peer can reject or cap the MTU. Always read back the negotiated value from the completion event and size your payloads to `mtu - 3` — sending a longer notification gets truncated or dropped by the stack.
3. **Chasing 2M PHY without DLE.** A 2M PHY with 27-byte LL payloads gains little because per-packet overhead dominates. DLE and 2M together are what move the needle; tune them as a pair and verify the actual PHY in the completion callback, since the peer may decline.

## Try It Yourself

1. **Measure the difference.** Connect a dev board to a phone running nRF Connect, enable notifications on a test characteristic, and log the notification rate at default MTU vs. after requesting MTU 247. Compute effective bytes/sec both times.
2. **Force an indication.** Add a second characteristic configured for indications and send the same payload. Observe the CFM round-trip in a sniffer (nRF Sniffer or Ellisys) and note how the interval gates your rate.
3. **Toggle the PHY.** Request 2M PHY and confirm via the update-PHY event whether it was accepted. Then disable DLE and re-measure to see how much of your gain came from each knob.

## Next Up

Tomorrow: **Designing a Custom GATT Profile for a Medical Sensor** — laying out services, characteristics, and descriptors that survive regulatory review, and why your characteristic properties and permissions are part of your safety story.
