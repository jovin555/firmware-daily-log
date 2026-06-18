---
title: "Day 06: Building the Linux Kernel for Embedded Targets"
date: 2026-06-18
tags: ["til", "embedded-linux", "kernel", "build"]
---

## What I Explored Today

Today I went through the full workflow of cross-compiling the Linux kernel for an ARM embedded target (BeagleBone Black as my reference board). I’ve built kernels for x86 before, but embedded targets add layers: cross-toolchains, custom device trees, and minimal configurations. I walked away with a repeatable build recipe and a much deeper appreciation for `Kconfig`, `make` targets, and the boot flow from `zImage` to `uImage` to `FIT`.

## The Core Concept

Building a kernel for embedded Linux isn’t just about running `make` on a different architecture. The core challenge is that your build host (x86_64) and your target (ARM, RISC-V, AArch64) are different instruction sets. You need a cross-compiler that produces binaries for the target, and you must configure the kernel to match your exact hardware — not a generic distro kernel.

Why not just grab a prebuilt kernel? Because embedded systems have fixed, minimal resources. You don’t want a 50MB kernel with drivers for every SATA controller when your board has only SPI flash and a single Ethernet PHY. You also need to enable exactly the right drivers, built-in (not as modules) for rootfs-on-initramfs scenarios, and you need to embed or append the correct Device Tree Blob (DTB). The kernel build system is your tool for this precision.

The key insight: the kernel’s `Kconfig` system and `Makefile` targets are designed for this. You set `ARCH` and `CROSS_COMPILE`, run `make <board>_defconfig` to get a baseline, then fine-tune with `menuconfig`. The output is a `zImage` (compressed kernel) and a `.dtb` file. For U-Boot systems, you often wrap these into a `uImage` or a Flattened Image Tree (FIT) image.

## Key Commands / Configuration / Code

Below is the exact sequence I used today for a BeagleBone Black target. I’m using Linaro’s ARM cross-toolchain (gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf).

**1. Set up environment and cross-compiler path**

```bash
export CROSS_COMPILE=arm-none-linux-gnueabihf-
export ARCH=arm
export PATH=$PATH:/opt/gcc-arm-9.2-2019.12-x86_64-arm-none-linux-gnueabihf/bin
```

**2. Get kernel source and apply default config**

```bash
git clone --depth=1 --branch v5.10.168 \
    https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
cd linux
make bb.org_defconfig   # BeagleBone Black defconfig from TI/beagleboard
```

**3. Customize configuration interactively**

```bash
make menuconfig
# I enabled:
#   Device Drivers -> SPI support -> SPI_OMAP24XX (built-in)
#   Device Drivers -> GPIO support -> GPIO_SYSFS (still useful for debug)
#   Kernel Features -> Preemption Model -> Voluntary Kernel Preemption (Desktop)
# Disabled: CONFIG_SOUND (no audio needed), CONFIG_WIRELESS (no WiFi)
```

**4. Build kernel, modules, and device tree**

```bash
make -j$(nproc) zImage modules dtbs
# Outputs:
#   arch/arm/boot/zImage
#   arch/arm/boot/dts/am335x-boneblack.dtb
#   modules under /lib/modules/5.10.168/ in staging dir
```

**5. Install modules to a staging directory (for rootfs)**

```bash
make modules_install INSTALL_MOD_PATH=/home/me/rootfs_staging
```

**6. Create a U-Boot uImage (optional, for older bootloaders)**

```bash
mkimage -A arm -O linux -T kernel -C none \
    -a 0x80008000 -e 0x80008000 \
    -n "Linux 5.10.168" -d arch/arm/boot/zImage uImage
```

**7. Verify the DTB is correct**

```bash
dtc -I dtb -O dts arch/arm/boot/dts/am335x-boneblack.dtb | head -50
# Check that model = "TI AM335x BeagleBone Black" and compatible strings match
```

## Common Pitfalls & Gotchas

**1. Forgetting `ARCH` and `CROSS_COMPILE`**
This is the #1 mistake. If you run `make` without these, the build system assumes x86_64 host and native compiler. You’ll get x86 binaries that won’t run on ARM. Always export them in your shell or pass them on every `make` invocation. I now have a `setenv.sh` script I source before any kernel work.

**2. Mismatched DTB and kernel config**
You can build a perfect `zImage` but if your DTB references a driver that’s built as a module and your rootfs doesn’t have it, the device won’t probe. For example, enabling `CONFIG_MMC_OMAP_HS` as a module but booting from eMMC — the kernel can’t load the module to read rootfs. Solution: build critical storage and clock drivers directly into the kernel (`=y`), not as modules (`=m`).

**3. Using the wrong defconfig**
`make defconfig` gives you a generic ARM multiplatform kernel with everything enabled. It will boot but be huge and slow. Always use a board-specific defconfig (e.g., `bb.org_defconfig`, `bcm2835_defconfig`, `sunxi_defconfig`). If your board isn’t in mainline, start from a similar SoC’s defconfig and trim.

**4. Not cleaning between config changes**
If you change `ARCH` or switch between defconfigs without `make distclean`, stale object files can cause subtle build failures or runtime crashes. Always `make distclean` when switching architectures or major configs.

## Try It Yourself

1. **Cross-compile a minimal kernel for QEMU’s virt machine.** Use `ARCH=arm64`, `CROSS_COMPILE=aarch64-linux-gnu-`, and `make defconfig`. Then boot it with `qemu-system-aarch64 -M virt -kernel arch/arm64/boot/Image -nographic`. This validates your toolchain and build flow without hardware.

2. **Add a custom driver as a built-in.** Take any existing driver (e.g., a GPIO LED driver) and change its `Kconfig` from `tristate` to `bool` in a local patch, then rebuild. Verify the driver is in `System.map` and not in the modules list.

3. **Extract and inspect a DTB from a running board.** On your target (or QEMU), run `dtc -I fs -O dts /proc/device-tree > board.dts`. Compare it to the source DTS you built. Look for nodes that were added by the bootloader (like `chosen` or `memory`).

## Next Up

Tomorrow we dive into **Device Tree: Syntax, Bindings & Overlays**. We’ll write a custom DTS from scratch, understand the `compatible` matching, and learn how to apply runtime overlays to reconfigure hardware without rebuilding the kernel.
