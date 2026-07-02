---
title: "Day 20: Comparing C vs Rust Driver: Safety Wins & Trade-offs"
date: 2026-07-02
tags: ["til", "rust-embedded", "comparison", "c", "rust"]
---

## What I Explored Today

Today I did a side-by-side comparison of a real I²C temperature sensor driver (the TMP102) written in both C and Rust. I wanted to see where the safety claims actually hold up under a microscope—and where Rust forces you to pay a complexity tax. I ported a production C driver I wrote last year to idiomatic Rust using `embedded-hal`, then benchmarked both on an STM32L4. The results confirmed Rust catches memory bugs at compile time that C would only reveal through a logic analyzer or a hard fault, but the trade-offs in compile-time generics and trait overhead are real.

## The Core Concept

The fundamental difference isn't about syntax—it's about *ownership of hardware resources*. In C, every driver function receives a raw pointer to a peripheral struct, and it's your job to ensure no two functions write to the same register simultaneously. The compiler trusts you. In Rust, the `embedded-hal` traits encode ownership at the type level: you can't call `write_register` on an I²C bus that's already been moved into another function. This eliminates an entire class of race conditions and use-after-free bugs that plague C drivers in interrupt-heavy contexts.

But the trade-off is that Rust's type system forces you to think about *who owns the bus* at every call site. In C, you can pass a pointer around freely and just hope nobody else touches it. In Rust, you must explicitly model sharing with `RefCell` or `Mutex` for interrupts, or accept that the bus is consumed by a single code path. This is safer, but it means your driver's API surface is more rigid.

## Key Commands / Configuration / Code

Let's compare a minimal TMP102 read function in both languages.

**C driver (typical for STM32 HAL):**
```c
// C: Manual pointer management, no borrow checking
#include "stm32l4xx_hal.h"

#define TMP102_ADDR 0x48 << 1
#define TMP102_TEMP_REG 0x00

// Returns temperature in centi-Celsius, or -1 on error
int32_t tmp102_read_temp(I2C_HandleTypeDef *hi2c) {
    uint8_t reg = TMP102_TEMP_REG;
    uint8_t buf[2] = {0};
    
    // Must manually check HAL return codes
    if (HAL_I2C_Master_Transmit(hi2c, TMP102_ADDR, &reg, 1, 100) != HAL_OK) {
        return -1;  // Error: no type-safe error handling
    }
    if (HAL_I2C_Master_Receive(hi2c, TMP102_ADDR, buf, 2, 100) != HAL_OK) {
        return -1;
    }
    
    // Raw 12-bit value (left-aligned in 16-bit)
    int16_t raw = ((int16_t)buf[0] << 8) | buf[1];
    raw >>= 4;  // Shift to 12-bit
    return (raw * 100) / 16;  // 0.0625°C per LSB
}
```

**Rust driver (using `embedded-hal`):**
```rust
// Rust: Type-level safety, no raw pointers
use embedded_hal::i2c::{I2c, ErrorType};

const TMP102_ADDR: u8 = 0x48;
const TMP102_TEMP_REG: u8 = 0x00;

// Error is generic over the I2C bus error type
pub fn read_temperature<I2C>(i2c: &mut I2C) -> Result<i16, I2C::Error>
where
    I2C: I2c,  // Trait bound ensures correct bus type
{
    let mut buf = [0u8; 2];
    
    // Compile-time guarantee: i2c is not aliased elsewhere
    i2c.write_read(TMP102_ADDR, &[TMP102_TEMP_REG], &mut buf)?;
    
    let raw = i16::from_be_bytes(buf);
    let raw_12bit = raw >> 4;
    // No integer overflow: wrapping arithmetic is explicit
    Ok(raw_12bit.wrapping_mul(100) / 16)
}
```

**Key differences:**
- Rust's `Result` type forces the caller to handle errors—no silent -1 returns.
- The `I2c` trait bound means you can pass any I²C implementation (hardware, bit-banged, mock) without changing the driver.
- Rust's `wrapping_mul` makes overflow behavior explicit; C's implicit wrapping is undefined behavior for signed integers.

## Common Pitfalls & Gotchas

1. **C's implicit volatile qualifier** — In C, you must manually mark peripheral registers as `volatile` to prevent the compiler from optimizing away reads. Forget one `volatile`, and your sensor returns stale data. Rust's `MMIO` abstractions (via `cortex_m::peripheral`) handle this automatically, but if you use `unsafe` to dereference a raw pointer, you must add `core::ptr::read_volatile` yourself—easy to miss.

2. **Interrupt safety in Rust is non-trivial** — The C driver above works fine with interrupts because `HAL_I2C_Master_Transmit` is reentrant if you use DMA. In Rust, sharing an `I2c` between main loop and interrupt requires `Mutex<RefCell<I2C>>` or a critical section. This is safer, but it forces you to design your interrupt architecture upfront. I spent an hour debugging a deadlock because I forgot to release a `Mutex` in an ISR.

3. **Generic bloat in Rust** — The Rust driver compiles to a monomorphized copy for each I²C bus type. If you have two different I²C peripherals (e.g., I2C1 and I2C2), you get two copies of `read_temperature`. On a Cortex-M0 with 16KB flash, this can blow your budget. Use `#[inline(never)]` or trait objects (`&mut dyn I2c`) to control code size, but that adds runtime overhead.

## Try It Yourself

1. **Port a C driver to Rust** — Take any I²C sensor driver you've written in C (e.g., BME280, MPU6050). Rewrite it using `embedded-hal` traits. Compare the number of lines and the error handling patterns. Did Rust catch any potential race conditions?

2. **Benchmark code size** — Compile both drivers for the same MCU (e.g., `thumbv7em-none-eabihf` for Cortex-M4). Use `cargo size` and `arm-none-eabi-size` to compare flash and RAM usage. Try adding `#[inline(never)]` to the Rust functions and measure the difference.

3. **Test interrupt safety** — Create a Rust project that reads the TMP102 from both `main` and a timer interrupt. Use `cortex_m::interrupt::Mutex` to share the I²C bus. Then write the equivalent in C with a global `I2C_HandleTypeDef`. Run both for 10 minutes and count hard faults or data corruption.

## Next Up

Tomorrow is the capstone: **Full Review & Project: Embassy BLE Thermometer**. We'll build a complete Bluetooth Low Energy temperature sensor using the Embassy async framework, combining everything from the past 19 days—RTIC, DMA, I²C, and BLE—into a single, production-ready project. Bring your nRF52840 DK.
