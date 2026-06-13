---
title: "Day 01: Linux Tracing Overview: ftrace, perf, eBPF & the Stack"
date: 2026-06-13
tags: ["til", "ebpf", "tracing", "ftrace", "ebpf"]
---

## What I Explored Today

Today I mapped the Linux tracing landscape — ftrace, perf, and eBPF — and how they fit together on the kernel's instrumentation stack. I've been debugging performance issues and kernel panics for years, but I never had a clear picture of which tool to reach for and why. After digging into the kernel source, reading Documentation/trace/, and running real experiments, I can finally see the architecture: ftrace is the low-level hook framework, perf builds on it for sampling, and eBPF adds programmable, safe, in-kernel logic. This post captures the mental model I wish I'd had from day one.

## The Core Concept

Linux tracing isn't a single tool — it's a layered stack. At the bottom are **tracepoints** (static, compile-time hooks) and **kprobes/uprobes** (dynamic, runtime hooks). Above that sits **ftrace**, the core function tracer infrastructure that manages these hooks. **perf** uses ftrace's ring buffer and tracepoints for sampling and counting. **eBPF** attaches programs to these same hooks but runs sandboxed bytecode in the kernel, enabling custom aggregation and filtering without dumping raw data to userspace.

Why does this matter? Because choosing the wrong layer wastes time. If you need a histogram of `kmalloc` sizes, writing an eBPF program is overkill — `perf stat` gives you that in one command. If you need to trace a specific function argument across 10,000 calls per second, ftrace's `function_graph` tracer will drown you in data; eBPF can filter in-kernel. Understanding the stack means you pick the right tool for the signal-to-noise ratio you need.

## Key Commands / Configuration / Code

### 1. ftrace: The Foundation

ftrace exposes its control files in `/sys/kernel/tracing/` (or `/sys/kernel/debug/tracing/` on older kernels). The key files:

```bash
# Check available tracers
cat /sys/kernel/tracing/available_tracers

# Enable function tracing (lightweight, function entry only)
echo function > /sys/kernel/tracing/current_tracer
echo 1 > /sys/kernel/tracing/tracing_on
cat /sys/kernel/tracing/trace | head -20

# Enable function_graph (shows entry/exit with duration)
echo function_graph > /sys/kernel/tracing/current_tracer

# Filter to a specific function
echo do_sys_open > /sys/kernel/tracing/set_ftrace_filter

# View trace buffer
cat /sys/kernel/tracing/trace_pipe  # streaming output
```

### 2. perf: Sampling & Counting

perf builds on ftrace's tracepoints but adds hardware PMU counters and sophisticated aggregation:

```bash
# Count syscall events system-wide for 5 seconds
perf stat -e 'syscalls:sys_enter_openat' -a -- sleep 5

# Record call-graph samples (uses ftrace function_graph internally)
perf record -g -a -- sleep 10
perf report -g graph

# Trace a specific tracepoint with arguments
perf trace -e 'kmem:kmalloc' --max-events=10
```

### 3. eBPF: Programmable Tracing

eBPF attaches to the same hooks but runs user-defined programs. Minimal example using `bpftrace`:

```bash
# Count malloc calls per process (uses uprobe)
bpftrace -e 'uprobe:/lib/x86_64-linux-gnu/libc.so.6:malloc { @[comm] = count(); }'

# Trace kernel function with arguments (uses kprobe)
bpftrace -e 'kprobe:do_sys_open { printf("%s(%s)\n", comm, str(arg1)); }'
```

For a compiled eBPF program (using libbpf):

```c
// minimal_kmalloc.bpf.c
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

SEC("tracepoint/kmem/kmalloc")
int trace_kmalloc(struct trace_event_raw_kmalloc *ctx) {
    bpf_printk("kmalloc size=%d, ptr=%llx\n", ctx->size, ctx->ptr);
    return 0;
}
```

Compile with `clang -target bpf -c minimal_kmalloc.bpf.c -o minimal_kmalloc.o`, then load with `bpftool prog load` or via a minimal loader.

## Common Pitfalls & Gotchas

1. **ftrace buffer overflow**: The default trace buffer is small (often 1-2 MB per CPU). If you trace a high-frequency function like `kmalloc`, the buffer wraps in milliseconds. Always set a filter (`set_ftrace_filter`) or increase buffer size: `echo 8192 > /sys/kernel/tracing/buffer_size_kb`. I learned this the hard way when my trace showed only idle functions.

2. **perf and ftrace conflict**: Both tools use the same ftrace infrastructure. Running `perf record -g` while ftrace is active will fail silently or produce corrupted traces. Always check `cat /sys/kernel/tracing/current_tracer` is `nop` before running perf. Use `echo nop > current_tracer` to reset.

3. **eBPF verifier limits**: The eBPF verifier enforces strict bounds on loops (must be bounded) and stack size (512 bytes max). A common mistake is trying to iterate a variable-length list — the verifier rejects it. Use `bpf_for_each_map_elem` or bounded loops with `#pragma unroll`. Also, never use `bpf_printk` in production; it writes to `/sys/kernel/debug/tracing/trace_pipe` and kills performance.

## Try It Yourself

1. **Trace `open` syscalls with ftrace**: Set `current_tracer` to `function`, filter on `do_sys_open`, then run `ls` in another terminal. Pipe the output to `wc -l` to see how many times `open` is called. Then switch to `function_graph` and note the duration column — which file operations take the longest?

2. **Count page faults with perf**: Run `perf stat -e 'exceptions:page_fault_user' -a -- sleep 10` while running a memory-intensive program (e.g., `stress-ng --vm 2 --vm-bytes 256M`). Compare the count to an idle system. Then try `perf record -e 'exceptions:page_fault_user' -a -g` and generate a flamegraph with `perf script | stackcollapse-perf.pl | flamegraph.pl`.

3. **Write a one-liner eBPF program**: Use `bpftrace` to trace all `kmalloc` calls and print the size distribution: `bpftrace -e 'kprobe:kmalloc { @size = hist(arg0); }'`. Run for 10 seconds, then Ctrl-C to see the histogram. Notice the bimodal distribution — small allocations for objects, large ones for pages.

## Next Up

Tomorrow I'll dive into **ftrace: Function Tracer & trace_printk Setup** — how to instrument specific kernel functions, use `trace_printk()` for ad-hoc debugging without recompiling, and build a custom tracer that logs function arguments. We'll go from theory to a working debug session on a real kernel module.
