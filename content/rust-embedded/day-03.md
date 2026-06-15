---
title: "Day 03: no_std: Writing Embedded Rust Without the Standard Library"
date: 2026-06-15
tags: ["til", "rust-embedded", "no-std", "bare-metal"]
---

## What I Explored Today

Today I dove into the `no_std` environment — the foundation of every embedded Rust project. I learned how to configure a Rust project to run without the standard library, what `#![no_std]` actually disables, and how to set up a minimal bare-metal binary that compiles for a Cortex-M microcontroller. This is the first real step away from hosted Rust and into the world where you control every byte.

## The Core Concept

The Rust standard library (`std`) assumes an underlying operating system. It provides heap allocation, file I/O, networking, threads, and — critically — a global allocator backed by `malloc`. On a microcontroller with no OS, none of these exist. The `no_std` attribute strips away everything that depends on OS services, leaving only the core library (`core`) and the alloc library (if you bring your own allocator).

Why does this matter? Because `std` pulls in startup code that calls `main` with environment setup, unwinding support, and a runtime that expects `libc`. On a Cortex-M, your reset vector points directly to your entry point — there is no `libc` to initialize. Writing `no_std` means you take full responsibility for:

- **Panic behavior**: No stack unwinding, no backtrace. You define what happens on panic (usually a tight loop or a hardware reset).
- **Memory initialization**: No OS to zero BSS or copy data segments. You must do it yourself in the startup code.
- **No heap by default**: If you want `Vec`, `Box`, or `String`, you must provide a global allocator.

The `core` crate is always available. It gives you `core::iter`, `core::cell`, `core::cmp`, `core::ptr`, and most of the language primitives you rely on. The key difference: no `std::io`, no `std::fs`, no `std::thread`. For embedded work, you don't miss them — you replace them with register-level I/O and interrupt handlers.

## Key Commands / Configuration / Code

### 1. Minimal `no_std` Binary for Cortex-M

Create a new project with `cargo init` and replace `src/main.rs`:

```rust
// src/main.rs — minimal no_std binary for ARM Cortex-M
#![no_std]        // Remove the standard library
#![no_main]       // We define our own entry point, not the OS-style main

// Import the panic handler from the panic-halt crate
// This crate defines what happens on panic: it just loops forever
use panic_halt as _;

// Import the cortex-m-rt crate for the entry point and vector table
use cortex_m_rt::entry;

// The #[entry] attribute marks this as the reset handler
// It replaces the normal main function
#[entry]
fn main() -> ! {
    // The '!' return type means this function never returns
    // In embedded, main typically runs an infinite loop

    // Read the CPUID register to verify we're running
    let cpuid: u32;
    unsafe {
        // Direct register read using core::ptr::read_volatile
        // 0xE000_ED00 is the address of the CPUID register on Cortex-M
        cpuid = core::ptr::read_volatile(0xE000_ED00 as *const u32);
    }

    // Loop forever — no OS to return to
    loop {}
}
```

### 2. `Cargo.toml` Dependencies

```toml
[package]
name = "no_std_demo"
version = "0.1.0"
edition = "2021"

[dependencies]
# The minimal runtime for Cortex-M: vector table, entry point, stack init
cortex-m-rt = "0.7"

# Panic behavior: halt (loop forever) on panic
panic-halt = "0.2"

# Optional: access to Cortex-M peripherals
cortex-m = "0.7"

# We don't need a build target here — set it in .cargo/config.toml
```

### 3. `.cargo/config.toml` — Target and Linker

```toml
# .cargo/config.toml
[build]
# Target triple for Cortex-M3 (e.g., STM32F103)
target = "thumbv7m-none-eabi"

[target.thumbv7m-none-eabi]
# Use the GCC linker from the ARM toolchain
# Adjust path to your arm-none-eabi-gcc installation
rustflags = ["-C", "linker=arm-none-eabi-gcc"]
```

### 4. `memory.x` — Linker Script for Cortex-M

Create a file `memory.x` in the project root:

```ld
/* memory.x — defines flash and RAM layout */
MEMORY
{
  FLASH : ORIGIN = 0x08000000, LENGTH = 64K
  RAM   : ORIGIN = 0x20000000, LENGTH = 20K
}

/* Stack size for the main stack */
_stack_size = 1024;
```

Then reference it in `build.rs`:

```rust
// build.rs — copies memory.x to the linker
use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let out = &PathBuf::from(env::var_os("OUT_DIR").unwrap());
    fs::copy("memory.x", out.join("memory.x")).unwrap();
    println!("cargo:rustc-link-search={}", out.display());
    println!("cargo:rerun-if-changed=memory.x");
}
```

## Common Pitfalls & Gotchas

### 1. Forgetting `#![no_main]`
If you write `fn main()` without `#![no_main]`, the compiler expects a `main` function with the standard signature `fn main() -> ()`. On bare metal, there's no runtime to call it. You'll get linker errors about `__libc_init_array` or `_start`. Always use `#![no_main]` and the `#[entry]` attribute from `cortex-m-rt`.

### 2. Using `std` Types Without an Allocator
You cannot use `Vec`, `Box`, `String`, or `HashMap` without a global allocator. The compiler will complain about missing `#[global_allocator]`. If you need heap allocation, either:
- Use the `alloc` crate with a custom allocator (e.g., `cortex-m-alloc` or `embedded-alloc`).
- Or use fixed-size arrays and `heapless` data structures (my preferred approach for deterministic systems).

### 3. Panic Handler Missing
Without a panic handler, the linker will fail with `undefined reference to `rust_begin_unwind``. Always include a panic crate like `panic-halt`, `panic-abort`, or `panic-semihosting`. The `panic-halt` crate is the safest for production — it just loops forever, preventing undefined behavior.

## Try It Yourself

1. **Build and disassemble**: Create the project above, run `cargo build --release`, then use `arm-none-eabi-objdump -d target/thumbv7m-none-eabi/release/no_std_demo` to inspect the generated assembly. Find the `loop` instruction that implements the infinite loop.

2. **Add a panic handler**: Replace `panic-halt` with `panic-abort` (which calls `abort()`). Observe how the binary size changes. Then try `panic-semihosting` to output panic messages via the debugger.

3. **Read a GPIO register**: Add the `cortex-m` crate and use `cortex_m::peripheral::Peripherals::take()` to access the GPIO registers. Read the input data register of a pin and store it in a variable. Verify the code compiles and the register read is not optimized away (use `core::sync::atomic::compiler_fence` if needed).

## Next Up: Ownership & Borrowing — How It Prevents Embedded Bugs

Tomorrow I'll explore how Rust's ownership model catches use-after-free, double-free, and data races at compile time — bugs that plague C firmware. We'll look at how `&mut` references prevent aliasing in interrupt handlers and how the borrow checker eliminates entire classes of embedded bugs without runtime overhead.
