---
title: "Day 02: Schematic Editor (Eeschema): Symbols, Wires & Buses"
date: 2026-07-11
tags: ["til", "kicad", "eeschema", "symbols"]
---

## What I Explored Today

Today I dove deep into KiCad's schematic editor, Eeschema, focusing on the three fundamental building blocks of any schematic: symbols, wires, and buses. While I've placed components and drawn connections in other EDA tools before, KiCad's approach has some unique quirks—particularly around hierarchical sheets, global labels, and the way buses interact with individual signals. I spent the morning building a small ARM Cortex-M0 reference design from scratch, deliberately forcing myself to use buses for the address/data lines and hierarchical labels for power distribution. The goal was to understand not just *how* to place these elements, but *when* each tool is appropriate.

## The Core Concept

The schematic is the single source of truth for your entire PCB design. Every netlist, every footprint assignment, every ERC (Electrical Rules Check) violation traces back to decisions made here. The key insight is that KiCad treats symbols, wires, and buses as distinct objects with specific behaviors—not just visual placeholders.

**Symbols** are logical representations of components. They carry pin numbers, pin names, and electrical types (Input, Output, Passive, etc.). The electrical type matters because Eeschema's ERC uses it to flag unconnected outputs or conflicting drivers. A resistor symbol with Passive pins won't trigger warnings, but connecting two Output pins together will.

**Wires** are the actual electrical connections. In KiCad, a wire segment is a continuous line that, when connected to a pin or another wire, creates a net. The net name propagates automatically—you don't need to label every wire unless you want to force a specific net name. This is critical: KiCad's netlist generator traces connectivity through wire junctions (the small dot that appears when wires intersect properly).

**Buses** are groups of signals treated as a single drawing object. They're not electrical connections themselves—they're organizational tools. A bus line in Eeschema is purely visual; the actual connections happen when you attach individual wires from the bus to pins using bus wire entries. The bus label (e.g., `ADDR[0..15]`) must match the individual signal names (`ADDR0`, `ADDR1`, etc.) for the netlister to resolve them correctly.

The real power comes from combining these with **global labels** and **hierarchical labels**. Global labels connect nets across the entire project without visible wires. Hierarchical labels pass signals between sheets in a multi-page schematic. Understanding when to use a wire vs. a label vs. a bus is the difference between a readable schematic and a spaghetti mess.

## Key Commands / Configuration / Code

```bash
# Essential hotkeys in Eeschema (default KiCad 7/8 bindings)
# =========================================================
A          # Add symbol (opens component chooser)
W          # Start drawing a wire
B          # Start drawing a bus
E          # Edit properties of selected item (symbol, label, wire)
X          # Add bus wire entry (the diagonal line from bus to wire)
L          # Add a label (local net name)
Ctrl+H     # Add hierarchical label (for multi-sheet connections)
Ctrl+G     # Add global label (connects across entire project)
M          # Move item (preserves connections if wires attached)
Delete     # Delete item (does NOT delete connected wires)
```

```text
# Example: Creating a bus for an 8-bit data bus
# Steps:
# 1. Press B, click to start bus line, click to end
# 2. Press L to add label, type "D[0..7]" (note: square brackets, not parentheses)
# 3. Press X to add bus wire entry from bus to each pin
# 4. Press L on each bus wire entry wire, type "D0", "D1", ... "D7"
# The netlister will match D0..D7 to the bus label D[0..7] automatically

# Important: KiCad uses [ ] for bus ranges, not ( ) or { }
# Correct:  ADDR[0..15]
# Incorrect: ADDR(0:15)
# Incorrect: ADDR{0-15}
```

```text
# Configuring Electrical Rules Check (ERC) severity
# File -> Schematic Setup -> Electrical Rules
# Common settings for professional designs:
# - Unconnected passive pins: Warning (not error, since many resistors have unused pins)
# - Output pin connected to Output pin: Error (potential driver conflict)
# - Power input not driven: Error (floating VCC is a board killer)
# - No load on output: Warning (useful for finding unconnected op-amp outputs)
```

## Common Pitfalls & Gotchas

**1. Wire junctions are not automatic.** KiCad only creates a connection dot when a wire endpoint exactly touches another wire or pin. If you cross two wires without a junction dot, they are *not* connected. This is by design—it allows you to draw crossing wires that don't connect (common in bus routing). To force a junction, place a wire endpoint on top of another wire segment. If you need a junction at a crossing point, use the "Place Junction" tool (Shift+J) or ensure the wire ends precisely on the other wire.

**2. Bus signal names must match exactly.** If your bus is labeled `DATA[0..7]`, the individual wires must be labeled `DATA0`, `DATA1`, etc.—not `D0`, `D1`, or `data0`. The netlister does a string match, and case matters. I spent 20 minutes debugging a missing connection because I used `ADDR0` on the wire but `ADDR[0..15]` on the bus. The netlister silently dropped the mismatch.

**3. Global labels bypass hierarchy—use with caution.** A global label named `3V3` on sheet 1 connects to every other `3V3` global label in the project, regardless of sheet hierarchy. This is great for power rails but dangerous for control signals. I once had a `RESET` global label on a sub-sheet that inadvertently connected to the main sheet's `RESET` net, creating a feedback loop that the ERC didn't catch (because both were bidirectional). Use hierarchical labels for signals that should stay within a sheet boundary.

## Try It Yourself

1. **Build a bus-based memory interface.** Create a schematic with a microcontroller symbol and an SRAM symbol. Draw a bus labeled `ADDR[0..15]` between them. Add bus wire entries and individual labels for `ADDR0` through `ADDR15`. Run the ERC and verify no unconnected nets. Then change one label to `ADDR0` (lowercase) and watch the ERC flag it.

2. **Practice the hierarchy.** Create a two-sheet schematic. On sheet 1, place a connector symbol. On sheet 2, place a resistor and LED. Use hierarchical labels (Ctrl+H) to pass a signal named `LED_DRIVE` between sheets. Add a global label named `GND` on both sheets. Run the netlist export and inspect the `.net` file to see how global vs. hierarchical labels appear.

3. **Break the ERC on purpose.** Place two output pins (e.g., from two different op-amp symbols) and connect them with a wire. Run the ERC and observe the error. Then change one pin's electrical type to "Passive" in the symbol properties. Re-run ERC and note how the severity changes. This teaches you how pin types affect design rule checking.

## Next Up

Tomorrow, we'll move from placing symbols to creating them. I'll walk through the KiCad Symbol Editor (the tool behind the `A` key) and show you how to build a custom symbol from scratch—including proper pin placement, electrical type assignment, and how to make your symbols play nicely with the ERC. We'll also cover the difference between unit-based symbols (like a quad op-amp) and multi-part symbols (like a resistor array). See you then.
