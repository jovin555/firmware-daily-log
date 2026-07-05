---
title: "Day 23: ftrace: Function Tracer & trace_printk Setup"
date: 2026-07-05
tags: ["til", "ebpf", "ftrace", "tracing", "kernel"]
---

## What I Explored Today

After weeks of eBPF deep dives, I stepped back to master the kernel's built-in tracing infrastructure: ftrace. Today I focused on the function tracer and the `trace_printk()` facility — two complementary tools that let you trace kernel function calls and inject custom print statements into the trace buffer without the overhead of `printk()`. I set up ftrace from scratch on a 6.1 kernel, experimented with filtering, and got `trace_printk()` working in a kernel module. The key takeaway: ftrace is the kernel's native dynamic tracing framework, and understanding it is essential before layering eBPF on top.

## The Core Concept

Ftrace is not a single tool but a framework of tracers built into the kernel's `tracefs` filesystem, typically mounted at `/sys/kernel/tracing/`. It operates with near-zero overhead when disabled — the kernel compiles in static tracepoints that are patched with NOP instructions at boot. When you enable a tracer, ftrace uses runtime code modification (via `mcount` or `fentry`/`fexit` hooks) to insert tracing calls into function prologues.

Why does this matter? Because `printk()` is expensive — it acquires locks, formats strings, and writes to the kernel log buffer. `trace_printk()`, by contrast, writes directly into the per-CPU ring buffer used by ftrace, with minimal overhead and no locking. It's the kernel equivalent of a lightweight `printf` for debugging, and it integrates seamlessly with the ftrace infrastructure.

The function tracer specifically records every function entry (and optionally exit) across the kernel or a filtered subset. Combined with `trace_printk()`, you get both the "what" (function calls) and the "why" (your custom debug messages) in a single, chronologically ordered trace.

## Key Commands / Configuration / Code

### Mounting and Verifying ftrace

```bash
# Mount tracefs if not already mounted
mount -t tracefs tracefs /sys/kernel/tracing/

# Check available tracers
cat /sys/kernel/tracing/available_tracers
# Output: function function_graph wakeup_dl wakeup_rt wakeup irqsoff preemptoff preemptirqsoff nop
```

### Using the Function Tracer

```bash
# Set the tracer to 'function'
echo function > /sys/kernel/tracing/current_tracer

# Filter to trace only specific functions (e.g., kmalloc and kfree)
echo 'kmalloc' > /sys/kernel/tracing/set_ftrace_filter
echo 'kfree' >> /sys/kernel/tracing/set_ftrace_filter

# Verify filter
cat /sys/kernel/tracing/set_ftrace_filter
# Output: kfree
#         kmalloc

# Start tracing (clear buffer first)
echo 0 > /sys/kernel/tracing/tracing_on
echo > /sys/kernel/tracing/trace
echo 1 > /sys/kernel/tracing/tracing_on

# Run your workload, then stop
echo 0 > /sys/kernel/tracing/tracing_on

# Read the trace
cat /sys/kernel/tracing/trace | head -50
```

### Using trace_printk() in a Kernel Module

```c
// trace_debug.c — compile with: make -C /lib/modules/$(uname -r)/build M=$PWD modules
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/delay.h>
#include <linux/ktime.h>

static int __init trace_debug_init(void)
{
    int i;
    ktime_t start, end;
    s64 delta_ns;

    pr_info("trace_debug: module loaded\n");

    for (i = 0; i < 5; i++) {
        start = ktime_get();
        mdelay(10);  // Simulate work
        end = ktime_get();
        delta_ns = ktime_to_ns(ktime_sub(end, start));

        // trace_printk writes to ftrace buffer, not dmesg
        trace_printk("Iteration %d: delta = %lld ns\n", i, delta_ns);
    }

    return 0;
}

static void __exit trace_debug_exit(void)
{
    trace_printk("trace_debug: module unloaded\n");
    pr_info("trace_debug: module unloaded\n");
}

module_init(trace_debug_init);
module_exit(trace_debug_exit);
MODULE_LICENSE("GPL");
```

### Viewing trace_printk Output

```bash
# After loading the module, read the trace buffer
cat /sys/kernel/tracing/trace

# You'll see entries like:
# <...>-1234    [001] .....  123.456789: trace_debug_init: Iteration 0: delta = 10000000 ns
# <...>-1234    [001] .....  123.466789: trace_debug_init: Iteration 1: delta = 10000000 ns
```

### Combining Function Tracer with trace_printk

```bash
# Enable function tracer with a filter on your module's functions
echo function > /sys/kernel/tracing/current_tracer
echo 'trace_debug_init' > /sys/kernel/tracing/set_ftrace_filter

# Enable trace_printk output (it's always captured, but this ensures visibility)
echo 1 > /sys/kernel/tracing/options/trace_printk

# Clear and start
echo > /sys/kernel/tracing/trace
echo 1 > /sys/kernel/tracing/tracing_on

# Load your module
insmod trace_debug.ko

# Stop and read
echo 0 > /sys/kernel/tracing/tracing_on
cat /sys/kernel/tracing/trace
```

## Common Pitfalls & Gotchas

1. **trace_printk() requires CONFIG_TRACING and CONFIG_DYNAMIC_FTRACE** — Many production kernels disable these. Check with `zcat /proc/config.gz | grep CONFIG_TRACING`. If it's not set, you'll get a build error or silent no-op. Always verify your kernel config before writing trace_printk code.

2. **trace buffer is per-CPU and finite** — The default buffer size is often 1-2 MB per CPU. If you trace high-frequency functions like `kmalloc` without filtering, you'll overflow the buffer in milliseconds. Always set `set_ftrace_filter` to narrow scope, and increase buffer size with `echo 8192 > /sys/kernel/tracing/buffer_size_kb` if needed.

3. **trace_printk() output is NOT visible in dmesg** — This is the most common confusion. `trace_printk()` writes to the ftrace ring buffer, not the kernel log buffer. You must read `/sys/kernel/tracing/trace` (or use `trace-cmd`). If you want both, use `pr_info()` for dmesg and `trace_printk()` for ftrace — or just use `pr_info()` and filter with `trace-cmd`.

## Try It Yourself

1. **Filtered function trace**: Mount tracefs, set the tracer to `function`, filter for `do_sys_open` and `vfs_open`, then run `ls /tmp` and examine the trace output. Observe the call chain.

2. **trace_printk module**: Write a kernel module that calls `trace_printk()` with a counter in a loop. Load it, then read `/sys/kernel/tracing/trace` to see your messages interleaved with function traces (if the function tracer is enabled).

3. **Buffer sizing experiment**: Set `buffer_size_kb` to 64 (minimum), enable function tracer without any filter, run `find /usr -name "*.c"`, then read the trace. Notice the "lost events" counter at the top of the output. Increase the buffer to 8192 and repeat — compare the completeness.

## Next Up

Tomorrow I'll dive into the **Function Graph Tracer** — which records both entry and exit of functions along with their execution time — and explore **latency tracing** to measure preemption off and irq off durations. We'll use `trace-cmd` to visualize function call graphs and identify real-time scheduling bottlenecks.

---
*Found this useful? Follow along as I explore eBPF and kernel debugging, one ftrace feature at a time.*
