---
title: "Day 11: Power Management: nRF54LM20 Low Power Modes with Zephyr PM"
date: 2026-07-20
tags: ["til", "rust-zephyr-nrf54", "power-management", "zephyr-pm"]
---

## What I Explored Today

Today I dug into Zephyr's Power Management (PM) subsystem on the nRF54LM20, specifically how to transition between active, idle, and deep sleep states from Rust. The nRF54LM20 is a dual-core beast with a dedicated VPR (Vector Processing Radio) domain, but its real superpower is sub-µA sleep currents. I wired up a button interrupt to wake from System OFF, measured current draw with a Nordic PPK2, and confirmed we can hit ~0.6 µA in the deepest retention state. The key takeaway: Zephyr PM gives you a clean API, but the nRF54LM20's hardware constraints (like which RAM banks stay alive) require careful configuration.

## The Core Concept

Power management on the nRF54LM20 isn't just about calling `pm_state_force()`. The chip has three main sleep domains: System ON (CPU idle, peripherals clock-gated), System OFF (full power-down, wake via GPIO or RTC), and a new "Deep Sleep" mode that retains the 128 KB low-power RAM. Zephyr's PM subsystem abstracts these into states: PM_STATE_ACTIVE, PM_STATE_STANDBY, and PM_STATE_SUSPEND_TO_RAM. The critical insight is that the nRF54LM20's VPR domain (the BLE/802.15.4 radio coprocessor) has its own power rail — you can shut down the main Cortex-M33 entirely while the VPR handles radio traffic. This is where Rust's ownership model shines: we can enforce at compile time that the PM handle is only accessible when the main core is awake.

## Key Commands / Configuration / Code

### 1. Kconfig for PM (prj.conf)
```kconfig
# Enable Zephyr Power Management
CONFIG_PM=y
CONFIG_PM_DEVICE=y

# nRF54LM20-specific: keep LP RAM in retention
CONFIG_SOC_NRF54L20_RETENTION_RAM=y
CONFIG_SOC_NRF54L20_RETENTION_RAM_SIZE=0x20000  # 128 KB

# Wake sources
CONFIG_GPIO_NRFX=y
CONFIG_GPIO_WAKEUP=y
```

### 2. Rust PM State Machine (src/power.rs)
```rust
use zephyr::pm::{self, PowerState, WakeSource};
use zephyr::gpio::{Pin, Direction, Edge};
use core::sync::atomic::{AtomicBool, Ordering};

static WAKE_FLAG: AtomicBool = AtomicBool::new(false);

/// Configure GPIO wake-up on button press (P0.13)
pub fn init_wake_button() -> Pin {
    let btn = Pin::new(13);
    btn.configure(
        Direction::In,
        Edge::Rising,
        || { WAKE_FLAG.store(true, Ordering::SeqCst); }
    );
    btn.enable_wake_from_sleep();
    btn
}

/// Enter System OFF with LP RAM retention
pub fn enter_deep_sleep(btn: &Pin) -> ! {
    // Notify Zephyr PM we're going to SUSPEND_TO_RAM
    pm::state_force(PowerState::SuspendToRam);

    // nRF54LM20: must set RETENTION bit before WFI
    unsafe {
        core::ptr::write_volatile(
            0x5000_6000 as *mut u32,  // NRF_POWER->RETENTION
            0x0000_0001               // RETENTION_RAM0
        );
    }

    // Wait for interrupt (WFI) — button will wake us
    pm::cpu_sleep();

    // We never reach here in System OFF, but if we do:
    loop {
        cortex_m::asm::wfi();
    }
}

/// Check if we woke from deep sleep
pub fn was_wake_from_deep_sleep() -> bool {
    WAKE_FLAG.swap(false, Ordering::SeqCst)
}
```

### 3. Main loop with PM transitions (src/main.rs)
```rust
#[no_mangle]
pub extern "C" fn main() {
    let btn = power::init_wake_button();

    // Check reset reason — did we wake from System OFF?
    if power::was_wake_from_deep_sleep() {
        // Re-initialize peripherals that lost power
        init_uart();
        init_sensors();
        log::info!("Woke from deep sleep, re-initialized");
    }

    loop {
        // Normal operation: sample sensor, send data
        do_work();

        // After 10 seconds of idle, enter deep sleep
        if idle_time_elapsed() > 10_000 {
            log::info!("Entering deep sleep...");
            power::enter_deep_sleep(&btn);
        }

        // Light sleep between work cycles
        pm::cpu_sleep();
    }
}
```

### 4. Measuring current with PPK2
```bash
# Build with PM enabled
west build -b nrf54l20dk/nrf54l20/cpuapp -d build_pm

# Flash and connect PPK2
nrfjprog --program build_pm/zephyr/zephyr.hex --sectorerase
# PPK2: set VOUT=3.0V, measure average over 10 seconds
# Expected: ~0.6 µA in SUSPEND_TO_RAM, ~2.1 mA active
```

## Common Pitfalls & Gotchas

1. **RAM retention is bank-specific** — The nRF54LM20 has 256 KB of RAM, but only the first 128 KB (LP RAM) retains data in SUSPEND_TO_RAM. If your Rust globals or stack spill into the upper 128 KB, they'll be garbage on wake. Use the linker script to place critical data in `RETENTION_RAM` section:
   ```ld
   SECTIONS {
       .retention (NOLOAD) : {
           *(.retention*)
       } > RAM_LP
   }
   ```

2. **GPIO wake configuration must happen before sleep** — If you call `pm_state_force()` before enabling the wake pin's SENSE signal, the nRF54LM20 will never wake. Always call `btn.enable_wake_from_sleep()` *before* the sleep transition. I lost an hour to this — the PPK2 showed 0.6 µA but the board was bricked until reset.

3. **VPR domain doesn't auto-wake the main core** — If you're using the BLE radio coprocessor (VPR), it can stay awake while the main core sleeps. But the VPR won't trigger a wake-up unless you configure an inter-processor interrupt (IPC). This is a common trap: you think BLE events will wake the app, but they don't unless you explicitly set up the VPR-to-M33 mailbox.

## Try It Yourself

1. **Measure baseline sleep current** — Build the example above, flash to your nRF54L20 DK, and use a PPK2 (or multimeter in µA range) to measure current in SUSPEND_TO_RAM. Compare with the datasheet's 0.6 µA typical. Try disabling RETENTION_RAM and see the drop to ~0.3 µA.

2. **Add an RTC wake-up** — Replace the button wake with an RTC alarm. Configure the RTC to fire every 60 seconds, wake from SUSPEND_TO_RAM, log a timestamp, then re-enter sleep. Use `pm_state_force()` with `PM_STATE_STANDBY` for a faster wake (3 µs vs 130 µs).

3. **Profile active vs sleep ratio** — Add a GPIO toggle on a scope pin before and after `pm::cpu_sleep()`. Calculate your duty cycle: if you're awake 1 ms every 1000 ms at 2.1 mA, your average current is ~2.1 µA. Optimize by batching work into shorter bursts.

## Next Up

Tomorrow: **BLE on nRF54LM20: SoftDevice Controller & Rust Bindings** — we'll initialize the VPR radio coprocessor, bind the SoftDevice Controller's HCI interface to Rust, and send our first BLE advertisement from the nRF54LM20's dual-core architecture.
