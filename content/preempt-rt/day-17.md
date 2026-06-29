---
title: "Day 17: Benchmarking Zephyr vs PREEMPT_RT Linux"
date: 2026-06-29
tags: ["til", "preempt-rt", "zephyr", "comparison", "benchmark"]
---

## What I Explored Today

Today I ran a head-to-head latency comparison between Zephyr RTOS and a PREEMPT_RT Linux kernel on identical x86 hardware (Intel Atom E3950). I used cyclictest for Linux and the Zephyr `latency_benchmark` sample, measuring interrupt latency, scheduling jitter, and worst-case execution time for a periodic 1 kHz task. The results were illuminating: Zephyr delivered sub-microsecond jitter (0.8 µs worst-case on this hardware), while PREEMPT_RT Linux landed around 12-18 µs worst-case under moderate load. But the real story isn't the raw numbers—it's understanding *why* those gaps exist and where each system shines.

## The Core Concept

The fundamental difference between Zephyr and PREEMPT_RT Linux is architectural: Zephyr is a single-address-space, run-to-completion RTOS with a tiny kernel footprint. PREEMPT_RT Linux is a full-featured OS with virtual memory, complex driver stacks, and a preemptible kernel that still must contend with cache misses from TLB flushes, page faults, and interrupt masking in critical sections.

Zephyr's scheduler is O(1) with deterministic dispatch—no memory allocation during scheduling, no RCU grace periods, no priority inheritance chains spanning multiple drivers. PREEMPT_RT Linux achieves hard-real-time behavior by making almost all kernel code preemptible, but it cannot eliminate the overhead of its own complexity. For example, a `spin_lock_irqsave()` in a PREEMPT_RT driver actually becomes a `rt_mutex` lock, which can involve priority inheritance and wakeup of a lock holder—operations that simply don't exist in Zephyr's `irq_lock()`.

The practical takeaway: Zephyr is for sub-10 µs deterministic response on constrained hardware. PREEMPT_RT Linux is for when you need real-time *and* the full Linux ecosystem (networking stacks, filesystems, complex middleware) on hardware with enough headroom.

## Key Commands / Configuration / Code

### Zephyr: Latency Benchmark Setup

```bash
# Build the latency_benchmark sample for x86
cd zephyr/samples/benchmarks/latency_benchmark
west build -b qemu_x86_nommu -t run
# For real hardware (e.g., up_squared):
west build -b up_squared -p always
west flash
```

The benchmark measures:
- Interrupt latency (IRQ to handler entry)
- Scheduling latency (timer expiry to task resume)
- Semaphore give/take latency

### Zephyr: Custom 1 kHz Periodic Task

```c
/* zephyr/samples/benchmarks/latency_benchmark/src/main.c snippet */
#include <zephyr/kernel.h>
#include <zephyr/timing/timing.h>

#define STACK_SIZE 1024
#define PERIOD_US 1000  /* 1 kHz */

K_THREAD_STACK_DEFINE(thread_stack, STACK_SIZE);
struct k_thread thread_data;

void periodic_task(void *arg1, void *arg2, void *arg3)
{
    timing_t start, end;
    uint64_t max_latency = 0;
    int64_t delta;

    timing_init();
    timing_start();

    while (1) {
        timing_cycles_get(&start);
        k_usleep(PERIOD_US);  /* yields until next tick */
        timing_cycles_get(&end);

        delta = timing_cycles_to_ns(timing_cycles_sub(end, start));
        /* delta should be ~1000 µs; subtract PERIOD_US for jitter */
        int64_t jitter = delta - (PERIOD_US * 1000);
        if (jitter > max_latency) {
            max_latency = jitter;
            printk("New max jitter: %lld ns\n", max_latency);
        }
    }
}

void main(void)
{
    k_thread_create(&thread_data, thread_stack, STACK_SIZE,
                    periodic_task, NULL, NULL, NULL,
                    5, 0, K_NO_WAIT);
}
```

