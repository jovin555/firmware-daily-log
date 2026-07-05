---
title: "Day 23: perf: Profiling on Embedded"
date: 2026-07-05
tags: ["til", "embedded-linux", "perf", "profiling"]
---

## What I Explored Today

Today I dove into using `perf` for profiling on an embedded Linux target—specifically a dual-core ARM Cortex-A7 system with 512MB RAM and a Yocto-built rootfs. I needed to understand why a video decoder thread was missing its frame deadlines under load. `perf` is the swiss-army knife of Linux performance analysis, but on embedded systems it comes with constraints: limited memory, no GUI, and often a stripped-down kernel. I validated my setup, ran hardware and software event counters, and identified a cache-miss storm in the decoder’s motion compensation loop.

## The Core Concept

`perf` uses the Linux kernel’s Performance Events subsystem (`perf_event_open`) to access hardware performance counters (CPU cycles, cache misses, branch mispredictions) and software events (context switches, page faults, migrations). On embedded, the key insight is that you’re not chasing micro-optimizations for a web server—you’re hunting real-time violations, interrupt storms, or cache thrashing that cause deadline misses. The “why” is that embedded workloads are often deterministic: a 10% CPU overhead from a bad cache line layout can push a 30fps decode pipeline over budget. `perf` lets you pinpoint exactly which function, instruction, or even which data access is the bottleneck, without instrumenting your code.

On resource-constrained targets, you must be strategic: avoid recording every event (which fills the buffer and kills performance), and instead use sampling with a low frequency or focus on targeted events. The `perf record` / `perf report` workflow is your friend, but you’ll often run `perf stat` first to get a high-level view without generating a large data file.

## Key Commands / Configuration / Code

### 1. Verify kernel support
```bash
# On target, check if perf is available and events are accessible
zcat /proc/config.gz | grep PERF_EVENT
# Expect: CONFIG_PERF_EVENTS=y
# Also check for hardware counters
perf list | grep -E "cache|cycles|instructions"
# If empty, you may need to enable CONFIG_HW_PERF_EVENTS in kernel config
```

### 2. Quick system-level stat (no data file)
```bash
# Profile a running process (PID 1234) for 5 seconds
perf stat -e cycles,instructions,cache-misses,cache-references -p 1234 sleep 5
# Output example:
#   1,234,567,890      cycles                    # 0.80 GHz
#     987,654,321      instructions              # 0.80 insn per cycle
#      12,345,678      cache-misses              # 30.5% of all cache refs
#      40,123,456      cache-references
```
This tells you immediately if cache misses are pathological (above 20% is bad for embedded).

### 3. Sampling with call-graph (the real profiling)
```bash
# Record 1000 samples per second, with call-graph (dwarf unwinding)
perf record -F 1000 -g --call-graph dwarf -p 1234 -o /tmp/perf.data sleep 10
# -F 1000: sample rate (lower on embedded to reduce overhead)
# -g: enable call-graph
# --call-graph dwarf: use DWARF unwinding (works without frame pointers)
# -o: output to a file (avoid filling rootfs)
```
On embedded, `dwarf` unwinding can be slow. If your binaries are compiled with `-fno-omit-frame-pointer`, use `fp` instead:
```bash
perf record -F 1000 -g --call-graph fp -p 1234 -o /tmp/perf.data sleep 10
```

### 4. Analyze on host (copy perf.data off target)
```bash
# On host, with same kernel and cross-toolchain
perf report -i /tmp/perf.data --sort comm,dso,symbol
# Or get a flamegraph-style output
perf script -i /tmp/perf.data | ./stackcollapse-perf.pl | ./flamegraph.pl > profile.svg
```

### 5. Trace specific events (e.g., context switches)
```bash
# Record all context switches for 5 seconds
perf record -e context-switches -a -o /tmp/cs.data sleep 5
# Check if a thread is being preempted too often
perf report -i /tmp/cs.data --sort comm
```

## Common Pitfalls & Gotchas

**1. Kernel config missing hardware events.** Many embedded BSPs ship with `CONFIG_HW_PERF_EVENTS=n` to save space. You’ll get “perf_event_open failed: No such device” or empty `perf list` output. Fix: rebuild kernel with `CONFIG_HW_PERF_EVENTS=y` and `CONFIG_PERF_EVENTS=y`. Without hardware counters, you’re limited to software events (context switches, page faults) which are still useful but less precise.

**2. Sampling overhead on low-end CPUs.** On a single-core Cortex-A7 at 600 MHz, `perf record -F 1000` can add 5-10% CPU overhead. If your target is already at 95% utilization, the profiling itself can cause missed deadlines. Mitigation: use `-F 100` (100 Hz) for initial passes, or run `perf stat` first to see if overhead is acceptable. Alternatively, use `perf top` in live mode for a quick view without saving data.

**3. Call-graph unwinding fails with stripped binaries.** Embedded rootfs often strip debug info. If you see `[unknown]` frames in `perf report`, you need either unstripped binaries on the target (bad for space) or copy the debug symbols to the host and use `--symfs` during analysis. Better: compile with `-g` but strip at packaging time, keeping separate debug files (e.g., `.debug` directory in Yocto).

## Try It Yourself

1. **Check your kernel’s perf capabilities.** Run `perf list | head -20` on your target. If you see hardware events, run `perf stat -e cycles,instructions,cache-misses sleep 1` and note the instructions-per-cycle (IPC). A value below 0.5 suggests significant stalls.

2. **Profile a busy loop.** Write a simple C program that does 10 million integer additions in a loop. Compile with `-O2 -g -fno-omit-frame-pointer`. Run it under `perf record -F 1000 -g --call-graph fp ./a.out`. Copy the `perf.data` to your host and run `perf report`. Identify the hottest function and its caller.

3. **Detect context switch thrashing.** Run two CPU-bound threads that share a mutex (e.g., pthread mutex lock/unlock in a tight loop). Use `perf stat -e context-switches -p <PID>` to see if context switches are excessive (more than a few hundred per second is suspicious). Then use `perf record -e context-switches -a sleep 5` to see which processes are causing them.

## Next Up

Tomorrow, we lock down the boot chain: **Secure Boot: Verified Boot Chain on Embedded Linux**. I’ll walk through signing the bootloader, kernel, and rootfs with U-Boot’s verified boot, using `fit_image` and public key cryptography to prevent tampered firmware from running.
