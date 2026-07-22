---
title: "Day 13: Zephyr Bluetooth Host Stack from Rust: GATT Services"
date: 2026-07-22
tags: ["til", "rust-zephyr-nrf54", "bluetooth", "gatt"]
---

## What I Explored Today

Today I integrated a custom GATT service into the Zephyr Bluetooth Host stack, but from the Rust side using the `zephyr-sys` bindings. The nRF54LM20's Bluetooth controller is a beast—dual-mode Bluetooth 5.4 with LE Audio support—but the real challenge is wiring up GATT characteristics, notifications, and CCCDs (Client Characteristic Configuration Descriptors) through Zephyr's C API while keeping the service logic in Rust. I got a battery service (BAS) running with a notifying characteristic, and I'll walk through the exact Kconfig, device tree, and Rust FFI glue needed.

## The Core Concept

Why not just use the Zephyr Bluetooth sample in C? Because we want Rust's safety guarantees—no dangling pointers in GATT callbacks, no buffer overflows on notification payloads—while still leveraging Zephyr's battle-tested Bluetooth host stack. The nRF54LM20's Bluetooth controller is a hardware peripheral; the host stack (HCI, L2CAP, ATT, GATT) runs on the Cortex-M33. Zephyr exposes this via `bt_gatt_service_register()` and `bt_gatt_notify()`. From Rust, we need to:

1. Define a GATT service structure in C-compatible memory (using `#[repr(C)]`).
2. Register it via FFI to Zephyr's GATT subsystem.
3. Handle write requests (e.g., CCCD writes) through a Rust callback.
4. Send notifications from Rust tasks without data races.

The key insight: Zephyr's GATT API is callback-heavy and expects static or `k_malloc`-allocated structures. Rust's ownership model fights this, so we use `static mut` with `unsafe` blocks, carefully scoped, and a global `Mutex`-protected state for the notification buffer.

## Key Commands / Configuration / Code

### Kconfig (prj.conf)
Enable Bluetooth and GATT service support:
```kconfig
# Enable Bluetooth Host stack
CONFIG_BT=y
CONFIG_BT_LE=y
CONFIG_BT_GATT_CLIENT=y
CONFIG_BT_GATT_DYNAMIC_DB=y
CONFIG_BT_MAX_CONN=1
CONFIG_BT_MAX_PAIRED=1

# Enable GATT notifications
CONFIG_BT_GATT_NOTIFY_MULTIPLE=y
CONFIG_BT_GATT_CCC_MAX=4

# Required for Rust FFI
CONFIG_BT_GATT_CACHING=y
CONFIG_BT_DEVICE_NAME="nRF54-Rust-GATT"
```

### Device Tree (nrf54lm20_xxaa.dts)
No changes needed—the Bluetooth controller is already enabled in the SoC dtsi. But ensure the UART for HCI is configured:
```dts
&uart0 {
    status = "okay";
    current-speed = <1000000>;
    hci-uart {
        compatible = "zephyr,bt-hci-uart";
        hw-flow-control;
    };
};
```

### Rust GATT Service (src/gatt_battery.rs)
This defines a Battery Service with a notifying characteristic:
```rust
use core::sync::atomic::{AtomicU8, Ordering};
use zephyr_sys::raw;

// Battery level (0-100), shared between ISR and main
static BATTERY_LEVEL: AtomicU8 = AtomicU8::new(100);

// GATT service UUID: 0x180F (Battery Service)
const BT_UUID_BAS_VAL: raw::bt_uuid_16 = raw::bt_uuid_16 {
    uuid: raw::bt_uuid { type_: raw::BT_UUID_TYPE_16 },
    val: 0x180F,
};

// Characteristic UUID: 0x2A19 (Battery Level)
const BT_UUID_BATTERY_LEVEL_VAL: raw::bt_uuid_16 = raw::bt_uuid_16 {
    uuid: raw::bt_uuid { type_: raw::BT_UUID_TYPE_16 },
    val: 0x2A19,
};

// CCCD UUID: 0x2902
const BT_UUID_CCC_VAL: raw::bt_uuid_16 = raw::bt_uuid_16 {
    uuid: raw::bt_uuid { type_: raw::BT_UUID_TYPE_16 },
    val: 0x2902,
};

// GATT attribute structs must be static and #[repr(C)]
#[repr(C)]
struct BatteryService {
    svc: raw::bt_gatt_service_static,
    batt_level_chrc: raw::bt_gatt_chrc,
    batt_level_val: raw::bt_gatt_attr,
    ccc: raw::bt_gatt_attr,
}

static mut BATTERY_SERVICE: BatteryService = BatteryService {
    svc: raw::bt_gatt_service_static {
        // Will be initialized at runtime
        ..raw::bt_gatt_service_static::zeroed()
    },
    batt_level_chrc: raw::bt_gatt_chrc {
        uuid: &BT_UUID_BATTERY_LEVEL_VAL as *const _ as *const raw::bt_uuid,
        value_handle: 0,
        properties: raw::BT_GATT_CHRC_READ | raw::BT_GATT_CHRC_NOTIFY,
    },
    batt_level_val: raw::bt_gatt_attr {
        uuid: &BT_UUID_BATTERY_LEVEL_VAL as *const _ as *const raw::bt_uuid,
        read: Some(batt_level_read),
        write: None,
        user_data: core::ptr::null_mut(),
        ..raw::bt_gatt_attr::zeroed()
    },
    ccc: raw::bt_gatt_attr {
        uuid: &BT_UUID_CCC_VAL as *const _ as *const raw::bt_uuid,
        read: None,
        write: Some(ccc_write),
        user_data: core::ptr::null_mut(),
        ..raw::bt_gatt_attr::zeroed()
    },
};

// Read callback: return current battery level
unsafe extern "C" fn batt_level_read(
    conn: *mut raw::bt_conn,
    attr: *const raw::bt_gatt_attr,
    buf: *mut raw::bt_gatt_attr,
    len: u16,
    offset: u16,
) -> u8 {
    let level = BATTERY_LEVEL.load(Ordering::Relaxed);
    // Write single byte to buffer
    if offset == 0 && len >= 1 {
        core::ptr::write(buf as *mut u8, level);
        return 1; // bytes written
    }
    0
}

// CCCD write callback: enable/disable notifications
unsafe extern "C" fn ccc_write(
    conn: *mut raw::bt_conn,
    attr: *const raw::bt_gatt_attr,
    buf: *const u8,
    len: u16,
    offset: u16,
) -> u8 {
    if len < 2 {
        return 0;
    }
    let ccc_val = core::ptr::read_unaligned(buf as *const u16);
    // ccc_val == 0x0001 means notifications enabled
    // We could store this per-connection in a static array
    // For simplicity, just print
    if ccc_val == 0x0001 {
        // Notifications enabled
    }
    2 // bytes consumed
}

// Initialize and register the service
pub fn init_gatt_battery() {
    unsafe {
        // Build the service attribute list
        let attrs = [
            &BATTERY_SERVICE.batt_level_chrc as *const _ as *const raw::bt_gatt_attr,
            &BATTERY_SERVICE.batt_level_val as *const _ as *const raw::bt_gatt_attr,
            &BATTERY_SERVICE.ccc as *const _ as *const raw::bt_gatt_attr,
        ];
        BATTERY_SERVICE.svc = raw::bt_gatt_service_static {
            attrs: attrs.as_ptr(),
            attr_count: attrs.len() as u8,
        };
        raw::bt_gatt_service_register(
            &mut BATTERY_SERVICE.svc as *mut _ as *mut raw::bt_gatt_service,
        );
    }
}

// Call this from a timer or task to update battery level
pub fn update_battery_level(level: u8) {
    BATTERY_LEVEL.store(level, Ordering::Relaxed);
    // Notify all connected peers
    unsafe {
        // Get first connected connection (simplified)
        let conn = raw::bt_conn_lookup_state_le(raw::BT_ID_DEFAULT, &raw::BT_CONN_CONNECTED);
        if !conn.is_null() {
            raw::bt_gatt_notify(
                conn,
                &BATTERY_SERVICE.batt_level_val as *const _ as *const raw::bt_gatt_attr,
                &BATTERY_LEVEL as *const _ as *const core::ffi::c_void,
                1,
            );
            raw::bt_conn_unref(conn);
        }
    }
}
```

