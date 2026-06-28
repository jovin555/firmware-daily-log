---
title: "Day 16: Interrupt Routing in Device Tree: interrupt-parent"
date: 2026-06-28
tags: ["til", "devicetree", "interrupts", "gic", "routing"]
---

## What I Explored Today

Today I dug into how the Device Tree handles interrupt routing—specifically the `interrupt-parent` property. While `interrupts` and `interrupt-controller` are well-known, `interrupt-parent` is the glue that connects a peripheral to its interrupt controller, especially in multi-controller topologies. Without it, the kernel wouldn't know which GIC, GPIO controller, or interrupt expander to route the interrupt line through. I traced through real SoC DTS files (i.MX8M, STM32MP1) and verified how the kernel parses these bindings at boot.

## The Core Concept

Every device that generates interrupts must specify *where* its interrupt line goes. The `interrupt-parent` property is a phandle pointing to the node that handles interrupts for that device. If omitted, the kernel walks up the device tree hierarchy looking for the nearest `interrupt-parent`—usually at the root node or the SoC bus node.

Why is this important? Modern SoCs have multiple interrupt controllers: the main GIC (Generic Interrupt Controller) for CPU-bound interrupts, GPIO controllers that can act as interrupt parents for external peripherals, and sometimes dedicated interrupt expanders (like the TI TCA6416). A device might connect to a GPIO pin that itself routes to the GIC—so the device's `interrupt-parent` is the GPIO controller, not the GIC directly.

The kernel's interrupt domain mapping works like this: each `interrupt-controller` node creates an irq_domain. When a device driver calls `platform_get_irq()`, the kernel uses the `interrupt-parent` to find the correct domain, then decodes the `interrupts` property using that controller's `#interrupt-cells` specification. This is why mismatched parents cause silent failures or wrong IRQ numbers.

## Key Commands / Configuration / Code

**Basic interrupt-parent usage (single GIC):**
```dts
/ {
    interrupt-parent = <&gic>;  // default for all nodes

    gic: interrupt-controller@2f000000 {
        compatible = "arm,gic-v3";
        reg = <0x0 0x2f000000 0x0 0x10000>;
        interrupt-controller;
        #interrupt-cells = <3>;  // SPI: <0 0 4> means (type, PPI/SPI, flags)
    };

    uart0: serial@21c0000 {
        compatible = "fsl,imx8mm-uart";
        reg = <0x0 0x21c0000 0x0 0x4000>;
        interrupts = <0 0x1a 4>;  // SPI 26, active high level-sensitive
    };
};
```

**Multi-parent routing (GPIO as interrupt parent):**
```dts
&gpio5 {
    interrupt-controller;
    #interrupt-cells = <2>;  // <pin, flags>
};

&i2c3 {
    touch@38 {
        compatible = "edt,edt-ft5406";
        reg = <0x38>;
        interrupt-parent = <&gpio5>;  // touch IRQ goes to GPIO5
        interrupts = <7 IRQ_TYPE_EDGE_FALLING>;  // GPIO5 pin 7
    };
};
```

**Checking interrupt routing at runtime:**
```bash
# Show interrupt mappings for all devices
cat /proc/interrupts | head -20

# Check a specific device's IRQ domain
ls -la /sys/kernel/debug/irq/domains/

# Trace interrupt parent resolution (kernel debug)
echo 'file drivers/of/irq.c +p' > /sys/kernel/debug/dynamic_debug/control
dmesg -w | grep 'of_irq_parse'
```

**Verifying the DTS compiles correctly:**
```bash
# dtc will catch missing interrupt-parent or mismatched cells
dtc -I dts -O dtb -o test.dtb test.dts 2>&1
# Look for: "interrupts_extended_property: too many cells" or "missing interrupt-parent"
```

## Common Pitfalls & Gotchas

**1. Forgetting interrupt-parent on leaf nodes when the default is wrong**
If your root node sets `interrupt-parent = <&gic>` but a peripheral actually connects to a GPIO controller, the kernel will try to decode the `interrupts` property using GIC's 3-cell format instead of GPIO's 2-cell format. This silently corrupts the IRQ number. Always explicitly set `interrupt-parent` on nodes that don't use the default.

**2. Mixing `interrupts-extended` with `interrupt-parent`**
The `interrupts-extended` property is an alternative that embeds the parent phandle directly into each interrupt specifier: `interrupts-extended = <&gpio5 7 IRQ_TYPE_EDGE_FALLING>, <&gic 0 42 4>;`. This is useful when a device has interrupts going to *different* controllers. But if you use `interrupts-extended`, you must *not* also set `interrupt-parent`—the kernel will ignore it and may produce confusing warnings.

**3. Incorrect `#interrupt-cells` for the chosen parent**
Each interrupt controller defines how many cells its `interrupts` property uses. GICv3 uses 3 cells, most GPIO controllers use 2, and legacy interrupt controllers may use 1. If you specify `interrupts = <7>` but the parent expects 2 cells, dtc won't error (it can't validate cell counts across phandles), but the kernel will fail to parse the interrupt. Always cross-reference the controller's binding documentation.

## Try It Yourself

**Task 1: Trace interrupt-parent in a real DTS**
Pick a BSP kernel tree (e.g., Linux 6.1+). Find a device that uses a GPIO as interrupt-parent (search for `interrupt-parent = <&gpio`). Verify the GPIO node has `interrupt-controller;` and `#interrupt-cells = <2>;`. Then check the device's driver to see how it calls `devm_request_irq()`.

**Task 2: Build a multi-parent interrupt scenario**
Create a minimal DTS overlay that adds an I2C touch controller connected to GPIO5 pin 12, and a separate button connected to GPIO1 pin 3. Ensure each uses the correct `interrupt-parent` and `interrupts` format. Compile with `dtc` and verify no warnings.

**Task 3: Debug a missing interrupt-parent**
Take a working DTS, remove the `interrupt-parent` from a leaf node, and boot the kernel. Check `dmesg` for `of_irq_parse_one` errors. Then check `/proc/interrupts`—the device's IRQ line will either be missing or show a wildly wrong number. Restore the property and confirm the fix.

## Next Up

Tomorrow: **Device Tree in Yocto: KERNEL_DEVICETREE & DTBO** — how to integrate custom DTS and overlay files into a Yocto build, manage multiple device tree variants, and ensure your overlays are packaged into the root filesystem for runtime loading.
