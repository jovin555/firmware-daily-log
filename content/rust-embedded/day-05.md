---
title: "Day 05: Lifetimes in Embedded: Static References & Peripherals"
date: 2026-06-17
tags: ["til", "rust-embedded", "lifetimes", "static", "peripherals"]
---

## What I Explored Today

Today I dug into how Rust's lifetime system applies to embedded systems—specifically how `'static` lifetimes and reference semantics govern peripheral access. In bare-metal code, there's no OS or heap to manage memory, so the compiler's ability to guarantee that references to hardware registers remain valid is both a blessing and a constraint. I focused on understanding why peripherals are typically modeled as singleton resources with `'static` lifetimes, and how this prevents the kind of aliasing bugs that plague C firmware.

## The Core Concept

In embedded Rust, every peripheral (UART, GPIO, timer) maps to a fixed memory address in the microcontroller's address space. These addresses are valid for the entire program execution—they never move, never get deallocated. That makes them perfect candidates for `'static` references. But here's the subtlety: the borrow checker doesn't just care about *where* a reference points; it cares about *who* holds exclusive access.

The `'static` lifetime in embedded code doesn't mean "lives forever in heap memory" (there's no heap). It means "valid for the entire runtime of the program." When you write `let uart: &'static mut Uart = unsafe { &mut *(0x4000_1000 as *mut Uart) }`, you're telling the compiler: "This pointer is valid from power-on to power-off, and I'm taking exclusive mutable access for the rest of time."

This is why peripheral access crates (PACs) use `'static` references internally—they model hardware registers as global singletons. The borrow checker then enforces that you can't have two mutable references to the same UART at the same time, preventing the exact kind of race condition that happens when an ISR and main loop both write to the same register without synchronization.

## Key Commands / Configuration / Code

Let's look at how this works in practice. Here's a minimal example of safely accessing a GPIO peripheral using `'static` references:

```rust
// Target: ARM Cortex-M (e.g., STM32F4)
// Assumes GPIOA is at 0x4002_0000

use core::ptr;

// Define a register layout (simplified)
#[repr(C)]
struct GpioRegisters {
    moder: u32,   // 0x00
    otyper: u32,  // 0x04
    ospeedr: u32, // 0x08
    pupdr: u32,   // 0x0C
    idr: u32,     // 0x10
    odr: u32,     // 0x14
}

// The singleton pattern: only one mutable reference can exist
fn gpioa() -> &'static mut GpioRegisters {
    // SAFETY: 0x4002_0000 is the fixed base address for GPIOA
    // on this MCU. The pointer is valid for the entire program.
    unsafe { &mut *(0x4002_0000 as *mut GpioRegisters) }
}

fn main() -> ! {
    // First mutable borrow - OK
    let gpio = gpioa();
    gpio.moder = 0x5555_5555; // Set all pins as output
    
    // Uncommenting this would cause a compile error:
    // let gpio2 = gpioa(); // ERROR: cannot borrow `*gpio` as mutable more than once
    // gpio2.odr = 0x0001;
    
    loop {
        gpio.odr ^= 0x0001; // Toggle pin 0
        // gpio reference is dropped here, but since it's 'static,
        // the memory remains valid. The borrow checker just releases
        // the exclusive access for the next scope.
    }
}
```

Now, the real-world pattern using a PAC (Peripheral Access Crate) looks cleaner:

```rust
// Using the stm32f4xx-hal crate (simplified)
use stm32f4xx_hal::pac;

fn main() -> ! {
    // Take() returns an Option<&'static mut Peripheral>
    // It can only be called once per peripheral
    let peripherals = pac::Peripherals::take().unwrap();
    
    // peripherals.GPIOA is &'static mut GPIOA
    let gpioa = &peripherals.GPIOA;
    
    // The borrow checker now prevents:
    // let gpioa2 = &peripherals.GPIOA; // ERROR: already borrowed mutably
    
    // This is enforced at compile time - no runtime cost
    gpioa.odr.write(|w| w.bits(0x0001));
    
    loop {}
}
```

The `take()` function is a critical pattern. It uses an `Option` that starts as `Some(...)` and becomes `None` after the first call. Combined with `'static` lifetimes, this ensures that each peripheral can only be accessed from one code path at a time.

## Common Pitfalls & Gotchas

1. **Forgetting that `'static` doesn't mean thread-safe**: A `&'static mut T` reference is `Send` but not `Sync`. If you share it between threads (or between main and an ISR), you need proper synchronization. The compiler won't stop you from sending a `'static` mutable reference to an interrupt handler—you must use `Mutex` or `CriticalSection` manually.

2. **The `take()` pattern is one-shot**: If you call `Peripherals::take()` twice, the second call returns `None`. This is intentional—it prevents accidental aliasing—but it means you must store the peripherals in a global or pass them through your initialization chain. You can't re-acquire them later.

3. **Over-constraining with `'static` on function signatures**: When writing generic HAL code, resist the urge to slap `'static` on every reference parameter. Often you want `&'a mut T` where `'a` is the lifetime of the borrow, not the entire program. Using `'static` unnecessarily prevents the caller from using shorter-lived borrows.

## Try It Yourself

1. **Explore your MCU's memory map**: Find the datasheet for your target microcontroller. Identify the base addresses for three peripherals (e.g., UART, TIM, GPIO). Write a `struct` for each peripheral's register layout and create a `'static` reference function (like `gpioa()` above) for each.

2. **Break the borrow checker intentionally**: Write a function that tries to take two mutable references to the same peripheral. Observe the compiler error. Then fix it by using a scope or by passing the reference through a function that returns it.

3. **Implement a safe singleton**: Create a `Peripherals` struct that holds references to two different peripherals. Implement a `take()` method that returns `Option<&'static mut Self>` using a static `AtomicBool` flag. Verify that the second call returns `None`.

## Next Up

Tomorrow: **Peripheral Access Crate (PAC): Register-Level Access** — We'll dive into how PACs are generated from SVD files, how to read/write registers with type-safe bitfields, and why `read()`, `write()`, and `modify()` are safer than raw pointer arithmetic.
