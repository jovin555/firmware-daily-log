---
title: "Day 04: Building a PREEMPT_RT Kernel for Your Target"
date: 2026-06-16
tags: ["til", "preempt-rt", "preempt-rt", "build", "kernel"]
---

## What I Explored Today

Yesterday we dissected the PREEMPT_RT patchset. Today I got my hands dirty building a real-time kernel from source. I walked through the full workflow: fetching the correct kernel source, applying the RT patch, configuring for real-time, compiling for a target board (ARM64 in my case), and deploying. The goal was to produce a bootable kernel image with `PREEMPT_RT_FULL` enabled, then verify it's actually running in real-time mode. This is the step where theory meets practice—and where most engineers hit their first real snags.

## The Core Concept

Why build from source? Because PREEMPT_RT is not a kernel configuration option you can just toggle in your distro's default kernel. It requires a patchset that must be applied to a specific kernel version. The kernel.org RT tree (`linux-rt`) provides pre-patched trees, but for embedded targets you often need custom configurations, out-of-tree drivers, or board-specific Device Trees. Building from source gives you full control over what goes into the kernel—and lets you verify the RT features are actually compiled in.

The critical insight: **the kernel configuration is where real-time happens**. Enabling `CONFIG_PREEMPT_RT` is necessary, but it's not sufficient. You also need to disable or tune features that introduce unbounded latencies: kernel debugging options, heavy tracing, power management idle states, and certain CPU frequency governors. The build process is your chance to audit every option.

## Key Commands / Configuration / Code

### Step 1: Get the right source tree

I used the `linux-rt` tree from kernel.org, which has the RT patchset already applied:

```bash
# Clone the stable RT tree (v6.1.y-rt in this example)
git clone git://git.kernel.org/pub/scm/linux/kernel/git/rt/linux-rt-devel.git
cd linux-rt-devel
git checkout v6.1.46-rt14
```

Alternatively, if you're applying the patch manually:

```bash
wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.1.46.tar.xz
wget https://cdn.kernel.org/pub/linux/kernel/projects/rt/6.1/older/patch-6.1.46-rt14.patch.xz
tar xf linux-6.1.46.tar.xz
cd linux-6.1.46
xzcat ../patch-6.1.46-rt14.patch.xz | patch -p1
```

### Step 2: Configure for real-time

Start from your target's defconfig (or a known-good config), then enable RT:

```bash
# For a Raspberry Pi 4 (ARM64)
make ARCH=arm64 bcm2711_defconfig

# Now enter menuconfig to enable PREEMPT_RT
make ARCH=arm64 menuconfig
```

In menuconfig, navigate to:
```
General setup  --->
  Preemption Model (Fully Preemptible Kernel (Real-Time))  --->
    (X) Fully Preemptible Kernel (Real-Time)
```

This selects `CONFIG_PREEMPT_RT=y`. Verify these are also set (they should be auto-selected):

```bash
# Check critical RT configs
grep -E "CONFIG_PREEMPT_RT|CONFIG_HIGH_RES_TIMERS|CONFIG_NO_HZ_FULL" .config
```

Output should show:
```
CONFIG_PREEMPT_RT=y
CONFIG_HIGH_RES_TIMERS=y
CONFIG_NO_HZ_FULL=y
```

### Step 3: Disable latency-killing options

Add these to your `.config` or toggle them off in menuconfig:

```bash
# Disable kernel debugging (huge latency source)
# CONFIG_DEBUG_KERNEL is not set
# CONFIG_DEBUG_PREEMPT is not set
# CONFIG_LOCKDEP is not set

# Disable dynamic tick for full NO_HZ
CONFIG_NO_HZ_FULL_ALL=y

# Set timer frequency to 1000 Hz (RT standard)
CONFIG_HZ_1000=y
```

### Step 4: Build for your target

For an ARM64 target (e.g., Raspberry Pi 4):

```bash
# Set cross-compiler (adjust for your toolchain)
export CROSS_COMPILE=aarch64-linux-gnu-
export ARCH=arm64

# Build kernel and Device Tree
make -j$(nproc) Image.gz
make -j$(nproc) dtbs

# Build modules (if needed)
make -j$(nproc) modules
make INSTALL_MOD_PATH=/path/to/rootfs modules_install
```

For x86_64 (testing on a VM):

```bash
make -j$(nproc) bzImage
make -j$(nproc) modules
```

### Step 5: Verify the build

After booting the new kernel, check it's running RT:

```bash
# Should print "PREEMPT_RT" (not "PREEMPT" or "PREEMPT_DYNAMIC")
uname -a

# Check kernel config at runtime
zcat /proc/config.gz | grep PREEMPT_RT
# Or if config is not compressed:
cat /boot/config-$(uname -r) | grep PREEMPT_RT
```

Expected output:
```
CONFIG_PREEMPT_RT=y
```

## Common Pitfalls & Gotchas

1. **Wrong kernel version for the patch**: The RT patchset is tied to a specific kernel release (e.g., `6.1.46-rt14` applies only to `6.1.46`). Applying it to `6.1.47` will fail with fuzz. Always verify the patch matches your kernel tarball exactly. Use `git describe` on the RT tree to confirm.

2. **Missing `CONFIG_PREEMPT_RT` in menuconfig**: If you don't see "Fully Preemptible Kernel (Real-Time)" as an option, your kernel source doesn't have the RT patch applied. The vanilla kernel only offers `PREEMPT`, `PREEMPT_VOLUNTARY`, and `PREEMPT_DYNAMIC`. The RT option only appears after patching.

3. **Debug options left enabled**: `CONFIG_DEBUG_PREEMPT`, `CONFIG_LOCKDEP`, and `CONFIG_DEBUG_ATOMIC_SLEEP` are often enabled by default in development configs. They add significant overhead and can cause false-positive splats under RT. Always run `make savedefconfig` after your changes and review the diff.

4. **Boot hangs on real hardware**: If your target hangs at boot after enabling RT, it's often due to a driver that doesn't support threaded interrupts or raw spinlocks. Check `dmesg` for "BUG: scheduling while atomic" messages. You may need to blacklist certain drivers or add `threadirqs` to the kernel command line.

## Try It Yourself

1. **Build an RT kernel for a QEMU ARM64 VM**: Use `defconfig`, enable `CONFIG_PREEMPT_RT`, build, and boot with QEMU. Verify `uname -a` shows `PREEMPT_RT`. This is the fastest way to validate your toolchain and build process.

2. **Compare boot-time latency with and without RT**: Boot your target with a vanilla kernel (same version, no RT patch) and measure `dmesg` timestamps. Then boot the RT kernel. Note the difference in total boot time—RT kernels are slightly slower due to additional preemption checks.

3. **Audit your `.config` for latency sources**: Run `grep -E "DEBUG|TRACE|LOCKDEP|PROVE_LOCKING" .config` and disable any that are enabled. Rebuild and boot. Use `cyclictest` (we'll cover this tomorrow) to measure the improvement.

## Next Up: cyclictest — Measuring Worst-Case Latency

We've built the RT kernel. Now how do we know it's actually working? Tomorrow I'll dive into `cyclictest`, the standard tool for measuring scheduling latency. We'll run it on our freshly built kernel, interpret the output, and understand what "worst-case latency" really means for your real-time application.
