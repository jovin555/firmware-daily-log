---
title: "Day 07: UART Communication: Async Rust Zephyr Drivers"
date: 2026-07-16
tags: ["til", "rust-zephyr-nrf54", "uart", "async"]
---

## What I Explored Today

Today I got UART (serial) communication working on the nRF54LM20 using Zephyr's async Rust driver bindings. After days of GPIO toggling and timer interrupts, this feels like real I/O. The goal was straightforward: send "Hello from nRF54LM20\n" every second over UART0 (P0.00 TX, P0.01 RX at 115200 baud), and echo back any received characters. What I learned about Zephyr's async UART API, buffer management, and the Rust `async`/`await` integration was surprisingly nuanced.

## The Core Concept

Zephyr's UART driver in Rust is built on top of the C `uart_irq_callback_set` and DMA-capable `uart_rx_enable`/`uart_tx` functions, but wrapped in an async Rust API that uses Zephyr's own workqueue-based executor. The key insight: you don't spin-wait or use interrupts directly. Instead, you call `uart.write(&buf).await` and the driver suspends your task, sets up a DMA or interrupt-driven transfer, and resumes when the hardware signals completion.

Why this matters for embedded: async UART eliminates busy-looping `while (UART->TXRDY == 0)` patterns. On the nRF54LM20, which has a Cortex-M33 with a small 256KB SRAM, this means the CPU can service other tasks (sensor reads, BLE stack) while a UART transfer completes in the background. The Rust borrow checker also prevents you from accidentally sharing the UART handle across tasks without proper synchronization — a common source of buffer corruption in C.

## Key Commands / Configuration / Code

**Device Tree Overlay** (`boards/arm/nrf54lm20/nrf54lm20.overlay`):
```dts
&uart0 {
    status = "okay";
    current-speed = <115200>;
    pinctrl-0 = <&uart0_default>;
    pinctrl-1 = <&uart0_sleep>;
    pinctrl-names = "default", "sleep";
};
```

**Pin Control** (in the same overlay):
```dts
&pinctrl {
    uart0_default: uart0_default {
        group1 {
            psels = <NRF_PSEL(UART_TX, 0, 0)>,
                    <NRF_PSEL(UART_RX, 0, 1)>;
        };
    };
    uart0_sleep: uart0_sleep {
        group1 {
            psels = <NRF_PSEL(UART_TX, 0, 0)>,
                    <NRF_PSEL(UART_RX, 0, 1)>;
            low-power-enable;
        };
    };
};
```

**Rust Application** (`src/main.rs`):
```rust
use zephyr::uart::{Uart, Config, Parity, StopBits, DataBits};
use zephyr::sync::Mutex;
use core::cell::RefCell;

// Static UART handle — Zephyr requires device tree label
static UART: Mutex<RefCell<Option<Uart>>> = Mutex::new(RefCell::new(None));

#[zephyr::task]
async fn uart_echo() {
    // Initialize UART0 at 115200 8N1
    let config = Config {
        baudrate: 115200,
        parity: Parity::None,
        stop_bits: StopBits::One,
        data_bits: DataBits::Eight,
        flow_control: false,
    };
    
    let mut uart = Uart::new("uart0", config).unwrap();
    
    // TX buffer — static to avoid stack allocation in async context
    let tx_buf: &[u8] = b"Hello from nRF54LM20\n";
    let mut rx_buf = [0u8; 64];
    
    loop {
        // Send greeting
        uart.write(tx_buf).await.unwrap();
        
        // Read up to 64 bytes (non-blocking, returns actual count)
        let n = uart.read(&mut rx_buf).await.unwrap();
        if n > 0 {
            // Echo back what we received
            uart.write(&rx_buf[..n]).await.unwrap();
        }
        
        // Yield to other tasks for 1 second
        zephyr::time::sleep(zephyr::time::Duration::secs(1)).await;
    }
}

fn main() {
    // Register our async task with Zephyr's workqueue
    zephyr::task::spawn(uart_echo());
}
```

**Build and Flash**:
```bash
west build -b nrf54lm20/nrf54lm20/cpuapp -p always .
west flash --runner nrfjprog
# Monitor with: screen /dev/ttyACM0 115200
```

## Common Pitfalls & Gotchas

1. **Buffer lifetimes in async contexts**: The `uart.write()` call takes a `&[u8]` that must live until the future completes. If you pass a stack-allocated buffer that goes out of scope (e.g., inside a loop iteration), the borrow checker will catch it — but only if you use the correct lifetime annotations. I initially tried passing a `Vec<u8>` created inside the loop, which compiled but caused random data corruption because the DMA engine read freed memory. Solution: use `static` buffers or allocate them with `Box::pin` before the loop.

2. **UART handle ownership**: Zephyr's `Uart::new()` consumes the device and returns a single-owner handle. You cannot clone it or share it between tasks without wrapping in a `Mutex<RefCell<>>`. Attempting to call `uart.write()` from two tasks simultaneously will panic at runtime (the driver checks for exclusive access). I learned this the hard way when trying to have a button task and a sensor task both write to the same UART.

3. **Baud rate mismatch with nRF54 bootloader**: The nRF54LM20's ROM bootloader uses 115200 baud, but some Zephyr configurations default to 1000000 (1Mbps). If your overlay doesn't explicitly set `current-speed = <115200>`, the bootloader and application will use different rates, and you'll see garbage on the terminal. Always verify with a logic analyzer or scope if possible.

## Try It Yourself

1. **Add a second UART instance**: Configure UART1 on P0.10 (TX) and P0.11 (RX) at 9600 baud. Create a separate async task that reads from UART1 and forwards to UART0. This simulates a serial bridge.

2. **Implement a simple command parser**: Modify the echo task to recognize a "LED_ON" command (received over UART) and toggle an LED on P0.13. Use `str::from_utf8` on the received buffer and match against known commands.

3. **Measure throughput**: Add a counter that increments every 1000 bytes sent. Use `zephyr::time::Instant::now()` to measure how long it takes to send 10KB of data. Compare the async approach with a busy-loop version (you can use `uart.write_blocking()` for the latter).

## Next Up

Tomorrow I'm tackling **SPI & I2C Peripheral Access in Rust on nRF54LM20** — reading an MPU6050 IMU over I2C and an SD card over SPI, with proper async transaction handling and device tree pin muxing.
