---
title: "Day 04: trace-cmd: Front-End for ftrace in Practice"
date: 2026-06-16
tags: ["til", "ebpf", "trace-cmd", "ftrace"]
---

## What I Explored Today

Today I went deep on `trace-cmd`, the command-line front-end that wraps the kernel's ftrace infrastructure into something actually usable for real-world debugging. I've been manually poking at `/sys/kernel/tracing/` for weeks, but `trace-cmd` eliminates the boilerplate while exposing ftrace's full power. I tested it on a 6.8 kernel running on an x86_64 workstation, tracing everything from scheduler wakeups to block I/O completions. The key insight: `trace-cmd` doesn't add new tracing capabilities—it makes ftrace's existing machinery accessible without writing shell scripts that manipulate tracefs files.

## The Core Concept

Ftrace is the kernel's built-in tracer, but its native interface is a filesystem: you echo values into control files, read trace outputs from pseudo-files, and manage buffers manually. This works for quick experiments, but it's brittle and doesn't scale. `trace-cmd` solves this by providing a unified CLI that handles buffer setup, event selection, recording, and post-processing. Under the hood, `trace-cmd` still writes to the same tracefs files—it just does it correctly and atomically.

The real power comes from `trace-cmd record` and `trace-cmd report`. The `record` command captures trace data into a binary file (`trace.dat` by default) with full timestamps and CPU affinity. The `report` command parses that file into human-readable output, with optional filtering and format customization. This decoupling means you can capture traces on a production system with minimal overhead, then analyze them offline.

## Key Commands / Configuration / Code

### Basic event tracing

```bash
# Record all sched_switch events for 5 seconds
trace-cmd record -e sched:sched_switch sleep 5

# View the recorded trace
trace-cmd report
```

### Tracing a specific function with function_graph

```bash
# Enable function_graph tracer on a single function
trace-cmd start -p function_graph -g do_sys_open
# Run your workload
ls /tmp
# Stop and dump
trace-cmd stop
trace-cmd show > function_trace.txt
trace-cmd reset
```

### Filtering events by PID and field values

```bash
# Only trace write syscalls from PID 1234, with size > 4096
trace-cmd record -e syscalls:sys_enter_write \
    -f 'common_pid == 1234 && count > 4096' \
    sleep 3
```

### Recording with stack traces

```bash
# Record block I/O completions with kernel stack traces
trace-cmd record -e block:block_rq_complete \
    -T \
    sleep 10

# -T adds stack traces to each event
```

### Using instances for isolation

```bash
# Create a separate trace instance to avoid polluting the main buffer
trace-cmd record -B my_instance \
    -e sched:sched_wakeup \
    -e sched:sched_switch \
    sleep 5

# Check instance exists
ls /sys/kernel/tracing/instances/my_instance/
```

### Custom trace with plugins

```bash
# Use the 'blk' plugin for block layer tracing
trace-cmd record -p blk sleep 5
trace-cmd report --cpu 2-3  # Only show CPUs 2 and 3
```

## Common Pitfalls & Gotchas

**1. Forgetting to reset after `trace-cmd start`**
If you use `trace-cmd start` (which leaves tracing enabled), you must call `trace-cmd reset` when done. Otherwise, ftrace remains active and consumes buffer space and CPU. Always prefer `trace-cmd record` for bounded tracing—it automatically resets on completion.

**2. Buffer size mismatches for long-running traces**
Default per-CPU buffer is ~1MB. For high-throughput events (like `sched_switch` on a 128-CPU box), this fills in milliseconds. Use `-b` to increase buffer size:
```bash
trace-cmd record -b 4096 -e sched:sched_switch sleep 60  # 4MB per CPU
```
Check buffer usage with `trace-cmd stat` during recording.

**3. Event name ambiguity**
Event names are hierarchical: `sched:sched_switch` means subsystem `sched`, event `sched_switch`. Omitting the subsystem (`-e sched_switch`) sometimes works but can match multiple events. Always use the full `subsystem:event` syntax to avoid surprises.

**4. `trace-cmd report` timestamp drift on NUMA systems**
On multi-socket machines, TSC synchronization isn't perfect. Use `trace-cmd report --ts-offset` to apply manual corrections, or record with `-k` (keep kernel clock) for better cross-CPU ordering.

## Try It Yourself

1. **Trace a specific process's system calls**: Run `trace-cmd record -e syscalls:sys_enter_openat -P $(pidof your_app) sleep 5`, then use `trace-cmd report` to see every file your application opened. Filter the output to find failed opens (return value < 0).

2. **Measure scheduler latency**: Record `sched:sched_wakeup` and `sched:sched_switch` events for 10 seconds while running a CPU-bound workload. Use `trace-cmd report --event-comm` to see which tasks are preempting each other, then calculate the average wakeup-to-schedule latency using `trace-cmd stat`.

3. **Debug a kernel module with function_graph**: Load a custom kernel module, then run `trace-cmd start -p function_graph -g my_module_function` followed by your test workload. Dump the trace with `trace-cmd show` and look for unexpected function call chains or excessive nesting depth.

## Next Up

Tomorrow I'm diving into **perf: Performance Counters & Hardware PMU Events**. While ftrace gives us software events and function tracing, perf unlocks the CPU's hardware performance monitoring unit—cache misses, branch mispredictions, stalled cycles, and more. We'll compare `perf stat` vs `perf record`, learn how to multiplex PMU events on modern Intel/AMD cores, and use `perf top` to find hot functions in real-time.
