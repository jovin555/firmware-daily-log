---
title: "Day 13: Embassy Peripherals: GPIO, UART, SPI, I2C Async APIs"
date: 2026-06-25
tags: ["til", "rust-embedded", "peripherals", "async", "drivers"]
---

## What I Explored Today

Today I dove into Embassy's async peripheral APIs for the four most common embedded interfaces: GPIO, UART, SPI, and I2C. After weeks of using blocking HALs and manual state machines, seeing how Embassy wraps these peripherals in `async fn` calls that yield to the executor during I/O waits felt like a revelation. I wired up an nRF52840 to an external EEPROM over I2C, a GPS module over UART, and an LED matrix over SPI — all running concurrently under Embassy's executor without a single busy-wait loop.

## The Core Concept

The fundamental shift Embassy brings is that **peripheral operations become awaitable futures**. Instead of calling `blocking_read()` and stalling the entire CPU, you call `read_async()` which returns a future that yields control back to the executor. The hardware DMA or interrupt handles the actual transfer, and when it completes, the executor resumes your task.

This matters because in real embedded systems, you're rarely doing just one thing. A sensor read might take 10ms over I2C — that's 10ms of wasted CPU cycles if you block. With Embassy's async peripherals, that same 10ms can service a UART buffer, toggle a status LED, or process incoming SPI data. The executor multiplexes all these I/O-bound tasks efficiently.

The pattern is consistent across all peripherals: you get a peripheral instance from the HAL (often via `take()` or `split()`), configure it with Embassy's `Config` structs, then call async methods. Under the hood, Embassy uses the hardware's interrupt-driven or DMA capabilities, registered with the executor via `impl_embassy_async` or similar macros.

## Key Commands / Configuration / Code

Here's a concrete example showing all four peripherals running concurrently on an nRF52840:

```rust
// Cargo.toml dependencies
// embassy-executor = { version = "0.6", features = ["arch-cortex-m", "executor-thread"] }
// embassy-nrf = { version = "0.6", features = ["gpiote", "time-driver-rtc1", "nrf52840"] }
// embassy-time = { version = "0.3", features = ["tick-hz-32_768"] }

use embassy_executor::Spawner;
use embassy_nrf::{
    bind_interrupts,
    gpio::{AnyPin, Input, Level, Output, OutputDrive, Pull},
    i2c::{self, I2c},
    peripherals,
    spim::{self, Spim},
    uarte::{self, Uarte},
};
use embassy_time::{Duration, Timer};

bind_interrupts!(struct Irqs {
    UARTE0_UART0 => uarte::InterruptHandler<peripherals::UARTE0>;
    SPIM0_SPIS0_TWIM0_TWIS0_SPI0_TWI0 => spim::InterruptHandler<peripherals::SPIM0>;
    TWIM1_TWIS1_SPI1_TWI1 => i2c::InterruptHandler<peripherals::TWIM1>;
});

#[embassy_executor::main]
async fn main(spawner: Spawner) {
    let p = embassy_nrf::init(Default::default());

    // GPIO: blink an LED on a timer
    let led = Output::new(p.P0_13, Level::Low, OutputDrive::Standard);
    spawner.spawn(blink(led)).unwrap();

    // UART: read from GPS at 9600 baud
    let mut uart_config = uarte::Config::default();
    uart_config.parity = uarte::Parity::EXCLUDED;
    uart_config.baudrate = uarte::Baudrate::BAUD9600;
    let uart = Uarte::new(p.UARTE0, Irqs, p.P0_08, p.P0_06, uart_config);
    spawner.spawn(read_gps(uart)).unwrap();

    // SPI: drive an LED matrix (74HC595 shift registers)
    let mut spi_config = spim::Config::default();
    spi_config.frequency = spim::Frequency::M1;
    let spi = Spim::new(p.SPIM0, Irqs, p.P0_03, p.P0_04, p.P0_05, spi_config);
    spawner.spawn(display_matrix(spi)).unwrap();

    // I2C: read temperature from an LM75 sensor
    let mut i2c_config = i2c::Config::default();
    i2c_config.frequency = i2c::Frequency::K100;
    let i2c = I2c::new(p.TWIM1, Irqs, p.P0_26, p.P0_27, i2c_config);
    spawner.spawn(read_temperature(i2c)).unwrap();

    loop {
        Timer::after(Duration::from_secs(1)).await;
    }
}

#[embassy_executor::task]
async fn blink(mut led: Output<'static>) {
    loop {
        led.set_high();
        Timer::after(Duration::from_millis(500)).await;
        led.set_low();
        Timer::after(Duration::from_millis(500)).await;
    }
}

#[embassy_executor::task]
async fn read_gps(mut uart: Uarte<'static>) {
    let mut buf = [0u8; 64];
    loop {
        // Async read — yields while waiting for UART data
        match uart.read_async(&mut buf).await {
            Ok(n) => { /* process n bytes from GPS */ }
            Err(e) => { /* handle error */ }
        }
    }
}

#[embassy_executor::task]
async fn display_matrix(mut spi: Spim<'static>) {
    let frame = [0xAA, 0x55, 0xAA, 0x55]; // checkerboard pattern
    loop {
        // Async SPI write — DMA handles the transfer
        spi.write_async(&frame).await.unwrap();
        Timer::after(Duration::from_millis(100)).await;
    }
}

#[embassy_executor::task]
async fn read_temperature(mut i2c: I2c<'static>) {
    let addr: u8 = 0x48; // LM75 address
    let reg: u8 = 0x00;  // temperature register
    let mut temp_buf = [0u8; 2];
    loop {
        // Async I2C transaction — write register address, then read 2 bytes
        i2c.write_read_async(addr, &[reg], &mut temp_buf).await.unwrap();
        let temp_c = i16::from_be_bytes(temp_buf) as f32 / 256.0;
        Timer::after(Duration::from_secs(1)).await;
    }
}
```

