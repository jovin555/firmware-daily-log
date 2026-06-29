---
title: "Day 17: Testing Embedded Rust: Unit Tests on Host & QEMU"
date: 2026-06-29
tags: ["til", "rust-embedded", "testing", "qemu", "hil"]
---

## What I Explored Today

Today I wired up a proper testing pipeline for an embedded Rust project targeting a Cortex-M4 MCU. I got unit tests running natively on my host machine (fast iteration, no hardware), and integration tests executing under QEMU in system emulation mode (closer to real hardware, still no soldering iron). The goal was to catch logic errors early without flashing a board 200 times.

## The Core Concept

Embedded testing has a tension: you want the speed of `cargo test` on your laptop, but you need to verify hardware interactions. The pragmatic split is:

- **Host-side unit tests**: Test pure logic, data structures, and algorithms. These run at native speed, use `std` (if you gate it), and catch 80% of bugs.
- **QEMU integration tests**: Test peripheral interactions, interrupt handlers, and memory-mapped I/O patterns. QEMU emulates the CPU and common peripherals (UART, GPIO, timers) well enough to catch register-level mistakes.

The trick is to structure your crate so that hardware-dependent code is behind a trait or conditional compilation. You test the trait implementations on host with mock peripherals, then verify the real implementation under QEMU.

## Key Commands / Configuration / Code

### 1. Cargo workspace structure

```
my-project/
├── Cargo.toml          # workspace root
├── firmware/
│   ├── Cargo.toml      # #![no_std] crate
│   └── src/
│       ├── lib.rs
│       ├── uart.rs
│       └── tests/      # integration tests (host)
└── tests/              # integration tests (QEMU)
    ├── qemu_uart.rs
    └── qemu_test_runner.rs
```

### 2. Host-side unit tests with conditional std

In `firmware/Cargo.toml`:
```toml
[package]
name = "firmware"
version = "0.1.0"
edition = "2021"

[dependencies]
cortex-m = "0.7"
cortex-m-rt = "0.7"
panic-halt = "0.2"

[dev-dependencies]
# Only used when testing on host
std = { package = "std", version = "1" }  # dummy, we use cfg(test)
```

In `firmware/src/lib.rs`:
```rust
#![no_std]
#![cfg_attr(not(test), no_main)]  // no_main only in non-test builds

use core::fmt::Write;

// Trait for UART abstraction — testable on host
pub trait UartWrite {
    fn write_byte(&mut self, byte: u8);
    fn write_str(&mut self, s: &str) {
        for b in s.bytes() {
            self.write_byte(b);
        }
    }
}

// Production implementation (Cortex-M specific)
#[cfg(not(test))]
pub mod hal {
    use super::UartWrite;
    use cortex_m::asm;

    pub struct Uart {
        base: usize,
    }

    impl UartWrite for Uart {
        fn write_byte(&mut self, byte: u8) {
            // Wait until TX buffer empty
            while unsafe { core::ptr::read_volatile((self.base + 0x18) as *const u32) } & (1 << 5) == 0 {}
            unsafe { core::ptr::write_volatile((self.base + 0x00) as *mut u8, byte); }
        }
    }
}

// Mock implementation for host testing
#[cfg(test)]
pub mod mock {
    use super::UartWrite;
    use std::sync::Mutex;

    pub struct MockUart {
        pub output: Mutex<Vec<u8>>,
    }

    impl MockUart {
        pub fn new() -> Self {
            MockUart { output: Mutex::new(Vec::new()) }
        }
    }

    impl UartWrite for MockUart {
        fn write_byte(&mut self, byte: u8) {
            self.output.lock().unwrap().push(byte);
        }
    }
}

// Function under test — works with any UartWrite impl
pub fn send_greeting(uart: &mut impl UartWrite) {
    uart.write_str("Hello, embedded!\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_send_greeting() {
        let mut uart = mock::MockUart::new();
        send_greeting(&mut uart);
        let output = uart.output.lock().unwrap();
        assert_eq!(&output[..], b"Hello, embedded!\n");
    }
}
```

