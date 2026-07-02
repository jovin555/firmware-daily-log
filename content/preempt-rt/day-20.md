---
title: "Day 20: Linux Scheduling: CFS, FIFO, RR & Deadline Policies"
date: 2026-07-02
tags: ["til", "preempt-rt", "cfs", "sched-fifo", "scheduling"]
---

## What I Explored Today

Today I dug into the Linux kernel's scheduling policies — the core mechanism that decides which thread runs when. For real-time work, understanding the difference between CFS, SCHED_FIFO, SCHED_RR, and SCHED_DEADLINE isn't academic trivia; it's the difference between a control loop that jitters by 10 µs and one that misses its deadline entirely. I traced through the scheduler code, ran experiments with `chrt` and `perf`, and confirmed exactly how each policy behaves under load.

## The Core Concept

The Linux scheduler is a **priority-driven preemptive scheduler** with multiple scheduling classes. The key insight: not all threads are equal, and the kernel needs to know *which* threads care about latency versus throughput.

**CFS (Completely Fair Scheduler)** — the default policy (`SCHED_OTHER`/`SCHED_NORMAL`). CFS uses a red-black tree of tasks, each with a `vruntime` (virtual runtime). It always picks the task with the smallest `vruntime`, aiming for perfect fairness. The "nice" value adjusts the weight of a task's time slice. CFS is great for desktop workloads but terrible for real-time: it has no concept of deadlines or bounded latency.

**SCHED_FIFO** — First-In, First-Out real-time policy (priority 1-99). A FIFO thread runs until it voluntarily yields (`sched_yield()`), blocks on I/O, or is preempted by a higher-priority FIFO thread. No time slicing. This is the go-to for short, deterministic tasks that must run immediately.

**SCHED_RR** — Round-Robin real-time policy (priority 1-99). Same as FIFO, but with a time slice (default 100ms on most kernels). If a RR thread doesn't yield before its slice expires, it goes to the back of its priority queue. Useful when you have multiple same-priority real-time threads that must share the CPU.

**SCHED_DEADLINE** — Earliest Deadline First (EDF) with CBS (Constant Bandwidth Server). You specify three parameters: `runtime` (how much CPU time per period), `deadline` (relative deadline), and `period` (the interval). The kernel guarantees that the thread gets `runtime` CPU time before each `deadline` expires. This is the most powerful real-time policy but requires careful admission control.

The hierarchy: SCHED_DEADLINE > SCHED_FIFO/RR > CFS. A deadline thread always preempts any FIFO thread, which always preempts any CFS thread.

## Key Commands / Configuration / Code

**Check current policy and priority:**
```bash
# Show scheduling policy for PID 1234
chrt -p 1234
# Output: pid 1234's current scheduling policy: SCHED_OTHER

# Show all threads in a process
ps -eLo pid,tid,cls,pri,ni,cmd | grep my_rt_app
# cls column: TS=CFS, FF=FIFO, RR=RR, DL=Deadline
```

**Set real-time policy:**
```bash
# Set PID 5678 to SCHED_FIFO priority 80
sudo chrt -f -p 80 5678

# Set to SCHED_RR priority 50
sudo chrt -r -p 50 5678

# Set to SCHED_DEADLINE (runtime=100ms, deadline=200ms, period=500ms)
sudo chrt -d --sched-runtime 100000000 \
            --sched-deadline 200000000 \
            --sched-period 500000000 0 ./deadline_app
```

**From C code:**
```c
#include <sched.h>
#include <pthread.h>

struct sched_param param;
param.sched_priority = 80; // Valid range: 1-99

// Set calling thread to SCHED_FIFO
if (sched_setscheduler(0, SCHED_FIFO, &param) == -1) {
    perror("sched_setscheduler");
    // Need CAP_SYS_NICE or root
}

// For SCHED_DEADLINE, use sched_setattr() (Linux 3.14+)
struct sched_attr attr = {
    .size = sizeof(attr),
    .sched_policy = SCHED_DEADLINE,
    .sched_runtime = 100000000,    // 100ms
    .sched_deadline = 200000000,   // 200ms
    .sched_period = 500000000,     // 500ms
};
sched_setattr(0, &attr, 0);
```

**Monitor scheduler behavior:**
```bash
# Trace scheduling events with perf
sudo perf sched record -- sleep 5
sudo perf sched latency

# Watch context switches per thread
sudo perf stat -e context-switches -p PID
```

## Common Pitfalls & Gotchas

**1. Priority inversion is real and silent.** A low-priority FIFO thread holding a mutex can block a high-priority FIFO thread. Without priority inheritance (which requires `pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT)`), your real-time thread will miss deadlines. Always use `PTHREAD_PRIO_INHERIT` on mutexes shared with real-time threads.

**2. SCHED_FIFO at priority 99 can lock up your system.** A compute-bound FIFO thread at max priority will starve everything, including the keyboard handler and SSH daemon. Always include a `sched_yield()` or blocking call in your real-time loops, or use SCHED_DEADLINE with a bounded runtime.

**3. Deadline admission control can fail silently.** `sched_setattr()` for SCHED_DEADLINE returns -EBUSY if the requested bandwidth exceeds the CPU capacity (default 95% of one core). Your app will fall back to SCHED_OTHER unless you check the return value. Always verify the return code and have a fallback policy.

**4. CFS "nice" values don't affect real-time threads.** Setting `nice -20` on a SCHED_FIFO thread does nothing. Real-time priorities are absolute, not relative. Mixing CFS and RT threads requires careful design — the RT thread will preempt CFS regardless of nice values.

## Try It Yourself

1. **Measure FIFO vs CFS latency:** Write a simple loop that reads `CLOCK_MONOTONIC` and computes the delta between iterations. Run it under SCHED_OTHER, then SCHED_FIFO priority 80. Use `stress --cpu 4` to generate load. Compare the max jitter using `perf stat -e cycles,instructions`.

2. **Verify priority inheritance:** Create two threads: one at FIFO priority 80 (holds a mutex, does 1ms work), one at FIFO priority 90 (tries to lock the same mutex). Without `PTHREAD_PRIO_INHERIT`, measure how long the high-priority thread waits. Then add the protocol and measure again.

3. **Test SCHED_DEADLINE admission control:** Write a program that requests 600ms runtime per 1000ms period (60% CPU). Run it, then try requesting 950ms runtime per 1000ms period. Observe the `sched_setattr()` return value and `dmesg` for admission control messages.

## Next Up

Tomorrow: **PREEMPT_RT Patch: What It Changes & How to Apply It** — we'll move from scheduling policies to the actual kernel patch that makes Linux a hard real-time OS. I'll show you the exact kernel config changes, the patch application process, and what `spin_lock()` becomes under PREEMPT_RT.
