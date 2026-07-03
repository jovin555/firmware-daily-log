---
title: "Day 21: Full Review & Project: Kernel Latency Monitor"
date: 2026-07-03
tags: ["til", "ebpf", "review", "project", "latency"]
---

## What I Explored Today

After three weeks of deep dives into eBPF internals, kprobes, tracepoints, maps, and the BPF verifier, today I stepped back to build something that ties it all together: a kernel latency monitor. This project instruments critical kernel functions—`do_sys_open`, `__x64_sys_write`, and `schedule`—to measure how long syscalls take and how often context switches occur. The goal wasn't just to write eBPF code, but to produce a tool that a production engineer could actually use to identify latency spikes without modifying the kernel or restarting services.

## The Core Concept

Latency monitoring at the kernel level is fundamentally different from userspace profiling. When an application reports a slow syscall, you need to know *where* the time went—was it in the VFS layer, block I/O, scheduler preemption, or memory reclaim? Userspace tools like `perf` or `strace` can show you entry and exit, but they add overhead and can't easily correlate events across CPUs or processes.

eBPF solves this by running sandboxed programs at kernel hook points with minimal overhead. The key insight: we can attach a kprobe at the entry of a function, store a timestamp in a BPF map keyed by thread ID, then attach a kprobe at the return (via `kretprobe`) to read that timestamp and compute the delta. This gives us per-syscall latency histograms with nanosecond precision, aggregated in-kernel to avoid flooding userspace.

The real power comes from combining multiple probes. By also hooking `finish_task_switch`, we can detect if a syscall was preempted mid-flight—a common cause of tail latency that's invisible to application-level profiling.

## Key Commands / Configuration / Code

Here's the core BPF C code for the latency monitor. I compiled it with `clang -O2 -target bpf -c latency_monitor.c -o latency_monitor.o` and loaded it via a Python frontend using `ctypes` and the `bpf()` syscall.

```c
// latency_monitor.c - Kernel Latency Monitor (BPF program)
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

// Map: keyed by PID, stores entry timestamp (ns)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 10240);
    __type(key, u32);
    __type(value, u64);
} syscall_start SEC(".maps");

// Histogram: 64 buckets from 1us to 10s (log2 scale)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 64);
    __type(key, u32);
    __type(value, u64);
} latency_hist SEC(".maps");

// Track preempted syscalls
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 10240);
    __type(key, u32);
    __type(value, u8);
} preempted SEC(".maps");

SEC("kprobe/do_sys_open")
int trace_open_entry(struct pt_regs *ctx)
{
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 ts = bpf_ktime_get_ns();
    bpf_map_update_elem(&syscall_start, &pid, &ts, BPF_ANY);
    return 0;
}

SEC("kretprobe/do_sys_open")
int trace_open_return(struct pt_regs *ctx)
{
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 *start_ts = bpf_map_lookup_elem(&syscall_start, &pid);
    if (!start_ts)
        return 0;

    u64 delta = bpf_ktime_get_ns() - *start_ts;
    // Convert to microseconds for histogram bucket
    u32 bucket = delta / 1000;
    // Clamp to 63 (max bucket)
    if (bucket > 63) bucket = 63;

    u64 *count = bpf_map_lookup_elem(&latency_hist, &bucket);
    if (count) {
        __sync_fetch_and_add(count, 1);
    } else {
        u64 one = 1;
        bpf_map_update_elem(&latency_hist, &bucket, &one, BPF_NOEXIST);
    }

    // Check if this syscall was preempted
    u8 *was_preempted = bpf_map_lookup_elem(&preempted, &pid);
    if (was_preempted) {
        // Log to trace pipe for debugging
        bpf_printk("PID %d preempted during open, delta=%llu us\n", pid, delta / 1000);
        bpf_map_delete_elem(&preempted, &pid);
    }

    bpf_map_delete_elem(&syscall_start, &pid);
    return 0;
}

SEC("kprobe/finish_task_switch")
int trace_sched_switch(struct pt_regs *ctx)
{
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    // Mark this PID as preempted if it has an active syscall
    u64 *start_ts = bpf_map_lookup_elem(&syscall_start, &pid);
    if (start_ts) {
        u8 flag = 1;
        bpf_map_update_elem(&preempted, &pid, &flag, BPF_ANY);
    }
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
```

To load and read the histogram from userspace:

```bash
# Load the BPF program (requires root)
sudo python3 -c "
import ctypes, os
# Simplified: use bpftool for quick testing
"
# Alternative: use bpftool to load and pin
sudo bpftool prog load latency_monitor.o /sys/fs/bpf/latency_monitor
sudo bpftool prog attach pinned /sys/fs/bpf/latency_monitor kprobe do_sys_open

# Read histogram (dump map ID 2)
sudo bpftool map dump name latency_hist
```

## Common Pitfalls & Gotchas

1. **PID collisions in hash maps**: When a process exits and its PID is reused, the old entry in `syscall_start` can cause false latency readings. Always delete the entry on return (as shown above), and consider using `BPF_MAP_TYPE_LRU_HASH` with a TTL to auto-evict stale entries.

2. **kretprobe stack depth**: If the kernel function you're probing can be called recursively (e.g., `do_sys_open` calling into VFS which calls another `do_sys_open` for a mount point), your entry/return probes will nest. The fix: store a per-CPU recursion counter or use a stack of timestamps per PID.

3. **Overhead from `bpf_printk`**: In the preemption detection code, I used `bpf_printk` which writes to `/sys/kernel/debug/tracing/trace_pipe`. This is slow and should only be used for debugging. In production, increment a counter in a separate map instead.

## Try It Yourself

1. **Extend the monitor to track `__x64_sys_write`**: Add kprobe/kretprobe pairs for the write syscall. Modify the histogram map to include a key for syscall type (0=open, 1=write) so you can compare latencies.

2. **Add a threshold alert**: Create a new BPF map that stores a latency threshold (e.g., 10ms). In the return probe, if `delta > threshold`, send a signal to userspace by incrementing a perf event array. Write a Python script that polls the perf buffer and prints a stack trace.

3. **Measure context switch overhead**: Instead of marking syscalls as preempted, instrument `__schedule` entry and exit to measure how long the scheduler itself takes. Compare this to the syscall latency to see if scheduling is a bottleneck.

## Next Up

Tomorrow begins our **Full Review** week. We'll revisit every concept from days 1-20, identify the most common mistakes, and build a comprehensive cheat sheet for production eBPF debugging. Bring your questions—we're going to stress-test everything we've learned.
