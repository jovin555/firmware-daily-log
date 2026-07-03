---
title: "Day 21: PREEMPT_RT Patch: What It Changes & How to Apply It"
date: 2026-07-03
tags: ["til", "preempt-rt", "preempt-rt", "patch", "kernel"]
---

## What I Explored Today

Today I dove into the PREEMPT_RT patch set — what it actually changes under the hood and, more importantly, how to apply it correctly to a vanilla kernel tree. After weeks of discussing scheduling theory and latency measurement, it's time to get our hands dirty with the real patch that makes Linux a hard real-time OS.

## The Core Concept

The PREEMPT_RT patch set (mainlined incrementally since kernel 5.x, but still requiring the full patch for complete real-time behavior) fundamentally transforms Linux's kernel preemption model. Here's what it actually changes:

**1. Spinlock → Sleeping Mutex Conversion**  
The most critical change. In mainline Linux, spinlocks disable preemption on the current CPU. Under PREEMPT_RT, most spinlock_t instances become rt_mutex-backed sleeping locks. This means a high-priority task can preempt a lower-priority task even while it holds a lock — the lock holder simply gets scheduled out and the waiter blocks. This eliminates priority inversion at the lock level.

**2. Interrupt Handlers Become Kernel Threads**  
Hard IRQ handlers (request_irq) are converted to threaded interrupt handlers running at SCHED_FIFO priority 50 by default. This allows the scheduler to manage interrupt processing like any other task, preventing IRQs from starving user-space RT threads. The top-half (hardirq) still runs in interrupt context, but it's minimized to just acknowledging the hardware.

**3. Priority Inheritance for All Sleeping Locks**  
PREEMPT_RT implements priority inheritance for rt_mutex, which propagates through the entire lock chain. If a low-priority task holds a lock that a high-priority task needs, the low-priority task temporarily inherits the high priority, preventing unbounded priority inversion.

**4. High-Resolution Timers Everywhere**  
The patch enables hrtimers for all kernel timers, not just userspace POSIX timers. This gives you sub-microsecond timer resolution for things like `schedule_timeout()` and driver timeouts.

**5. RCU Preemption**  
Read-Copy-Update (RCU) read-side critical sections become preemptible, meaning a high-priority task can preempt an RCU reader without waiting for a quiescent state.

## Key Commands / Configuration / Code

### Applying the Patch

```bash
# Get the kernel source (use a longterm stable version)
wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.30.tar.xz
tar -xf linux-6.6.30.tar.xz
cd linux-6.6.30

# Get the matching PREEMPT_RT patch
# Check https://cdn.kernel.org/pub/linux/kernel/projects/rt/ for your version
wget https://cdn.kernel.org/pub/linux/kernel/projects/rt/6.6/patch-6.6.30-rt42.patch.xz
xz -d patch-6.6.30-rt42.patch.xz

# Apply the patch
patch -p1 < patch-6.6.30-rt42.patch
# Expected output: "patching file ..." with no rejects
```

### Kernel Configuration (Critical Options)

```bash
# Start from a known-good config
make defconfig

# Enable PREEMPT_RT (this replaces PREEMPT_DYNAMIC)
make menuconfig
# Navigate to:
#   General setup --->
#     Preemption Model (Fully Preemptible Kernel (Real-Time)) --->
#       (X) Fully Preemptible Kernel (Real-Time)

# Verify these are set (they should auto-select):
# CONFIG_PREEMPT_RT=y
# CONFIG_PREEMPT_RT_FULL=y
# CONFIG_HIGH_RES_TIMERS=y
# CONFIG_PREEMPT_COUNT=y

# Disable debugging (unless you want 10x slower boot)
# Kernel hacking --->
#   [ ] Debug preemptible kernel
#   [ ] Debug spinlocks
#   [ ] Debug sleeping locks

# Build
make -j$(nproc)
make modules_install
make install
```

### Verifying the Patch Applied

```bash
# After booting the new kernel
uname -r
# Should show: 6.6.30-rt42

# Check kernel config at runtime
zcat /proc/config.gz | grep PREEMPT_RT
# CONFIG_PREEMPT_RT=y
# CONFIG_PREEMPT_RT_FULL=y

# Check if interrupts are threaded
ps -eo pid,comm,policy,rtprio | grep irq
# Should show irq/* threads with RR or FIFO policy
```

## Common Pitfalls & Gotchas

**1. Patch Version Must Match Kernel Version Exactly**  
The PREEMPT_RT patch is generated against a specific kernel commit. Using `patch-6.6.30-rt42` on `linux-6.6.31` will fail with hunks rejected. Always match the exact kernel tarball version to the patch version. Check `https://cdn.kernel.org/pub/linux/kernel/projects/rt/` for the correct patch for your kernel.

**2. Out-of-Tree Drivers Will Break**  
Proprietary GPU drivers (NVIDIA), WiFi drivers, and many vendor BSP modules use spinlock APIs that become sleeping locks under PREEMPT_RT. If the driver calls `spin_lock_irqsave()` from a context where sleeping is illegal (like a raw spinlock section), you'll get "scheduling while atomic" warnings and kernel panics. Always test with `CONFIG_DEBUG_ATOMIC_SLEEP=y` first.

**3. Not All Hardware Works**  
Some DMA engines and hardware with strict interrupt latency requirements may malfunction when their IRQ handlers become threads. The `threadirqs` kernel parameter can force this, but some devices (like certain network controllers) need `irqaffinity` tuning or explicit `request_irq()` with `IRQF_NO_THREAD` flag. Check `dmesg | grep "Threaded"` for devices that refused threading.

## Try It Yourself

1. **Patch and Build a PREEMPT_RT Kernel**  
   Download `linux-6.6.30` and the matching `patch-6.6.30-rt42`. Apply the patch, configure with `Fully Preemptible Kernel (Real-Time)`, build, and boot. Verify with `uname -r` and `zcat /proc/config.gz | grep PREEMPT_RT`.

2. **Measure the Difference**  
   Write a simple cyclictest (from rt-tests package) that runs for 60 seconds on both a vanilla kernel and your PREEMPT_RT kernel. Compare max latency: `cyclictest -l 60000 -m -n -p 99 -i 1000`. Expect vanilla to show 100-500µs max, PREEMPT_RT under 30µs.

3. **Find a Broken Driver**  
   Boot with `threadirqs` on a vanilla kernel (simulates PREEMPT_RT's threaded IRQ behavior). Run `dmesg | grep -i "thread"` and identify any driver that complains. Research whether that driver has a PREEMPT_RT fix or needs `IRQF_NO_THREAD`.

## Next Up: Building a PREEMPT_RT Kernel for Your Target

Tomorrow, we'll move from the generic desktop build to cross-compiling a PREEMPT_RT kernel for an embedded ARM target (BeagleBone Black). We'll cover device tree configuration, rootfs integration, and the specific `defconfig` fragments needed for real-time embedded systems. Bring your cross-compiler — we're going embedded.
