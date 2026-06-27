---
title: "Day 15: defmt: Efficient Logging for Embedded Rust"
date: 2026-06-27
tags: ["til", "rust-embedded", "defmt", "logging", "rtt"]
---

## What I Explored Today

Today I integrated `defmt` (deferred formatting) into an STM32F4 firmware project and finally understood why every production embedded Rust project uses it. The standard `println!` approach consumes ~200 bytes per format string and blocks the CPU during UART transmission. `defmt` flips that model: format strings live on the host, only binary data crosses the wire, and the host reconstructs the log messages. My test firmware went from 12 KB of log overhead to under 400 bytes, with zero blocking on the target.

## The Core Concept

The fundamental insight of `defmt` is that **format strings are static metadata, not runtime data**. When you write `defmt::info!("Sensor reading: {}", value)`, the compiler extracts the format string `"Sensor reading: {}"` into a separate ELF section (`.defmt`). The target only transmits the raw bytes of `value` — typically 4 bytes for a `u32`. The host tool (like `probe-rs` or `defmt-print`) reads the ELF file, finds the format strings by index, and reconstructs the human-readable message.

This matters because on a Cortex-M4 with 64 KB of RAM and 256 KB of flash, every byte counts. A single `println!("Temperature: {}°C, humidity: {}%", temp, hum)` would send ~40 ASCII characters over UART at 115200 baud, taking ~3.5 ms. With `defmt`, it sends 8 bytes (two `u32` values) in under 0.7 ms. The CPU is free to handle interrupts instead of spinning on TX FIFO.

`defmt` also supports a logging framework with five levels: `trace`, `debug`, `info`, `warn`, `error`. At compile time, you can set a maximum level — logs below that threshold are compiled out entirely, producing zero code size impact. This is a game-changer for release builds.

## Key Commands / Configuration / Code

### Cargo.toml dependencies

```toml
[dependencies]
defmt = "0.3"
defmt-rtt = "0.4"
cortex-m = "0.7"
cortex-m-rt = "0.7"
panic-probe = { version = "0.3", features = ["print-defmt"] }

[profile.release]
debug = 2  # Required: defmt needs debug info for format strings
```

### Initializing the logger

```rust
// main.rs
#![no_std]
#![no_main]

use defmt_rtt as _;          // Global logger using RTT (no UART pins needed)
use panic_probe as _;        // Panic handler that prints via defmt

#[cortex_m_rt::entry]
fn main() -> ! {
    // defmt is automatically initialized via defmt_rtt
    // No init call needed — it's a global singleton

    defmt::info!("System starting");
    defmt::debug!("Clock configured at {} MHz", 168u32);

    let sensor_val: u32 = 0xABCD;
    defmt::info!("Sensor raw: {=u32:08x}", sensor_val);
    // Host sees: "Sensor raw: 0000abcd"

    loop {
        defmt::trace!("Main loop iteration");
        cortex_m::asm::wfi();
    }
}
```

### Viewing logs with probe-rs

```bash
# Terminal 1: Flash and view logs
probe-rs run --chip STM32F407ZGTX target/thumbv7em-none-eabihf/debug/my-firmware

# Or use defmt-print for offline analysis
probe-rs download --chip STM32F407ZGTX firmware.elf
probe-rs rtt --chip STM32F407ZGTX | defmt-print -e firmware.elf
```

### Setting log level at compile time

```rust
// In main.rs or lib.rs
// Only info, warn, error will be compiled
// trace and debug are eliminated
#![defmt_log_level = "info"]
```

Or via environment variable:
```bash
DEFMT_LOG=info cargo build
```

## Common Pitfalls & Gotchas

**1. Forgetting debug symbols in release builds**
`defmt` requires the `.defmt` section in the ELF file, which is only present when `debug = 2` or `debug = 1` is set in `[profile.release]`. Without it, the host tool can't find format strings and you'll see raw hex output. Always verify with `cargo readobj -- --sections | grep defmt`.

**2. Using format strings with non-defmt types**
`defmt` has its own `Format` trait. Standard `core::fmt::Display` types won't work. Use `defmt::Format` derive macro for your structs, or use the `{=u32}` syntax for primitive types. The compiler error is cryptic: "the trait `defmt::Format` is not implemented".

**3. RTT buffer overflow on high-frequency logging**
The default RTT up-buffer is 1 KB. If you log faster than the host reads, the buffer wraps and you lose messages. Increase it with `#[defmt_rtt::defmt_rtt(up_buffer_size = 4096)]` in your main.rs, or throttle logs with a rate limiter in hot loops.

## Try It Yourself

1. **Port a `println!`-based project to `defmt`**: Take any existing firmware that uses `cortex_m_semihosting::hprintln` or UART-based printing. Replace with `defmt` + `defmt-rtt`. Compare the binary sizes with `cargo size --release` before and after.

2. **Implement a custom `Format` for a sensor struct**: Create a struct with temperature and humidity fields. Derive `defmt::Format` and log it with `defmt::info!("Sensor: {}", my_struct)`. Verify the output shows field names and values.

3. **Measure logging latency with a GPIO toggle**: Toggle a GPIO pin before and after a `defmt::info!` call. Use a logic analyzer to measure the pulse width. Compare against the same test with `println!` over UART at 115200 baud.

## Next up

Tomorrow I'll dive into **probe-rs: Flash, Debug & RTT for Embedded Rust** — the Swiss Army knife for embedded development. We'll set up a debugging workflow with VS Code, use RTT for real-time data streaming, and flash firmware without touching a single button.
