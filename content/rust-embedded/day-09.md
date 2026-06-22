---
title: "Day 09: Interrupt Handlers in Rust: cortex-m & RTIC"
date: 2026-06-22
tags: ["til", "rust-embedded", "interrupts", "cortex-m", "rtic"]
---

## What I Explored Today

Today I dove into interrupt handling on Cortex-M microcontrollers using Rust. While polling loops work for trivial examples, real embedded systems need interrupt-driven I/O to meet timing constraints and reduce power consumption. I explored the `cortex-m-rt` crate's interrupt infrastructure, then got my first taste of the Real-Time Interrupt-driven Concurrency (RTIC) framework. The contrast between raw interrupt service routines (ISRs) and RTIC's structured approach is night and day.

## The Core Concept

Interrupts are the backbone of responsive embedded systems. When an external event (GPIO edge, timer overflow, UART byte received) occurs, the CPU suspends normal execution, saves context, and jumps to a predefined handler address. On Cortex-M, this is vectored interrupt handling — each interrupt source has a fixed entry in the vector table.

The challenge in Rust is safety. Interrupt handlers run in a context where the borrow checker can't protect you — they can preempt any normal code, including other interrupt handlers. A shared variable accessed by both `main()` and an ISR is a data race waiting to happen. The `cortex-m-rt` crate provides the `#[interrupt]` attribute macro, but you're responsible for synchronization. RTIC elevates this by providing a compile-time checked framework for resource sharing and priority-based scheduling.

## Key Commands / Configuration / Code

### 1. Raw Interrupt Handler with `cortex-m-rt`

First, set up a project with the standard Cortex-M dependencies:

```toml
# Cargo.toml
[dependencies]
cortex-m = "0.7.7"
cortex-m-rt = "0.7.3"
cortex-m-semihosting = "0.5.0"
panic-halt = "0.2.0"

[features]
default = ["cortex-m-rt/device"]
```

A simple GPIO interrupt handler for an STM32F4:

```rust
// src/main.rs
#![no_std]
#![no_main]

use cortex_m::asm;
use cortex_m_rt::entry;
use panic_halt as _;

// Assume a PAC (Peripheral Access Crate) is used
use stm32f4xx_hal as hal;

// Shared state — must be protected
static mut COUNTER: u32 = 0;

#[entry]
fn main() -> ! {
    let dp = hal::stm32::Peripherals::take().unwrap();
    let mut rcc = dp.RCC.constrain();
    let mut gpioa = dp.GPIOA.split(&mut rcc.ahb1);

    // Configure PA0 as falling-edge interrupt
    let mut button = gpioa.pa0.into_pull_down_input();
    button.make_interrupt_source(&mut dp.SYSCFG);
    button.enable_interrupt(&mut dp.EXTI);
    button.trigger_on_edge(&mut dp.EXTI, hal::gpio::Edge::Falling);

    // Enable the interrupt in NVIC
    unsafe {
        cortex_m::peripheral::NVIC::unmask(hal::stm32::Interrupt::EXTI0);
    }

    loop {
        asm::wfi(); // Wait for interrupt
    }
}

// Interrupt handler — note the naming convention
#[interrupt]
fn EXTI0() {
    unsafe {
        COUNTER += 1;
        // Clear the pending bit (peripheral-specific)
        // Usually done via the EXTI peripheral's PR register
    }
}
```

**Key points:**
- The handler name must match the interrupt name in the PAC's `Interrupt` enum
- `static mut` is required for shared state, but it's `unsafe` to access
- You must manually clear the interrupt pending flag

### 2. RTIC: The Better Way

RTIC (Real-Time Interrupt-driven Concurrency) eliminates the `unsafe` and provides priority-based scheduling. Add to `Cargo.toml`:

```toml
[dependencies]
rtic = "2.1.1"
cortex-m = "0.7.7"
cortex-m-rt = "0.7.3"
```