Run host tests:
```bash
cd firmware
cargo test --lib   # runs host-side unit tests
```

### 3. QEMU integration tests

Install QEMU for ARM:
```bash
# Ubuntu/Debian
sudo apt install qemu-system-arm

# macOS
brew install qemu
```

Create `tests/qemu_uart.rs`:
```rust
//! Integration test that runs under QEMU system emulation
//! Uses semihosting to print results back to host

#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;
use firmware::hal::Uart;
use firmware::send_greeting;

#[entry]
fn main() -> ! {
    // UART0 base address for STM32F4 (example)
    let mut uart = Uart { base: 0x4001_1000 };
    send_greeting(&mut uart);

    // Signal test pass via semihosting
    loop {
        // In real test, you'd check UART output via QEMU's -serial file:...
    }
}
```

Build and run under QEMU:
```bash
# Build for target
cargo build --target thumbv7em-none-eabihf --release

# Run under QEMU (STM32F4 Discovery board emulation)
qemu-system-arm \
    -machine stm32f4-discovery \
    -kernel target/thumbv7em-none-eabihf/release/firmware \
    -nographic \
    -serial mon:stdio \
    -semihosting
```

### 4. Automating with a test runner script

Create `run_qemu_tests.sh`:
```bash
#!/bin/bash
set -euo pipefail

TARGET=thumbv7em-none-eabihf
BINARY=target/$TARGET/release/firmware

echo "Building for QEMU..."
cargo build --target $TARGET --release

echo "Running under QEMU..."
qemu-system-arm \
    -machine stm32f4-discovery \
    -kernel $BINARY \
    -nographic \
    -serial file:qemu_output.txt \
    -semihosting \
    -semihosting-config target=native,target=auto

# Check output for expected string
if grep -q "Hello, embedded!" qemu_output.txt; then
    echo "QEMU test PASSED"
    rm qemu_output.txt
else
    echo "QEMU test FAILED"
    cat qemu_output.txt
    exit 1
fi
```

## Common Pitfalls & Gotchas

1. **`#[cfg(test)]` vs `#[cfg(not(test))]` confusion**: If you use `#![no_std]` but need `std` for test mocks, wrap the mock module in `#[cfg(test)]`. The production code stays `no_std`. Forgetting this leads to "cannot find crate `std`" errors in release builds.

2. **QEMU peripheral models are not cycle-accurate**: Your UART polling loop might work on real hardware but hang in QEMU because the emulated peripheral flags behave differently. Always add a timeout or watchdog in test code. I use a simple loop counter that panics after 10,000 iterations.

3. **Semihosting conflicts with debug probes**: If you use semihosting for test output, you cannot simultaneously attach a hardware debugger (OpenOCD, JLink) because they share the same exception mechanism. Use `-serial file:` or `-serial stdio` for QEMU tests and reserve semihosting for hardware bring-up.

## Try It Yourself

1. **Add a mock for a GPIO output pin** — implement a `GpioWrite` trait with `set_high()` and `set_low()`. Write a host test that toggles the pin and verifies the sequence of states.

2. **Run your existing embedded project under QEMU** — pick a board supported by QEMU (e.g., `stm32f4-discovery`, `lm3s6965evb`). Build with the correct target and verify basic UART output appears on the host terminal.

3. **Set up a CI pipeline** — create a GitHub Actions workflow that runs `cargo test --lib` on push, and a separate job that runs the QEMU integration test script. Use `dtolnay/rust-toolchain` and `cargo install cargo-binutils` for the ARM target.

## Next Up

Tomorrow I'm diving into **Rust in the Linux Kernel: rust_module! Basics (v6.1+)** — we'll write a minimal kernel module using the new `rust_module!` macro, build it with `rustc_codegen_llvm`, and load it into a QEMU virtual machine running a custom kernel. No more bare metal, but still no user space.
