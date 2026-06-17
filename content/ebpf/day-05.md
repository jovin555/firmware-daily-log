---
title: "Day 05: perf: Performance Counters & Hardware PMU Events"
date: 2026-06-17
tags: ["til", "ebpf", "perf", "pmu", "counters"]
---

## What I Explored Today

Today I dug into `perf stat` and the Performance Monitoring Unit (PMU) — the hardware counters baked into every modern CPU. While eBPF gives us software-defined probes, the PMU is the silicon-level instrumentation that counts cycles, cache misses, branch mispredictions, and stalled instructions without any code modification. I learned how to enumerate PMU events, run statistical profiling with multiplexing, and interpret the raw counter values that tell you exactly where a CPU-bound workload is bottlenecked.

## The Core Concept

The PMU is a set of hardware registers on each core that count microarchitectural events. On x86, these are things like `INST_RETIRED.ANY`, `CACHE_MISSES`, `BRANCH_MISPREDICT`. On ARM, they're `CPU_CYCLES`, `L1D_CACHE_REFILL`, `BR_MIS_PRED`. The key insight: **these counters are non-invasive**. They don't slow down your code, they don't require instrumentation, and they give you cycle-accurate data.

Why does this matter? Because software profilers (like `gprof` or simple timers) can only measure wall-clock time. The PMU tells you *why* time is being spent: is the CPU stalled waiting for memory? Is it flushing the pipeline due to mispredicted branches? Are we thrashing the L1 cache? These are questions you cannot answer with a stopwatch.

`perf` exposes the PMU through the `perf_event_open` syscall, which eBPF programs can also attach to via `bpf_perf_event_output`. But today I'm focusing on the user-facing tool: `perf stat` for counting, and `perf list` for discovering what your CPU supports.

## Key Commands / Configuration / Code

### 1. List all PMU events on your system
```bash
# Show all hardware events, software events, and tracepoints
perf list

# Filter to hardware PMU events only
perf list hw

# On Intel, show raw event codes (useful for uncore events)
perf list --details
```

### 2. Basic counting with `perf stat`
```bash
# Count cycles, instructions, cache misses for a command
perf stat -e cycles,instructions,cache-misses,branch-misses \
  ./my_heavy_binary

# Output example:
#   1,234,567,890      cycles                    #    3.45 GHz
#     987,654,321      instructions              #    0.80  insn per cycle
#      12,345,678      cache-misses              #   12.3% of all cache refs
#       1,234,567      branch-misses             #    2.1% of all branches
```

### 3. Count events for a running process (PID)
```bash
# Attach to PID 1234 for 10 seconds
perf stat -p 1234 -e cycles,instructions sleep 10
```

### 4. System-wide counting with multiplexing
```bash
# Count across all CPUs, multiplex if more events than counters
# The 'scale' attribute tells you if multiplexing was used
perf stat -a -e cycles,instructions,cache-misses,branch-misses,stalled-cycles-frontend,stalled-cycles-backend sleep 5
```

### 5. Raw PMU events (when you know the hex code)
```bash
# Intel: count L2 cache misses (event 0x24, umask 0x01)
perf stat -e r2401 ./my_binary

# ARM: count L1 data cache refill (event 0x03)
perf stat -e r03 ./my_binary
```

### 6. Using `perf_event_open` from C (simplified)
```c
#include <linux/perf_event.h>
#include <sys/syscall.h>

struct perf_event_attr pe = {
    .type = PERF_TYPE_HARDWARE,
    .size = sizeof(struct perf_event_attr),
    .config = PERF_COUNT_HW_CPU_CYCLES,
    .disabled = 1,
    .exclude_kernel = 1,
    .exclude_hv = 1,
};

int fd = syscall(SYS_perf_event_open, &pe, 0, -1, -1, 0);
ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);
// ... run your workload ...
ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
read(fd, &count, sizeof(count));
printf("Cycles: %llu\n", count);
```

## Common Pitfalls & Gotchas

**1. Multiplexing skews absolute counts.** When you ask for more events than physical counters (typically 4-8 on modern x86), `perf` time-shares the counters. The reported counts are scaled, but if your workload is bursty, the scaling can be inaccurate. Always check for the `#` or `(scaled from ...)` annotation in `perf stat` output. If you see it, consider running fewer events or increasing the sampling interval.

**2. Hyper-threading doubles the counters.** On Intel CPUs with Hyper-Threading, each logical core has its own set of PMU counters. But some events (like L3 cache misses) are shared across physical cores. You can get double-counting if you sum across logical cores. Use `-C 0,2,4,6` to pin to physical cores only, or consult the Intel SDM for which events are "core-scoped" vs "package-scoped".

**3. Kernel vs user-space counts.** By default, `perf stat` counts events in both kernel and user space. If you're profiling a user-space application, kernel interrupts (syscalls, page faults, scheduler) will inflate your cycle counts. Use `:u` suffix to restrict to user-space only:
```bash
perf stat -e cycles:u,instructions:u ./my_binary
```

**4. Virtualization hides PMU events.** Inside a VM, the hypervisor may not expose PMU counters, or may only expose a limited subset. If you see `perf: pmu not supported`, check if you're in a container or VM. On AWS EC2, you need `HVM` instances with `Intel VT-x` enabled.

## Try It Yourself

1. **Discover your CPU's PMU capabilities.** Run `perf list hw` and identify at least 5 hardware events your CPU supports. Then run `perf stat -e <event1>,<event2> sleep 1` to verify they work. Note which events are "scaled" due to multiplexing.

2. **Find a cache-thrashing workload.** Write a small C program that walks a large array with a stride that evicts cache lines (e.g., `int arr[1024*1024]; for(i=0;i<1024*1024;i+=64) arr[i]++;`). Run `perf stat -e cache-misses,cache-references,cycles ./cache_thrash`. Compare the cache-miss ratio to a sequential-access version.

3. **Measure branch mispredictions.** Write a binary search on a sorted array vs a linear search on an unsorted array. Use `perf stat -e branch-misses,branch-instructions,instructions` on both. Calculate the misprediction rate and correlate it with runtime. The unsorted linear search should have near-zero mispredictions; the binary search will have many.

## Next Up

Tomorrow I'll move from counting to sampling with `perf record` and `perf report`. We'll profile a real running system, capture call-graphs, and identify hot functions — all using the same PMU counters we explored today.
