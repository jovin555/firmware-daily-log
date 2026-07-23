---
title: "Day 14: Matter/Thread Support on nRF54LM20 with Zephyr"
date: 2026-07-23
tags: ["til", "rust-zephyr-nrf54", "matter", "thread"]
---

## What I Explored Today

Today I integrated Matter over Thread on the nRF54LM20 using Zephyr's Matter stack, bridging our Rust application logic with the Zigbee/IP-based smart home protocol. The goal was to get a minimal Matter accessory (a light switch) advertising and responding to Thread network commands, all while keeping our Rust bindings clean and safe. I focused on the practical steps: configuring the OpenThread radio driver, enabling the Matter stack in Zephyr, and writing a Rust wrapper for the ZCL (Zigbee Cluster Library) callbacks.

## The Core Concept

Matter (formerly Project CHIP) runs over Thread for low-power mesh networking, using IPv6 over 6LoWPAN. On the nRF54LM20, the built-in 802.15.4 radio (IEEE 802.15.4-2015 compliant) handles the physical layer, while Zephyr's OpenThread integration provides the network stack. The key insight: Matter is not a separate protocol—it's an application-layer framework that sits on top of Thread's UDP transport. When you build a Matter device, you're really building a Thread node that speaks the Matter data model (ZCL clusters) over a secure, commissioned session.

The nRF54LM20's radio peripheral is shared between BLE (for Matter commissioning) and Thread (for operational communication). Zephyr's multiprotocol support handles time-slicing, but you must configure the coexistence carefully—especially the antenna switching and radio priority. The Rust side matters because the ZCL callbacks (attribute reads, commands, and events) are C function pointers that we must wrap in `unsafe` blocks and expose to Rust's async runtime.

## Key Commands / Configuration / Code

### 1. Kconfig for Matter + Thread on nRF54LM20

```kconfig
# prj.conf additions for Matter over Thread
CONFIG_CHIP=y
CONFIG_CHIP_BUILD_DEVICE=y
CONFIG_CHIP_DEVICE_PRODUCT_ID=0x8001
CONFIG_CHIP_DEVICE_VENDOR_ID=0xFFF1

# Thread radio config
CONFIG_OPENTHREAD=y
CONFIG_OPENTHREAD_MTD=y                    # Minimal Thread Device
CONFIG_OPENTHREAD_COPROCESSOR=n           # We're running on-chip
CONFIG_OPENTHREAD_RADIO_SPINEL=n

# nRF54LM20 radio specific
CONFIG_NRF_802154=y
CONFIG_NRF_802154_SRC_IEEE_ADDR_FROM_FACTORY=y
CONFIG_NRF_802154_CSL_ENABLED=y           # Coordinated Sampled Listening for low power

# Multiprotocol (BLE + Thread)
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_CTLR_TX_PWR_PLUS_8=y
CONFIG_MULTIPROTOCOL=y
```

### 2. Rust FFI wrapper for ZCL On/Off cluster callback

```rust
// src/matter/zcl_onoff.rs
use core::ffi::{c_void, c_uint};

// Bind to Zephyr's ZCL callback type
type ZclCallback = unsafe extern "C" fn(
    endpoint: u8,
    cluster: u16,
    command: u8,
    data: *const c_void,
    data_len: u16,
) -> u8;

// The actual C callback we register with the Matter stack
unsafe extern "C" fn onoff_handler(
    endpoint: u8,
    cluster: u16,
    command: u8,
    data: *const c_void,
    data_len: u16,
) -> u8 {
    // Safety: data is guaranteed by Matter to be valid for data_len bytes
    let slice = unsafe { core::slice::from_raw_parts(data as *const u8, data_len as usize) };
    
    // Match on the On/Off cluster commands (0x00 = Off, 0x01 = On, 0x02 = Toggle)
    match command {
        0x00 => {
            // Call into Rust application logic
            crate::app::light_off();
            0x00 // ZCL_SUCCESS
        }
        0x01 => {
            crate::app::light_on();
            0x00
        }
        0x02 => {
            crate::app::light_toggle();
            0x00
        }
        _ => 0x01, // ZCL_UNSUPPORTED_COMMAND
    }
}

// Register with the Matter endpoint
#[no_mangle]
pub extern "C" fn matter_zcl_onoff_init(endpoint: u8) {
    // This would be called from C init code
    // The actual registration uses Zephyr's chip::DeviceLayer::PlatformMgr
    // For brevity, we show the function pointer assignment
    unsafe {
        // Register our callback with the Matter stack
        chip_register_zcl_callback(endpoint, 0x0006, onoff_handler);
    }
}

extern "C" {
    fn chip_register_zcl_callback(endpoint: u8, cluster_id: u16, cb: ZclCallback);
}
```

