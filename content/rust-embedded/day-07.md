---
title: "Day 07: Embedded HAL: The Hardware Abstraction Layer Traits"
date: 2026-06-19
tags: ["til", "rust-embedded", "embedded-hal", "traits", "abstraction"]
---

## What I Explored Today

Today I dug into the `embedded-hal` crate—the trait-based abstraction layer that makes Rust embedded code portable across microcontrollers. Instead of writing GPIO toggle code that only works on an STM32, then rewriting it for an nRF52840, `embedded-hal` defines traits like `OutputPin`, `InputPin`, `SpiBus`, and `I2c` that any HAL implementation can implement. I spent the morning understanding how these traits work, why they exist, and how to write driver code that doesn't care which chip it runs on.

## The Core Concept

The embedded ecosystem has a fragmentation problem. Every microcontroller vendor has its own peripheral registers, memory maps, and initialization sequences. Without abstraction, every driver is tied to a specific chip. The `embedded-hal` crate solves this by defining a set of *traits* that represent common hardware operations—setting a pin high, reading an ADC value, writing to an I2C bus.

The key insight: **traits decouple the *what* from the *how***. A temperature sensor driver only needs to know "I can read bytes over I2C"—it doesn't care if that I2C bus is on an STM32, an ESP32, or a Raspberry Pi Pico. The driver is written against the trait, and the user provides the concrete implementation when they instantiate the driver.

This is the same pattern as `std::io::Read` and `std::io::Write` in standard Rust. You write code that works with any reader or writer, and the concrete type is injected at runtime (or compile time, thanks to generics).

## Key Commands / Configuration / Code

### Adding embedded-hal to your project

```toml
# Cargo.toml
[dependencies]
embedded-hal = "1.0.0"
# Pick one chip-specific HAL:
stm32f4xx-hal = { version = "0.18", features = ["stm32f407"] }
# or
nrf52840-hal = "0.17"
```

### Writing a portable LED driver

Here's a driver that works with *any* microcontroller that implements `OutputPin`:

```rust
use embedded_hal::digital::OutputPin;
use core::convert::Infallible;

pub struct Led<P: OutputPin> {
    pin: P,
}

impl<P: OutputPin> Led<P> {
    pub fn new(pin: P) -> Self {
        Self { pin }
    }

    pub fn on(&mut self) -> Result<(), P::Error> {
        self.pin.set_high()
    }

    pub fn off(&mut self) -> Result<(), P::Error> {
        self.pin.set_low()
    }

    pub fn toggle(&mut self) -> Result<(), P::Error> {
        // Read current state and invert it
        if self.pin.is_set_high()? {
            self.pin.set_low()
        } else {
            self.pin.set_high()
        }
    }
}
```

### Using the driver on two different MCUs

```rust
// On STM32F4
use stm32f4xx_hal::{pac, prelude::*, gpio::GpioExt};

let dp = pac::Peripherals::take().unwrap();
let gpioa = dp.GPIOA.split();
let pa5 = gpioa.pa5.into_push_pull_output();
let mut led = Led::new(pa5);
led.on().unwrap();

// On nRF52840 — same driver, different pin
use nrf52840_hal::{pac, prelude::*, gpio::GpioExt};

let dp = pac::Peripherals::take().unwrap();
let port0 = dp.P0.split();
let p0_13 = port0.p0_13.into_push_pull_output();
let mut led = Led::new(p0_13);
led.on().unwrap();
```

### Writing a generic I2C sensor driver

```rust
use embedded_hal::i2c::I2c;

pub struct TemperatureSensor<I2C> {
    i2c: I2C,
    address: u8,
}

impl<I2C: I2c> TemperatureSensor<I2C> {
    pub fn new(i2c: I2C, address: u8) -> Self {
        Self { i2c, address }
    }

    pub fn read_temperature(&mut self) -> Result<f32, I2C::Error> {
        let mut buf = [0u8; 2];
        // Write register address, then read 2 bytes
        self.i2c.write_read(self.address, &[0x00], &mut buf)?;
        let raw = u16::from_be_bytes(buf);
        // Convert to Celsius (example: TMP102 sensor)
        Ok(raw as f32 * 0.0625)
    }
}
```

## Common Pitfalls & Gotchas

### 1. Error types are generic and can be `Infallible`

Many digital pins have `Error = Infallible` (the error can never happen). But if you write `led.on().unwrap()` and later switch to a pin that can actually fail (like an I2C expander), your code will panic. **Always propagate errors with `?`** in library code, and only `unwrap()` in application code where you know the error type.

### 2. `OutputPin::set_high()` takes `&mut self`

The `OutputPin` trait requires `&mut self` because setting a pin changes hardware state. This means you can't have two references to the same pin. If you need to share a pin (e.g., a shared bus), you'll need a `RefCell` or `Mutex` wrapper. This is intentional—it prevents race conditions at compile time.

### 3. Not all HALs implement all traits

The `embedded-hal` trait set is large (digital, analog, PWM, SPI, I2C, etc.). A HAL for a low-end microcontroller might only implement `OutputPin` and `InputPin`. Always check the HAL's documentation for which traits are implemented. Trying to use an unimplemented trait will give you a confusing "trait bound not satisfied" error.

## Try It Yourself

1. **Port your existing blink code**: Take any LED blinking example you wrote earlier this week. Refactor it to use the `Led<P>` generic driver above. Verify it still compiles and works on your board.

2. **Write a button debouncer**: Create a generic `Button<I: InputPin>` struct that debounces input using a simple state machine. Implement `is_pressed()` and `is_released()` methods that return `Result<bool, I::Error>`.

3. **Combine with a delay**: Add a `DelayMs` parameter to your `Led` struct (from `embedded_hal::delay::DelayNs`). Write a `blink(&mut self, delay: &mut impl DelayNs, period_ms: u32)` method that toggles the LED at the given period.

## Next Up

Tomorrow we'll get hands-on with the three most common embedded protocols: **GPIO, SPI, and I2C**. We'll write drivers that use `embedded-hal` traits directly, explore the differences between blocking and DMA transfers, and build a multi-sensor data logger that works on any board. Bring your oscilloscope—we're going to look at real waveforms.
