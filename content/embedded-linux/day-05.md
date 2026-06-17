---
title: "Day 05: Kernel Configuration: menuconfig, defconfig & Fragments"
date: 2026-06-17
tags: ["til", "embedded-linux", "kernel", "kconfig"]
---

## What I Explored Today

Today I dove into the Linux kernel's configuration system — the Kconfig infrastructure that determines exactly what gets compiled into your kernel. For embedded systems, this isn't just an academic exercise; a bloated kernel wastes precious flash space, increases boot time, and can introduce security vulnerabilities through unused drivers. I focused on three practical workflows: interactive configuration with `menuconfig`, managing baseline configurations with `defconfig`, and the increasingly essential technique of using configuration fragments to layer changes on top of reference configs without forking entire files.

## The Core Concept

The kernel's build system uses Kconfig to define a tree of configuration symbols — each with dependencies, selects, and visibility conditions. When you run `make menuconfig`, you're navigating this tree and writing decisions to `.config`. But in embedded development, you rarely configure from scratch. You start with a `defconfig` — a minimal, sane baseline for your architecture or board — then overlay your specific changes.

The critical insight is that `.config` is not a diff; it's a complete snapshot. Every symbol is either set to `y`, `m`, or left commented out (meaning `n`). This makes it fragile for version control — a single `make olddefconfig` can silently drop your custom settings if a symbol was renamed or its dependencies changed. Fragments solve this by storing only your intentional overrides as a minimal `.config` snippet, which you merge on top of a base defconfig. This separation of concerns is what makes kernel configuration maintainable across kernel version bumps and team workflows.

## Key Commands / Configuration / Code

### 1. Interactive Configuration with menuconfig

```bash
# Navigate to kernel source, load defaults for your architecture
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- defconfig

# Launch the ncurses-based menu
make ARCH=arm menuconfig
```

Inside `menuconfig`, use `/` to search for symbols by name or description. For example, searching for `CONFIG_CMA` reveals its dependencies and current value. Press `?` on any symbol to see its help text, dependencies, and what selects it — invaluable for debugging why a feature is hidden.

### 2. Working with defconfigs

```bash
# Generate a defconfig from your current .config (strips defaults)
make ARCH=arm savedefconfig
# Output: defconfig file (typically ~200 lines vs 6000+ in .config)

# View the diff between two defconfigs
diff -u arch/arm/configs/multi_v7_defconfig my_defconfig
```

The `savedefconfig` target is a lifesaver. It produces a minimal file containing only the symbols that differ from the architecture's default values. This is what you check into your BSP repository, not the full `.config`.

### 3. Configuration Fragments (merge_config.sh)

```bash
# Create a fragment file (e.g., my_features.cfg)
cat > my_features.cfg << 'EOF'
# Enable USB gadget support
CONFIG_USB_GADGET=y
CONFIG_USB_GADGETFS=y
# Enable debug filesystem
CONFIG_DEBUG_FS=y
# Set a custom kernel command line
CONFIG_CMDLINE="console=ttyAMA0,115200 root=/dev/mmcblk0p2 rootwait"
EOF

# Merge fragment onto a base defconfig
ARCH=arm scripts/kconfig/merge_config.sh \
    -m -O build_dir \
    arch/arm/configs/multi_v7_defconfig \
    my_features.cfg

# The -m flag means "don't warn about missing symbols"
# The -O flag specifies output directory for the merged .config
```

For complex projects, you can chain multiple fragments:

```bash
# Layer fragments: base -> board -> debug
scripts/kconfig/merge_config.sh \
    base_defconfig \
    board_overlays/beaglebone.cfg \
    debug_tools.cfg
```

### 4. Automating with a build script

```bash
#!/bin/bash
# kernel_config.sh - Idempotent kernel config for embedded target
set -euo pipefail

ARCH=arm
CROSS_COMPILE=arm-linux-gnueabihf-
BUILD_DIR=build
FRAGMENTS_DIR=fragments

# Start from clean baseline
make ARCH=${ARCH} distclean

# Apply base defconfig
make ARCH=${ARCH} multi_v7_defconfig O=${BUILD_DIR}

# Merge board-specific and feature fragments
for f in ${FRAGMENTS_DIR}/*.cfg; do
    ARCH=${ARCH} scripts/kconfig/merge_config.sh \
        -m -O ${BUILD_DIR} \
        ${BUILD_DIR}/.config "$f"
done

# Finalize (resolve any new symbols added by fragments)
make ARCH=${ARCH} olddefconfig O=${BUILD_DIR}
```

## Common Pitfalls & Gotchas

**1. Silent symbol removal during `olddefconfig`**  
When you update your kernel and run `make olddefconfig`, any symbol that was removed or renamed in the new source gets silently dropped from `.config`. Your custom setting vanishes without warning. Always use `scripts/diffconfig` after a version bump to compare old and new `.config` files:  
`scripts/diffconfig .config.old .config | grep "^<"` shows removed symbols.

**2. Dependency hell in fragments**  
A fragment might set `CONFIG_FOO=y`, but `FOO` depends on `CONFIG_BAR` which isn't enabled. The merge script will either silently disable `FOO` (with `-m` flag) or error out. Always run `make ARCH=arm menuconfig` after merging to verify your intended symbols are actually enabled. Use `make ARCH=arm nconfig` for a faster, searchable interface.

**3. Forgetting to set architecture-specific symbols**  
Many embedded boards require `CONFIG_ARCH_MULTI_V7` or similar top-level architecture symbols. If your fragment only sets driver options without the parent architecture symbol, nothing gets compiled. Check `arch/arm/Kconfig` for the correct `ARCH_*` symbol for your SoC family.

## Try It Yourself

1. **Extract and compare defconfigs**: Clone a stable kernel tree, run `make ARCH=arm multi_v7_defconfig`, then `make ARCH=arm savedefconfig`. Compare the output `defconfig` with `arch/arm/configs/multi_v7_defconfig` using `diff`. Notice how `savedefconfig` removes architecture-wide defaults.

2. **Create a debug fragment**: Write a fragment that enables `CONFIG_DEBUG_KERNEL`, `CONFIG_DYNAMIC_DEBUG`, and `CONFIG_FTRACE`. Merge it onto `multi_v7_defconfig`, then run `make ARCH=arm menuconfig` and verify the debug options are now visible and enabled.

3. **Simulate a kernel version bump**: Save your `.config` as `.config.old`, then run `make ARCH=arm olddefconfig`. Use `scripts/diffconfig .config.old .config` to see what changed. Repeat with a fragment-based workflow — note how fragments preserve your intent across the "bump."

## Next Up

Tomorrow, I'll tackle **Building the Linux Kernel for Embedded Targets** — from cross-compilation toolchain setup and `make` targets to producing bootable `zImage` and device tree blobs, with a focus on optimizing build time for iterative development cycles.
