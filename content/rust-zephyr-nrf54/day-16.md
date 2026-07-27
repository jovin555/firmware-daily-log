---
title: "Day 16: Logging & Debugging: defmt/RTT with Zephyr on nRF54LM20"
date: 2026-07-27
tags: ["til", "rust-zephyr-nrf54", "defmt", "rtt"]
---

## What I Explored Today

Today I integrated `defmt` (deferred formatting) with RTT (Real-Time Transfer) into my Rust + Zephyr workflow on the nRF54LM20. After weeks of relying on GPIO toggles and the occasional `printk` panic, I finally have structured, low-overhead logging that doesn't steal CPU cycles from my real-time tasks. The setup uses the `defmt-rtt` crate to stream formatted log messages over the debug probe's RTT channel, with Zephyr's own logging system bridged through a custom backend. The result: sub-microsecond log overhead, zero heap allocation, and full integration with `probe-rs` and `rtt-target`.

## The Core Concept

Embedded logging has always been a trade-off: you want rich debug output, but every `printf` call blocks the CPU, allocates memory, or both. `defmt` solves this by deferring the expensive string formatting to the host. Instead of formatting `"sensor_read: temp=%d, pressure=%d"` on the target, the target sends a compact binary frame containing a format string index and raw integers. The host tool (like `probe-rs` or `defmt-print`) reconstructs the human-readable message.

RTT (Real-Time Transfer) is the transport layer. Unlike UART, RTT uses a shared memory buffer that the debug probe polls via SWD/JTAG. The target writes log entries into a ring buffer; the host reads them out as fast as the debug probe can poll. This is non-blocking for the target—no waiting for bytes to shift out a UART line.

For Zephyr integration, the trick is to replace Zephyr's default logging backend with one that feeds into `defmt`. This gives us access to Zephyr's rich log macros (`LOG_INF`, `LOG_ERR`, etc.) while keeping the performance benefits of `defmt`. The nRF54LM20's Cortex-M33 core has a DWT cycle counter, so we can even timestamp logs with single-cycle precision.

## Key Commands / Configuration / Code

### Cargo dependencies (Cargo.toml)
```toml
[dependencies]
defmt = "0.3"
defmt-rtt = "0.4"
zephyr = { git = "https://github.com/zephyrproject-rtos/zephyr", features = ["log"] }

# For cycle-accurate timestamps
cortex-m = "0.7"
cortex-m-rt = "0.7"
```

### Zephyr Kconfig (prj.conf)
```kconfig
# Enable Zephyr logging
CONFIG_LOG=y
CONFIG_LOG_MODE_IMMEDIATE=y

# Disable default UART backend — we'll use defmt-RTT
CONFIG_LOG_BACKEND_UART=n

# Reduce log buffer to save RAM (defmt handles buffering)
CONFIG_LOG_BUFFER_SIZE=256

# Enable RTT peripheral
CONFIG_HAS_SEGGER_RTT=y
CONFIG_RTT_CONSOLE=n  # We don't want Zephyr's RTT console, just defmt
```

### Initialization code (main.rs)
```rust
use defmt_rtt as _;  // Initialize RTT channel on startup
use zephyr::log::*;

// Global logger instance that bridges Zephyr logs to defmt
struct DefmtLogger;

impl LogBackend for DefmtLogger {
    fn put(&self, level: LogLevel, msg: &str) {
        // Forward to defmt with level mapping
        match level {
            LogLevel::Err => defmt::error!("{}", msg),
            LogLevel::Wrn => defmt::warn!("{}", msg),
            LogLevel::Inf => defmt::info!("{}", msg),
            LogLevel::Dbg => defmt::debug!("{}", msg),
        }
    }
}

#[no_mangle]
pub extern "C" fn rust_main() {
    // Register our backend before any Zephyr init
    static LOGGER: DefmtLogger = DefmtLogger;
    log_backend_register(&LOGGER);

    // Now Zephyr's LOG_INF, etc. will flow through defmt
    LOG_INF!("Zephyr logging via defmt-RTT initialized");

    // Direct defmt usage for performance-critical paths
    let sensor_val: u16 = 0xABCD;
    defmt::info!("sensor_read: val={=u16:04x}", sensor_val);
}
```

### Host-side viewing (two options)
```bash
# Option 1: probe-rs with defmt support
probe-rs run --chip nRF54LM20 target/thumbv8m.main-none-eabi/debug/myapp --defmt

# Option 2: Standalone defmt-print (for CI or headless)
probe-rs rtt --chip nRF54LM20 | defmt-print -e target/thumbv8m.main-none-eabi/debug/myapp
```

### Timestamp integration (optional but recommended)
```rust
use cortex_m::peripheral::DWT;

// In your main loop or ISR
let cycles = DWT::get_cycle_count();
defmt::info!("cycle_count={=u32}", cycles);
```

## Common Pitfalls & Gotchas

1. **RTT buffer overflow silently drops logs.** The default RTT buffer in `defmt-rtt` is 1024 bytes. If your logging rate exceeds the host's read speed, the ring buffer wraps and older entries are lost. Monitor this by checking `defmt_rtt::get_buf().wraps()` periodically. Increase buffer size with `#[defmt_rtt::buffer(4096)]` if needed.

2. **Zephyr's `LOG_INF` macros expect a format string at compile time.** If you pass a dynamic string (e.g., from a sensor buffer), Zephyr's logger will try to format it at runtime, defeating `defmt`'s purpose. Always use `defmt::info!("raw={=u8}", byte)` for dynamic data, and reserve `LOG_INF!` for static messages.

3. **`defmt-rtt` must be initialized before any Zephyr logging call.** If a Zephyr module calls `LOG_INF` during its constructor (before `rust_main` runs), the defmt RTT channel won't be ready. Fix this by initializing `defmt_rtt` in a `#[pre_init]` function:

```rust
#[pre_init]
unsafe fn early_init() {
    defmt_rtt::init();
}
```

## Try It Yourself

1. **Set up the defmt-RTT bridge.** Add the dependencies above to your project, configure `prj.conf` to disable UART logging, and implement the `DefmtLogger` backend. Run `probe-rs run --defmt` and verify you see "Zephyr logging via defmt-RTT initialized" in the host output.

2. **Profile log overhead with DWT.** Add cycle counting around a `defmt::info!` call in a tight loop (e.g., 1000 iterations). Measure the total cycles and divide by iterations. Compare this to the same loop using `printk`. You should see defmt taking <100 cycles vs. printk's thousands.

3. **Add structured logging with timestamps.** Modify your sensor reading code to log each reading with a cycle timestamp. Use `defmt::info!("sensor={=u16:04x} @cycle={=u32}", val, DWT::get_cycle_count())`. Pipe the output through `defmt-print` and verify timestamps are monotonically increasing.

## Next Up

Tomorrow we tackle **Unit Testing Rust Zephyr Code: Twister & Host Tests**. I'll show you how to run Zephyr's Twister test framework against Rust modules, mock hardware peripherals for host-side testing, and integrate `cargo test` with Zephyr's CMake build system. No more flashing to test a simple state machine.