Note the key patterns:
- `bind_interrupts!` macro connects hardware interrupts to Embassy's driver
- Each peripheral gets its own `#[embassy_executor::task]` — these are lightweight coroutines
- `read_async()`, `write_async()`, `write_read_async()` all return futures
- `Timer::after()` is the async equivalent of `delay_ms()` — non-blocking

## Common Pitfalls & Gotchas

1. **Interrupt binding must match hardware exactly.** If you bind `UARTE0_UART0` but your chip uses `UARTE1`, the executor will never see the interrupt completion. Check your chip's datasheet for exact interrupt names — they vary between nRF52 variants and are completely different on STM32 or RP2040.

2. **Peripheral instances are consumed once.** You cannot call `Uarte::new()` twice on the same peripheral. If you need to share a UART between tasks, use Embassy's `share` mechanism or wrap it in a `Mutex` — but the simpler approach is to have one task own the peripheral and communicate via channels.

3. **Async methods require the peripheral to be `'static`.** Notice the `'static` lifetime in the task signatures. If you try to pass a local peripheral reference, the compiler will reject it because the executor needs the future to outlive the current scope. Use `move` closures or pass owned peripherals.

4. **DMA buffers must remain valid for the entire async operation.** If you pass a stack-local buffer to `read_async()` and the task yields, the buffer might be overwritten. Always use `static mut` buffers or heap-allocated slices for DMA transfers.

## Try It Yourself

1. **Extend the example above** to add a fourth task that reads a button press (GPIO input with interrupt) and toggles the LED blink rate. Use `Input::new()` with `Pull::Up` and `embassy_nrf::gpio::InputPolarity`.

2. **Replace the UART GPS reader** with a loopback test: connect TX to RX on your board and verify that `write_async()` followed by `read_async()` returns the same bytes. This confirms your async UART pipeline works end-to-end.

3. **Add error recovery** to the I2C temperature task. I2C buses can NAK or timeout. Wrap the `write_read_async()` call in a retry loop with exponential backoff using `Timer::after()` between attempts.

## Next Up

Tomorrow, we take these async peripherals to the network layer. I'll explore **Embassy Networking: TCP/IP & BLE with nrf-softdevice** — running an HTTP server and BLE GATT service concurrently on the same chip, all under the Embassy executor.
