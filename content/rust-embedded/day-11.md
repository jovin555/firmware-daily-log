---
title: "Day 11: Embassy: Async/Await for Embedded Rust"
date: 2026-06-23
tags: ["til", "rust-embedded", "embassy", "async", "await"]
---

## What I Explored Today

Today I dove into **Embassy**, the async/await framework that’s changing how we write embedded Rust. Instead of polling loops, busy-wait delays, and manual state machines, Embassy lets us write concurrent code that looks almost like synchronous code—but yields control when waiting for hardware. I built a simple async LED blinker and a UART echo server, and the difference in readability and maintainability is staggering. No more `loop { delay_ms(500); toggle(); }`—now it’s `loop { Timer::after(Duration::from_millis(500)).await; toggle().await; }`.

## The Core Concept

Traditional embedded firmware uses one of two patterns: **super-loop** (poll everything sequentially) or **RTOS** (preemptive threads with mutexes). Both have problems. Super-loops waste CPU cycles polling peripherals that aren’t ready. RTOS threads require careful priority management and can cause priority inversion or stack bloat.

Embassy solves this with **cooperative multitasking via async/await**. When a task calls `.await` on an operation that isn’t complete (e.g., a timer hasn’t fired, a byte hasn’t arrived on UART), the task *yields* control back to the executor. The executor then runs another ready task. No polling, no busy-wait, no preemption—just efficient, deterministic concurrency.

The key insight: Embassy provides **hardware-level abstractions** that implement Rust’s `Future` trait. When you `await` a `Timer`, the executor knows exactly when to wake the task. When you `await` a `Uart::read()`, the executor registers an interrupt handler that wakes the task when data arrives. This is zero-cost: the compiler generates state machines that are as efficient as hand-coded interrupt handlers.

## Key Commands / Configuration / Code

### Adding Embassy to Your Project

First, add the dependencies to `Cargo.toml`. For an STM32F4 example:

```toml
[dependencies]
embassy-executor = { version = "0.6", features = ["arch-cortex-m", "executor-thread"] }
embassy-time = { version = "0.3", features = ["tick-hz-32_768"] }
embassy-stm32 = { version = "0.1", features = ["stm32f411ce", "time-driver-tim2"] }
embassy-futures = "0.1"
```

The `executor-thread` feature gives us a single-threaded executor (perfect for most MCUs). The `tick-hz-32_768` configures the time driver for a 32.768 kHz RTC tick.

### Async Blinky (The Hello World of Embedded)

```rust
#![no_std]
#![no_main]

use embassy_executor::Spawner;
use embassy_stm32::gpio::{Level, Output, Speed};
use embassy_time::{Duration, Timer};
use {defmt_rtt as _, panic_probe as _};

#[embassy_executor::main]
async fn main(_spawner: Spawner) -> ! {
    let p = embassy_stm32::init(Default::default());
    let mut led = Output::new(p.PC13, Level::High, Speed::Low);

    loop {
        led.set_low().await;   // Turn on (active low)
        Timer::after(Duration::from_millis(500)).await;
        led.set_high().await;  // Turn off
        Timer::after(Duration::from_millis(500)).await;
    }
}
```

Notice: `#[embassy_executor::main]` transforms `main` into an async task. The `Spawner` parameter lets us spawn additional tasks. The `Output::set_low()` is async because on some chips, GPIO writes go through a bus that may be contended.

### Async UART Echo with Concurrent Tasks

```rust
#[embassy_executor::main]
async fn main(spawner: Spawner) -> ! {
    let p = embassy_stm32::init(Default::default());
    
    let mut usart = embassy_stm32::usart::Uart::new(
        p.USART1,
        p.PA10,  // RX
        p.PA9,   // TX
        NoPin,   // RTS
        NoPin,   // CTS
        Config::default(),
    ).unwrap();

    // Spawn a concurrent task
    spawner.spawn(blink_task()).unwrap();

    // Echo loop
    let mut buf = [0u8; 1];
    loop {
        usart.read(&mut buf).await.unwrap();
        usart.write(&buf).await.unwrap();
    }
}

#[embassy_executor::task]
async fn blink_task() -> ! {
    // ... same blinky logic as above
}
```

The `#[embassy_executor::task]` attribute marks a function as a spawnable task. Both tasks run concurrently on the same executor—no interrupts, no RTOS, just async/await.

## Common Pitfalls & Gotchas

### 1. Forgetting `#[embassy_executor::main]` or `#[embassy_executor::task]`

If you write `async fn main()` without the attribute, the compiler will complain about a missing `#[main]` attribute or the executor won’t be initialized. The attribute macro generates the entry point and initializes the executor. Without it, your async code never runs.

### 2. Blocking Inside an Async Task

Calling `block_on()` or a synchronous `delay_ms()` inside an async task will **block the entire executor**. All other tasks will starve. Use `Timer::after().await` for delays, and never call `nb::block!()` on Embassy futures. If you must run a blocking operation, wrap it in `embassy_futures::block_on()` only in a dedicated thread (if you have one).

### 3. Stack Size for Tasks

Each spawned task gets its own stack. By default, Embassy uses a small stack (e.g., 2 KB). If your task has large local variables or deep call chains, you’ll get a stack overflow. Use `#[embassy_executor::task(pool_size = 4, stack_size = 4096)]` to increase it. Debug with `defmt` logs to catch overflows early.

## Try It Yourself

1. **Convert a polling loop to async**: Take a simple firmware that polls a button in a loop and toggles an LED. Rewrite it using Embassy’s `Input` and `Timer`. Use `ExtiInput` for interrupt-driven button detection.

2. **Build a two-task system**: Create one task that blinks an LED at 1 Hz, and another that reads a potentiometer via ADC every 100 ms and prints the value over UART. Use `embassy_time::Ticker` for periodic tasks.

3. **Add a software timer**: Use `embassy_time::with_timeout()` to implement a watchdog: if the UART doesn’t receive a byte within 5 seconds, reset the device. Hint: `select!` from `embassy_futures` can race the UART read against a timeout.

## Next Up

Tomorrow we’ll peel back the curtain on **Embassy Executor & Tasks: Cooperative Multitasking**. We’ll look at how the executor schedules tasks, what happens when a task panics, and how to use `Spawner` and `Signal` for inter-task communication. You’ll learn the difference between `#[embassy_executor::main]` and manual executor creation, and when to use `pool_size` vs `stack_size`. See you then.
