---
title: "Day 04: Address Cells & Size Cells: Memory Maps in DT"
date: 2026-06-16
tags: ["til", "devicetree", "address-cells", "size-cells"]
---

## What I Explored Today

Yesterday we learned how to write a basic node and property. Today I dug into the backbone of every real Device Tree: how addresses and sizes are encoded. Without `#address-cells` and `#size-cells`, your `reg` properties are just meaningless hex numbers. I spent the day tracing how the kernel interprets these cells to build the physical memory map, and why getting them wrong silently breaks DMA, MMIO, and memory reservations.

## The Core Concept

A Device Tree describes hardware, and hardware lives at addresses. But address widths vary wildly: a 32-bit ARM SoC might use 32-bit addresses, while a 64-bit RISC-V chip might need 64-bit addresses, and a PCI bridge might use 3 cells (bus, device, function). The `#address-cells` and `#size-cells` properties tell the parser how many 32-bit words to consume for each address and each size field inside the `reg` property of child nodes.

Think of it as a contract: a parent node declares its address space format, and all children must comply. The parent’s `#address-cells` defines the width of addresses in its domain, and `#size-cells` defines the width of region lengths. The root node sets the system-wide default, but any bus bridge can redefine it for its subtree.

Why does this matter? Because the kernel’s `of_translate_address()` function walks up the tree, applying parent address cells at each level to compute the physical address. If you mismatch cells, the translation produces garbage, and your driver’s `ioremap()` maps to the wrong memory.

## Key Commands / Configuration / Code

Let’s start with the root node — the system’s top-level address map:

```dts
/ {
    #address-cells = <1>;   // 32-bit addresses
    #size-cells = <1>;      // 32-bit sizes

    memory@80000000 {
        device_type = "memory";
        reg = <0x80000000 0x10000000>;  // start=0x80000000, size=256MB
    };

    soc {
        #address-cells = <1>;
        #size-cells = <1>;
        compatible = "simple-bus";
        ranges;  // direct 1:1 mapping to parent

        uart@10000000 {
            compatible = "ns16550";
            reg = <0x10000000 0x1000>;   // 4KB MMIO region
            interrupts = <0 33 4>;
        };
    };
};
```

Now a 64-bit example — common on modern ARM64 or RISC-V:

```dts
/ {
    #address-cells = <2>;   // 64-bit addresses (two 32-bit cells)
    #size-cells = <2>;      // 64-bit sizes

    memory@80000000 {
        device_type = "memory";
        reg = <0x0 0x80000000 0x0 0x80000000>;
        //  address_hi=0x0, address_lo=0x80000000
        //  size_hi=0x0,    size_lo=0x80000000
        //  = 2GB starting at 0x80000000
    };
};
```

The `ranges` property deserves special attention. It translates child addresses to parent addresses:

```dts
soc {
    #address-cells = <1>;
    #size-cells = <1>;
    ranges = <0x0 0x10000000 0x1000>;
    // child_addr=0x0, parent_addr=0x10000000, length=0x1000
    // So child address 0x0 maps to parent address 0x10000000

    uart@0 {
        reg = <0x0 0x1000>;  // child sees address 0x0
    };
};
```

To inspect the parsed address map on a running system:

```bash
# Show the resolved memory map
cat /proc/iomem

# Dump the live Device Tree with resolved addresses
dtc -I fs -O dts /sys/firmware/devicetree/base

# Check a specific node's reg property
cat /sys/firmware/devicetree/base/soc/uart@10000000/reg | xxd
```

## Common Pitfalls & Gotchas

**1. Mismatched cells between parent and child `reg`**
The most frequent bug: a child node uses `#address-cells = <1>` but its parent expects `<2>`. The kernel reads the first 32-bit word as the address and the second as the size, producing wildly wrong translations. Always verify that every node with a `reg` property has a parent that defines `#address-cells` and `#size-cells`.

**2. Forgetting `ranges` or using it incorrectly**
If a bus bridge omits `ranges`, the kernel treats child addresses as un-translatable — drivers will fail to `ioremap()`. If you want a 1:1 mapping, use `ranges;` (empty). If you need a window, provide the triplets. A common mistake is providing `ranges` but with wrong cell counts.

**3. Mixing cell sizes in the same tree**
You cannot have a 32-bit root and a 64-bit child without proper translation. The kernel’s address translation walks parent-by-parent. If a parent uses `<1>` and the child uses `<2>`, the parser reads the child’s `reg` as two 32-bit words (address, size) instead of four (address_hi, address_lo, size_hi, size_lo). This corrupts every memory region below that node.

## Try It Yourself

1. **Decode a real `reg` property**: On any Linux system with Device Tree support, run `dtc -I fs -O dts /sys/firmware/devicetree/base > system.dts`. Find the `memory` node and manually decode its `reg` property based on the root’s `#address-cells` and `#size-cells`. Verify against `cat /proc/iomem`.

2. **Create a 64-bit memory map**: Write a minimal DTS file for a system with 4GB of RAM starting at 0x40000000. Use `#address-cells = <2>` and `#size-cells = <2>`. Compile it with `dtc -I dts -O dtb -o test.dtb test.dts` and decompile it back to verify your encoding.

3. **Add a bus with address translation**: Extend your DTS from task 2 with a `simple-bus` node that maps a 1MB child window to parent address 0x50000000. Add a child UART at child address 0x0 with size 0x1000. Use `dtc` to compile and check the `ranges` property is correctly encoded.

## Next Up

Tomorrow we tackle **Phandles & References: Linking Nodes Together**. You’ll learn how to create cross-node references, why `phandle` and `&label` are essential for interrupt controllers and clocks, and how to avoid the dreaded “Reference to non-existent node” error.
