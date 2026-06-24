---
title: "Day 12: bpftrace: One-Liners for Kernel Tracing"
date: 2026-06-24
tags: ["til", "ebpf", "bpftrace", "ebpf", "tracing"]
---

## What I Explored Today

Today I dove headfirst into bpftrace, the high-level tracing frontend for eBPF that turns kernel instrumentation into one-liners. After days of writing raw eBPF C programs and dealing with verifier complexity, bpftrace feels like cheating — and I mean that in the best way. I spent the morning converting common debugging scenarios into single-line commands that attach kprobes, tracepoints, and uprobes without writing a single line of kernel C.

## The Core Concept

bpftrace exists because raw eBPF development has a steep learning curve. You need to write C, compile with LLVM, load via libbpf, handle maps, and satisfy the verifier. For quick investigations — "why is my process blocking on I/O?" or "what syscalls is this container making?" — that overhead kills productivity.

bpftrace gives you an awk-like language that compiles to eBPF bytecode on the fly. The syntax mirrors awk's pattern-action structure: you specify an event (probe point) and an action (what to record or print). The key insight is that bpftrace handles all the boilerplate: map creation, perf event output, probe attachment, and cleanup. You focus on the signal, not the plumbing.

The real power comes from bpftrace's built-in variables and functions. `pid`, `comm`, `kstack`, `ustack`, `args`, `retval` — these are mapped directly to kernel data structures. When you write `@[pid] = count()`, bpftrace creates a hash map keyed by PID and increments it atomically. The `count()` function compiles to a BPF map update with `BPF_MAP_TYPE_PERCPU_HASH` for performance.

## Key Commands / Configuration / Code

Let's start with the most practical one-liners I use daily. All of these run without sudo if your user has `CAP_BPF` and `CAP_PERFMON`, but typically you'll run as root.

```bash
# Count syscalls per process (top offenders)
bpftrace -e 'tracepoint:raw_syscalls:sys_enter { @[comm] = count(); }'

# Blocking I/O: trace filesystem sync operations
bpftrace -e 'kprobe:vfs_write { @[pid, comm] = count(); }'

# New process execution tracing
bpftrace -e 'tracepoint:syscalls:sys_enter_execve { printf("%s called execve\n", comm); }'

# Kernel function latency distribution (nanoseconds)
bpftrace -e 'kprobe:do_nanosleep { @start[tid] = nsecs; } kretprobe:do_nanosleep /@start[tid]/ { @sleep_ns = hist(nsecs - @start[tid]); delete(@start[tid]); }'

# Track OOM killer activity
bpftrace -e 'tracepoint:oom:mark_victim { printf("OOM killed %s (pid %d)\n", comm, pid); }'
```

For more structured investigations, bpftrace supports multi-line scripts. Here's a script I keep in my toolkit for diagnosing high CPU in the kernel:

```bpftrace
#!/usr/bin/bpftrace
// profile.bt: Sample kernel stacks at 99Hz
BEGIN
{
    printf("Sampling kernel stacks at 99 Hz. Ctrl-C to stop.\n");
}

profile:hz:99
{
    @[kstack] = count();
}

END
{
    clear(@);
}
```

Run it with: `bpftrace profile.bt`

The `profile:hz:99` probe is special — it fires on a timer interrupt at 99 Hz, capturing the kernel stack at each sample. This is the eBPF equivalent of `perf top` but with full stack aggregation.

For filesystem debugging, this one-liner shows which files are being opened:

```bash
bpftrace -e 'tracepoint:syscalls:sys_enter_openat { printf("%s opened %s\n", comm, str(args->filename)); }'
```

The `str()` function is critical — it reads the user-space string pointer safely, respecting the kernel's copy_from_user semantics.

## Common Pitfalls & Gotchas

1. **Missing `str()` for string arguments**: This is the #1 mistake. Kernel tracepoint arguments like `filename` are `const char __user *` pointers. If you write `printf("%s\n", args->filename)`, you'll print a kernel address, not the string. Always wrap user-space pointers with `str()`. For kernel-space strings (like `comm`), bpftrace handles them automatically.

2. **Map key collisions with `tid` vs `pid`**: When using `@start[tid]` in kprobe/kretprobe pairs, always key by thread ID (`tid`), not process ID (`pid`). Multiple threads in the same process can call the same function concurrently. Using `pid` as the key will cause one thread's return to overwrite another's start timestamp, giving you negative latency values. I've debugged this exact issue for an hour before realizing my mistake.

3. **Overhead from high-frequency probes**: Attaching a kprobe to `do_syscall_64` (every syscall) on a busy system can add 5-10% CPU overhead. bpftrace is efficient, but every probe fires in kernel context. Use tracepoints instead of kprobes when possible (they're designed for tracing), and always use frequency-limited probes (`profile:hz:99`) instead of counting every event when you only need sampling.

## Try It Yourself

1. **Find your top syscall**: Run `bpftrace -e 'tracepoint:raw_syscalls:sys_enter { @[comm] = count(); }'` for 30 seconds on a busy system. Identify which process makes the most syscalls. Then narrow it down to the specific syscall number using `@[comm, args->id]`.

2. **Trace file writes by PID**: Write a one-liner that prints the PID, command name, and file descriptor number every time `vfs_write` is called. Bonus: add a filter to only show writes from your shell's PID.

3. **Measure mutex contention**: Use `tracepoint:lock:lock_contended` and `tracepoint:lock:lock_acquired` to measure how long processes wait for mutexes. Print a histogram of wait times per process. Hint: you'll need `@start[tid]` and `hist()`.

## Next Up

Tomorrow, we go deeper into the kernel with **eBPF kprobes & kretprobes: Dynamic Instrumentation**. We'll move beyond bpftrace's one-liners and write raw kprobe programs that can inspect function arguments, modify return values, and trace kernel internals that tracepoints can't reach. Bring your kernel source — we're going spelunking.
