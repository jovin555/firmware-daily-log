---
title: "Day 26: perf: Performance Counters & Hardware PMU Events"
date: 2026-07-08
tags: ["til", "ebpf", "perf", "pmu", "counters"]
---

## What I Explored Today

Today I dove into the hardware side of `perf` — specifically the Performance Monitoring Unit (PMU) counters that live right on the CPU die. While `perf` is often used for software tracing (tracepoints, kprobes), its original and arguably most powerful capability is reading hardware performance counters: cycles, instructions, cache misses, branch mispredictions, and dozens of CPU-specific events. I spent the morning running `perf stat` against real workloads and poking at `/sys/devices/cpu/events/` to understand how these counters are exposed to userspace.

## The Core Concept

Modern CPUs contain dedicated hardware counters that increment on microarchitectural events — a cache line eviction, a mispredicted branch, a TLB miss. These counters are fast (zero overhead when running, minimal when read) and precise. The key insight: **hardware counters let you measure what actually happened on the silicon, not what the kernel thinks happened**.

Why does this matter? Software profiling (e.g., sampling `gettimeofday()`) introduces measurement bias and misses microarchitectural effects. A function that runs 10% slower due to cache pressure won't show more CPU time — it just runs more cycles. PMU counters catch that. They also let you answer questions like "Is this workload memory-bound or compute-bound?" by comparing `cycles` to `instructions` (IPC ratio) and `cache-misses` to `cache-references` (miss rate).

The `perf` subsystem in Linux abstracts these hardware counters through the `perf_event_open` syscall, exposing a unified interface across x86 (Intel/AMD), ARM, RISC-V, and others. The kernel handles multiplexing, scaling, and event scheduling when you request more counters than the hardware supports simultaneously.

## Key Commands / Configuration / Code

### 1. Listing available PMU events

```bash
# Show all hardware events for the CPU PMU
perf list hw

# Show cache-related events (L1, L2, LLC, TLB)
perf list cache

# Show raw events (arch-specific hex codes)
perf list pmu
```

On my Intel Sapphire Rapids system, `perf list hw` shows:
```
  cpu-cycles OR cycles
  instructions
  branch-instructions OR branches
  branch-misses
  bus-cycles
  stalled-cycles-frontend
  stalled-cycles-backend
  ref-cycles
```

### 2. Counting events with `perf stat`

```bash
# Count cycles and instructions for a command
perf stat -e cycles,instructions ./my_workload

# Count cache misses and references
perf stat -e cache-misses,cache-references ./my_workload

# Count multiple PMU events with group (ensures they're scheduled together)
perf stat -e '{cycles,instructions,stalled-cycles-frontend}' ./my_workload
```

### 3. Raw event encoding (when generic names aren't enough)

```bash
# Intel: event=0xC0, umask=0x00 (INST_RETIRED.ANY)
perf stat -e r00c0 ./my_workload

# ARM: use sysfs to find raw codes
cat /sys/devices/cpu/events/inst_retired
# output: event=0x08
```

### 4. Sampling with `perf record` (preview)

```bash
# Sample on every 100,000th cycle
perf record -e cycles -F 100000 ./my_workload

# Sample on cache misses with call stacks
perf record -e cache-misses -g ./my_workload
```

### 5. Programmatic access via `perf_event_open`

```c
#include <linux/perf_event.h>
#include <sys/syscall.h>
#include <unistd.h>

static long
perf_event_open(struct perf_event_attr *hw_event, pid_t pid,
                int cpu, int group_fd, unsigned long flags)
{
    return syscall(__NR_perf_event_open, hw_event, pid, cpu, group_fd, flags);
}

int main() {
    struct perf_event_attr pe;
    int fd;

    memset(&pe, 0, sizeof(pe));
    pe.type = PERF_TYPE_HARDWARE;          // PMU hardware events
    pe.size = sizeof(pe);
    pe.config = PERF_COUNT_HW_CPU_CYCLES;  // cycles
    pe.disabled = 1;                       // start disabled
    pe.exclude_kernel = 1;                 // user-space only
    pe.exclude_hv = 1;                     // exclude hypervisor

    fd = perf_event_open(&pe, 0, -1, -1, 0);
    if (fd == -1) {
        perror("perf_event_open");
        return 1;
    }

    ioctl(fd, PERF_EVENT_IOC_RESET, 0);
    ioctl(fd, PERF_EVENT_IOC_ENABLE, 0);

    // ... run workload ...

    ioctl(fd, PERF_EVENT_IOC_DISABLE, 0);
    long long count;
    read(fd, &count, sizeof(count));
    printf("Cycles: %lld\n", count);

    close(fd);
    return 0;
}
```

## Common Pitfalls & Gotchas

**1. Multiplexing skews absolute counts.** When you request more events than hardware counters (typically 4-8 on x86), the kernel time-shares them. `perf stat` shows scaled counts, but scaling introduces error. Always check the `#` column — if it shows `(99.99%)` you're fine; below 90% means significant multiplexing. Use event groups `{}` to keep related counters scheduled together.

**2. Hypervisor and kernel exclusion matters.** By default, `perf stat` counts kernel + userspace. If you're profiling a userspace app, add `:u` suffix (e.g., `cycles:u`) to exclude kernel cycles. On virtualized systems, `:h` excludes hypervisor ticks. Mixing domains gives misleading IPC ratios.

**3. Event aliases differ across architectures.** `cache-misses` on Intel means LLC misses; on ARM it might mean L2 misses. Always verify with `perf stat --detailed` or check the PMU documentation for your specific CPU. The raw event codes (`rXXXX`) are the only portable way to guarantee you're measuring the same thing across kernel versions.

**4. Frequency scaling invalidates cycle counts.** On modern CPUs with dynamic frequency scaling (Intel Turbo Boost, AMD Precision Boost), cycle counts are not proportional to time. Use `ref-cycles` (unscaled reference clock) for time-proportional measurements, or use `task-clock` for wall-clock time.

## Try It Yourself

1. **Measure your compiler's IPC.** Run `perf stat -e cycles,instructions,cycles:u,instructions:u make -j$(nproc)` on a small C project. Compare the kernel vs userspace IPC ratios. What does the kernel code do that lowers IPC?

2. **Find cache-miss hot spots.** Write a small C program that traverses a large array in row-major vs column-major order. Use `perf stat -e cache-misses,cache-references ./program` to quantify the miss rate difference. Then try `perf record -e cache-misses -g ./program` and `perf report` to see where misses concentrate.

3. **Raw event exploration.** Pick a CPU-specific event from your processor's manual (e.g., Intel's `MEM_LOAD_RETIRED.L3_MISS` = event 0xD1, umask 0x20). Run `perf stat -e r20D1 ./workload` and compare to the generic `cache-misses` count. Are they the same? Why or why not?

## Next Up

Tomorrow we go deeper: `perf record` and `perf report` for profiling a running system. We'll attach to a live process, sample on hardware events, generate flame graphs, and identify the exact instructions causing cache misses and branch mispredictions. Bring a real application to profile.
