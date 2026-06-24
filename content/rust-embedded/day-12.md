---
title: "Day 12: Embassy Executor & Tasks: Cooperative Multitasking"
date: 2026-06-24
tags: ["til", "rust-embedded", "executor", "tasks", "embassy"]
---

## What I Explored Today

Today I dove into the heart of Embassy's runtime: the async executor and task system. After weeks of bare-metal register manipulation and blocking drivers, I finally understand how Embassy enables truly concurrent embedded software without a traditional RTOS. I built a multi-task blinky that toggles LEDs at different rates, plus a button debouncer that runs alongside a serial logger — all without a single interrupt handler or `loop {}` in sight.

## The Core Concept

The fundamental shift here is from *preemptive* multitasking (where an RTOS scheduler forcibly swaps tasks) to *cooperative* multitasking (where tasks voluntarily yield at `await` points). Embassy's executor is a single-threaded, non-blocking scheduler that polls a set of async tasks, advancing each one only when it's ready to make progress.

Why does this matter for embedded? Because most embedded workloads are I/O-bound, not CPU-bound. A sensor reading task spends 99% of its time waiting for an I2C transaction to complete. With cooperative multitasking, that waiting time is reclaimed: while one task awaits an I2C response, the executor polls other tasks that *are* ready. No interrupts, no context-switch overhead, no stack-per-task memory waste.

The key insight is that Embassy's executor runs in a single `#[embassy_executor::main]` function, which never returns. Tasks are spawned onto this executor, and each task is a Rust async function that runs to completion (or loops forever). The executor's `run()` method is a tight loop that polls all spawned tasks, using a `Waker` mechanism to know which tasks are ready to make progress.

## Key Commands / Configuration / Code

Here's a minimal two-task blinky that demonstrates the pattern. I'm targeting an STM32F411 (Black Pill), but the concept is board-agnostic.

```rust
// Cargo.toml dependencies (relevant excerpt)
// [dependencies]
// embassy-executor = { version = "0.6", features = ["arch-cortex-m", "executor-thread"] }
// embassy-stm32 = { version = "0.2", features = ["stm32f411ce", "time-driver-tim2"] }
// embassy-time = { version = "0.3", features = ["tick-hz-32_768"] }

#![no_std]
#![no_main]

use embassy_executor::Spawner;
use embassy_stm32::gpio::{Level, Output, Speed};
use embassy_stm32::Peripherals;
use embassy_time::{Duration, Timer};
use panic_halt as _;

// Task 1: Blink LED1 at 500ms interval
#[embassy_executor::task]
async fn blink_red(led: Output<'static>) {
    let mut led = led;
    loop {
        led.set_high();
        Timer::after(Duration::from_millis(500)).await;
        led.set_low();
        Timer::after(Duration::from_millis(500)).await;
    }
}

// Task 2: Blink LED2 at 1s interval (slower)
#[embassy_executor::task]
async fn blink_green(led: Output<'static>) {
    let mut led = led;
    loop {
        led.set_high();
        Timer::after(Duration::from_secs(1)).await;
        led.set_low();
        Timer::after(Duration::from_secs(1)).await;
    }
}

#[embassy_executor::main]
async fn main(spawner: Spawner) {
    let p = embassy_stm32::init(Default::default());

    // Configure two GPIO pins as push-pull outputs
    let led_red = Output::new(p.PA5, Level::Low, Speed::Low);
    let led_green = Output::new(p.PB0, Level::Low, Speed::Low);

    // Spawn both tasks onto the executor
    spawner.spawn(blink_red(led_red)).unwrap();
    spawner.spawn(blink_green(led_green)).unwrap();

    // The main function returns, but the executor keeps running
}
```

Key observations:
- `#[embassy_executor::task]` marks an async function as a task that can be spawned.
- Tasks take ownership of their resources (e.g., `Output` pins). This is how Embassy enforces memory safety — no shared mutable state without explicit synchronization.
- `Timer::after(...).await` is the yield point. The task suspends, and the executor polls other tasks until the timer fires.
- `spawner.spawn(...)` returns a `Result` — if the executor's task pool is full, it returns an error.

## Common Pitfalls & Gotchas

1. **Task pool exhaustion by default.** Embassy's executor has a fixed-size task pool (default is 8 tasks). If you try to spawn more, `spawn()` returns `Err(NoCapacity)`. Fix: increase the pool size with `#[embassy_executor::task(pool_size = 16)]` on the task, or configure globally via `embassy-executor` features. I hit this on my third task and spent 20 minutes debugging.

2. **Borrowed resources across tasks.** You cannot share a `Peripherals` struct between tasks — it's `!Send` and `!Sync`. The solution is to split peripherals at initialization and pass owned handles to each task. If you need shared state, use `embassy_sync::Channel` or `Mutex` (which is different from `std::sync::Mutex` — it's designed for async contexts).

3. **Blocking inside an async task.** If you call `delay_ms(100)` from a blocking HAL inside an async task, you block the *entire executor*. All other tasks stop running. Always use `Timer::after(...).await` or embassy's non-blocking equivalents. I once accidentally used a blocking UART write and wondered why my LED task stopped blinking.

## Try It Yourself

1. **Three-task traffic light.** Build a state machine with three tasks: one for red LED (2s on, 1s off), one for yellow (1s on, 1s off), one for green (3s on, 1s off). Use `embassy_time::Ticker` for precise periodic timing instead of raw `Timer::after`.

2. **Button debouncer with channel.** Create a button-reading task that debounces using a 50ms timer, then sends a message over `embassy_sync::channel::Channel` to a second task that toggles an LED. This demonstrates inter-task communication without shared state.

3. **Executor capacity test.** Write a program that spawns 12 identical tasks (each blinking an LED at a unique rate). Observe the `spawn()` error when you exceed the pool. Then add `pool_size = 16` to one task and verify all 12 run.

## Next Up

Tomorrow: **Embassy Peripherals: GPIO, UART, SPI, I2C Async APIs**. I'll explore how Embassy wraps hardware peripherals in async interfaces — no more blocking `read()` calls or polling loops. We'll build a non-blocking sensor reader that reads from an I2C temperature sensor while simultaneously logging over UART, all in a single task.
