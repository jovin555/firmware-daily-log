---
title: "Day 18: Bluetooth LE: Advertising, Scanning & GATT"
date: 2026-06-30
tags: ["til", "zephyr", "ble", "bluetooth"]
---

## What I Explored Today

Today I wired up the three foundational pillars of Bluetooth Low Energy in Zephyr: **advertising** (broadcasting presence), **scanning** (discovering nearby devices), and **GATT** (Generic Attribute Profile for data exchange). While the Bluetooth stack in Zephyr is rich and layered, getting these three primitives right is the difference between a device that "works" and one that reliably connects and exchanges data. I focused on the `bt_le_adv` and `bt_le_scan` APIs, plus the GATT server initialization flow, using the nRF52840 DK as my target.

## The Core Concept

BLE communication is asymmetric by design. A **peripheral** (like a sensor tag) advertises its presence; a **central** (like a phone or gateway) scans for those advertisements. Once the central initiates a connection, both sides use **GATT** to talk—the peripheral exposes services and characteristics, the central reads/writes them. In Zephyr, you don't need to implement the full Bluetooth spec; the stack abstracts the HCI and link layer. Your job is to configure the advertising data, set up the GATT database, and handle connection events.

Why does this matter? Because misconfigured advertising intervals or scan windows can drain batteries, miss connections, or fail certification. Zephyr gives you fine-grained control—but with that comes responsibility. The stack uses a **static** GATT table (registered at compile time via `BT_GATT_SERVICE_DEFINE`), which is efficient but means you must plan your service structure before flashing.

## Key Commands / Configuration / Code

### 1. Advertising Setup (Peripheral Role)

```c
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gap.h>

/* Advertising parameters: fast advertising with 30ms interval */
static const struct bt_le_adv_param adv_param = {
    .options = BT_LE_ADV_OPT_CONNECTABLE | BT_LE_ADV_OPT_USE_NAME,
    .interval_min = BT_GAP_ADV_FAST_INT_MIN_2,  /* 30ms */
    .interval_max = BT_GAP_ADV_FAST_INT_MAX_2,  /* 60ms */
};

/* Advertising data: include TX power and appearance */
static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA_BYTES(BT_DATA_TX_POWER, 0x08),  /* +8 dBm */
    BT_DATA_BYTES(BT_DATA_GAP_APPEARANCE, 0x00, 0x00),  /* Generic sensor */
};

/* Scan response data: include device name */
static const struct bt_data sd[] = {
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

void start_advertising(void)
{
    int err = bt_le_adv_start(&adv_param, ad, ARRAY_SIZE(ad),
                              sd, ARRAY_SIZE(sd));
    if (err) {
        printk("Advertising failed to start (err %d)\n", err);
    }
}
```

### 2. Scanning Setup (Central Role)

```c
/* Scan parameters: passive scan, 30ms window, 60ms interval */
static const struct bt_le_scan_param scan_param = {
    .type       = BT_LE_SCAN_TYPE_PASSIVE,
    .options    = BT_LE_SCAN_OPT_NONE,
    .interval   = 0x0060,  /* 60ms */
    .window     = 0x0030,  /* 30ms */
};

/* Callback when a device is found */
static void scan_cb(const struct bt_le_scan_recv_info *info,
                    struct net_buf_simple *ad_data)
{
    char addr_str[BT_ADDR_LE_STR_LEN];
    bt_addr_le_to_str(info->addr, addr_str, sizeof(addr_str));
    printk("Device found: %s, RSSI %d\n", addr_str, info->rssi);
}

void start_scanning(void)
{
    int err = bt_le_scan_start(&scan_param, scan_cb);
    if (err) {
        printk("Scanning failed to start (err %d)\n", err);
    }
}
```

### 3. GATT Initialization (Both Roles)

GATT services are defined statically. Here's a minimal battery service:

```c
#include <zephyr/bluetooth/gatt.h>

static uint8_t battery_level = 100;

static ssize_t read_battery(struct bt_conn *conn,
                            const struct bt_gatt_attr *attr,
                            void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset,
                             &battery_level, sizeof(battery_level));
}

BT_GATT_SERVICE_DEFINE(battery_svc,
    BT_GATT_PRIMARY_SERVICE(BT_UUID_BATTERY),
    BT_GATT_CHARACTERISTIC(BT_UUID_BATTERY_LEVEL,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           read_battery, NULL, &battery_level),
    BT_GATT_CCC,  /* Client Characteristic Configuration Descriptor */
);
```

### 4. Kconfig Requirements

```kconfig
# prj.conf
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_CENTRAL=y          # if scanning
CONFIG_BT_GATT_CLIENT=y      # if connecting as central
CONFIG_BT_DEVICE_NAME="Zephyr Sensor"
CONFIG_BT_MAX_CONN=1
```

## Common Pitfalls & Gotchas

1. **Advertising data too large** — The advertising PDU is limited to 31 bytes for the advertising payload and 31 for scan response. If you pack too many manufacturer-specific data fields, the stack silently truncates. Always check `bt_le_adv_start()` return value; if it returns `-EINVAL`, your data exceeds the limit.

2. **Scanning without stopping before connect** — Zephyr's stack does not automatically stop scanning when you initiate a connection. If you call `bt_conn_le_create()` while scanning is active, the scan may interfere with connection establishment. Always stop scanning (`bt_le_scan_stop()`) before calling connect.

3. **GATT CCC not enabled** — If you define a characteristic with `BT_GATT_CHRC_NOTIFY`, you *must* include a `BT_GATT_CCC` descriptor in the same service definition. Without it, the stack will not allow subscriptions, and `bt_gatt_notify()` will silently fail.

## Try It Yourself

1. **Modify advertising interval** — Change `interval_min` and `interval_max` in `adv_param` to `BT_GAP_ADV_SLOW_INT_MIN` (100ms) and observe how discovery latency changes. Use a BLE scanner app on your phone to measure the difference.

2. **Add manufacturer data to scan response** — Extend the `sd[]` array with `BT_DATA_BYTES(BT_DATA_MANUFACTURER_DATA, 0x59, 0x00, 0x01, 0x02)` (Nordic Semiconductor company ID). Verify the data appears in your phone's scanner.

3. **Implement a connection callback** — Register `bt_conn_cb_register()` with callbacks for `connected` and `disconnected`. Print the peer address and connection handle. This is essential for managing multi-connection scenarios.

## Next Up

Tomorrow: **BLE GATT: Custom Service & Characteristic** — we'll move beyond built-in profiles and define our own custom service with a writable characteristic, including proper security permissions and notification handling.
