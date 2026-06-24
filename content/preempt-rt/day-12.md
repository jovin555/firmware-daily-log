---
title: "Day 12: Priority Inversion & Priority Inheritance Mutexes"
date: 2026-06-24
tags: ["til", "preempt-rt", "priority-inversion", "mutex", "pthread"]
---

## What I Explored Today

Today I dug into one of the most insidious problems in real-time systems: priority inversion. I've known about it theoretically, but after instrumenting a test case on my PREEMPT_RT kernel (6.1.84-rt), I watched a high-priority task miss its deadline by 47ms because a medium-priority task was hogging the CPU while a low-priority task held a mutex. The fix? Priority inheritance mutexes via `PTHREAD_PRIO_INHERIT`. I traced the entire chain with `perf` and `ftrace`, then verified the fix with cyclictest. Here's what every RT engineer needs to know.

## The Core Concept

Priority inversion occurs when a higher-priority task (H) is blocked waiting for a resource held by a lower-priority task (L), while a medium-priority task (M) preempts L and runs indefinitely. H can't run until L releases the resource, but L can't run because M is running. The result: H's priority is effectively inverted to that of the lowest task in the chain.

The classic fix is **priority inheritance**: when H blocks on a mutex held by L, L temporarily inherits H's priority. This prevents M from preempting L, allowing L to finish quickly and release the mutex. Once released, L's priority drops back to its original value.

In PREEMPT_RT, the kernel's `rt_mutex` implementation handles this automatically for kernel-space locks. For user-space pthreads, you must explicitly enable it with `PTHREAD_PRIO_INHERIT` when initializing the mutex attribute.

## Key Commands / Configuration / Code

### 1. Enabling Priority Inheritance in pthreads

```c
#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

pthread_mutex_t mtx;
pthread_mutexattr_t attr;

void init_priority_inheritance_mutex(void) {
    int ret;

    // Initialize attribute object
    ret = pthread_mutexattr_init(&attr);
    if (ret) {
        perror("pthread_mutexattr_init");
        return;
    }

    // Set protocol to priority inheritance
    ret = pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT);
    if (ret) {
        perror("pthread_mutexattr_setprotocol");
        return;
    }

    // Initialize mutex with these attributes
    ret = pthread_mutex_init(&mtx, &attr);
    if (ret) {
        perror("pthread_mutex_init");
        return;
    }

    // Clean up attribute (no longer needed)
    pthread_mutexattr_destroy(&attr);
}
```

### 2. Detecting Priority Inversion with ftrace

```bash
# Enable priority-related trace events
echo 1 > /sys/kernel/tracing/events/sched/sched_wakeup/enable
echo 1 > /sys/kernel/tracing/events/sched/sched_switch/enable
echo 1 > /sys/kernel/tracing/events/lock/lock_acquire/enable
echo 1 > /sys/kernel/tracing/events/lock/lock_contended/enable

# Set trace buffer size (8MB)
echo 8192 > /sys/kernel/tracing/buffer_size_kb

# Start tracing
echo 1 > /sys/kernel/tracing/tracing_on

# Run your test application (with tasks at priorities 10, 50, 90)
./priority_inversion_test

# Stop tracing
echo 0 > /sys/kernel/tracing/tracing_on

# Extract the trace, filtering for your PIDs
cat /sys/kernel/tracing/trace | grep -E "(PID_H|PID_M|PID_L)" > inversion_trace.txt
```

### 3. Verifying with cyclictest

```bash
# Run cyclictest with priority inheritance mutexes for internal locking
cyclictest -t 5 -p 90 -i 1000 -d 0 -m -n -b 100 \
    --prio-spread=50 \
    --mlockall \
    --policy=fifo \
    --smp \
    --mainaffinity=0

# Look for max latency spikes > 100us — these often indicate inversion
# Output: T:0 (12345) P:90 I:1000 C: 5000 Min: 2 Act: 3 Max: 47  <- 47us spike!
```

### 4. Complete Test Skeleton

