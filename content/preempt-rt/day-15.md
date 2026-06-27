---
title: "Day 15: SCHED_DEADLINE: Sporadic Task Scheduling"
date: 2026-06-27
tags: ["til", "preempt-rt", "sched-deadline", "sporadic", "edf"]
---

## What I Explored Today

Today I dove into `SCHED_DEADLINE`, Linux's implementation of the Earliest Deadline First (EDF) algorithm with sporadic task support. Unlike `SCHED_FIFO` or `SCHED_RR` which use static priorities, `SCHED_DEADLINE` lets you specify a task's runtime, deadline, and period — and the kernel guarantees that the task will meet its deadline as long as the system isn't overloaded. I built a sporadic task generator, measured its scheduling behavior with `trace-cmd`, and validated that the kernel's admission control actually prevents overcommitment.

## The Core Concept

Real-time tasks come in three flavors: periodic (fixed interval), aperiodic (random, no deadline), and sporadic (random but with a minimum inter-arrival time). Sporadic tasks are the hardest to schedule because you can't predict exactly when they'll fire, but you know they won't fire more often than some bound.

`SCHED_DEADLINE` solves this using the **Constant Bandwidth Server (CBS)** algorithm. Each task gets three parameters:
- `sched_runtime` — how much CPU time the task needs per activation
- `sched_deadline` — the relative deadline from the activation time
- `sched_period` — the minimum inter-arrival time (period)

The kernel maintains an admission control test: the sum of all `runtime/period` ratios must be ≤ 1 (on each CPU). If you try to create a task set that exceeds this, `sched_setattr()` returns `-EBUSY`. This is a hard guarantee — no priority inversion, no priority boosting, just deterministic scheduling.

Why does this matter for embedded engineers? Because industrial control, audio processing, and robotics workloads are inherently sporadic. A sensor interrupt might arrive at irregular intervals, but you still need to process it within 500 µs. With `SCHED_DEADLINE`, you can express this directly: "Give me 100 µs of CPU within 500 µs of activation, and don't let me fire more often than every 1 ms."

## Key Commands / Configuration / Code

### 1. Setting SCHED_DEADLINE via chrt (limited)

The `chrt` utility only supports `SCHED_FIFO` and `SCHED_RR`. For `SCHED_DEADLINE`, you must use the `sched_setattr()` system call directly. Here's a minimal C program:

```c
// deadline_sporadic.c
#define _GNU_SOURCE
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <linux/sched/types.h>

int main(int argc, char *argv[]) {
    struct sched_attr attr = {
        .size = sizeof(attr),
        .sched_policy = SCHED_DEADLINE,
        .sched_runtime = 100000,    // 100 µs runtime
        .sched_deadline = 500000,   // 500 µs deadline
        .sched_period = 1000000,    // 1 ms period
    };

    // sched_setattr() is not in glibc, use syscall
    if (syscall(SYS_sched_setattr, 0, &attr, 0) == -1) {
        perror("sched_setattr");
        return 1;
    }

    // Sporadic work loop: simulate bursty activation
    while (1) {
        // Wait for external trigger (e.g., GPIO interrupt)
        // In this demo, just busy-wait for a random interval
        usleep(rand() % 5000 + 1000); // 1-6 ms random delay

        // Do bounded work (must complete within runtime)
        volatile unsigned long count = 0;
        for (int i = 0; i < 50000; i++) count++;
    }
    return 0;
}
```

Compile with: `gcc -o deadline_sporadic deadline_sporadic.c -lrt`

### 2. Monitoring with trace-cmd

```bash
# Trace scheduling events for our task
sudo trace-cmd record -e sched:sched_switch -e sched:sched_wakeup \
    -e sched:sched_deadline:dl_runtime_exceeded \
    -F -p 1234  # replace with PID of your deadline task

# After stopping, view the trace
trace-cmd report | grep "deadline\|dl_runtime"
```

### 3. Checking admission control limits

```bash
# View per-CPU SCHED_DEADLINE bandwidth
cat /proc/sys/kernel/sched_rt_runtime_us
cat /proc/sys/kernel/sched_rt_period_us

# Default: 950000 µs runtime per 1000000 µs period (95% max)
# SCHED_DEADLINE shares this pool with SCHED_FIFO/RR
```

