---
title: "Day 08: GPIO, SPI & I2C with embedded-hal Traits"
date: 2026-06-22
tags: ["til", "rust-embedded", "gpio", "spi", "i2c"]
---

## What I Explored Today

Today I dug into the `embedded-hal` trait system for GPIO, SPI, and I2C. The goal was to understand how Rust's HAL abstraction layer lets me write peripheral drivers that work across STM32, nRF, and ESP32 without changing a single line of application code. I wired up an STM32L4 to an MCP23017 I2C GPIO expander and an SPI-based ILI9341 display, using only generic `embedded-hal` traits.

## The Core Concept

The `embedded-hal` crate defines a set of traits that abstract over hardware peripherals. Instead of calling `stm32l4xx_hal::gpio::Pin::set_high()`, you write code against `embedded_hal::digital::OutputPin`. The same code then compiles for any MCU that implements those traits.

Why this matters: In production, you often swap MCU families mid-project due to supply chain or power constraints. With `embedded-hal`, your driver code is portable. The HAL implementation for each chip handles the register-level details; you just call `.set_high()` or `.read()`.

The SPI and I2C traits work the same way. `embedded_hal::spi::SpiBus` gives you `read()`, `write()`, and `transfer()`. `embedded_hal::i2c::I2c` gives you `read()`, `write()`, and `write_read()`. Your driver takes a generic type parameter bounded by these traits.

## Key Commands / Configuration / Code

Here's the pattern for a generic GPIO output driver:

```rust
// Cargo.toml dependency
// embedded-hal = "1.0.0"

use embedded_hal::digital::OutputPin;

struct Led<P: OutputPin> {
    pin: P,
}

impl<P: OutputPin> Led<P> {
    fn new(pin: P) -> Self {
        Self { pin }
    }

    fn on(&mut self) {
        self.pin.set_high().unwrap();
    }

    fn off(&mut self) {
        self.pin.set_low().unwrap();
    }
}
```

Now for an I2C sensor driver (e.g., BME280):

```rust
use embedded_hal::i2c::I2c;

pub struct Bme280<I2C> {
    i2c: I2C,
    addr: u8,
}

impl<I2C: I2c> Bme280<I2C> {
    pub fn new(i2c: I2C, address: u8) -> Self {
        Self { i2c, addr: address }
    }

    pub fn read_temperature(&mut self) -> Result<f32, I2C::Error> {
        let mut buf = [0u8; 3];
        // Write register address, then read 3 bytes
        self.i2c.write_read(self.addr, &[0xFA], &mut buf)?;
        // Convert raw ADC value to temperature (simplified)
        let raw = ((buf[0] as u32) << 12) | ((buf[1] as u32) << 4) | ((buf[2] as u32) >> 4);
        Ok(raw as f32 * 0.01) // placeholder calibration
    }
}
```

SPI example — writing to an ILI9341 display:

```rust
use embedded_hal::spi::SpiBus;
use embedded_hal::digital::OutputPin;

struct Ili9341<SPI, DC, CS>
where
    SPI: SpiBus<u8>,
    DC: OutputPin,
    CS: OutputPin,
{
    spi: SPI,
    dc: DC,
    cs: CS,
}

impl<SPI, DC, CS> Ili9341<SPI, DC, CS>
where
    SPI: SpiBus<u8>,
    DC: OutputPin,
    CS: OutputPin,
{
    pub fn write_command(&mut self, cmd: u8) {
        self.dc.set_low().unwrap();   // command mode
        self.cs.set_low().unwrap();   // select chip
        self.spi.write(&[cmd]).unwrap();
        self.cs.set_high().unwrap();  // deselect
    }

    pub fn write_data(&mut self, data: &[u8]) {
        self.dc.set_high().unwrap();  // data mode
        self.cs.set_low().unwrap();
        self.spi.write(data).unwrap();
        self.cs.set_high().unwrap();
    }
}
```

To use this on an STM32L4:

```rust
use stm32l4xx_hal::{pac, prelude::*, spi::Spi, gpio::GpioExt};

let dp = pac::Peripherals::take().unwrap();
let mut rcc = dp.RCC.constrain();
let mut gpioa = dp.GPIOA.split(&mut rcc);

let sck = gpioa.pa5.into_alternate();
let miso = gpioa.pa6.into_alternate();
let mosi = gpioa.pa7.into_alternate();

let spi = Spi::new(dp.SPI1, (sck, miso, mosi), 8.mhz(), &mut rcc);
let dc = gpioa.pa0.into_push_pull_output();
let cs = gpioa.pa1.into_push_pull_output();

let mut display = Ili9341::new(spi, dc, cs);
display.write_command(0x11); // Sleep out
```

## Common Pitfalls & Gotchas

1. **Trait bound explosion with `SpiBus` vs `SpiDevice`**: `SpiBus` assumes you control the CS pin externally. If your driver manages CS internally, use `SpiDevice` instead. Mixing them up causes confusing lifetime errors. Always check which trait your HAL implements.

2. **Error type propagation**: The `I2c` trait has an associated `Error` type. If you write a driver that returns `Result<(), I2C::Error>`, you can't easily combine it with a different error type from another driver. Use `Infallible` for GPIO (which never errors) or define a custom error enum that wraps both.

3. **Pin state at initialization**: Many HALs leave pins in high-impedance input mode after `split()`. If you call `set_high()` on an `OutputPin` before configuring the alternate function, you'll get a panic or undefined behavior. Always configure pin mode explicitly before using it in a peripheral.

## Try It Yourself

1. **Port a driver**: Take the `Bme280` struct above and make it work with an nRF52840 using `nrf52840-hal`. You only need to change the HAL import and pin configuration — the driver code stays identical.

2. **Add error handling**: Modify the `Ili9341` SPI driver to return `Result` types instead of unwrapping. Use a custom `DisplayError` enum that wraps `SpiBus::Error` and `OutputPin::Error`.

3. **Build a generic scanner**: Write a function that takes any `I2c` implementation and scans all 127 possible addresses, printing which ones ACK. Test it on both an STM32 and an ESP32-C3.

## Next Up

Tomorrow we tackle **Interrupt Handlers in Rust: cortex-m & RTIC**. We'll move from polling to event-driven code, setting up NVIC priorities, writing safe interrupt service routines, and using RTIC's hardware tasks to eliminate data races at compile time.
