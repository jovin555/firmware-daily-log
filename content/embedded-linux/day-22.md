---
title: "Day 22: ftrace & trace-cmd: Function & Latency Tracing"
date: 2026-07-04
tags: ["til", "embedded-linux", "ftrace", "tracing"]
---

## What I Explored Today

Today I dug into ftrace, the Linux kernel's built-in tracing framework, and its companion tool `trace-cmd`. On embedded systems where every microsecond matters, ftrace lets you trace kernel function calls, measure interrupt latencies, and track scheduling events with minimal overhead—often less than 1% CPU impact. I focused on two practical workflows: function call tracing to find unexpected code paths, and latency tracing to catch interrupt storms and preemption delays that plague real-time systems.

## The Core Concept

Ftrace is not a single tool but a collection of tracers built into the kernel's tracing infrastructure. It works by inserting lightweight probes at function entry and exit points, or by using static tracepoints placed by developers. The key insight: ftrace can be enabled and disabled at runtime without recompiling the kernel, making it invaluable for debugging production embedded systems.

Why does this matter for embedded engineers? When your sensor driver misses a deadline or your audio pipeline glitches, you need to know *what the kernel was doing* at that exact moment. Ftrace gives you a function-level call graph showing every kernel function executed, with timestamps precise to the nanosecond. Unlike `perf` which samples, ftrace can record *every* function call in a critical path—though you must be careful about overhead on slower CPUs.

The architecture is simple: the kernel maintains per-CPU trace buffers. Tracers write to these buffers, and you read them via debugfs (`/sys/kernel/debug/tracing/`) or with `trace-cmd` which provides a cleaner interface and binary recording format.

## Key Commands / Configuration / Code

### Prerequisites: Kernel config
Ensure your kernel has these enabled (check `/boot/config-$(uname -r)`):
```
CONFIG_FUNCTION_TRACER=y
CONFIG_FUNCTION_GRAPH_TRACER=y
CONFIG_IRQSOFF_TRACER=y
CONFIG_PREEMPTIRQ_TRACER=y
CONFIG_TRACER_SNAPSHOT=y
```

### 1. Function tracing with trace-cmd

```bash
# Record all function calls in the 'my_driver' module for 5 seconds
trace-cmd record -p function -l 'my_driver:*' -T -o trace.dat sleep 5

# View the recorded trace
trace-cmd report trace.dat | head -50

# Live tracing (no recording)
trace-cmd start -p function -l 'my_driver:*'
# ... do something ...
trace-cmd stop
trace-cmd show
```

### 2. Function graph tracing (shows call depth and duration)

```bash
# Trace with function graph, filtering to a specific function
trace-cmd record -p function_graph -g my_function -T sleep 3

# The -g flag sets the "graph function" filter
# Output shows entry/exit with duration:
#  my_function() {
#    sub_func1() {
#      ...
#    } /* sub_func1: 2.345 us */
#  } /* my_function: 5.678 us */
```

### 3. Latency tracing: irqsoff and preemptoff

```bash
# Trace maximum time interrupts were disabled
echo irqsoff > /sys/kernel/debug/tracing/current_tracer
echo 1 > /sys/kernel/debug/tracing/tracing_on
# Wait for a latency event...
cat /sys/kernel/debug/tracing/trace  # Shows the worst-case latency path

# Using trace-cmd for the same
trace-cmd record -p irqsoff sleep 10
trace-cmd report trace.dat | grep -A 20 "latency"
```

### 4. Using trace events (static tracepoints)

```bash
# List available events
trace-cmd list -e

# Trace scheduler wakeups and IRQ handlers
trace-cmd record -e sched:sched_wakeup -e irq:irq_handler_entry sleep 5

# Filter events by PID
trace-cmd record -e sched:sched_switch -f 'prev_pid == 1234' sleep 5
```

### 5. Snapshot on latency trigger

```bash
# Set a latency threshold (in microseconds)
echo 100 > /sys/kernel/debug/tracing/tracing_thresh
echo irqsoff > /sys/kernel/debug/tracing/current_tracer
echo 1 > /sys/kernel/debug/tracing/tracing_on

# When an IRQ-off period exceeds 100us, the buffer is snapshotted
cat /sys/kernel/debug/tracing/trace  # Shows the snapshot
```

## Common Pitfalls & Gotchas

1. **Buffer overflow on slow targets**: The default trace buffer is 1-2 MB per CPU. On a 200 MHz ARM Cortex-A5, tracing every function call in a hot path can overflow the buffer in milliseconds. Always set a filter (`-l` or `-g`) and consider reducing buffer size: `echo 512 > /sys/kernel/debug/tracing/buffer_size_kb`.

2. **Function tracing overhead is real**: While ftrace is lightweight (typically 50-200 ns per function entry), tracing every kernel function on a busy system can add 5-10% CPU overhead. On deeply embedded systems, use trace events instead of function tracers, or limit tracing to specific modules.

3. **trace-cmd record vs trace-cmd start confusion**: `trace-cmd record` captures data to a file and stops automatically. `trace-cmd start` enables tracing in the background—you must manually `stop` and `extract` or `show`. Forgetting to stop leaves tracing running, consuming memory and CPU.

4. **Snapshot mode requires explicit setup**: The `tracing_thresh` + snapshot trick only works if you've enabled `CONFIG_TRACER_SNAPSHOT`. Without it, the latency tracer will still record, but you'll get the entire buffer, not just the worst-case event.

## Try It Yourself

1. **Find your longest IRQ-off latency**: On your target board, enable the `irqsoff` tracer, set `tracing_thresh` to 50 microseconds, and trigger a network transfer or USB operation. Examine the trace to identify which function held interrupts off the longest.

2. **Trace a driver probe**: Use `trace-cmd record -p function_graph -g <your_driver_probe_function>` to capture the full call graph during driver initialization. Look for unexpected calls to `msleep()` or `printk()` that could slow boot time.

3. **Filter a noisy trace**: Enable `sched:sched_switch` events for your application's PID only. Use `trace-cmd record -e sched:sched_switch -f 'next_pid == <your_pid>' sleep 5`. Analyze how often your task gets preempted and by which process.

## Next Up

Tomorrow we'll move from tracing to profiling with `perf`: sampling CPU performance counters, finding hot functions, and measuring cache misses—all on resource-constrained embedded targets. We'll cover how to use `perf stat` for cycle counting and `perf record` with call-graphs to identify optimization opportunities without a full debugger.
