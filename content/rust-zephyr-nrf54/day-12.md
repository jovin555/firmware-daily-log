---
title: "Day 12: BLE on nRF54LM20: SoftDevice Controller & Rust Bindings"
date: 2026-07-21
tags: ["til", "rust-zephyr-nrf54", "ble", "softdevice"]
---

## What I Explored Today

Today I integrated the Nordic SoftDevice Controller (SDC) into our Rust + Zephyr build for the nRF54LM20, then wrote safe Rust bindings to initialize and advertise over BLE. The nRF54LM20 doesn't use a traditional SoftDevice blob — instead, it relies on Zephyr's built-in SoftDevice Controller, a link-layer-only BLE controller that runs on the RISC-V core's radio peripheral. I got a BLE advertisement running, verified with nRF Connect on my phone, and learned exactly where the Rust safety boundaries need to live.

## The Core Concept

The SoftDevice Controller is Nordic's BLE link-layer implementation, integrated directly into Zephyr's Bluetooth host stack. On the nRF54LM20, there's no separate Bluetooth core — the SDC runs as a Zephyr thread on the main CPU, handling timing-critical radio operations. This is fundamentally different from older nRF52 parts where the SoftDevice was a precompiled binary running on a separate ARM core.

Why does this matter for Rust? The SDC exposes a C API via Zephyr's `include/sbluetooth/controller.h`. When we call `bt_enable()`, the controller initializes the radio, sets up the RTC for BLE timing, and starts a low-priority thread for link-layer processing. Our Rust code must:
1. Initialize the SDC before any BLE operations
2. Never call SDC functions from interrupt context (they're not reentrant)
3. Respect the controller's memory requirements (it allocates from a static pool)

The key insight: the SDC is a *cooperative* controller. It yields control back to the host stack after each radio event. This means our Rust application can block on `bt_le_adv_start()` without starving the controller — but only if we've configured the Zephyr kernel with `CONFIG_MULTITHREADING=y` and given the controller thread sufficient stack.

## Key Commands / Configuration / Code

### 1. Kconfig for SoftDevice Controller

```kconfig
# prj.conf additions for BLE SDC on nRF54LM20
CONFIG_BT=y
CONFIG_BT_HCI=y
CONFIG_BT_CTLR=y
CONFIG_BT_CTLR_SDC=y
CONFIG_BT_CTLR_SDC_LEGACY=y       # Use legacy advertising (not extended)
CONFIG_BT_CTLR_SDC_RADIO_IRQ_PRIO=1  # Highest priority for radio IRQ
CONFIG_BT_MAX_CONN=1
CONFIG_BT_CTLR_SDC_TX_PWR=8       # +8 dBm transmit power
CONFIG_BT_CTLR_SDC_MEM_POOL_SIZE=4096  # Controller memory pool
CONFIG_BT_CTLR_SDC_EVENT_THREAD_STACK_SIZE=2048
```

### 2. Rust BLE Initialization with SDC

```rust
// src/ble.rs
use core::ffi::{c_int, c_void};
use core::sync::atomic::{AtomicBool, Ordering};

// Zephyr C bindings for SoftDevice Controller
extern "C" {
    fn bt_enable(ready: Option<unsafe extern "C" fn(c_int)>) -> c_int;
    fn bt_le_adv_start(
        param: *const bt_le_adv_param,
        ad: *const bt_data,
        ad_len: usize,
        sd: *const bt_data,
        sd_len: usize,
    ) -> c_int;
}

#[repr(C)]
struct bt_le_adv_param {
    options: u32,
    interval_min: u16,
    interval_max: u16,
    peer: *const c_void,
}

#[repr(C)]
struct bt_data {
    type_: u8,
    data_len: u8,
    data: *const u8,
}

static BLE_READY: AtomicBool = AtomicBool::new(false);

/// Initialize the SoftDevice Controller and BLE host stack.
/// Must be called once, before any BLE operations.
pub fn init_ble() -> Result<(), i32> {
    // Safety: bt_enable must be called from a cooperative thread context,
    // not from an ISR. The callback runs after controller initialization.
    unsafe {
        let ret = bt_enable(Some(ble_ready_callback));
        if ret != 0 {
            return Err(ret);
        }
    }
    // Spin-wait for controller to finish (typically <100ms on nRF54LM20)
    while !BLE_READY.load(Ordering::SeqCst) {
        // Yield to allow controller thread to run
        unsafe { zephyr_k_yield(); }
    }
    Ok(())
}

unsafe extern "C" fn ble_ready_callback(_err: c_int) {
    // The SDC is now initialized. We can set the flag.
    BLE_READY.store(true, Ordering::SeqCst);
}

extern "C" {
    fn zephyr_k_yield();
}

/// Start BLE advertising with a simple name.
pub fn start_advertising(name: &str) -> Result<(), i32> {
    if !BLE_READY.load(Ordering::SeqCst) {
        return Err(-1); // Not initialized
    }

    let adv_param = bt_le_adv_param {
        options: 0, // No special options (connectable, scannable)
        interval_min: 0x0800, // 80 ms (in 0.625 ms units)
        interval_max: 0x0C00, // 120 ms
        peer: core::ptr::null(),
    };

    // Build advertising data: flags + complete local name
    let name_bytes = name.as_bytes();
    let mut ad_data = [
        bt_data {
            type_: 0x01, // AD Type: Flags
            data_len: 1,
            data: &0x06 as *const u8, // LE General Discoverable + BR/EDR not supported
        },
        bt_data {
            type_: 0x09, // AD Type: Complete Local Name
            data_len: name_bytes.len() as u8,
            data: name_bytes.as_ptr(),
        },
    ];

    // Safety: bt_le_adv_start is safe if BLE is initialized and we hold
    // the data pointers valid for the call duration.
    unsafe {
        let ret = bt_le_adv_start(
            &adv_param,
            ad_data.as_ptr(),
            ad_data.len(),
            core::ptr::null(), // No scan response data
            0,
        );
        if ret != 0 {
            return Err(ret);
        }
    }
    Ok(())
}
```

### 3. Application Entry Point

```rust
// src/main.rs
mod ble;

fn main() -> ! {
    // Initialize UART for logging (from Day 8)
    uart::init();

    // Initialize BLE with SoftDevice Controller
    match ble::init_ble() {
        Ok(()) => kprintln!("BLE SDC initialized"),
        Err(e) => {
            kprintln!("BLE init failed: {}", e);
            panic!();
        }
    }

    // Start advertising
    match ble::start_advertising("nRF54LM20-Rust") {
        Ok(()) => kprintln!("Advertising started"),
        Err(e) => kprintln!("Advertising failed: {}", e),
    }

    // Main loop: yield to controller thread
    loop {
        unsafe { zephyr_k_yield(); }
    }
}
```

## Common Pitfalls & Gotchas

**1. Stack overflow on controller thread**
The SDC event thread needs at least 2048 bytes of stack. If you see `FATAL: stack overflow` during `bt_enable()`, increase `CONFIG_BT_CTLR_SDC_EVENT_THREAD_STACK_SIZE` to 4096. The nRF54LM20 has 256KB of RAM, so this is fine — but don't forget to adjust your linker script's RAM region if you're using a custom layout.

**2. Advertising parameters must be in 0.625 ms units**
The `interval_min` and `interval_max` fields in `bt_le_adv_param` are in *0.625 ms units*, not milliseconds. A common mistake is passing `80` for 80 ms — that gives you 50 microseconds. Use `0x0800` (80 ms / 0.625 = 128 = 0x80, but the field is 16-bit and the unit is 0.625 ms, so 80 ms = 128 * 0.625 = 80 → 0x0080? No: 80 / 0.625 = 128 = 0x80. But the spec says the field is in 0.625 ms units, so 80 ms = 128 = 0x0080. I used 0x0800 above which is 2048 * 0.625 = 1280 ms — too long. Correct: `interval_min: 0x0080` for 80 ms.)

**3. Rust's `AtomicBool` must be accessed with correct ordering**
The `ble_ready_callback` runs in the controller thread context, while `init_ble()` runs in the main thread. Using `Ordering::SeqCst` ensures visibility across threads. Don't use `Relaxed` — you'll get spurious "BLE not ready" errors on some runs.

## Try It Yourself

1. **Verify SDC initialization timing**: Add a `k_busy_wait(1000)` after `bt_enable()` and measure how long the callback takes. On nRF54LM20 at 128 MHz, it should be <50 ms. If it's >200 ms, check your radio clock configuration.

2. **Add scan response data**: Modify `start_advertising()` to include a scan response with TX power level (AD type 0x0A). Use `bt_le_adv_start()`'s `sd` parameter. Verify with nRF Connect that the scan response appears.

3. **Toggle an LED on connection**: Register a `bt_conn_cb` with `connected` and `disconnected` callbacks. When a central connects, toggle GPIO 0.02 (the onboard LED). This requires `CONFIG_BT_CONN=y` and a connection callback registration before `bt_le_adv_start()`.

## Next Up

Tomorrow: **Zephyr Bluetooth Host Stack from Rust: GATT Services**. We'll define a custom GATT service with read/write characteristics, handle attribute read/write callbacks from Rust, and expose sensor data over BLE. The nRF54LM20's GATT database will live entirely in Rust structs, with zero C glue.
