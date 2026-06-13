---
title: "Day 01: What Makes a System Real-Time? WCET, Jitter & Latency"
date: 2026-06-13
tags: ["til", "preempt-rt", "real-time", "wcet", "latency"]
---

## What I Explored Today

Today I dug into the foundational question: what actually makes a system "real-time"? It's not about speed—it's about predictability. I explored the three pillars that define real-time behavior: Worst-Case Execution Time (WCET), jitter, and latency. Understanding these concepts is critical before we touch a single kernel config or PREEMPT_RT patch, because they form the vocabulary we'll use to measure and debug everything going forward.

## The Core Concept

A real-time system guarantees that a task will complete within a specified deadline. The key word is *guarantee*, not *fast*. A stock Linux kernel can often respond in microseconds, but occasionally it might take milliseconds—that unpredictability is fatal for applications like CNC controllers, avionics, or audio processing.

Three metrics define real-time behavior:

- **Latency**: The time between an event (e.g., interrupt from a sensor) and the start of the task that handles it. This includes interrupt masking, scheduler overhead, and cache misses. In real-time systems, we care about *maximum* latency, not average.

- **Jitter**: The variation in latency or task completion time across multiple cycles. Low jitter means the system behaves consistently. High jitter means the system is unpredictable—even if the average latency looks good.

- **WCET (Worst-Case Execution Time)**: The maximum time a task takes to run on a given hardware platform, assuming worst-case conditions (cache misses, bus contention, etc.). This is the hardest number to measure because you can't test every possible state. Engineers often over-provision by 20-50% to account for unknowns.

The relationship is simple: `deadline > WCET + worst-case latency`. If you can't bound these values, you don't have a real-time system—you have a fast system that occasionally fails.

## Key Commands / Configuration / Code

Let's get practical. Here's how you start measuring these metrics on a running Linux system.

### 1. Measuring Scheduling Latency with `cyclictest`

`cyclictest` is the gold standard for measuring real-time performance. It measures the difference between when a thread *should* wake up and when it *actually* wakes up.

```bash
# Run cyclictest with 1 thread, 1000us interval, 10000 iterations
# -p 99: SCHED_FIFO priority 99 (highest)
# -n: use clock_nanosleep
# -l 10000: stop after 10000 samples
sudo cyclictest -p 99 -n -l 10000 -i 1000

# Output example (trimmed):
# T: 0 (12345) P: 99 I: 1000 Min: 2 Act: 3 Avg: 4 Max: 18
# Min=2us, Max=18us — that's your worst-case scheduling latency
```

The `Max` value is your measured worst-case latency. On a stock kernel, you might see Max spike to 500+ us. On a PREEMPT_RT kernel, it should stay under 50 us on decent hardware.

### 2. Measuring Interrupt Latency with `hwlatdetect`

Interrupt latency is the time from hardware interrupt assertion to the first instruction of the handler. `hwlatdetect` uses a hardware timer to measure this directly.

```bash
# Load the hwlat detector module
sudo modprobe hwlat_detector

# Check the results (in microseconds)
cat /sys/kernel/debug/hwlat_detector/state
# Sample output: "window=1000000 width=500000 latency=12"
# latency=12 means max interrupt latency was 12us
```

### 3. Estimating WCET with `perf`

WCET estimation is complex, but `perf stat` gives you a starting point by measuring execution time variance.

```c
// wcet_test.c — a simple task to measure
#include <stdio.h>
#include <time.h>

void critical_task() {
    volatile int sum = 0;
    for (int i = 0; i < 10000; i++) {
        sum += i * i;  // worst-case: all cache misses
    }
}

int main() {
    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);
    critical_task();
    clock_gettime(CLOCK_MONOTONIC, &end);
    long elapsed = (end.tv_sec - start.tv_sec) * 1e9 +
                   (end.tv_nsec - start.tv_nsec);
    printf("Execution time: %ld ns\n", elapsed);
    return 0;
}
```

```bash
# Compile and run with perf to see variance
gcc -O0 -o wcet_test wcet_test.c
perf stat -e cycles,instructions,cache-misses ./wcet_test
# Run 1000 times and take the max
for i in $(seq 1 1000); do ./wcet_test; done | sort -n | tail -1
```

## Common Pitfalls & Gotchas

1. **Confusing average with worst-case.** I've seen engineers run `cyclictest` for 10 seconds, see Max=30us, and declare victory. Real-time requires running for hours or days. Thermal throttling, kernel housekeeping, and hardware interrupts can cause rare spikes. Always test for at least 24 hours in production-like conditions.

2. **Ignoring cache effects.** Your WCET measurement on a warm cache might be 10x faster than on a cold cache. A context switch can flush the TLB and L1 cache. Always measure with cache misses forced (e.g., by touching a large array before your task).

3. **Assuming `sched_setattr` works without RT permissions.** You need `CAP_SYS_NICE` or root to set `SCHED_FIFO` or `SCHED_DEADLINE`. Without it, the call silently fails or uses `SCHED_OTHER`. Always check the return value:

```c
struct sched_attr attr = { .size = sizeof(attr), .sched_policy = SCHED_FIFO, .sched_priority = 99 };
if (sched_setattr(0, &attr, 0) == -1) {
    perror("sched_setattr failed — are you root?");
}
```

## Try It Yourself

1. **Measure your current latency baseline.** Run `sudo cyclictest -p 99 -n -l 100000 -i 1000` on a stock kernel. Note the Max value. Then run it again while compiling a kernel (`make -j4`) in another terminal. How much does the Max spike?

2. **Write a WCET measurement script.** Take the `wcet_test.c` above, run it 10,000 times, and record the min, max, and standard deviation. Plot the distribution with `gnuplot` or Python. Is it a normal distribution or does it have long tails?

3. **Check your kernel's current real-time capabilities.** Run `uname -r` and check if PREEMPT_RT is enabled: `zcat /proc/config.gz | grep PREEMPT`. If you see `CONFIG_PREEMPT_RT=y`, you're on a real-time kernel. If not, note that for Day 3 when we build one.

## Next Up

Tomorrow: **Linux Scheduling: CFS, FIFO, RR & Deadline Policies**. We'll break down how the Linux scheduler decides which task runs next, why `SCHED_FIFO` priority 99 isn't always the answer, and how the new `SCHED_DEADLINE` policy gives you hard guarantees. Bring your `sched_setattr` man page.