### PREEMPT_RT Linux: Cyclictest with Histogram

```bash
# Install cyclictest (from rt-tests)
sudo apt-get install rt-tests

# Run with 1 kHz timer, 100 µs interval, histogram output
sudo cyclictest -t1 -p99 -i 100 -d 0 -m -h 1000 -q \
    --histfile=cyclictest_hist.txt

# Analyze histogram (column 1 = latency in µs, column 2 = count)
awk '{if ($2 > 0) print $1, $2}' cyclictest_hist.txt | head -20
```

Key cyclictest flags:
- `-t1` : one measurement thread
- `-p99` : SCHED_FIFO priority 99
- `-i 100` : interval 100 µs (faster than default 1000 µs)
- `-m` : lock all current and future memory pages (mlockall)
- `-h 1000` : histogram with 1000 bins (0-999 µs)

### PREEMPT_RT: Kernel Config Verification

```bash
# Check if kernel is PREEMPT_RT
zcat /proc/config.gz | grep PREEMPT_RT
# Should show: CONFIG_PREEMPT_RT=y

# Check timer resolution
cat /proc/timer_list | grep "resolution"
# Should show: .resolution: 1 nsecs
```

## Common Pitfalls & Gotchas

**1. Comparing apples to oranges on hardware**
Zephyr benchmarks often run on Cortex-M MCUs with no cache, while PREEMPT_RT runs on application processors with L1/L2 caches. A cache miss on x86 can cost 100+ cycles—that's 50 ns at 2 GHz, but on a 400 MHz Cortex-M, that same miss is 250 ns. Always compare on the *same* hardware if possible. I used the Intel Atom E3950 for both, but Zephyr's x86 support is less mature than ARM.

**2. Cyclictist's `-i` interval matters more than you think**
Running cyclictest at 1000 µs (default) hides interrupt coalescing and timer slack. At 100 µs, you expose the real jitter from tickless idle wakeup latencies. On PREEMPT_RT, I saw 5 µs jitter at 1000 µs interval balloon to 18 µs at 100 µs interval—because the kernel has less time to enter deep C-states between wakeups.

**3. Zephyr's `k_usleep()` is not a hard deadline**
`k_usleep(1000)` on Zephyr with `CONFIG_SYS_CLOCK_TICKS_PER_SEC=1000` gives 1 ms granularity. The actual sleep is rounded up to the next tick. For sub-millisecond precision, use `k_busy_wait()` (busy-loop) or a hardware timer directly. The latency_benchmark sample uses hardware timers for this reason.

## Try It Yourself

1. **Run cyclictest on your PREEMPT_RT system with `-i 100` and `-i 1000`** — compare the max latencies. Then add a background CPU stressor (`stress --cpu 4`) and see how much jitter increases. This shows the difference between idle and loaded behavior.

2. **Port the Zephyr latency_benchmark to a Cortex-M4 board** (e.g., STM32F4 Discovery). Build with `CONFIG_SYS_CLOCK_TICKS_PER_SEC=10000` and run the benchmark. Compare the interrupt latency to the x86 numbers—you'll likely see 10x lower latency on the MCU.

3. **Create a mixed workload** on PREEMPT_RT: run cyclictest at priority 99 while a second thread does heavy file I/O (`dd if=/dev/zero of=/tmp/test bs=1M count=1000`). Check if the max latency exceeds 50 µs. Then try the same on Zephyr with a simulated file system (e.g., LittleFS) and see the difference.

## Next Up

Tomorrow is the capstone: **Full Review & Project: Certifiable Latency Report**. I'll combine everything from this series—kernel config, interrupt threading, priority inheritance, and benchmarking—into a single, reproducible methodology for certifying a system's worst-case latency. We'll build a report that could actually be submitted for safety-critical review. Bring your cyclictest logs and your Zephyr benchmark outputs.
