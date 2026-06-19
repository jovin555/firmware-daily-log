---
title: "Day 07: Semaphores & Mutexes: Producer-Consumer Patterns"
date: 2026-06-19
tags: ["til", "zephyr", "semaphore", "mutex"]
---

## What I Explored Today

Today I dove into Zephyr's synchronization primitives—specifically semaphores and mutexes—by implementing a classic producer-consumer pattern on an nRF52840 DK. I needed to coordinate two threads sharing a fixed-size buffer without data corruption or busy-waiting. The result: a clean, interrupt-safe pipeline where a sensor-data producer thread signals a consumer thread via a counting semaphore, while a mutex guards the shared buffer against concurrent access.

## The Core Concept

The producer-consumer problem is the "Hello World" of RTOS synchronization. You have one thread producing data (e.g., reading an ADC, parsing a UART packet) and another consuming it (e.g., logging to flash, sending over BLE). Without coordination, the consumer might read stale data, or the producer might overwrite data before it's consumed.

Zephyr provides two key primitives here:

- **Counting semaphore**: Tracks how many "units" of work are available. The producer calls `k_sem_give()` to increment the count; the consumer calls `k_sem_take()` to decrement it. If the count is zero, the consumer blocks—no busy-waiting.

- **Mutex**: A binary semaphore with priority inheritance, used to protect shared resources (like the buffer) from concurrent writes. Unlike a raw semaphore, a mutex can only be unlocked by the thread that locked it, preventing accidental unlocks from ISRs or other threads.

Why not just use a single semaphore? Because the semaphore only signals *availability*, not *exclusive access*. You need both: the semaphore says "data is ready," the mutex says "I'm reading/writing the buffer—wait your turn."

## Key Commands / Configuration / Code

### Kconfig Dependencies
In your `prj.conf`, ensure these are enabled (they're usually on by default, but explicit is better):
```kconfig
CONFIG_SEMAPHORES=y
CONFIG_MUTEXES=y
CONFIG_THREAD_NAME=y
```

### Shared Buffer and Synchronization Objects
```c
/* buffer.h */
#define BUF_SIZE 4

struct shared_buffer {
    uint32_t data[BUF_SIZE];
    struct k_mutex lock;
    struct k_semavail;    /* counts available items */
    int head;             /* producer index */
    int tail;             /* consumer index */
};

extern struct shared_buffer buf;
```

### Initialization
```c
/* main.c */
#include <zephyr/kernel.h>
#include "buffer.h"

struct shared_buffer buf;

void init_buffer(void)
{
    k_mutex_init(&buf.lock);
    k_sem_init(&buf.avail, 0, BUF_SIZE);  /* start empty, max BUF_SIZE */
    buf.head = 0;
    buf.tail = 0;
}
```

### Producer Thread
```c
void producer_thread(void *arg1, void *arg2, void *arg3)
{
    uint32_t sensor_val = 0;

    while (1) {
        sensor_val = read_sensor();  /* hypothetical sensor read */

        /* Wait for space in the buffer (optional: use a "free" semaphore) */
        k_mutex_lock(&buf.lock, K_FOREVER);
        buf.data[buf.head] = sensor_val;
        buf.head = (buf.head + 1) % BUF_SIZE;
        k_mutex_unlock(&buf.lock);

        /* Signal consumer that data is ready */
        k_sem_give(&buf.avail);

        /* Simulate sensor sampling interval */
        k_sleep(K_MSEC(100));
    }
}

K_THREAD_DEFINE(producer_tid, 1024,
                producer_thread, NULL, NULL, NULL,
                5, 0, 0);
```

### Consumer Thread
```c
void consumer_thread(void *arg1, void *arg2, void *arg3)
{
    uint32_t val;

    while (1) {
        /* Wait for data to be available */
        k_sem_take(&buf.avail, K_FOREVER);

        k_mutex_lock(&buf.lock, K_FOREVER);
        val = buf.data[buf.tail];
        buf.tail = (buf.tail + 1) % BUF_SIZE;
        k_mutex_unlock(&buf.lock);

        process_data(val);  /* e.g., printk, store to flash */
    }
}

K_THREAD_DEFINE(consumer_tid, 1024,
                consumer_thread, NULL, NULL, NULL,
                4, 0, 0);
```

### Key Points in the Code
- The semaphore `avail` is initialized to 0—consumer blocks until producer gives.
- The mutex `lock` is held only for the duration of the buffer access (microsecond-scale), minimizing contention.
- The producer does **not** hold the mutex while sleeping—critical for real-time responsiveness.
- Thread priorities: producer at 5, consumer at 4 (lower number = higher priority in Zephyr). This ensures the consumer runs immediately when data is available, preventing buffer overflow.

## Common Pitfalls & Gotchas

1. **Mutex in ISR**: Never call `k_mutex_lock()` from an interrupt service routine. Mutexes can block, and ISRs must not block. Use `k_sem_give()` (which is ISR-safe) to signal threads from interrupts. If you need mutual exclusion in an ISR, use `k_spin_lock()` instead.

2. **Semaphore count overflow**: If your producer runs faster than your consumer, `k_sem_give()` will fail if the semaphore count is already at its maximum (BUF_SIZE in our example). Always check the return value: `if (k_sem_give(&buf.avail) != 0) { /* buffer full, handle overflow */ }`. Alternatively, use a "free slots" semaphore initialized to BUF_SIZE that the consumer gives and the producer takes.

3. **Priority inversion with mutexes**: Zephyr's mutexes implement priority inheritance, but it only works if all threads using the mutex are in the cooperative or preemptible scheduling policies. If a thread is marked `K_FP_REGS` (floating point) or uses `K_ESSENTIAL`, inheritance may not function correctly. Stick with default thread options unless you have a specific need.

## Try It Yourself

1. **Add a "free slots" semaphore**: Modify the producer to `k_sem_take()` a "free" semaphore (initialized to BUF_SIZE) before writing, and the consumer to `k_sem_give()` it after reading. This prevents the producer from overwriting unread data.

2. **Measure worst-case blocking time**: Use `k_cycle_get_32()` to timestamp before and after `k_mutex_lock()` in both threads. Log the maximum time the mutex was held. Is it under 10 microseconds? If not, reduce the critical section.

3. **Replace mutex with a lock-free ring buffer**: For a single-producer, single-consumer scenario, you can eliminate the mutex entirely by using atomic index updates. Implement this using `atomic_t` for `head` and `tail`, and verify it works correctly under stress.

## Next Up

Tomorrow, I'll tackle **Message Queues & Mailboxes: Thread Communication**. While semaphores signal *that* data is ready, message queues let you pass *the data itself* between threads—including from ISRs to tasks. We'll build a UART RX parser that queues received bytes for a processing thread, and compare the performance of `k_msgq_put()` vs. the semaphore+mutex approach we used today.
