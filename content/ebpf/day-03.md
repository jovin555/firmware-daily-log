---
title: "Day 03: ftrace: Function Graph Tracer & Latency Tracing"
date: 2026-06-15
tags: ["til", "ebpf", "ftrace", "latency", "graph"]
---

## What I Explored Today

Today I dove deep into ftrace's function graph tracer and latency tracing capabilities. While Day 2 covered basic function tracing (which function was called), the function graph tracer shows you the call flow with entry and exit points, plus execution duration. I also explored ftrace's specialized latency tracers—irqsoff, preemptoff, and wakeup—that automatically instrument the kernel to find worst-case latency paths. This is the tool you reach for when a real-time audio thread misses its deadline or when an embedded control loop sporadically jitters.

## The Core Concept

The function graph tracer (`function_graph`) is fundamentally different from the plain `function` tracer. The plain tracer hooks into `mcount` (or `fentry` on modern kernels) at function entry only. The graph tracer instruments both entry and exit, using a per-CPU stack of return addresses patched at runtime. When a traced function returns, ftrace's trampoline intercepts the return and records the duration.

Why does this matter? Because in embedded systems, you don't just care *that* a function was called—you care *how long it took*. A 10ms delay in `schedule()` might be acceptable in a server but catastrophic in a 1kHz motor control loop. The graph tracer gives you per-function latency histograms without needing to recompile or add `printk` statements.

The latency tracers (`irqsoff`, `preemptoff`, `wakeup`) take this further. They enable a special "latency tracking" mode that records the longest observed interval where interrupts or preemption were disabled. When a new maximum is hit, the tracer dumps the full call stack and function graph of what caused the delay. This is how you find the real culprit—often a driver holding a spinlock for too long or a misplaced `local_irq_save()`.

## Key Commands / Configuration / Code

### Setting up the function graph tracer

```bash
# Mount tracefs if not already mounted
mount -t tracefs tracefs /sys/kernel/tracing

# Set the current tracer to function_graph
echo function_graph > /sys/kernel/tracing/current_tracer

# Filter to only trace specific functions (critical for performance)
echo "do_sys_open" > /sys/kernel/tracing/set_graph_function

# Set a max depth to avoid drowning in output
echo 5 > /sys/kernel/tracing/max_graph_depth

# Start tracing
echo 1 > /sys/kernel/tracing/tracing_on

# Perform the operation you want to trace
ls /tmp

# Stop tracing
echo 0 > /sys/kernel/tracing/tracing_on

# Read the trace output
cat /sys/kernel/tracing/trace
```

Sample output (abbreviated):
```
# tracer: function_graph
#
# CPU  DURATION                  FUNCTION CALLS
# |     |   |                     |   |   |   |
 0)   0.125 us    |  do_sys_open();
 0)   0.083 us    |    getname();
 0)   0.042 us    |    get_unused_fd_flags();
 0)   0.125 us    |    do_filp_open();
 0)   0.042 us    |      path_openat();
 0)   0.083 us    |        alloc_empty_file();
 0)   0.125 us    |        dentry_open();
```

### Latency tracing: finding the worst-case IRQ-off duration

```bash
# Enable the irqsoff tracer
echo irqsoff > /sys/kernel/tracing/current_tracer

# Set a threshold (in microseconds) - only record if latency exceeds this
echo 100 > /sys/kernel/tracing/tracing_thresh

# Start tracing
echo 1 > /sys/kernel/tracing/tracing_on

# Let the system run for a while (or stress it)
sleep 10

# Stop and check the max latency
echo 0 > /sys/kernel/tracing/tracing_on
cat /sys/kernel/tracing/tracing_max_latency
# Output: 152 us (example)

# View the full trace of the worst-case event
cat /sys/kernel/tracing/trace
```

### Using trace options for better output

```bash
# Enable function graph with timestamps in absolute time (useful for correlation)
echo 1 > /sys/kernel/tracing/options/funcgraph-abstime

# Show the CPU number in the trace
echo 1 > /sys/kernel/tracing/options/funcgraph-cpu

# Don't show duration for leaf functions (cleaner output)
echo 1 > /sys/kernel/tracing/options/funcgraph-tail
```

## Common Pitfalls & Gotchas

1. **Function graph tracer overhead is significant.** Each traced function adds ~100ns of overhead due to the return trampoline. If you trace `schedule()` or `do_IRQ()` without filters, you'll distort your measurements and potentially cause livelock. Always use `set_graph_function` or `set_ftrace_filter` to narrow the scope. On embedded systems with slow CPUs (e.g., ARM Cortex-M class), even a few traced functions can cause noticeable slowdown.

2. **The `tracing_thresh` file is only used by latency tracers.** New users often set `tracing_thresh` while using the `function_graph` tracer and wonder why nothing changes. The threshold only applies to `irqsoff`, `preemptoff`, and `wakeup` tracers. For `function_graph`, you control verbosity via `max_graph_depth` and function filters.

3. **Buffer size matters for latency tracing.** The default trace buffer (often ~1MB per CPU) can overflow during long runs, causing the worst-case latency event to be lost. Always increase the buffer size before starting a latency trace: `echo 8192 > /sys/kernel/tracing/buffer_size_kb`. Each CPU gets this amount, so on a 4-core system, that's 32MB total.

## Try It Yourself

1. **Profile a syscall's function graph:** Trace `do_sys_open` with `max_graph_depth=3` while running `find /usr -name "*.conf"`. Identify which internal function takes the most cumulative time. Hint: look at the `DURATION` column for functions with children.

2. **Find your system's worst-case IRQ-off latency:** Enable the `irqsoff` tracer, set `tracing_thresh` to 50µs, and run a network stress test (`ping -f localhost` or `iperf3`). After 30 seconds, read `tracing_max_latency` and the full trace. Identify the driver or kernel path responsible.

3. **Compare function vs. function_graph overhead:** Trace `schedule` with the plain `function` tracer for 10 seconds, counting total events (`wc -l /sys/kernel/tracing/trace`). Repeat with `function_graph` and the same filter. Note the difference in event count and system responsiveness. This demonstrates why you should never use graph tracer on hot paths in production.

## Next Up

Tomorrow we'll look at **trace-cmd: Front-End for ftrace in Practice**. While direct sysfs access is great for debugging, `trace-cmd` provides a unified interface for recording, filtering, and analyzing ftrace data—including support for function graph, events, and kprobes in a single command. We'll also cover how to record traces on an embedded target and analyze them on a development host, which is the standard workflow for production debugging.
