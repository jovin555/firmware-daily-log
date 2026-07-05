---
title: "Day 23: DTS Syntax: Nodes, Properties, Cells & Phandles"
date: 2026-07-05
tags: ["til", "devicetree", "dts", "nodes", "properties"]
---

## What I Explored Today

Today I dug into the raw syntax of Device Tree Source (DTS) files — the grammar that underpins every `.dts` and `.dtsi` file in the kernel. While I've been writing overlays for weeks, I realized I was cargo-culting the structure without understanding the formal rules. I focused on four core syntactic elements: **nodes** (the tree structure), **properties** (key-value pairs), **cells** (32-bit integers in arrays), and **phandles** (pointer references between nodes). This is the syntax you'll see in every `arch/arm/boot/dts/` file, and getting it right is non-negotiable for correct hardware description.

## The Core Concept

Device Tree is not a programming language — it's a data structure. The syntax exists to describe hardware topology and configuration in a way that's both human-readable and machine-parsable. Every DTS file is a single tree of **nodes**, each node containing **properties** that hold data. The magic comes from **phandles**: numeric labels that let one node reference another, enabling the kernel to wire up drivers, interrupts, GPIOs, and clocks across the tree.

Think of it like a filesystem: nodes are directories, properties are files. But unlike a filesystem, you can have "symlinks" via phandles. The **cells** are the raw data units — typically 32-bit integers — that fill those property files. Understanding how these four elements compose is the difference between writing an overlay that works and one that silently fails at boot.

## Key Commands / Configuration / Code

### 1. Node Syntax

Nodes are defined with a name and optional unit address (for memory-mapped devices):

```dts
// Simple node with unit address (the @0x1c10000 part)
uart0: serial@1c10000 {
    compatible = "allwinner,sun4i-a10-uart";
    reg = <0x01c10000 0x400>;
    interrupts = <0 0 4>;  // 3 cells: GIC type, SPI number, flags
};
```

- `uart0:` is a **label** — a local alias used for phandle references
- `serial@1c10000` is the node name + unit address (must match first `reg` cell)
- Braces `{}` enclose child nodes and properties
- Semicolons terminate each property statement

### 2. Properties and Cells

Properties are key-value pairs. The value can be a single cell, an array of cells, a string, or a byte array:

```dts
// Single cell (32-bit integer)
clock-frequency = <24000000>;

// Cell array (multiple 32-bit values)
reg = <0x01c10000 0x400>;  // address, length

// String
status = "okay";

// String list (compatible is always a string list)
compatible = "allwinner,sun4i-a10-uart", "ns16550";

// Byte array (for MAC addresses, etc.)
local-mac-address = [00 11 22 33 44 55];

// Empty property (boolean flag)
interrupt-controller;
```

The `< >` brackets denote a list of **cells** (u32 values). Each cell is 4 bytes. When you see `<0x01c10000 0x400>`, that's two cells: base address and size.

### 3. Phandles: The Reference System

Phandles are how nodes point to each other. There are two syntaxes:

```dts
// Explicit phandle property (rarely written manually)
interrupt-parent = <0x00000001>;  // numeric phandle

// Label-based reference (preferred)
interrupt-parent = <&gic>;  // & expands to the phandle value

// With cells appended (for GPIOs, clocks, interrupts)
reset-gpios = <&pio 7 6 GPIO_ACTIVE_LOW>;
//          phandle | cell1 | cell2 | cell3
```

The `&` prefix resolves to the phandle number of the labeled node. The compiler (`dtc`) replaces `&gic` with the actual numeric phandle value. Cells after the phandle are interpreted by the binding — for GPIOs, that's bank, pin, and flags.

### 4. Complete Example: Interrupt Controller and Consumer

```dts
/ {
    // Interrupt controller node
    gic: interrupt-controller@1c81000 {
        compatible = "arm,cortex-a7-gic";
        reg = <0x01c81000 0x1000>,
              <0x01c82000 0x2000>;
        interrupt-controller;          // boolean property
        #interrupt-cells = <3>;        // 3 cells per interrupt specifier
    };

    // Consumer node referencing the GIC
    serial@1c10000 {
        compatible = "allwinner,sun4i-a10-uart";
        reg = <0x01c10000 0x400>;
        interrupt-parent = <&gic>;     // phandle to GIC
        interrupts = <0 0 4>;          // 3 cells: type=0, SPI=0, flags=4
    };
};
```

The `#interrupt-cells = <3>` tells the kernel that any `interrupts` property referencing this controller must provide exactly 3 cells per interrupt.

## Common Pitfalls & Gotchas

1. **Missing `#*-cells` properties**: If a node is an interrupt controller, GPIO controller, or clock provider, it *must* declare `#interrupt-cells`, `#gpio-cells`, or `#clock-cells`. Without these, the kernel can't parse the cell arrays in consumer nodes. The compiler won't warn you — the boot will just fail silently.

2. **Phandle vs. label confusion**: A label (`uart0:`) is a compile-time alias. A phandle is a runtime numeric ID. You can't use a label in a property value without the `&` prefix. Writing `interrupt-parent = <uart0>` is wrong — it must be `interrupt-parent = <&uart0>`. The compiler will error on this, but I've seen people confuse it with string properties.

3. **Cell count mismatches**: If a GPIO controller declares `#gpio-cells = <2>`, you must provide exactly 2 cells after the phandle: `<&gpio0 12 GPIO_ACTIVE_HIGH>` is correct; `<&gpio0 12>` is missing the flags cell. The kernel's GPIO subsystem will read garbage and likely crash.

## Try It Yourself

1. **Parse a real DTS**: Open `arch/arm/boot/dts/sun8i-h3.dtsi` and find a node with an `interrupts` property. Count the cells and verify they match the `#interrupt-cells` of the referenced interrupt controller.

2. **Write a minimal overlay**: Create an overlay that adds a new I2C device node with a `reg` property of 2 cells and a `compatible` string. Reference the I2C controller using a phandle (`&i2c0`). Compile it with `dtc -@ -I dts -O dtb -o test.dtbo test.dts`.

3. **Debug a phandle error**: Take a working DTS, remove the `#interrupt-cells` from the GIC node, and compile. Observe that `dtc` doesn't error. Then try to boot it on QEMU and see the kernel panic. This drives home why binding documentation matters.

## Next Up

Tomorrow: **Data Types in Device Tree: u32, string, bytearray** — we'll go beyond cells and explore how the kernel interprets different property value formats, including endianness, string encoding, and the dreaded `phandle + cells` ambiguity.
