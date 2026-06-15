---
title: "Day 03: Data Types in Device Tree: u32, string, bytearray"
date: 2026-06-15
tags: ["til", "devicetree", "dtypes", "cells", "arrays"]
---

## What I Explored Today

After two days of understanding the tree structure and node hierarchy, I needed to get my hands dirty with actual data. Device Tree is essentially a structured data description language, and today I dug into the three fundamental data types that form the backbone of every property: `u32` (32-bit unsigned integers), strings, and byte arrays. Understanding these types is critical because every hardware property—from register addresses to interrupt numbers to compatible strings—is expressed through them.

## The Core Concept

Device Tree is not a programming language; it's a data structure definition language. This means it has no loops, no conditionals, and no complex type system. Instead, it provides a minimal set of primitive types that are directly translatable to what the kernel's OF (Open Firmware) layer consumes at boot time.

The design philosophy is simple: every property value must be representable as a sequence of bytes that the bootloader or kernel can parse without ambiguity. The DTS compiler (`dtc`) enforces this by supporting only three raw data types:

1. **`u32` (cells)** – 32-bit unsigned integers, the most common type for addresses, sizes, and flags.
2. **Strings** – Null-terminated ASCII text, used for human-readable identifiers.
3. **Byte arrays** – Raw binary data, used for MAC addresses, device-specific configuration blobs, or opaque firmware data.

The key insight: the compiler internally represents *everything* as a byte array. The type annotations you write in DTS are syntactic sugar that `dtc` converts into the appropriate binary format in the compiled `.dtb` file.

## Key Commands / Configuration / Code

### u32 (Single Cell)

A single 32-bit value. Written as a decimal or hexadecimal literal:

```dts
// Single u32 property
reg = <0x10000000>;          // 32-bit address in hex
interrupts = <15>;           // IRQ line number (decimal)
clock-frequency = <50000000>; // 50 MHz in Hz
```

### u32 Array (Multiple Cells)

Multiple 32-bit values in angle brackets, space-separated:

```dts
// Two-cell address (common for ARM peripherals)
reg = <0x10000000 0x1000>;   // base address, size

// Three interrupt specifiers
interrupts = <0 15 4>;       // interrupt type, number, flags

// Array of GPIO pins
gpios = <&gpio0 17 0 &gpio1 3 0>;
```

### Strings

Single string or array of strings:

```dts
// Single string
compatible = "ti,am335x-uart";

// Array of strings (ordered by specificity)
compatible = "ti,am335x-uart", "ns16550a";

// Device name
device_type = "memory";
```

### Byte Arrays

Raw bytes in hex, enclosed in square brackets:

```dts
// MAC address (6 bytes)
local-mac-address = [00 11 22 33 44 55];

// Device-specific configuration blob
custom-config = [DE AD BE EF 01 02 03 04];

// Mixed with cells (using angle brackets for cells, brackets for bytes)
reg = <0x10000000 0x1000>, [01 02 03 04];
```

### Practical Example: UART Node

Here's how these types come together in a real device node:

```dts
uart0: serial@10000000 {
    compatible = "ti,am335x-uart", "ns16550a";  // string array
    reg = <0x10000000 0x1000>;                   // two u32 cells: base, size
    interrupts = <0 72 4>;                       // three u32 cells: type, irq, flags
    clock-frequency = <48000000>;                // single u32
    current-speed = <115200>;                    // single u32
    local-mac-address = [00 11 22 33 44 55];     // byte array (6 bytes)
    status = "okay";                             // string
};
```

### Compiler Verification

Always verify your types with `dtc`:

```bash
# Compile to DTB and decompile to check binary output
dtc -I dts -O dtb -o test.dtb test.dts
dtc -I dtb -O dts test.dtb   # human-readable decompilation
```

## Common Pitfalls & Gotchas

### 1. **Mixing Angle Brackets and Square Brackets Incorrectly**

The most common mistake is using angle brackets `< >` for byte arrays or square brackets `[ ]` for cells. The compiler will catch this, but the error messages can be cryptic:

```dts
// WRONG: byte array in angle brackets
reg = <0x10000000 [00 11 22]>;  // dtc error: Expected number, got '['

// CORRECT: separate with comma
reg = <0x10000000>, [00 11 22];
```

### 2. **String Array Ordering Matters**

The `compatible` property is an ordered list. The kernel tries each string in order, from most specific to most generic. Reversing the order will break driver matching:

```dts
// WRONG: generic first
compatible = "ns16550a", "ti,am335x-uart";  // kernel may bind wrong driver

// CORRECT: specific first
compatible = "ti,am335x-uart", "ns16550a";
```

### 3. **Byte Array vs. String Confusion**

A byte array `[48 65 6C]` is *not* the same as a string `"Hel"`. The kernel treats them differently—strings are null-terminated and may be parsed as text, while byte arrays are opaque binary data. Use strings for human-readable identifiers, byte arrays for hardware blobs.

## Try It Yourself

1. **Create a minimal DTS file** with a `memory` node that uses a two-cell `reg` property (base address `0x80000000`, size `0x10000000`). Compile with `dtc` and verify the output with `hexdump -C`.

2. **Add a `compatible` string array** to a GPIO controller node with three fallback strings: `"brcm,bcm2835-gpio"`, `"brcm,bcm2835-gpio-v2"`, and `"generic-gpio"`. Decompile the `.dtb` to confirm the order is preserved.

3. **Write a node with a byte array** containing a 6-byte MAC address `[DE AD BE EF 00 01]`. Use `dtc -O dtb` then `strings` on the output to see how the bytes are stored versus string properties.

## Next Up: Address Cells & Size Cells: Memory Maps in DT

Tomorrow, I'll tackle how Device Tree describes memory maps using `#address-cells` and `#size-cells`. These properties control how many `u32` values are used for addresses and sizes in child nodes—critical for understanding `reg` properties across different bus architectures. We'll decode the infamous `reg = <0x10000000 0x1000>` and learn why some devices use two cells per address while others use one.
