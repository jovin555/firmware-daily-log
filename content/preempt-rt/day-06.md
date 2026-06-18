---
title: "Day 06: hackbench & stress-ng: Generating Realistic Load"
date: 2026-06-18
tags: ["til", "preempt-rt", "hackbench", "stress", "load"]
---

## What I Explored Today

Today I focused on the practical side of load generation for PREEMPT_RT testing. It's one thing to run cyclictest on an idle system—it's another to see how your real-time latencies hold up when the system is under realistic stress. I spent the day with `hackbench` and `stress-ng`, two tools that create reproducible, configurable workloads. The goal was to understand what each tool actually does to the kernel scheduler and memory subsystem, and how to combine them with cyclictest for meaningful measurements.

## The Core Concept

The fundamental challenge in real-time testing is that *idle systems lie*. A kernel that delivers 10 µs maximum latency at idle might jump to 500 µs under a moderate scheduler or memory load. If you're shipping a product that runs audio processing, motor control, or data acquisition, the system will never be idle. You need to know the worst-case latency under the exact types of load your application will encounter.

`hackbench` and `stress-ng` serve different purposes here. `hackbench` is a scheduler torture test—it spawns pairs of processes or threads that pass messages back and forth via pipes or sockets. This creates heavy context-switch and wake-up latency pressure, which is exactly what PREEMPT_RT aims to minimize. `stress-ng` is a broader tool: it can hammer CPU caches, memory bandwidth, I/O, and even specific kernel subsystems like futexes or file descriptors. The key insight is that different loads stress different parts of the real-time path. A cache-miss storm from `stress-ng` might expose a different latency source than a scheduler overload from `hackbench`.

## Key Commands / Configuration / Code

### Basic hackbench usage

```bash
# Default: 100 pairs of processes, using pipes
hackbench

# Threads instead of processes (lighter weight, tests different scheduler paths)
hackbench --threads

# Control the number of message-passing groups
hackbench -g 20 -l 1000   # 20 groups, 1000 loops each

# Run for a fixed duration (seconds)
hackbench -T 30            # Run for 30 seconds
```

### stress-ng for targeted load

```bash
# CPU-bound: matrix multiplication (cache thrashing)
stress-ng --matrix 4 --matrix-size 256 --timeout 30s

# Memory bandwidth: streaming memory copies
stress-ng --memcpy 4 --memcpy-method all --timeout 30s

# I/O pressure: sync writes to temp files
stress-ng --hdd 2 --hdd-bytes 1G --timeout 30s

# Combined: CPU + memory + I/O (most realistic)
stress-ng --cpu 2 --vm 2 --hdd 1 --timeout 60s
```

### Running cyclictest under load

```bash
# Terminal 1: Start the load
stress-ng --matrix 4 --timeout 120s &

# Terminal 2: Run cyclictest with histogram
sudo cyclictest --mlockall --priority=95 --interval=1000 \
    --distance=0 --histogram=1000 --histfile=latency_under_load.txt \
    --duration=60s
```

The `--mlockall` flag is critical here—it locks cyclictest's memory to prevent page faults from skewing your measurements. Without it, you're measuring page fault latency, not scheduler latency.

### Combining both tools for maximum stress

```bash
# Heavy scheduler + memory pressure
hackbench -g 50 -T 60 &
stress-ng --vm 4 --vm-bytes 512M --matrix 2 --timeout 60s &
sudo cyclictest --mlockall --priority=95 --interval=1000 \
    --histogram=500 --duration=60s
```

## Common Pitfalls & Gotchas

1. **Not pinning cyclictest to a dedicated CPU.** If cyclictest shares a CPU with hackbench or stress-ng, it will be preempted by the load generators. Always use `taskset` or cgroups to isolate cyclictest to a core that isn't under load. For example: `taskset -c 0 sudo cyclictest ...` while running load on cores 1-3.

2. **Forgetting that `stress-ng` defaults can be misleading.** The default `--cpu` stressor uses busy loops that don't actually stress the memory hierarchy. If you want to test cache effects, you need `--matrix` or `--stream`. Similarly, `--vm` without `--vm-bytes` allocates tiny chunks. Always specify the memory footprint that matches your application.

3. **Running load for too short a duration.** Real-time latency outliers can be rare. A 10-second test might miss a worst-case that occurs every 30 seconds. I've learned to run load tests for at least 60 seconds, and ideally 5-10 minutes for production validation. The histogram output from cyclictest will show you the distribution—if the max keeps climbing, you haven't run long enough.

## Try It Yourself

1. **Compare idle vs. loaded latency.** Run cyclictest for 60 seconds on an idle system, then run it again with `hackbench -g 20 -T 60` running on a different core. Compare the max latency and the histogram tail. You'll likely see a 2-5x increase.

2. **Isolate the worst stressor.** Run cyclictest under three separate loads: `stress-ng --matrix 4`, `stress-ng --vm 4 --vm-bytes 512M`, and `hackbench -g 50`. Which one causes the highest max latency? Which causes the most jitter (variance in the histogram)?

3. **Test with and without PREEMPT_RT.** If you have a non-RT kernel available, run the same load+cyclictest combination on both kernels. Document the difference in max latency and the shape of the histogram. This is the most convincing demonstration of PREEMPT_RT's value.

## Next Up

Tomorrow we dive into **Latency Histograms: Interpreting cyclictest Output**. We'll break down what those columns of numbers actually mean, how to spot cache effects vs. scheduler issues, and how to use the histogram to diagnose specific kernel bottlenecks. Bring your worst cyclictest logs—we're going to read them like a real-time detective.
