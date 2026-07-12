---
title: "Day 03: Setting Up Rust + Zephyr: zephyr-rust Crate & Toolchain"
date: 2026-07-12
tags: ["til", "rust-zephyr-nrf54", "zephyr-rust", "toolchain"]
---

## What I Explored Today

Today I dove into the `zephyr-rust` crate—the official Rust-to-Zephyr binding layer—and the toolchain plumbing required to compile Rust code for the nRF54LM20. After yesterday's successful Zephyr build, I needed to understand how Rust code actually links into a Zephyr image, what the crate provides, and how to configure the cross-compilation toolchain so that `cargo build` produces a valid Zephyr module. I ended up with a working Rust static library that Zephyr's CMake build system can consume.

## The Core Concept

The `zephyr-rust` crate is not a standalone runtime. It's a thin FFI shim that gives Rust code access to Zephyr's kernel APIs (threads, semaphores, timers, logging) while respecting Zephyr's memory model and interrupt context. The key insight: Rust code compiles to a static library (`librust_app.a`), which Zephyr's linker pulls in as a built-in module. No separate bootloader, no Rust-based main loop—Zephyr's `main()` calls into Rust via an extern "C" entry point.

The toolchain challenge is that Rust's LLVM backend must target the same ARM Cortex-M33 (with FPU and TrustZone) as Zephyr's GCC. The `zephyr-rust` crate handles the ABI compatibility layer, but you still need the correct `target.json` specification for the nRF54LM20's exact CPU features. Without this, you'll get linker errors about mismatched FPU ABI or missing hardware intrinsics.

## Key Commands / Configuration / Code

### 1. Install the Rust Zephyr Target

First, I needed a custom target specification for the nRF54LM20. Zephyr's Rust integration provides a script:

```bash
# From the Zephyr workspace root
west rust target --target-dir /path/to/rust/targets
```

This generates `thumbv8m.main-none-eabihf.json` (the generic Cortex-M33 HF target). For the nRF54LM20's specific FPU and TrustZone settings, I created a custom target:

```json
// nrf54lm20.json
{
  "arch": "arm",
  "cpu": "cortex-m33",
  "data-layout": "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64",
  "executables": true,
  "features": "+fp-armv8d16sp-d16,+hwdiv,+strict-align",
  "llvm-target": "thumbv8m.main-none-eabihf",
  "max-atomic-width": 32,
  "os": "none",
  "relocation-model": "static",
  "target-pointer-width": "32",
  "vendor": "nordic"
}
```

### 2. Configure Cargo for Zephyr

In your Rust project's `.cargo/config.toml`:

```toml
[target.thumbv8m.main-none-eabihf]
rustflags = [
  "-C", "link-arg=-Tzephyr/linker.ld",      # Zephyr linker script
  "-C", "link-arg=-L/path/to/zephyr/build/zephyr",  # Zephyr built libs
  "-C", "link-arg=--specs=nano.specs",       # Newlib nano
  "-C", "linker=arm-zephyr-eabi-gcc",        # Zephyr's GCC as linker
  "-C", "panic=abort",
]

[build]
target = "thumbv8m.main-none-eabihf"
```

### 3. Minimal Rust Module with zephyr-rust

Create `src/lib.rs`:

```rust
//! Rust module that Zephyr will call into
#![no_std]

use zephyr_rust::prelude::*;

// Entry point called from Zephyr's main()
#[no_mangle]
pub extern "C" fn rust_main() {
    // Initialize Zephyr logging for this module
    log::info!("Rust module started on nRF54LM20");

    // Create a Zephyr thread from Rust
    let mut thread = Thread::new(
        "rust_worker",
        worker_task,
        Stack::new(&mut [0u8; 2048]),
        Priority::from(5),
    );
    thread.start();
}

fn worker_task() {
    loop {
        log::info!("Rust worker tick");
        k_sleep(K_MSEC(1000));
    }
}
```

### 4. Build the Rust Library

```bash
# Build the static library
cargo build --release

# Output: target/thumbv8m.main-none-eabihf/release/librust_app.a
```

### 5. Integrate into Zephyr's CMake

In your Zephyr application's `CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.20)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nrf54lm20_rust_app)

# Import the prebuilt Rust static library
add_library(rust_app STATIC IMPORTED)
set_target_properties(rust_app PROPERTIES
    IMPORTED_LOCATION ${CMAKE_CURRENT_SOURCE_DIR}/rust_app/target/thumbv8m.main-none-eabihf/release/librust_app.a
)

# Link it into the Zephyr image
target_link_libraries(app PRIVATE rust_app)
```

Then build normally with `west build -b nrf54lm20dk/nrf54lm20/cpuapp`.

## Common Pitfalls & Gotchas

### 1. FPU ABI Mismatch
The nRF54LM20 uses hardware float (single-precision). If your Rust target doesn't specify `+fp-armv8d16sp-d16`, the compiler will generate soft-float calls, and the linker will fail with "undefined reference to `__aeabi_fadd`". Always verify with `rustc --print cfg --target nrf54lm20.json | grep fpu`.

### 2. Zephyr Thread Stack Alignment
Zephyr expects thread stacks to be 8-byte aligned. If you allocate a Rust `Stack` on the heap (via `Box`), it may not meet this alignment. Always use a static `static mut` buffer or `Stack::new()` with a stack-allocated array. Misaligned stacks cause silent corruption in context switching.

### 3. Missing `zephyr-rust` Crate Features
The `zephyr-rust` crate has feature flags for different Zephyr subsystems. If you use `log::info!` without enabling the `logging` feature, you'll get compile errors about missing `Z_LOG2` macros. Add this to your `Cargo.toml`:

```toml
[dependencies]
zephyr-rust = { git = "https://github.com/zephyrproject-rtos/zephyr-rust", features = ["logging", "threads"] }
```

## Try It Yourself

1. **Generate the target spec**: Run `west rust target` and inspect the generated JSON. Compare it to the nRF54LM20's CPU features in the datasheet (Cortex-M33 with FPv5-SP-D16). Modify the `features` field to match.

2. **Build the minimal Rust library**: Create a new `cargo new --lib rust_app`, add the `zephyr-rust` dependency, and implement `rust_main()` that prints a log message. Build with `cargo build --release` and verify `librust_app.a` exists.

3. **Link into Zephyr**: Set up a Zephyr application with the CMake snippet above. Run `west build` and check that the linker output includes your Rust symbols (`nm build/zephyr/zephyr.elf | grep rust_main`).

## Next Up

Tomorrow we'll take this static library and actually flash it to the nRF54LM20 DK. I'll cover the `west flash` configuration for the nRF54L series, debugging with `west debug` (via JLink), and verifying that our Rust thread is alive by watching the log output over RTT. We'll also handle the common "Rust panic = Zephyr crash" scenario with a custom panic handler.