### 3. Thread network commissioning (from Rust)

```rust
// src/matter/commissioning.rs
use zephyr_sys::raw::*;

pub fn start_thread_network() -> Result<(), i32> {
    // Initialize OpenThread instance
    let instance = unsafe { otInstanceInitSingle() };
    if instance.is_null() {
        return Err(-1);
    }

    // Set Thread network parameters (for development, use well-known credentials)
    let network_name = CString::new("MATTER-DEV")?;
    let ext_pan_id: [u8; 8] = [0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77];
    let network_key: [u8; 16] = [
        0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
        0x88, 0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF,
    ];

    unsafe {
        otThreadSetNetworkName(instance, network_name.as_ptr());
        otThreadSetExtendedPanId(instance, ext_pan_id.as_ptr());
        otThreadSetMasterKey(instance, network_key.as_ptr());
        otThreadSetEnabled(instance, true);
    }

    Ok(())
}
```

## Common Pitfalls & Gotchas

1. **BLE + Thread Coexistence Timeouts**  
   The nRF54LM20's radio cannot transmit BLE and Thread simultaneously. If you don't set `CONFIG_MULTIPROTOCOL_SCHEDULER=y` and configure the time-slice ratio (e.g., 70% Thread, 30% BLE), commissioning will fail silently. I spent two hours debugging why the Matter commissioner couldn't discover the device—turns out the BLE advertising was being starved by Thread polling.

2. **Factory IEEE Address Mismatch**  
   The nRF54LM20's factory-programmed IEEE address (used for Thread EUI64) is stored in FICR. If you override it via `CONFIG_OPENTHREAD_IEEE802154_DEVICE_EUI64`, you must ensure it matches the Matter commissioning certificate. Otherwise, the device will pass Thread authentication but fail Matter's CASE (Certificate Authenticated Session Establishment) handshake.

3. **Rust `unsafe` Callback Lifetime**  
   The ZCL callback function pointer you register with the Matter stack must remain valid for the entire device lifetime. If you pass a Rust closure or a reference to a stack-local variable, the callback will become a dangling pointer after the function returns. Always use `static` or `Box::leak` for the callback state.

## Try It Yourself

1. **Commission a Matter Light Switch**  
   Build the project with the Kconfig above, flash to nRF54LM20, and use the `chip-tool` Python script to commission it over BLE. Run:  
   `chip-tool pairing ble-thread 0x1234 20202021 0x00112233445566778899 0x00112233445566778899aabbccddeeff`  
   Verify the device appears in the Matter fabric.

2. **Toggle the On/Off Cluster from Rust**  
   Modify the `onoff_handler` to log the command via `k_printk` (wrapped in Rust). Add a `light_toggle()` function that toggles a GPIO pin on the nRF54LM20 DK. Use `nrf_gpio_pin_toggle()` from the nRF HAL.

3. **Add a Temperature Measurement Cluster**  
   Extend the Matter endpoint to include a temperature measurement cluster (cluster ID 0x0402). Register a read callback that returns a simulated temperature value (e.g., `22.5°C` encoded as a signed 16-bit integer in 0.01°C units). Use `chip-tool readattribute` to verify.

## Next Up

Tomorrow: **Memory Safety at the Boundary: Rust/C FFI in Zephyr Modules** — we'll dive into the unsafe Rust patterns for wrapping Zephyr's kernel APIs, handling interrupt context, and avoiding undefined behavior when passing slices across the FFI boundary.
