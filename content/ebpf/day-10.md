---
title: "Day 10: eBPF Architecture: BPF VM, Maps & Helper Functions"
date: 2026-06-22
tags: ["til", "ebpf", "ebpf", "bpf-vm", "maps"]
---

## What I Explored Today

After nine days of practical tracing and debugging, I finally stepped back to understand the engine under the hood. Today I dissected the eBPF architecture: the BPF virtual machine that executes our programs, the maps that persist state between kernel and userspace, and the helper functions that give eBPF programs safe access to kernel internals. This is the foundation that makes everything else—kprobes, tracepoints, XDP—actually work.

## The Core Concept

eBPF isn't just a fancy way to run code in the kernel. It's a carefully designed execution environment that prioritizes safety and performance. The BPF VM is a register-based virtual machine with 11 64-bit registers (r0–r10), a 512-byte stack, and a strict verifier that ensures every program terminates and never corrupts kernel memory.

Why does this matter? Because without the VM, we'd be writing kernel modules—with all the crash risk that entails. The VM gives us a sandbox where the verifier can statically analyze every instruction path before execution. If your program has loops without bounds, accesses memory out of range, or calls a forbidden function, the verifier rejects it at load time. No kernel panic. No reboot.

Maps are the bridge between the kernel and userspace. They're key-value stores (hash maps, arrays, per-CPU variants) that eBPF programs can read and write, and that userspace can access via `bpf()` syscalls. This is how you collect metrics in the kernel and read them from a Python script.

Helper functions are the API that eBPF programs use to interact with the kernel. You can't just call any kernel function—the verifier enforces a whitelist. Helpers like `bpf_get_current_pid_tgid()`, `bpf_trace_printk()`, and `bpf_map_update_elem()` are the only way to do I/O, read process info, or manipulate maps.

## Key Commands / Configuration / Code

Let's look at a minimal eBPF program that uses maps and helpers. This counts the number of times each syscall is called:

```c
// syscall_count_kern.c
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

// Define a hash map: key = syscall ID (int), value = count (long)
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, int);
    __type(value, long);
} syscall_count SEC(".maps");

SEC("tracepoint/raw_syscalls/sys_enter")
int count_syscall(struct trace_event_raw_sys_enter *ctx)
{
    int syscall_id = ctx->id;
    long *count, zero = 0;

    // bpf_map_lookup_elem: get current count (helper function)
    count = bpf_map_lookup_elem(&syscall_count, &syscall_id);
    if (!count) {
        // First time seeing this syscall: insert zero
        bpf_map_update_elem(&syscall_count, &syscall_id, &zero, BPF_ANY);
        count = bpf_map_lookup_elem(&syscall_count, &syscall_id);
        if (!count)
            return 0;
    }
    // Atomically increment (__sync_fetch_and_add is a built-in, not a helper)
    __sync_fetch_and_add(count, 1);
    return 0;
}

char _license[] SEC("license") = "GPL";
```

Compile with:
```bash
clang -O2 -target bpf -c syscall_count_kern.c -o syscall_count_kern.o
```

Load and read with bpftool:
```bash
# Load the program into a tracepoint
bpftool prog load syscall_count_kern.o /sys/fs/bpf/syscall_count

# Pin the map so userspace can read it
bpftool map pin id $(bpftool map list | grep syscall_count | awk '{print $1}') /sys/fs/bpf/syscall_count_map

# Dump the map contents
bpftool map dump pinned /sys/fs/bpf/syscall_count_map
```

The key insight: `bpf_map_lookup_elem` and `bpf_map_update_elem` are helper functions. The verifier checks that we pass a valid map pointer and that the key type matches. The `__sync_fetch_and_add` is a compiler built-in that generates atomic instructions—the verifier allows this because it doesn't call any kernel functions.

## Common Pitfalls & Gotchas

**1. Stack size limit (512 bytes)**
The BPF VM stack is only 512 bytes. If you declare large local arrays or deeply nested structs, the verifier will reject your program. Workaround: use per-CPU arrays in maps for larger data, or break your logic into smaller programs.

**2. Verifier complexity limits**
The verifier explores every possible execution path. If your program has many branches (e.g., a switch with 100 cases), the verifier may hit its complexity limit (default 1 million instructions explored). Keep control flow simple—linear or shallow branching.

**3. Map key/value size restrictions**
Maps have a maximum key size of 256 bytes and value size of 4KB (for most map types). For larger data, use `BPF_MAP_TYPE_PERCPU_ARRAY` or `BPF_MAP_TYPE_STACK_TRACE`. Always check `bpf_map_create()` return values in userspace—silent failures are common.

## Try It Yourself

1. **Modify the syscall counter** to track per-process syscall counts. Add `bpf_get_current_pid_tgid()` to get the PID, and use a nested map key (struct with PID and syscall ID).

2. **Write a map that stores the last 10 syscall entries per CPU.** Use `BPF_MAP_TYPE_PERCPU_ARRAY` with a fixed-size ring buffer. Read it from userspace with `bpftool map dump`.

3. **Experiment with the verifier.** Write a program with an unbounded loop (e.g., `while (1) { ... }`) and try to load it. Observe the verifier error message. Then fix it with a bounded loop (e.g., `#pragma unroll` or a fixed iteration count).

## Next Up

Tomorrow we'll leave raw C behind and dive into **BCC: Writing eBPF Programs in Python**. BCC provides Python bindings that handle compilation, loading, and map access—making eBPF accessible without writing kernel C by hand. We'll rewrite the syscall counter in a few lines of Python and add real-time output.
