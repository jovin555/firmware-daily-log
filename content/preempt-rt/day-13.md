---
title: "Day 13: pthread Real-Time API: SCHED_FIFO & CPU Affinity"
date: 2026-06-25
tags: ["til", "preempt-rt", "pthread", "sched-fifo", "affinity"]
---

## What I Explored Today

Today I dug into the pthread real-time API, specifically `SCHED_FIFO` scheduling policy and CPU affinity. While `SCHED_FIFO` is a POSIX standard, its behavior on a PREEMPT_RT kernel has critical nuances that can make or break a real-time system. I focused on how to correctly set thread priorities, pin threads to cores, and avoid the subtle priority inversion traps that lurk in even simple designs.

## The Core Concept

`SCHED_FIFO` is a fixed-priority, preemptive scheduling policy. A thread with a given priority runs until it either blocks (on I/O, a mutex, or a syscall), yields voluntarily, or is preempted by a higher-priority `SCHED_FIFO` thread. Unlike `SCHED_OTHER` (the default Linux time-sharing scheduler), `SCHED_FIFO` threads have no timeslice — they run until they're done or a higher-priority thread needs the CPU.

The "why" is simple: deterministic latency. In a real-time control loop, you cannot afford to have your 1 kHz thread randomly descheduled because its timeslice expired. `SCHED_FIFO` gives you that guarantee — but only if you pair it with proper CPU affinity.

CPU affinity (`sched_setaffinity`) binds a thread to a specific core. This is essential for two reasons: first, it prevents cache thrashing when the scheduler migrates your thread between cores; second, it isolates your real-time thread from the kernel's housekeeping tasks (like RCU callbacks or timer interrupts) that may run on other cores. On a PREEMPT_RT system, you typically reserve one or more cores exclusively for real-time work via the `isolcpus` kernel boot parameter.

The combination is powerful: a `SCHED_FIFO` thread pinned to an isolated core has near-zero jitter, limited only by hardware interrupts and cache misses.

## Key Commands / Configuration / Code

### Setting SCHED_FIFO and Priority

```c
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <errno.h>

void *rt_thread(void *arg) {
    // ... real-time work here
    return NULL;
}

int main() {
    pthread_t thread;
    pthread_attr_t attr;
    struct sched_param param;

    // Initialize thread attributes
    pthread_attr_init(&attr);

    // Explicitly set the scheduling policy to SCHED_FIFO
    // This must be done before setting the priority
    pthread_attr_setschedpolicy(&attr, SCHED_FIFO);

    // Set priority: 1-99, where 99 is highest
    // WARNING: priority 99 can starve kernel threads (e.g., ksoftirqd)
    param.sched_priority = 80;  // High, but not max
    pthread_attr_setschedparam(&attr, &param);

    // Critical: use EXPLICIT scheduling, not INHERIT
    // Without this, the thread inherits the calling thread's (non-RT) policy
    pthread_attr_setinheritsched(&attr, PTHREAD_EXPLICIT_SCHED);

    // Create the thread
    int ret = pthread_create(&thread, &attr, rt_thread, NULL);
    if (ret != 0) {
        errno = ret;
        perror("pthread_create");
        return 1;
    }

    pthread_attr_destroy(&attr);
    pthread_join(thread, NULL);
    return 0;
}
```

### Setting CPU Affinity

```c
#include <sched.h>

// Pin the current thread to CPU core 2
cpu_set_t cpuset;
CPU_ZERO(&cpuset);
CPU_SET(2, &cpuset);  // Core numbering starts at 0

int ret = pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
if (ret != 0) {
    errno = ret;
    perror("pthread_setaffinity_np");
}
```

### Checking Current Settings

```bash
# Check scheduling policy and priority of a thread
chrt -p <PID>

# Check CPU affinity
taskset -p <PID>

# List isolated CPUs from kernel command line
cat /proc/cmdline | grep isolcpus
```

### Complete Example: RT Thread with Affinity

```c
void *rt_worker(void *arg) {
    // Pin to core 3
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(3, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);

    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);

    while (1) {
        // Do real-time work (e.g., read sensor, compute, actuate)
        // ...

        // Sleep until next period (e.g., 1 ms)
        ts.tv_nsec += 1_000_000;  // 1 ms in nanoseconds
        if (ts.tv_nsec >= 1_000_000_000) {
            ts.tv_sec++;
            ts.tv_nsec -= 1_000_000_000;
        }
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
    }
    return NULL;
}
```

## Common Pitfalls & Gotchas

### 1. Forgetting `PTHREAD_EXPLICIT_SCHED`

This is the #1 mistake. By default, threads inherit the scheduling policy of the creating thread. If your main thread runs under `SCHED_OTHER` (the default), your "RT" thread will also run under `SCHED_OTHER` — silently. Always set `PTHREAD_EXPLICIT_SCHED` in the attributes before creating the thread.

### 2. Priority 99 Starvation

Setting `sched_priority = 99` makes your thread the highest priority in the system. This can starve kernel threads like `ksoftirqd` or `rcu_preempt`, which run at priority 99 on PREEMPT_RT. The result? Network interrupts may not be processed, RCU callbacks stall, and your system becomes unresponsive. Use priority 98 or lower unless you absolutely know what you're doing.

### 3. Affinity Without Isolation

Pinning a `SCHED_FIFO` thread to a core that also runs `SCHED_OTHER` tasks is nearly useless. The kernel's scheduler still runs on that core, and your RT thread will be interrupted by context switches, TLB flushes, and cache pollution from other tasks. Always pair CPU affinity with `isolcpus` on the kernel command line to remove the core from the general scheduler's purview.

## Try It Yourself

1. **Measure the impact of no affinity**: Write two `SCHED_FIFO` threads (priority 50) that each increment a counter in a tight loop. Run them on the same core (no affinity) and measure the total throughput. Then pin each to a separate core and compare. You'll see the cost of cache bouncing.

2. **Priority inversion experiment**: Create three threads: low (priority 10), medium (priority 20), and high (priority 30). The low thread locks a mutex, then the high thread tries to lock the same mutex. Meanwhile, the medium thread runs. Observe how the high thread is blocked by the low thread, which is preempted by the medium thread. This is classic priority inversion — fix it with `pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT)`.

3. **Jitter measurement**: Pin a `SCHED_FIFO` thread to an isolated core (add `isolcpus=3` to your kernel command line). Have it sleep for exactly 1 ms using `clock_nanosleep` with `TIMER_ABSTIME`. Measure the actual wake-up time using `clock_gettime` and log the jitter. Compare with a non-isolated core.

## Next Up

Tomorrow, we tackle **lock-free data structures for RT code**. Mutexes and spinlocks are the enemy of deterministic timing — we'll explore atomic operations, seqlocks, and wait-free ring buffers that let you share data between RT and non-RT threads without priority inversion or unbounded blocking.
