---
title: "Day 25: Ownership & Borrowing: How It Prevents Embedded Bugs"
date: 2026-07-07
tags: ["til", "rust-embedded", "ownership", "borrowing", "safety"]
---

## What I Explored Today

Today I dug deep into Rust's ownership and borrowing rules—not as abstract theory, but as a concrete bug-prevention mechanism for embedded systems. After years of debugging use-after-free in DMA buffers, accidental peripheral aliasing, and race conditions in interrupt handlers, I finally understand why Rust's approach is revolutionary for embedded. The borrow checker isn't a nuisance; it's a compile-time watchdog that catches the exact bugs that plague C firmware.

## The Core Concept

In C, you can have multiple pointers to the same memory, write to it from an interrupt and main loop simultaneously, and the compiler will happily generate broken code. Rust's ownership model enforces three rules at compile time:

1. **Each value has exactly one owner** at any time
2. **You can have either one mutable reference or any number of immutable references**, but not both
3. **References must always be valid** (no dangling pointers)

For embedded engineers, this translates directly to hardware safety. When you map a peripheral register to a memory address, Rust ensures only one piece of code can mutate it at a time. No more "I forgot to disable the interrupt before writing to UART->DR" bugs.

The key insight: ownership maps to resource exclusivity. A `DMA1` peripheral is a resource. If you pass a mutable reference to it into a function, the compiler guarantees no other code path touches it until that function returns. This is not a runtime check—it's zero-cost at runtime.

## Key Commands / Configuration / Code

Let's see ownership in action with a typical embedded pattern: a shared buffer between an interrupt handler and main loop.

```rust
// BAD: C-style thinking in Rust - won't compile
use core::cell::RefCell;

static SHARED_BUF: RefCell<[u8; 64]> = RefCell::new([0u8; 64]);

fn main() -> ! {
    // This would cause a panic at runtime if interrupt fires
    let mut buf = SHARED_BUF.borrow_mut();
    // Interrupt fires here, tries to borrow_mut() -> PANIC
    process_buffer(&mut buf);
    loop {}
}

fn process_buffer(data: &mut [u8]) {
    // Safe mutation, but only if no other borrow exists
    data[0] = 0xFF;
}
```

The `RefCell` gives runtime borrow checking, but the real power is compile-time checking with `&mut` references:

```rust
// GOOD: Compile-time guaranteed exclusive access
use cortex_m::interrupt::Mutex;
use core::cell::Cell;

// Static mutex for interrupt-safe sharing
static COUNTER: Mutex<Cell<u32>> = Mutex::new(Cell::new(0));

fn main() -> ! {
    // Critical section ensures exclusive access
    cortex_m::interrupt::free(|cs| {
        let counter = COUNTER.borrow(cs);
        counter.set(counter.get() + 1);
    });
    
    // The borrow checker prevents us from holding the reference
    // across an interrupt boundary
    loop {}
}

// Interrupt handler - also uses critical section
#[interrupt]
fn TIM2() {
    cortex_m::interrupt::free(|cs| {
        let counter = COUNTER.borrow(cs);
        counter.set(counter.get() + 1);
    });
}
```

Here's a more practical example: preventing accidental peripheral aliasing:

```rust
// Peripheral singleton pattern - ownership prevents duplication
pub struct Uart {
    regs: &'static mut uart::RegisterBlock,
}

impl Uart {
    // Only one mutable reference to UART registers can exist
    pub fn new() -> Self {
        // SAFETY: We promise this is the only instance
        let regs = unsafe { &mut *(0x4000_4400 as *mut uart::RegisterBlock) };
        Uart { regs }
    }
    
    pub fn write_byte(&mut self, byte: u8) {
        // Wait until TX buffer empty
        while self.regs.sr.read().txe().bit_is_clear() {}
        self.regs.dr.write(|w| w.dr().bits(byte));
    }
}

fn main() {
    let mut uart1 = Uart::new();
    // let mut uart2 = Uart::new(); // COMPILE ERROR: cannot borrow as mutable more than once
    
    uart1.write_byte(b'H');
}
```

## Common Pitfalls & Gotchas

**1. Holding references across yield points in async code**
When using `embassy` or other async executors, you cannot hold a mutable reference to a peripheral across an `.await`. The borrow checker will catch this, but new users often fight it. Solution: use `&mut` only within a single async block, or use `Cell`/`RefCell` for shared state.

**2. Forgetting that `&mut T` is exclusive, even for reads**
In C, you can have multiple readers of a register. In Rust, `&mut T` means exclusive access. If you need read-only access from multiple places, use `&T` (immutable reference). For peripherals with read-only status registers, always use `&` not `&mut`.

**3. The `static mut` trap**
`static mut` in Rust is `unsafe` and should be avoided. It bypasses ownership rules entirely. Use `Mutex` (from `cortex_m` or `critical_section`) or `Atomic` types instead. I've seen production code with `static mut` that had the exact same race conditions as C.

## Try It Yourself

1. **Reproduce a classic embedded bug**: Write a program that creates two mutable references to the same `static mut` buffer (using `unsafe`). Then try to fix it using `RefCell` and critical sections. Observe how the borrow checker prevents the unsafe version from compiling without explicit `unsafe` blocks.

2. **Implement a safe register accessor**: Create a struct that wraps a memory-mapped GPIO output register. Implement `set_high()` and `set_low()` methods that take `&mut self`. Then try to call both methods simultaneously from main and an interrupt handler—watch the compiler reject it.

3. **Build a one-shot timer with ownership**: Create a `OneShotTimer` struct that owns a hardware timer peripheral. Implement a `start()` method that takes `&mut self` and returns a `Timeout` token. The token should own the timer's state, preventing the timer from being reconfigured while a timeout is pending.

## Next Up

Tomorrow: **Lifetimes in Embedded: Static References & Peripherals** — We'll explore how Rust's lifetime system guarantees that references to hardware registers and static data are always valid, and how `'static` lifetimes interact with interrupt handlers and DMA transfers.
