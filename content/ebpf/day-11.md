---
title: "Day 11: BCC: Writing eBPF Programs in Python"
date: 2026-06-23
tags: ["til", "ebpf", "bcc", "ebpf", "python"]
---

## What I Explored Today

Today I dove into BCC (BPF Compiler Collection), the Python frontend that makes eBPF programming accessible without writing raw BPF bytecode. Instead of crafting C programs and manually loading them with `bpf()` syscalls, BCC lets me write kernel-level tracing tools using Python with embedded C for the BPF programs. I built a simple filesystem latency tracer and a syscall counter, and the experience was eye-opening — the Python wrapper handles compilation, map management, and data retrieval, while the C code inside string literals runs in the kernel.

## The Core Concept

BCC solves a fundamental tension in eBPF development: the kernel requires BPF programs to be written in a restricted C (or compiled from LLVM IR), but we want to interact with them from a high-level language. BCC's approach is elegant — you embed C code as a string in Python, BCC compiles it with LLVM, loads it into the kernel, and exposes the resulting maps and perf events as Python objects.

Why this matters: raw eBPF development requires managing bytecode loading, map creation, and event polling manually. BCC abstracts this into a clean Python API while keeping the kernel-side code in C for performance. The Python layer handles the "plumbing" — attaching probes to tracepoints/kprobes, reading perf buffers, and printing formatted output — so you focus on the tracing logic.

The key insight is that BCC is not a "Python eBPF runtime." The actual BPF programs still run in kernel context, with all the usual restrictions (no loops, bounded stack, verifier checks). Python only manages the user-space side: loading, data collection, and presentation.

## Key Commands / Configuration / Code

Here's a complete BCC program that counts syscalls per process. This is the "hello world" of BCC tracing:

```python
#!/usr/bin/env python3
from bcc import BPF
import ctypes as ct

# BPF program written in C, embedded as a string
bpf_text = """
#include <uapi/linux/ptrace.h>

// Hash map: key = pid, value = count
BPF_HASH(syscall_count, u32, u64);

int trace_sys_enter(struct pt_regs *ctx) {
    u32 pid = bpf_get_current_pid_tgid() >> 32;
    u64 *count, zero = 0;
    
    // Lookup or initialize counter for this pid
    count = syscall_count.lookup(&pid);
    if (count) {
        *count += 1;
    } else {
        syscall_count.update(&pid, &zero);
    }
    return 0;
}
"""

# Load and compile BPF program
b = BPF(text=bpf_text)

# Attach to raw syscall tracepoint (most efficient)
b.attach_raw_tracepoint(tp="sys_enter", fn_name="trace_sys_enter")

print("Tracing syscalls... Hit Ctrl-C to stop.")

# Poll loop: read and print map every second
try:
    while True:
        b.perf_buffer_poll(timeout=1000)  # 1 second timeout
        print("\n=== Syscall counts (top 10) ===")
        # Iterate over map entries
        for pid, count in sorted(
            b["syscall_count"].items(),
            key=lambda kv: kv[1].value,
            reverse=True
        )[:10]:
            try:
                comm = b.get_comm(pid.value).decode('utf-8', 'replace')
            except:
                comm = "?"
            print(f"PID {pid.value:>6} ({comm:<16}): {count.value}")
except KeyboardInterrupt:
    print("\nDetaching...")
```

Key points about this code:
- `BPF_HASH` creates a kernel-side hash map accessible from both kernel and user space
- `attach_raw_tracepoint` is the most efficient way to trace syscalls (avoids kprobe overhead)
- `b["syscall_count"]` returns a Python dict-like object backed by the kernel map
- `b.perf_buffer_poll()` is needed to trigger the tracepoint handler (even though we don't use perf events here)

For a more practical example, here's a filesystem latency tracer using kprobes:

```python
#!/usr/bin/env python3
from bcc import BPF
import time

bpf_text = """
#include <linux/fs.h>

// Store timestamp per inode
BPF_HASH(start, u64, u64);

int trace_vfs_read_entry(struct pt_regs *ctx, struct file *file) {
    u64 inode = file->f_inode->i_ino;
    u64 ts = bpf_ktime_get_ns();
    start.update(&inode, &ts);
    return 0;
}

int trace_vfs_read_return(struct pt_regs *ctx) {
    u64 inode = file->f_inode->i_ino;  // Need to get file from return context
    u64 *tsp = start.lookup(&inode);
    if (tsp) {
        u64 delta = bpf_ktime_get_ns() - *tsp;
        // Output via perf buffer
        bpf_trace_printk("inode %llu latency %llu ns\\n", inode, delta);
        start.delete(&inode);
    }
    return 0;
}
"""

b = BPF(text=bpf_text)
b.attach_kprobe(event="vfs_read", fn_name="trace_vfs_read_entry")
b.attach_kretprobe(event="vfs_read", fn_name="trace_vfs_read_return")

print("Tracing VFS read latency... Ctrl-C to exit.")
b.trace_print()  # Simple output for demo
```

## Common Pitfalls & Gotchas

1. **BPF program size limits**: The verifier enforces a 4096-byte instruction limit (1M instructions on newer kernels). Complex C code in your BPF program can hit this quickly. Always check `dmesg` for verifier errors like "BPF program too large." Solution: keep kernel-side logic minimal, move aggregation to user space.

2. **Map key/value types must match exactly**: If you declare `BPF_HASH(my_map, u32, u64)` but try to update with a Python `int` (which is 64-bit), you'll get silent corruption. Always use `ctypes.c_uint32()` for keys and `ctypes.c_uint64()` for values when interacting from Python. The example above works because we iterate with `.items()` which handles typing, but manual updates need care.

3. **`bpf_trace_printk()` is for debugging only**: It writes to `/sys/kernel/debug/tracing/trace_pipe` and has a 3-argument limit. For production tracing, use perf buffers or ring buffers. The `b.trace_print()` method is convenient but slow — it polls the trace pipe every 100ms.

## Try It Yourself

1. **Extend the syscall counter**: Modify the example to group by syscall number instead of PID. Use `ctx->orig_ax` (x86) or `PT_REGS_PARM1(ctx)` to get the syscall number. Print the top 5 syscalls globally.

2. **Build a TCP connection monitor**: Write a BCC program that attaches to `tcp_connect` kprobe and prints source/destination IPs. Use `BPF_PERF_OUTPUT` to send structured events to user space instead of `bpf_trace_printk`. Hint: include `net/inet_sock.h` and use `struct sock *sk`.

3. **Add histogram output**: Modify the filesystem latency tracer to output a log2 histogram using `BPF_HISTOGRAM`. Print percentiles (p50, p95, p99) every 5 seconds. BCC's `print_log2_hist()` helper does this automatically.

## Next Up

Tomorrow, I'm tackling **bpftrace: One-Liners for Kernel Tracing** — the awk-like language that lets you write powerful eBPF programs in a single line. No Python, no C compilation, just instant kernel tracing for debugging and performance analysis.
