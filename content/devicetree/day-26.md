---
title: "Day 26: Phandles & References: Linking Nodes Together"
date: 2026-07-08
tags: ["til", "devicetree", "phandles", "references", "labels"]
---

## What I Explored Today

Today I dug into how Device Tree nodes communicate with each other — not through magic, but through **phandles** and **references**. If you've ever wondered how a GPIO controller node tells the world "I'm the one you talk to for pin control," or how an I2C device says "my interrupt comes from that GIC node over there," you're dealing with phandles. I spent the day tracing through real kernel DTS files, compiling overlays with `dtc`, and understanding the difference between a `phandle` property (the integer identifier) and the `&label` syntax (the human-friendly reference). This is the glue that makes Device Tree a graph, not just a tree.

## The Core Concept

A Device Tree is a tree structure, but real hardware isn't a strict hierarchy — peripherals need to point to other peripherals. An Ethernet controller needs to know which PHY it talks to. A DMA client needs to reference its DMA controller. A clock consumer needs to find its clock provider.

The solution is the **phandle** — a unique 32-bit integer assigned to a node that can be referenced by other nodes. When the compiler (`dtc`) sees a reference like `&gpio0`, it resolves it to the target node's phandle value and inserts that integer into the referencing property.

Why not just use node names or paths? Because paths are fragile — renaming a node or moving it in the hierarchy breaks everything. Phandles are stable identifiers that survive reorganization. The `&label` syntax is syntactic sugar that the compiler resolves at build time, giving you both readability and robustness.

## Key Commands / Configuration / Code

### 1. Defining a node with a phandle (explicit vs. automatic)

```dts
// Explicit phandle assignment (rarely needed, dtc auto-assigns)
gpio0: gpio@ff000000 {
    compatible = "brcm,bcm2835-gpio";
    reg = <0xff000000 0x1000>;
    phandle = <42>;  // Explicitly set phandle to 42
};

// More common: let dtc assign phandles automatically
gpio1: gpio@ff001000 {
    compatible = "brcm,bcm2835-gpio";
    reg = <0xff001000 0x1000>;
    // dtc will assign a unique phandle (typically starting at 1)
};
```

### 2. Referencing a phandle in a property

```dts
/ {
    model = "My Board";
    compatible = "my,board";

    // Consumer node referencing the GPIO controller
    led {
        compatible = "gpio-leds";
        gpios = <&gpio0 17 GPIO_ACTIVE_HIGH>;
        // &gpio0 resolves to the phandle of gpio0 node
        // dtc inserts the integer phandle value here
    };

    // Interrupt consumer
    uart@fe201000 {
        compatible = "ns16550a";
        reg = <0xfe201000 0x1000>;
        interrupts = <0 33 4>;
        interrupt-parent = <&gic>;  // Reference to interrupt controller
    };
};
```

### 3. Compiling and inspecting phandles

```bash
# Compile DTS to DTB
dtc -I dts -O dtb -o board.dtb board.dts

# Decompile DTB back to DTS to see resolved phandles
dtc -I dtb -O dts board.dtb

# Output will show phandle properties explicitly:
# gpio0: gpio@ff000000 {
#     ...
#     phandle = <0x00000001>;
#     linux,phandle = <0x00000001>;
# };

# Use fdtdump for raw hex view
fdtdump board.dtb | grep phandle
```

### 4. Overlay with phandle references

```dts
// overlay.dts
/dts-v1/;
/plugin/;

&i2c1 {  // Reference to base tree label
    status = "okay";
    temp-sensor@48 {
        compatible = "ti,tmp102";
        reg = <0x48>;
        interrupts-extended = <&gpio0 10 IRQ_TYPE_EDGE_FALLING>;
        // &gpio0 must exist in the base tree
    };
};
```

### 5. Multiple phandles in a single property (cells)

```dts
// Clock consumer referencing multiple providers
cpu@0 {
    clocks = <&clk_osc 0>, <&clk_pll 1>;
    // Each entry is a <phandle cell> pair
    // dtc packs: <phandle_of_clk_osc 0 phandle_of_clk_pll 1>
};

// DMA client with channel specifier
spi@ff204000 {
    dmas = <&dma0 2>, <&dma0 3>;
    dma-names = "tx", "rx";
};
```

## Common Pitfalls & Gotchas

### 1. Missing labels cause silent failures
If you reference `&nonexistent_node`, `dtc` will throw an error — but only if you're compiling the full tree. In overlays, a missing label in the base tree produces a cryptic "label not found" at overlay apply time. Always verify your base tree exports the labels you need with `dtc -@` (which generates symbols).

### 2. Phandle values are not stable across compilations
Never hardcode phandle integers (e.g., `phandle = <42>`). The compiler assigns them sequentially based on node order, which can change if you add or remove nodes. Always use labels and let `dtc` manage the integers. Hardcoding phandles is the #1 cause of "it worked yesterday" bugs.

### 3. The `interrupt-parent` inheritance trap
If you don't explicitly set `interrupt-parent` on a node, it inherits from its parent. This seems convenient until you move a node in the tree and its interrupt parent changes silently. Always explicitly set `interrupt-parent` on leaf nodes that generate interrupts, especially in overlays where the parent context may differ.

## Try It Yourself

1. **Trace phandles in a real DTS**: Grab any ARM board DTS (e.g., `arch/arm/boot/dts/bcm2837-rpi-3-b.dts`), compile it with `dtc -@`, then decompile and grep for `phandle`. Map each phandle value back to its node. How many unique phandles exist?

2. **Create a two-node reference**: Write a minimal DTS with a "provider" node (label `my_prov`) and a "consumer" node that references it via `&my_prov`. Compile, decompile, and verify the consumer property contains the provider's phandle integer.

3. **Break an overlay on purpose**: Write an overlay that references a label not in your base tree. Try to apply it with `configfs` or `dtbo` and observe the error. Then fix it by adding the label to the base tree.

## Next Up

Tomorrow: **Binding Documentation: Writing & Reading DT Bindings** — we'll decode the YAML binding files in `Documentation/devicetree/bindings/` and learn how to write our own. Because without bindings, your DTS is just a pile of properties nobody can validate.
