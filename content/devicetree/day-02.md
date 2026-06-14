---
title: "Day 02: DTS Syntax: Nodes, Properties, Cells & Phandles"
date: 2026-06-14
tags: ["til", "devicetree", "dts", "nodes", "properties"]
---

## What I Explored Today

After yesterday's high-level overview of why Device Trees exist, I dove into the actual syntax that makes them work. DTS (Device Tree Source) files are surprisingly readable once you understand the grammar. Today I focused on the four fundamental building blocks: nodes (the hardware components), properties (their attributes), cells (numeric data), and phandles (pointer-like references). I wrote a small DTS fragment for an imaginary SoC and compiled it with `dtc` to verify correctness—nothing beats seeing the binary blob come out clean.

## The Core Concept

Think of a Device Tree as a filesystem for hardware. Nodes are directories, properties are files. But unlike a filesystem, the tree is strictly hierarchical and every node has exactly one parent (except the root). The real power comes from how nodes reference each other: phandles are essentially symbolic links that let one node point to another without duplicating data.

Why does this matter? Because real hardware is interconnected. A UART controller needs to know which interrupt controller handles its IRQ line. An I2C bus needs to know which GPIO pins serve as SDA and SCL. Without phandles, you'd have to hardcode addresses or duplicate entire node definitions. With phandles, you get clean, maintainable references that the kernel can resolve at boot time.

The `#address-cells` and `#size-cells` properties are the unsung heroes here. They tell the parser how many 32-bit words to use for addresses and sizes in child nodes. Get these wrong, and your entire memory map shifts—a classic "why isn't my driver seeing the right register base?" bug.

## Key Commands / Configuration / Code

Let's build a minimal but realistic DTS fragment. I'll model a simple SoC with a UART and an interrupt controller.

```dts
// my-soc.dts - Minimal SoC with UART and interrupt controller
/dts-v1/;

/ {
    // Root node: the entire board
    compatible = "mycompany,my-soc-v1";
    #address-cells = <1>;  // 1 cell (32 bits) for addresses
    #size-cells = <1>;     // 1 cell (32 bits) for sizes

    // Interrupt controller at 0x10000000, 4KB size
    intc: interrupt-controller@10000000 {
        compatible = "mycompany,intc-v1";
        reg = <0x10000000 0x1000>;  // address, size
        interrupt-controller;       // boolean property (no value)
        #interrupt-cells = <2>;     // 2 cells: <IRQ_number flags>
    };

    // UART at 0x20000000, 1KB size
    uart0: serial@20000000 {
        compatible = "mycompany,uart-v1";
        reg = <0x20000000 0x400>;   // address, size
        interrupts = <0 4>;         // IRQ 0, active high level-sensitive
        interrupt-parent = <&intc>; // phandle to intc node
        clock-frequency = <24000000>; // 24 MHz
    };
};
```

Now compile it to verify syntax:

```bash
# Install device-tree-compiler if needed (Ubuntu/Debian)
sudo apt-get install device-tree-compiler

# Compile DTS to DTB (binary blob)
dtc -I dts -O dtb -o my-soc.dtb my-soc.dts

# Decompile back to DTS to see what dtc normalized
dtc -I dtb -O dts -o my-soc-decompiled.dts my-soc.dtb

# Check for warnings/errors (always do this)
dtc -I dts -O dtb -o /dev/null my-soc.dts 2>&1
```

Key observations from the decompiled output:
- `dtc` automatically assigns a phandle value (e.g., `phandle = <0x00000001>;`) to any node with a label (`intc:`).
- The `&intc` reference is resolved to that numeric phandle.
- The `interrupts` property is stored as raw cells: `<0 4>`.

## Common Pitfalls & Gotchas

1. **Mismatched address/size cells**: If your parent says `#address-cells = <2>` but you provide only one cell in `reg`, `dtc` won't always catch it—it just reads garbage. Always cross-check. For 64-bit addresses, use `<2>` for address cells.

2. **Phandle label vs. path reference**: `&intc` is a label reference (requires a label like `intc:`). You can also use `&{/interrupt-controller@10000000}` for a full path, but labels are cleaner. Never mix both styles in the same property—it's confusing and fragile.

3. **Boolean properties vs. empty values**: `interrupt-controller;` (no value) is a boolean property. Don't write `interrupt-controller = <>;` or `interrupt-controller = <0>;`—that changes semantics. Some bindings treat a zero value as "disabled," which is not what you want.

4. **Cell ordering in interrupts**: The number of cells per interrupt is defined by `#interrupt-cells` in the interrupt controller. For ARM GIC, it's often 3 cells (type, number, flags). For a simple controller, it might be 2. Always check the binding documentation—don't guess.

## Try It Yourself

1. **Add a GPIO controller**: Extend the DTS above with a GPIO controller at 0x30000000, size 0x1000, with 32 GPIOs. Give it a label `gpio0` and add a `#gpio-cells = <2>` property. Then make the UART reference a GPIO line for flow control using `gpios = <&gpio0 5 0>;`.

2. **Experiment with cell sizes**: Change `#address-cells` to `<2>` in the root node, then update the `reg` properties to use two cells each (e.g., `<0 0x10000000 0 0x1000>`). Compile and decompile to see how the binary representation changes.

3. **Force a phandle conflict**: Create two nodes with the same label (e.g., `foo: node@1` and `foo: node@2`). Run `dtc` and observe the error. Then fix it by renaming one label.

## Next Up

Tomorrow I'll tackle **Data Types in Device Tree: u32, string, bytearray**. We'll look at how `dtc` encodes different property values, why `reg` is always a list of u32 cells, and how to embed binary data (like firmware blobs) using `/incbin/`. This is where the rubber meets the road for driver developers.