```rust
// src/main.rs
#![no_std]
#![no_main]

use panic_halt as _;

#[rtic::app(device = stm32f4xx_hal::stm32, peripherals = true)]
mod app {
    use stm32f4xx_hal as hal;

    // Resources shared between tasks
    #[shared]
    struct Shared {
        counter: u32,
    }

    // Local resources (task-specific)
    #[local]
    struct Local {
        button: hal::gpio::Pin<'A', 0, hal::gpio::Input>,
    }

    #[init]
    fn init(cx: init::Context) -> (Shared, Local) {
        let dp = cx.device;
        let mut rcc = dp.RCC.constrain();
        let gpioa = dp.GPIOA.split(&mut rcc.ahb1);

        let mut button = gpioa.pa0.into_pull_down_input();
        button.make_interrupt_source(&mut dp.SYSCFG);
        button.enable_interrupt(&mut dp.EXTI);
        button.trigger_on_edge(&mut dp.EXTI, hal::gpio::Edge::Falling);

        // RTIC automatically enables the interrupt in NVIC
        (Shared { counter: 0 }, Local { button })
    }

    // Interrupt task — runs when EXTI0 fires
    #[task(binds = EXTI0, shared = [counter], local = [button])]
    fn button_press(cx: button_press::Context) {
        // Safe access to shared resource
        cx.shared.counter.lock(|c| *c += 1);

        // Clear interrupt flag through local resource
        cx.local.button.clear_interrupt_pending_bit();
    }

    // Idle task (lowest priority)
    #[idle]
    fn idle(_: idle::Context) -> ! {
        loop {
            cortex_m::asm::wfi();
        }
    }
}
```

**What RTIC gives you:**
- `#[shared]` resources with compile-time checked lock-based access
- `#[local]` resources that are exclusive to a task
- Priority-based preemption (higher priority tasks preempt lower ones)
- Automatic NVIC configuration and interrupt enabling

## Common Pitfalls & Gotchas

### 1. Forgetting to Clear the Interrupt Pending Flag
The most common bug. On Cortex-M, the NVIC latches the interrupt request. If you don't clear the peripheral's pending flag in the handler, the interrupt fires again immediately upon return. Your handler becomes a tight loop. Always check the reference manual for the correct register (e.g., `EXTI->PR` on STM32).

### 2. Data Races with `static mut`
Using `static mut` in raw interrupt handlers is a ticking time bomb. If a higher-priority interrupt preempts a lower-priority one and both access the same variable, you get undefined behavior. RTIC's `lock()` API on shared resources disables interrupts of equal or lower priority during the critical section, preventing this.

### 3. Stack Overflow from Deep Interrupt Nesting
Cortex-M supports nested interrupts by default. If you have a chain of high-priority interrupts, each one consumes stack space for its context save. Without careful stack sizing, you can overflow into adjacent memory regions. RTIC helps by analyzing the task graph and suggesting minimum stack sizes, but you still need to account for worst-case nesting depth.

### 4. Incorrect Handler Naming
In raw `cortex-m-rt`, the handler function name must exactly match the interrupt name in the PAC's vector table. A typo like `EXTI0` vs `EXTI0_IRQ` means your handler never gets linked — the default handler (usually an infinite loop) runs instead. RTIC's `binds = EXTI0` attribute catches this at compile time.

## Try It Yourself

1. **Raw ISR with Atomic Counter**: Modify the raw ISR example to use `core::sync::atomic::AtomicU32` instead of `static mut`. Verify that the compiler no longer requires `unsafe` for the counter access. Measure the overhead with a logic analyzer.

2. **RTIC Priority Inversion**: Create two RTIC tasks: one at priority 1 that toggles an LED every 100ms, and one at priority 2 that writes to a UART. Add a shared resource. Observe how the high-priority task preempts the low-priority one, and how `lock()` prevents the low-priority task from being interrupted while accessing the resource.

3. **Interrupt Latency Measurement**: Use the Cortex-M DWT cycle counter to measure the time from interrupt assertion to first instruction in the handler. Compare raw `cortex-m-rt` vs RTIC. What's the overhead of RTIC's resource locking?

## Next Up

Tomorrow, we'll fully commit to RTIC and explore its real-time capabilities: software tasks, message passing, and the timer queue. We'll build a multi-rate control system with tasks running at 1kHz, 100Hz, and 10Hz, all safely sharing sensor data through RTIC's resource management. **RTIC Framework: Real-Time Interrupt-Driven Concurrency** — where we stop fighting the borrow checker and start shipping reliable firmware.
