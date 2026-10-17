---
title: "Day 07: ATT Protocol: Attributes, Handles, UUIDs & MTU Exchange"
date: 2026-10-17
tags: ["til", "ble-medical", "att", "mtu"]
---

## What I Explored Today

Today I dropped below GATT and spent the day with the Attribute Protocol (ATT), the wire-level protocol that GATT is built on top of. Everything a BLE medical device exposes — heart rate measurements, battery levels, device info — is ultimately an *attribute* stored in a server's attribute table, addressed by a 16-bit handle. I traced how handles get assigned, how UUIDs identify what an attribute *is*, and how the MTU exchange changes the maximum payload per ATT PDU. I also confirmed on a Nordic nRF52 and an ESP32 that the default ATT MTU of 23 bytes (20 bytes of payload after the 3-byte ATT header) is almost always too small for real medical payloads, and that negotiating a larger MTU is one of the highest-leverage optimizations you can make.

## The Core Concept

ATT is a client/server protocol. The **server** (your peripheral, e.g. a pulse oximeter) holds an **attribute table**: a flat, ordered list of attributes. Each attribute has four fields:

- **Handle** — a 16-bit address (0x0001–0xFFFF), unique within the server, assigned in ascending order. This is what the client actually uses on the wire.
- **Type** — a UUID (16-bit Bluetooth SIG, or 128-bit vendor) saying *what* the attribute is.
- **Value** — the bytes.
- **Permissions** — read/write/notify access rules enforced by the server.

The key insight: **handles are the addressing mechanism, UUIDs are the semantics.** GATT never sends UUIDs on the hot path — it sends handles. When your phone discovers a service, it's really walking the attribute table and reading the *type* UUID of each handle to build a map. After discovery, a "read heart rate" is just `ATT_READ_REQ(handle=0x0016)`.

This matters for medical devices because the attribute table is fixed at build time (or at least at boot). Handles are stable across connections but **not guaranteed stable across firmware versions** — if you insert a new characteristic, every handle after it shifts. Never hardcode handles in a client; always discover.

The **MTU exchange** is the other half. The ATT MTU is the max size of an ATT PDU. Default is 23 bytes. The ATT header is 1 byte opcode + 2 bytes handle (for most PDUs), leaving 20 bytes of payload. A single ECG sample packet or a multi-field vitals record easily exceeds that, forcing fragmentation at the L2CAP layer. The client initiates `ATT_EXCHANGE_MTU_REQ` with its supported RX MTU; the server replies with its own. The effective MTU is the **minimum** of the two, and it's asymmetric — each direction uses the other side's advertised value.

## Key Commands / Configuration / Code

**1. Reading the attribute table on a Linux host with BlueZ** — `gatttool` is deprecated but `bluetoothctl` still exposes handles:

```bash
# Connect and enumerate; note the "handle:" field on each line
bluetoothctl
[bluetooth]# connect AA:BB:CC:DD:EE:FF
[Medical Sensor]# list-attributes
# Attribute /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/service0001 ...
#   Characteristic .../char0002
#     Handle: 0x0010   <-- this is what goes on the wire
```

**2. MTU exchange on an ESP32 (ESP-IDF)** — request a larger MTU before discovery:

```c
// In the GAP event handler, after connect
case ESP_GATTC_CONNECT_EVT:
    // Request 517-byte MTU (common max on Android; iOS caps at 185)
    esp_ble_gattc_send_mtu_req(gattc_if, param->connect.conn_id);
    break;

case ESP_GATTC_CFG_MTU_EVT:
    ESP_LOGI(TAG, "Negotiated MTU: %d", param->cfg_mtu.mtu);
    // Payload per write = MTU - 3 (ATT header)
    break;
```

**3. Setting the server-side preferred MTU on nRF52 (Nordic SDK)** — in `ble_stack_init()` or before advertising:

```c
// sdk_config.h: NRF_SDH_BLE_GATT_MAX_MTU_SIZE
#define NRF_SDH_BLE_GATT_MAX_MTU_SIZE 247   // 244-byte payload
// The SoftDevice will honor the client's request up to this ceiling.
```

**4. Raw ATT MTU request PDU** (what actually goes on the wire, opcode 0x02):

```
02  FD 02
│   └──┴── Client RX MTU = 0x02FD = 765
└── ATT_EXCHANGE_MTU_REQ opcode
```

The server responds with opcode `0x03` and its own MTU. Effective MTU = min(client_rx, server_rx).

## Common Pitfalls & Gotchas

- **Assuming MTU is symmetric.** It isn't. If your phone advertises 517 but your peripheral caps at 247, the negotiated MTU is 247, and the *phone's* TX payload is limited by *your* RX MTU. Size your notification buffers to the negotiated value, not the requested one.
- **Hardcoding handles.** Handles shift when you add a characteristic. A client that caches `0x0016` as "heart rate" will silently read the wrong attribute after a firmware update. Always re-discover on reconnect, or use a service-changed characteristic (0x2A05) to invalidate caches.
- **Forgetting the 3-byte ATT header when sizing payloads.** A 20-byte notification is the *payload*; the PDU is 23 bytes. When you negotiate MTU 247, your max notification payload is 244, not 247. Off-by-three bugs here cause truncated vitals records that look like sensor faults.

## Try It Yourself

1. **Map a real attribute table.** Connect to any BLE peripheral you have (a fitness band, a dev board) with `bluetoothctl` or nRF Connect, run `list-attributes`, and write down the handle range for one service. Confirm the handles are contiguous and ascending.
2. **Measure the MTU effect.** On an ESP32 or nRF52, send a 100-byte notification with the default MTU (23) and capture it in Wireshark with the BLE sniffer. Count the fragments. Then negotiate MTU 247 and repeat — you should see a single PDU.
3. **Break a client on purpose.** Take a working client, insert a dummy characteristic at the top of your GATT table, reflash, and observe the handle shift. Then fix the client to discover dynamically. This is the single most common field failure in medical BLE integrations.

## Next Up

Tomorrow: **GATT Services & Characteristics: Properties, Descriptors & the CCCD.** We'll go from raw attributes to the GATT layer — how services group characteristics, what `READ`/`WRITE`/`NOTIFY`/`INDICATE` properties actually gate, and why the Client Characteristic Configuration Descriptor (0x2902) is the one descriptor every medical device must get right or notifications silently never arrive.
