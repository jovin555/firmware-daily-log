---
title: "Day 06: perf record & report: Profiling a Running System"
date: 2026-06-18
tags: ["til", "ebpf", "perf", "profiling", "flamegraph"]
---

## What I Explored Today

Today I dove into the workhorse of Linux performance analysis: `perf record` and `perf report`. While `perf stat` gives you aggregate counters, `perf record` captures samples of what the CPU is actually executing, and `perf report` turns those samples into a browsable profile. I spent the day profiling a production NGINX server under load, generating flamegraphs, and learning how to interpret the hierarchical call stacks that reveal where cycles are really going.

## The Core Concept

The fundamental insight behind statistical profiling is that you don't need to trace every instruction — you just need to sample the program counter (PC) and call stack at regular intervals. If a function is on the stack in 30% of your samples, it's consuming roughly 30% of CPU time. This is the **statistical sampling** approach, and it's remarkably accurate for CPU-bound workloads.

`perf record` works by programming hardware performance counters (typically the `cycles` counter) to generate an interrupt every N events. When the interrupt fires, the kernel records:
- The current instruction pointer (IP)
- The full call stack (via frame pointers or DWARF unwinding)
- The process/thread ID
- Optional: other counters at that instant

The key parameter is the sampling frequency. Too high and you perturb the system (sampling overhead becomes significant). Too low and you miss short-lived hotspots. The default of 4000 Hz (samples per second per CPU) is a good starting point for most workloads.

## Key Commands / Configuration / Code

### Basic profiling session

```bash
# Profile a running process for 30 seconds
sudo perf record -p $(pgrep nginx) -g -- sleep 30

# -p: PID to attach to
# -g: capture call graphs (stack traces)
# sleep 30: duration of profiling

# Generate the report
perf report -i perf.data --stdio

# Interactive TUI mode (default)
perf report -i perf.data
```

### Controlling sample frequency

```bash
# Use frequency-based sampling (default ~4000 Hz)
perf record -F 99 -p $PID -g -- sleep 10

# Use period-based sampling (every 100,000 cycles)
perf record -c 100000 -p $PID -g -- sleep 10

# Profile all CPUs system-wide
perf record -a -g -- sleep 10
```

### Generating flamegraphs

```bash
# Capture with frame pointers (required for reliable stacks)
perf record -F 99 -p $PID --call-graph fp -- sleep 30

# Fold the stacks
perf script -i perf.data | ./stackcollapse-perf.pl > out.folded

# Generate SVG flamegraph
./flamegraph.pl out.folded > flamegraph.svg
```

### Filtering by event

```bash
# Profile only L1 cache misses
perf record -e L1-dcache-load-misses -p $PID -g -- sleep 10

# Profile branch mispredictions
perf record -e branch-misses -p $PID -g -- sleep 10
```

## Common Pitfalls & Gotchas

### 1. Missing frame pointers
The most common issue is getting broken or truncated stack traces. Modern compilers optimize away the frame pointer register (`rbp` on x86) by default. Without it, `perf` can't unwind the stack reliably. You'll see `[unknown]` frames or only partial stacks.

**Fix**: Recompile with `-fno-omit-frame-pointer`, or use `--call-graph dwarf` (slower but more reliable) or `--call-graph lbr` (Intel only, very fast).

### 2. Sampling bias from timer-based profiling
When using `-F` (frequency), the sampling is driven by a timer interrupt, not the performance counter. This means you're sampling at fixed time intervals, not at fixed cycle counts. If your workload has frequency scaling (CPUFreq), you'll oversample during low-frequency phases and undersample during turbo.

**Fix**: Use `-c` (period) with the `cycles` event for cycle-accurate sampling, or pin frequency with `cpupower frequency-set -g performance`.

### 3. Interpreting inclusive vs. exclusive samples
`perf report` defaults to showing **self** (exclusive) samples — time spent in the function itself, not its children. This is misleading for high-level functions that call many subroutines. Always toggle to **children** mode (press `c` in TUI, or use `--children`) to see the full cost including callees.

## Try It Yourself

1. **Profile your web server**: Run `perf record -F 99 -p $(pgrep nginx) -g -- sleep 30` while generating load with `wrk` or `ab`. Generate a flamegraph and identify the top 3 functions consuming CPU.

2. **Compare sampling methods**: Profile the same workload with `-F 99` (timer-based) and `-c 100000` (cycle-based). Compare the resulting profiles — do the hot functions change? Why?

3. **Debug missing stacks**: Run `perf record -F 99 -p $PID --call-graph fp` on a binary compiled without `-fno-omit-frame-pointer`. Observe the `[unknown]` frames. Then recompile with the flag and compare the stack quality.

## Next Up

Tomorrow we step back from sampling to precise counting: **perf stat: Cycle Counting & CPI Analysis**. We'll break down how to measure Cycles Per Instruction, identify pipeline stalls, and use top-down microarchitecture analysis to find exactly where your CPU is wasting cycles.
