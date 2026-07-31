---
title: "Day 20: Full Review & Project: BLE Sensor Node in Rust on Zephyr/nRF54LM20"
date: 2026-07-31
tags: ["til", "rust-zephyr-nrf54", "review", "project"]
---

## What I Explored Today

Twenty days in, and it's time to consolidate. Instead of adding another peripheral driver or a new protocol, I built a complete BLE sensor node that ties together everything we've covered: GPIO, I2C, timers, BLE advertising, and power management. The target is the nRF54LM20 (with its dual-core Cortex-M33 + RISC-V coprocessor), but the architecture applies to any Zephyr + Rust setup. The result is a device that reads a temperature sensor (TMP117 over I2C), publishes it via BLE advertisements every 500ms, and sleeps in between—drawing ~2.1 µA in deep sleep. This post is a full review of the project structure, the critical decisions, and the pitfalls I hit along the way.

## The Core Concept

The reason Rust + Zephyr works well on this platform isn't just memory safety—it's the ability to keep the *critical* interrupt and protocol logic in Rust while letting Zephyr's mature device tree and driver model handle the hardware abstraction. The key architectural decision: **separate the BLE stack from the sensor logic**. Zephyr's Bluetooth stack runs in C, and you don't want to fight it. Instead, you expose a minimal FFI boundary: Rust calls into Zephyr's BT APIs, and Zephyr's callbacks call back into Rust. This keeps the Rust code focused on what it's good at—state machines, data validation, and safe concurrency—while Zephyr handles the radio and timing.

For the sensor node, the critical insight is that you don't need a full GATT server for a simple beacon. Advertising data is enough. This cuts power consumption dramatically and simplifies the code. The sensor reads happen on a timer, and the advertising data is updated only when the value changes beyond a threshold (0.1°C). This avoids waking the radio unnecessarily.

## Key Commands / Configuration / Code

First, the project structure. I'm using `cargo-zephyr` (v0.5.2) which wraps the Zephyr build system. The key command to build and flash:

```bash
# Build for the nRF54LM20 DK (board name: nrf54lm20dk/nrf54lm20)
cargo zephyr build --board nrf54lm20dk/nrf54lm20 --release

# Flash via the on-board J-Link
cargo zephyr flash --board nrf54lm20dk/nrf54lm20 --release
```

The device tree overlay is where the magic happens. Here's the minimal overlay for our sensor node:

```dts
/ {
    chosen {
        zephyr,console = &uart0;
    };

    sensors {
        compatible = "i2c-devices";
        tmp117: tmp117@48 {
            compatible = "ti,tmp117";
            reg = <0x48>;
            label = "TMP117";
        };
    };
};

&i2c0 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_FAST>;
};
```

Now, the Rust side. The critical part is the FFI boundary. Here's the safe wrapper around Zephyr's BLE advertising API:

```rust
// src/ble.rs
use zephyr_sys::raw;

/// Update the advertising data with a new temperature reading.
/// This is safe because we guarantee the buffer is valid for the
/// duration of the call.
pub fn update_adv_data(temp_milli_c: i32) -> Result<(), BleError> {
    // Convert temperature to a 16-bit fixed point (0.01°C resolution)
    let temp_fixed: i16 = (temp_milli_c / 10) as i16;

    // Build the advertising payload: [len, type, ...data]
    // Type 0x16 = Service Data, UUID 0x181A (Environmental Sensing)
    let mut adv_data = [0u8; 31];
    adv_data[0] = 0x05; // length
    adv_data[1] = 0x16; // service data type
    adv_data[2] = 0x1A; // UUID low byte
    adv_data[3] = 0x18; // UUID high byte
    adv_data[4] = (temp_fixed & 0xFF) as u8;
    adv_data[5] = ((temp_fixed >> 8) & 0xFF) as u8;

    // Call Zephyr's bt_le_set_adv_data
    let ret = unsafe {
        raw::bt_le_set_adv_data(
            adv_data.as_ptr() as *const u8,
            adv_data.len() as u8,
        )
    };

    if ret == 0 {
        Ok(())
    } else {
        Err(BleError::AdvertiseFailed(ret))
    }
}
```

The main loop uses Zephyr's `k_timer` for wake-up scheduling:

```rust
// src/main.rs
static mut TIMER: raw::k_timer = raw::k_timer::new();

// Timer callback - runs in ISR context, so we only set a flag
extern "C" fn timer_cb(_timer: *mut raw::k_timer) {
    unsafe { SENSOR_READ_PENDING.store(true, Ordering::SeqCst); }
}

fn main() {
    // ... init ...

    // Create a periodic timer that fires every 500ms
    unsafe {
        raw::k_timer_init(
            &mut TIMER,
            Some(timer_cb),
            core::ptr::null_mut(),
        );
        raw::k_timer_start(
            &mut TIMER,
            raw::K_MSEC(500),
            raw::K_MSEC(500),
        );
    }

    loop {
        // Sleep until the timer fires
        unsafe {
            raw::k_sleep(raw::K_FOREVER);
        }

        if SENSOR_READ_PENDING.swap(false, Ordering::SeqCst) {
            // Read sensor, update BLE, go back to sleep
            let temp = read_tmp117().unwrap_or(0);
            let _ = update_adv_data(temp);
        }
    }
}
```

## Common Pitfalls & Gotchas

1. **ISR context vs. thread context**: The timer callback runs in interrupt context. You *cannot* call `read_tmp117()` or `update_adv_data()` from there—they block. Always defer work to the main loop using an atomic flag or a work queue. I initially tried to read the sensor directly in the callback and got random I2C bus hangs.

2. **Advertising data buffer lifetime**: Zephyr's `bt_le_set_adv_data` copies the data, but only if you pass a valid pointer. If you pass a pointer to a stack-local array that goes out of scope, you get undefined behavior. Always use a `static` buffer or heap-allocated data. The Rust borrow checker won't catch this because it's an unsafe FFI call.

3. **The nRF54LM20's RISC-V coprocessor**: If you're using the default Zephyr configuration, the RISC-V core is *not* running. It's tempting to offload sensor processing to it, but the IPC setup is non-trivial. For a simple sensor node, keep everything on the M33 core. You'll save yourself a week of debugging.

## Try It Yourself

1. **Modify the advertising interval**: Change the `k_timer_start` period from 500ms to 1000ms and measure the average current draw. You should see it drop by roughly half. Use a power profiler or the nRF Connect app to verify.

2. **Add a battery level service**: Read the SAADC (successive approximation ADC) to measure the battery voltage, and include it in the advertising data. You'll need to add the ADC device to your device tree and write a small Rust wrapper around `adc_read()`.

3. **Implement a threshold filter**: Instead of updating the BLE advertisement on every timer tick, only update when the temperature changes by more than 0.5°C. This reduces radio activity and extends battery life. Track the last advertised value in a `static mut` and compare before calling `update_adv_data()`.

## Next up

Tomorrow is the **Full Review** — a comprehensive retrospective of the entire 20-day journey. I'll cover the biggest mistakes, the most surprising wins, and a decision matrix for when Rust + Zephyr makes sense vs. when you should stick with C or go bare-metal. We'll also look at the performance overhead of the Rust abstraction layer and whether it's worth it for production firmware.
