---
title: "Day 14: eBPF uprobes: Tracing Userspace from Kernel"
date: 2026-06-26
tags: ["til", "ebpf", "uprobes", "ebpf"]
---

## What I Explored Today

Today I dove into eBPF uprobes—the mechanism that lets kernel-space eBPF programs attach to userspace function entry and exit points. Unlike kprobes (kernel probes) which hook kernel functions, uprobes operate on any userspace binary, shared library, or even JIT-compiled code. I built a tracer that intercepts `malloc` calls in a running process, capturing allocation sizes and stack traces without modifying the application or recompiling anything. This is the foundation for tools like `bpftrace` and `perf` when they profile userspace.

## The Core Concept

The power of uprobes is that they bridge the kernel-userspace boundary with zero instrumentation overhead when not active. You attach a tiny eBPF program to a specific instruction address in a userspace binary. When that instruction executes, the CPU traps into the kernel, runs your eBPF program, and returns—all in the context of the triggering process.

Why not just use `ptrace`? Because `ptrace` stops the process, injects a signal, and requires context switches. Uprobes execute inline, with microsecond-level latency, and can filter or aggregate data without ever waking userspace. The key insight: uprobes run in kernel context but have access to the userspace register state and memory via `bpf_probe_read_user()`.

The attachment point is a file offset or symbol name in an ELF binary. The kernel inserts a breakpoint instruction (typically `int3` on x86) at that address. When hit, the breakpoint handler checks if an eBPF program is registered for that address, executes it, then single-steps the original instruction and resumes.

## Key Commands / Configuration / Code

Let's trace `malloc` in a running `bash` process. First, find the `malloc` address in libc:

```bash
# Get PID of a running bash
BASH_PID=$(pgrep -n bash)

# Find libc base address from /proc/<pid>/maps
LIBC_BASE=$(grep libc /proc/$BASH_PID/maps | head -1 | awk '{print $1}' | cut -d'-' -f1)

# Get offset of malloc in libc
MALLOC_OFF=$(nm -D /usr/lib/x86_64-linux-gnu/libc.so.6 | grep '\<malloc\>' | awk '{print $1}')

# Calculate absolute address for uprobe
MALLOC_ADDR=$((0x$LIBC_BASE + 0x$MALLOC_OFF))
echo "Attaching uprobe at 0x$(printf '%x' $MALLOC_ADDR)"
```

Now the eBPF C program (`malloc_trace.c`):

```c
// SPDX-License-Identifier: GPL-2.0
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

// Perf event output buffer
struct {
    __uint(type, BPF_MAP_TYPE_PERF_EVENT_ARRAY);
    __uint(key_size, sizeof(int));
    __uint(value_size, sizeof(u32));
    __uint(max_entries, 128);
} events SEC(".maps");

// Capture malloc(size) argument
SEC("uprobe//usr/lib/x86_64-linux-gnu/libc.so.6:malloc")
int trace_malloc_entry(struct pt_regs *ctx)
{
    // On x86_64, first argument is in di register
    size_t size = PT_REGS_PARM1(ctx);
    
    // Build event struct
    struct {
        u32 pid;
        u64 size;
        u64 timestamp;
    } event = {
        .pid = bpf_get_current_pid_tgid() >> 32,
        .size = size,
        .timestamp = bpf_ktime_get_ns(),
    };
    
    // Output to perf buffer (CPU 0 for simplicity)
    bpf_perf_event_output(ctx, &events, BPF_F_CURRENT_CPU,
                          &event, sizeof(event));
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
```

Compile and load:

```bash
# Compile with clang (requires bpf target)
clang -O2 -target bpf -c malloc_trace.c -o malloc_trace.o

# Attach uprobe to running bash
sudo bpftool prog load malloc_trace.o /sys/fs/bpf/malloc_trace
sudo bpftool prog attach pinned /sys/fs/bpf/malloc_trace uprobe /proc/$BASH_PID/fd/3 0x$(printf '%x' $MALLOC_ADDR)
```

Read events from userspace (simplified Python with `bcc`):

```python
from bcc import BPF
import time

b = BPF(src_file="malloc_trace.c")
b.attach_uprobe(name="/usr/lib/x86_64-linux-gnu/libc.so.6",
                sym="malloc", fn_name="trace_malloc_entry")

def print_event(cpu, data, size):
    event = b["events"].event(data)
    print(f"PID {event.pid}: malloc({event.size}) at {event.timestamp}")

b["events"].open_perf_buffer(print_event)
while True:
    b.perf_buffer_poll(timeout=100)
```

## Common Pitfalls & Gotchas

**1. Address space layout randomization (ASLR) breaks hardcoded offsets.**  
You can't use the same absolute address across runs or even across different processes. Always resolve the address dynamically from `/proc/<pid>/maps` at attach time, or use symbol-based attachment (which `bpftrace` and `bcc` do for you). If you hardcode an offset from a specific libc build, it will fail on the next library update.

**2. `bpf_probe_read_user()` vs direct dereference.**  
You cannot directly dereference userspace pointers in eBPF. The kernel runs in a different address space. Always use `bpf_probe_read_user()` (or `bpf_probe_read_user_str()` for strings) to safely read userspace memory. Forgetting this causes verifier rejection or kernel crashes.

**3. Uretprobes require careful stack state management.**  
Uretprobes (tracing function returns) work by hijacking the return address on the stack. This means the eBPF program runs *after* the function returns, but the return value is in the register. The tricky part: you must store context from the entry probe (e.g., via a BPF map) because the uretprobe has no access to the original arguments. Always pair entry and exit probes with a per-thread map keyed by PID+TID.

## Try It Yourself

1. **Trace `strlen` calls in a running process.** Attach a uprobe to `libc:strlen` and log the string length and first 16 characters (using `bpf_probe_read_user_str`). Verify with a simple `echo "hello"` in the target shell.

2. **Build a malloc/free leak detector.** Create a pair of uprobe (malloc entry) and uretprobe (malloc return) to track allocated addresses. On free (uprobe on `free`), remove the address. Print any addresses still allocated after 10 seconds. Use a BPF hash map keyed by PID.

3. **Profile a specific function's execution time.** Attach a uprobe at function entry to record a timestamp in a per-thread map, and a uretprobe at exit to compute the delta. Output to perf buffer. Try it on a function in your own compiled C program.

## Next Up

Tomorrow: **eBPF Maps: Hash, Array, Ring Buffer & Perf Events** — we'll dive into the data structures that make eBPF programs stateful, covering map types, key/value design patterns, and how to choose between ring buffers and perf event arrays for high-throughput tracing.
