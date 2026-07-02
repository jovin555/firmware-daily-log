---
title: "Day 20: Common Device Tree Bugs & How to Debug Them"
date: 2026-07-02
tags: ["til", "devicetree", "debug", "bugs", "dtc"]
---

## What I Explored Today

After weeks of building Device Trees and overlays, I finally hit a wall of silent failures — peripherals not probing, wrong interrupts firing, and memory regions overlapping. Today I systematically catalogued the most common Device Tree bugs I've encountered in production and embedded Linux bring-up, and more importantly, how to catch them before they waste hours of debug time. I focused on real-world patterns: what the DTC compiler won't tell you, what the kernel logs actually mean, and how to validate your tree without booting.

## The Core Concept

Device Tree bugs are insidious because the DTC compiler only checks syntax, not semantics. A valid `.dtb` can still describe a completely broken hardware configuration. The kernel will silently skip nodes with missing dependencies, use wrong register offsets, or fail to match drivers — all without a single compile error.

The root cause is almost always one of three things: **address/size mismatches** between the node and its parent's `#address-cells`/`#size-cells`, **phandle resolution failures** where a reference points to a non-existent or incorrectly typed node, or **status property conflicts** where a node is disabled by a board-level `.dts` but an overlay expects it enabled. The kernel's driver model is strict: if the `compatible` string matches but the `reg` property has the wrong number of cells, the driver's probe function never runs.

Debugging these requires a three-layer approach: static analysis with `dtc` and `dt-validate`, runtime inspection via `/sys/firmware/devicetree/base`, and kernel log filtering for `of_` and `driver_probe` messages. Most engineers skip the first layer and pay for it later.

## Key Commands / Configuration / Code

### 1. Static Validation with DTC

Always compile with `-W` warnings enabled. The default `dtc` invocation hides many issues:

```bash
# Compile with all warnings, treat them as errors
dtc -W all -E -I dts -O dtb -o board.dtb board.dts

# Check for unit-address vs. reg mismatch
dtc -W unit_address_vs_reg -W simple_bus_reg board.dts
```

The `-E` flag enables error-on-warning for strict compliance. Common warnings you should never ignore: `graph_endpoint`, `interrupt_provider`, `reg_format`.

### 2. Runtime Inspection via DebugFS

Mount debugfs and inspect the live tree:

```bash
mount -t debugfs none /sys/kernel/debug
cat /sys/kernel/debug/device_tree/__symbols__  # Check phandle resolution
cat /sys/kernel/debug/gpio  # Verify GPIO mappings match DT
```

For a specific node, check its properties directly:

```bash
# Check if a node actually exists in the live tree
ls /sys/firmware/devicetree/base/soc/i2c@7e804000/

# Read a property as raw bytes (watch endianness!)
hexdump -C /sys/firmware/devicetree/base/soc/i2c@7e804000/reg
```

### 3. Kernel Log Filtering for Probe Failures

The kernel logs are your best friend. Filter for the relevant subsystems:

```bash
# Watch for driver probe issues in real-time
dmesg -w | grep -E "(of_|driver_probe|platform_probe|i2c|spi)"

# After boot, find why a specific driver didn't bind
dmesg | grep -i "my_driver"  # Replace with your compatible string
dmesg | grep "EPROBE_DEFER"  # Deferred probes often hide bugs
```

### 4. Overlay Application Debugging

When an overlay fails to apply, use configfs to get detailed errors:

```bash
# Apply overlay via configfs
mkdir /sys/kernel/config/device-tree/overlays/test
cat my_overlay.dtbo > /sys/kernel/config/device-tree/overlays/test/dtbo

# Check for errors
cat /sys/kernel/config/device-tree/overlays/test/status  # "applied" or error
dmesg | tail -20 | grep -i overlay
```

## Common Pitfalls & Gotchas

### 1. The `reg` Property Cell Count Mismatch

This is the #1 bug. If your parent bus uses `#address-cells = <2>` (e.g., some ARM64 systems), but your child node's `reg` only provides one address cell, the kernel silently skips the node. The DTC compiler won't warn you unless you use `-W reg_format`.

**Fix:** Always check the parent's `#address-cells` and `#size-cells` before writing `reg`. Use `dtc -W reg_format` during compilation.

### 2. Phandle to a Disabled Node

You reference `&i2c0` in an overlay, but the base `.dts` has `&i2c0 { status = "disabled"; };`. The overlay's `__fixups__` resolves the phandle, but the kernel's driver core never probes the disabled node. This manifests as a silent probe failure.

**Fix:** Before applying overlays, verify the target node's status in the base tree: `cat /sys/firmware/devicetree/base/soc/i2c@7e804000/status`. If it's "disabled", your overlay must explicitly set `status = "okay"`.

### 3. Overlay Fragment Ordering Dependencies

When an overlay has multiple fragments, and fragment 2 depends on a node created by fragment 1, the kernel applies fragments sequentially. If fragment 2 references a node that doesn't exist yet, the overlay fails with `-EINVAL` and no helpful message.

**Fix:** Use `__overlay__` targets only on existing nodes. If you must create new nodes, ensure they are in the same fragment or use a single fragment. Alternatively, split into separate overlay files and apply them in order.

## Try It Yourself

1. **Find a silent `reg` bug**: Take a working `.dts` for a Raspberry Pi or BeagleBone, change the `#address-cells` of the `soc` node from `<1>` to `<2>`, and recompile. Observe that `dtc` without `-W reg_format` produces no error. Then boot and check `dmesg` for missing devices.

2. **Trace a deferred probe**: On any Linux board with Device Tree, run `dmesg | grep EPROBE_DEFER`. Pick one driver that deferred, find its node in the `.dts`, and identify which dependency (clock, regulator, interrupt) was missing. Fix the node and rebuild.

3. **Validate an overlay before applying**: Write a simple overlay that enables an I2C device. Before applying it, use `dtc -I dtb -O dts /sys/firmware/devicetree/base` to dump the live tree, then manually check that the target node exists and is enabled. Apply the overlay and verify with `cat /sys/kernel/config/device-tree/overlays/test/status`.

## Next Up

Tomorrow is the capstone: **Full Review & Project: DT Overlay for a Custom Sensor**. We'll take everything from the past 20 days — addressing, interrupts, pinmux, overlays, and debugging — and build a complete, production-quality overlay for a real I2C sensor (the BME280 environmental sensor). You'll write the `.dts`, compile it, apply it, and verify the sensor is probed and functional. Bring your board and a sensor module.
