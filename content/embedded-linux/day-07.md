---
title: "Day 07: Device Tree: Syntax, Bindings & Overlays"
date: 2026-06-19
tags: ["til", "embedded-linux", "devicetree", "dts"]
---

## What I Explored Today

I dove deep into the Device Tree — the data structure that tells the Linux kernel what hardware exists and how it's wired together. After weeks of bootloader and kernel configuration, I finally understood why Device Tree is the backbone of embedded Linux portability. Today I focused on three things: the syntax of `.dts` files, how bindings define hardware contracts, and the overlay mechanism that lets us modify the tree at runtime without recompiling.

## The Core Concept

The Device Tree solves a fundamental problem: how does a single kernel binary support hundreds of different ARM, RISC-V, or x86 boards? Before Device Tree, board-specific code was hardcoded in the kernel — a maintenance nightmare. The Device Tree is a hardware description language, not configuration. It describes *what* is connected (a UART at address `0x1c090000`, interrupt line 37) and *how* it's connected (clock parent, DMA channel, GPIO muxing). The kernel's device drivers then match against these descriptions using `compatible` strings.

Why this matters for engineers: you don't modify kernel source to add a new peripheral. You write a Device Tree source file, compile it to a binary blob (DTB), and pass it to the kernel at boot. The same kernel image boots on a BeagleBone Black and a Raspberry Pi 3 — only the DTB changes. Overlays take this further: you can enable a SPI bus, configure an LCD panel, or add a sensor without touching the base tree.

## Key Commands / Configuration / Code

### 1. Device Tree Source (DTS) — Basic Structure

```dts
// minimal.dts — A minimal device tree for a virtual SoC
/dts-v1/;

/ {
    model = "MyBoard v1";
    compatible = "mycompany,myboard", "arm,vexpress";  // match against kernel driver

    #address-cells = <1>;  // 32-bit addresses
    #size-cells = <1>;     // 32-bit sizes

    memory@80000000 {
        device_type = "memory";
        reg = <0x80000000 0x10000000>;  // 256 MB at 0x80000000
    };

    chosen {
        bootargs = "console=ttyAMA0,115200 root=/dev/mmcblk0p2";
        stdout-path = &uart0;
    };

    soc {
        #address-cells = <1>;
        #size-cells = <1>;
        ranges;  // translate child address to parent

        uart0: serial@1c090000 {
            compatible = "ns16550a";
            reg = <0x1c090000 0x1000>;
            interrupts = <0 37 4>;  // SPI, IRQ 37, active high
            clock-frequency = <24000000>;
            status = "okay";  // enable this node
        };

        gpio0: gpio@1c100000 {
            compatible = "mycompany,gpio";
            reg = <0x1c100000 0x1000>;
            gpio-controller;
            #gpio-cells = <2>;  // <pin, flags>
        };
    };
};
```

### 2. Compiling and Decompiling

```bash
# Compile DTS to DTB
dtc -I dts -O dtb -o myboard.dtb myboard.dts

# Decompile DTB back to DTS (useful for reverse engineering)
dtc -I dtb -O dts -o myboard_decompiled.dts myboard.dtb

# Check for errors with verbose output
dtc -I dts -O dtb -o myboard.dtb -@ myboard.dts  # -@ enables overlay support
```

### 3. Device Tree Overlay — Adding a SPI Device at Runtime

```dts
// overlay-spi.dts — Enable SPI1 and attach an MCP3008 ADC
/dts-v1/;
/plugin/;

/ {
    fragment@0 {
        target = <&spi1>;  // reference to base tree node
        __overlay__ {
            status = "okay";
            #address-cells = <1>;
            #size-cells = <0>;

            mcp3008@0 {
                compatible = "microchip,mcp3008";
                reg = <0>;  // chip select 0
                spi-max-frequency = <1000000>;
            };
        };
    };
};
```

Apply the overlay:

```bash
# Compile overlay
dtc -I dts -O dtb -o overlay-spi.dtbo overlay-spi.dts

# Apply at runtime (requires configfs support)
mkdir /sys/kernel/config/device-tree/overlays/spi-adc
cat overlay-spi.dtbo > /sys/kernel/config/device-tree/overlays/spi-adc/dtbo
```

### 4. Inspecting the Live Device Tree

```bash
# Full tree from /proc
dtc -I fs -O dts /proc/device-tree

# Quick check for a specific node
cat /proc/device-tree/soc/serial@1c090000/compatible
# Output: ns16550a

# List all enabled devices
find /proc/device-tree -name "status" -exec grep -l "okay" {} \;
```

## Common Pitfalls & Gotchas

**1. Address and size cell mismatch** — The most frequent bug. If `#address-cells = <2>` (64-bit addresses), your `reg` property must have two cells per address. A mismatch causes the kernel to silently misparse memory regions. Always verify with `dtc -I dts -O dtb -o test.dtb test.dts` — the compiler catches this.

**2. Forgetting `status = "okay"`** — By default, nodes are disabled. I spent an hour debugging a missing UART only to find the node had no status property. The kernel skips disabled nodes entirely. Always explicitly set `status = "okay"` for peripherals you want active.

**3. Overlay phandle conflicts** — When applying multiple overlays, phandle (pointer handle) numbers can collide. Use `dtc -@` to generate symbols, and ensure your overlay uses `&label` references rather than raw phandle numbers. The kernel's overlay system reassigns phandles, but raw numbers break.

**4. Binding documentation is your friend** — Don't guess property names. Every `compatible` string has a binding in `Documentation/devicetree/bindings/`. For example, `Documentation/devicetree/bindings/serial/8250.yaml` tells you exactly which properties `ns16550a` expects. Guessing leads to silent driver probe failures.

## Try It Yourself

1. **Decompile your board's DTB** — On a running system, run `dtc -I fs -O dts /proc/device-tree > myboard.dts`. Find the `chosen` node and identify the bootargs. Then add a new node for an imaginary I2C device at address 0x50, recompile, and verify with `dtc`.

2. **Write a GPIO LED overlay** — Create an overlay that enables a GPIO pin as an LED (use `compatible = "gpio-leds"`). Apply it at runtime via configfs, then trigger the LED from userspace by writing to `/sys/class/leds/<name>/brightness`.

3. **Fix a broken DTS** — Take the minimal DTS above, change `#address-cells` to `<2>` but leave `reg = <0x80000000 0x10000000>` (only one cell). Compile with `dtc` and observe the error. Then fix it by adding the second address cell. This teaches you the address/size cell relationship.

## Next Up

Tomorrow I'm building a root filesystem from scratch — BusyBox for userland utilities, initramfs for early boot, and understanding the classic filesystem layout (`/bin`, `/sbin`, `/etc`, `/dev`, `/proc`, `/sys`). We'll go from kernel panic to a working shell prompt.
