---
title: "Day 25: trace-cmd: Front-End for ftrace in Practice"
date: 2026-07-07
tags: ["til", "ebpf", "trace-cmd", "ftrace"]
---

## What I Explored Today

After weeks of manually interacting with `/sys/kernel/tracing/` and writing shell scripts to toggle trace points, I finally dedicated a full day to `trace-cmd` — the proper command-line front-end for ftrace. While raw ftrace gives you surgical control, `trace-cmd` wraps that power into a sane, reproducible workflow. Today I used it to trace a real-world kernel preemption issue in a network driver, and I’m not going back to manual file writes for anything beyond quick experiments.

## The Core Concept

`trace-cmd` is to ftrace what `strace` is to `ptrace` — it abstracts the kernel’s tracing infrastructure into a CLI that handles setup, teardown, and data collection without you touching tracefs directly. But it’s not just a wrapper; it adds critical features: per-CPU buffering, event filtering, function graph depth control, and a binary output format (`trace.dat`) that can be post-processed with `kernelshark` or custom scripts.

The real win is **reproducibility**. A single `trace-cmd record` command replaces a dozen `echo` writes to tracefs files, and the `-e` flag lets you specify events with glob patterns. For production debugging, you can run it with `-B` to create a separate buffer per CPU, avoiding trace loss on heavily loaded systems.

## Key Commands / Configuration / Code

### 1. Basic Event Recording

```bash
# Record all sched_switch events for 5 seconds
trace-cmd record -e sched:sched_switch -o trace.dat sleep 5

# Record with function graph for a specific function, 3 levels deep
trace-cmd record -p function_graph -g netif_receive_skb --max-graph-depth 3 sleep 2
```

### 2. Filtering Events by PID and Field Values

```bash
# Trace only events from PID 1234, with wakeup latency > 1000us
trace-cmd record -e sched:sched_wakeup \
    -f "common_pid == 1234 && prio < 100" \
    -e sched:sched_switch \
    -f "prev_pid == 1234 || next_pid == 1234" \
    sleep 10
```

The `-f` flag accepts ftrace filter syntax — same as writing to `events/*/filter` files. Use `common_pid` to filter by the tracing process itself, or `prev_pid`/`next_pid` for scheduler events.

### 3. Per-CPU Buffers and Snapshot Mode

```bash
# Create per-CPU buffers (avoids lock contention on shared buffer)
trace-cmd record -B cpu0 -e irq:irq_handler_entry \
                 -B cpu1 -e irq:irq_handler_entry \
                 sleep 3

# Snapshot mode: start tracing, then take a snapshot on demand
trace-cmd start -e sched:sched_switch -B snapshot
# ... wait for condition ...
trace-cmd snapshot -s
trace-cmd stop
trace-cmd show > snapshot_output.txt
```

### 4. Reading and Analyzing Output

```bash
# Dump recorded trace to human-readable format
trace-cmd report trace.dat | head -20

# Use kernelshark for GUI analysis (install separately)
kernelshark trace.dat &

# Extract only events from a specific CPU
trace-cmd report --cpu 2 trace.dat
```

### 5. Practical Example: Tracing Network SoftIRQ Latency

```bash
# Record softirq entry/exit with timestamps
trace-cmd record -e irq:softirq_entry \
                 -e irq:softirq_exit \
                 -e net:netif_receive_skb \
                 -T  # adds stack traces on events
```

The `-T` flag is a lifesaver — it records kernel stack traces for each event, letting you see exactly which code path triggered the softirq.

## Common Pitfalls & Gotchas

1. **Buffer Size Mismanagement**: Default trace buffer is 1MB per CPU. On a 64-core machine recording `sched_switch` at 100k events/sec, you’ll overflow in under a second. Always set `-b 4096` (4MB per CPU) or higher for production workloads. Use `trace-cmd stat` to check current buffer usage.

2. **Filter Syntax Is Fragile**: The ftrace filter parser is picky. `-f "prev_pid == 1234"` works, but `-f "prev_pid == 1234 && next_pid == 5678"` may silently fail if the event doesn’t have `next_pid`. Always run `trace-cmd record -e sched:sched_switch -f "bogus_field == 1" sleep 1` first — it will print an error if the field doesn’t exist.

3. **Snapshot Mode Requires Pre-Allocation**: If you use `-B snapshot`, you must call `trace-cmd snapshot -s` *before* the buffer fills. The snapshot buffer is a separate, pre-allocated buffer that captures the current trace buffer atomically. If you wait too long, the snapshot will be empty because the main buffer already overwrote the data.

## Try It Yourself

1. **Trace a specific process’s system calls**: Use `trace-cmd record -e syscalls:sys_enter_* -P $(pidof your_daemon) sleep 5` to capture all syscall entries for a running daemon. Then use `trace-cmd report trace.dat | awk '{print $6}' | sort | uniq -c | sort -rn` to find the most frequent syscalls.

2. **Measure interrupt latency**: Record `irq:irq_handler_entry` and `irq:irq_handler_exit` for your network interface (e.g., `eth0`). Use `trace-cmd report` and pipe to `awk` to compute the delta between entry and exit timestamps. Identify the longest handler.

3. **Debug a kernel function with graph tracing**: Pick a function you suspect is slow (e.g., `tcp_v4_rcv`). Run `trace-cmd record -p function_graph -g tcp_v4_rcv --max-graph-depth 5 sleep 3`. Open the output in `kernelshark` and look for functions with unusually high execution time.

## Next Up

Tomorrow we leave ftrace behind and dive into **perf: Performance Counters & Hardware PMU Events** — we’ll measure cache misses, branch mispredictions, and CPU cycles at the hardware level, and learn how to correlate them with kernel trace events for holistic performance analysis.
