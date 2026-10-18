---
title: "Day 08: GATT Services & Characteristics: Properties, Descriptors & the CCCD"
date: 2026-10-18
tags: ["til", "ble-medical", "gatt", "cccd"]
---

## What I Explored Today

Today I dug into the GATT layer itself — the part of BLE that actually carries medical data. Up to now I've been treating services and characteristics as opaque handles that "just work" once you discover them. That's fine until you need to subscribe to a heart-rate measurement stream, and suddenly the CCCD descriptor matters, the characteristic *properties* byte matters, and the difference between "notify" and "indicate" stops being academic. I spent the day with `bluetoothctl`, `btmon`, and a Nordic nRF52 dev board, mapping the attribute table of a standard Heart Rate Service and watching what actually happens on the wire when a central subscribes.

## The Core Concept

GATT is a *server* that exposes an attribute table; the client (central) reads and writes entries in that table. The table is organized hierarchically: **services** group related data, **characteristics** hold a single value plus metadata, and **descriptors** describe a characteristic.

The metadata that trips people up is the **properties** field on each characteristic. It's a bitmask telling the client *how* it may interact with the value: `Read`, `Write`, `Write Without Response`, `Notify`, `Indicate`, `Signed Write`, `Broadcast`, `Authenticated Signed Write`, `Extended Properties`. A characteristic that supports `Notify` is useless to a subscriber until the client tells the server "yes, send me those." That's what the **Client Characteristic Configuration Descriptor (CCCD)** is for — a 2-byte descriptor (UUID `0x2902`) whose value is a bitfield: bit 0 = notifications enabled, bit 1 = indications enabled. Writing `0x0001` subscribes to notifications; `0x0002` subscribes to indications; `0x0000` unsubscribes.

Why a descriptor and not a command? Because GATT is deliberately dumb — it's just an attribute table. Subscription state is *state*, so it lives in an attribute. The server keeps the CCCD value per-client (per bonded connection) and only pushes data to clients that have set the bit. This is also why the CCCD must be **bonded/persistent** for medical devices: if the bond is lost, the subscription is lost, and a monitor that assumes it's still streaming will silently stop delivering alarms.

Descriptors aren't only the CCCD. The **Characteristic User Description** (`0x2901`) gives a human-readable label, and the **Characteristic Presentation Format** (`0x2904`) encodes units, exponent, and format — critical for medical values where "37" means nothing without "°C, signed 16-bit, exponent 0."

## Key Commands / Configuration / Code

Discover the attribute table and inspect properties with `bluetoothctl`:

```bash
# Connect and list GATT attributes (services, characteristics, descriptors)
bluetoothctl
[bluetooth]# connect AA:BB:CC:DD:EE:FF
[Heart Rate]# menu gatt
[Heart Rate]# list-attributes

# Example output (abridged):
# Service 0000180d-... (Heart Rate)
#   Characteristic 00002a37-... (Heart Rate Measurement)  flags: notify
#     Descriptor 00002902-... (Client Characteristic Configuration)
#   Characteristic 00002a38-... (Body Sensor Location)     flags: read
```

Subscribe by writing the CCCD directly:

```bash
# Enable notifications: write 0x0001 (little-endian) to the CCCD handle
[Heart Rate]# select-attribute /org/bluez/hci0/dev_AA_.../service.../char.../desc...
[Heart Rate]# write "0x01 0x00"

# Now notifications arrive as "Characteristic Value Changed" events
[Heart Rate]# notify on
```

On the firmware side (Zephyr, nRF Connect SDK), the CCCD is generated for you — but you must handle the subscription callback and gate your sends on it:

```c
/* Zephyr: define a notify-only characteristic with a CCCD */
static struct bt_gatt_attr attrs[] = {
    BT_GATT_PRIMARY_SERVICE(&hrs_svc),
    BT_GATT_CHARACTERISTIC(&hrs_meas_uuid.uuid,
        BT_GATT_CHRC_NOTIFY,               /* properties: notify only */
        BT_GATT_PERM_NONE,                 /* value not directly readable */
        NULL, NULL, NULL),
    BT_GATT_CCC(hrs_ccc_changed,           /* CCCD + callback */
        BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static bool notify_enabled;

static void hrs_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    /* value is the CCCD bitfield: 0x0001 = notify, 0x0002 = indicate */
    notify_enabled = (value & BT_GATT_CCC_NOTIFY) != 0;
}

/* Only push when the client actually subscribed */
if (notify_enabled) {
    bt_gatt_notify(NULL, &attrs[1], &meas, sizeof(meas));
}
```

The `BT_GATT_CCC` macro auto-creates the `0x2902` descriptor and routes writes to your callback. Note `BT_GATT_PERM_NONE` on the value: a notify-only characteristic typically isn't readable, so the client *must* subscribe to get data.

## Common Pitfalls & Gotchas

- **Forgetting the CCCD is per-connection and per-bond.** A medical monitor that caches "subscribed = true" in flash without tying it to a bond will keep notifying into the void after a re-pair, or worse, leak patient data to a reconnecting client that never subscribed. Always re-check the CCCD value on reconnect.
- **Confusing `Notify` with `Indicate` at the property level.** They're separate bits. A characteristic can advertise both, and the client picks one via the CCCD. If your device only sets `BT_GATT_CHRC_NOTIFY` but a client writes `0x0002`, the write should be rejected — don't silently accept it.
- **Assuming the CCCD handle is fixed.** Handles are assigned at build time and shift whenever you add or reorder attributes. Hardcoding a handle in test scripts breaks the moment someone inserts a descriptor. Discover by UUID, not by handle.

## Try It Yourself

1. Connect to any BLE peripheral with `bluetoothctl`, run `list-attributes`, and identify every characteristic's property flags. Pick one with `notify` and manually write `0x01 0x00` to its CCCD — confirm you receive `Characteristic Value Changed` events.
2. On a Zephyr/nRF52 board, add a `BT_GATT_CCC` callback that logs the raw `value` argument. Subscribe with `0x0001`, then `0x0002`, then `0x0000`, and verify your callback fires with the correct bitfield each time.
3. Write a small script that discovers a characteristic by UUID (not handle) and subscribes to it — then reflash the firmware with an extra descriptor inserted before it and confirm your script still works.

## Next Up

Tomorrow: **Notifications vs Indications & Throughput Tuning** — why indications cost you a round-trip per packet, how to size your payloads, and what Data Length Extension (DLE) and 2M PHY actually buy you on a medical sensor streaming at 100 Hz.
