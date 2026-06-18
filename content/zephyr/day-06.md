---
title: "Day 06: Threads: k_thread_create, Priorities & Scheduling"
date: 2026-06-18
tags: ["til", "zephyr", "threads", "scheduling"]
---

## What I Explored Today

Today I dug into Zephyr's threading primitives—specifically `k_thread_create()`, priority assignment, and the preemptive scheduling model. After spending days configuring device trees and GPIO interrupts, I needed to understand how to actually run concurrent work. Zephyr's threading is deceptively simple on the surface, but the priority system and scheduling behavior have sharp edges that will bite you if you assume it works like Linux or FreeRTOS.

## The Core Concept

Zephyr uses a **preemptive, priority-based scheduler** with optional cooperative threads. Every thread has a priority from 0 (highest) to `CONFIG_NUM_PREEMPT_PRIORITIES - 1` (lowest) for preemptive threads, and negative values for cooperative threads. The key insight: **cooperative threads never yield unless they explicitly call `k_yield()` or block on a kernel object**. Preemptive threads get swapped out whenever a higher-priority thread becomes ready.

Why this matters: If you're coming from a Linux background, you might expect time-slicing between equal-priority threads. Zephyr does support round-robin scheduling, but only if you explicitly enable `CONFIG_TIMESLICING` and configure time slices. Without that, equal-priority preemptive threads run to completion (or until they block) before the next one runs. This is a "run-to-block" model, not "run-to-timeslice."

The `k_thread_create()` API is the workhorse. It takes a stack buffer (which you must allocate), a thread control block, priority, options flags, and a delay parameter. The delay is critical: if you pass `K_NO_WAIT`, the thread starts immediately. If you pass a timeout, it starts after that delay. This is how you sequence startup without explicit synchronization.

## Key Commands / Configuration / Code

Here's a practical example showing two threads with different priorities and a shared resource (a UART print, which is inherently serialized):

```c
/* Stack and thread control block definitions */
#define STACK_SIZE 1024
#define THREAD_PRIORITY_HIGH 2
#define THREAD_PRIORITY_LOW  5

K_THREAD_STACK_DEFINE(high_stack, STACK_SIZE);
K_THREAD_STACK_DEFINE(low_stack, STACK_SIZE);

struct k_thread high_thread_data;
struct k_thread low_thread_data;

/* Thread entry points */
void high_prio_thread(void *arg1, void *arg2, void *arg3)
{
    while (1) {
        printk("High priority thread running\n");
        /* Yield to let lower priority threads run */
        k_yield();
        /* Simulate work */
        k_sleep(K_MSEC(100));
    }
}

void low_prio_thread(void *arg1, void *arg2, void *arg3)
{
    while (1) {
        printk("Low priority thread running\n");
        k_sleep(K_MSEC(500));
    }
}

void main(void)
{
    /* Create high priority thread - starts immediately */
    k_thread_create(&high_thread_data, high_stack,
                    K_THREAD_STACK_SIZEOF(high_stack),
                    high_prio_thread,
                    NULL, NULL, NULL,
                    THREAD_PRIORITY_HIGH,
                    K_ESSENTIAL,
                    K_NO_WAIT);

    /* Create low priority thread - starts after 1 second */
    k_thread_create(&low_thread_data, low_stack,
                    K_THREAD_STACK_SIZEOF(low_stack),
                    low_prio_thread,
                    NULL, NULL, NULL,
                    THREAD_PRIORITY_LOW,
                    0,
                    K_MSEC(1000));

    /* Main thread continues at its own priority (usually 0 or configurable) */
    while (1) {
        printk("Main thread running\n");
        k_sleep(K_MSEC(200));
    }
}
```

Key configuration in `prj.conf`:
```c
CONFIG_NUM_PREEMPT_PRIORITIES=10   /* Priorities 0-9 are preemptive */
CONFIG_NUM_COOP_PRIORITIES=4       /* Priorities -1 to -4 are cooperative */
CONFIG_TIMESLICING=y               /* Enable round-robin for equal priorities */
CONFIG_TIMESLICE_SIZE=10           /* 10ms time slice */
CONFIG_TIMESLICE_PRIORITY=5        /* Only time-slice priorities >= 5 */
```

The `K_ESSENTIAL` flag in the high-priority thread means the system will panic if this thread exits. Use this sparingly—typically only for threads that must always be running (like a watchdog monitor).

## Common Pitfalls & Gotchas

1. **Stack overflow detection is not automatic.** Zephyr provides `CONFIG_INIT_STACKS` and `CONFIG_STACK_SENTINEL` to help, but they add overhead. Always use `K_THREAD_STACK_DEFINE()` (which aligns stacks properly) rather than raw arrays. I wasted an afternoon debugging a stack corruption that was actually a misaligned stack pointer.

2. **Priority inversion is real and silent.** If a low-priority thread holds a mutex that a high-priority thread needs, the high-priority thread blocks. Zephyr does not implement priority inheritance by default—you must enable `CONFIG_PRIORITY_CEILING` or use `CONFIG_MUTEX_PRIORITY_INHERITANCE`. Without it, your real-time guarantees evaporate.

3. **`k_yield()` vs `k_sleep(0)` are not the same.** `k_yield()` gives up the current time slice and lets the scheduler pick the next ready thread of equal or higher priority. `k_sleep(0)` is actually a no-op in most Zephyr configurations—it does not yield. Use `k_yield()` when you want cooperative scheduling within the same priority level.

## Try It Yourself

1. **Priority inversion experiment:** Create three threads: high (prio 0), medium (prio 2), and low (prio 4). Have the low thread acquire a mutex, then sleep. The medium thread should run a tight loop. Observe how the high thread starves. Then enable `CONFIG_MUTEX_PRIORITY_INHERITANCE` and see the difference.

2. **Stack sizing exercise:** Write a thread that recursively calls a function 50 times, each time adding a 128-byte local array. Use `k_thread_stack_space_get()` to measure actual stack usage. Compare with your `STACK_SIZE`—you'll likely find you can reduce it by 30-50%.

3. **Time-slicing test:** Create two threads at the same priority that both print a counter. First run without `CONFIG_TIMESLICING`—one thread will hog the CPU. Then enable it and observe the interleaving. Adjust `CONFIG_TIMESLICE_SIZE` to see how it affects fairness.

## Next up

Tomorrow we tackle **Semaphores & Mutexes: Producer-Consumer Patterns**. We'll build a real buffered UART driver using counting semaphores to synchronize an interrupt handler with a worker thread, and explore the subtle differences between `k_sem_give()` from ISR context versus thread context.
