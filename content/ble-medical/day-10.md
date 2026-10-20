---
title: "Day 10: Designing a Custom GATT Profile for a Medical Sensor"
date: 2026-10-20
tags: ["til", "ble-medical", "gatt-profile", "medical"]
---

## What I Explored Today

Today I moved past consuming standard GATT services and designed my own custom profile for a multi-parameter medical sensor — a small board reporting skin temperature, SpO₂, and a battery level. The goal was to understand the anatomy of a custom profile: how services, characteristics, descriptors, and permissions fit together, and how to lay them out so a central (phone or gateway) can discover and subscribe to them without ambiguity. I used Nordic's nRF Connect SDK (Zephyr) on an nRF52840, but the concepts map 1:1 to ESP-IDF, STM32WB, or any BLE stack.

## The Core Concept

A GATT profile is really a contract: it tells a client *what* data exists, *how* to read or subscribe to it, and *what format* the bytes are in. The Bluetooth SIG defines 16-bit UUIDs for adopted services and characteristics, but for anything custom you use a 128-bit UUID. The temptation is to cram everything into one characteristic — resist it. Each logically independent measurement should be its own characteristic so a client can subscribe to temperature without waking up for SpO₂ notifications.

Two design decisions dominate the layout:

1. **Service boundaries.** Group characteristics that share a lifecycle. A "Medical Sensor Service" holding temperature + SpO₂ makes sense; battery belongs in the standard Battery Service (0x180F) so off-the-shelf tooling recognizes it.
2. **Characteristic properties and permissions.** Properties (read, write, notify, indicate) are what the client sees. Permissions (read/write with encryption/authentication) are enforced by the stack. For medical data, notifications should require an encrypted link — mark the characteristic as requiring encryption so the stack rejects access on a plaintext connection.

For multi-byte values, always attach a **Characteristic Presentation Format** descriptor (0x2904) and, for aggregate measurements, a **Characteristic Aggregate Format** (0x2905). This is what lets a generic client decode your float without a hardcoded parser. Use IEEE-11073 SFLOAT for medical values where the SIG does, but a plain `float32` (format 0x14) is acceptable for custom characteristics as long as you document it.

## Key Commands / Configuration / Code

Defining the service in Zephyr's GATT database (`.gatt`-style, using the BT_GATT_SERVICE_DEFINE macro):

```c
/* 128-bit custom UUIDs — generate once, keep them stable across firmware versions */
#define MED_SVC_UUID \
    BT_UUID_128_ENCODE(0x1b4e28ba, 0x2fa1, 0x11d3, 0x9d3b, 0x0016f2a5c1e0)
#define MED_TEMP_UUID \
    BT_UUID_128_ENCODE(0x1b4e28ba, 0x2fa1, 0x11d3, 0x9d3b, 0x0016f2a5c1e1)
#define MED_SPO2_UUID \
    BT_UUID_128_ENCODE(0x1b4e28ba, 0x2fa1, 0x11d3, 0x9d3b, 0x0016f2a5c1e2)

static struct bt_gatt_attr attrs[] = {
    BT_GATT_PRIMARY_SERVICE(BT_UUID_DECLARE_128(MED_SVC_UUID)),

    /* Temperature: notify + read, requires encryption */
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_128(MED_TEMP_UUID),
        BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ_ENCRYPT,          /* plaintext read is rejected */
        read_temp, NULL, &temp_value),
    BT_GATT_CCC(temp_ccc_changed,           /* CCC: subscribe/unsubscribe callback */
        BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_ENCRYPT),
    /* Presentation format: float32, unit = Celsius (0x272F), 1 decimal */
    BT_GATT_CPF(BT_GATT_CPF_FORMAT_FLOAT32, 0, 0x272F, 0x01, 0),

    /* SpO2: notify only, percent, requires encryption */
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_128(MED_SPO2_UUID),
        BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_NONE,                  /* no direct read */
        NULL, NULL, &spo2_value),
    BT_GATT_CCC(spo2_ccc_changed,
        BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_ENCRYPT),
    BT_GATT_CPF(BT_GATT_CPF_FORMAT_UINT8, 0, 0x27AD, 0x00, 0),
};

BT_GATT_SERVICE_DEFINE(med_svc, attrs);
```

Sending a notification (only fires if the client subscribed):

```c
float temp = read_sensor_celsius();
bt_gatt_notify(NULL, &attrs[1], &temp, sizeof(temp));
```

Inspecting the result from a Linux host with BlueZ:

```bash
# Discover the custom service and its characteristics
bluetoothctl
> connect AA:BB:CC:DD:EE:FF
> menu gatt
> list-attributes
# Subscribe to notifications on the temperature characteristic
> select-attribute /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/service000c/char000d
> notify on
```

## Common Pitfalls & Gotchas

- **Forgetting the CCC descriptor.** A characteristic with `BT_GATT_CHRC_NOTIFY` but no Client Characteristic Configuration descriptor will never let the client subscribe — `bt_gatt_notify` silently does nothing. The `BT_GATT_CCC` entry is mandatory for notify/indicate.
- **Permissions vs. properties mismatch.** Setting `BT_GATT_PERM_READ` on a notify-only characteristic exposes the value to any client that reads it, bypassing your subscription model. Use `BT_GATT_PERM_NONE` and rely on notifications.
- **Unstable UUIDs.** Regenerating the 128-bit UUID between builds breaks every bonded client's cached attribute handles. Freeze your UUIDs and version the service (e.g., bump the last byte) only on a breaking layout change.

## Try It Yourself

1. Add a third characteristic for a device status enum (uint8) with read + indicate, and confirm in nRF Connect that the indicate handshake completes.
2. Attach a `BT_GATT_CPF` descriptor to your temperature characteristic and verify a generic client (e.g., the nRF Connect "float" view) decodes it without a custom parser.
3. Set the temperature characteristic's read permission to `BT_GATT_PERM_READ_ENCRYPT` and confirm a read over an unpaired link returns *Insufficient Authentication*.

## Next Up

Tomorrow I'll compare my hand-rolled profile against the SIG's adopted medical services — Heart Rate (0x180D), Health Thermometer (0x1809), Pulse Oximeter (0x1822), and the Generic Health Sensor (GHS) profile — and figure out when to reuse them instead of reinventing the wheel.
