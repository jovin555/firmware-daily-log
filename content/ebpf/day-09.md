---
title: "Day 09: perf sched: Scheduling Latency Analysis"
date: 2026-06-22
tags: ["til", "ebpf", "perf", "scheduling", "latency"]
---

## What I Explored Today

Today I dove into `perf sched`, the Linux perf subsystem's dedicated scheduler profiling tool. While I've used `perf stat` and `perf record` for general profiling, I've never systematically analyzed scheduling latency—the time a task spends waiting on a runqueue before getting CPU time. I spent the morning running `perf sched record` on a busy web server, then used `perf sched latency` and `perf sched timehist` to pinpoint exactly where and why threads were being delayed. The results were eye-opening: a 12ms scheduling latency spike correlated perfectly with a kworker thread hammering a shared spinlock.

## The Core Concept

Scheduling latency matters because it's invisible in most profiling tools. When you look at `perf top`, you see where CPU cycles are spent, but you don't see the time a thread spends *ready to run but not running*. This is the scheduler's "wakeup latency"—the gap between when a task becomes runnable (e.g., after an I/O completion) and when it actually gets scheduled on a core.

The Linux CFS (Completely Fair Scheduler) tries to keep this latency under control, but real-world systems break the guarantees: priority inversion, preempt-off sections, excessive IRQ handling, or simply too many runnable tasks for the available cores. `perf sched` captures every context switch, wakeup, and migration event via tracepoints (`sched:sched_switch`, `sched:sched_wakeup`, etc.), then reconstructs the timeline. The key metric is `sched_latency`—the time from wakeup to first execution. Anything above 1-2ms in a latency-sensitive workload (audio, trading, real-time control) is a red flag.

## Key Commands / Configuration / Code

### 1. Recording scheduler events

```bash
# Record scheduler events for 10 seconds on all CPUs
sudo perf sched record -- sleep 10

# Or record with custom event selection (more precise)
sudo perf sched record -e sched:sched_switch,sched:sched_wakeup,sched:sched_wakeup_new -- sleep 10
```

The `--` separates perf options from the command to trace. Without it, `sleep 10` becomes the workload. The default output file is `perf.data`.

### 2. Latency summary (the "money shot")

```bash
# Show per-task scheduling latency statistics
sudo perf sched latency

# Output snippet (annotated):
# -----------------------------------------------------------------------------------------------------------------
#  Task                  |   Runtime ms  | Switches | Average delay ms | Maximum delay ms | Maximum delay at    |
# -----------------------------------------------------------------------------------------------------------------
#  nginx:worker (1234)   |   4502.345    |   8921   |    0.023         |    12.104        |   3456.789 sec      |
#  kworker/u8:2 (567)    |   1234.567    |   3456   |    0.089         |    11.987        |   3456.789 sec      |
#  mysqld (7890)         |   8901.234    |  12345   |    0.045         |    0.567         |   3456.789 sec      |
# -----------------------------------------------------------------------------------------------------------------
```

The `Average delay ms` column is the mean time between wakeup and first execution. `Maximum delay ms` is your worst-case latency. The `Maximum delay at` timestamp helps correlate with other system events.

### 3. Time-based histogram

```bash
# Show a timeline of scheduling events (useful for correlation)
sudo perf sched timehist -s -p 1234

# -s: show summary statistics per task
# -p: filter to specific PID
```

This outputs a columnar timeline: `comm`, `pid`, `wakeup time`, `runtime`, `delay`, `wait time`. The `delay` column is the scheduler latency we care about.

### 4. Visualizing the scheduler map

```bash
# Generate a visual timeline of CPU ownership
sudo perf sched map

# Output (conceptual):
#    *            .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .   .
#    *            A   A   A   .   B   B   B   B   .   C   C   C   .   A   A   .   .   D   D   D   D   .   .   .
#    *CPU0        A   A   A   .   B   B   B   B   .   C   C   C   .   A   A   .   .   D   D   D   D   .   .   .
#    *CPU1        .   .   .   A   .   .   .   .   B   .   .   .   C   .   .   D   D   .   .   .   .   .   .   .
```

Each column is a time slice (default 1ms). Letters represent tasks. Dots are idle. This is great for spotting "CPU hog" patterns—a single task monopolizing a core while others wait.

### 5. Replaying the scheduler trace

```bash
# Replay the recorded trace to measure theoretical scheduling
sudo perf sched replay
```

This simulates the recorded workload against the scheduler and reports "scheduling overhead" and "total runtime". It's useful for comparing scheduler behavior across kernel versions or configs.

## Common Pitfalls & Gotchas

### 1. Overhead from tracing itself
`perf sched record` captures every context switch. On a busy system (10k+ switches/sec), the trace buffer can overflow, dropping events and producing misleading latency numbers. Always check `perf sched latency` for a warning like "lost 1234 events". If you see it, increase the buffer size: `sudo perf sched record -m 256, -- sleep 10` (256 pages per CPU ring buffer).

### 2. Interpreting "delay" incorrectly
The `delay` column in `perf sched timehist` is the time from *wakeup* to *first execution*, not the total time on the runqueue. If a task is preempted mid-execution, that preemption time shows up as `wait time`, not `delay`. For true end-to-end scheduling latency, sum `delay` + `wait time` for each scheduling quantum.

### 3. Missing wakeup events for kernel threads
Some kernel threads (e.g., `ksoftirqd`, `kworker`) use internal wakeup mechanisms that don't always fire the `sched:sched_wakeup` tracepoint. This leads to underreported latency for those threads. Cross-check with `/proc/<pid>/sched`'s `se.statistics.wait_sum` field for validation.

## Try It Yourself

1. **Find your worst-case scheduler latency**: Run `sudo perf sched record -- sleep 30` on a production-like workload (e.g., `stress --cpu 4 --io 2`), then `sudo perf sched latency`. Identify the task with the highest `Maximum delay ms`. What was it doing? Check `/proc/<pid>/status` for its state.

2. **Correlate latency with CPU affinity**: Pin a latency-sensitive task to a single core (`taskset -c 0 ./your_app`), then run `sudo perf sched timehist -s -p <PID>`. Compare the delay distribution to the unpinned case. Does CPU pinning help or hurt?

3. **Visualize the scheduler map**: Run `sudo perf sched record -- sleep 5` while running `dd if=/dev/zero of=/dev/null bs=1M count=1000` in parallel. Then `sudo perf sched map | head -50`. Can you spot the I/O-bound vs CPU-bound task patterns?

## Next Up

Tomorrow, we go deeper into the eBPF architecture: the BPF virtual machine instruction set, map types (hash, array, per-CPU), and helper functions that make eBPF programs actually useful. We'll write a tiny eBPF program that counts scheduling events—without `perf` at all.
