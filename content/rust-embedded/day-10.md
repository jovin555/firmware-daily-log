---
title: "Day 10: RTIC Framework: Real-Time Interrupt-Driven Concurrency"
date: 2026-06-22
tags: ["til", "rust-embedded", "rtic", "concurrency", "tasks"]
---

## What I Explored Today

Today I dove into the **Real-Time Interrupt-driven Concurrency (RTIC)** framework, a powerful concurrency model for embedded Rust that replaces the traditional `#[interrupt]` and `#[entry]` approach with a declarative task-based system. RTIC provides compile-time guaranteed priority scheduling, resource management without locks, and a deterministic execution model — all without needing a heap or an RTOS. I built a multi-rate sensor sampling application with three tasks running at different priorities, and the experience fundamentally changed how I think about interrupt-driven design.

## The Core Concept

The core insight of RTIC is that **interrupts are tasks, and tasks should be statically analyzable**. Traditional interrupt handlers are fire-and-forget: you set a flag, clear the interrupt, and hope the main loop picks it up. This leads to race conditions, priority inversion, and hard-to-debug timing issues.

RTIC flips this by treating every interrupt as a **hardware task** with a fixed priority (determined by the NVIC priority number), and allowing you to define **software tasks** that run at any priority level. The framework uses Rust's type system to enforce that:

- **Shared resources** are accessed via a `lock()` method that disables all tasks with equal or lower priority, preventing data races at compile time.
- **Task scheduling** is deterministic — you know exactly when a task will run relative to others because priorities are static and the scheduler is non-preemptive for same-priority tasks.
- **No global state** — all mutable data is explicitly declared as a resource, and the compiler ensures you access it safely.

The real magic is that RTIC eliminates the need for mutexes, semaphores, or critical sections in the traditional sense. The `lock()` on a resource automatically handles priority-based access, and the framework guarantees deadlock freedom at compile time.

## Key Commands / Configuration / Code

First, add RTIC to your `Cargo.toml`. For a Cortex-M target (e.g., STM32, nRF):

```toml
[dependencies]
cortex-m = "0.7"
cortex-m-rt = "0.7"
rtic = "2.1.1"
panic-halt = "0.2"
```

Here's a complete RTIC application that samples two sensors at different rates, with a high-priority button interrupt:

```rust
// src/main.rs
#![no_std]
#![no_main]

use panic_halt as _;

#[rtic::app(device = cortex_m::Peripherals, dispatchers = [SYS_TICK])]
mod app {
    use cortex_m::asm;
    use rtic::time::duration::Milliseconds;

    // Shared resources — accessed safely via lock()
    #[shared]
    struct Shared {
        sensor_a_reading: u16,
        sensor_b_reading: u16,
    }

    // Local resources — task-private, no locking needed
    #[local]
    struct Local {
        led_state: bool,
        button_debounce_counter: u8,
    }

    #[init]
    fn init(cx: init::Context) -> (Shared, Local, init::Monotonics) {
        // Initialize hardware (GPIO, timers, etc.)
        let _device = cx.device; // cortex_m::Peripherals

        // Start the 1ms software task (lowest priority)
        rtic::pend(rtic::export::Interrupt::SYS_TICK);

        (
            Shared {
                sensor_a_reading: 0,
                sensor_b_reading: 0,
            },
            Local {
                led_state: false,
                button_debounce_counter: 0,
            },
            init::Monotonics(), // No hardware timer monotonic in this example
        )
    }

    // Software task: runs every 10ms (priority 1 — lowest)
    #[task(priority = 1, schedule = [sensor_a_task])]
    fn sensor_a_task(cx: sensor_a_task::Context) {
        // Simulate reading sensor A (I2C/SPI would go here)
        let reading = 42u16;

        // Lock shared resource to write
        cx.shared.sensor_a_reading.lock(|val| *val = reading);

        // Reschedule: run again in 10ms
        cx.schedule.sensor_a_task(
            cx.scheduled + Milliseconds(10u32)
        ).ok();
    }

    // Software task: runs every 50ms (priority 2 — higher than sensor_a)
    #[task(priority = 2, schedule = [sensor_b_task])]
    fn sensor_b_task(cx: sensor_b_task::Context) {
        let reading = 100u16;

        cx.shared.sensor_b_reading.lock(|val| *val = reading);

        cx.schedule.sensor_b_task(
            cx.scheduled + Milliseconds(50u32)
        ).ok();
    }

    // Hardware task: triggered by external interrupt (priority 3 — highest)
    #[task(binds = EXTI0, priority = 3)]
    fn button_interrupt(cx: button_interrupt::Context) {
        // Access local resource without lock
        cx.local.button_debounce_counter = 5;

        // Read both sensor values atomically (locks are nested safely)
        let (a, b) = cx.shared.lock(|s| {
            (s.sensor_a_reading, s.sensor_b_reading)
        });

        // Toggle LED based on sensor values
        if a > b {
            cx.local.led_state = !cx.local.led_state;
        }
    }

    // Idle task: runs when nothing else is pending
    #[idle]
    fn idle(_cx: idle::Context) -> ! {
        loop {
            asm::wfi(); // Wait for interrupt
        }
    }
}
```

The `dispatchers = [SYS_TICK]` attribute tells RTIC which interrupt to use for dispatching software tasks. You can list multiple interrupts to support more priority levels.

## Common Pitfalls & Gotchas

1. **Priority inversion via resource locking**: While RTIC prevents data races, it doesn't prevent a low-priority task from holding a lock that a high-priority task needs. The high-priority task will be blocked until the low-priority task releases the lock. Keep critical sections inside `lock()` as short as possible — ideally just a single read or write.

2. **Forgetting to reschedule periodic tasks**: RTIC tasks don't automatically repeat. If you define a `schedule` attribute, you must explicitly call `cx.schedule.task_name()` at the end of the handler. Miss this, and the task runs exactly once. I wasted 30 minutes debugging why my sensor task stopped after the first iteration.

3. **Stack overflow with deep nesting**: RTIC tasks each get their own stack frame, but the total stack usage is the sum of all task stacks plus the main stack. If you have many priority levels and deeply nested preemptions, you can overflow. Use `rtic::export::run()` or a stack analyzer to check. For Cortex-M, the default stack size is 256 bytes per task — bump it with `#[task(priority = 1, stack = 512)]` if you see hard faults.

## Try It Yourself

1. **Add a third task**: Create a `heartbeat_task` at priority 1 that toggles an LED every 500ms. Use a local `bool` for the LED state. Observe how it gets preempted by higher-priority tasks.

2. **Measure task timing**: Add a monotonically increasing counter (use `rtic::time::Monotonic` with a hardware timer) and log the actual execution time of each task. Compare with the scheduled period — you'll see jitter from priority preemption.

3. **Implement a software timer**: Instead of scheduling tasks periodically, create a one-shot task that starts a 100ms delay, then schedules a second task. This simulates a timeout or debounce pattern.

## Next Up

Tomorrow: **Embassy: Async/Await for Embedded Rust** — we'll explore how Embassy brings Rust's async/await to bare-metal embedded, providing cooperative multitasking with zero-cost futures, async I/O, and a runtime that runs on a single stack. We'll compare it head-to-head with RTIC and see when each framework shines.
