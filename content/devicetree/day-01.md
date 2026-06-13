---
title: "Day 01: Device Tree Origins: Why It Exists & What Problem It Solves"
date: 2026-06-13
tags: ["til", "devicetree", "devicetree", "origins"]
---

## What I Explored Today

I dug into the history and motivation behind the Device Tree (DT) — specifically, why Linux on ARM was a mess before it, and how DT replaced a spaghetti of board-specific C files. The short answer: every ARM board required a custom `arch/arm/mach-*` directory with hardcoded register addresses, clock definitions, and interrupt mappings. The Device Tree flattened that into a single, board-agnostic kernel that discovers hardware at boot via a binary blob. Today I traced the lineage from PowerPC’s Open Firmware to the current `*.dtb` files we flash alongside `zImage`.

## The Core Concept

The Device Tree solves one fundamental problem: **separating hardware description from kernel code**. Before DT, if you wanted Linux to boot on a new ARM board, you either patched the kernel with a new `board-*.c` file or you maintained a fork. Every kernel release broke your board. The DT approach treats the hardware topology as *data*, not code. The kernel binary stays identical across boards; only the `.dtb` changes.

Think of it as a hardware schema: a tree of nodes, each with properties (registers, interrupts, clocks). The kernel’s driver probes against this tree, matching `compatible` strings. No more `#ifdef CONFIG_BOARD_FOO`. No more magic numbers scattered across C files. The DT is compiled once by `dtc` (Device Tree Compiler) into a binary `.dtb`, which the bootloader passes to the kernel at `r2` on ARM, or via UEFI’s `devicetree` protocol on AArch64.

The real genius? Overlays. You can compose a base DT for a SoC (e.g., i.MX8M) and then layer on a board-specific overlay for your custom peripherals — without recompiling the kernel. This is how Raspberry Pi handles HATs, and how Yocto/Buildroot manage BSP variants.

## Key Commands / Configuration / Code

Let’s start with the toolchain. You need `dtc` — the Device Tree Compiler. On Ubuntu/Debian:

```bash
sudo apt install device-tree-compiler
# Verify:
dtc --version   # Should show v1.6.x or later
```

A minimal Device Tree source (`.dts`) file:

```dts
/dts-v1/;

/ {
    model = "ACME Cortex-A53 Board";
    compatible = "acme,board-v1", "arm,vexpress";

    #address-cells = <1>;
    #size-cells = <1>;

    memory@80000000 {
        device_type = "memory";
        reg = <0x80000000 0x40000000>;  // 1 GiB at 0x8000_0000
    };

    uart0: serial@1c090000 {
        compatible = "ns16550a";
        reg = <0x1c090000 0x1000>;
        interrupts = <0 5 4>;          // GIC SPI 5, level-high
        clock-frequency = <24000000>;
    };
};
```

Compile it to a DTB:

```bash
dtc -I dts -O dtb -o board.dtb board.dts
```

Decompile a DTB back to human-readable DTS (great for reverse-engineering a shipped board):

```bash
dtc -I dtb -O dts -o decompiled.dts board.dtb
```

To see the DT that the kernel actually used (from a running system):

```bash
# On the target:
cat /sys/firmware/devicetree/base/model
# Or dump the whole tree:
dtc -I fs -O dts /sys/firmware/devicetree/base
```

The `-I fs` flag reads the kernel’s live devicetree filesystem — no DTB file needed.

## Common Pitfalls & Gotchas

1. **Missing `#address-cells` and `#size-cells`**  
   If you omit these in a bus node (like `soc` or `amba`), the kernel will misinterpret `reg` properties. Default is 2 cells each on 64-bit systems, but many 32-bit peripherals expect 1. Always set them explicitly. A missing `#size-cells` can cause the kernel to read 8 bytes of address when you intended 4 — silent memory corruption.

2. **`compatible` string ordering matters**  
   The kernel matches from left to right. Put the most specific string first, then fallbacks. For example: `"ti,am335x-uart", "ns16550a"`. If you reverse it, the kernel will bind the generic 16550 driver even if a TI-specific driver exists with quirks. This is a common source of “why is my baud rate wrong?” bugs.

3. **Overlay phandle collisions**  
   When applying overlays, phandle numbers must be unique. If your base DT uses phandle `0x01` for the UART and your overlay also uses `0x01` for an I2C controller, the kernel will reject the overlay with a cryptic `FDT_ERR_BADPHANDLE`. Always use `dtc -@` to generate a base DT with symbols, and let the overlay reference symbols by name, not raw numbers.

## Try It Yourself

1. **Decompile your own board’s DTB**  
   If you have a Raspberry Pi or BeagleBone, run `dtc -I fs -O dts /sys/firmware/devicetree/base > myboard.dts`. Open the file and find the `memory` node, the `chosen` node (usually contains `bootargs`), and the UART node. Note the `reg` and `interrupts` values.

2. **Create a minimal overlay**  
   Write a `.dts` overlay that adds a GPIO-led node to a base DT. Compile with `dtc -@ -I dts -O dtb -o overlay.dtbo overlay.dts`. Apply it with `configfs` (if your kernel supports it):  
   ```bash
   mkdir /sys/kernel/config/device-tree/overlays/test
   cat overlay.dtbo > /sys/kernel/config/device-tree/overlays/test/dtbo
   ```

3. **Break and fix a DTS**  
   Take the minimal DTS above, remove the `#address-cells` line, recompile, and boot it in QEMU. Observe the kernel panic or hang. Then add it back and confirm the board boots.

## Next Up

Tomorrow we’ll dive into **DTS Syntax: Nodes, Properties, Cells & Phandles** — the grammar that makes the Device Tree tick. We’ll write a complete SoC-level DTS from scratch, learn how `reg` maps to physical addresses, and demystify phandle references (the `&uart0` syntax). Bring your text editor.
