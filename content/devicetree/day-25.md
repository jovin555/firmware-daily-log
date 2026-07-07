---
title: "Day 25: Address Cells & Size Cells: Memory Maps in DT"
date: 2026-07-07
tags: ["til", "devicetree", "address-cells", "size-cells"]
---

## What I Explored Today

Today I dug into the two properties that form the backbone of every memory-mapped device in a Device Tree: `#address-cells` and `#size-cells`. These deceptively simple integer properties define how addresses and lengths are encoded in the `reg` property of child nodes. Without them, the kernel literally cannot parse where your peripherals live in the physical address space. I spent the morning tracing through real-world `.dts` files for an i.MX8M Plus board and the Linux kernel's `drivers/of/address.c` to understand how the OF core resolves these cells into `struct resource` entries.

## The Core Concept

Every device that sits on a memory-mapped bus (like AMBA, AXI, or even a simple internal peripheral bus) needs to tell the OS: "I am at physical address X, and I occupy Y bytes." That information lives in the `reg` property. But `reg` is just a sequence of 32-bit integers. The *interpretation* of those integers depends entirely on `#address-cells` and `#size-cells`.

Think of it as a contract between a parent bus node and its children. The parent declares:
- `#address-cells`: how many 32-bit cells form one address
- `#size-cells`: how many 32-bit cells form one size/length

A child's `reg` property is then a concatenation of `(address, size)` tuples. For a 32-bit system, you typically see `#address-cells = <1>` and `#size-cells = <1>`. For a 64-bit system (like ARMv8 with >4GB DRAM), you'll see `#address-cells = <2>` and `#size-cells = <2>`, because a single 32-bit cell can't hold a 64-bit address.

The kernel's OF core walks the tree, reads these properties from each bus node, and uses them to decode `reg` into the `struct resource` that drivers request with `platform_get_resource()`. Get the cell counts wrong, and your driver will request memory at address `0x00000000_00001000` instead of `0x00000001_00001000` — a silent, hard-to-debug failure.

## Key Commands / Configuration / Code

Let's look at a concrete example from a real i.MX8M Plus UART node:

```dts
// Parent bus node (from imx8mp.dtsi)
soc@0 {
    compatible = "simple-bus";
    #address-cells = <2>;   // 64-bit addresses
    #size-cells = <2>;      // 64-bit sizes
    ranges;                 // direct mapping to parent address space

    uart1: serial@30860000 {
        compatible = "fsl,imx8mp-uart", "fsl,imx6q-uart";
        reg = <0x00 0x30860000 0x00 0x10000>;
        //         ^address (64-bit)  ^size (64-bit)
        //         high  low           high  low
        interrupts = <GIC_SPI 26 IRQ_TYPE_LEVEL_HIGH>;
        clocks = <&uart1_clk>;
        status = "disabled";
    };
};
```

Notice the `reg` property has four 32-bit cells: two for the address (0x00_30860000) and two for the size (0x00_00010000). If the parent had `#address-cells = <1>` and `#size-cells = <1>`, the same `reg` would be parsed as address=0x00, size=0x30860000 — completely wrong.

Now let's decode this in a driver:

```c
// Inside the UART driver's probe function
static int imx_uart_probe(struct platform_device *pdev)
{
    struct resource *res;

    // Kernel automatically decodes reg using parent's cell counts
    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    if (!res)
        return -ENXIO;

    // res->start = 0x30860000
    // res->end   = 0x3086FFFF
    // resource_size(res) = 0x10000

    dev_info(&pdev->dev, "UART at 0x%llx size %llu\n",
             (unsigned long long)res->start,
             (unsigned long long)resource_size(res));

    // Request and ioremap the region
    if (!request_mem_region(res->start, resource_size(res), "imx-uart"))
        return -EBUSY;

    void __iomem *base = ioremap(res->start, resource_size(res));
    // ... hardware access ...
}
```

To inspect what the kernel actually parsed, use the OF debugfs interface:

```bash
# On the target board
cat /proc/device-tree/soc@0/uart1@30860000/reg
# Output: 00 00 30 86 00 00 00 00 01 00 00
#         ^--address (8 bytes)  ^--size (8 bytes)

# Or use dtc to decompile the live tree
dtc -I fs -O dts /proc/device-tree
```

## Common Pitfalls & Gotchas

1. **Mismatched cell counts between parent and child `ranges`**: The `ranges` property also uses the parent's `#address-cells` and `#size-cells` for its own encoding. If you change `#address-cells` in a bus node, you must update every `reg` and `ranges` entry in that node's subtree. I've seen a board fail to boot because a PCIe bridge node had `#address-cells = <3>` (PCIe uses 3 cells: bus/dev/func + address space type + address) but the child's `reg` was written with only 2 cells.

2. **Forgetting that `#address-cells` and `#size-cells` are inherited**: If a bus node doesn't explicitly declare them, the kernel uses the parent's values. This can cause subtle bugs when you add a new bus node (like a simple-bus) under a root node that has `#address-cells = <2>` — your new bus inherits those values, but you might write `reg` entries with single cells.

3. **Zero `#size-cells` for non-memory-mapped devices**: Some buses (like I2C or SPI) have `#size-cells = <0>` because their children don't occupy memory space. In that case, the `reg` property contains only an address (e.g., an I2C slave address), with no size. Writing a size in `reg` when `#size-cells = <0>` will cause the kernel to misparse all subsequent properties.

## Try It Yourself

1. **Decode a real board's memory map**: On your target board, run `dtc -I fs -O dts /proc/device-tree > /tmp/live.dts`. Find a node with `#address-cells = <2>` and `#size-cells = <2>`. Manually decode its child's `reg` property into physical address and size. Verify against the board's reference manual.

2. **Write a device tree fragment for a 64-bit memory region**: Create an overlay that adds a reserved memory region at 0x1_0000_0000 (4GB boundary) with size 0x1000. Use `#address-cells = <2>` and `#size-cells = <2>`. Compile with `dtc -@ -I dts -O dtb -o test.dtb test.dts` and check the binary with `hexdump -C`.

3. **Break it on purpose**: Take a working `.dts` file and change `#address-cells` from `<2>` to `<1>` in a bus node. Recompile and boot. Observe the kernel warning in `drivers/of/address.c` when it detects the mismatch. Use `devmem2` to verify the driver mapped the wrong address.

## Next Up

Tomorrow: **Phandles & References: Linking Nodes Together** — we'll explore how Device Tree nodes reference each other using `phandle` and `&label` syntax, and how the kernel resolves these references at boot time to build the driver graph.
