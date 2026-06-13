---
title: "Day 01: Embedded Linux Architecture: Components & Boot Flow"
date: 2026-06-13
tags: ["til", "embedded-linux", "embedded-linux", "architecture"]
---

## What I Explored Today

Today I mapped the full boot chain of an embedded Linux system—from power-on reset to a running userspace. I traced through each component: the boot ROM, bootloader stages (SPL/TPL and U-Boot proper), the kernel, device tree, and root filesystem. The goal was to understand not just *what* runs, but *why* each piece exists and how they hand off control. I built a minimal boot flow on a BeagleBone Black emulator to verify each stage.

## The Core Concept

Embedded Linux is not a monolithic OS—it's a carefully staged sequence of increasingly capable programs. The boot flow exists because hardware constraints force it: the CPU's internal SRAM is tiny (often 4–64 KB), SDRAM requires initialization, and the kernel is too large to load directly from raw NAND or eMMC.

The boot chain solves three problems in order:
1. **Initialize minimal hardware** (clock, PLL, DRAM controller) from on-chip SRAM
2. **Load a larger program** (bootloader) into DRAM, which then loads the kernel
3. **Provide hardware description** (device tree) so the kernel doesn't need hardcoded board support

Each stage trusts the previous one. The boot ROM is mask-programmed by the SoC vendor and cannot be modified. The first-stage bootloader (SPL/TPL) is board-specific and lives in a fixed location. U-Boot proper is flexible—it can read from MMC, NAND, TFTP, or USB. The kernel receives a flattened device tree (FDT) that describes the exact hardware, then mounts a root filesystem to launch `init`.

## Key Commands / Configuration / Code

### 1. Inspecting the Boot ROM on a Real Board

On a running i.MX6 or AM335x system, you can see where the boot ROM placed the initial loader:

```bash
# Check the boot device from which the ROM loaded SPL
cat /sys/devices/platform/omap_hsmmc.*/mmc_host/mmc*/mmc*/boot_config
# For AM335x, the boot ROM stores the boot device info in a register
devmem2 0x44E10000 32   # Read CONTROL_STATUS register
```

### 2. Building a Minimal U-Boot with Verified Boot Flow

The following shows a typical U-Boot build configuration for a BeagleBone Black:

```bash
# Set cross-compiler (from Linaro toolchain)
export CROSS_COMPILE=arm-linux-gnueabihf-
export ARCH=arm

# Configure for BeagleBone Black (AM335x)
make am335x_evm_defconfig

# Enable verbose boot progress for debugging
make menuconfig  # Navigate to: Boot media -> Enable SPL verbose output

# Build SPL and U-Boot proper
make -j4
# Outputs: MLO (SPL), u-boot.img (U-Boot proper)
```

### 3. Device Tree Compilation and Inspection

The device tree is compiled from `.dts` source to `.dtb` binary. You can decompile it back to verify:

```bash
# Compile device tree
dtc -I dts -O dtb -o am335x-boneblack.dtb arch/arm/boot/dts/am335x-boneblack.dts

# Decompile to human-readable form (useful for debugging)
dtc -I dtb -O dts am335x-boneblack.dtb | head -80

# Check which device tree the kernel actually used
cat /proc/device-tree/model
cat /proc/device-tree/compatible
```

### 4. Minimal Boot Log Analysis

A healthy boot log shows the handoff chain. Key lines to grep for:

```bash
# On a running system, extract boot messages
dmesg | grep -E "Booting Linux|Machine model|Kernel command line|VFS: Mounted root"

# Example output (annotated):
# [    0.000000] Booting Linux on physical CPU 0x0
# [    0.000000] Machine model: TI AM335x BeagleBone Black
# [    0.000000] Kernel command line: console=ttyO0,115200 root=/dev/mmcblk0p2 rw
# [    2.345678] VFS: Mounted root (ext4 filesystem) on device 179:2.
```

## Common Pitfalls & Gotchas

### 1. **SPL Size Limit Exceeded**
The SPL must fit in the SoC's internal SRAM. For AM335x, that's 128 KB (including the 32 KB header). If you enable too many drivers (e.g., USB, Ethernet) in SPL, the build will silently succeed but the board won't boot. Always check the actual size:
```bash
size MLO
# If text+data+bss > 0x20000 (128 KB), you'll hang after ROM
```

### 2. **Device Tree Mismatch**
Using a device tree compiled for a different board revision (e.g., BeagleBone White vs. Black) will cause subtle failures—MMC might not probe, GPIOs won't map, or the Ethernet PHY won't initialize. Always verify:
```bash
# Compare the kernel's expected compatible string with the DTB
strings uImage | grep "compatible="
dtc -I dtb -O dts /boot/dtb/am335x-boneblack.dtb | grep compatible
```

### 3. **Root Filesystem Not Found**
The kernel command line must match the actual root device. A common mistake: using `root=/dev/mmcblk0p2` when the rootfs is on partition 1, or forgetting to enable the MMC driver in the kernel. Debug with:
```bash
# In U-Boot, verify the partition layout
mmc dev 0
mmc part
# Then check the kernel's console output for "VFS: Cannot open root device"
```

## Try It Yourself

1. **Trace your board's boot flow**: On a Raspberry Pi or BeagleBone, capture the full boot log using a serial console (115200 baud, 8N1). Identify where the boot ROM hands off to the bootloader, and where the bootloader loads the kernel. Note the time between each stage.

2. **Decompile and modify a device tree**: Extract the DTB from a running system (`cat /proc/device-tree > /tmp/full.dtb`), decompile it with `dtc`, change a single property (e.g., `clock-frequency` of a UART), recompile, and load it manually via U-Boot (`fatload mmc 0:1 0x88000000 my.dtb`).

3. **Build U-Boot from source**: Clone the official U-Boot repository, configure for your board, and build both SPL and U-Boot proper. Flash the SPL to the first sector of an SD card (`dd if=MLO of=/dev/sdX bs=512 seek=1`). Observe the boot output change when you enable `CONFIG_SPL_DEBUG`.

## Next Up

Tomorrow we dive into **Cross-Compilation Toolchain: crosstool-NG & Linaro**—building a custom GCC toolchain tailored for your target architecture, avoiding the pitfalls of prebuilt binaries, and understanding why `--sysroot` is your best friend.
