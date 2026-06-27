---
title: "Day 15: Kernel Config Fragments & defconfig in Yocto"
date: 2026-06-27
tags: ["til", "yocto", "kernel-config", "cfg-fragment"]
---

## What I Explored Today

Today I dove into how Yocto manages kernel configuration beyond the traditional `menuconfig` workflow. The key insight is that Yocto treats kernel configuration as a layered, mergeable artifact—not a monolithic `.config` file. I worked with configuration fragments (`.cfg` files) and `defconfig` files, learning how to selectively enable, disable, or modify kernel options without touching the vendor kernel tree. This is essential for maintaining clean, board-specific kernel configs that survive kernel version bumps.

## The Core Concept

In a typical embedded Linux workflow, you run `make menuconfig`, save your `.config`, and call it done. In Yocto, that approach breaks down because:

1. **Kernel recipes are shared** across multiple machines and BSP layers.
2. **Patches and kernel version updates** can silently drop or change config options.
3. **You need to audit and reproduce** config changes across builds.

Yocto solves this with a **merge-based configuration system**. The kernel recipe starts with a base configuration (often a `defconfig` from the kernel source or a BSP layer). Then, configuration fragments—plain text files containing `CONFIG_*` lines—are merged on top. The merge happens in a deterministic order, and Yocto’s `merge_config.sh` script (from the kernel build system) handles conflicts.

The result: you can maintain a minimal `defconfig` for your SoC and layer on board-specific fragments for peripherals, filesystems, or debugging features. Each fragment is a single responsibility unit—e.g., `usb-gadget.cfg`, `debug-ftrace.cfg`, `enable-ipv6.cfg`.

## Key Commands / Configuration / Code

### 1. Adding a `defconfig` to a kernel recipe

Place your `defconfig` in the kernel recipe directory or a machine-specific override:

```
meta-custom/recipes-kernel/linux/linux-custom/
├── defconfig
├── enable-rtc.cfg
└── disable-bluetooth.cfg
```

In the recipe (`linux-custom.bb`), inherit the kernel class and point to your defconfig:

```bitbake
inherit kernel

# Use a custom defconfig from the recipe directory
SRC_URI += "file://defconfig"

# Optional: add configuration fragments
SRC_URI += "file://enable-rtc.cfg"
SRC_URI += "file://disable-bluetooth.cfg"
```

### 2. Writing a configuration fragment

A `.cfg` file is a plain text file with kernel config options. Example `enable-rtc.cfg`:

```kconfig
# Enable RTC class and a specific RTC driver
CONFIG_RTC_CLASS=y
CONFIG_RTC_DRV_DS1307=y
CONFIG_RTC_SYSTOHC=y
```

Example `disable-bluetooth.cfg`:

```kconfig
# Disable Bluetooth subsystem entirely
# CONFIG_BT is not set
CONFIG_BT_LE=n
```

**Important**: Use `# CONFIG_FOO is not set` to explicitly disable a config. Using `CONFIG_FOO=n` is not equivalent in all kernel versions.

### 3. Verifying the merged config

After building, inspect the final `.config` in the kernel build directory:

```bash
# Find the kernel build directory
bitbake -e linux-custom | grep ^B=
# Output: B="/path/to/build/tmp/work/<machine>/linux-custom/<version>/build"

# Check the merged config
grep CONFIG_RTC_CLASS /path/to/build/.config
# Should show: CONFIG_RTC_CLASS=y
```

### 4. Using `menuconfig` to generate fragments

You can interactively configure and then extract only the changes:

```bash
# Start menuconfig in the build directory
bitbake -c menuconfig linux-custom

# After saving, extract differences from the base defconfig
bitbake -c diffconfig linux-custom
```

This generates a file `fragment.cfg` in the build directory containing only the options you changed. Copy that to your recipe as a new fragment.

### 5. Fragment merge order and overrides

Yocto merges fragments in the order they appear in `SRC_URI`. Later fragments override earlier ones. For machine-specific overrides:

```bitbake
# In a machine.conf or bbappend
SRC_URI:append:my-machine = " file://my-machine-fix.cfg"
```

## Common Pitfalls & Gotchas

### 1. `defconfig` vs. `config` naming

Yocto expects the file to be named exactly `defconfig` (lowercase). If you name it `myboard_defconfig`, it won't be automatically applied. You can work around this by setting `KBUILD_DEFCONFIG` in the recipe, but sticking with `defconfig` is simpler.

### 2. Fragment syntax: `# CONFIG_FOO is not set` vs `CONFIG_FOO=n`

Always use the comment-style disable syntax. The kernel's `merge_config.sh` script treats `CONFIG_FOO=n` differently—it may leave the option as a module instead of fully disabling it. Use `# CONFIG_FOO is not set` for reliable disabling.

### 3. Silent failures from missing dependencies

If your fragment enables `CONFIG_RTC_DRV_DS1307=y` but `CONFIG_I2C` is not enabled, the option will be silently dropped. Always run `bitbake -c kernel_configcheck linux-custom` to see warnings about unsatisfied dependencies. This command checks that all options in your fragments are actually applied.

## Try It Yourself

1. **Create a debug fragment**: Write a `.cfg` file that enables `CONFIG_DEBUG_KERNEL`, `CONFIG_DYNAMIC_DEBUG`, and `CONFIG_FTRACE`. Add it to a kernel recipe and verify the options appear in the final `.config`.

2. **Extract a fragment from menuconfig**: Build any kernel recipe, run `bitbake -c menuconfig`, change one option (e.g., enable `CONFIG_NETFILTER`), save, then run `bitbake -c diffconfig`. Examine the generated `fragment.cfg`.

3. **Resolve a dependency conflict**: Intentionally create a fragment that enables a driver requiring a disabled subsystem (e.g., enable `CONFIG_DRM_I915` without `CONFIG_DRM`). Run `bitbake -c kernel_configcheck` and read the warnings. Then fix the fragment by adding the missing dependency.

## Next Up

Tomorrow: **Device Tree in Yocto: KERNEL_DEVICETREE** — how to manage device tree sources, overlays, and the `KERNEL_DEVICETREE` variable to keep your hardware description clean and board-specific.
