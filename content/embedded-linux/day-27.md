---
title: "Day 27: Embedded Linux Architecture: Components & Boot Flow"
date: 2026-07-09
tags: ["til", "embedded-linux", "embedded-linux", "architecture"]
---

## What I Explored Today

Today I mapped out the full boot flow of an embedded Linux system from power-on to userspace, and dissected the four critical software components that make it happen: boot ROM, bootloader, kernel, and root filesystem. I traced through the boot sequence on a BeagleBone Black (AM335x) and an i.MX6UL reference board, verifying each stage with hardware debuggers and serial console logs. The goal was to understand not just *what* runs, but *why* each component exists and how they hand off control.

## The Core Concept

Embedded Linux isn't a monolithic OS — it's a carefully orchestrated relay race. The boot flow exists because no single piece of software can do everything: the CPU needs hardware initialization before DRAM works, the kernel needs a filesystem to mount root, and the filesystem needs the kernel's drivers to access storage. Each stage is progressively more abstract and feature-rich.

The four components are:

1. **Boot ROM** — Hardwired in silicon, runs the moment the CPU powers on. It's tiny (4–32 KB) and board-specific. Its only job: initialize minimal hardware (usually just the boot media interface) and load the next stage. You can't modify it without a new chip revision.

2. **Bootloader** — Usually U-Boot or Barebox. Initializes DRAM, clocks, pinmux, and storage controllers. Loads the kernel and device tree from flash, network, or SD card. Provides a recovery shell. This is the first place you have real control.

3. **Kernel** — The Linux kernel proper. Decompresses itself, mounts a temporary rootfs (initramfs) if needed, probes drivers against the device tree, then mounts the real root filesystem and executes `/sbin/init`.

4. **Root Filesystem** — Contains init system (systemd/BusyBox), libraries, applications, and configuration. Can be read-only (squashfs) or writable (ext4/UBIFS). The kernel hands off to PID 1 here.

The handoff chain is: `Boot ROM → Bootloader (SPL → U-Boot) → Kernel → init (PID 1)`. Each stage validates and loads the next, with increasing complexity.

## Key Commands / Configuration / Code

### 1. Inspecting the Boot ROM (AM335x)

On the BeagleBone Black, the ROM reads the SYSBOOT pins to decide boot order. You can't change the ROM, but you can see what it does via the debug UART:

```bash
# Connect serial console at 115200 baud
screen /dev/ttyUSB0 115200

# Power cycle — ROM prints nothing, but you'll see SPL output immediately
# To verify ROM is running, measure the time from power-on to first UART byte
# ~200ms on AM335x at 1GHz
```

### 2. U-Boot SPL (Secondary Program Loader)

SPL is the first-stage bootloader, limited to SRAM size (~64KB on AM335x). It initializes DRAM and loads the full U-Boot:

```bash
# Build SPL for BeagleBone Black
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- am335x_evm_defconfig
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- SPL

# Check SPL size — must fit in SRAM
ls -lh spl/u-boot-spl.bin
# Should be < 64KB
```

### 3. Full U-Boot Environment

Once DRAM is up, U-Boot loads the kernel and device tree:

```bash
# From U-Boot shell on target
# Load kernel from MMC
mmc dev 0
fatload mmc 0:1 0x82000000 zImage
fatload mmc 0:1 0x88000000 am335x-boneblack.dtb

# Boot with console on ttyO0
setenv bootargs console=ttyO0,115200 root=/dev/mmcblk0p2 rw
bootz 0x82000000 - 0x88000000
```

### 4. Kernel Boot Parameters

The kernel command line is critical. Here's a typical embedded setup:

```bash
# Minimal bootargs for NAND flash root
console=ttyS0,115200 root=/dev/mtdblock3 rootfstype=jffs2 rw

# With initramfs (no separate rootfs)
console=ttyS0,115200 root=/dev/ram0 initrd=0x88000000,8M

# Debugging early boot
earlyprintk debug ignore_loglevel loglevel=8
```

### 5. Device Tree Handoff

The bootloader passes the device tree blob (DTB) address to the kernel in register r2 (ARM). Verify it's correct:

```bash
# In U-Boot, check the DTB is valid
fdt addr 0x88000000
fdt list /soc   # Should show SoC nodes
```

## Common Pitfalls & Gotchas

**1. Boot ROM expects specific image headers.** The AM335x ROM requires a "GP header" (4 bytes of size + load address) before the SPL binary. Forgetting this causes silent boot failure — the ROM loads garbage and hangs. Use `mkimage` to prepend the header: `mkimage -A arm -O u-boot -T standalone -C none -a 0x402F0400 -e 0x402F0400 -d u-boot-spl.bin MLO`.

**2. Kernel panic: VFS: Unable to mount root fs.** This is the #1 boot failure. The kernel can't find the root filesystem because: wrong `root=` parameter, missing driver for the storage controller, or the rootfs is on a partition the kernel doesn't recognize. Always verify with `root=/dev/ram0` and an initramfs first to isolate the issue.

**3. Device tree mismatch.** Using a DTB built for a different board revision (e.g., BeagleBone Black DTB on a BeagleBone Green) causes random driver probe failures. The kernel will boot but peripherals (MMC, Ethernet, GPIO) won't work. Always dump the board's DTB from a known-good system: `dtc -I dtb -O dts /sys/firmware/devicetree/base > board.dts`.

## Try It Yourself

1. **Trace the boot flow on your board.** Connect a serial console and capture the entire boot log from power-on to login prompt. Identify each stage: ROM (no output), SPL (first text), U-Boot (version string), kernel (booting Linux...), init (starting services). Time each phase with a stopwatch.

2. **Break the boot chain intentionally.** Corrupt the kernel image on the SD card (overwrite the first 1KB with zeros) and observe the bootloader error. Then corrupt the device tree blob. Note the different failure modes — U-Boot will report "bad magic number" for the kernel, but may hang silently for a bad DTB.

3. **Build a minimal initramfs.** Create a rootfs with just BusyBox and a static `init` binary. Boot with `root=/dev/ram0` and verify you get a shell. Then switch to a real rootfs on MMC or NAND and fix any mount errors.

## Next Up

Tomorrow we build a cross-compilation toolchain from scratch using crosstool-NG and explore the Linaro GCC releases. You'll learn why `gcc` on your x86 laptop can't compile for ARM, and how to create a toolchain that produces binaries for any embedded target.
