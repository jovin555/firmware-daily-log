---
title: "Day 19: Implementing a BLE Peripheral in Zephyr / nRF Connect SDK"
date: 2026-10-29
tags: ["til", "ble-medical", "zephyr", "peripheral"]
---

# Day 19: Implementing a BLE Peripheral in Zephyr / nRF Connect SDK

## What I Explored Today

Today I moved from the "hello world" of BLE on Zephyr to a realistic peripheral that a medical device would actually ship: a custom GATT service exposing a heart-rate-like measurement characteristic with notifications, plus a battery service. I worked through the nRF Connect SDK (NCS) v2.6.x toolchain, the `bt_gatt_service_static` vs. dynamic registration tradeoff, and the subtle ordering rules around advertising, connection callbacks, and CCC descriptor handling. The goal was to understand not just *how* to call the Zephyr Bluetooth APIs, but *why* the stack is structured the way it is — because that structure is what keeps you out of trouble when a central subscribes, disconnects, and reconnects in the middle of a clinical measurement session.

## The Core Concept

Zephyr's Bluetooth Host is built around a **callback-driven, attribute-table model**. Unlike some vendor SDKs where you imperatively push data to a peer, Zephyr asks you to declare your GATT database up front as an array of `struct bt_gatt_attr`, then register it with `bt_gatt_service_register()`. The stack owns the attribute handles; you never hardcode them. Instead, you look them up via the attribute pointers you defined, or you use `BT_GATT_SERVICE_DEFINE` macros that give you a handle to the service object.

The reason this matters for medical firmware is **lifecycle correctness**. A peripheral's real job is to respond to *events* — a central enabling notifications via the CCC descriptor, a connection being established, a PHY update, a disconnect — and to keep its state machine consistent across those events. If you treat BLE as a series of function calls rather than a state machine reacting to callbacks, you'll ship a device that leaks subscriptions, sends notifications to a disconnected link, or fails to re-advertise after a central walks away. The attribute-table model forces you to think about the database as the source of truth and the callbacks as the transitions.

A second core idea: **notifications are gated by the CCC descriptor, not by your code**. You can call `bt_gatt_notify()` all day, but if the central hasn't written `0x0001` to the CCC, the stack silently drops it (returns `-ENOTCONN` or succeeds without transmitting, depending on state). Your firmware must track subscription state itself if it wants to avoid wasted work — e.g., don't sample the sensor at 100 Hz if nobody's listening.

## Key Commands / Configuration / Code

**Project config (`prj.conf`)** — the minimum for a connectable peripheral with a custom 128-bit service:

```conf
# prj.conf
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_DEVICE_NAME="MedSensor"
CONFIG_BT_DEVICE_APPEARANCE=0          # 0 = Unknown; use 833 for Generic Sensor
CONFIG_BT_MAX_CONN=1                   # medical peripherals rarely need more
CONFIG_BT_MAX_PAIRED=1
CONFIG_BT_GATT_DYNAMIC_DB=y            # needed if you register services at runtime
CONFIG_BT_SETTINGS=y                   # persist bonds across reboots
CONFIG_BT_ATT_PREPARE_COUNT=2          # long writes for config blobs
CONFIG_LOG=y
CONFIG_BT_DEBUG_LOG=y
```

**Service definition** — a static 128-bit service with one notify characteristic and a CCC:

```c
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>

/* 128-bit UUIDs — generate once, keep stable across firmware versions */
#define BT_UUID_MED_SVC_VAL \
    BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef0)
#define BT_UUID_MED_MEAS_VAL \
    BT_UUID_128_ENCODE(0x12345678, 0x1234, 0x5678, 0x1234, 0x56789abcdef1)

static struct bt_uuid_128 med_svc_uuid  = BT_UUID_INIT_128(BT_UUID_MED_SVC_VAL);
static struct bt_uuid_128 med_meas_uuid = BT_UUID_INIT_128(BT_UUID_MED_MEAS_VAL);

static uint16_t meas_value;   /* little-endian on the wire */
static bool     notify_enabled;

/* CCC write callback — this is where subscription state lives */
static void meas_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    notify_enabled = (value == BT_GATT_CCC_NOTIFY);
    printk("Notifications %s\n", notify_enabled ? "enabled" : "disabled");
}

/* Read callback for the measurement characteristic */
static ssize_t read_meas(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                         void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset,
                             &meas_value, sizeof(meas_value));
}

BT_GATT_SERVICE_DEFINE(med_svc,
    BT_GATT_PRIMARY_SERVICE(&med_svc_uuid),
    BT_GATT_CHARACTERISTIC(&med_meas_uuid.uuid,
        BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ,
        read_meas, NULL, &meas_value),
    BT_GATT_CCC(meas_ccc_changed,
        BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
);
```

