---
title: "Day 16: probe-rs: Flash, Debug & RTT for Embedded Rust"
date: 2026-06-28
tags: ["til", "rust-embedded", "probe-rs", "flash", "rtt"]
---

## What I Explored Today

Today I went all-in on `probe-rs`, the Swiss Army knife for embedded Rust development. After weeks of manually invoking `cargo flash` and `cargo run` with separate debuggers, I finally wired up a complete workflow: flashing firmware, interactive debugging with GDB, and real-time logging via RTT (Real-Time Transfer). The tooling is mature enough that I can now replace OpenOCD, JLinkExe, and semihosting with a single Rust-native toolchain.

## The Core Concept

`probe-rs` is a library and CLI tool that talks directly to debug probes (ST-Link, J-Link, CMSIS-DAP, etc.) using the CMSIS-DAP or USB protocols. No external GDB server needed. It handles three critical tasks:

1. **Flashing** — Erase and program target flash memory with ELF binaries
2. **Debugging** — Provide a GDB stub so you can use `gdb-multiarch` or `lldb` for breakpoints, stepping, and memory inspection
3. **RTT** — Capture `rprintln!()` output from your firmware over the debug probe, without blocking execution

The "why" is simple: every other approach adds latency or complexity. OpenOCD requires configuration files and separate server processes. Semihosting requires a debugger connection and can crash if the host isn't listening. RTT is non-blocking, zero-wire (uses existing SWD pins), and gives you printf-style debugging without sacrificing real-time behavior.

## Key Commands / Configuration / Code

### 1. Installing probe-rs

```bash
# Install the CLI tools
cargo install probe-rs-tools --features cli

# Verify probe detection
probe-rs list
# Example output:
# [0]: STLink v3 (VID: 0483, PID: 374e, Serial: 003002...)
```

### 2. Flashing firmware

```bash
# Flash a release binary to an STM32F4
probe-rs run --chip STM32F407VGT6 target/thumbv7em-none-eabihf/release/my-firmware

# Or just flash without running (useful for testing)
probe-rs download --chip STM32F407VGT6 --format elf target/thumbv7em-none-eabihf/release/my-firmware
```

### 3. Debugging with GDB

```bash
# Start probe-rs in GDB server mode (port 1337 by default)
probe-rs gdb --chip STM32F407VGT6

# In another terminal, connect with GDB
gdb-multiarch target/thumbv7em-none-eabihf/debug/my-firmware
(gdb) target remote :1337
(gdb) load
(gdb) monitor reset
(gdb) break main
(gdb) continue
```

### 4. RTT Configuration in Cargo.toml

```toml
[dependencies]
rtt-target = { version = "0.4", features = ["cortex-m"] }
```

### 5. RTT Initialization in main.rs

```rust
// src/main.rs
#![no_std]
#![no_main]

use cortex_m_rt::entry;
use rtt_target::{rtt_init_print, rprintln};
use panic_halt as _;

#[entry]
fn main() -> ! {
    // Initialize RTT with up-channel 0 (default for print)
    rtt_init_print!();

    loop {
        rprintln!("Hello from probe-rs RTT! Tick: {}", systick::now());
        // Your real-time code here
        cortex_m::asm::delay(10_000_000);
    }
}
```

### 6. Capturing RTT Output

```bash
# Start RTT logging (non-blocking, runs alongside debugger)
probe-rs rtt --chip STM32F407VGT6

# You'll see live output:
# Hello from probe-rs RTT! Tick: 0
# Hello from probe-rs RTT! Tick: 1
# ...
```

### 7. Complete Cargo Config for probe-rs Runner

```toml
# .cargo/config.toml
[target.'cfg(all(target_arch = "arm", target_os = "none"))']
runner = "probe-rs run --chip STM32F407VGT6"

[build]
target = "thumbv7em-none-eabihf"
```

Now `cargo run` flashes and runs your firmware in one step.

## Common Pitfalls & Gotchas

### 1. RTT Buffer Overflow
RTT uses a fixed-size circular buffer (default 1024 bytes). If your firmware writes faster than the host reads, old data gets overwritten silently. Increase buffer size via `rtt_init_print!(UpBufferSize(4096))` or throttle your `rprintln!()` calls.

### 2. GDB Connection Drops on Reset
When you issue `monitor reset` from GDB, the target resets and the SWD connection can drop. Always follow with `continue` immediately, or use `monitor reset halt` to keep the CPU stopped after reset. I lost 30 minutes to this — the target was running but GDB thought it was disconnected.

### 3. Chip Selection Mismatch
`probe-rs` uses exact chip part numbers. `STM32F407VGT6` works, but `STM32F407` (without suffix) fails. Run `probe-rs chip list | grep STM32F407` to find the exact name. Wrong chip = flash address errors or bricked debug session.

### 4. RTT Requires Debug Connection
RTT works over SWD, so you need the debug probe connected and powered. If you unplug the probe, RTT output stops silently — no error, no warning. Always verify the probe is listed with `probe-rs list` before starting RTT capture.

## Try It Yourself

1. **Flash and RTT**: Create a new `cortex-m-quickstart` project, add `rtt-target` dependency, and flash it using `probe-rs run`. Capture the RTT output with `probe-rs rtt` in a separate terminal.

2. **GDB Breakpoint Exercise**: Set a breakpoint on a function that toggles an LED. Use `probe-rs gdb` to start the server, connect GDB, step through the function, and verify the pin state with `monitor peek32 0x40020C14` (GPIO ODR for STM32F4).

3. **RTT Performance Test**: Write a firmware loop that calls `rprintln!()` every microsecond (use a hardware timer). Measure how many messages per second you can capture without data loss. Increase the RTT buffer to 8KB and compare throughput.

## Next Up

Tomorrow: **Testing Embedded Rust: Unit Tests on Host & QEMU** — I'll show you how to run `cargo test` for `no_std` code on your development machine, mock hardware peripherals, and use QEMU to integration-test interrupt handlers without touching real silicon.
