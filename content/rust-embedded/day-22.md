---
title: "Day 22: Why Rust for Embedded? Memory Safety Without GC"
date: 2026-07-04
tags: ["til", "rust-embedded", "rust", "memory-safety", "embedded"]
---

## What I Explored Today

I've been writing C for embedded systems for over a decade, and I've lost count of the late-night debugging sessions chasing use-after-free bugs in interrupt handlers or buffer overflows in DMA transfers. Today I dove into Rust's ownership model and borrow checker to understand why it's gaining traction in embedded—specifically how it delivers memory safety guarantees without a garbage collector, which is a non-starter in resource-constrained environments. The key insight: Rust enforces memory safety at compile time through a static analysis system that has zero runtime overhead, making it ideal for microcontrollers with kilobytes of RAM.

## The Core Concept

Traditional embedded C relies on the programmer to manually manage memory—malloc/free, careful pointer arithmetic, and disciplined use of static buffers. One mistake, and you get undefined behavior: stack corruption, hard faults, or security vulnerabilities. Garbage-collected languages like Java or Go solve this but require a runtime that consumes RAM and CPU cycles, plus unpredictable pause times—unacceptable for real-time control.

Rust's approach is fundamentally different. Instead of runtime checks, it uses a **borrow checker** that analyzes ownership rules at compile time:

1. **Every value has exactly one owner** at any time
2. **References either borrow immutably (many) or mutably (one)**, never both simultaneously
3. **References must always be valid**—no dangling pointers

For embedded systems, this means:
- No garbage collector needed—memory is freed deterministically when the owner goes out of scope
- No data races in interrupt handlers—the borrow checker prevents shared mutable state without synchronization
- No buffer overflows—array bounds are checked at compile time or with optional runtime checks in debug builds

The compiler enforces these rules. If your code compiles, you've eliminated entire classes of bugs that plague embedded C projects.

## Key Commands / Configuration / Code

Let's see this in action with a concrete embedded example—managing a shared buffer between main loop and interrupt handler:

```rust
// core/src/main.rs
#![no_std]
#![no_main]

use core::cell::RefCell;
use cortex_m::interrupt::Mutex;

// A shared buffer protected by the interrupt system
static SHARED_DATA: Mutex<RefCell<[u8; 32]>> = Mutex::new(RefCell::new([0u8; 32]));

#[entry]
fn main() -> ! {
    // In the main context, we can access the buffer
    cortex_m::interrupt::free(|cs| {
        let buffer = SHARED_DATA.borrow(cs).borrow_mut();
        // buffer is a &mut [u8; 32] - safe to modify
        buffer[0] = 0xAA;
        // buffer dropped here, releasing the borrow
    });
    
    loop {
        // Main loop work
    }
}

// Interrupt handler - note: no data races possible
#[interrupt]
fn TIM2() {
    cortex_m::interrupt::free(|cs| {
        let buffer = SHARED_DATA.borrow(cs).borrow();
        // buffer is a &[u8; 32] - read-only
        let value = buffer[0];
        // If we tried buffer[0] = 0xBB, compiler would reject it
    });
}
```

**What's happening here:**
- `Mutex` provides safe access across interrupt boundaries
- `RefCell` gives interior mutability (needed because `Mutex` requires `Send`)
- The borrow checker ensures we never have simultaneous mutable access from main and interrupt
- No runtime overhead in release mode—the checks are optimized away

For a simpler ownership example without interrupts:

```rust
// Ownership in action - no GC needed
fn process_sensor_data(data: &mut [u16; 100]) {
    // data is borrowed mutably - we can modify it
    for sample in data.iter_mut() {
        *sample = sample.saturating_add(10);
    }
    // borrow ends here
}

fn main() -> ! {
    let mut buffer: [u16; 100] = [0; 100];
    
    // buffer is owned by main
    process_sensor_data(&mut buffer);  // borrow passes to function
    // buffer ownership returns here - no free needed
    
    // buffer is still valid - no dangling pointer
    let first = buffer[0];
}
```

## Common Pitfalls & Gotchas

1. **Interior mutability confusion**: Newcomers often try to use `RefCell` without `Mutex` in interrupt contexts, hitting compiler errors about `Send`/`Sync` traits. Remember: `RefCell` alone is `!Sync`—you need `Mutex` (from `cortex-m`) or `critical_section` for cross-interrupt safety.

2. **Stack overflow from recursive types**: Rust's ownership model encourages heap-free designs, but recursive data structures (linked lists, trees) require `Box` or `alloc` support. In `#![no_std]` without an allocator, you'll hit "recursive type has infinite size" errors. Use fixed-size arrays or `heapless` crate's `Vec` instead.

3. **Borrow checker fights with peripheral registers**: Memory-mapped I/O registers are inherently mutable and shared. The `volatile_register` crate or `svd2rust`-generated code uses `UnsafeCell` internally. Never try to wrap registers in `RefCell`—use the generated safe abstractions from your SVD file.

## Try It Yourself

1. **Ownership exercise**: Write a function that takes a `&mut [u8; 64]` and fills it with a pattern. Then call it from two places in your main loop. Observe the compiler error when you try to use the buffer after the mutable borrow is still active.

2. **Interrupt safety test**: Create a shared `u32` counter using `Mutex<RefCell<u32>>`. Increment it in a timer interrupt and read it in the main loop. Try adding a second interrupt that also writes to the same counter—the compiler will catch the potential data race.

3. **No-alloc linked list**: Implement a singly-linked list using `heapless::LinkedList` (from the `heapless` crate) with a fixed capacity. Push and pop items without any dynamic memory allocation, verifying that the borrow checker prevents dangling references.

## Next Up

Tomorrow, we'll set up the Rust toolchain for embedded development: installing `rustup`, adding the correct target triple (e.g., `thumbv7em-none-eabihf` for Cortex-M4F), configuring `.cargo/config.toml` with the right linker and runner, and building your first blinky project. No more guessing which GCC version you need—Rust's toolchain management is a breath of fresh air.
