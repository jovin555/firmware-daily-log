---
title: "Day 19: dtc & fdtdump: Compiling & Inspecting DTBs"
date: 2026-07-01
tags: ["til", "devicetree", "dtc", "fdtdump", "tools"]
---

## What I Explored Today

Today I went deep into the two workhorse tools of Device Tree work: `dtc` (Device Tree Compiler) and `fdtdump`. While I've used both casually for years, I spent today understanding their full capabilities—not just compiling `.dts` to `.dtb`, but also decompiling, overlaying, inspecting binary blobs, and debugging malformed trees. These tools are the gateway between human-readable source and the binary format the kernel consumes, and getting them right saves hours of boot-time head-scratching.

## The Core Concept

Device Tree source (`.dts`) is a human-readable text format, but the kernel and bootloaders consume flattened Device Tree blobs (`.dtb`)—a compact, binary representation. The `dtc` tool compiles `.dts` → `.dtb`, and can also decompile `.dtb` → `.dts` (with `-I dtb -O dts`). The `fdtdump` tool is a simpler, faster inspector that prints the raw structure of a `.dtb` without attempting full decompilation.

Why does this matter? Because in real engineering work, you rarely write a `.dts` from scratch. You start with a vendor-provided `.dtb`, decompile it to understand the board's base configuration, then write an overlay. Or you're debugging why a property isn't taking effect—you dump the final `.dtb` that was loaded, compare it to your source, and find the mismatch. Without these tools, you're flying blind.

The key insight: `dtc` is a compiler in the full sense—it performs syntax checking, semantic validation, and even optimization (like merging adjacent memory reservations). `fdtdump` is a disassembler-lite: it shows you the raw node/property tree without trying to reconstruct C-style syntax. Use `dtc` when you need to edit; use `fdtdump` when you need to quickly verify what's actually in the blob.

## Key Commands / Configuration / Code

### Basic Compilation and Decompilation

```bash
# Compile .dts to .dtb (most common)
dtc -I dts -O dtb -o my-board.dtb my-board.dts

# Decompile .dtb back to .dts (for inspection)
dtc -I dtb -O dts -o my-board-decompiled.dts my-board.dtb

# With annotations (preserves labels and phandles)
dtc -I dtb -O dts -o my-board-annotated.dts -@ my-board.dtb
```

### Advanced Flags

```bash
# Enable symbol generation for overlays (critical!)
dtc -@ -I dts -O dtb -o base.dtb base.dts

# Compile an overlay .dtso → .dtbo
dtc -@ -I dts -O dtb -o my-overlay.dtbo my-overlay.dtso

# Check for errors without generating output
dtc -I dts -O dtb -o /dev/null my-board.dts 2>&1

# Force output even with warnings (use with caution)
dtc -Wno-unit_address_vs_reg -I dts -O dtb -o output.dtb input.dts
```

### Using fdtdump

```bash
# Quick dump of entire tree
fdtdump my-board.dtb

# Pipe to less for scrolling
fdtdump my-board.dtb | less

# Check header info only
fdtdump -H my-board.dtb

# Compare two DTBs (after dumping to text)
fdtdump board-A.dtb > /tmp/a.txt
fdtdump board-B.dtb > /tmp/b.txt
diff /tmp/a.txt /tmp/b.txt
```

### Real-World Workflow: Inspecting a Kernel-Provided DTB

```bash
# Find the DTB that was actually loaded (on a running system)
# Usually in /sys/firmware/fdt or /proc/device-tree
cp /sys/firmware/fdt /tmp/loaded.dtb

# Decompile it to see what the kernel actually sees
dtc -I dtb -O dts -o /tmp/loaded.dts /tmp/loaded.dtb

# Compare with your source
diff -u my-board.dts /tmp/loaded.dts
```

### Creating and Applying Overlays

```bash
# Step 1: Create base DTB with symbols
dtc -@ -I dts -O dtb -o base.dtb base.dts

# Step 2: Create overlay DTB
dtc -@ -I dts -O dtb -o overlay.dtbo overlay.dtso

# Step 3: Apply overlay (produces final DTB)
fdtoverlay -o final.dtb -i base.dtb overlay.dtbo

# Step 4: Verify the result
dtc -I dtb -O dts final.dtb
```

## Common Pitfalls & Gotchas

1. **Missing `-@` flag when compiling base trees for overlays.** If you compile your base `.dts` without `-@`, it won't contain the `__symbols__` node. Overlays will fail to apply with cryptic "no symbols" errors. Always use `-@` if you plan to use overlays, even if you're not applying them immediately.

2. **`fdtdump` output is not valid `.dts`.** It's a debugging format, not a round-trip format. If you try to pipe `fdtdump` output directly into `dtc`, it will fail. Always use `dtc -I dtb -O dts` for decompilation that you intend to recompile.

3. **Phandle numbering can change between compilations.** The same `.dts` compiled twice may produce different phandle values if the compiler assigns them in a different order. Never hardcode phandle numbers in scripts—use labels and let `dtc` resolve them.

4. **Overlay `.dtbo` files must be compiled with `-@` too.** Both the base tree and the overlay need symbols. The overlay needs symbols so the base tree's `__fixups__` can be resolved. Forgetting `-@` on the overlay produces a `.dtbo` that can't be applied.

## Try It Yourself

1. **Decompile your running system's DTB.** Run `cp /sys/firmware/fdt /tmp/current.dtb` then `dtc -I dtb -O dts -o /tmp/current.dts /tmp/current.dtb`. Open the `.dts` and find the `chosen` node—what bootargs are set?

2. **Create a minimal overlay.** Write a 10-line `.dtso` that changes a single property (e.g., `status = "disabled"` on an LED node). Compile with `-@`, apply with `fdtoverlay`, and verify the property changed in the output.

3. **Compare vendor vs. decompiled DTB.** Take a vendor-provided `.dts`, compile it, then decompile the result. Use `diff` to see what changed—you'll likely see phandle renumbering and property reordering. This is normal, but understanding it prevents panic.

## Next Up

Tomorrow: **Common Device Tree Bugs & How to Debug Them** — we'll cover the top 5 mistakes that waste hours of debugging time, from unit address mismatches to missing `#address-cells`, and how to use `dtc` warnings, kernel logs, and `of_*` API checks to find them fast.