### Main.rs Integration
```rust
mod gatt_battery;

fn main() -> ! {
    // Initialize Bluetooth
    unsafe {
        raw::bt_enable(raw::bt_ready_cb_t::None);
    }
    gatt_battery::init_gatt_battery();

    // Start advertising
    let ad = raw::bt_data {
        type_: raw::BT_DATA_NAME_COMPLETE,
        data_len: 15,
        data: b"nRF54-Rust-GATT\0" as *const u8,
    };
    unsafe {
        raw::bt_le_adv_start(
            raw::BT_LE_ADV_CONN,
            &ad as *const raw::bt_data,
            1,
            core::ptr::null(),
            0,
        );
    }

    // Simulate battery level changes
    loop {
        gatt_battery::update_battery_level(85);
        unsafe { raw::k_sleep(raw::K_SECONDS(10)); }
    }
}
```

### Build & Flash
```bash
west build -b nrf54lm20_xxaa -d build .
west flash --runner nrfjprog
```

## Common Pitfalls & Gotchas

1. **GATT Service Registration Order**: You must register services *after* `bt_enable()` completes. If you register before, Zephyr's GATT database isn't initialized, and `bt_gatt_service_register()` returns `-EAGAIN`. In Rust, we call `init_gatt_battery()` after `bt_enable()` in main.

2. **Static Lifetime of GATT Attributes**: Zephyr stores pointers to your attribute structures—they must live forever. Using `static mut` is correct, but beware of Rust's aliasing rules. Never take a mutable reference to `BATTERY_SERVICE` after registration; only access through raw pointers in callbacks.

3. **Notification Buffer Ownership**: `bt_gatt_notify()` does not copy the data buffer—it must remain valid until the callback `bt_gatt_notify_cb` fires (or for synchronous sends, until the function returns). Our `AtomicU8` is fine for single-byte values, but for larger payloads, use a `static mut` buffer protected by a mutex or use `k_malloc` with `k_free` in the callback.

## Try It Yourself

1. **Add a second characteristic** (e.g., Battery Power State 0x2A1A) with read and write permissions. Register it in the same service and handle writes from Rust to toggle an LED.

2. **Implement per-connection CCCD tracking**: Instead of ignoring the CCCD write, store the notification state in a `static mut [u16; CONFIG_BT_MAX_CONN]` array indexed by connection handle. Only notify connections that have enabled notifications.

3. **Stress-test notifications**: Set up a periodic timer (using `k_timer` from Zephyr) that calls `update_battery_level()` every 100ms. Monitor with a BLE sniffer (e.g., nRF Sniffer) to verify notification timing and no dropped packets.

## Next Up

Tomorrow, I'm diving into **Matter/Thread support on nRF54LM20 with Zephyr**—specifically, how to initialize the OpenThread stack from Rust, configure the radio for Thread 1.3, and bridge a Matter endpoint to a custom GATT service. The nRF54LM20 has a dedicated RISC-V coprocessor for the 802.15.4 radio; I'll show you the device tree bindings and Rust FFI to talk to it.
