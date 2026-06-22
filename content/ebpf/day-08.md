---
title: "Day 08: Flame Graphs: Visualizing perf Stack Traces"
date: 2026-06-22
tags: ["til", "ebpf", "flamegraph", "perf", "visualization"]
---

## What I Explored Today

Today I finally tackled flame graphs—the gold standard for visualizing CPU profiling data from `perf`. I've been collecting stack traces with `perf record` for days, but staring at raw text output and nested call chains in a terminal is like debugging blindfolded. I walked through the full pipeline: capturing stack traces with `perf`, folding them into a format the FlameGraph tools understand, and generating interactive SVG flame graphs. The result is a visual heatmap of where the CPU actually spends its cycles, revealing bottlenecks that text dumps simply hide.

## The Core Concept

A flame graph is a **stack trace visualization** where each rectangle (frame) represents a function call, the width corresponds to the proportion of samples where that function was on-CPU, and the y-axis shows the call stack depth. The bottom is the root (often `_start` or `main`), and the top is the leaf function actually running on the CPU.

Why not just use `perf report`? Because `perf report` aggregates by function, but it doesn't show you the *path* to that function. A function like `malloc` might be called from 50 different call sites, and `perf report` lumps them together. A flame graph preserves the full context: you can see that 40% of `malloc` samples come from `json_parse` → `tokenize` → `malloc`, while only 5% come from `config_load` → `malloc`. That distinction is critical for targeted optimization.

The key insight: **flame graphs are not about counting function calls—they're about showing where the CPU is actually stuck**. A wide frame at the top means that function is the hot leaf. A wide frame at the bottom with narrow children means the function itself is expensive (not its callees). This is the "why" behind the "what."

## Key Commands / Configuration / Code

### 1. Capture stack traces with frame pointers

Most modern distros omit frame pointers by default (gcc `-fomit-frame-pointer`). You need to either rebuild with `-fno-omit-frame-pointer` or use `dwarf` unwinding. For production, `dwarf` is safer (no rebuild), but slower:

```bash
# Capture with DWARF unwinding (works on any binary)
perf record -F 99 -g --call-graph dwarf -a -- sleep 60

# Or if you have frame pointers compiled in (faster)
perf record -F 99 -g -a -- sleep 60
```

- `-F 99`: Sample at 99 Hz (avoids aliasing with 100 Hz timer ticks)
- `-g`: Capture call graphs (stack traces)
- `--call-graph dwarf`: Use DWARF debug info for unwinding
- `-a`: Profile all CPUs
- `sleep 60`: Profile for 60 seconds

### 2. Generate the folded stack file

The FlameGraph tools expect a specific format: one line per sample, with functions separated by semicolons, followed by a space and a count. `perf script` outputs raw samples; we fold them:

```bash
# Clone FlameGraph tools (Brendan Gregg's repo)
git clone https://github.com/brendangregg/FlameGraph
cd FlameGraph

# Generate folded stacks from perf.data
perf script -i /path/to/perf.data | ./stackcollapse-perf.pl > out.folded
```

### 3. Generate the SVG flame graph

```bash
# Generate interactive SVG (inverted: icicle view)
./flamegraph.pl --title="CPU Flame Graph - My Service" \
  --width=1200 \
  --colors=java \
  out.folded > flame.svg

# For a "flame" view (bottom-up, root at bottom), use --inverted
./flamegraph.pl --inverted --title="CPU Flame Graph" out.folded > flame.svg
```

Open `flame.svg` in a browser. Hover to see function names and sample counts. Click to zoom into a stack frame.

### 4. Alternative: `perf report` with `--stdio` for quick text check

Before generating the SVG, I always do a quick sanity check:

```bash
perf report --stdio --sort=comm,dso,symbol --no-children | head -40
```

This shows top functions by CPU usage. If the top function is `__do_softirq` or `spin_lock`, you know you're looking at kernel contention, not application logic.

## Common Pitfalls & Gotchas

### 1. Missing frame pointers produce broken stacks

If you use `-g` without `--call-graph dwarf` on a binary compiled with `-fomit-frame-pointer`, you'll see stacks like `[unknown]` or truncated call chains. The fix: always use `--call-graph dwarf` unless you've verified frame pointers are enabled. On modern Fedora/RHEL, the kernel is fine, but user-space apps often lack frame pointers.

### 2. Sampling frequency aliasing with periodic work

Sampling at exactly 100 Hz can alias with a timer tick that fires every 10ms. You might over-represent or under-represent work that synchronizes with the timer. Use a prime number like 97 or 99 Hz. Or use `-F 997` for high-resolution profiling on fast CPUs.

### 3. Interpreting wide top frames incorrectly

A wide frame at the top of a flame graph means that function is *on-CPU* a lot. But that doesn't always mean it's the problem. For example, `__GI___libc_write` being wide might just mean you're doing a lot of I/O—the bottleneck could be the disk, not the write syscall. Always correlate flame graphs with other metrics (disk utilization, network stats) before declaring a function as the root cause.

## Try It Yourself

1. **Profile your own application for 30 seconds**: Run `perf record -F 99 -g --call-graph dwarf -p $(pgrep -f your_app) sleep 30`, then generate a flame graph. Identify the widest leaf function and trace its call path back to your code.

2. **Compare flame graphs with and without frame pointers**: If you have a C/C++ binary, rebuild it with `-fno-omit-frame-pointer`, profile both versions, and compare the flame graphs. Notice how the DWARF version has more complete stacks but higher overhead.

3. **Zoom into a suspicious frame**: Open the SVG in a browser, click on a wide frame that looks like a hot function (e.g., `malloc` or `memcpy`). Read the call chain leading to it. Is it being called from an unexpected code path? If so, that's your optimization target.

## Next Up: perf sched — Scheduling Latency Analysis

Tomorrow, I'm diving into `perf sched` to measure scheduling latency—how long tasks wait before getting CPU time. Flame graphs show *where* CPU time is spent, but they don't show *why* a task is waiting. `perf sched record` and `perf sched latency` will reveal preemption delays, wake-up latencies, and scheduler-induced jitter. If you've ever wondered why your real-time thread misses its deadline, this is the tool.
