---
title: "Day 24: no_std: Writing Embedded Rust Without the Standard Library"
date: 2026-07-06
tags: ["til", "rust-embedded", "no-std", "bare-metal"]
---

## What I Explored Today

Today I dug into the `no_std` environment — the foundation of every embedded Rust project that runs on bare metal. I've been using `#[no_std]` in my Cargo.toml for weeks, but I finally took the time to understand exactly what gets stripped away, what remains, and how to live without the OS abstractions we take for granted. The key insight: `no_std` isn't just "Rust without the standard library" — it's a different execution model where you control everything from heap allocation to panic behavior.

## The Core Concept

The Rust standard library (`std`) assumes an underlying operating system. It provides heap allocation via `Box`, `Vec`, and `String`, file I/O, networking, threading, and — critically — a global allocator backed by `malloc`. On a Cortex-M microcontroller with 64KB of RAM, none of these exist.

When you write `#![no_std]` in your crate root, you tell the compiler: "I will not use `std`." Instead, you get the **core library** (`core`), which provides language primitives like `Option`, `Result`, iterators, `Clone`, `Copy`, and arithmetic traits. Everything that doesn't require OS support lives in `core`.

But here's the practical reality: `core` has no heap allocator. No `Box`. No `Vec`. No `String`. No `println!`. No `panic!` that prints a message. You must provide your own allocator if you want dynamic memory, or — more commonly for embedded — you simply avoid it entirely and use fixed-size buffers and stack allocation.

The linker also changes. Without `std`, there's no `crt0` (C runtime startup) that sets up `.bss` and `.data` sections. You must write your own entry point and initialization code. This is where the `cortex-m-rt` crate comes in — it provides the vector table, reset handler, and memory initialization that `std` normally handles.

## Key Commands / Configuration / Code

**1. Minimal no_std binary for Cortex-M**

```rust
// src/main.rs
#![no_std]        // Don't link std
#![no_main]       // No main() — we define our own entry point

// Panic handler — required by no_std
// Without this, the linker will fail
#[panic_handler]
fn panic(_info: &core::panic::PanickInfo) -> ! {
    loop {}  // Halt on panic
}

// Entry point — called by reset vector
#[cortex_m_rt::entry]
fn init() -> ! {
    // Stack-allocated array — no heap needed
    let buffer: [u8; 256] = [0u8; 256];
    
    // Use core iterators — they work without alloc
    for (i, byte) in buffer.iter().enumerate() {
        // Write to a register or UART
        // (pseudocode: write_byte(*byte));
    }
    
    loop {}
}
```

**2. Cargo.toml for a no_std project**

```toml
[package]
name = "blinky-no-std"
version = "0.1.0"
edition = "2021"

[dependencies]
cortex-m = "0.7.7"
cortex-m-rt = "0.7.3"
panic-halt = "0.2.0"  # Simple halt-on-panic

# No std feature — critical!
[profile.release]
opt-level = "s"       # Optimize for size
lto = true
```

**3. Using a global allocator (when you must have heap)**

```rust
// Only if you really need dynamic allocation
// Requires a heap region defined in the linker script

use alloc::vec::Vec;
use alloc::boxed::Box;

// Declare a global allocator
#[global_allocator]
static ALLOCATOR: cortex_m::alloc::Heap = cortex_m::alloc::Heap::empty();

// Initialize in entry point
#[cortex_m_rt::entry]
fn init() -> ! {
    // Give the allocator 4KB of heap
    unsafe { ALLOCATOR.init(core::ptr::addr_of_mut!(HEAP_MEM) as usize, 4096); }
    
    // Now Vec works — but use sparingly!
    let mut data: Vec<u8> = Vec::new();
    data.push(42);
    
    loop {}
}
```

## Common Pitfalls & Gotchas

**1. Forgetting the panic handler**
The most common linker error: `undefined reference to `rust_begin_unwind``. Every `no_std` binary must define a `#[panic_handler]` function. The `panic-halt` crate is the simplest fix — it just loops forever. For debugging, use `panic-semihosting` or `panic-itm` to get panic messages out via debug probes.

**2. Accidentally pulling in std through dependencies**
A transitive dependency that uses `std` will break your build. Always check your dependency tree with `cargo tree`. Look for crates that don't declare `#![no_std]` compatibility. The `embedded-hal` ecosystem is safe; `rand` or `serde_json` often are not (without feature flags).

**3. Assuming `println!` works**
`println!` is a macro from `std` that writes to stdout. In `no_std`, you must implement your own output — typically by writing to a UART register or using a debug probe. The `rtt` (Real-Time Transfer) crate from Segger is a popular choice for debugging output without blocking.

**4. Heap fragmentation on small MCUs**
Even if you add a global allocator, dynamic allocation on a 64KB Cortex-M is risky. Fragmentation can quickly exhaust memory. Prefer fixed-size arrays and pool allocators. If you must use `Vec`, pre-allocate with `Vec::with_capacity()` to avoid repeated reallocations.

## Try It Yourself

1. **Strip std from an existing project**: Take a simple embedded project that uses `std` (maybe from an earlier day). Add `#![no_std]` and `#![no_main]`. Add a panic handler. Fix the compile errors. Notice how many things break — this shows you what `std` was providing.

2. **Implement a custom panic handler**: Write a panic handler that toggles an LED instead of halting. Use `core::panic::PanickInfo` to extract the panic message (if available) and blink a pattern indicating the error code.

3. **Measure the binary size difference**: Build a minimal blinky program with `std` (using `cargo new` with default settings) and the same program with `no_std`. Compare the `.text` section sizes using `cargo size`. The `no_std` version should be dramatically smaller — often 10x or more.

## Next Up

Tomorrow: **Ownership & Borrowing: How It Prevents Embedded Bugs** — we'll see how Rust's ownership model catches use-after-free, double-free, and data races at compile time, even in interrupt handlers and DMA transfers. No garbage collector, no runtime overhead — just the borrow checker keeping your hardware safe.
