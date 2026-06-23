---
title: "Day 11: Device Tree Overlays (DTBO): Syntax & Structure"
date: 2026-06-23
tags: ["til", "devicetree", "dtbo", "overlay", "syntax"]
---

## What I Explored Today

After days of working with static `.dts` files, today I dove into the overlay syntax that makes runtime hardware configuration possible. I compiled my first `.dtbo` from an overlay source (`.dtso`), examined the binary structure with `fdtdump`, and traced how the kernel applies fragments at load time. The key insight: overlays aren't just "extra nodes"—they're a structured patching mechanism with explicit target references and fragment encapsulation.

## The Core Concept

A Device Tree Overlay (DTBO) is a binary blob that modifies an existing base Device Tree (DTB) at runtime. Unlike a full `.dts` that describes an entire system, an overlay contains only *fragments*—self-contained patches that target specific nodes in the base tree. Each fragment carries a target (either a phandle or a path) and a delta (the nodes/properties to add, change, or remove).

The kernel's overlay mechanism works like a surgical patch: it reads each fragment, locates the target node in the live tree, and applies the delta using a merge algorithm. This is fundamentally different from compile-time inclusion (`#include`). Overlays can be loaded and unloaded dynamically, making them essential for FPGA reconfiguration, cape/hat support (BeagleBone, Raspberry Pi), and modular driver bringup.

The `.dtso` source format is nearly identical to `.dts`, but with two mandatory additions: the `/plugin/;` directive and explicit `target` properties in each fragment. Without `/plugin/;`, the compiler treats the file as a standalone tree and will complain about missing root nodes.

## Key Commands / Configuration / Code

### 1. Minimal Overlay Source (`my-overlay.dtso`)

```dts
// SPDX-License-Identifier: GPL-2.0-only OR MIT
/dts-v1/;
/plugin/;                          // REQUIRED: marks this as an overlay

/ {
    fragment@0 {                   // Fragment 0: add a new I2C device
        target = <&i2c1>;          // Target by phandle (must exist in base)
        __overlay__ {
            #address-cells = <1>;
            #size-cells = <0>;
            my-sensor@48 {
                compatible = "bosch,bme280";
                reg = <0x48>;
            };
        };
    };

    fragment@1 {                   // Fragment 1: modify an existing node
        target-path = "/soc/gpio@ff000000";  // Target by path string
        __overlay__ {
            gpio-line-names = "LED_RED", "LED_GREEN", "BTN_USER";
        };
    };
};
```

### 2. Compilation and Inspection

```bash
# Compile overlay source to .dtbo
dtc -@ -I dts -O dtb -o my-overlay.dtbo my-overlay.dtso
#   -@  : enable overlay support (generates __symbols__ node)
#   -I  : input format (dts)
#   -O  : output format (dtb, but .dtbo is conventional)

# Inspect the binary overlay
fdtdump my-overlay.dtbo

# Check for correct fragment structure
dtc -I dtb -O dts my-overlay.dtbo | head -30
# Should show /plugin/ and fragment@N nodes

# Verify symbols are present
fdtdump my-overlay.dtbo | grep -A2 '__symbols__'
```

### 3. Applying an Overlay at Runtime (sysfs)

```bash
# Check if configfs is mounted
mount | grep configfs

# Load overlay (requires kernel config CONFIG_OF_OVERLAY=y)
mkdir /configfs/device-tree/overlays/my-overlay
cat my-overlay.dtbo > /configfs/device-tree/overlays/my-overlay/dtbo

# Verify it applied
ls /configfs/device-tree/overlays/my-overlay/
cat /configfs/device-tree/overlays/my-overlay/status  # "applied"

# Remove overlay
rmdir /configfs/device-tree/overlays/my-overlay
```

### 4. Fragment Targeting: Phandle vs Path

```dts
// Method 1: phandle (preferred, compile-time checked)
fragment@0 {
    target = <&i2c1>;          // Resolved during dtc compilation
    __overlay__ { ... };
};

// Method 2: path string (runtime resolved, no compile-time check)
fragment@1 {
    target-path = "/soc/spi@ff010000";
    __overlay__ { ... };
};

// Method 3: explicit phandle (for complex cases)
fragment@2 {
    target = <0xdeadbeef>;     // Raw phandle value (rarely used)
    __overlay__ { ... };
};
```

## Common Pitfalls & Gotchas

### 1. Missing `/plugin/;` Causes Compilation Errors
Without `/plugin/;`, `dtc` expects a complete tree with a root node. You'll get errors like `FATAL ERROR: Syntax error parsing input tree` or warnings about missing `#address-cells`. Always start your `.dtso` with `/dts-v1/;` followed immediately by `/plugin/;`.

### 2. Phandle Targets Require Symbol Export in Base DTB
If you use `target = <&i2c1>;`, the base DTB must have a `__symbols__` node that maps `i2c1` to a phandle. Compile the base DTB with `dtc -@` (same flag as overlays). Without `-@`, the overlay will fail to apply with `symbols not found` errors. Many distro kernels ship without symbols—check with `fdtdump base.dtb | grep __symbols__`.

### 3. Overlay Application Order Matters
If overlay A depends on a node added by overlay B, you must load B first. The kernel doesn't resolve cross-overlay dependencies. I learned this the hard way when my GPIO expander overlay failed because the parent I2C bus overlay wasn't loaded yet. Always load parent dependencies before children.

### 4. Properties Are Merged, Not Replaced (by Default)
When an overlay adds a property that already exists in the base tree, the kernel merges them. For `gpio-line-names`, this appends to the existing list. To *replace* a property, you must explicitly set it to an empty value first, then add the new one. This is a frequent source of "why is my property doubled?" bugs.

## Try It Yourself

1. **Create a minimal overlay** for your target board that adds a new I2C device (e.g., an EEPROM at address 0x50). Compile it with `dtc -@`, then inspect the binary with `fdtdump`. Verify the fragment structure is correct.

2. **Apply an overlay at runtime** using configfs. Start with a simple overlay that changes a `status` property from `"disabled"` to `"okay"` on an unused SPI controller. Check `/sys/kernel/debug/devicetree` before and after to confirm the change.

3. **Debug a failed overlay application**. Intentionally create an overlay with a wrong phandle target (e.g., `target = <&nonexistent>`). Compile it, attempt to load it via configfs, and capture the kernel log (`dmesg | tail`). Identify the error message and fix the overlay.

## Next Up

Tomorrow we'll tackle **Applying Overlays at Boot: U-Boot & overlays.txt**. We'll cover how to load overlaves automatically during kernel boot using U-Boot's `fdt apply` command, the `overlays.txt` configuration file, and how to bake overlays into FIT images. Bring your boot logs.
