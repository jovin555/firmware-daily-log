---
title: "Day 23: cyclictest: Measuring Worst-Case Latency"
date: 2026-07-05
tags: ["til", "preempt-rt", "cyclictest", "latency", "measurement"]
---

## What I Explored Today

Today I dug deep into `cyclictest`, the de facto standard tool for measuring scheduling latency on PREEMPT_RT systems. While I've run it before as a quick "is my kernel real-time?" check, I spent today understanding its internals, interpreting its output correctly, and learning how to design a measurement campaign that reveals true worst-case latency rather than just a pretty histogram.

## The Core Concept

`cyclictest` measures the time difference between *when a thread was supposed to wake up* and *when it actually woke up*. That difference is the scheduling latency — the delay introduced by the kernel's scheduler, interrupt handling, and any interference from other tasks.

The key insight: **latency is not a single number**. It's a distribution. The mean is nearly irrelevant for real-time systems; the *worst-case* (max) latency is what matters, and even that is probabilistic. A system that runs for 10 minutes with a 50 µs max might hit 200 µs on hour three when a cache miss aligns with an NMI handler.

`cyclictest` works by creating one or more real-time threads (SCHED_FIFO by default), each sleeping for a fixed interval (e.g., 100 µs), then measuring the delta between the expected wakeup time and the actual `clock_gettime()` value. It tracks min, max, and a running histogram of these deltas.

The tool is deceptively simple — it's just a tight loop of `clock_nanosleep()` followed by `clock_gettime()`. But the measurement itself can perturb the system if not configured carefully. Running with too high a priority or too short an interval can starve other critical tasks, making your latency numbers worse than reality.

## Key Commands / Configuration / Code

### Basic Latency Measurement
```bash
# Run with 1 thread, 100us interval, SCHED_FIFO priority 99
# -n uses clock_nanosleep for better precision
# -m locks memory to prevent page faults
cyclictest -t 1 -p 99 -i 100 -n -m -l 1000000
```

### Multi-Core Stress Test
```bash
# Pin thread to CPU 2, run for 1 hour (3600 seconds)
# -a 2 pins affinity, -D 3600 sets duration
# -h 1000 creates histogram with 1000 buckets (1us each)
cyclictest -t 1 -p 95 -i 200 -n -m -a 2 -D 3600 -h 1000
```

### Interpreting Output
```
# T: 0 (0) P: 95 I: 200 C: 18000000 Min: 2 Act: 5 Avg: 4 Max: 47
```
- `T: 0` — Thread number (0-indexed)
- `P: 95` — Priority
- `I: 200` — Interval in microseconds
- `C: 18000000` — Number of cycles completed
- `Min: 2` — Minimum observed latency (µs)
- `Act: 5` — Current/actual latency (µs)
- `Avg: 4` — Average latency (µs)
- `Max: 47` — **Worst-case latency** (µs) — this is your headline number

### Generating Histogram Data
```bash
# Run and dump histogram to file for post-processing
cyclictest -t 1 -p 95 -i 200 -n -m -D 3600 -h 2000 \
  --histfile=/tmp/latency_hist.txt

# Plot with gnuplot (or import into Python)
gnuplot -e "set terminal png; \
  plot '/tmp/latency_hist.txt' using 1:2 with lines" > latency.png
```

### Custom Test: Background Load + cyclictest
```bash
# Run cyclictest on CPU 2 while hammering CPU 0 and 1
taskset -c 2 cyclictest -t 1 -p 95 -i 200 -n -m -D 300 -h 2000 &
taskset -c 0 stress-ng --cpu 1 --cpu-method matrixprod -t 300 &
taskset -c 1 stress-ng --cpu 1 --cpu-method fft -t 300 &
wait
```

## Common Pitfalls & Gotchas

### 1. Running cyclictest at Priority 99 on the Wrong CPU
Priority 99 is the highest SCHED_FIFO priority. If you pin cyclictest to the same CPU as your real-time application, you're measuring *your own test tool's* latency, not the system's. Always pin cyclictest to a dedicated isolation CPU (e.g., `isolcpus=2` in kernel cmdline) or at least a CPU not running critical tasks.

### 2. Ignoring the First Few Minutes
Many systems show artificially low latency for the first 5-10 minutes. Caches are warm, page faults have settled, and thermal throttling hasn't kicked in. A 24-hour run is standard for certification; a 1-hour run is the absolute minimum for development sanity checks. I once saw a system that ran clean for 55 minutes, then hit a 500 µs spike during a background cron job.

### 3. Misinterpreting the Histogram Buckets
The `-h 1000` flag creates 1000 buckets, each 1 µs wide by default. If your max latency is 47 µs, you only used 47 of 1000 buckets — that's fine. But if your max is 2500 µs and you only allocated 1000 buckets, cyclictest silently drops samples above bucket 999. Always set `-h` to at least 2x your expected worst case. When in doubt, use `-h 10000` (10 ms range) and trim later.

## Try It Yourself

1. **Baseline measurement**: Run `cyclictest -t 1 -p 95 -i 200 -n -m -D 600 -h 2000` on an idle system. Record the Max value. Then run the same command with `stress-ng --cpu 4` in the background. Compare the Max values. What's the degradation?

2. **Histogram analysis**: Run a 1-hour test with `--histfile` output. Write a Python script that reads the histogram and computes the 99.9th percentile latency. How does it compare to the absolute Max? (Hint: the 99.9th is often much more stable across runs.)

3. **Priority inversion test**: Create two cyclictest threads at different priorities on the same CPU: `cyclictest -t 2 -p 80:50 -i 200:200 -n -m -D 300`. The lower-priority thread will show higher latency because it's preempted by the higher-priority thread. This demonstrates why priority assignment matters in real systems.

## Next Up

Tomorrow we'll put our cyclictest setup to work with **hackbench & stress-ng: Generating Realistic Load**. We'll explore how to create controlled interference patterns — CPU-bound, memory-bound, and I/O-bound — to stress-test your latency bounds under conditions that actually resemble production workloads.
