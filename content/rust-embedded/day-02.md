---
title: "Day 02: Rust Toolchain for Embedded: rustup, targets & cargo"
date: 2026-06-14
tags: ["til", "rust-embedded", "rustup", "cargo", "targets"]
---

## What I Explored Today

Today I dove into the Rust toolchain specifically configured for embedded development. While `rustup` and `cargo` are familiar from desktop Rust, embedded work requires cross-compilation targets, linker scripts, and a fundamentally different approach to building binaries. I set up a complete toolchain for ARM Cortex-M development, learned how `rustup target add` works under the hood, and configured `cargo` to produce binaries that actually run on bare metal.

## The Core Concept

The key insight is that embedded Rust is always cross-compilation. Your host machine (x86_64, aarch64) runs the compiler, but the output must target a completely different CPU architecture. This is where **target triples** come in — they describe three things: the CPU architecture, the vendor, and the operating system (or lack thereof).

For embedded, we use targets like `thumbv7em-none-eabihf`. Let's break that down:
- `thumbv7em` — ARM Cortex-M4/M7 with Thumb-2 instruction set and hardware multiply
- `none` — no operating system (bare metal)
- `eabihf` — Embedded Application Binary Interface, hardware floating-point

Without the correct target, `cargo build` will try to compile for your host system, producing a binary that's useless on a microcontroller. The toolchain must include:
1. A **cross-compiling Rust compiler** (the standard `rustc` can do this, but needs target support)
2. A **cross-compiling linker** (usually `arm-none-eabi-gcc` or `rust-lld`)
3. **Target-specific libraries** (core, compiler-builtins)

## Key Commands / Configuration / Code

### 1. Installing the target and toolchain components

```bash
# Add the ARM Cortex-M target (hard-float variant)
rustup target add thumbv7em-none-eabihf

# Install the LLVM-based linker (avoids needing arm-none-eabi-gcc)
rustup component add llvm-tools-preview

# Verify installed targets
rustup target list --installed
```

### 2. Minimal Cargo configuration for embedded

Create `.cargo/config.toml` in your project root:

```toml
# .cargo/config.toml
[build]
# Default target for this project (override with --target)
target = "thumbv7em-none-eabihf"

[target.thumbv7em-none-eabihf]
# Use LLVM's linker instead of GCC's
linker = "rust-lld"

# Pass flags to the linker
rustflags = [
    # Linker script for your specific MCU
    "-C", "link-arg=-Tlink.x",
    # Enable linker garbage collection
    "-C", "link-arg=--gc-sections",
]
```

### 3. Building and inspecting the output

```bash
# Build for the embedded target
cargo build --target thumbv7em-none-eabihf

# Check the file type — should say "ELF 32-bit LSB executable, ARM"
file target/thumbv7em-none-eabihf/debug/my_project

# Check the size breakdown
cargo size --target thumbv7em-none-eabihf -- -A

# Dump the symbol table to verify no stdlib references
cargo nm --target thumbv7em-none-eabihf | grep -i "std"
```

### 4. Minimal `no_std` binary structure

```rust
// src/main.rs
#![no_std]        // Don't link the standard library
#![no_main]       // Don't use the standard main interface

use core::panic::PanicInfo;

// Required for no_std — called on unrecoverable errors
#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}

// Entry point — called by the reset vector
#[no_mangle]
pub extern "C" fn main() -> ! {
    // Your embedded code here
    loop {}
}
```

## Common Pitfalls & Gotchas

### 1. Forgetting `#![no_std]` and `#![no_main]`
Without these attributes, `rustc` will try to link `std`, which requires an operating system. The error message is cryptic: `error[E0463]: can't find crate for std`. Always start new embedded projects with these attributes at the crate root.

### 2. Wrong target triple for your hardware
Using `thumbv7em-none-eabihf` on a Cortex-M0+ (which lacks hardware floating-point) will produce illegal instruction exceptions. Check your MCU's core:
- Cortex-M0/M0+: `thumbv6m-none-eabi`
- Cortex-M3: `thumbv7m-none-eabi`
- Cortex-M4/M7 (no FPU): `thumbv7em-none-eabi`
- Cortex-M4/M7 (with FPU): `thumbv7em-none-eabihf`

### 3. Linker script missing or wrong
The `link.x` file tells the linker where to place code, data, and the vector table. Without it, your binary won't boot. Use the `cortex-m-rt` crate which provides a default `link.x` for your target:

```bash
cargo add cortex-m-rt
```

Then in `main.rs`:
```rust
use cortex_m_rt::entry;

#[entry]
fn main() -> ! {
    loop {}
}
```

## Try It Yourself

1. **Set up a new embedded project**: Create a new binary crate, add `thumbv7em-none-eabihf` as a target, configure `.cargo/config.toml` with the LLVM linker, and verify `cargo build` produces an ELF file.

2. **Inspect the binary**: Use `cargo size` and `cargo nm` on your built binary. Identify which symbols come from `core` vs. your code. Check that no `std` symbols appear.

3. **Experiment with targets**: Create a second project targeting `thumbv6m-none-eabi` (Cortex-M0). Compare the binary size and note the different instruction encoding by disassembling with `cargo objdump -- -d`.

## Next Up

Tomorrow we'll strip away the last training wheels and go fully **no_std: Writing Embedded Rust Without the Standard Library**. We'll explore what `core` provides, how to handle allocations without a heap, and why `#[panic_handler]` is your new best friend.
