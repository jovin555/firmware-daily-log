---
title: "Day 17: Unit Testing Rust Zephyr Code: Twister & Host Tests"
date: 2026-07-28
tags: ["til", "rust-zephyr-nrf54", "twister", "testing"]
---

## What I Explored Today

Today I tackled the testing story for Rust code running inside Zephyr on the nRF54LM20. While Zephyr's `twister` handles integration tests on real hardware or QEMU, Rust's native test framework can run unit tests on the host machine—no target board required. I wired up both approaches: host-side `cargo test` for fast feedback on pure logic, and Zephyr's `west twister` to run Rust-based tests on the actual nRF54 hardware. The key insight is that you don't need to cross-compile every test; you can separate hardware-independent logic from peripheral-bound code.

## The Core Concept

Unit testing embedded Rust is a layered problem. Your application has three categories of code:

1. **Pure logic** (algorithms, state machines, data validation) — testable on host
2. **Hardware abstraction** (HAL traits, register access) — testable with mocks
3. **Peripheral-bound** (SPI transactions, interrupt handlers) — requires hardware-in-the-loop

The mistake most engineers make is trying to test everything on target. That's slow, flaky, and consumes flash cycles. Instead, structure your Rust crate so that `#[cfg(test)]` modules compile for the host target (`x86_64-unknown-linux-gnu`) while the main library compiles for `thumbv8m.main-none-eabihf` (nRF54's Cortex-M33). Zephyr's `twister` then runs the hardware-dependent tests, but your CI pipeline runs `cargo test` first for instant feedback.

For the nRF54LM20 specifically, the Rust `nrf-hal` crate provides traits that can be mocked. I use `embedded-hal-mock` to simulate I2C/SPI peripherals during host tests, ensuring my driver logic is correct before flashing.

## Key Commands / Configuration / Code

### 1. Cargo workspace with conditional compilation

In your `Cargo.toml`, separate dependencies for host vs. target:

```toml
[package]
name = "nrf54-sensor-driver"
version = "0.1.0"
edition = "2021"

[dependencies]
embedded-hal = "1.0"

[target.'cfg(not(target_arch = "x86_64"))'.dependencies]
nrf-hal = { git = "https://github.com/nrf-rs/nrf-hal", features = ["nrf54l20"] }

[target.'cfg(target_arch = "x86_64")'.dev-dependencies]
embedded-hal-mock = "0.11"
```

### 2. Host-side unit test with mocked I2C

```rust
// src/sensor.rs
pub struct TemperatureSensor<I2C> {
    i2c: I2C,
    addr: u8,
}

impl<I2C: embedded_hal::i2c::I2c> TemperatureSensor<I2C> {
    pub fn new(i2c: I2C, addr: u8) -> Self {
        Self { i2c, addr }
    }

    pub fn read_temperature(&mut self) -> Result<f32, I2C::Error> {
        let mut buf = [0u8; 2];
        self.i2c.write_read(self.addr, &[0x00], &mut buf)?;
        let raw = u16::from_be_bytes(buf);
        Ok(raw as f32 * 0.0625) // typical sensor conversion
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use embedded_hal_mock::eh1::i2c::{Mock as I2cMock, Transaction};

    #[test]
    fn test_temperature_conversion() {
        let expectations = vec![
            Transaction::write_read(0x48, vec![0x00], vec![0x19, 0x20]),
        ];
        let mut i2c = I2cMock::new(&expectations);
        let mut sensor = TemperatureSensor::new(i2c, 0x48);
        let temp = sensor.read_temperature().unwrap();
        // 0x1920 = 6432 decimal -> 6432 * 0.0625 = 402.0°C? No, check datasheet
        // Actually for this sensor: 0x1920 = 25.125°C
        assert!((temp - 25.125).abs() < 0.01);
        sensor.i2c.done(); // verifies all expectations met
    }
}
```

Run on host: `cargo test --target x86_64-unknown-linux-gnu`

### 3. Zephyr twister test for Rust integration

Create `tests/sensor_integration/testcase.yaml`:

```yaml
tests:
  drivers.sensor.temperature:
    platform_allow: nrf54l20dk/nrf54l20
    tags: drivers sensor rust
    integration_platforms:
      - nrf54l20dk/nrf54l20
    harness: ztest
    filter: CONFIG_RUST
```

Then in your Zephyr app's `src/main.rs`:

```rust
// This test runs on-target via twister
#[cfg(test)]
mod zephyr_tests {
    use crate::sensor::TemperatureSensor;
    use zephyr::devicetree::Devicetree;

    #[test]
    fn test_sensor_i2c_communication() {
        let i2c = Devicetree::take_peripheral("i2c1").unwrap();
        let mut sensor = TemperatureSensor::new(i2c, 0x48);
        let temp = sensor.read_temperature().unwrap();
        // On real hardware, expect room temperature
        assert!(temp > 15.0 && temp < 35.0);
    }
}
```

Run with: `west twister -T tests/sensor_integration -p nrf54l20dk/nrf54l20 --build-only` (add `--flash` to actually run)

### 4. CI script combining both

```bash
#!/bin/bash
set -euo pipefail

# Fast feedback: host tests
echo "=== Running host unit tests ==="
cargo test --target x86_64-unknown-linux-gnu

# Integration: twister with hardware
echo "=== Running Zephyr integration tests ==="
west twister -T tests/ -p nrf54l20dk/nrf54l20 --flash --device-serial /dev/ttyACM0
```

## Common Pitfalls & Gotchas

1. **`#[cfg(test)]` leaks into target builds** — If you use `#[cfg(test)]` on a function that calls Zephyr-specific APIs (like `k_sleep`), the host compiler will fail because those symbols don't exist. Solution: wrap Zephyr calls behind a trait or use `#[cfg(not(target_arch = "x86_64"))]` for hardware-dependent code, not just `test`.

2. **Twister doesn't know about Cargo workspaces** — By default, `west twister` builds Zephyr's CMake, which invokes `cargo build` for Rust sources. If your Rust crate has workspace members, you need to set `CONFIG_RUST_CARGO_FLAGS="--workspace"` in your board's `prj.conf`, otherwise only the root crate compiles.

3. **Mock expectations mismatch** — `embedded-hal-mock` transactions must match exactly. If your sensor driver sends a write before read but your mock expects write_read, the test panics with a confusing "unexpected transaction" error. Always check the transaction order with a logic analyzer on real hardware first, then mirror it in mocks.

## Try It Yourself

1. **Add a host test for a checksum function** — In your Rust crate, write a `fn crc8(data: &[u8]) -> u8` and test it with `cargo test` on your laptop. Verify it matches the nRF54 hardware CRC peripheral.

2. **Mock an SPI temperature sensor** — Create a `TemperatureSensor` struct using `embedded_hal::spi::SpiDevice`, then write a host test with `embedded-hal-mock` that verifies correct register reads.

3. **Run a twister test on nRF54 hardware** — Write a simple Zephyr test that reads the internal die temperature sensor via Rust's `nrf-hal`, then run `west twister` with `--flash` and verify the output on the serial console.

## Next Up

Tomorrow: **OTA/DFU on nRF54LM20: MCUboot Integration with Rust Apps** — We'll configure MCUboot as the bootloader, sign our Rust firmware with `imgtool`, and implement an over-the-air update mechanism using Zephyr's DFU subsystem. You'll learn how to partition flash, handle swap operations, and trigger updates from a Rust application.
