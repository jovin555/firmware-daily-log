---
title: "Day 22: Linux Tracing Overview: ftrace, perf, eBPF & the Stack"
date: 2026-07-04
tags: ["til", "ebpf", "tracing", "ftrace", "ebpf"]
---

## What I Explored Today

Today I zoomed out to map the Linux tracing landscape. After weeks of deep-diving into eBPF internals, I realized I needed a mental model of how ftrace, perf, and eBPF fit together—and more importantly, when to use each. I spent the day tracing through kernel documentation, reading the tracefs filesystem layout, and running side-by-side comparisons of the same tracing task with different tools. The key insight: these aren't competing technologies; they're layers of the same onion, with eBPF being the most recent and flexible, but not always the right choice.

## The Core Concept

Linux tracing is fundamentally about observing kernel and user-space execution without modifying code or restarting systems. The tracing stack has evolved in three generations:

**Generation 1: ftrace** (2008) — The function tracer. Built into the kernel, exposed via debugfs/tracefs. Zero overhead when disabled. Perfect for function entry/exit tracing, latency analysis, and simple event counting. No BPF bytecode required.

**Generation 2: perf** (2009) — The performance counter subsystem. Uses hardware PMU counters, software events, and tracepoints. Provides sampling, counting, and profiling. The `perf` tool is the user-facing interface. It can use eBPF programs since kernel 4.9, but its core is counter-based.

**Generation 3: eBPF** (2014+) — The programmable tracer. Allows safe, sandboxed programs to run inside the kernel at tracepoints, kprobes, and perf events. Provides arbitrary data aggregation, filtering, and output. Requires a compiler toolchain (clang/LLVM) and kernel support.

The critical distinction: ftrace is for *observation*, perf is for *measurement*, eBPF is for *programmable observation and control*. Choose ftrace when you need to see function call flows. Choose perf when you need CPU cycle counts or hardware events. Choose eBPF when you need custom logic, complex filtering, or data aggregation.

## Key Commands / Configuration / Code

### 1. ftrace: Quick function graph trace
```bash
# Mount tracefs if not already mounted
mount -t tracefs tracefs /sys/kernel/tracing

# Set the tracer to function_graph
echo function_graph > /sys/kernel/tracing/current_tracer

# Filter to a specific function (e.g., do_sys_open)
echo do_sys_open > /sys/kernel/tracing/set_ftrace_filter

# Start tracing
echo 1 > /sys/kernel/tracing/tracing_on

# Trigger the function (e.g., open a file)
cat /etc/passwd > /dev/null

# Stop and read
echo 0 > /sys/kernel/tracing/tracing_on
cat /sys/kernel/tracing/trace | head -40
```

### 2. perf: Hardware event sampling
```bash
# Count CPU cycles for a command
perf stat -e cycles,instructions,cache-misses sleep 1

# Sample stack traces at 99 Hz
perf record -F 99 -a -g -- sleep 10
perf report --stdio

# Trace a specific syscall with arguments
perf trace -e openat,close -- ls /tmp
```

### 3. eBPF: Custom tracepoint program (bpftrace one-liner)
```bash
# Count syscalls by process name (requires bpftrace)
bpftrace -e 'tracepoint:syscalls:sys_enter_* { @[probe] = count(); }'

# Trace openat with filename and return value
bpftrace -e 'tracepoint:syscalls:sys_enter_openat { printf("%s %s\n", comm, str(args->filename)); }'
```

### 4. Kernel config check
```bash
# Verify tracing support in your kernel
zcat /proc/config.gz | grep -E "FTRACE|PERF_EVENT|BPF"
# Look for: CONFIG_FTRACE=y, CONFIG_PERF_EVENTS=y, CONFIG_BPF=y
```

## Common Pitfalls & Gotchas

**1. ftrace buffer overflow on fast paths**
When tracing high-frequency functions (like `kmalloc` or `schedule`), the ftrace ring buffer fills in milliseconds. Always use `set_ftrace_filter` to narrow scope, or increase buffer size: `echo 8192 > /sys/kernel/tracing/buffer_size_kb`. Without filtering, you'll lose events or crash the system with trace log flood.

**2. perf sampling vs. counting confusion**
`perf stat` counts *all* events (exact, but high overhead). `perf record` *samples* events (low overhead, but statistical). New engineers often use `perf record` for precise counts and get misleading results. Use `perf stat` for exact counts, `perf record` for profiling where statistical accuracy is acceptable.

**3. eBPF program complexity limits**
eBPF verifier enforces strict limits: 4096 instructions, 512 bytes of stack, no loops (unless bounded and verified). Complex tracepoint programs that work on one kernel version may fail on another due to verifier changes. Always test with `bpftool prog load` before attaching to production systems.

## Try It Yourself

1. **Compare ftrace and perf for the same task**: Trace the `do_sys_open` function using ftrace's function_graph tracer, then use `perf trace -e openat` to capture the same syscall. Note the difference in output format and overhead (run each for 10 seconds while `ls -R /usr` runs in another terminal).

2. **Measure context switch latency with ftrace**: Enable the `sched_switch` tracepoint via ftrace: `echo 1 > /sys/kernel/tracing/events/sched/sched_switch/enable`. Run a CPU-bound process and measure the time between consecutive switches. Compare with `perf sched record` output.

3. **Write a bpftrace one-liner to count failed syscalls**: Use the `tracepoint:syscalls:sys_exit_*` probe and filter for return values < 0. Count by syscall name and error code. Hint: `args->ret` contains the return value.

## Next Up

Tomorrow we dive deep into **ftrace: Function Tracer & trace_printk Setup**. We'll configure ftrace from scratch, use `trace_printk()` to instrument kernel modules without recompiling, and build a custom function graph trace for a real-world driver. Bring your kernel source tree—we're going hands-on with the tracefs filesystem.
