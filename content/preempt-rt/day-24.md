---
title: "Day 24: hackbench & stress-ng: Generating Realistic Load"
date: 2026-07-06
tags: ["til", "preempt-rt", "hackbench", "stress", "load"]
---

## What I Explored Today

Today I focused on the practical art of generating realistic system load for PREEMPT_RT testing. While cyclictest gives us latency numbers, those numbers are meaningless without a representative workload stressing the system. I spent the day benchmarking with `hackbench` (a scheduler stress tool) and `stress-ng` (a comprehensive stress framework), learning how to craft load profiles that mimic real embedded workloads—network processing, disk I/O, memory pressure, and interrupt storms.

## The Core Concept

The fundamental problem in real-time testing is that a system under no load will always show excellent latency. The real question is: *what happens when the system is busy?* Generating realistic load isn't about just making the CPU busy—it's about creating the specific contention patterns that trigger priority inversion, cache thrashing, and interrupt latency spikes.

`hackbench` is deceptively simple: it creates pairs of tasks that pass messages back and forth via pipes or sockets. This stresses the scheduler's ability to handle frequent context switches and wake-up latencies. It's the closest thing to a "real-time worst-case" workload for scheduler testing.

`stress-ng` is the Swiss Army knife. It can hammer specific subsystems: CPU caches, memory bandwidth, disk I/O, file system metadata, network sockets, and even kernel futex contention. The trick is combining stressors to match your actual deployment scenario—a camera processing pipeline has different stress patterns than an industrial PLC.

The key insight: you want to measure latency *while* the system is under load that exercises the same kernel paths your real-time tasks will contend with. Running cyclictest with `stress-ng --cpu 0` (just CPU burn) will miss the real problems caused by memory pressure or interrupt storms.

## Key Commands / Configuration / Code

### Basic hackbench for scheduler stress

```bash
# Run hackbench with 40 groups (80 tasks) via pipes
# -P: use processes (not threads) for worst-case scheduling
# -l 100000: loop count for sustained load
hackbench -P -l 100000 -g 40

# Socket-based variant (stresses networking stack too)
hackbench -P -s -l 100000 -g 20

# Run alongside cyclictest (background)
hackbench -P -l 50000 -g 20 &
cyclictest -t1 -p99 -i 1000 -l 100000 -m -n
```

### stress-ng for targeted subsystem load

```bash
# CPU + cache + memory bandwidth stress
# --cache 4: 4 cache thrashing workers
# --memthrash 2: memory thrashing workers
# --vm 2: virtual memory pressure
stress-ng --cpu 4 --cache 4 --memthrash 2 --vm 2 --vm-bytes 75% --timeout 60s

# I/O + interrupt stress (common in embedded)
# --hdd 2: disk write stress
# --aio 2: async I/O workers
# --timer 8: timer interrupt generators
stress-ng --hdd 2 --hdd-bytes 4G --aio 2 --timer 8 --timeout 60s

# Mixed workload: network + futex + file system
# --sock 4: socket pair stress
# --futex 4: futex contention
# --fallocate 2: file allocation stress
stress-ng --sock 4 --futex 4 --fallocate 2 --timeout 60s
```

### Combining stressors with cyclictest

```bash
#!/bin/bash
# Realistic load profile for a network camera system
stress-ng \
  --cpu 2 \           # Image processing threads
  --cache 2 \         # Cache thrashing from pixel data
  --sock 4 \          # Network streaming
  --hdd 1 --hdd-bytes 1G \  # Recording to disk
  --timer 4 \         # Periodic sensor interrupts
  --timeout 120s &

# Run cyclictest with histogram output
cyclictest -t1 -p99 -i 1000 -l 120000 -m -n \
  --histogram=latency_hist.txt \
  --histofall=latency_fall.txt

wait
```

### Parsing results for worst-case analysis

```bash
# Extract max latency from cyclictest output
grep "Max Latencies" /dev/cyclictest | awk '{print $NF}'

# Find the 99.9th percentile from histogram
awk 'NR>1 && $1>0 {sum+=$2; if (sum >= total*0.999) {print $1; exit}}' \
  total=$(awk 'NR>1 {s+=$2} END{print s}' latency_hist.txt) \
  latency_hist.txt
```

## Common Pitfalls & Gotchas

**1. Running stressors on isolated CPUs**
If you've isolated CPUs for real-time tasks (via `isolcpus` or `cpuset`), running `stress-ng --cpu 0` will only stress the housekeeping CPU. Always pin stressors to the same CPUs your real-time tasks will run on, or use `--taskset` to force them onto isolated cores. Otherwise you're measuring an empty system.

**2. Forgetting memory bandwidth saturation**
CPU-bound stress doesn't touch memory bandwidth. Many real-time systems are memory-bandwidth-bound (think video processing). Use `stress-ng --memthrash` or `--stream` to saturate memory channels. I've seen latency jump from 5μs to 200μs just by adding memory pressure.

**3. Ignoring interrupt affinity**
`stress-ng --timer` generates timer interrupts, but they may land on any CPU. Check `/proc/interrupts` to see where they're delivered. If your real-time task is on CPU2 and timer interrupts are also on CPU2, you'll see inflated latencies. Use `irqbalance` or manual IRQ affinity to move interrupts away from critical CPUs.

## Try It Yourself

1. **Baseline vs. loaded comparison**: Run `cyclictest -t1 -p99 -i 1000 -l 50000 -m -n` with no load, then with `hackbench -P -g 20 -l 50000` in the background. Compare max latencies. The difference is your scheduler-induced latency penalty.

2. **Memory bandwidth test**: Run `cyclictest` with `stress-ng --memthrash 2 --vm 2 --vm-bytes 50%` in parallel. Then add `--cache 4` and observe how cache thrashing compounds the latency. Record the 99.9th percentile for each case.

3. **Custom workload profile**: Design a stress profile that mimics your target system (e.g., network server: `--sock 8 --futex 4 --cpu 2`). Run cyclictest for 10 minutes. Then add one more stressor (like `--hdd 2`) and see which subsystem causes the biggest latency spike.

## Next Up

Tomorrow: **Latency Histograms: Interpreting cyclictest Output** — raw max latency numbers hide the real story. We'll dive into histogram analysis, learn to spot bimodal distributions, and identify whether your latency spikes come from scheduler jitter, interrupt storms, or priority inversion.
