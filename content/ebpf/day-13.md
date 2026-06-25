---
title: "Day 13: eBPF kprobes & kretprobes: Dynamic Instrumentation"
date: 2026-06-25
tags: ["til", "ebpf", "kprobes", "ebpf"]
---

## What I Explored Today

Today I dug deep into kprobes and kretprobes — the dynamic instrumentation mechanisms that let eBPF attach to any kernel function without recompiling or rebooting. I traced `do_sys_openat2` to catch every file open call on a production node, measured latency of `tcp_v4_connect`, and debugged a subtle race condition in a network driver by inspecting function arguments and return values. The power is intoxicating: you can instrument any of the ~60,000 kernel functions with zero overhead when not attached.

## The Core Concept

Kprobes (kernel probes) are the foundation. When you attach a kprobe to a function, the kernel replaces the first instruction of that function with a breakpoint instruction (int3 on x86). When execution hits that breakpoint, it traps into the kernel's kprobe handler, which executes your eBPF program, then single-steps the original instruction and resumes. The overhead is microseconds per invocation — negligible for debugging, but you wouldn't want it in a hot path at 1M ops/sec.

Kretprobes work differently. They instrument the *return* of a function. The kernel hijacks the return address on the stack, replacing it with a trampoline. When the function returns, control goes to your kretprobe handler instead of the caller. This lets you capture return values and compute elapsed time. The critical insight: kretprobes use a "kretprobe_instance" per CPU to store state between entry and exit. You must manage this state carefully — the instance is preallocated and limited.

Why not just use tracepoints? Tracepoints are stable, documented hooks, but they're limited to ~2,000 locations. Kprobes give you *every* function. When you're debugging a kernel bug that only manifests in `__alloc_pages_nodemask` with a specific GFP flag, tracepoints won't help. Kprobes will.

## Key Commands / Configuration / Code

### Basic kprobe: Count `tcp_v4_connect` calls

```c
// tcp_connect_kprobe.bpf.c
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

SEC("kprobe/tcp_v4_connect")
int kprobe__tcp_v4_connect(struct pt_regs *ctx)
{
    // The first argument (rdi on x86) is struct sock *sk
    // We just increment a counter here
    bpf_printk("tcp_v4_connect called\n");
    return 0;
}

char _license[] SEC("license") = "GPL";
```

Compile and load:
```bash
clang -O2 -target bpf -c tcp_connect_kprobe.bpf.c -o tcp_connect_kprobe.o
bpftool prog load tcp_connect_kprobe.o /sys/fs/bpf/tcp_connect_kprobe
bpftool prog attach pinned /sys/fs/bpf/tcp_connect_kprobe kprobe tcp_v4_connect
```

### kretprobe: Measure function latency

```c
// tcp_connect_latency.bpf.c
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, u64);  // pid_tgid
    __type(value, u64); // timestamp
} start_map SEC(".maps");

SEC("kprobe/tcp_v4_connect")
int kprobe_entry(struct pt_regs *ctx)
{
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u64 ts = bpf_ktime_get_ns();
    bpf_map_update_elem(&start_map, &pid_tgid, &ts, BPF_ANY);
    return 0;
}

SEC("kretprobe/tcp_v4_connect")
int kretprobe_exit(struct pt_regs *ctx)
{
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u64 *start_ts = bpf_map_lookup_elem(&start_map, &pid_tgid);
    if (!start_ts)
        return 0;  // missed entry, skip

    u64 delta_us = (bpf_ktime_get_ns() - *start_ts) / 1000;
    bpf_printk("tcp_v4_connect took %llu us, ret=%d\n",
               delta_us, PT_REGS_RC(ctx));
    bpf_map_delete_elem(&start_map, &pid_tgid);
    return 0;
}
```

### Reading function arguments (x86-64 ABI)

```c
// First 6 args in: rdi, rsi, rdx, rcx, r8, r9
// Helper macros from bpf_tracing.h:
// PT_REGS_PARM1(ctx) through PT_REGS_PARM5(ctx)

SEC("kprobe/do_sys_openat2")
int trace_openat2(struct pt_regs *ctx)
{
    // arg1: int dfd, arg2: const char __user *filename
    int dfd = PT_REGS_PARM1(ctx);
    const char *filename = (const char *)PT_REGS_PARM2(ctx);
    
    // bpf_probe_read_user_str to read userspace string
    char comm[16];
    bpf_get_current_comm(comm, sizeof(comm));
    bpf_printk("PID %d (%s) opening file from fd %d\n",
               bpf_get_current_pid_tgid() >> 32, comm, dfd);
    return 0;
}
```

## Common Pitfalls & Gotchas

**1. kretprobe instance exhaustion.** Each kretprobe has a limited pool of instances (default: `maxactive=20` per CPU). If your function is recursive or called more times than instances before any return, you'll silently lose probes. Always check `cat /sys/kernel/debug/kprobes/list` for "missed" counts. For high-frequency functions, increase `maxactive` in your kprobe registration (up to 4096).

**2. Missing entry events in kretprobe.** If your kprobe entry fails (e.g., map update rejected due to memory pressure), the kretprobe will fire without a matching entry. Always check map lookups for NULL and handle gracefully. I've seen this cause NULL pointer dereferences in eBPF programs that assumed entry always precedes exit.

**3. Function inlining and optimization.** Modern kernels inline many functions. `kprobe/tcp_v4_connect` might not fire if the compiler inlined it. Check `/proc/kallsyms` first — if the symbol doesn't appear, it's inlined. Use `kprobe/tcp_v4_connect.isra.0` (the `.isra` variant) or attach to a parent function. Alternatively, disable inlining for debugging with `func=*tcp_v4_connect` on the kernel command line.

**4. Stack depth and recursion.** Kprobes can fire from any context, including interrupt handlers. If your eBPF program calls `bpf_printk` from a kprobe attached to a printk-related function, you'll create infinite recursion and panic the kernel. Always verify your probe target isn't in the call chain of your helper functions.

## Try It Yourself

1. **Trace all file opens on your system.** Write a kprobe for `do_sys_openat2` that logs the filename and PID. Run `cat /var/log/syslog` (or `bpftool prog tracelog`) to see the output. Filter out noise by checking `bpf_get_current_comm` equals "cat" or "bash".

2. **Measure `kmalloc` latency.** Attach a kretprobe to `__kmalloc` and compute the allocation time. Create a histogram map (BPF_MAP_TYPE_PERCPU_ARRAY with log2 buckets) to see the distribution. Run `stress-ng --malloc 4` to generate load.

3. **Debug a network connection timeout.** Attach kprobe/kretprobe to `tcp_connect` and log the destination IP (from `struct sock->sk_daddr`). Add a kprobe to `tcp_retransmit_skb` to count retransmissions. Trigger a connection to a slow server and correlate the logs.

## Next Up

Tomorrow: **eBPF uprobes: Tracing Userspace from Kernel**. We'll attach probes to `malloc`, `pthread_mutex_lock`, and even specific Python function calls — all from kernel context, with zero changes to userspace code. Get ready to instrument your applications without recompilation.
