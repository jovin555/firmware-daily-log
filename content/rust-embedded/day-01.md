---
title: "Day 01: Why Rust for Embedded? Memory Safety Without GC"
date: 2026-06-13
tags: ["til", "rust-embedded", "rust", "memory-safety", "embedded"]
---

## What I Explored Today

I spent the morning digging into why Rust is gaining serious traction in embedded systems—and it’s not just hype. The core promise is memory safety without a garbage collector, which is a game-changer for resource-constrained targets. I walked through the ownership model, looked at how it prevents use-after-free and buffer overflows at compile time, and verified that no runtime overhead is introduced. The result: you get the safety of a managed language with the performance and predictability of C.

## The Core Concept

Embedded systems have a hard constraint: no heap allocation after init, no GC pauses, and deterministic execution. C and C++ give you control but leave memory bugs as runtime landmines. Rust’s ownership system enforces three rules at compile time:

1. Each value has exactly one owner.
2. References are either shared (`&T`) or mutable (`&mut T`), never both.
3. References must always be valid (no dangling pointers).

Because these checks happen at compile time, there’s zero runtime cost. No reference counting, no mark-and-sweep, no stop-the-world. The borrow checker is effectively a static analyzer that guarantees memory safety without sacrificing control over layout or timing.

For embedded, this means you can safely share peripherals between interrupt handlers and main loops, pass buffers without copying, and never worry about double-free or buffer overflow—all while maintaining predictable latency.

## Key Commands / Configuration / Code

Let’s see the ownership model in action with a minimal embedded-style example. We’ll simulate a peripheral register that can only be written once.

```rust
// A simple peripheral that owns a hardware register
struct Led {
    // In real embedded, this would be a memory-mapped register
    pin: u8,
}

impl Led {
    // Consumes self: only one caller can turn on the LED
    fn turn_on(self) {
        // SAFETY: In real code, use volatile writes to a register address
        println!("LED on pin {} is ON", self.pin);
        // self is dropped here; cannot be used again
    }
}

fn main() {
    let led = Led { pin: 13 };
    led.turn_on();
    // Uncommenting the next line causes a compile error:
    // led.turn_on(); // error: use of moved value: `led`
}
```

This demonstrates ownership transfer. Once `turn_on` consumes `led`, the compiler prevents a second call—exactly what you want for a one-shot hardware operation like configuring a timer.

For shared access (e.g., a UART peripheral used by both main loop and interrupt), we use references:

```rust
struct Uart {
    baud_rate: u32,
}

impl Uart {
    // Shared reference: multiple readers allowed
    fn read_byte(&self) -> u8 {
        // In real code: read from data register
        0x41 // 'A'
    }

    // Mutable reference: exclusive write access
    fn write_byte(&mut self, byte: u8) {
        // In real code: write to data register
        println!("Wrote byte: {}", byte);
    }
}

fn main() {
    let mut uart = Uart { baud_rate: 115200 };

    // Multiple shared borrows are fine
    let r1 = &uart;
    let r2 = &uart;
    println!("Read: {}", r1.read_byte());
    println!("Read: {}", r2.read_byte());

    // Mutable borrow requires exclusive access
    let w = &mut uart;
    w.write_byte(0x42);
    // println!("Read: {}", uart.read_byte()); // ERROR: cannot borrow as immutable
}
```

The borrow checker prevents you from reading while writing—eliminating data races at compile time.

## Common Pitfalls & Gotchas

**1. Forgetting that `&mut` references are exclusive.**  
You cannot have a mutable reference and any other reference (shared or mutable) to the same data at the same time. This is intentional for safety, but it trips up developers used to C where you can pass pointers freely. In embedded, this often manifests when trying to access a peripheral from both an interrupt and main loop—you’ll need interior mutability patterns like `Mutex` or `Cell`.

**2. Assuming `no_std` means no allocator.**  
Rust’s standard library depends on heap allocation. In embedded, you typically use `#![no_std]` to exclude it. This means no `Vec`, `String`, or `Box` unless you bring your own allocator. Many embedded projects never allocate after boot, so you’ll work with fixed-size arrays and slices. The compiler enforces this—no accidental heap usage.

**3. Overlooking volatile access for memory-mapped I/O.**  
Rust’s compiler is aggressive about optimizing away reads/writes it considers dead. For hardware registers, you must use `core::ptr::read_volatile` and `write_volatile` (or the `cortex_m::peripheral` abstractions). A plain `*ptr = value` may be optimized out, leaving your hardware unconfigured.

```rust
// WRONG: may be optimized away
unsafe { *(0x4000_2000 as *mut u32) = 0x01; }

// RIGHT: compiler preserves the write
unsafe { core::ptr::write_volatile(0x4000_2000 as *mut u32, 0x01); }
```

## Try It Yourself

1. **Ownership transfer exercise:** Write a struct `GpioPin` with a method `set_high(self)` that consumes the pin. Try calling it twice and observe the compiler error. Then modify it to take `&self` and see what changes.

2. **Borrow checker challenge:** Create a struct `Sensor` with a `read()` method taking `&self` and a `calibrate()` method taking `&mut self`. In `main()`, try to call `read()` while a mutable borrow is active. Fix the code by reordering calls or using a scope.

3. **Volatile write test:** Write a small `no_std` program (you can run it on your host with `cargo run` if you use `core::ptr::write_volatile` to a stack variable) that writes to a raw pointer with and without `write_volatile`. Use `cargo asm` or inspect the generated assembly to see the difference.

## Next Up

Tomorrow, we’ll set up the Rust toolchain for embedded development: installing `rustup`, adding the correct target (e.g., `thumbv7em-none-eabihf` for Cortex-M4F), and configuring `cargo` with a `.cargo/config.toml` for cross-compilation. We’ll also build and flash a minimal blinky to verify everything works. See you then.
