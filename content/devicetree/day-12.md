---
title: "Day 12: Applying Overlays at Boot: U-Boot & overlays.txt"
date: 2026-06-24
tags: ["til", "devicetree", "uboot", "overlay", "boot"]
---

## What I Explored Today

Today I dug into the boot-time overlay application pipeline, specifically how U-Boot applies Device Tree overlays before the kernel starts. While runtime overlay management is powerful, many production systems need overlays active from the very first instruction of kernel boot. I focused on the `overlays.txt` mechanism and the `fdt apply` command in U-Boot, which together form the most common approach for applying overlays on ARM and RISC-V embedded systems that use U-Boot as their bootloader.

## The Core Concept

The fundamental problem: Device Tree overlays are applied by the kernel at runtime using `configfs`, but what if your overlay configures a critical bus controller, a memory-mapped FPGA bridge, or a power management IC that must be initialized before the kernel's device model starts? You can't wait for user-space — you need the overlay applied during boot.

U-Boot solves this by loading the base DTB, then applying one or more `.dtbo` overlay blobs before passing the final tree to the kernel. This happens in the bootloader stage, meaning the kernel never sees the base tree — it only sees the merged result. The `overlays.txt` file is a simple text manifest that tells U-Boot which overlays to apply and in what order. This is particularly important because overlay application order matters: if two overlays modify the same node, the last one applied wins.

The `overlays.txt` approach is the de facto standard on Raspberry Pi and many NXP i.MX boards, but the underlying mechanism — `fdt apply` in U-Boot — is universal across any platform using U-Boot with Device Tree support.

## Key Commands / Configuration / Code

### The overlays.txt File

This file lives in the boot partition (usually FAT32 on the SD card or eMMC). Each line specifies an overlay filename relative to the overlay directory.

```
# overlays.txt - applied in order
# Enable SPI controller with custom chip select
spi0-cs1.dtbo
# Configure the GPIO expander on that SPI bus
gpio-expander-pcal6416a.dtbo
# Enable audio codec on I2C1
wm8960-audio.dtbo
```

### U-Boot Script Integration

Most BSPs use a `boot.scr` or `boot.cmd` script that reads `overlays.txt`. Here's a typical script fragment:

```bash
# boot.cmd - load base DTB, then apply overlays from overlays.txt
load mmc 0:1 ${fdt_addr_r} /${board_name}.dtb
fdt addr ${fdt_addr_r}

# Read overlays.txt line by line
if load mmc 0:1 ${loadaddr} /overlays.txt; then
    # Process each overlay filename
    while read line; do
        if test -n "$line"; then
            echo "Applying overlay: $line"
            load mmc 0:1 ${fdt_overlay_addr} /overlays/${line}
            fdt apply ${fdt_overlay_addr} || echo "FAILED: $line"
        fi
    done < ${loadaddr}
fi

# Boot with merged tree
booti ${kernel_addr_r} - ${fdt_addr_r}
```

### Manual U-Boot Commands (for debugging)

When you're at the U-Boot prompt troubleshooting, you can manually step through the process:

```
# Load base DTB
=> load mmc 0:1 ${fdt_addr_r} imx8mp-evk.dtb
# Set FDT address for operations
=> fdt addr ${fdt_addr_r}
# Load an overlay
=> load mmc 0:1 ${fdt_overlay_addr} overlays/spi0-cs1.dtbo
# Apply it
=> fdt apply ${fdt_overlay_addr}
# Verify the merge (look for the new node)
=> fdt list /soc/spi@30820000
# Load and apply another
=> load mmc 0:1 ${fdt_overlay_addr} overlays/gpio-expander.dtbo
=> fdt apply ${fdt_overlay_addr}
# Boot
=> booti ${kernel_addr_r} - ${fdt_addr_r}
```

### Kernel Config Requirements

Your kernel must be built with overlay support compiled in (not as a module, since it's needed before rootfs):

```
CONFIG_OF_OVERLAY=y
CONFIG_OF_CONFIGFS=y    # for runtime, but also needed for dtbo parsing
```

## Common Pitfalls & Gotchas

### 1. Overlay Application Order and Symbol Resolution

The most insidious bug: overlays that depend on symbols from other overlays must be applied in the correct order. If overlay A adds a label `&gpio_expander` and overlay B references it, B must come after A in `overlays.txt`. U-Boot doesn't do dependency resolution — it applies in file order. Always test with `fdt list` after each manual apply to verify symbols resolve.

### 2. DTB and Overlay Version Mismatch

Overlays are compiled against a specific base DTB version. If you update your kernel and DTB but forget to recompile your overlays, you'll get cryptic `fdt apply` failures like "FDT_ERR_BADMAGIC" or "FDT_ERR_NOTFOUND". Always rebuild overlays from source when the base DTB changes. The `dtc` compiler with `-@` flag is your friend here.

### 3. Memory Allocation for Overlay Storage

U-Boot uses a fixed memory region for the FDT work area. If you apply too many overlays or one very large overlay, you can overflow this buffer. Symptoms: `fdt apply` succeeds but the kernel crashes on boot with "FDT_ERR_TRUNCATED". Increase `fdt_high` or `fdt_overlay_addr` in your U-Boot config, or reduce overlay complexity. On constrained systems, I've seen this with as few as 3 overlays.

## Try It Yourself

1. **Manual overlay application at U-Boot prompt**: Boot your board to the U-Boot prompt. Load the base DTB, then manually load and apply a single overlay using `fdt apply`. Use `fdt list` to verify the new node exists before booting. This isolates overlay issues from boot script complexity.

2. **Create and test an overlays.txt file**: Write a simple `overlays.txt` with two overlays. Modify your `boot.cmd` to read and apply them. Intentionally reverse the order and observe what happens (or doesn't). This teaches you about dependency ordering.

3. **Debug a failed overlay application**: Take an overlay compiled for a different kernel version. Attempt to apply it via `fdt apply` at the U-Boot prompt. Capture the exact error message and use `dtc -I dtb -O dts` to compare the overlay's target node paths against the base DTB. Fix the path mismatch and recompile.

## Next Up

Tomorrow we move from boot-time to runtime: **Runtime Overlays: configfs & dtoverlay**. We'll explore how to apply and remove overlays on a live system without rebooting — the key technique for FPGA reconfiguration, hot-plug hardware, and dynamic peripheral management.