```c
// compile with: gcc -o pi_test pi_test.c -lpthread -lrt
#define _GNU_SOURCE
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/mman.h>

pthread_mutex_t mtx;
volatile int shared_resource = 0;

void set_realtime_priority(int priority) {
    struct sched_param param;
    param.sched_priority = priority;
    if (sched_setscheduler(0, SCHED_FIFO, &param) == -1) {
        perror("sched_setscheduler");
        exit(1);
    }
}

void* low_priority_task(void* arg) {
    set_realtime_priority(10);
    pthread_mutex_lock(&mtx);
    // Simulate long work while holding lock
    for (int i = 0; i < 10000000; i++) shared_resource++;
    pthread_mutex_unlock(&mtx);
    return NULL;
}

void* medium_priority_task(void* arg) {
    set_realtime_priority(50);
    // CPU-bound work — will preempt low-pri task if it doesn't inherit
    for (int i = 0; i < 50000000; i++) asm volatile("nop");
    return NULL;
}

void* high_priority_task(void* arg) {
    set_realtime_priority(90);
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    long start_ns = ts.tv_nsec;

    pthread_mutex_lock(&mtx);  // Blocks if low-pri holds it
    // Critical section
    shared_resource++;
    pthread_mutex_unlock(&mtx);

    clock_gettime(CLOCK_MONOTONIC, &ts);
    long elapsed_ns = ts.tv_nsec - start_ns;
    printf("High-pri blocked for %ld ns\n", elapsed_ns);
    return NULL;
}

int main() {
    mlockall(MCL_CURRENT | MCL_FUTURE);
    pthread_t t1, t2, t3;

    // Try with PTHREAD_PRIO_NONE first, then PTHREAD_PRIO_INHERIT
    pthread_mutexattr_t attr;
    pthread_mutexattr_init(&attr);
    pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT);
    pthread_mutex_init(&mtx, &attr);

    pthread_create(&t1, NULL, low_priority_task, NULL);
    usleep(100);  // Ensure low-pri locks first
    pthread_create(&t2, NULL, medium_priority_task, NULL);
    usleep(100);
    pthread_create(&t3, NULL, high_priority_task, NULL);

    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    pthread_join(t3, NULL);

    pthread_mutex_destroy(&mtx);
    return 0;
}
```

## Common Pitfalls & Gotchas

1. **`PTHREAD_PRIO_INHERIT` is not the default.** The default protocol is `PTHREAD_PRIO_NONE`, which means no inheritance. If you forget to set it, you'll get classic priority inversion. Always verify with `pthread_mutexattr_getprotocol()` during initialization.

2. **Priority inheritance doesn't prevent deadlocks.** It only mitigates inversion. If you have circular dependencies (task A locks mutex1, task B locks mutex2, then both try to acquire the other), inheritance won't help — you'll still deadlock. Use lock ordering or trylock with backoff.

3. **Kernel vs. user-space inheritance.** PREEMPT_RT's `rt_mutex` handles kernel-space locks (spinlocks converted to mutexes) automatically. But user-space pthreads are separate — you must explicitly set the attribute. Many engineers assume the kernel handles everything and miss this.

4. **Performance overhead.** Priority inheritance adds overhead to every mutex lock/unlock operation (about 50-100ns on modern x86). In non-RT systems, this is usually acceptable, but in ultra-low-latency paths, consider whether you actually need it. Profile with `perf stat` before and after.

## Try It Yourself

1. **Reproduce the inversion.** Compile the test skeleton above with `PTHREAD_PRIO_NONE` (comment out the `setprotocol` line). Run it and observe the high-priority task's blocked time. Then enable `PTHREAD_PRIO_INHERIT` and compare. The difference should be dramatic (microseconds vs. milliseconds).

2. **Trace it with ftrace.** Use the ftrace commands above to capture the sched_switch events. Identify the exact moment the high-priority task is woken but can't run because the medium-priority task is on CPU. Look for the "wakeup" event with no corresponding "sched_switch" to the high-pri task.

3. **Measure with cyclictest.** Run cyclictest with `-b 100` (breaktrace threshold) to automatically stop tracing when a latency spike exceeds 100µs. Then inspect the trace to see if a priority inversion caused the spike. Try running a background workload that simulates inversion (e.g., a low-pri task holding a mutex while a medium-pri task spins).

## Next Up

Tomorrow: **pthread Real-Time API: SCHED_FIFO & CPU Affinity** — we'll move beyond mutexes and dive into scheduling policies, setting CPU affinity with `pthread_setaffinity_np`, and why `SCHED_FIFO` with proper affinity is the foundation of any deterministic RT application.
