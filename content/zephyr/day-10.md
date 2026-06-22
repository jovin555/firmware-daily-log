---
title: "Day 10: Timers & Delayed Work: k_timer, k_work"
date: 2026-06-22
tags: ["til", "zephyr", "timers", "work-queue"]
---

## What I Explored Today

Today I dug into Zephyr's timer and delayed work primitives — `k_timer` and `k_work` — which are essential for scheduling periodic or one-shot actions without burning CPU cycles in busy loops. I've been relying on `k_sleep()` for delays, but that blocks the calling thread. These kernel objects let me schedule work to run in a different context, freeing up the current thread for other tasks. I tested both timer-driven callbacks and deferred work items on a work queue, and the difference in system responsiveness is dramatic.

## The Core Concept

The fundamental problem: embedded systems need to do things *later*, not *now*. Polling loops waste power and CPU time. Interrupts are immediate but must be short. Timers and work queues solve this by decoupling *when* something happens from *where* it runs.

**`k_timer`** is a kernel object that counts ticks and fires a callback when the count reaches zero. You configure it for one-shot or periodic mode. The callback runs in interrupt context (by default), so it must be fast and non-blocking. For heavier work, you use the timer to submit a work item instead.

**`k_work`** is a deferred execution primitive. You define a work item (a function + its arguments) and submit it to a work queue. The work queue is a dedicated thread that processes items sequentially. This moves your work out of interrupt context into thread context, where you can use mutexes, semaphores, and blocking calls safely.

The key insight: timers handle *timing*, work queues handle *execution context*. Combine them for robust, non-blocking designs.

## Key Commands / Configuration / Code

### Basic k_timer: One-shot and Periodic

```c
#include <zephyr/kernel.h>

// Timer callback — runs in interrupt context, keep it short
void my_timer_handler(struct k_timer *timer_id)
{
    // Do NOT block here. Use k_work_submit() for heavy work.
    printk("Timer fired at %lld ms\n", k_uptime_get());
}

// Define and initialize a timer
K_TIMER_DEFINE(my_timer, my_timer_handler, NULL);

void start_example(void)
{
    // One-shot: fire after 500 ms
    k_timer_start(&my_timer, K_MSEC(500), K_NO_WAIT);

    // Periodic: fire every 1000 ms, first after 200 ms
    k_timer_start(&my_timer, K_MSEC(200), K_MSEC(1000));

    // Stop the timer
    k_timer_stop(&my_timer);

    // Query remaining time
    k_timeout_t remaining = k_timer_remaining_get(&my_timer);
    printk("Remaining: %lld ms\n", k_ticks_to_ms_near32(remaining.ticks));
}
```

### k_work: Deferred Work on System Work Queue

```c
#include <zephyr/kernel.h>

// Work handler — runs in thread context, can block
void my_work_handler(struct k_work *work)
{
    printk("Work executed at %lld ms\n", k_uptime_get());
    // Safe to take mutex, sleep, etc.
    k_sleep(K_MSEC(10));
}

// Define a work item
K_WORK_DEFINE(my_work, my_work_handler);

void submit_work_example(void)
{
    // Submit to the system work queue (default priority)
    k_work_submit(&my_work);
}
```

### Combining Timer + Work Queue (Best Practice)

```c
#include <zephyr/kernel.h>

static struct k_work my_deferred_work;
static struct k_timer my_timer;

void deferred_handler(struct k_work *work)
{
    // Heavy lifting here — thread context
    printk("Deferred work at %lld ms\n", k_uptime_get());
}

void timer_callback(struct k_timer *timer)
{
    // Interrupt context — just submit work
    k_work_submit(&my_deferred_work);
}

K_WORK_DEFINE(my_deferred_work, deferred_handler);
K_TIMER_DEFINE(my_timer, timer_callback, NULL);

void start_combined(void)
{
    k_timer_start(&my_timer, K_MSEC(100), K_MSEC(500));
}
```

### Configuration: Work Queue Stack Size

The system work queue has a default stack (typically 2 KB). For larger workloads, define a custom work queue:

```c
// In your prj.conf
CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4096

// Or define a custom queue
K_THREAD_STACK_DEFINE(my_workq_stack, 4096);
struct k_work_q my_work_q;

void init_custom_workq(void)
{
    k_work_q_start(&my_work_q, my_workq_stack,
                   K_PRIO_PREEMPT(10), 100);
    k_work_submit_to_queue(&my_work_q, &my_deferred_work);
}
```

## Common Pitfalls & Gotchas

1. **Blocking in timer callbacks** — The timer callback runs in interrupt context. Calling `k_sleep()`, `k_sem_take()` with timeout, or any blocking API will crash or deadlock your system. Always use `k_work_submit()` to defer blocking operations.

2. **Work queue starvation** — If one work item runs forever (infinite loop or long blocking), it stalls all other work on that queue. Use `k_work_poll()` or design work items to be short-lived. For time-critical work, use a dedicated work queue with an appropriate priority.

3. **Timer drift in periodic mode** — `k_timer_start()` with a periodic interval uses absolute ticks. If your callback takes significant time, the next firing is delayed. For hard real-time, consider using a dedicated timer ISR or hardware timer directly. Zephyr's `k_timer` is best for soft timing.

## Try It Yourself

1. **One-shot LED blink** — Create a timer that toggles an LED once after 2 seconds. Use `k_timer_start()` with `K_MSEC(2000)` and `K_NO_WAIT`. Verify the LED turns on/off exactly once.

2. **Periodic sensor read** — Set up a timer to fire every 100 ms. In the timer callback, submit a work item that reads an I2C sensor and prints the value. Observe the timing with `k_uptime_get()`.

3. **Custom work queue for heavy processing** — Define a second work queue with a 4 KB stack and priority lower than the system queue. Submit a CPU-intensive work item (e.g., FFT calculation) to it. Verify the system stays responsive by blinking an LED from the main thread.

## Next Up

Tomorrow, we'll get physical: **GPIO Driver API: Input, Output, Interrupts**. I'll cover `gpio_pin_configure()`, `gpio_pin_set()`, and how to wire up edge-triggered interrupts with callbacks — the foundation for buttons, sensors, and actuators.
