---
title: "Day 02: ftrace: Function Tracer & trace_printk Setup"
date: 2026-06-14
tags: ["til", "ebpf", "ftrace", "tracing", "kernel"]
---

## What I Explored Today

After yesterday's deep dive into eBPF's verifier, I needed to understand the foundational tracing infrastructure that eBPF hooks into. Today I went all-in on ftrace — the kernel's built-in function tracer. I set up the debugfs interface, configured function tracing for specific kernel functions, and most importantly, got `trace_printk()` working in a kernel module. This is the bread and butter of kernel debugging when you need to see what's happening inside a function without the overhead of full kprobes or the complexity of writing eBPF programs for every little thing.

## The Core Concept

ftrace is not a single tracer — it's a framework. Think of it as the kernel's instrumentation backbone. It uses `-pg` profiling flags during compilation to insert `mcount()` (or `fentry` on modern x86) calls at function entry points. When enabled, these calls redirect to ftrace's handler, which can record timestamps, function names, and even call graphs.

Why should you care? Because ftrace is the fastest way to answer "is this function being called, and when?" It adds minimal overhead (nanoseconds per call) and requires zero kernel rebuilds if your kernel has `CONFIG_FUNCTION_TRACER=y`. Unlike `printk()` which blocks and floods dmesg, `trace_printk()` writes to a per-CPU ring buffer that's lockless and designed for tracing. It's the difference between a firehose and a precision nozzle.

The real power is composability: you can stack ftrace with tracepoints, kprobes, and eBPF programs. But start here — master the function tracer and `trace_printk()` before layering complexity.

## Key Commands / Configuration / Code

### 1. Verify ftrace is available

```bash
# Check if debugfs is mounted
mount | grep debugfs
# If not:
sudo mount -t debugfs none /sys/kernel/debug

# Verify ftrace directory exists
ls /sys/kernel/debug/tracing/
# Look for: available_tracers, current_tracer, set_ftrace_filter
```

### 2. Enable function tracing for a specific function

```bash
cd /sys/kernel/debug/tracing

# See available tracers
cat available_tracers
# Output: function function_graph nop ...

# Set the function tracer
echo function > current_tracer

# Trace only do_sys_open (the kernel's open syscall handler)
echo do_sys_open > set_ftrace_filter

# Start tracing (1 = enable, 0 = disable)
echo 1 > tracing_on

# Generate some activity
ls /tmp > /dev/null

# Read the trace buffer
cat trace | head -20
# Output shows: function name, PID, latency format, timestamp
```

### 3. Using trace_printk() in a kernel module

```c
// ftrace_test.c — minimal module to demonstrate trace_printk
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/tracepoint.h>  // Not strictly needed, but good practice

static int __init ftrace_test_init(void)
{
    // trace_printk() writes to ftrace ring buffer, NOT dmesg
    // Use %pS for symbol resolution, %pK for kernel addresses
    trace_printk("ftrace_test module loaded at %pS\n", ftrace_test_init);
    
    // You can call it multiple times — it's designed for high-frequency use
    for (int i = 0; i < 5; i++) {
        trace_printk("iteration %d, current jiffies: %lu\n", i, jiffies);
    }
    
    return 0;
}

static void __exit ftrace_test_exit(void)
{
    trace_printk("ftrace_test module unloading\n");
}

module_init(ftrace_test_init);
module_exit(ftrace_test_exit);
MODULE_LICENSE("GPL");
```

Build with:
```bash
# Makefile snippet
obj-m += ftrace_test.o
KDIR := /lib/modules/$(shell uname -r)/build
all:
	make -C $(KDIR) M=$(PWD) modules
clean:
	make -C $(KDIR) M=$(PWD) clean
```

### 4. Reading trace_printk() output

```bash
# After insmod, read the trace buffer
cat /sys/kernel/debug/tracing/trace

# To see only your module's output, filter by PID
# First find PID:
cat /sys/kernel/debug/tracing/trace | grep ftrace_test

# Or clear and retrace:
echo > trace
insmod ftrace_test.ko
cat trace
```

### 5. Essential tracing control commands

```bash
# Set trace buffer size (per-CPU, in KB)
echo 4096 > buffer_size_kb

# Trace specific PIDs only
echo 1234 > set_ftrace_pid

# Add a trace_marker (user-space annotation)
echo "hello from userspace" > /sys/kernel/debug/tracing/trace_marker

# Disable tracing without losing buffer
echo 0 > tracing_on
```

## Common Pitfalls & Gotchas

1. **trace_printk() output goes to ftrace buffer, not dmesg** — This is the #1 mistake. Newcomers expect `printk()` behavior. If you `insmod` a module with `trace_printk()` and then run `dmesg`, you'll see nothing. Always read `/sys/kernel/debug/tracing/trace`. The buffer is per-CPU and lockless, so it won't corrupt under heavy tracing, but it's also not guaranteed to be in chronological order across CPUs.

2. **set_ftrace_filter is a prefix match, not exact** — Writing `do_sys_open` to the filter will match `do_sys_open`, `do_sys_openat2`, and anything else starting with that string. Use `echo 'do_sys_open' > set_ftrace_filter` with quotes to be explicit, but even then, the kernel treats it as a glob pattern. Check with `cat set_ftrace_filter` to see what actually matched. For exact matching, use `echo 'do_sys_open$' > set_ftrace_filter` (the `$` anchors the end).

3. **ftrace buffer wraps silently** — The default buffer size is often 1408 KB per CPU. If you're tracing a high-frequency function, the buffer wraps and you lose old entries. Always set `buffer_size_kb` to something appropriate for your workload. For a quick test, 512 KB is fine; for production debugging, consider 10+ MB. The tradeoff is memory pressure — each CPU gets its own buffer.

## Try It Yourself

1. **Trace the `__kmalloc` function** — Enable function tracer, filter for `__kmalloc`, then run `stress --vm 1 --vm-bytes 256M` in another terminal. Read the trace and observe the allocation patterns. Note the latency column — you'll see how long each allocation takes.

2. **Add trace_printk() to a running module** — Write a simple module that calls `trace_printk()` in a timer callback every 100ms. Load it, then use `echo function_graph > current_tracer` to see the call graph around your timer interrupt. This shows how ftrace layers work.

3. **Measure function call frequency** — Filter for `schedule` (the scheduler function), enable tracing for 5 seconds, then count occurrences: `grep -c 'schedule' /sys/kernel/debug/tracing/trace`. Compare with and without a CPU-bound workload running. This is a primitive but effective way to measure scheduler activity.

## Next Up

Tomorrow: **ftrace: Function Graph Tracer & Latency Tracing** — We'll move from "is this function called?" to "how long did it take?" The function graph tracer shows entry and exit of functions with precise timestamps, and we'll use it to find latency spikes in the block I/O layer. You'll learn how to spot the difference between a 1μs and a 100ms `submit_bio` call, and why that matters for storage performance debugging.
