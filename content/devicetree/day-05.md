---
title: "Day 05: Phandles & References: Linking Nodes Together"
date: 2026-06-17
tags: ["til", "devicetree", "phandles", "references", "labels"]
---

## What I Explored Today

Today I dug into how Device Tree nodes reference each other — the glue that turns a flat tree of hardware descriptions into a connected graph of dependencies. Specifically, I worked with **phandles** (numeric node identifiers) and **labels** (human-readable aliases), and how the DTC compiler resolves `&label` references into actual phandle values. This is essential for any driver that needs to point to another node: an interrupt controller, a clock provider, a GPIO bank, or a power domain.

## The Core Concept

A Device Tree is a tree, but hardware isn't always hierarchical. An Ethernet controller needs to know which PHY chip it talks to. A display driver needs to know which backlight PWM it controls. A USB controller needs to know its associated PHY. These are cross-tree relationships — a node in one branch must reference a node in a completely different branch.

The solution is the **phandle** (pointer handle). Every node can have a `phandle` property containing a unique 32-bit integer. When the DTC compiles a `.dts` file, it automatically assigns these numbers. As a developer, you never write raw phandle values — you use **labels** and the **reference syntax** (`&label`). The compiler resolves these references into the correct phandle number in the compiled `.dtb`.

This is not just syntactic sugar. Without phandles, you'd have to manually assign and track integer IDs across the entire tree — a maintenance nightmare. With labels, you can move nodes around, rename them, and the references update automatically.

## Key Commands / Configuration / Code

### Defining a label and using it as a phandle reference

```dts
// Define a node with a label
clk_pll: clock-controller@44e00000 {
    compatible = "ti,am3xx-pll";
    reg = <0x44e00000 0x1000>;
    #clock-cells = <0>;  // This node provides a single clock
};

// Another node that consumes the clock
uart0: serial@44e09000 {
    compatible = "ti,am3352-uart";
    reg = <0x44e09000 0x2000>;
    clocks = <&clk_pll>;  // Reference to the PLL node
    clock-names = "fck";
};
```

When compiled, `&clk_pll` becomes a `phandle` property value in the `clocks` cell. The `#clock-cells = <0>` tells the consumer that this clock provider takes zero arguments — just the phandle itself.

### Multiple cells in a phandle reference

```dts
gpio0: gpio@44e07000 {
    compatible = "ti,omap4-gpio";
    reg = <0x44e07000 0x1000>;
    #gpio-cells = <2>;  // GPIO specifier: <phandle gpio_num flags>
    gpio-controller;
};

leds {
    compatible = "gpio-leds";
    led-0 {
        gpios = <&gpio0 23 GPIO_ACTIVE_LOW>;  // phandle + 2 cells
        label = "heartbeat";
    };
};
```

Here `&gpio0` is the phandle, `23` is the GPIO number within that bank, and `GPIO_ACTIVE_LOW` is the flag. The `#gpio-cells = <2>` tells the compiler how many additional cells follow the phandle.

### Using phandles directly (rare, but you'll see it)

```dts
// This is what the compiler generates internally — you almost never write this
interrupt-parent = <0x00000003>;  // phandle value 3 points to some interrupt controller
```

Don't write raw hex phandles. Always use labels. The only time you see these is when disassembling `.dtb` files with `dtc -I dtb -O dts`.

### Checking phandle resolution in compiled output

```bash
# Disassemble a compiled DTB to see resolved phandles
dtc -I dtb -O dts -o output.dts boot.dtb

# Look for lines like:
#   phandle = <0x00000003>;
#   linux,phandle = <0x00000003>;
# These are the auto-generated phandle values
```

## Common Pitfalls & Gotchas

1. **Missing `#*-cells` properties.** If you reference a node with `&clk_pll` but the provider node lacks `#clock-cells`, the compiler will throw a warning or silently produce garbage. Every provider must declare how many cells its specifier takes. For clocks: `#clock-cells = <0>` (single clock) or `<1>` (multiple outputs). For GPIOs: typically `<2>`. For interrupts: `<3>` on ARM GIC.

2. **Circular references.** The DTC compiler will detect and reject circular phandle chains (A points to B, B points to A). This usually happens when you accidentally create a loop in power domains or clock parents. The error message is cryptic: "Reference to node that is not a phandle target" or simply a segfault in older dtc versions. Always check your dependency graph.

3. **Label scope and collisions.** Labels must be unique across the entire `.dts` and all included `.dtsi` files. If two included files define `clk_pll`, you get a duplicate label error. Use vendor or subsystem prefixes: `clk_am3_pll`, `clk_rk3399_gpll`. The kernel's `scripts/dtc/` has a `-Wunique_label` flag to catch these early.

4. **Overlays and phandle renumbering.** When applying an overlay, the base DTB's phandles are fixed, but the overlay's phandles get renumbered at apply time. If your overlay hardcodes a phandle value (e.g., `interrupt-parent = <0x03>`), it will break. Always use labels and `&reference` — the overlay loader handles remapping.

## Try It Yourself

1. **Trace a phandle chain.** Take a real `.dts` from your board (e.g., `arch/arm/boot/dts/am335x-boneblack.dts`). Find a node that uses `clocks = <&some_clk>`. Disassemble the compiled `.dtb` and verify that `some_clk` has a `phandle` property matching the value in the `clocks` cell.

2. **Break a reference intentionally.** Create a minimal `.dts` with two nodes: one that references `&target` and a `target` node that lacks `#clock-cells`. Compile with `dtc -@ -I dts -O dtb test.dts -o test.dtb`. Observe the warning. Then add `#clock-cells = <0>;` and recompile — the warning disappears.

3. **Write an overlay that references a base node.** Create a base `.dts` with a `gpio@...` node labeled `mygpio`. Write an overlay that adds a `leds` node with `gpios = <&mygpio 5 GPIO_ACTIVE_HIGH>`. Compile the base, then compile the overlay with `-@` flag. Apply the overlay using `configfs` or `dtbo` and verify the LED appears in `/sys/class/leds/`.

## Next Up

Tomorrow: **Binding Documentation: Writing & Reading DT Bindings** — we'll decode the YAML binding files in `Documentation/devicetree/bindings/`, learn how to write a binding for a new device, and understand why the kernel's `dt_binding_check` target is your new best friend.
