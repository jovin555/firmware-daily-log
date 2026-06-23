---
title: "Day 11: Machine Configuration: MACHINE, TUNE & BSP Layers"
date: 2026-06-23
tags: ["til", "yocto", "machine", "bsp"]
---

## What I Explored Today

Today I dove into the machine configuration layer of Yocto — the mechanism that tells the build system exactly what hardware we're targeting. I've been treating `MACHINE` as a simple variable assignment, but behind it lies a sophisticated system of tune files, kernel recipes, and board support package (BSP) layers that together define everything from CPU instruction sets to device tree blobs. I walked through creating a custom machine configuration for an i.MX6ULL board, traced how tune files propagate compiler flags, and untangled the relationship between BSP layers and the core metadata.

## The Core Concept

Machine configuration is Yocto's answer to hardware abstraction. Every embedded board has a unique combination of CPU architecture, memory layout, peripheral interfaces, and boot process. Rather than hardcoding these details across hundreds of recipes, Yocto centralizes them in a single `.conf` file and a set of tune include files.

The `MACHINE` variable is the key that unlocks the right set of hardware-specific metadata. When you set `MACHINE = "my-imx6ull"`, the build system:
1. Loads `conf/machine/my-imx6ull.conf` from the active BSP layer
2. Inherits tune files that define the CPU architecture and ABI
3. Selects the appropriate kernel recipe, device tree, and bootloader
4. Configures package architectures (e.g., `armv7at2hf-neon`)

The tune system is particularly elegant. Instead of repeating `-march=armv7-a -mfloat-abi=hard -mfpu=neon` across dozens of recipes, a tune file like `tune-cortexa7.inc` defines `TUNE_FEATURES` and `TUNE_CCARGS` once. Recipes inherit these through `TUNE_PKGARCH` and `TARGET_CC_ARCH`, ensuring every compiled binary is optimized for the target CPU.

BSP layers (like `meta-freescale` or `meta-raspberrypi`) provide the machine configurations, kernel recipes, and firmware blobs. They sit on top of `meta` and `meta-yocto-bsp`, overriding generic settings with board-specific ones. The layer priority system ensures that BSP-specific recipes take precedence over generic ones.

## Key Commands / Configuration / Code

### 1. Minimal Machine Configuration
```bitbake
# conf/machine/my-imx6ull.conf
# Include tune file for Cortex-A7 with hardware floating point
require conf/machine/include/tune-cortexa7.inc

# Machine identification
MACHINEOVERRIDES = "my-imx6ull"
MACHINE_FEATURES = "apm usbgadget usbhost vfat alsa touchscreen"

# Kernel and bootloader
PREFERRED_PROVIDER_virtual/kernel = "linux-imx"
KERNEL_DEVICETREE = "imx6ull-14x14-evk.dtb"
PREFERRED_PROVIDER_u-boot = "u-boot-imx"

# Image configuration
IMAGE_FSTYPES += "tar.bz2 ext4 wic"
SERIAL_CONSOLES = "115200;ttymxc0"
MACHINE_ESSENTIAL_EXTRA_RRECOMMENDS += "kernel-modules"
```

### 2. Tune File Inheritance Chain
```bitbake
# meta/conf/machine/include/tune-cortexa7.inc
# This file is included by machine configs using Cortex-A7

DEFAULTTUNE ?= "cortexa7thf-neon"
require conf/machine/include/arm/arch-armv7ve.inc

# Available tunes for Cortex-A7
AVAILTUNES += "cortexa7thf-neon"
TUNE_FEATURES_tune-cortexa7thf-neon = "${TUNE_FEATURES_tune-armv7vethf-neon} cortexa7"
PACKAGE_EXTRA_ARCHS_tune-cortexa7thf-neon = "${PACKAGE_EXTRA_ARCHS_tune-armv7vethf-neon} cortexa7thf-neon"
```

### 3. Checking Active Tune Flags
```bash
# See what compiler flags your machine config produces
bitbake -e | grep ^TUNE_CCARGS
# Output example: TUNE_CCARGS="-march=armv7-a -mfloat-abi=hard -mfpu=neon -mtune=cortex-a7"

# Verify the package architecture
bitbake -e | grep ^TUNE_PKGARCH
# Output: TUNE_PKGARCH="cortexa7thf-neon"

# List all available machines from active layers
ls meta-*/conf/machine/*.conf
```

### 4. BSP Layer Structure
```
meta-myboard/
├── conf/
│   ├── layer.conf          # Layer priority and dependencies
│   └── machine/
│       └── myboard.conf    # Machine configuration
├── recipes-bsp/
│   ├── u-boot/
│   │   └── u-boot-myboard_2024.01.bb
│   └── device-tree/
│       └── myboard.dts
├── recipes-kernel/
│   └── linux/
│       └── linux-myboard_6.6.bb
└── recipes-core/
    └── images/
        └── myboard-image.bb
```

## Common Pitfalls & Gotchas

**1. Mismatched Tune and Kernel Architecture**
The most common failure I've seen: using a tune file for Cortex-A7 but a kernel configured for ARMv5. The kernel will compile but produce illegal instruction faults at runtime. Always verify `TUNE_CCARGS` matches your kernel's `ARCH` and `CROSS_COMPILE` settings. Use `bitbake -e virtual/kernel | grep '^TARGET_CC_ARCH'` to confirm alignment.

**2. Forgetting MACHINEOVERRIDES**
Without `MACHINEOVERRIDES`, your machine-specific overrides in recipes (like `do_configure:append:my-imx6ull()`) will never trigger. This variable must be set in the machine config, not in `local.conf`. I've debugged for hours only to find the override variable was missing.

**3. Layer Priority Conflicts**
When two BSP layers provide the same machine name, the higher-priority layer wins. This can silently override your custom kernel recipe. Always check `BBLAYERS` order in `bblayers.conf` and use `bitbake-layers show-recipes` to verify which recipe is selected. A common mistake is adding a BSP layer after `meta-yocto-bsp` but expecting it to take precedence.

**4. Device Tree Path Assumptions**
`KERNEL_DEVICETREE` expects paths relative to the kernel's `arch/arm/boot/dts/` directory. If your `.dts` file is in a recipe's `files/` directory, you need to use `SRC_URI` and a kernel bbappend to deploy it. I've seen many engineers set `KERNEL_DEVICETREE = "myboard.dtb"` without ensuring the kernel recipe actually builds that file.

## Try It Yourself

1. **Inspect Your Current Machine Config**: Run `bitbake -e | grep -E '^(MACHINE|TUNE_|PACKAGE_EXTRA_ARCHS)'` and map each variable back to its source file. Trace the include chain from your machine config through the tune files.

2. **Create a Custom Machine Override**: In your `local.conf`, add a machine-specific override for `IMAGE_INSTALL:append:your-machine = " strace"`. Then build and verify `strace` appears only for that machine.

3. **Add a New Device Tree**: Pick a supported machine, create a `.dts` file in a custom layer, and add it to `KERNEL_DEVICETREE`. Use `bitbake -c devshell virtual/kernel` to verify the device tree compiles correctly.

## Next Up

Tomorrow we'll explore distro configuration — how `DISTRO_FEATURES` controls which system-level features (systemd vs sysvinit, Wayland vs X11, pulseaudio vs alsa) get enabled, and how distro policies shape the final image. We'll build a minimal distro from scratch and see how policy decisions ripple through every recipe.
