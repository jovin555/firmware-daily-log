---
title: "Day 22: Building a PREEMPT_RT Kernel for Your Target"
date: 2026-07-04
tags: ["til", "preempt-rt", "preempt-rt", "build", "kernel"]
---

## What I Explored Today

Today I walked through the complete process of building a PREEMPT_RT kernel from source for a real target board—a BeagleBone Black running a 5.10.y LTS kernel. While many developers rely on prebuilt images or vendor BSPs, understanding the manual build flow is essential when you need to tune configuration, apply custom patches, or support a non-mainline platform. I covered everything from applying the RT patch set to configuring the kernel, cross-compiling, and deploying to the target.

## The Core Concept

A PREEMPT_RT kernel isn't a separate kernel tree—it's a set of patches applied on top of a specific Linux kernel version, typically an LTS release. The patches convert most kernel spinlocks into preemptible mutexes, add priority inheritance for most kernel synchronization primitives, and enable threaded interrupt handlers by default. The result is a kernel where almost any execution context can be preempted by a higher-priority real-time task, reducing worst-case latency to tens of microseconds on commodity hardware.

The build process mirrors a standard kernel build but with critical differences: you must select the correct patch version matching your kernel base, enable `CONFIG_PREEMPT_RT` (not just `CONFIG_PREEMPT`), and carefully manage kernel configuration to avoid features that introduce unbounded latencies (e.g., power management idle states, certain CPU frequency governors). The target's bootloader, device tree, and root filesystem must also be prepared to use the new kernel image.

## Key Commands / Configuration / Code

### 1. Obtaining the Sources

```bash
# Choose an LTS kernel version that has a matching RT patch
# As of 2026, 5.10.y is a stable LTS with mature RT support
KERNEL_VERSION=5.10.220
RT_PATCH_VERSION=5.10.220-rt111

# Download kernel source
wget https://cdn.kernel.org/pub/linux/kernel/v5.x/linux-${KERNEL_VERSION}.tar.xz
tar -xf linux-${KERNEL_VERSION}.tar.xz
cd linux-${KERNEL_VERSION}

# Download and apply the RT patch
wget https://cdn.kernel.org/pub/linux/kernel/projects/rt/5.10/patch-${RT_PATCH_VERSION}.patch.xz
xzcat patch-${RT_PATCH_VERSION}.patch.xz | patch -p1 --dry-run  # verify first
xzcat patch-${RT_PATCH_VERSION}.patch.xz | patch -p1
```

### 2. Kernel Configuration

```bash
# For cross-compilation to ARM (BeagleBone Black)
export ARCH=arm
export CROSS_COMPILE=arm-linux-gnueabihf-

# Start from the vendor defconfig (omap2plus_defconfig for TI AM335x)
make omap2plus_defconfig

# Enable PREEMPT_RT — this is the critical step
# Use menuconfig or directly set:
make menuconfig
# Navigate to: General setup -> Preemption Model
# Select: "Fully Preemptible Kernel (Real-Time)"

# Alternatively, set it directly in .config
sed -i 's/CONFIG_PREEMPT=y/CONFIG_PREEMPT_RT=y/' .config
# Remove any conflicting preemption settings
sed -i '/CONFIG_PREEMPT_VOLUNTARY/d' .config
sed -i '/CONFIG_PREEMPT_NONE/d' .config

# Disable known latency offenders
# Power management deep idle states
scripts/config --disable CPU_IDLE_GOV_TEO
scripts/config --disable CPU_FREQ_GOV_ONDEMAND
scripts/config --disable CPU_FREQ_GOV_CONSERVATIVE
# Use performance governor for deterministic behavior
scripts/config --enable CPU_FREQ_GOV_PERFORMANCE
scripts/config --set-val CPU_FREQ_DEFAULT_GOV_PERFORMANCE y

# Ensure threaded IRQs are default
scripts/config --enable PREEMPT_RT_FULL  # legacy alias, still works
```

### 3. Building and Deploying

```bash
# Build the kernel, modules, and device tree blobs
make -j$(nproc) zImage modules dtbs

# Install modules to a staging directory (for rootfs)
make modules_install INSTALL_MOD_PATH=/path/to/rootfs

# Copy kernel image and DTB to boot partition
cp arch/arm/boot/zImage /media/boot/
cp arch/arm/boot/dts/am335x-boneblack.dtb /media/boot/

# For u-boot: create a uImage if needed
mkimage -A arm -O linux -T kernel -C none -a 0x80008000 -e 0x80008000 \
        -n "PREEMPT_RT Kernel" -d arch/arm/boot/zImage /media/boot/uImage
```

### 4. Verifying the Build

```bash
# On the target, check kernel version and preemption model
uname -a
# Should show: ... PREEMPT_RT ...

# Check that RT features are active
cat /sys/kernel/realtime
# Should print: 1

# Verify threaded IRQs
cat /proc/interrupts | head -5
# All interrupts should show a handler thread (e.g., [irq/xx-xxx])
```

## Common Pitfalls & Gotchas

1. **Patch version mismatch**: The RT patch must exactly match the kernel base version. Applying `patch-5.10.220-rt111.patch` to `linux-5.10.219` will fail with fuzz or rejections. Always verify with `--dry-run` first. Use `git am` if you need to track patch conflicts.

2. **Missing `CONFIG_PREEMPT_RT` in defconfig**: Many vendor defconfigs enable `CONFIG_PREEMPT` (standard preempt) but not `CONFIG_PREEMPT_RT`. You must explicitly select "Fully Preemptible Kernel (Real-Time)" in the preemption model menu. If you see `CONFIG_PREEMPT=y` in your `.config` after enabling RT, you have a conflict—run `make olddefconfig` to resolve.

3. **Boot hangs with no console output**: This is often caused by the RT patch changing how early printk or serial drivers initialize. Common fixes: ensure `CONFIG_SERIAL_8250_CONSOLE` is enabled, add `console=ttyO0,115200n8` to kernel cmdline, and disable `CONFIG_DEBUG_RODATA` if you see page table issues on older ARM platforms.

## Try It Yourself

1. **Cross-compile a PREEMPT_RT kernel for your target board** using the exact steps above. Use `qemu-system-arm` with a `vexpress-a9` machine if you don't have physical hardware—the process is identical.

2. **Compare boot-time latency** between a stock kernel and your RT kernel by measuring `dmesg` timestamps for critical drivers. Use `grep -E "^\[.*\]" /var/log/kern.log` to spot differences in interrupt registration order.

3. **Enable `CONFIG_SCHED_DEBUG` and inspect RT throttling**: After boot, check `/proc/sys/kernel/sched_rt_runtime_us` and `/proc/sys/kernel/sched_rt_period_us`. Try setting `sched_rt_runtime_us=-1` to disable throttling and observe the effect on a CPU-bound RT task.

## Next Up

Tomorrow we'll put this kernel to the test with **cyclictest: Measuring Worst-Case Latency**. We'll run the standard real-time benchmarking tool, interpret its output, and learn how to identify latency sources from the histogram data.
