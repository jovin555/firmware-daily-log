---
title: "Day 18: eBPF Security: LSM Hooks & Seccomp Filters"
date: 2026-06-30
tags: ["til", "ebpf", "lsm", "seccomp", "security"]
---

## What I Explored Today

Today I dove into the intersection of eBPF and Linux security primitives—specifically how eBPF programs can attach to Linux Security Module (LSM) hooks and integrate with seccomp filters. While seccomp has been the go-to for syscall-level sandboxing, LSM hooks give eBPF the ability to enforce policy at a much finer granularity: on individual kernel objects like inodes, files, and sockets. I spent the day writing a BPF program that intercepts `file_open` via an LSM hook and cross-references it with a seccomp filter to block dangerous combinations—like opening `/etc/shadow` with `O_RDONLY` from a non-root process that also called `connect()`.

## The Core Concept

The traditional seccomp-bpf filter operates at the syscall boundary. It sees `openat(AT_FDCWD, "/etc/shadow", O_RDONLY)` but has no visibility into the actual file path—only the syscall number and arguments. You can block `openat` entirely, but you can't selectively allow it for `/etc/passwd` while denying `/etc/shadow`. That's where LSM hooks come in.

LSM hooks are placed deep in the kernel's access control logic, right before a privileged operation is performed. The `security_file_open` hook, for example, fires after the path is resolved but before the file is opened. An eBPF program attached to this hook receives a `struct file *` and can inspect the full path via `d_path()`. This gives us path-aware security decisions that seccomp alone cannot achieve.

The real power comes from combining both: use seccomp to reduce the attack surface at the syscall level (e.g., block `execve`, `ptrace`, `mount`), then use LSM hooks for fine-grained object-level policy. This is exactly how projects like Tetragon and Falco implement their security monitoring—they attach eBPF to LSM hooks and correlate events across the kernel.

## Key Commands / Configuration / Code

Here's a practical example: an eBPF program that blocks opening `/etc/shadow` for reading, using the LSM `file_open` hook.

```c
// lsm_shadow_blocker.bpf.c
#include <linux/bpf.h>
#include <linux/fs.h>
#include <linux/dcache.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>

char LICENSE[] SEC("license") = "GPL";

SEC("lsm/file_open")
int BPF_PROG(block_shadow_open, struct file *file)
{
    // We need to extract the path from the file struct
    // d_path() is available in LSM context since kernel 5.7
    char path[256];
    int ret = bpf_d_path(&file->f_path, path, sizeof(path));
    if (ret < 0)
        return 0; // allow if we can't read path

    // Compare with our target
    // Note: bpf_strncmp is a helper available in newer kernels
    // For older kernels, use bpf_probe_read_str and manual compare
    if (bpf_strncmp(path, sizeof(path), "/etc/shadow") == 0) {
        // Block the open with -EPERM
        return -1;
    }

    return 0; // allow everything else
}
```

Compile and load:
```bash
# Compile with clang targeting BPF
clang -O2 -target bpf -c lsm_shadow_blocker.bpf.c -o lsm_shadow_blocker.o

# Load the program (requires kernel 5.7+ with CONFIG_BPF_LSM=y)
# First, check if LSM BPF is enabled
cat /sys/kernel/security/lsm | grep bpf

# Load via bpftool
bpftool prog load lsm_shadow_blocker.o /sys/fs/bpf/lsm_shadow_blocker
bpftool prog attach pinned /sys/fs/bpf/lsm_shadow_blocker lsm file_open
```

Now, combine with a seccomp filter that blocks `connect()` for extra safety:
```python
# seccomp_restrict_connect.py
import ctypes
import os

# seccomp syscall numbers
PR_SET_SECCOMP = 22
SECCOMP_SET_MODE_FILTER = 1

# BPF instruction structure
class sock_fprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort),
                ("filter", ctypes.POINTER(ctypes.c_uint64))]

# Simple filter: allow everything except connect (syscall 42 on x86_64)
# This is a minimal example; real filters should use libseccomp
filter_code = [
    0x20, 0x00, 0x00, 0x00000004,  # ld [4]          ; load arch
    0x15, 0x00, 0x03, 0xc000003e,  # jeq AUDIT_ARCH_X86_64, next
    0x06, 0x00, 0x00, 0x00000000,  # ret KILL         ; wrong arch
    0x20, 0x00, 0x00, 0x00000000,  # ld [0]          ; load syscall number
    0x15, 0x01, 0x00, 0x0000002a,  # jeq 42, allow   ; connect() allowed
    0x06, 0x00, 0x00, 0x7fff0000,  # ret ALLOW
    0x06, 0x00, 0x00, 0x00000000,  # ret KILL
]

prog = sock_fprog(len(filter_code), (ctypes.c_uint64 * len(filter_code))(*filter_code))
libc = ctypes.CDLL("libc.so.6")
ret = libc.prctl(PR_SET_SECCOMP, SECCOMP_SET_MODE_FILTER, ctypes.byref(prog))
if ret != 0:
    raise OSError("seccomp filter failed")
```

## Common Pitfalls & Gotchas

1. **LSM hook availability depends on kernel config**: The `CONFIG_BPF_LSM` option must be enabled, and the `bpf` LSM must be in the `CONFIG_LSM` order list. Many distros (especially older Ubuntu LTS) ship without it. Always check `/sys/kernel/security/lsm` first. If `bpf` isn't listed, you'll get `ENOENT` when attaching.

2. **Path resolution in LSM hooks is tricky**: The `bpf_d_path()` helper works only in sleepable LSM programs (those marked `SEC("lsm.s/file_open")`). Non-sleepable LSM programs cannot call `d_path()` and must use `bpf_probe_read_str` on the `dentry` directly, which is fragile across kernel versions. Always test on your target kernel.

3. **Seccomp + LSM ordering matters**: Seccomp filters run before LSM hooks. If seccomp kills the process on `openat`, the LSM hook never fires. This is actually desirable—seccomp provides the first line of defense. But if you're debugging, remember that seccomp failures will mask LSM events. Use `bpftool prog tracelog` to see LSM hook invocations, but check seccomp audit logs (`ausearch --start today -m SECCOMP`) separately.

## Try It Yourself

1. **Write a path-aware LSM blocker**: Modify the example above to block writes to `/etc/passwd` but allow reads. Use the `file->f_mode` field to check for `FMODE_WRITE`. Attach to the `file_open` LSM hook and test with `echo "test" >> /etc/passwd` as non-root.

2. **Combine seccomp and LSM for a sandbox**: Create a seccomp filter that allows only `read`, `write`, `openat`, and `exit_group`. Then attach an LSM program that only allows opening files under `/tmp/`. Run a shell under this sandbox and try to read `/etc/shadow`—it should be blocked by the LSM hook, not seccomp.

3. **Monitor LSM hook invocations with bpftool**: Instead of blocking, write an LSM program that logs every `file_open` event to the trace pipe using `bpf_printk()`. Attach it, then run `cat /var/log/syslog` and observe the trace output. This is how you build a file access monitor without modifying the kernel.

## Next Up

Tomorrow: **Debugging Driver Latency with eBPF: End-to-End** — we'll trace a block I/O request from the application through the VFS layer, into the device driver, and back, using kprobes and tracepoints to pinpoint where microseconds turn into milliseconds.
