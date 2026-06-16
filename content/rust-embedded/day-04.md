---
title: "Day 04: Ownership & Borrowing: How It Prevents Embedded Bugs"
date: 2026-06-16
tags: ["til", "rust-embedded", "ownership", "borrowing", "safety"]
---

## What I Explored Today

Today I dug into the core of Rust's safety guarantees: ownership and borrowing. Coming from C, I've spent years debugging use-after-free, double-free, and data races in interrupt handlers. Rust's ownership model isn't just academic—it's a compile-time firewall that eliminates entire classes of embedded bugs. I implemented a simple GPIO toggling example that would have been a data-race nightmare in C, and watched the compiler enforce correctness.

## The Core Concept

Ownership is Rust's solution to the memory management problem without a garbage collector. Every value has exactly one owner at any time. When the owner goes out of scope, the value is dropped. This is deterministic and predictable—critical for embedded systems where you can't afford GC pauses.

Borrowing lets you temporarily access a value without taking ownership. You can have either:
- One mutable reference (`&mut T`) — exclusive write access
- Many immutable references (`&T`) — shared read access

Never both at the same time.

Why does this matter for embedded? Consider a typical scenario: a DMA buffer shared between an interrupt handler and main loop. In C, you'd use volatile and pray. In Rust, the borrow checker ensures you can't write to the buffer while the DMA engine reads it, or read it while you're modifying it. This is enforced at compile time, not runtime.

## Key Commands / Configuration / Code

Let's see ownership in action with a simple embedded pattern: toggling an LED via a memory-mapped GPIO register.

```rust
// src/main.rs — Ownership prevents accidental reuse of peripherals
#![no_std]
#![no_main]

use cortex_m_rt::entry;
use panic_halt as _;

// Simulated GPIO register (real embedded would use PAC crate)
struct GpioPort {
    // Memory-mapped register at fixed address
    output: u32,
}

impl GpioPort {
    // Ownership: consuming self ensures only one instance exists
    fn new() -> Self {
        // In real code: unsafe { &*(0x40020_0014 as *const u32) }
        GpioPort { output: 0 }
    }

    // Borrowing: &mut self gives exclusive access to toggle
    fn toggle_pin(&mut self, pin: u32) {
        self.output ^= 1 << pin;  // XOR to toggle
    }
}

#[entry]
fn main() -> ! {
    // Ownership: gpio owns the peripheral
    let mut gpio = GpioPort::new();

    // Borrowing: &mut gpio — exclusive access
    gpio.toggle_pin(13);  // Toggle LED on pin 13

    // This would fail to compile:
    // let gpio2 = gpio;  // Move! gpio is no longer valid
    // gpio.toggle_pin(13);  // ERROR: use of moved value

    loop {
        // &mut gpio again — previous borrow ended
        gpio.toggle_pin(13);
        // Delay would go here
    }
}
```

Now, a real-world example showing how borrowing prevents data races in interrupt handlers:

```rust
// Ownership prevents shared mutable state in interrupts
use core::cell::RefCell;
use cortex_m::interrupt::{self, Mutex};

static SHARED_COUNTER: Mutex<RefCell<u32>> = 
    Mutex::new(RefCell::new(0));

fn main() {
    // Safe access pattern: critical section
    interrupt::free(|cs| {
        // cs (CriticalSection token) proves we're in a critical section
        let counter = SHARED_COUNTER.borrow(cs);
        *counter.borrow_mut() += 1;
    });
    // Borrow ends here — no way to hold reference across interrupt
}
```

The `Mutex` and `RefCell` pattern is how embedded Rust handles shared state. The `interrupt::free` closure ensures interrupts are disabled while we access the data. The borrow checker then ensures we can't leak that reference outside the critical section.

## Common Pitfalls & Gotchas

**1. Trying to share peripherals across functions**
In C, you'd pass a pointer to a GPIO register to multiple functions. In Rust, ownership means you can't just clone a peripheral. The solution: use `take()` methods from PAC crates that return an `Option<Peripheral>`. Only one `take()` succeeds—the rest get `None`. This prevents two drivers from configuring the same UART.

**2. Forgetting that `&mut` is exclusive**
You might think you can read a register while writing to it. Rust says no. If you have `&mut GpioPort`, you can't also have `&GpioPort`. This is correct behavior—reading a register you're writing to is undefined behavior in many architectures due to side effects.

**3. Lifetime elision confusion in interrupt handlers**
Newcomers often write:
```rust
// WRONG — borrow doesn't live long enough
static COUNTER: Mutex<RefCell<u32>> = ...;
fn bad_handler() {
    let mut c = COUNTER.borrow(&CriticalSection::new());
    // c is dropped here, but we try to use it later
}
```
The `CriticalSection` token must outlive the borrow. Always use `interrupt::free` to get a valid token.

## Try It Yourself

1. **Ownership transfer experiment**: Write a function that takes ownership of a `GpioPort` struct, toggles a pin, and returns it. Then try to use the original variable after the call. Observe the compiler error.

2. **Borrow checker challenge**: Create two functions—one that takes `&GpioPort` (read) and one that takes `&mut GpioPort` (write). Try calling both simultaneously in the same scope. Fix it by sequencing the calls.

3. **Interrupt-safe counter**: Implement a shared counter using `Mutex<RefCell<u32>>` that increments in an interrupt handler and reads in main. Verify the compiler prevents you from accessing the counter outside a critical section.

## Next Up

Tomorrow: **Lifetimes in Embedded: Static References & Peripherals**. We'll explore how Rust's lifetime system ensures that references to memory-mapped registers and static buffers are valid for exactly as long as needed—preventing dangling pointer bugs that plague firmware.
