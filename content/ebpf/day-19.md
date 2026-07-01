---
title: "Day 19: Debugging Driver Latency with eBPF: End-to-End"
date: 2026-07-01
tags: ["til", "ebpf", "driver", "latency", "example"]
---

## What I Explored Today

Today I built a complete eBPF-based latency tracing pipeline for a storage driver. The goal was to measure end-to-end I/O latency through a NVMe driver path, from the block layer submission to the driver completion interrupt. I used kprobes, tracepoints, and a BPF map to correlate requests across kernel boundaries. The result: a real-time histogram showing where time is spent inside the driver, without modifying a single line of kernel code.

## The Core Concept

Driver latency is notoriously hard to debug. Traditional tools like `perf` or `ftrace` give you function call counts and durations, but they don't easily correlate a single I/O request across multiple driver stages. You need to know: did the driver spend time in the submission path, waiting for hardware, or in the completion path?

eBPF solves this by letting you attach probes at specific driver entry and exit points, then use a BPF map to store per-request timestamps. By hashing on a unique request identifier (like the request pointer or a tag), you can track the same I/O through submission, hardware submission queue doorbell write, interrupt handler entry, and completion callback. The key insight is that the BPF map acts as a lightweight, in-kernel hash table that survives across different probe contexts.

This approach is end-to-end because you instrument the entire driver lifecycle. It's non-invasive because you never recompile or reboot. And it's precise because you measure in nanoseconds using `bpf_ktime_get_ns()`.

## Key Commands / Configuration / Code

Here's the core BPF C program that traces a NVMe driver path. I'm using the `blk_account_io_start` tracepoint for submission and the `nvme_pci_complete_rq` function for completion.

```c
// driver_latency.c
#include <linux/bpf.h>
#include <linux/ptrace.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

// Map to store per-request start times
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, struct request *);
    __type(value, u64);
} start_times SEC(".maps");

// Histogram map: 64 buckets, log2 scale
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 64);
    __type(key, u32);  // bucket index
    __type(value, u64); // count
} latency_hist SEC(".maps");

// Tracepoint: block layer I/O start
SEC("tracepoint/block/block_rq_issue")
int trace_block_rq_issue(struct trace_event_raw_block_rq *ctx)
{
    struct request *rq = (struct request *)ctx->dev;
    u64 ts = bpf_ktime_get_ns();
    bpf_map_update_elem(&start_times, &rq, &ts, BPF_ANY);
    return 0;
}

// Kprobe: NVMe driver completion
SEC("kprobe/nvme_pci_complete_rq")
int trace_nvme_complete(struct pt_regs *ctx)
{
    struct request *rq = (struct request *)PT_REGS_PARM1(ctx);
    u64 *start_ts = bpf_map_lookup_elem(&start_times, &rq);
    if (!start_ts)
        return 0;

    u64 delta_us = (bpf_ktime_get_ns() - *start_ts) / 1000;
    bpf_map_delete_elem(&start_times, &rq);

    // Log2 bucket: 0=1us, 1=2us, ... 63=~1s
    u32 bucket = 0;
    u64 val = delta_us;
    while (val >>= 1)
        bucket++;
    if (bucket > 63)
        bucket = 63;

    u64 *count = bpf_map_lookup_elem(&latency_hist, &bucket);
    u64 new_count = count ? *count + 1 : 1;
    bpf_map_update_elem(&latency_hist, &bucket, &new_count, BPF_ANY);
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
```

Compile and load:

```bash
# Compile with clang for BPF target
clang -O2 -target bpf -c driver_latency.c -o driver_latency.o

# Load and attach
sudo bpftool prog load driver_latency.o /sys/fs/bpf/driver_latency
sudo bpftool prog attach pinned /sys/fs/bpf/driver_latency tracepoint block/block_rq_issue
sudo bpftool prog attach pinned /sys/fs/bpf/driver_latency kprobe nvme_pci_complete_rq

# Read the histogram
sudo bpftool map dump name latency_hist
```

To make this practical, I also added a userspace reader using libbpf:

```python
#!/usr/bin/env python3
# reader.py
import ctypes, os, time

# Load the BPF map via bpftool JSON output
# Simplified: read /sys/fs/bpf/driver_latency_hist
# In production, use bcc or libbpf Python bindings

def read_hist():
    import subprocess
    result = subprocess.run(
        ["sudo", "bpftool", "map", "dump", "name", "latency_hist", "-j"],
        capture_output=True, text=True
    )
    # Parse JSON and print human-readable histogram
    import json
    data = json.loads(result.stdout)
    print("Latency (us) | Count")
    print("-------------|------")
    for entry in data:
        bucket = entry['key']
        count = entry['value']
        # Convert bucket to upper bound
        upper_us = 1 << bucket
        print(f"< {upper_us:>8}  | {count}")

while True:
    read_hist()
    time.sleep(2)
```

## Common Pitfalls & Gotchas

1. **Request pointer reuse**: The `struct request *` pointer can be reused by the block layer after completion. If your completion probe fires after the request has been recycled for a new I/O, you'll get a false start time. Always delete the map entry in the completion probe (as shown above) to avoid stale data.

2. **Missing tracepoints**: Not all drivers have convenient tracepoints. The `block_rq_issue` tracepoint works for block layer, but if your driver bypasses the block layer (e.g., some NVMe passthrough paths), you need to kprobe `nvme_submit_cmd` instead. Check `/sys/kernel/debug/tracing/events/` for available tracepoints.

3. **Interrupt context vs process context**: Your completion probe might run in hardirq context where `bpf_ktime_get_ns()` is safe, but `bpf_printk()` is not. Always use maps for data collection, never printk in interrupt handlers. Also, BPF stack size is limited to 512 bytes—don't allocate large local arrays.

## Try It Yourself

1. **Extend the histogram**: Add a second map to track per-CPU latency distribution. Use `bpf_get_smp_processor_id()` as part of the key to see if a specific CPU is experiencing higher driver latency due to IRQ affinity issues.

2. **Instrument a different driver**: Pick a network driver (e.g., `ixgbe` or `mlx5`). Trace from `ndo_start_xmit` to the TX completion interrupt handler. Use the skb pointer as the correlation key instead of `struct request`.

3. **Add a latency threshold alarm**: Modify the BPF program to send a perf event to userspace when a single I/O exceeds 10ms. Use `bpf_perf_event_output()` and a userspace program that logs the offending request details.

## Next Up

Tomorrow, I'll show you how to dynamically trace a custom kernel module that isn't built into the kernel tree. We'll use eBPF to probe its exported functions and internal data structures, even when the module has no tracepoints or debugfs interfaces. This is the ultimate "black box" debugging technique for third-party or proprietary drivers.
