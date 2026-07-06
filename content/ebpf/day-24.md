---
title: "Day 24: ftrace: Function Graph Tracer & Latency Tracing"
date: 2026-07-06
tags: ["til", "ebpf", "ftrace", "latency", "graph"]
---

## What I Explored Today

Today I dove deep into ftrace's function_graph tracer and its latency tracing capabilities. While the function tracer shows you *which* kernel functions are called, the function_graph tracer reveals the call hierarchy and execution duration at each level. I spent the morning instrumenting a USB storage driver to understand why `blk_mq_make_request` was sporadically taking 200+ milliseconds. The function_graph tracer, combined with ftrace's built-in latency triggers, let me pinpoint the exact call chain causing the stall without recompiling the kernel or adding a single printk.

## The Core Concept

The function_graph tracer works by hooking into the kernel's function entry and return paths (`mcount`/`fentry` and `fexit`). At each function entry, it records a timestamp and pushes the function name onto a per-CPU stack. At return, it computes the delta and pops the stack. The result is a tree-structured trace showing not just which functions ran, but how long each took.

Why this matters: When you're debugging a latency spike in an interrupt handler, a syscall, or a kernel worker thread, you need to know *where* the time went. The function tracer alone gives you a flat list of called functions—useful for counting, useless for timing. The function_graph tracer gives you a hierarchical view with microsecond precision. It's the difference between knowing "`do_sync_write` was called 500 times" and seeing "`do_sync_write` → `vfs_write` → `ext4_file_write_iter` → `ext4_da_write_begin` took 47ms because of a page allocation stall."

ftrace's latency tracing extends this further. You can configure triggers that capture a function_graph trace only when a function's execution exceeds a threshold, or when a specific event (like a scheduler wakeup) occurs. This is invaluable for catching rare, intermittent latency issues that would flood your logs if traced continuously.

## Key Commands / Configuration / Code

First, verify function_graph is available:

```bash
# List available tracers
cat /sys/kernel/tracing/available_tracers
# Should include: function_graph function nop
```

Enable the function_graph tracer and trace a specific function:

```bash
cd /sys/kernel/tracing

# Set the tracer
echo function_graph > current_tracer

# Trace only the function we care about (and its callees)
echo __blk_mq_make_request > set_graph_function

# Set max depth to avoid infinite recursion in common helpers
echo 20 > max_graph_depth

# Enable tracing
echo 1 > tracing_on

# Wait for the event (or trigger it manually)
# ... time passes ...

# Capture the trace
cat trace > /tmp/graph_trace.txt

# Disable when done
echo 0 > tracing_on
echo nop > current_tracer
```

For latency tracing with a threshold trigger:

```bash
# Set function_graph tracer
echo function_graph > current_tracer

# Add a latency trigger on a specific function
# This captures a graph trace whenever __blk_mq_make_request takes > 50ms
echo '__blk_mq_make_request: latency=50000' > set_ftrace_filter

# Enable the trace buffer to be large enough for the capture
echo 4096 > buffer_size_kb

# Start tracing
echo 1 > tracing_on

# After the latency event occurs, check the trace
cat trace
```

To trace a specific process's syscall latency:

```bash
# Trace only PID 1234
echo 1234 > set_ftrace_pid

# Set function_graph
echo function_graph > current_tracer

# Optionally, only trace functions matching a pattern
echo 'do_sys_*' > set_graph_function

# Start
echo 1 > tracing_on
```

Interpreting the output:

```
 1)               |  __blk_mq_make_request() {
 1)   0.120 us    |    blk_mq_get_tag();
 1)   0.050 us    |    blk_mq_bio_to_request();
 1)               |    blk_mq_map_request() {
 1)   0.030 us    |      blk_mq_rq_ctx_init();
 1)   0.020 us    |      blk_mq_map_swqueue();
 1)   0.080 us    |    }
 1)   0.010 us    |    blk_mq_queue_rq();
 1) ! 201.450 us  |  }
```

The `!` marker indicates this function took over 100 microseconds. The timestamp is in microseconds. The indentation shows the call depth.

## Common Pitfalls & Gotchas

1. **Buffer overflow with function_graph**: The function_graph tracer generates enormous amounts of data. If you trace a frequently called function (like `schedule` or `kmalloc`) without a filter, you'll fill the trace buffer in milliseconds. Always set `set_graph_function` or `set_ftrace_pid` first. I once crashed a production box by forgetting to set a filter—the trace buffer consumed all available memory.

2. **max_graph_depth is your friend**: Without a depth limit, ftrace will follow every nested call, including common helpers like `spin_lock` and `preempt_enable`. This creates noise and can cause stack overflows on deeply nested paths. Set `max_graph_depth` to 10-20 for most debugging sessions.

3. **Latency triggers are one-shot by default**: When you set a latency threshold trigger, ftrace captures one event and then stops tracing. You need to clear the trace buffer and re-enable tracing for each subsequent capture. Use `echo > trace` to clear, then `echo 1 > tracing_on` to re-arm.

4. **SMP artifacts**: On multi-core systems, the function_graph output interleaves traces from different CPUs. Look at the CPU number in the first column (e.g., `1)` means CPU 1). If you're debugging a single-threaded issue, filter by PID to avoid cross-CPU noise.

## Try It Yourself

1. **Measure syscall latency**: Write a simple C program that calls `write()` to a file. Use `set_graph_function` to trace only `sys_write` and its callees. Run your program and capture the graph. Identify which function inside the write path takes the most time.

2. **Set up a latency trigger**: Choose a function you suspect might occasionally stall (e.g., `do_sync_write` on a slow filesystem). Set a latency threshold of 10ms. Trigger the condition (e.g., by writing a large file to an NFS mount). Capture the trace and identify the exact function that caused the delay.

3. **Compare function vs function_graph**: Trace the same workload (e.g., `ls -lR /usr`) with both the `function` and `function_graph` tracers. Compare the output formats. Notice how `function` gives you a flat call count, while `function_graph` shows the call tree and durations. Which one would you use for a performance regression?

## Next Up

Tomorrow, we'll move from raw ftrace to **trace-cmd: Front-End for ftrace in Practice**. We'll explore how trace-cmd simplifies tracing setup, enables recording to disk for offline analysis, and provides a unified interface for both ftrace and perf events—essential for any engineer who needs to trace kernel behavior without memorizing every sysfs knob.
