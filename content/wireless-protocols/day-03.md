---
title: "Day 03: BLE GATT: Services, Characteristics & Attribute Protocol"
date: 2026-07-03
tags: ["til", "wireless-protocols", "gatt", "att"]
---

## What I Explored Today

Today I dug into the Generic Attribute Profile (GATT) and its underlying Attribute Protocol (ATT), the layer that makes BLE useful beyond simple beaconing. While the Link Layer handles who talks when, GATT defines *what* they talk about. I spent the morning tracing attribute handles on a Nordic nRF52840 DK, reading through the Bluetooth Core Spec Vol 3, Part G, and mapping out how a heart rate sensor exposes its data. The key insight: GATT is a strict client-server model, and every piece of data lives in a hierarchical tree of services, characteristics, and descriptors.

## The Core Concept

GATT exists because BLE needed a standardized way for devices to expose and consume data without custom application protocols. Instead of inventing your own packet formats, you define a *service* (like "Heart Rate" with UUID 0x180D), populate it with *characteristics* (like "Heart Rate Measurement" with UUID 0x2A37), and optionally add *descriptors* (like "Client Characteristic Configuration" for notifications).

The Attribute Protocol (ATT) is the transport. Every attribute—whether it's a service declaration, characteristic value, or descriptor—has a 16-bit handle, a UUID type, and a set of permissions. The GATT layer builds on ATT by defining how these attributes are grouped into services and how characteristics interact (read, write, notify, indicate). When you call `bt_gatt_notify()` in Zephyr, you're actually writing to the CCCD (Client Characteristic Configuration Descriptor) handle, which tells the client "expect a notification on this handle."

The real engineering value: once you understand the attribute hierarchy, you can debug any BLE device with a sniffer. You'll see ATT Read By Group Type requests (0x10) discovering services, followed by Read By Type (0x08) for characteristics, and finally Read/Write requests for values. Every BLE interaction is just ATT operations on handles.

## Key Commands / Configuration / Code

Here's a minimal GATT service definition using Zephyr RTOS (the most common BLE stack in production):

```c
/* Heart Rate Service - Bluetooth Core Spec 4.0, Vol 3, Part C, Section 12.1 */
#define BT_UUID_HRS_VAL              0x180D
#define BT_UUID_HRS_MEASUREMENT_VAL  0x2A37
#define BT_UUID_HRS_BODY_SENSOR_VAL  0x2A38

static struct bt_gatt_attr hrs_attrs[] = {
    /* Service Declaration - handle auto-assigned by stack */
    BT_GATT_PRIMARY_SERVICE(BT_UUID_DECLARE_16(BT_UUID_HRS_VAL)),

    /* Characteristic: Heart Rate Measurement (notifiable) */
    BT_GATT_CHARACTERISTIC(BT_UUID_DECLARE_16(BT_UUID_HRS_MEASUREMENT_VAL),
                           BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_NONE,  /* no read/write from client */
                           NULL, NULL, NULL),

    /* Characteristic Value - stored in RAM, updated by application */
    BT_GATT_CCC(&hrs_ccc_cfg,
                bt_gatt_cfg_changed_ccc),
};

/* Notification callback - called when client enables/disables notifications */
static void hrs_ccc_cfg_changed(const struct bt_gatt_attr *attr,
                                uint16_t value)
{
    /* value == 0x0001 means notifications enabled */
    /* value == 0x0002 means indications enabled */
    /* value == 0x0000 means disabled */
    if (value == BT_GATT_CCC_NOTIFY) {
        printk("Client subscribed to HR notifications\n");
    }
}

/* Send heart rate measurement (8-bit value, sensor contact supported) */
void send_heart_rate(uint8_t hr_value)
{
    /* Format: Flags byte (0x00 = 8-bit, no sensor contact) + HR value */
    uint8_t hrm_data[2] = { 0x00, hr_value };
    
    bt_gatt_notify(NULL, &hrs_attrs[3], hrm_data, sizeof(hrm_data));
}
```

On the client side (e.g., a phone or another BLE device), discovering this service looks like:

```c
/* After connection, discover services */
static void discover_hrs(struct bt_conn *conn)
{
    struct bt_uuid_16 uuid = BT_UUID_INIT_16(BT_UUID_HRS_VAL);
    
    /* This triggers ATT Read By Group Type (0x10) */
    bt_gatt_discover(conn, NULL, &uuid.uuid,
                     discovery_complete_cb, NULL);
}

/* Discovery callback - receives attribute handles */
static void discovery_complete_cb(struct bt_conn *conn,
                                  struct bt_gatt_attr *attrs,
                                  size_t count)
{
    /* attrs[0] = service handle (0x0010 typical)
     * attrs[1] = characteristic declaration (0x0011)
     * attrs[2] = CCCD handle (0x0012)
     * attrs[3] = value handle (0x0013)
     */
    struct bt_gatt_subscribe_params params = {
        .value = BT_GATT_CCC_NOTIFY,
        .value_handle = attrs[3].handle,  /* HR measurement value */
        .ccc_handle = attrs[2].handle,    /* CCCD */
    };
    
    bt_gatt_subscribe(conn, &params, notification_handler, NULL);
}
```

## Common Pitfalls & Gotchas

1. **Handle ordering matters for CCCD**: The Client Characteristic Configuration Descriptor *must* be the first descriptor after the characteristic value declaration. If you place it elsewhere, some BLE stacks (especially on iOS) will reject your service. I've seen this cause "service not found" errors that took hours to debug. Always declare CCCD immediately after the characteristic value attribute.

2. **MTU negotiation is not automatic**: The default ATT MTU is 23 bytes (3 bytes header + 20 bytes payload). If you need to send larger characteristic values, you must explicitly request an MTU exchange after connection. In Zephyr, call `bt_gatt_exchange_mtu(conn, NULL)` in the connected callback. Without this, any write longer than 20 bytes will silently fail or truncate.

3. **Notification vs. Indication reliability**: Notifications (ATT Handle Value Notification, 0x1B) are fire-and-forget—no acknowledgment. Indications (ATT Handle Value Indication, 0x1D) require a confirmation from the client. If you need guaranteed delivery (e.g., critical sensor data), use indications. But beware: indications are slower because of the round-trip, and only one indication can be pending at a time. Many engineers default to notifications and lose data under congestion.

## Try It Yourself

1. **Sniff a GATT discovery**: Use a BLE sniffer (nRF Sniffer or Ellisys) and capture the ATT packets during service discovery. Identify the Read By Group Type request and response, then trace how the client discovers characteristics. Note the handle numbers and UUIDs.

2. **Modify the CCCD callback**: In the Zephyr example above, add logic to blink an LED when a client subscribes to notifications. This gives you a physical indicator of GATT subscription state—invaluable for debugging.

3. **Implement a custom service**: Create a simple "Device Information" service (UUID 0x180A) with a "Manufacturer Name String" characteristic (UUID 0x2A29). Expose your board's name as a readable string. Verify it appears in nRF Connect or LightBlue on your phone.

## Next Up

Tomorrow: **BLE Power Profiling: Connection Intervals & Duty Cycling**. We'll measure real current draw on an nRF52840 with different connection intervals (7.5ms vs 400ms), calculate average power consumption, and explore how the GATT notification rate directly impacts battery life. Bring your oscilloscope or current probe.
