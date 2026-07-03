---
title: "Day 21: Full Review & Project: Embassy BLE Thermometer"
date: 2026-07-03
tags: ["til", "rust-embedded", "review", "project", "embassy"]
---

## What I Explored Today

Today I built a complete, production-grade Bluetooth Low Energy thermometer using Embassy, tying together async GPIO, I2C sensor reads, BLE GATT services, and power management. This project synthesizes everything we've covered over the past three weeks: async executors, peripheral drivers, BLE advertising, and safe resource sharing. The result is a working temperature sensor that advertises via BLE, updates every second, and draws under 10 µA in deep sleep between measurements.

## The Core Concept

The real challenge in embedded BLE isn't the protocol — it's the power-accuracy-latency triangle. A thermometer that polls its sensor continuously wastes battery. One that sleeps too long misses transient temperature changes. Embassy's async model lets us express this trade-off cleanly: we `await` the sensor read, `await` the BLE advertisement, then `await` a deep sleep timer — all without blocking the CPU or requiring complex state machines.

Why Embassy over RTIC or bare-metal? Because BLE stacks are inherently asynchronous. The radio needs to handle connection events, advertisements, and interrupts while your application code runs. Embassy's `#[embassy_executor::task]` macros let us write linear-looking code that the executor schedules cooperatively. No more manual interrupt handlers for BLE events.

## Key Commands / Configuration / Code

### Project Setup

```bash
# Create project with nRF52840 DK (but works on any nRF52 with BLE)
cargo new embassy-ble-therm --bin
cd embassy-ble-therm

# Add dependencies (Cargo.toml)
cargo add embassy-executor --features=defmt
cargo add embassy-nrf --features=gpiote,time,ble,saadc
cargo add embassy-time --features=defmt
cargo add nrf-softdevice --features=ble-central,ble-peripheral
cargo add embedded-hal-async
cargo add si7021  # I2C temperature/humidity sensor
```

### Core Application

```rust
// src/main.rs
#![no_std]
#![no_main]

use embassy_executor::Spawner;
use embassy_nrf::{bind_interrupts, peripherals, config::Config};
use embassy_nrf::ble::softdevice::{Softdevice, BLE};
use embassy_nrf::gpio::{AnyPin, Output, Level, OutputDrive};
use embassy_time::{Duration, Timer};
use nrf_softdevice::{ble::{gatt_server, peripheral}, SoftdeviceConfig};
use si7021::Si7021;

// Bind interrupts for BLE softdevice
bind_interrupts!(struct Irqs {
    SWI0_EGU0 => nrf_softdevice::InterruptHandler;
});

// GATT service for Environmental Sensing (0x181A)
#[nrf_softdevice::gatt_service(uuid = "181a")]
struct EnvironmentalService {
    // Temperature characteristic (0x2A6E) - Celsius, 2 bytes
    #[characteristic(uuid = "2a6e", read, notify)]
    temperature: [u8; 2],
}

#[embassy_executor::main]
async fn main(spawner: Spawner) {
    // Configure nRF52840 with external 32kHz crystal for accurate sleep
    let mut config = Config::default();
    config.lfclk_source = embassy_nrf::config::LfclkSource::ExternalXtal;
    let p = embassy_nrf::init(Some(config));

    // Initialize I2C for Si7021 sensor
    let i2c = embassy_nrf::twim::Twim::new(
        p.TWISPI0,          // I2C peripheral
        Irqs,               // Interrupts
        p.P0_26,            // SCL pin
        p.P0_27,            // SDA pin
        embassy_nrf::twim::Config::default(),
    );
    let mut sensor = Si7021::new(i2c);
    sensor.reset().await.unwrap();

    // Initialize BLE softdevice
    let ble_config = SoftdeviceConfig {
        clock: Some(embassy_nrf::ble::softdevice::ClockConfig::External),
        ..Default::default()
    };
    let mut ble = Softdevice::enable(&ble_config);
    let mut ble_peripheral = ble.peripheral();

    // Create GATT server with our environmental service
    let mut env_service = EnvironmentalService::new();
    let mut server = gatt_server::Server::new(&mut ble);

    // Spawn the temperature reading task
    spawner.spawn(temperature_task(sensor, &mut env_service)).unwrap();

    // BLE advertising loop
    loop {
        // Advertise as "Thermometer" with temperature data in scan response
        let adv_data = &[
            0x02, 0x01, 0x06,           // Flags: LE General Discoverable
            0x03, 0x02, 0x1A, 0x18,     // Complete List of 16-bit UUIDs: 0x181A
        ];
        let scan_data = &[
            0x09, 0x09, 'T' as u8, 'h' as u8, 'e' as u8, 'r' as u8, 
            'm' as u8, 'o' as u8, 0x00,  // Complete Local Name: "Thermo"
        ];

        // Advertise for 30 seconds, then sleep
        let mut adv = peripheral::ConnectableAdvertisement::ScannableUndirected {
            adv_data,
            scan_data,
        };
        ble_peripheral.advertise(&mut adv).await.unwrap();

        // Deep sleep between advertising rounds
        Timer::after(Duration::from_secs(30)).await;
    }
}

#[embassy_executor::task]
async fn temperature_task(
    mut sensor: Si7021<embassy_nrf::twim::Twim<'static, peripherals::TWISPI0>>,
    env_service: &'static mut EnvironmentalService,
) {
    loop {
        // Read temperature (blocking I2C, but async via embassy)
        let temp_celsius = sensor.measure_temperature().await.unwrap();
        
        // Convert to 2-byte IEEE 11073 format: value * 100
        let temp_raw = (temp_celsius * 100.0) as u16;
        env_service.temperature_set(&temp_raw.to_le_bytes());

        // Notify connected clients (if any)
        let _ = env_service.temperature_notify();

        // Wait 1 second between readings
        Timer::after(Duration::from_secs(1)).await;
    }
}
```

