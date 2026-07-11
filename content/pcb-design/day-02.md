---
title: "Day 02: Schematic Capture Best Practices: Nets, Hierarchical Sheets & Annotations"
date: 2026-07-11
tags: ["til", "pcb-design", "schematic", "nets"]
---

## What I Explored Today

Yesterday we laid out the PCB design workflow. Today I dove into the schematic capture phase—specifically how to manage connectivity, organize complexity, and keep the design database sane. I focused on three pillars: net labeling conventions, hierarchical sheet decomposition, and annotation strategies. These aren't just "nice to have"; they determine whether your design review is a productive discussion or a painful hunt for floating nets and unlabeled buses.

## The Core Concept

A schematic is not a drawing—it's a **database of connectivity**. Every wire, net label, and off-page connector is a relationship that the EDA tool uses to generate the netlist, which then drives the layout and BOM. If your schematic is ambiguous, the netlist will be wrong, and the board will fail.

The key insight: **nets are the atoms of your design**. A net is a single electrical node—a continuous copper path. When you place a net label like `3V3`, you're telling the tool that every pin connected to that label is the same node. This is fundamentally different from drawing a wire across the page. Wires are visual; net labels are logical.

Hierarchical sheets solve the problem of "one giant flat schematic." Instead of scrolling through 50 pages of spaghetti, you decompose the design into functional blocks (power, MCU, sensors, connectors). Each block gets its own sheet, and you connect them via hierarchical ports. This mirrors how firmware engineers use functions—encapsulation and clear interfaces.

Annotation is the process of assigning unique reference designators (like `R1`, `C5`, `U2`) to every component. You *must* do this before generating the netlist. The order matters: annotate after you're done placing components, not before. Re-annotating later breaks your BOM cross-references.

## Key Commands / Configuration / Code

Here are the practical commands and patterns I use daily in KiCad (v8+), but the concepts apply to Altium, Eagle, or OrCAD.

### Net Labeling (KiCad)

```text
# Place a global net label (same net across all sheets)
Place → Net Label (or press 'L')
# Type the net name: e.g., I2C_SCL, SPI_MOSI, VBAT

# For buses (groups of nets)
Place → Bus (or press 'B')
# Then place bus entries for each member
# Bus label syntax: I2C[0..3]  or  DATA[7..0]

# Power symbols are special global nets
Place → Power Port → select VCC, GND, 3V3
# These are automatically global—no label needed
```

### Hierarchical Sheets (KiCad)

```text
# Create a hierarchical sheet
Place → Hierarchical Sheet (or press 'S')
# Name it: e.g., "Power_Regulation"
# Assign a file name: "power_regulation.sch"

# Add hierarchical ports to the sheet
Place → Hierarchical Pin → choose type:
  - Input: signal coming INTO this sheet
  - Output: signal leaving this sheet  
  - Bidirectional: for data buses

# On the child sheet, place corresponding
# hierarchical labels (same name, same type)
Place → Hierarchical Label
```

### Annotation (KiCad)

```text
# After all components are placed:
Tools → Annotate Schematic (or press Ctrl+A)

# Settings I use:
# - Order: "Sort by X position" (left-to-right, top-to-bottom)
# - Keep existing annotations: UNCHECKED (for first pass)
# - Reset all: CHECKED (clean slate)

# For incremental changes (adding one resistor):
# Check "Keep existing annotations" 
# Then "Annotate" — it only assigns new refdes to new parts
```

### Netlist Generation

```text
# After annotation, generate the netlist
Tools → Generate Netlist File (or press Ctrl+N)

# Format: KiCad netlist (default)
# This file feeds into the PCB layout tool
# Always verify: no "unconnected" warnings
```

## Common Pitfalls & Gotchas

**1. Mixing local and global net labels.** If you use `VCC` as a power symbol on one sheet and `VCC` as a regular net label on another, the tool may treat them as different nets. Always use power symbols for power rails—they're inherently global. Regular net labels are local to their sheet unless you explicitly mark them global.

**2. Forgetting to annotate before netlist generation.** This is the #1 rookie mistake. You'll get errors like "Component U? has no reference." The fix: annotate, then generate netlist. Every time. I've seen engineers waste an hour debugging a netlist only to realize they skipped annotation.

**3. Overusing hierarchical sheets.** If your "power" sheet has three components and one connector, don't make it hierarchical. Flat is fine for small designs. Hierarchical sheets add overhead (port matching, file management). Use them when a functional block has more than 10-15 components or when you need to reuse the same block multiple times (e.g., four identical motor driver channels).

## Try It Yourself

1. **Net label audit:** Open an existing schematic. Find every net label that isn't a power symbol. Verify that each label is either local (used only on one sheet) or explicitly global. Fix any mismatches.

2. **Hierarchical decomposition:** Take a flat schematic with 5+ pages. Identify three functional blocks (e.g., power, MCU, sensors). Create hierarchical sheets for each, using ports for all inter-block signals. Verify the netlist still matches the original.

3. **Annotation order experiment:** Create a schematic with 10 resistors. Annotate them in "Sort by X position" order. Then re-annotate with "Sort by Y position." Compare the resulting reference designators. Which ordering makes more sense for your board's physical layout?

## Next Up

Tomorrow: **Component Footprints & Land Patterns: IPC-7351 Standards** — we'll cover how to select the right footprint, why IPC-7351 matters for manufacturability, and how to avoid the most common land pattern mistakes that cause tombstoning and solder bridges.
