---
title: "Day 19: BLE GATT: Custom Service & Characteristic"
date: 2026-07-01
tags: ["til", "zephyr", "ble", "gatt"]
---

## What I Explored Today

Today I implemented a custom Bluetooth Low Energy GATT service with a writable characteristic on the nRF52840 DK using Zephyr RTOS. The goal was to move beyond the standard Device Information Service and Heart Rate Service examples and build something truly application-specific: a service that exposes a 32-bit counter that a peer can read, increment, and reset. This required registering a custom UUID, defining a service and characteristic in the GATT database, and handling both read and write callbacks. I learned that while Zephyr’s `bt_gatt_service_register()` API is straightforward, the subtlety lies in correctly managing attribute metadata, CCCD (Client Characteristic Configuration Descriptor) for notifications, and ensuring the BLE stack is initialized before service registration.

## The Core Concept

GATT (Generic Attribute Profile) organizes data into services and characteristics. Each service groups related functionality (e.g., a "Counter Service"), and each characteristic exposes a value with defined properties (read, write, notify) and permissions (open, authenticated, encrypted). In Zephyr, you define these using the `BT_GATT_SERVICE_DEFINE()` macro, which statically allocates the attribute table at build time. The macro takes a list of attribute entries: primary service declaration, characteristic declaration, value declaration, and optional CCCD.

Why not just use a simple global variable? Because BLE requires attribute handles, security levels, and notification mechanisms. The GATT layer abstracts these, but you must provide callbacks for every operation the peer may attempt. The key insight is that the characteristic value is *not* just a variable—it’s a GATT attribute that the stack manages. You provide a buffer (`BT_GATT_ATTRIBUTE`) and a set of callbacks (`BT_GATT_CHRC`). When a peer writes, your callback validates the data and updates the buffer. When a peer reads, your callback can return the current value or perform side effects. For notifications, you must also include a CCCD attribute so the peer can enable them.

Zephyr’s `bt_gatt_notify()` function sends a notification to a connected peer, but only if the peer has enabled notifications via the CCCD. This is a common source of bugs: forgetting to check the CCCD state before calling notify.

## Key Commands / Configuration / Code

First, define a custom 128-bit UUID. Zephyr provides `BT_UUID_DECLARE_128()` for this. I used a base UUID with a 16-bit short form for simplicity, but the full 128-bit is required for custom services.

```c
/* Custom service UUID: 0000C001-0000-1000-8000-00805F9B34FB */
#define BT_UUID_CUSTOM_SERVICE_VAL \
	BT_UUID_128_ENCODE(0x0000C001, 0x0000, 0x1000, 0x8000, 0x00805F9B34FB)

struct bt_uuid_128 custom_service_uuid = BT_UUID_INIT_128(BT_UUID_CUSTOM_SERVICE_VAL);

/* Custom characteristic UUID: 0000C101-0000-1000-8000-00805F9B34FB */
#define BT_UUID_CUSTOM_COUNTER_VAL \
	BT_UUID_128_ENCODE(0x0000C101, 0x0000, 0x1000, 0x8000, 0x00805F9B34FB)

struct bt_uuid_128 custom_counter_uuid = BT_UUID_INIT_128(BT_UUID_CUSTOM_COUNTER_VAL);
```

Now define the service and characteristic using the macro. Note the CCCD for notifications.

```c
static uint32_t counter_value = 0;

static ssize_t read_counter(struct bt_conn *conn,
			    const struct bt_gatt_attr *attr,
			    void *buf, uint16_t len, uint16_t offset)
{
	/* Return the 4-byte counter value in little-endian */
	return bt_gatt_attr_read(conn, attr, buf, len, offset,
				 &counter_value, sizeof(counter_value));
}

static ssize_t write_counter(struct bt_conn *conn,
			     const struct bt_gatt_attr *attr,
			     const void *buf, uint16_t len,
			     uint16_t offset, uint8_t flags)
{
	uint32_t val;

	if (offset != 0 || len != sizeof(val)) {
		return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
	}

	memcpy(&val, buf, sizeof(val));

	/* Interpret write: 0 = reset, 1 = increment, else set directly */
	if (val == 0) {
		counter_value = 0;
	} else if (val == 1) {
		counter_value++;
	} else {
		counter_value = val;
	}

	printk("Counter updated to %u\n", counter_value);
	return len;
}

BT_GATT_SERVICE_DEFINE(custom_svc,
	BT_GATT_PRIMARY_SERVICE(&custom_service_uuid),
	BT_GATT_CHARACTERISTIC(&custom_counter_uuid.uuid,
			       BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
			       BT_GATT_PERM_READ | BT_GATT_PERM_WRITE,
			       read_counter, write_counter, &counter_value),
	BT_GATT_CCC(NULL, NULL),  /* CCCD for notifications */
);
```

In `main()`, after `bt_enable()`, register the service:

```c
bt_gatt_service_register(&custom_svc);
```

To send a notification when the counter changes (e.g., after a button press):

```c
void notify_counter(struct bt_conn *conn)
{
	/* Only notify if CCCD indicates notifications are enabled */
	if (bt_gatt_is_subscribed(conn, &custom_svc.attrs[2],
				  BT_GATT_CCC_NOTIFY)) {
		bt_gatt_notify(conn, &custom_svc.attrs[1],
			       &counter_value, sizeof(counter_value));
	}
}
```

Build with `west build -b nrf52840dk_nrf52840 -t menuconfig` and ensure `CONFIG_BT=y`, `CONFIG_BT_PERIPHERAL=y`, and `CONFIG_BT_GATT_DYNAMIC_DB=n` (static is simpler for this case).

## Common Pitfalls & Gotchas

1. **UUID byte order**: Zephyr’s `BT_UUID_128_ENCODE()` expects the UUID in *big-endian* byte order (the standard human-readable format). If you reverse the bytes, the service won’t match the peer’s expectation. Always double-check with a BLE sniffer or `bt_uuid_to_str()`.

2. **CCCD subscription check**: Calling `bt_gatt_notify()` without checking `bt_gatt_is_subscribed()` will succeed but the peer won’t receive the notification. Worse, the stack may silently drop it. Always guard notifications with the subscription check.

3. **Attribute offset handling**: The `offset` parameter in read/write callbacks is critical for long reads. If you ignore it and always return the full value, the peer may get corrupted data. The helper `bt_gatt_attr_read()` handles offset correctly—use it.

## Try It Yourself

1. **Extend the service**: Add a second characteristic that exposes a string (e.g., device name) with read-only permissions. Use `BT_GATT_CHRC_READ` and a fixed buffer.

2. **Add security**: Change the characteristic permission to `BT_GATT_PERM_READ_ENCRYPT` and `BT_GATT_PERM_WRITE_ENCRYPT`. Pair with a peer and verify that unencrypted reads fail.

3. **Implement a notification loop**: Use a timer to increment the counter every second and notify all connected peers. Handle the case where no peer is connected (skip notify).

## Next Up

Tomorrow, I’m diving into OpenThread: 802.15.4 & Thread Network. We’ll build a Thread node that communicates over a mesh, configure the RCP (Radio Co-Processor) mode, and send sensor data across the network. No BLE, no Wi-Fi—just low-power mesh networking.