**Advertising and connection callbacks** — the state machine:

```c
static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME,
            sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static const struct bt_data sd[] = {
    BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_MED_SVC_VAL),
};

static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err) { printk("Connection failed (err %u)\n", err); return; }
    printk("Connected\n");
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    printk("Disconnected (reason %u)\n", reason);
    notify_enabled = false;                 /* central's CCC is gone */
    int rc = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad),
                             sd, ARRAY_SIZE(sd));
    if (rc) { printk("Re-advertise failed (%d)\n", rc); }
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected    = connected,
    .disconnected = disconnected,
};
```

**Sending a notification** — note the guard:

```c
int send_measurement(uint16_t value)
{
    if (!notify_enabled) return -EAGAIN;    /* nobody subscribed */
    meas_value = value;
    return bt_gatt_notify(NULL, &med_svc.attrs[1], &meas_value,
                          sizeof(meas_value));
}
```

Build and flash with NCS:

```bash
west build -b nrf52840dk/nrf52840 -- -DCONFIG_BT_DEVICE_NAME='"MedSensor"'
west flash
```

## Common Pitfalls & Gotchas

1. **Re-advertising after disconnect is your job.** The stack does *not* restart advertising automatically. If you forget `bt_le_adv_start()` in the `disconnected` callback, your device looks dead to every central after the first connection. Worse, if you call it from the wrong context (e.g., inside a GATT write callback), you can get `-EALREADY` or a race with the stack's own teardown. Do it in `disconnected`.

2. **`notify_enabled` must be reset on disconnect, not just on CCC write.** The CCC value lives in the peer's bond, not in your RAM. On reconnect, the stack restores the CCC from settings *before* your `connected` callback fires — so if you naively reset `notify_enabled = false` in `connected`, you'll suppress notifications the central legitimately re-subscribed to. Reset it in `disconnected` only, and let the CCC callback re-arm it on reconnect.

3. **Attribute index arithmetic is fragile.** `&med_svc.attrs[1]` assumes the characteristic value is at index 1. If you insert a `BT_GATT_CHARACTERISTIC` before it, the index shifts and you'll notify the wrong attribute (or crash). Prefer `bt_gatt_notify_uuid()` with the characteristic UUID, or capture the attribute pointer via a `BT_GATT_SERVICE_DEFINE` accessor pattern. For medical firmware where a wrong notification could mean a missed alarm, use the UUID form.

## Try It Yourself

1. **Add a Battery Service** using `BT_GATT_SERVICE_DEFINE` with the standard `BT_UUID_BAS` and a read-only `BT_GATT_CHRC_READ` characteristic. Verify with `nRF Connect for Mobile` that both services appear and the battery level reads correctly.

2. **Instrument the CCC callback** to log the exact `value` written (0x0000, 0x0001, 0x0002) and confirm the behavior when a central writes `0x0002` (indicate) to a notify-only characteristic — the stack should reject it with an ATT error. Capture the error code.

3. **Break it deliberately:** remove the `bt_le_adv_start()` call from `disconnected`, connect with a phone, then disconnect. Confirm the device stops advertising, then add it back and verify re-advertising works. This is the single most common field bug in BLE peripherals.

## Next Up

Tomorrow: **Implementing Pairing, Bonding & Secured Characteristics in Zephyr** — we'll wire up `BT_GATT_PERM_READ_ENCRYPT`, configure LE Secure Connections with `CONFIG_BT_SMP_SC_ONLY`, handle the `auth_info` callback for passkey entry, and persist bonds via `CONFIG_BT_SETTINGS` so a paired monitor reconnects without re-pairing after a battery swap.
