---
title: "Day 02: Linux Scheduling: CFS, FIFO, RR & Deadline Policies"
date: 2026-06-14
tags: ["til", "preempt-rt", "cfs", "sched-fifo", "scheduling"]
---

## What I Explored Today

Today I dug into the Linux scheduler's policy landscape—specifically how CFS, FIFO, Round Robin, and Deadline scheduling interact, and why this matters for real-time systems. The kernel's scheduler isn't a single monolithic algorithm; it's a policy framework where the right choice can mean the difference between a 10 µs jitter and a 100 ms latency spike. I focused on understanding which policy to use when, and how PREEMPT_RT changes the rules of the game.

## The Core Concept

The Linux scheduler (CFS, `sched/fair.c`) is designed for throughput and fairness—it tries to give every task a proportional slice of CPU time. That's great for servers and desktops, but terrible for real-time. A high-priority audio thread shouldn't yield to a background cron job. So the kernel provides three real-time scheduling policies that bypass CFS entirely:

- **SCHED_FIFO** (First In, First Out): Strict priority. A running FIFO task runs until it blocks, yields, or is preempted by a higher-priority FIFO/RR task. No time slicing. This is your go-to for hard real-time threads that must run to completion without interruption.
- **SCHED_RR** (Round Robin): Same as FIFO, but with a time quantum. If a RR task doesn't complete within its slice, it goes to the back of its priority queue. Useful when you have multiple same-priority real-time tasks that need fairness among themselves.
- **SCHED_DEADLINE** (Deadline): The newest and most sophisticated. You specify runtime, period, and deadline. The kernel uses Earliest Deadline First (EDF) with constant bandwidth server (CBS) guarantees. This is for tasks with explicit timing constraints—e.g., "I need 2 ms of CPU every 10 ms, and the result must be ready within 8 ms."

The critical insight: **real-time policies are not "faster"—they are more predictable.** A FIFO task at priority 99 will always preempt a FIFO task at priority 50, regardless of how much CPU the lower-priority task has consumed. This determinism is what real-time systems need.

## Key Commands / Configuration / Code

### Check Current Scheduling Policy and Priority

```bash
# Show policy and priority for a PID (e.g., PID 1234)
chrt -p 1234
# Output: pid 1234's current scheduling policy: SCHED_OTHER
#         pid 1234's current scheduling priority: 0
```

### Set a Real-Time Policy

```bash
# Set SCHED_FIFO with priority 80 for PID 5678
chrt -f -p 80 5678

# Set SCHED_RR with priority 50
chrt -r -p 50 5678

# Set SCHED_DEADLINE (runtime/period/deadline in microseconds)
chrt -d --sched-runtime 2000 --sched-deadline 8000 --sched-period 10000 0 ./my_deadline_task
```

### Programmatic Example (C)

```c
#include <sched.h>
#include <stdio.h>
#include <unistd.h>

int main() {
    struct sched_param param;
    param.sched_priority = 80;  // Range 1-99 for real-time

    // Set SCHED_FIFO
    if (sched_setscheduler(0, SCHED_FIFO, &param) == -1) {
        perror("sched_setscheduler failed");
        return 1;
    }

    // Verify
    int policy = sched_getscheduler(0);
    printf("Policy: %d (FIFO=%d, RR=%d, OTHER=%d)\n",
           policy, SCHED_FIFO, SCHED_RR, SCHED_OTHER);
    return 0;
}
```

### Kernel Configuration Check

```bash
# Verify real-time group scheduling is enabled
zcat /proc/config.gz | grep RT_GROUP_SCHED
# CONFIG_RT_GROUP_SCHED=y

# Check if deadline scheduler is available
zcat /proc/config.gz | grep SCHED_DEADLINE
# CONFIG_SCHED_DEADLINE=y
```

## Common Pitfalls & Gotchas

1. **Priority inversion without PI mutexes**: If a low-priority FIFO task holds a mutex that a high-priority FIFO task needs, the high-priority task blocks indefinitely. Always use `pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT)` to enable priority inheritance. Without it, you'll see mysterious latency spikes.

2. **SCHED_FIFO priority 99 can lock up your system**: A FIFO task at priority 99 that never blocks (e.g., a busy loop) will starve everything—including the shell and SSH. Always include a `sched_yield()` or blocking call in real-time loops, or use SCHED_DEADLINE which has built-in bandwidth enforcement.

3. **Deadline scheduling requires root or `CAP_SYS_NICE`**: Unlike FIFO/RR which can be set by non-root users with `ulimit -r`, SCHED_DEADLINE is restricted. Run your deadline tasks as root or set the capability: `setcap cap_sys_nice=ep ./my_deadline_binary`.

4. **CFS and real-time policies don't mix on the same CPU**: If you pin a FIFO task to CPU 0, and a CFS task is also on CPU 0, the FIFO task will preempt the CFS task. But the CFS task might have been holding a spinlock. This is why PREEMPT_RT converts spinlocks to mutexes—to avoid priority inversion at the kernel level.

## Try It Yourself

1. **Measure context switch latency**: Write a simple FIFO task that toggles a GPIO pin and measure the jitter with `trace-cmd`. Compare SCHED_FIFO vs SCHED_OTHER. You'll see CFS jitter in the millisecond range, FIFO in microseconds.

2. **Create a priority inversion scenario**: Write two threads—one high-priority FIFO (priority 80) and one low-priority FIFO (priority 20). Have them share a non-PI mutex. Observe the high-priority thread blocking. Then switch to `PTHREAD_PRIO_INHERIT` and see the difference.

3. **Test SCHED_DEADLINE bandwidth enforcement**: Write a task that requests 5 ms runtime every 10 ms period, but actually tries to run for 8 ms. The kernel will throttle it. Check `/proc/<pid>/sched` for `dl_throttled` count.

## Next Up: PREEMPT_RT Patch: What It Changes & How to Apply It

Tomorrow I'll apply the PREEMPT_RT patch to a kernel and show exactly what changes—spinlock-to-mutex conversion, interrupt threading, and how it transforms the scheduler from "fair" to "deterministic." We'll build a real-time kernel from source and measure the difference.
