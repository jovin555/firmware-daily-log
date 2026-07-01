---
title: "Day 19: What Makes a System Real-Time? WCET, Jitter & Latency"
date: 2026-07-01
tags: ["til", "preempt-rt", "real-time", "wcet", "latency"]
---

## What I Explored Today

After weeks of building and configuring PREEMPT_RT kernels, today I stepped back to answer a fundamental question: what *actually* makes a system real-time? It's not just about speed—it's about determinism. I dug into the three pillars of real-time analysis: Worst-Case Execution Time (WCET), jitter, and latency. These metrics separate a system that "usually works" from one that can guarantee a deadline. Without understanding these, you're just tuning a kernel blindfolded.

## The Core Concept

A real-time system is not a fast system—it's a *predictable* system. The key distinction is between *hard* real-time (missing a deadline is a system failure) and *soft* real-time (occasional misses degrade quality but don't break the system). PREEMPT_RT targets soft real-time for Linux, but the analysis tools apply to both.

Three metrics define real-time behavior:

1. **Latency** — The total time from an event (e.g., interrupt) to the completion of the response. This includes interrupt latency, scheduling latency, and execution time. In PREEMPT_RT, we measure this with tools like `cyclictest`.

2. **Jitter** — The variation in latency across multiple events. Low jitter means consistent timing. High jitter means the system is unpredictable. For a control loop sampling at 1 kHz, jitter of 100 µs might be acceptable; jitter of 1 ms means missed samples.

3. **WCET (Worst-Case Execution Time)** — The maximum time a task takes to execute on a given hardware platform. This is not the average—it's the absolute worst case, accounting for cache misses, pipeline stalls, interrupts, and memory contention. WCET analysis is the hardest part because you must consider every possible system state.

The relationship is simple: `deadline > latency + WCET + jitter`. If you can't guarantee this inequality for every execution, your system is not real-time.

## Key Commands / Configuration / Code

### Measuring Latency and Jitter with cyclictest

The standard tool for measuring real-time latency on Linux is `cyclictest` (from the `rt-tests` package). It measures the difference between when a thread *should* wake up and when it *actually* wakes up.

```bash
# Run cyclictest with 1 thread, 1 ms interval, 10000 iterations
# -p 99: FIFO priority 99 (highest)
# -n: use clock_nanosleep
# -l 10000: stop after 10k samples
# --histogram=100: print histogram with 100 bins (each bin = 1 us)
sudo cyclictest -p 99 -n -l 10000 --histogram=100

# Output snippet (simplified):
# T: 0 (12345) P: 99 I: 1000 Min: 2 Act: 5 Avg: 4 Max: 47
# Min=2us, Max=47us, Avg=4us — jitter = Max - Min = 45us
```

The `Max` value is your observed worst-case latency. If it's consistently below your deadline, you're in good shape. If it spikes (e.g., 47 µs to 500 µs), you have a jitter problem.

### Measuring Interrupt Latency with hwlatdetect

`hwlatdetect` (also from `rt-tests`) measures hardware-induced latency by polling the TSC (Time Stamp Counter) in a tight loop. This isolates hardware issues (SMIs, C-state transitions) from software scheduling.

```bash
# Run for 60 seconds, threshold 10 us
sudo hwlatdetect --duration=60 --threshold=10

# Output:
# Hardware latency: 12 us (above threshold 10 us)
# This means the hardware delayed execution by 12 us — likely an SMI
```

### Simple WCET Estimation (Static Analysis)

For embedded systems, you can use `aiT` (commercial) or `OTAWA` (open-source) for static WCET analysis. But for a quick empirical estimate, use `perf` to measure execution time under stress:

```bash
# Compile your real-time task with -O2 and no debug symbols
gcc -O2 -o rt_task rt_task.c -lrt

# Run under heavy load to stress caches and memory bus
stress --cpu 4 --io 2 --vm 2 --vm-bytes 128M &
perf stat -e cycles,instructions,cache-misses ./rt_task

# Look at max execution time from multiple runs
for i in {1..100}; do
    perf stat -o /tmp/perf_$i.log ./rt_task
done
# Then grep for "seconds time elapsed" and find the max
```

## Common Pitfalls & Gotchas

1. **Confusing average latency with worst-case latency.** Your system might average 5 µs, but if the max is 500 µs, you have a problem. Always measure the *max*, not the mean. `cyclictest` reports both—ignore the average for real-time guarantees.

2. **Ignoring hardware-induced latency (SMIs, C-states).** System Management Interrupts (SMIs) can pause the CPU for hundreds of microseconds. Disable them in BIOS (look for "SMI" or "C-state" settings) or use `hwlatdetect` to detect them. Also, disable deep C-states with `cpupower idle-set -d 2`.

3. **Assuming PREEMPT_RT eliminates all jitter.** PREEMPT_RT reduces kernel latencies but doesn't fix hardware issues, cache misses, or memory bus contention. A DMA transfer from a GPU can still cause 100 µs delays. Profile your *entire* system, not just the kernel.

## Try It Yourself

1. **Run cyclictest on a stock kernel vs. PREEMPT_RT kernel.** Boot into your standard kernel, run `sudo cyclictest -p 99 -n -l 10000 --histogram=100`, and note the Max latency. Reboot into your PREEMPT_RT kernel and repeat. Compare the histograms—you should see a dramatic reduction in the tail latency (the 99.9th percentile).

2. **Measure interrupt latency with hwlatdetect.** Run `sudo hwlatdetect --duration=120 --threshold=5`. If you see any samples above 10 µs, check your BIOS settings for SMI and C-state controls. Disable them and rerun—note the improvement.

3. **Empirically estimate WCET for a simple loop.** Write a program that does 1000 iterations of a floating-point matrix multiply. Use `perf stat` to measure execution time under three conditions: idle system, under CPU stress (`stress --cpu 4`), and under memory stress (`stress --vm 4 --vm-bytes 256M`). The max across all runs is your empirical WCET.

## Next Up

Tomorrow, we dive into the Linux scheduler itself. We'll compare CFS (Completely Fair Scheduler), FIFO, RR (Round Robin), and the Deadline scheduler—and show you exactly which one to use for your real-time tasks. Hint: FIFO is not always the answer.
