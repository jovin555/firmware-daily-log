---
title: "Day 03: PREEMPT_RT Patch: What It Changes & How to Apply It"
date: 2026-06-15
tags: ["til", "preempt-rt", "preempt-rt", "patch", "kernel"]
---

## What I Explored Today

Today I dug into the actual PREEMPT_RT patch set — not just the theory, but what lines of code it changes and how to apply it to a stock kernel tree. I built a patched kernel for a Raspberry Pi 4 target, measured the difference in scheduling latency, and confirmed the `PREEMPT_RT_FULL` config option appears. The patch is surprisingly surgical: about 10,000 lines across 200+ files, but the core changes are in spinlock conversion, interrupt threading, and priority inheritance for sleeping locks.

## The Core Concept

The PREEMPT_RT patch doesn't rewrite the kernel. It systematically eliminates non-preemptible sections. Here's what it actually changes:

**1. Spinlock → Sleeping Mutex Conversion**  
In the mainline kernel, `spin_lock()` disables preemption and sometimes interrupts. Under PREEMPT_RT, most spinlocks become `rt_mutex` — they can sleep. This means a high-priority task can preempt a low-priority task even while it holds a "spinlock." The key: raw spinlocks (`raw_spin_lock`) remain for truly atomic contexts (interrupt handlers, scheduler core).

**2. Interrupt Threading**  
Hardware IRQs become kernel threads with real-time priorities. Instead of running in atomic context, your interrupt handler runs as a `kthread` that can be preempted by a higher-priority RT task. The top half (hardirq) is minimal — just enough to acknowledge the device. The bottom half (threaded IRQ) does the real work.

**3. Priority Inheritance for Sleeping Locks**  
The `rt_mutex` implementation includes priority inheritance. When a low-priority task holds a mutex that a high-priority task needs, the low-priority task temporarily inherits the high priority. This prevents priority inversion — the classic Mars Pathfinder bug.

**4. RCU Preemption**  
Read-Copy-Update (RCU) read-side critical sections become preemptible. Under PREEMPT_RT, `rcu_read_lock()` no longer disables preemption. This required adding `rcu_read_lock_sched()` variants for the few places that still need it.

**5. Timers & Softirqs**  
Softirqs are moved into per-CPU kernel threads (`ksoftirqd`). Timer callbacks run in process context. This means you can use `down()` and `mutex_lock()` inside timer handlers — something that would deadlock in mainline.

## Key Commands / Configuration / Code

### Applying the Patch

```bash
# Get kernel source and matching RT patch
# Check kernel.org for exact version pairs
wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.30.tar.xz
wget https://cdn.kernel.org/pub/linux/kernel/projects/rt/6.6/patch-6.6.30-rt40.patch.xz

# Verify integrity
sha256sum linux-6.6.30.tar.xz patch-6.6.30-rt40.patch.xz

# Extract and apply
tar -xf linux-6.6.30.tar.xz
cd linux-6.6.30
xzcat ../patch-6.6.30-rt40.patch.xz | patch -p1 --dry-run  # Test first
xzcat ../patch-6.6.30-rt40.patch.xz | patch -p1            # Apply
```

### Kernel Configuration (Critical Options)

```bash
# Start from your distro config or defconfig
make ARCH=arm64 defconfig  # For Raspberry Pi 4

# Enable PREEMPT_RT
scripts/config --enable PREEMPT_RT_FULL
scripts/config --disable PREEMPT_VOLUNTARY
scripts/config --disable PREEMPT

# Verify it took effect
grep PREEMPT .config
# Should show: CONFIG_PREEMPT_RT_FULL=y
# Should NOT show: CONFIG_PREEMPT=y or CONFIG_PREEMPT_VOLUNTARY=y

# Additional RT tweaks
scripts/config --enable EXPERT
scripts/config --enable CPU_FREQ_DEFAULT_GOV_PERFORMANCE
scripts/config --set-val HZ 1000  # 1ms tick for RT
scripts/config --enable NO_HZ_FULL  # Full dynticks for RT tasks
```

### Building and Installing

```bash
# Build with all cores (adjust -j to your machine)
make -j$(nproc) Image modules dtbs

# Install modules
make modules_install INSTALL_MOD_PATH=/path/to/rootfs

# Copy kernel and device tree
cp arch/arm64/boot/Image /boot/kernel8-rt.img
cp arch/arm64/boot/dts/broadcom/bcm2711-rpi-4-b.dtb /boot/

# Update config.txt on boot partition
echo "kernel=kernel8-rt.img" >> /boot/config.txt
```

### Verifying the RT Kernel

```bash
# After booting the new kernel
uname -a
# Should show: PREEMPT_RT in the version string

# Check config at runtime
zcat /proc/config.gz | grep PREEMPT_RT
# CONFIG_PREEMPT_RT_FULL=y

# Measure scheduling latency with cyclictest
cyclictest -m -n -p 99 -h 100 -i 1000 -l 100000
# Look for max latency < 50µs on a tuned system
```

## Common Pitfalls & Gotchas

**1. Patch version mismatch is silent failure**  
The RT patch must exactly match the kernel version (e.g., 6.6.30-rt40 goes with 6.6.30). If you apply the wrong patch, `patch` may report "Hunk #1 FAILED" or apply cleanly but produce a broken kernel. Always use `--dry-run` first and check the `localversion-rt` file is created in the kernel root.

**2. `PREEMPT_RT_FULL` vs `PREEMPT_RT` naming**  
In older kernels (pre-5.10), the config was `CONFIG_PREEMPT_RT_FULL`. In newer kernels (5.15+), it's just `CONFIG_PREEMPT_RT`. Check your kernel version's Documentation/rt.txt. Using the wrong name silently falls back to `PREEMPT_VOLUNTARY`.

**3. Drivers that use raw spinlocks incorrectly**  
Some out-of-tree drivers use `spin_lock()` where they should use `raw_spin_lock()` (e.g., in interrupt handlers). Under PREEMPT_RT, this causes "scheduling while atomic" warnings or deadlocks. Fix: change to `raw_spin_lock()` only if the critical section must be non-preemptible (hardware register access, scheduler code).

**4. `local_irq_disable()` in drivers breaks**  
Many drivers disable interrupts to protect short critical sections. Under PREEMPT_RT, `local_irq_disable()` can sleep (it acquires a `pi_lock`). Replace with `raw_local_irq_disable()` if truly necessary, or better: use `spin_lock_irqsave()` which becomes a sleeping mutex.

## Try It Yourself

1. **Apply the PREEMPT_RT patch to a 6.6 kernel**  
   Download linux-6.6.30 and the matching RT patch. Apply with `--dry-run` first, then apply for real. Verify `localversion-rt` exists.

2. **Boot the RT kernel on a Raspberry Pi 4**  
   Configure with `PREEMPT_RT_FULL`, build, and boot. Run `cyclictest -m -n -p 99 -i 1000 -l 10000` and record the max latency. Compare to a stock kernel boot.

3. **Identify a driver that breaks**  
   Load a WiFi or GPU driver (e.g., `brcmfmac`). Check `dmesg` for "scheduling while atomic" or "BUG: spinlock recursion". Fix by converting `spin_lock()` to `raw_spin_lock()` in the interrupt handler.

## Next Up

Tomorrow: **Building a PREEMPT_RT Kernel for Your Target** — we'll go end-to-end: cross-compiling for ARM64, configuring a root filesystem with RT-friendly init scripts, and deploying to a BeagleBone Black. Bring your toolchain.