### 4. Python test harness for overcommitment

```python
#!/usr/bin/env python3
import ctypes, os, struct

SCHED_DEADLINE = 6
SYS_sched_setattr = 351  # x86_64

class SchedAttr(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint32),
        ("sched_policy", ctypes.c_uint32),
        ("sched_flags", ctypes.c_uint64),
        ("sched_nice", ctypes.c_int32),
        ("sched_priority", ctypes.c_uint32),
        ("sched_runtime", ctypes.c_uint64),
        ("sched_deadline", ctypes.c_uint64),
        ("sched_period", ctypes.c_uint64),
    ]

libc = ctypes.CDLL("libc.so.6")

def set_deadline(pid, runtime_us, deadline_us, period_us):
    attr = SchedAttr()
    attr.size = ctypes.sizeof(attr)
    attr.sched_policy = SCHED_DEADLINE
    attr.sched_runtime = runtime_us * 1000  # ns
    attr.sched_deadline = deadline_us * 1000
    attr.sched_period = period_us * 1000
    ret = libc.syscall(SYS_sched_setattr, pid, ctypes.byref(attr), 0)
    if ret != 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))

# Try to overcommit: two tasks each needing 60% CPU
try:
    set_deadline(0, 600, 1000, 1000)  # 60% of CPU
    print("Task 1 set")
except OSError as e:
    print(f"Task 1 failed: {e}")

# This should fail if task 1 succeeded
try:
    set_deadline(0, 600, 1000, 1000)  # Another 60%
    print("Task 2 set (overcommit!)")
except OSError as e:
    print(f"Task 2 correctly rejected: {e}")
```

## Common Pitfalls & Gotchas

1. **SCHED_DEADLINE shares the RT throttling pool with SCHED_FIFO/RR.** The kernel enforces a global limit (default 95%) for all real-time policies combined. If you have existing `SCHED_FIFO` tasks using 50% of CPU, `SCHED_DEADLINE` can only use the remaining 45%. Check `/proc/sys/kernel/sched_rt_runtime_us` and adjust with `sysctl -w kernel.sched_rt_runtime_us=-1` to disable throttling (not recommended for production).

2. **`sched_setattr()` is not in glibc.** You must use the raw `syscall()` function. On ARM64, the syscall number is 352, not 351. Always check your architecture's syscall table. The `sched_attr` struct must have `size` set correctly or the kernel will reject it with `-EINVAL`.

3. **Deadline misses don't crash the task — they silently degrade.** If your task exceeds its `sched_runtime`, the kernel throttles it until the next period. No signal, no log by default. You must explicitly enable `SCHED_FLAG_DL_OVERRUN` in `sched_flags` and handle `SIGXCPU` to detect overruns. Without this, your system will silently miss deadlines.

## Try It Yourself

1. **Write a sporadic task that triggers on a GPIO edge.** Use `libgpiod` to wait for a rising edge, then process data within a `SCHED_DEADLINE` budget. Measure the jitter between activation and completion using `clock_gettime(CLOCK_MONOTONIC)`.

2. **Stress-test admission control.** Write a script that attempts to create 10 `SCHED_DEADLINE` tasks, each with `runtime=200ms, period=1000ms` (20% each). Observe which ones fail and why. Then reduce the runtime until all 10 fit.

3. **Compare SCHED_DEADLINE vs SCHED_FIFO for sporadic load.** Create a task that busy-waits for 500 µs every 2 ms (randomized arrival). Run it under both policies and measure the maximum observed latency using `cyclictest` or `ftrace`. Which one gives tighter bounds?

## Next Up Teaser

Tomorrow we leave the scheduler and enter the factory floor: **RT Linux for Industrial Control: EtherCAT & Fieldbus**. We'll wire up a real-time EtherCAT master using the IgH EtherLab stack, configure PREEMPT_RT for sub-millisecond cycle times, and debug jitter with a logic analyzer. Bring your servo drives — it's about to get physical.
