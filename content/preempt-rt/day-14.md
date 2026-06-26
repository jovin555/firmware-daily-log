---
title: "Day 14: Lock-Free Data Structures for RT Code"
date: 2026-06-26
tags: ["til", "preempt-rt", "lock-free", "atomic", "wait-free"]
---

## What I Explored Today

Today I dug into lock-free and wait-free data structures for real-time code running under PREEMPT_RT. While the kernel's RT mutexes and priority inheritance solve priority inversion for most cases, there are still scenarios—like interrupt handlers, high-frequency sensor fusion loops, or scheduler tick paths—where taking a lock is either impossible or introduces unacceptable jitter. I focused on practical atomic operations, the Linux kernel's `kfifo` lockless ring buffer, and a minimal single-producer/single-consumer (SPSC) queue pattern that I can drop into a driver or RT thread tomorrow.

## The Core Concept

The fundamental problem with locks in real-time code isn't just priority inversion—it's *determinism*. A lock forces a thread to wait for an unknown duration: the lock holder could be preempted, take a page fault, or get stalled by a cache miss. Even with PREEMPT_RT's fully preemptible kernel, lock contention introduces statistical tail latency that kills hard real-time guarantees.

Lock-free data structures use atomic hardware primitives (like `cmpxchg` or `atomic_add_return`) to allow concurrent access without a mutex. The key insight: instead of *blocking* when a resource is busy, the operation *retries* until it succeeds. This bounds the worst-case execution time to the number of retries, which is typically small and deterministic on a single-core or carefully designed multi-core system.

The gold standard is *wait-free*: every thread completes its operation in a bounded number of steps, regardless of what other threads do. Lock-free means *some* thread makes progress, but individual threads may starve temporarily. For RT, wait-free is ideal but harder to implement. In practice, a well-designed lock-free SPSC queue (single producer, single consumer) is often sufficient and trivially wait-free.

## Key Commands / Configuration / Code

### 1. Linux Kernel Atomic Operations (the building blocks)

```c
// Atomic set and get — no memory barrier unless you need it
atomic_t counter = ATOMIC_INIT(0);
atomic_set(&counter, 42);
int val = atomic_read(&counter);

// Atomic increment and return (useful for sequence counters)
int seq = atomic_inc_return(&counter);

// Compare-and-swap (cmpxchg) — the heart of lock-free
// Atomically: if *ptr == old, set *ptr = new and return old
u32 old_val = 10;
u32 new_val = 20;
u32 prev = cmpxchg(&my_var, old_val, new_val);
if (prev == old_val) {
    // We successfully swapped — no contention
}
```

### 2. kfifo — Kernel's Lockless Ring Buffer

The kernel already ships a battle-tested lock-free FIFO for single-producer/single-consumer:

```c
#include <linux/kfifo.h>

// Declare and initialize a kfifo for 1024 bytes
DECLARE_KFIFO(my_fifo, unsigned char, 1024);
INIT_KFIFO(my_fifo);

// Producer (IRQ context or RT thread)
unsigned char data = read_sensor();
if (kfifo_in(&my_fifo, &data, 1) != 1) {
    // FIFO full — handle overflow (drop or spin)
}

// Consumer (RT task)
unsigned char sample;
if (kfifo_out(&my_fifo, &sample, 1) == 1) {
    process_sample(sample);
}
```

This is wait-free for SPSC: no locks, no atomic RMW in the fast path (it uses memory barriers only). Perfect for interrupt-to-task communication.

### 3. Custom SPSC Queue (Simplified)

When kfifo doesn't fit (e.g., you need variable-size messages), here's a minimal lock-free SPSC:

```c
struct spsc_queue {
    struct message *buffer;
    atomic_t head;  // producer writes here
    atomic_t tail;  // consumer reads here
    int size;
};

// Producer (must be single thread)
int spsc_push(struct spsc_queue *q, struct message *msg) {
    int head = atomic_read(&q->head);
    int next_head = (head + 1) % q->size;
    if (next_head == atomic_read(&q->tail))
        return -1; // full
    q->buffer[head] = *msg;
    smp_store_release(&q->head, next_head); // publish
    return 0;
}

// Consumer (must be single thread)
int spsc_pop(struct spsc_queue *q, struct message *msg) {
    int tail = atomic_read(&q->tail);
    if (tail == atomic_read(&q->head))
        return -1; // empty
    *msg = q->buffer[tail];
    smp_store_release(&q->tail, (tail + 1) % q->size);
    return 0;
}
```

The `smp_store_release()` ensures that the data write is visible before the head/tail update, preventing the consumer from reading stale data.

## Common Pitfalls & Gotchas

1. **ABA problem with cmpxchg on pointers**: If you're building a lock-free stack or list, a compare-and-swap can succeed when the pointer value is the same but the pointed-to memory has changed. Always use tagged pointers (e.g., `atomic_cmpxchg` with a sequence counter) or hazard pointers. For SPSC queues, this isn't an issue because you never free memory during operation.

2. **Memory ordering is architecture-specific**: `smp_store_release()` and `smp_load_acquire()` are your friends—they provide the right barriers on ARM, x86, and RISC-V. Don't use raw `smp_mb()` unless you understand the cost. On x86, release/acquire are nearly free; on ARM, they're not. Profile your target.

3. **Lock-free does not mean deterministic under contention**: A lock-free stack with many concurrent pushers can cause unbounded retries (each thread spins on cmpxchg). For hard RT, you must bound the number of retries or use a wait-free design. SPSC avoids this entirely—there's no contention by design.

## Try It Yourself

1. **Measure kfifo latency**: Write a kernel module that sends 10,000 samples from a timer callback (simulating an interrupt) to a kfifo, then reads them in a real-time task. Use `trace-cmd` to record the wakeup latency. Compare with a version using `spin_lock_irqsave`.

2. **Build a lock-free flag for deferred work**: Create a simple atomic flag (`atomic_t`) that an IRQ handler sets to indicate "data ready." The RT task clears it with `atomic_cmpxchg` to avoid missing events. Measure the maximum time between IRQ and task wakeup.

3. **Port the SPSC queue to userspace**: Write a C program using C11 `atomic_compare_exchange_strong` that implements the SPSC queue above. Run it on a dual-core Raspberry Pi with `chrt -f 99` and verify that the producer (pinned to CPU 0) never blocks the consumer (CPU 1).

## Next Up

Tomorrow I'm tackling **SCHED_DEADLINE: Sporadic Task Scheduling**—the Linux kernel's hard real-time scheduler that lets you specify a period, runtime, and deadline for each task. We'll wire it up with `chrt` and `sched_setattr`, and measure whether it actually beats SCHED_FIFO for bursty workloads.
