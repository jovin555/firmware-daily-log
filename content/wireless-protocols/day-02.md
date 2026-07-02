---
title: "Day 02: BLE Fundamentals: GAP Roles, Advertising & Connections"
date: 2026-07-02
tags: ["til", "wireless-protocols", "ble", "gap"]
---

## What I Explored Today

Today I dug into the Generic Access Profile (GAP) — the layer that controls how BLE devices discover each other, advertise their presence, and establish connections. GAP defines the roles devices play (Broadcaster, Observer, Peripheral, Central) and the advertising/scanning procedures that make BLE's connection model work. I focused on the practical mechanics: advertising PDUs, scan request/response flows, connection parameter negotiation, and how to configure these in real firmware using the Zephyr RTOS BLE stack.

## The Core Concept

BLE isn't a continuous broadcast protocol like classic Bluetooth. It's built around a **connection-oriented** model with a **discovery phase** that uses advertising. Why? Power. A device can advertise for a few milliseconds, then sleep for 100ms or more. If a Central wants to connect, it sends a connection request during that tiny advertising window. No connection means the Peripheral goes back to sleep.

GAP splits the world into four roles:
- **Broadcaster**: Sends advertising packets, never connects (e.g., a beacon)
- **Observer**: Listens for advertisements, never connects (e.g., a scanner)
- **Peripheral**: Advertises, accepts connections (e.g., a sensor)
- **Central**: Scans, initiates connections (e.g., a phone)

The magic is in the **advertising interval** and **scan window**. A Peripheral advertising every 100ms with a 3ms advertising event consumes ~3% duty cycle. A Central scanning with a 30ms window every 100ms catches that advertisement reliably. This asymmetric power budget is why BLE sensors can run for years on a coin cell while the phone drains faster.

Connection parameters (connection interval, slave latency, supervision timeout) are negotiated after the connection request. The Peripheral requests parameters; the Central accepts or rejects. Getting this wrong causes disconnections or excessive power draw.

## Key Commands / Configuration / Code

Here's a minimal Zephyr BLE Peripheral setup that configures advertising and handles a connection:

```c
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gap.h>

/* Advertising data: just a name and appearance */
static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, "MySensor", 8),
};

/* Scan response data: additional info */
static const struct bt_data sd[] = {
    BT_DATA_BYTES(BT_DATA_UUID16_SOME, 0x0A, 0x18), /* Battery Service */
};

/* Connection callback */
static void connected(struct bt_conn *conn, uint8_t err) {
    if (err) {
        printk("Connection failed (err %u)\n", err);
        return;
    }
    printk("Connected!\n");
    /* Request 50ms connection interval, 0 slave latency, 4s timeout */
    struct bt_le_conn_param param = {
        .interval_min = 40,   /* 40 * 1.25ms = 50ms */
        .interval_max = 40,
        .latency = 0,
        .timeout = 400,       /* 400 * 10ms = 4s */
    };
    bt_conn_le_param_update(conn, &param);
}

static void disconnected(struct bt_conn *conn, uint8_t reason) {
    printk("Disconnected (reason %u)\n", reason);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
};

void main(void) {
    int err;

    err = bt_enable(NULL);
    if (err) {
        printk("Bluetooth init failed (err %d)\n", err);
        return;
    }

    /* Start advertising: connectable, general discoverable */
    err = bt_le_adv_start(BT_LE_ADV_CONN, ad, ARRAY_SIZE(ad),
                          sd, ARRAY_SIZE(sd));
    if (err) {
        printk("Advertising failed to start (err %d)\n", err);
        return;
    }

    printk("Advertising as 'MySensor'...\n");
    /* Sleep forever; callbacks handle the rest */
    k_sleep(K_FOREVER);
}
```

Key details:
- `BT_LE_ADV_CONN` makes the device connectable. Use `BT_LE_ADV_NCONN` for non-connectable beacons.
- Connection interval is in units of 1.25ms. A range of 7.5ms (min) to 4s (max) is allowed.
- Slave latency allows the Peripheral to skip connection events to save power. Latency=3 means it can miss up to 3 consecutive events.

To configure advertising on a Nordic nRF52840 DK using the command line (nRF Connect or similar):

```
# Set advertising interval to 100ms (0x00A0 in 0.625ms units)
bt gatt-server advertise interval 160
# Start connectable advertising
bt gatt-server advertise on
```

## Common Pitfalls & Gotchas

1. **Advertising interval units are 0.625ms, not 1ms.**  
   A common mistake: setting `interval = 100` thinking it's 100ms. It's actually 62.5ms. Always multiply by 1.6 to convert from ms to units, or use the `BT_GAP_ADV_FAST_INTERVAL_*` macros.

2. **Connection parameter update rejection.**  
   The Central (phone) often rejects aggressive parameter requests. If your sensor requests a 7.5ms interval, the phone may disconnect. Start with 50-100ms and negotiate down only if needed. Check `bt_conn_le_param_update()` return value.

3. **Advertising data length limits.**  
   A single advertising PDU is limited to 31 bytes of data (including flags and UUIDs). Scan response gives another 31 bytes. If you need more, use extended advertising (BLE 5.0) or put data in the GATT server. I've seen firmware crash because the advertising data struct exceeded 31 bytes.

## Try It Yourself

1. **Modify the advertising interval** in the Zephyr example above. Set it to 200ms (320 in units of 0.625ms) and measure the current draw with a power profiler. Compare to 20ms advertising. Note the trade-off between discoverability latency and power.

2. **Build a non-connectable broadcaster** that sends a custom 16-byte payload (e.g., temperature reading) in the advertising data. Use an Observer on a second board to parse and print the data. This is the foundation for beacon applications.

3. **Experiment with slave latency.** In the `connected()` callback, request a connection with latency=4 and a 100ms interval. Use a logic analyzer or sniffer to see how many connection events the Peripheral skips. What happens if the sensor has data to send during a skipped event?

## Next Up

Tomorrow: **BLE GATT: Services, Characteristics & Attribute Protocol**. We'll move up the stack to the Generic Attribute Profile — how data is organized into services (like Battery Service 0x180F), how characteristics expose readable/writable values, and how the Attribute Protocol (ATT) handles read/write/notify operations. We'll write a GATT service from scratch and test it with a phone app.
