---
title: "Day 07: perf stat: Cycle Counting & CPI Analysis"
date: 2026-06-19
tags: ["til", "ebpf", "perf", "stat", "cpi"]
---

## What I Explored Today

Today I dug into `perf stat` for cycle-accurate performance analysis, focusing on Cycles Per Instruction (CPI) as a first-principles metric. While most engineers reach for `perf record` and flame graphs immediately, `perf stat` gives you the hardware-level pulse of your workload without the overhead of sampling. I spent the morning running cycle counts against a memcpy-heavy workload, then cross-referencing with cache misses and branch mispredictions to understand *why* CPI was high. The key insight: CPI isn't just a number—it's a diagnostic that tells you exactly where the CPU is stalled.

## The Core Concept

CPI (Cycles Per Instruction) is the inverse of IPC (Instructions Per Cycle). Modern superscalar CPUs can retire multiple instructions per cycle, so a CPI of 0.25 means you're averaging 4 instructions per cycle—excellent. A CPI of 2.0+ means the pipeline is stalling badly. The beauty of CPI is that it normalizes across different instruction mixes: a tight loop of integer arithmetic might hit CPI 0.5, while a pointer-chasing linked list traversal might hit CPI 3.0 due to cache misses.

The real power comes from breaking CPI down into its components using the "top-down microarchitecture analysis" method. The CPU pipeline has four main stall categories:
- **Front-end bound**: instruction fetch/decode bottlenecks (icache misses, TLB misses)
- **Back-end bound**: execution resource stalls (cache misses, store buffer full)
- **Bad speculation**: branch mispredictions that flush the pipeline
- **Retiring**: actual useful work (but high here with low efficiency means heavy microcode assists)

`perf stat` gives you the raw cycle and instruction counts. With the right events, you can attribute those cycles to specific stall reasons.

## Key Commands / Configuration / Code

### Basic cycle counting
```bash
# Count cycles and instructions for a single command
perf stat -e cycles,instructions ./my_workload

# Output:
# 1,234,567,890      cycles
# 2,345,678,901      instructions
# CPI = cycles / instructions = 0.53
```

### Automatic CPI calculation
```bash
# perf stat already computes IPC for you
perf stat ./my_workload

# Look for "insn per cycle" in the output
```

### Top-down analysis on Intel
```bash
# Requires kernel 4.15+ and perf 4.14+
perf stat --topdown ./my_workload

# Example output:
#  retiring      bad speculation   frontend bound   backend bound
#  45.2%         8.3%              12.1%            34.4%
```

### Custom event groups for stall breakdown
```bash
# Measure L1 misses, branch mispredicts, and cycles together
perf stat -e cycles,instructions,L1-dcache-load-misses,branch-misses \
  ./my_workload

# Calculate CPI contributions:
# L1 miss penalty ~10 cycles each
# Branch miss penalty ~15 cycles each
```

### System-wide monitoring with interval
```bash
# Watch CPI change over time (1-second intervals)
perf stat -I 1000 -e cycles,instructions -a sleep 10
```

### Using `perf stat` with specific PID
```bash
# Attach to running process
perf stat -p $(pgrep my_app) sleep 5
```

## Common Pitfalls & Gotchas

**1. Don't trust single-run CPI for short workloads**
If your workload runs for less than 100ms, `perf stat` may not have enough samples for accurate counts. Always run for at least 1 second, or use `--repeat N` to average multiple runs:
```bash
perf stat -r 10 -e cycles,instructions ./short_workload
```

**2. Virtualization skews cycle counts**
On cloud VMs (especially AWS Nitro or GCP), the `cycles` event may count host cycles, not guest cycles. You'll see wildly different CPI between bare metal and VM. Use `cpu-cycles` instead of `cycles` on some kernels, or better, test on bare metal for microarchitecture analysis.

**3. Frequency scaling makes cycle counts misleading**
If your CPU is in powersave mode (scaling governor = powersave), cycles are slower. Always pin frequency or use `performance` governor:
```bash
# Check current governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Set to performance (requires root)
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

**4. Hyperthreading inflates instruction counts**
On a hyperthreaded core, `instructions` counts both hardware threads. If your workload is single-threaded but the sibling thread is running something else, your CPI will look artificially good (more instructions per cycle than actually executed by your code). Use `taskset` to pin to a specific core and disable the sibling.

## Try It Yourself

**Task 1: Compare CPI of sequential vs random memory access**
Write two small C programs: one that sums a large array sequentially, another that sums it with random access (pointer chasing). Run `perf stat` on both and compare CPI. The random access version should show 3-5x higher CPI due to cache misses.

**Task 2: Break down CPI with top-down analysis**
Run `perf stat --topdown` on a CPU-bound workload (e.g., `openssl speed aes-128-cbc`). Identify which bottleneck category dominates. Then try `perf stat --topdown -e L1-dcache-load-misses` to correlate backend bound with cache misses.

**Task 3: Measure CPI impact of branch mispredictions**
Write a function that sorts an array of random integers, then searches it with a binary search. Compare CPI with and without `__builtin_expect` hints. Use `perf stat -e branch-misses,cycles,instructions` to see if the hints actually reduce mispredictions.

## Next Up

Tomorrow: **Flame Graphs: Visualizing perf Stack Traces** — We'll take the raw stack samples from `perf record` and turn them into the iconic flame graph visualization that makes bottleneck identification intuitive. You'll learn how to generate SVG flame graphs, interpret the "icicle" patterns, and find the hot functions that are burning your CPU cycles.
