---
title: "Day 27: perf record & report: Profiling a Running System"
date: 2026-07-09
tags: ["til", "ebpf", "perf", "profiling", "flamegraph"]
---

## What I Explored Today

Today I dove deep into `perf record` and `perf report` — the workhorses of Linux performance profiling. While I've used `perf stat` for counting events, I needed to understand *where* CPU cycles are actually spent in a running system. I instrumented a production-like Nginx server under load, captured call stacks at 99 Hz, and generated flamegraphs to visualize hotspots. The goal: move from "CPU is high" to "function X at line Y is the bottleneck."

## The Core Concept

`perf record` is a sampling profiler. It doesn't instrument every instruction — it takes periodic snapshots of the program counter (PC) and call stack. The default sampling frequency is 4000 Hz (every 250 µs), but for most systems you'll want to lower it to 49–99 Hz to avoid overhead.

The key insight: sampling is statistical. If a function appears in 30% of samples, it's likely consuming ~30% of CPU time. This works because the kernel's Performance Monitoring Unit (PMU) generates hardware interrupts at precise intervals, and `perf` records the current execution context in a `perf.data` file.

The real power comes from call-graph recording (`-g`). Without it, you only see leaf functions. With frame pointers or DWARF unwinding, you get the full stack trace — critical for understanding *why* a function is hot.

## Key Commands / Configuration / Code

### Basic profiling session

```bash
# Record 10 seconds of CPU samples across all CPUs
sudo perf record -a -g -F 99 -- sleep 10

# -a: all CPUs (system-wide)
# -g: capture call-graphs (stack traces)
# -F 99: sample at 99 Hz (avoids lockstep with common periodic work)
# sleep 10: profiling duration
```

### Profiling a specific process

```bash
# Find PID of nginx worker
pgrep -f 'nginx: worker'

# Profile only that PID for 30 seconds
sudo perf record -p 12345 -g -F 99 -- sleep 30
```

### Interactive report

```bash
# Open the interactive TUI
perf report

# Key shortcuts:
#   'h' - help
#   'Enter' - drill into function
#   'a' - annotate source/assembly
#   'k' - show kernel vs userspace
#   'F' - toggle percent calculation (relative vs global)
```

### Generate a flamegraph

```bash
# Step 1: Generate folded stack output
perf script > out.perf

# Step 2: Fold stacks (requires FlameGraph tools)
git clone https://github.com/brendangregg/FlameGraph
./FlameGraph/stackcollapse-perf.pl out.perf > out.folded

# Step 3: Generate SVG
./FlameGraph/flamegraph.pl out.folded > flamegraph.svg
```

### Annotating a hot function

```bash
# After perf report, press 'a' on a function to see:
# - Source line with sample counts
# - Assembly with sample counts per instruction
# - Annotations like:
#       │       if (buf->len > threshold) {
#  1.23 │       mov    0x18(%rdi),%eax
#       │       cmp    $0x400,%eax
#  0.05 │       jle    38
#       │           process_large(buf);
# 12.34 │       call   process_large
```

### Controlling sampling with events

```bash
# Profile only L1 cache misses (not cycles)
sudo perf record -e L1-dcache-load-misses -g -a -- sleep 5

# Profile branch misses
sudo perf record -e branch-misses -g -a -- sleep 5
```

## Common Pitfalls & Gotchas

### 1. Missing stack frames (the frame pointer trap)
Modern GCC defaults to `-fomit-frame-pointer`, which breaks call-graph unwinding. You'll see `[unknown]` entries in stacks. Fix: compile with `-fno-omit-frame-pointer` or use DWARF unwinding (`--call-graph dwarf`). DWARF is slower but works without recompilation.

### 2. Sampling frequency too high
`-F 4000` on a busy system can cause 5-10% overhead. The PMU interrupt handler itself consumes CPU. Start at `-F 49` or `-F 99` — Nyquist says you need 2x the frequency of the events you're sampling, but for CPU profiling, 99 Hz is plenty.

### 3. Interpreting percentages incorrectly
`perf report` shows percentages relative to the total samples. A function at 5% might be the top consumer, or there might be 20 functions at 5% each. Always check the "Children" column — it shows inclusive cost (function + all its callees). The "Self" column is exclusive cost (just that function).

### 4. Forgetting `-g` for call graphs
Without `-g`, you get flat profiles — you'll see `memcpy` is hot, but not *who* called it. Always add `-g` unless you're doing a quick check.

## Try It Yourself

1. **Profile your web server under load**: Run `ab -n 10000 -c 100 http://localhost/` against a local Nginx/Apache. Simultaneously run `sudo perf record -g -F 99 -p $(pgrep -f 'nginx: worker' | head -1) -- sleep 30`. Generate a flamegraph and identify the top 3 functions.

2. **Compare with and without frame pointers**: Write a small C program that does heavy string processing. Compile once with `-fomit-frame-pointer` (default) and once with `-fno-omit-frame-pointer`. Profile both with `perf record -g` and compare the quality of stack traces in `perf report`.

3. **Annotate a hot path**: Run `perf record` on a CPU-bound workload (e.g., `stress --cpu 4`). Open `perf report`, drill into the hottest kernel function, press `a` to annotate. Identify which assembly instruction consumes the most samples. Is it a memory load, a branch, or an ALU op?

## Next Up

Tomorrow: **perf stat: Cycle Counting & CPI Analysis** — we'll move from sampling to precise event counting, calculating Cycles Per Instruction (CPI), and identifying whether your bottleneck is front-end (instruction fetch) or back-end (execution/memory).
