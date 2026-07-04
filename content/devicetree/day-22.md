---
title: "Day 22: Device Tree Origins: Why It Exists & What Problem It Solves"
date: 2026-07-04
tags: ["til", "devicetree", "devicetree", "origins"]
---

## What I Explored Today

Today I stepped back from the practical mechanics of overlays and compilation to ask a fundamental question: why does the Device Tree exist at all? I traced the history from the early 2000s, when PowerPC Linux maintainers were drowning in board-specific `arch/ppc` code, through the adoption by ARM in 2011 (Linus Torvalds' infamous "this ARM thing is a f\*cking pain in the ass" rant at the 2011 ARM Linux Kernel Summit), to the modern flattened device tree (FDT) we use today. The core realization: Device Tree exists to decouple the kernel binary from hardware description, solving a maintainability crisis that had made Linux on embedded platforms nearly unmanageable.

## The Core Concept

Before Device Tree, each embedded board required a custom kernel binary. The kernel source tree was littered with `#ifdef CONFIG_BOARD_FOO` and board-specific `setup.c` files that hardcoded memory maps, interrupt numbers, and peripheral addresses. Every new board meant a new kernel build, a new patch set, and a new maintenance burden.

The problem was architectural: the kernel had to know, at compile time, exactly what hardware it would run on. This worked for x86 (where ACPI and PCI enumeration provided runtime discovery) but failed for embedded systems where memory-mapped peripherals, interrupt controllers, and GPIO banks were not discoverable. You couldn't "probe" for a UART at address 0x44E09000 — you had to be told it existed.

Device Tree solves this by moving hardware description from C code to a data structure passed to the kernel at boot. The kernel binary becomes board-agnostic; the bootloader (or firmware) provides the specific hardware topology as a flattened binary blob (DTB). This is the same principle as ACPI on x86, but designed for the simpler, more static world of embedded systems.

The key insight: **Device Tree is not a configuration language — it's a hardware description language.** You are not "configuring" Linux; you are describing the hardware so Linux can discover it.

## Key Commands / Configuration / Code

Let's see the difference in practice. Here's what the old approach looked like — hardcoded platform data in C:

```c
// arch/arm/mach-omap2/board-omap3beagle.c (simplified)
static struct resource uart1_resources[] = {
    {
        .start = 0x4806A000,  // UART1 base address
        .end   = 0x4806AFFF,
        .flags = IORESOURCE_MEM,
    },
    {
        .start = 72,  // IRQ number
        .end   = 72,
        .flags = IORESOURCE_IRQ,
    },
};

static void __init beagle_init(void) {
    platform_device_register(&uart1_device);
    // ... 200 more lines of board-specific setup
}
MACHINE_START(OMAP3_BEAGLE, "TI OMAP3 BeagleBoard")
    .init_machine = beagle_init,
    .map_io = omap3_map_io,
MACHINE_END
```

Now the Device Tree equivalent:

```dts
// arch/arm/boot/dts/omap3-beagle.dts
/ {
    model = "TI OMAP3 BeagleBoard";
    compatible = "ti,omap3-beagle", "ti,omap3";

    soc {
        uart1: serial@4806a000 {
            compatible = "ti,omap3-uart";
            reg = <0x4806a000 0x1000>;
            interrupts = <72>;
            status = "okay";
        };
    };
};
```

The kernel driver now matches on `compatible` strings:

```c
// drivers/tty/serial/omap-serial.c
static const struct of_device_id omap_serial_of_match[] = {
    { .compatible = "ti,omap3-uart", },
    { .compatible = "ti,omap4-uart", },
    { /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, omap_serial_of_match);

static int omap_serial_probe(struct platform_device *pdev) {
    struct resource *res;
    int irq;

    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    irq = platform_get_irq(pdev, 0);
    // No board-specific code needed — all from DT
}
```

To see what your current system provides, dump the live Device Tree:

```bash
# Dump the current DT to a human-readable format
dtc -I fs -O dts /sys/firmware/devicetree/base > current.dts

# Check the kernel's built-in DT compatibility list
cat /proc/device-tree/compatible
# Example output: "raspberrypi,4-model-b\0brcm,bcm2711"
```

## Common Pitfalls & Gotchas

1. **Confusing `compatible` with `model`.** The `model` property is a human-readable string (e.g., "TI OMAP3 BeagleBoard"). The `compatible` property is a prioritized list of machine identifiers used for matching. Always put the most specific match first: `"ti,omap3-beagle", "ti,omap3"`. The kernel walks the list until it finds a driver that matches.

2. **Assuming Device Tree replaces all board code.** It doesn't. Pinmuxing, clock tree setup, and power sequencing often still require C code in the kernel's machine-specific files. Device Tree describes *what* exists; the kernel still needs *how* to initialize it. The boundary is blurry and architecture-dependent.

3. **Forgetting that DT is a boot-time contract.** The kernel reads the DTB once during early boot. You cannot modify it at runtime (without `configfs` overlays). If your bootloader passes the wrong DTB, the kernel will happily boot with wrong memory sizes, missing peripherals, or incorrect interrupt routing. Always verify with `dtc -I dtb -O dts boot.dtb` before deployment.

## Try It Yourself

1. **Extract and inspect your running DT.** Run `dtc -I fs -O dts /sys/firmware/devicetree/base > system.dts`. Open the file and find the `chosen` node — it contains the kernel's boot arguments. Trace how `bootargs` from your bootloader ended up there.

2. **Compare old vs. new.** Find a legacy board file in the kernel source (e.g., `arch/arm/mach-pxa/` for PXA boards) and compare it to a modern DT-based board (e.g., `arch/arm/boot/dts/imx6qdl-sabresd.dtsi`). Count how many lines of C code were replaced by DT nodes.

3. **Simulate a missing DT.** Build a kernel without DT support for your architecture (set `CONFIG_OF=n` if possible) and try to boot it in QEMU. Observe the panic when the kernel can't find its hardware — this is the exact problem DT was created to solve.

## Next Up

Tomorrow we dive into the syntax itself: **DTS Syntax: Nodes, Properties, Cells & Phandles**. We'll dissect the grammar of `.dts` files, understand how `#address-cells` and `#size-cells` work, and learn how phandles create cross-references between nodes. Bring your text editor — we're writing Device Tree from scratch.
