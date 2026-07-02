---
title: "Day 20: Dynamic Tracing a Custom Kernel Module"
date: 2026-07-02
tags: ["til", "ebpf", "kernel-module", "tracing", "debug"]
---

## What I Explored Today

Today I dove into dynamic tracing of a custom kernel module using eBPF. While most eBPF tracing examples focus on built-in kernel functions, real-world systems often include proprietary or out-of-tree kernel modules. I built a minimal character driver, loaded it, and used bpftrace and BCC to trace its entry points, function arguments, and return values—without modifying the module source or recompiling the kernel. This is the difference between static instrumentation (adding tracepoints) and dynamic tracing (attaching to existing functions).

## The Core Concept

The key insight is that eBPF can attach kprobes and kretprobes to any non-inlined kernel function, including those exported by loadable modules. When a module is loaded, its symbols become visible in `/proc/kallsyms` (if `kptr_restrict` allows). eBPF programs use these addresses to attach probes. This means you can trace module functions even if the module was compiled without any tracing support—no `trace_printk`, no custom tracepoints, no recompilation.

The mechanism works because the kernel's ftrace infrastructure (which eBPF kprobes rely on) operates at the instruction level. When you attach a kprobe to `my_module_func`, the kernel patches the first byte(s) of that function with a breakpoint instruction. When the function executes, the breakpoint triggers, the kprobe handler runs your eBPF program, then single-steps the original instruction and resumes. This is entirely dynamic—the module doesn't need to know it's being traced.

## Key Commands / Configuration / Code

### 1. Build a Minimal Kernel Module for Tracing

```c
// traceme.c — A module with traceable functions
#include <linux/module.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/slab.h>

#define DEVICE_NAME "traceme"
#define CLASS_NAME  "traceme_class"

static int major;
static struct class *cls;

// Function we'll trace — takes a buffer and length
ssize_t traceme_write(struct file *filp, const char __user *buf,
                      size_t len, loff_t *off)
{
    char *kbuf;
    if (len > 1024)
        return -EINVAL;

    kbuf = kmalloc(len + 1, GFP_KERNEL);
    if (!kbuf)
        return -ENOMEM;

    if (copy_from_user(kbuf, buf, len)) {
        kfree(kbuf);
        return -EFAULT;
    }
    kbuf[len] = '\0';
    pr_info("traceme: received %zu bytes: %s\n", len, kbuf);
    kfree(kbuf);
    return len;
}

// Another function — returns a simple value
int traceme_get_status(void)
{
    return 42;  // Always 42 — easy to verify
}
EXPORT_SYMBOL(traceme_get_status);

static struct file_operations fops = {
    .owner = THIS_MODULE,
    .write = traceme_write,
};

static int __init init(void)
{
    major = register_chrdev(0, DEVICE_NAME, &fops);
    if (major < 0) return major;
    cls = class_create(THIS_MODULE, CLASS_NAME);
    device_create(cls, NULL, MKDEV(major, 0), NULL, DEVICE_NAME);
    pr_info("traceme loaded, major %d\n", major);
    return 0;
}

static void __exit cleanup(void)
{
    device_destroy(cls, MKDEV(major, 0));
    class_destroy(cls);
    unregister_chrdev(major, DEVICE_NAME);
}

module_init(init);
module_exit(cleanup);
MODULE_LICENSE("GPL");
```

Makefile:
```makefile
obj-m += traceme.o
KDIR := /lib/modules/$(shell uname -r)/build
all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules
clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
```

### 2. Load Module and Verify Symbols

```bash
# Build and load
make
sudo insmod traceme.ko

# Verify the module is loaded
lsmod | grep traceme

# Find our functions in kallsyms (need root)
sudo cat /proc/kallsyms | grep traceme
# Output example:
# ffffffffc0975000 t traceme_init     [traceme]
# ffffffffc0975040 t traceme_cleanup  [traceme]
# ffffffffc0975080 t traceme_write    [traceme]
# ffffffffc0975100 T traceme_get_status [traceme]
```

### 3. Trace with bpftrace (One-Liner)

```bash
# Trace entry and exit of traceme_write with arguments
sudo bpftrace -e '
kprobe:traceme_write {
    printf("write called: len=%d\n", arg2);
}
kretprobe:traceme_write {
    printf("write returned: %d\n", retval);
}
'
```

### 4. Trace with BCC (Python) — Capture Buffer Contents

```python
#!/usr/bin/env python3
# traceme_trace.py
from bcc import BPF

bpf_text = """
#include <linux/fs.h>
#include <linux/slab.h>

int kprobe__traceme_write(struct pt_regs *ctx, struct file *filp,
                          const char __user *buf, size_t len, loff_t *off)
{
    // Only trace writes > 0 bytes
    if (len == 0 || len > 256)
        return 0;

    char kbuf[256];
    bpf_probe_read_user(kbuf, len, buf);
    kbuf[len] = 0;

    bpf_trace_printk("write len=%d data=%s\\n", len, kbuf);
    return 0;
}
"""

b = BPF(text=bpf_text)
b.attach_kprobe(event="traceme_write", fn_name="kprobe__traceme_write")

print("Tracing traceme_write... Ctrl-C to exit")
b.trace_print()
```

Run it:
```bash
sudo python3 traceme_trace.py &
# In another terminal:
echo "hello eBPF" | sudo tee /dev/traceme
# Output: write len=11 data=hello eBPF
```

## Common Pitfalls & Gotchas

1. **Symbol visibility**: If `kernel.kptr_restrict` is set to 2, non-root users can't see module symbols. Even as root, some distributions hide symbols by default. Check with `cat /proc/sys/kernel/kptr_restrict`. Set to 1 temporarily if needed (`echo 1 | sudo tee /proc/sys/kernel/kptr_restrict`). For production, use `bpftrace -l 'kprobe:traceme_*'` to verify probes exist before attaching.

2. **Inlined functions**: If the module was compiled with optimizations, small functions may be inlined and won't have their own kallsyms entries. The compiler may also rename functions (e.g., `traceme_write` becomes `.isra.0`). Check the actual symbol name in `/proc/kallsyms`. Compile the module with `-fno-inline` for development tracing.

3. **Module unloading**: If the module is unloaded while a kprobe is attached, the kernel will panic (use-after-free). Always detach probes before `rmmod`. BCC and bpftrace clean up on exit, but if you crash the tracing tool, the probe may persist. Use `sudo bpftrace -e 'kprobe:traceme_write { }'` with a no-op body to test attachment, then detach with Ctrl-C. Verify with `cat /sys/kernel/debug/kprobes/list`.

## Try It Yourself

1. **Trace argument values**: Extend the bpftrace one-liner to print the first 16 bytes of the buffer passed to `traceme_write`. Use `str(arg0)` for the buffer pointer (arg0 is the first argument after `struct pt_regs *ctx`).

2. **Count function calls**: Write a BCC program that uses a BPF hash map to count how many times `traceme_write` is called with different `len` values. Print the histogram on Ctrl-C.

3. **Trace return values with filters**: Attach a kretprobe to `traceme_get_status` and print a message only when the return value is not 42. This simulates debugging unexpected module behavior.

## Next Up

Tomorrow is Day 21: **Full Review & Project: Kernel Latency Monitor**. We'll combine everything from the past 20 days into a single practical tool—a kernel latency monitor that traces syscalls, IRQ handlers, and custom module functions, aggregates latencies in eBPF maps, and exports them via a perf ring buffer. This will be the capstone project that ties tracing, maps, and user-space communication together.