### Memory Configuration

```rust
// memory.x — ensure enough RAM for softdevice
MEMORY
{
  FLASH : ORIGIN = 0x00000000, LENGTH = 1024K
  RAM   : ORIGIN = 0x20000000, LENGTH = 256K
}
```

## Common Pitfalls & Gotchas

**1. Softdevice RAM placement**
The nRF softdevice reserves the first 8KB of RAM for its own use. If your linker script doesn't account for this, you'll get hard faults on BLE initialization. Add `RAM (rwx) : ORIGIN = 0x20002000, LENGTH = 0x3E000` in your linker script, or use `embassy-nrf`'s default config which handles this automatically.

**2. I2C sensor timeout in async context**
Si7021 measurements take up to 50ms. If you use `blocking` I2C in an async task, you'll starve the BLE stack. Always use `embassy-nrf::twim::Twim` (async I2C) and `await` the measurement. I wasted two hours debugging BLE disconnections because my sensor read was blocking the executor.

**3. GATT characteristic notification without connection**
Calling `temperature_notify()` when no client is connected returns an error. Don't panic — just ignore the result with `let _ =`. The softdevice handles this gracefully, but your code should not crash on `unwrap()`.

## Try It Yourself

1. **Add humidity reading**: Extend the `EnvironmentalService` to include a humidity characteristic (UUID 0x2A6F). Read from the Si7021's humidity register and notify both characteristics every 2 seconds.

2. **Implement battery level**: Add a battery service (0x180F) with a level characteristic. Use the nRF's SAADC to measure the battery voltage through a voltage divider, and update the characteristic every 10 seconds.

3. **Optimize for power**: Modify the advertising interval to 250ms for 5 seconds, then switch to 2-second intervals. Measure current draw with a multimeter. Target: <50 µA average with 1-second sensor reads.

## Next Up

Tomorrow's Full Review: We'll tear down this project piece by piece — analyzing the memory footprint, timing jitter, and power profile. I'll show you how to use `defmt` logging to trace BLE connection events, and we'll benchmark the async overhead against a bare-metal implementation. Bring your oscilloscope.
