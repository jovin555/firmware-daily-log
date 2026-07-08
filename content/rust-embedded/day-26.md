---
title: "Day 26: Lifetimes in Embedded: Static References & Peripherals"
date: 2026-07-08
tags: ["til", "rust-embedded", "lifetimes", "static", "peripherals"]
---

## What I Explored Today

Today I dug into how Rust's lifetime system interacts with embedded systems—specifically, the `'static` lifetime and how it governs access to memory-mapped peripherals. On a microcontroller, peripherals like USART, GPIO, and timers live at fixed memory addresses that are valid for the entire program execution. But Rust's borrow checker doesn't automatically know that. I spent the afternoon understanding why `&'static mut` references are the idiomatic way to represent these hardware registers, and how the `cortex-m` and `riscv` crates use them to enforce single-owner access at compile time—preventing the exact kind of aliasing bugs that plague C firmware.

## The Core Concept

In embedded Rust, every peripheral is a singleton. There is exactly one USART1, one TIM2, one GPIOA. If two parts of your code both think they own the same UART, you get race conditions, corrupted registers, or silent hangs. The borrow checker prevents this, but only if we give it the right lifetime information.

The key insight: peripherals live at fixed memory addresses that are valid from `reset` to `power-off`. That makes them `'static`—they exist for the entire program duration. But `&'static T` is immutable, and we need to mutate registers. So we reach for `&'static mut T`, which gives us exclusive, permanent access to the hardware.

The `cortex_m::Peripherals::take()` method (and equivalents in other HALs) returns an `Option` that can only be called once. Internally, it uses a `static mut` flag and `unsafe` to hand out a `&'static mut` reference to each peripheral. After the first call, `take()` returns `None`. This pattern—often called the "singleton pattern" or "take pattern"—ensures that only one part of your program can ever hold a mutable reference to a given peripheral.

Why not just use `static mut` directly? Because `static mut` is inherently unsafe to read or write—the compiler can't prove you aren't creating aliases. By wrapping it in a safe `take()` API, we move the `unsafe` to a single, audited location and expose a safe, borrow-checker-verified interface to the rest of the code.

## Key Commands / Configuration / Code

Here's the canonical pattern for peripheral singletons, as seen in the `cortex-m` crate:

```rust
// This is what cortex_m::Peripherals::take() does internally
use core::cell::UnsafeCell;

// A wrapper that holds a &'static mut to the peripheral registers
pub struct Peripheral {
    // In real HALs, this is a pointer to a register block struct
    registers: UnsafeCell<u32>,
}

// SAFETY: Only one instance ever exists, guaranteed by take()
unsafe impl Send for Peripheral {}
unsafe impl Sync for Peripheral {}

impl Peripheral {
    pub fn new() -> Option<&'static mut Self> {
        // Static flag ensures single instantiation
        static mut TAKEN: bool = false;
        static mut PERIPHERAL: Peripheral = Peripheral {
            registers: UnsafeCell::new(0),
        };

        unsafe {
            if TAKEN {
                None
            } else {
                TAKEN = true;
                Some(&mut PERIPHERAL) // &'static mut is inferred
            }
        }
    }

    pub fn write(&mut self, val: u32) {
        unsafe { *self.registers.get() = val; }
    }
}

// Usage in main: only one mutable reference ever exists
fn main() -> ! {
    // This works
    let p = Peripheral::new().unwrap();
    p.write(0xDEAD);

    // This won't compile - p is still borrowed
    // let p2 = Peripheral::new(); // compile error: p is still alive

    loop {}
}
```

For a real-world example, here's how you'd use the `stm32f4xx_hal` crate:

```rust
use stm32f4xx_hal::{
    pac::Peripherals,
    prelude::*,
    serial::{config::Config, Serial},
};

fn main() -> ! {
    // take() returns Option<Peripherals>, can only be called once
    let dp = Peripherals::take().unwrap();

    // dp.USART1 is &'static mut USART1 — exclusive access
    let serial = Serial::new(
        dp.USART1,
        (dp.PA9, dp.PA10), // TX, RX pins
        Config::default(),
    );

    // If we tried to call Peripherals::take() again:
    // let dp2 = Peripherals::take(); // returns None at runtime

    loop {}
}
```

The borrow checker enforces that `dp` lives for the entire `main` function—you can't drop it and re-acquire it. This means all peripheral access is rooted in a single `take()` call at the start of your program.

## Common Pitfalls & Gotchas

1. **Forgetting that `take()` returns `Option`** — Many beginners unwrap blindly. If you accidentally call `take()` twice (e.g., in an interrupt handler and main), the second call returns `None` and your code panics. Always handle the `None` case, or structure your code so `take()` is called exactly once at initialization.

2. **Trying to store peripherals in `static` variables** — You cannot put `&'static mut` references into a `static` because that would create a second mutable reference. Instead, pass peripherals as function arguments or use `RefCell`/`Mutex` inside a `static` for shared access (covered in a future post on critical sections).

3. **Confusing `'static` with heap allocation** — On embedded systems, `'static` doesn't mean "allocated on the heap." It means "valid for the entire program lifetime." A `'static` reference can point to a stack variable that never goes out of scope (like `main`'s locals), or to a memory-mapped peripheral address. The borrow checker doesn't care where the memory lives, only that the reference is valid forever.

## Try It Yourself

1. **Trace the singleton pattern**: Open the `cortex-m` crate source (or your MCU's PAC) and find the `take()` implementation. Identify the `static mut` flag and the `unsafe` block that creates the `&'static mut` reference. Write a comment explaining each line.

2. **Break the borrow checker**: Write a program that calls `Peripherals::take()` twice in the same function. Observe the compiler error. Then, try to store the result in a `static` variable—note the error about `deref` and `Sync`.

3. **Build a safe wrapper**: Create a simple peripheral abstraction (e.g., for an LED on GPIO pin 13) that uses the singleton pattern. Implement `new() -> Option<&'static mut Self>` and a `toggle()` method. Verify that you cannot create two mutable references to the same LED.

## Next Up

Tomorrow we dive into **Peripheral Access Crates (PAC): Register-Level Access** — we'll look at how PACs generate type-safe register maps from SVD files, how to read/modify/write individual bitfields using `modify()`, and why `unsafe` is required for raw register access even in the safest HALs.
