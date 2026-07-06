---
title: "Day 24: Data Types in Device Tree: u32, string, bytearray"
date: 2026-07-06
tags: ["til", "devicetree", "dtypes", "cells", "arrays"]
---

## What I Explored Today

Today I dug into the actual data types used in Device Tree source files. While DTS looks like a simple key-value store, the type system is surprisingly constrained — and deliberately so. The kernel's DT parser (libfdt) only understands three primitive types: 32-bit unsigned integers (u32), strings, and byte arrays (bytearrays). Everything else — from GPIO pin numbers to interrupt specifiers — is built from combinations of these. I spent the day mapping out exactly how each type works in practice, and where the common foot-guns hide.

## The Core Concept

Device Tree is not a general-purpose data language like JSON or XML. It's a hardware description format that must be parsed by bootloaders and early kernel code running in constrained environments. The DT specification mandates exactly three data types because the parser (libfdt) is designed to be tiny, deterministic, and free of dynamic memory allocation.

The key insight: **every property value in a DT node is either a sequence of bytes, or a sequence of 32-bit big-endian integers.** Strings and bytearrays are both stored as raw byte sequences — the difference is purely semantic. A `u32` is always 4 bytes, big-endian. A `string` is null-terminated. A `bytearray` is an arbitrary sequence of bytes.

This means that when you write `reg = <0x1000 0x2000>;`, you're actually writing a sequence of two u32 cells. When you write `compatible = "my-device";`, you're writing a null-terminated byte string. The DTS compiler (dtc) handles the encoding, but understanding the binary representation is essential for debugging.

## Key Commands / Configuration / Code

### u32 (cells)

The most common type. Written inside angle brackets `< >`, each value is a 32-bit unsigned integer. Multiple values are space-separated.

```dts
// Single u32 property
clock-frequency = <1000000>;          // 1 MHz

// Multiple u32 values (cell array)
reg = <0x1000 0x100>;                // base address, length

// Hex and decimal mix — dtc handles both
gpios = <&gpio0 17 0>;               // phandle (u32), pin (u32), flags (u32)
```

**Important:** All u32 values are stored big-endian in the flattened blob. On a little-endian ARM system, the kernel swaps bytes when reading.

### Strings

Strings are enclosed in double quotes. Multiple strings can be concatenated with a null separator using the `,` syntax:

```dts
// Simple string
compatible = "vendor,device";

// Multiple strings (null-separated in binary)
compatible = "ti,am335x-uart", "ns16550";

// String list — dtc packs them back-to-back with null terminators
// Binary: "ti,am335x-uart\0ns16550\0"
```

The kernel's `of_property_read_string()` and `of_property_count_strings()` APIs handle the null-separated format transparently.

### Byte Arrays

Byte arrays use square brackets `[ ]` with hex bytes:

```dts
// MAC address as byte array
local-mac-address = [00 11 22 33 44 55];

// Custom byte blob
vendor-data = [01 02 03 ff];

// Mixed with cells? Not directly — must use separate properties
```

Byte arrays are **not** the same as cell arrays. `[01 02]` is 2 bytes. `<0x0102>` is 4 bytes with value 0x00000102. Mixing them in the same property is illegal in DTS.

### Mixed Types (The Tricky Part)

Some properties appear to mix types, but they don't — they use a single type with encoding conventions:

```dts
// This is WRONG — dtc will reject it:
// reg = <0x1000> [01 02];   // ERROR: mixed types

// Correct approach: use cells for everything, or bytes for everything
// For a register with a byte offset, use two cells:
reg = <0x1000 0x100>;        // base, length — both u32

// For a custom blob, use byte array:
firmware-data = [ff ff ff ff 00 01];
```

## Common Pitfalls & Gotchas

### 1. Endianness Surprises in Byte Arrays vs. Cells

A u32 `<0x12345678>` is stored as bytes `12 34 56 78` in the DT blob (big-endian). A byte array `[12 34 56 78]` is stored as the same bytes. But the kernel treats them differently — `of_property_read_u32()` will byte-swap on little-endian CPUs, while `of_property_read_u8_array()` will not. If you accidentally use the wrong accessor, you'll get swapped data.

**Fix:** Always use the correct accessor for the intended type. If the property is defined with `< >`, use `of_property_read_u32*`. If defined with `[ ]`, use `of_property_read_u8*`.

### 2. String Lists Are Not Arrays of Strings

When you write `compatible = "a", "b";`, dtc creates a single contiguous byte array with null separators. The kernel's `of_property_read_string_index()` walks through this array counting nulls. If you try to read the property as a raw string with `of_property_read_string()`, you only get the first entry.

**Fix:** Always use the index-based API for string lists. Never assume `of_property_read_string()` returns the full list.

### 3. Phandles Are Just u32 Values

A phandle like `<&gpio0>` compiles to a single u32 — the offset of the referenced node in the DT blob. This means `gpios = <&gpio0 17 0>;` is actually a 3-cell array: phandle, pin, flags. If you miscount cells, you'll read garbage.

**Fix:** Always check the binding documentation for the exact cell count. For GPIOs, it's typically 2 or 3 cells depending on the controller.

## Try It Yourself

1. **Inspect raw DT binary types:** Take a compiled `.dtb` file and use `fdtdump` to view the raw property values. Identify which properties are cells (shown as numbers in angle brackets) vs. strings vs. byte arrays. Compare with the DTS source.

2. **Write a DTS overlay with mixed types:** Create an overlay that adds a node with a `reg` property (u32 cells), a `compatible` string, and a `local-mac-address` byte array. Compile it with `dtc -@` and verify the binary output with `hexdump -C`.

3. **Fix a common endianness bug:** Write a kernel module that reads a u32 property using `of_property_read_u32()` and also reads the same property as a byte array using `of_property_read_u8_array()`. Print both values and observe the byte order difference on a little-endian platform.

## Next Up

Tomorrow: **Address Cells & Size Cells: Memory Maps in DT** — we'll decode the `#address-cells` and `#size-cells` properties that define how memory-mapped devices describe their address ranges, and why getting them wrong causes silent boot failures.
