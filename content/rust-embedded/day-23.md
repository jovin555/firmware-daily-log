---
title: "Day 23: Rust Toolchain for Embedded: rustup, targets & cargo"
date: 2026-07-05
tags: ["til", "rust-embedded", "rustup", "cargo", "targets"]
---

## What I Explored Today

Today I dug into the Rust toolchain specifically for embedded development. While `rustup`, `cargo`, and target triples are familiar from desktop Rust, embedded work demands a fundamentally different approach to toolchain management. I learned how to install cross-compilation targets, configure `.cargo/config.toml` for embedded workflows, and understand the precise relationship between host tools and target architecture.

## The Core Concept

The key insight is that embedded Rust development is **cross-compilation by default**. Your host machine (x86_64 Linux, aarch64 macOS, etc.) runs the compiler, but the output must execute on a completely different CPU architecture—typically ARM Cortex-M, RISC-V, or AVR. This means we need three things working in concert:

1. **A cross-compilation target** installed via `rustup` (e.g., `thumbv7em-none-eabihf` for Cortex-M4F)
2. **A linker** that understands the target's binary format (often `arm-none-eabi-gcc` or `rust-lld`)
3. **Cargo configuration** that tells the build system where to find these tools

The target triple format is critical: `arch-vendor-os-abi`. For embedded, we see patterns like `thumbv7em-none-eabihf`:
- `thumbv7em` = ARM Thumb-2 architecture, Cortex-M4/M7
- `none` = no operating system (bare metal)
- `eabihf` = Embedded ABI with hardware floating-point

Without understanding this triple, you'll waste hours on cryptic linker errors.

## Key Commands / Configuration / Code

### Installing a target

```bash
# List all available targets
rustup target list | grep thumb

# Install a specific embedded target
rustup target add thumbv7em-none-eabihf

# Verify installation
rustup target list --installed
```

### Minimal .cargo/config.toml for embedded

```toml
# .cargo/config.toml — project-level configuration
[build]
# Default target for cargo build (no --target needed)
target = "thumbv7em-none-eabihf"

[target.thumbv7em-none-eabihf]
# Use rust's built-in LLD linker for ARM
linker = "rust-lld"

# Alternative: use GCC linker (slower but more mature)
# linker = "arm-none-eabi-ld"

# Pass flags to the linker
rustflags = [
    "-C", "link-arg=-Tlink.x",      # Use memory layout script
    "-C", "link-arg=-Map=output.map", # Generate linker map
]
```

### Checking your toolchain

```bash
# Show current toolchain and active target
rustup show

# Check which compiler is actually being used
rustc --version --verbose
# Look for "host:" and "target:" lines

# Cross-compile a test
echo 'fn main() { println!("Hello"); }' > test.rs
rustc --target thumbv7em-none-eabihf test.rs
# This will fail with "error[E0463]: can't find crate for `std`"
# That's expected — embedded targets are no_std
```

### Creating a new embedded project

```bash
# Use cargo-generate with a template (recommended)
cargo install cargo-generate
cargo generate --git https://github.com/rust-embedded/cortex-m-quickstart

# Or manually
cargo new --bin my-embedded-project
cd my-embedded-project
# Add .cargo/config.toml as shown above
# Add to Cargo.toml:
cargo add cortex-m
cargo add cortex-m-rt
cargo add panic-halt
```

## Common Pitfalls & Gotchas

### 1. Forgetting to add the target

The most common mistake: running `cargo build` without installing the target first. You'll get:

```
error[E0463]: can't find crate for `core`
  = note: the `thumbv7em-none-eabihf` target may not be installed
```

Always run `rustup target add <triple>` before your first build. Add this to your project setup checklist.

### 2. Mixing up host and target tools

When you run `rustc` or `cargo`, they default to your **host** architecture. If you're on x86_64 and building for ARM, you must either:
- Set `target` in `.cargo/config.toml` (project-level)
- Pass `--target thumbv7em-none-eabihf` every time (error-prone)

I've seen teams waste days because someone ran `cargo build` without the target flag and got a working x86_64 binary that obviously couldn't run on the microcontroller.

### 3. Linker script mismatches

The `link.x` file referenced in `rustflags` must match your specific microcontroller. Using a Cortex-M4 linker script on a Cortex-M0 will produce a binary that either doesn't boot or corrupts memory. Always verify:

```bash
# Check which linker script is being used
cargo build --verbose 2>&1 | grep link.x
```

The output should show the path to your project's `memory.x` or the default from `cortex-m-rt`.

## Try It Yourself

1. **Install a target and inspect it**: Run `rustup target add thumbv6m-none-eabi` (for Cortex-M0). Then run `rustc --print target-spec-json --target thumbv6m-none-eabi` and examine the output. Note the `arch`, `cpu`, and `features` fields.

2. **Create a minimal embedded project**: Use `cargo new` to create a project, add `.cargo/config.toml` targeting `thumbv7em-none-eabihf`, and add `cortex-m`, `cortex-m-rt`, and `panic-halt` as dependencies. Build with `cargo build` and verify you get a `.elf` file in `target/thumbv7em-none-eabihf/debug/`.

3. **Debug a target mismatch**: Intentionally set the wrong target in `.cargo/config.toml` (e.g., `thumbv6m-none-eabi` for a Cortex-M4 project). Build and observe the error. Then fix it and confirm the build succeeds.

## Next Up

Tomorrow we tackle **no_std: Writing Embedded Rust Without the Standard Library**. We'll explore what happens when you remove `std`, how `core` and `alloc` replace it, and why `#[no_std]` is the foundation of every embedded Rust project. We'll also cover the `#[panic_handler]` and why your program needs one.
