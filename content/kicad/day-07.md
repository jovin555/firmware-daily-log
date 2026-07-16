---
title: "Day 07: Assigning Footprints & Netlist Generation"
date: 2026-07-16
tags: ["til", "kicad", "netlist", "footprint-assignment"]
---

## What I Explored Today

Today I bridged the gap between schematic capture and PCB layout by assigning physical footprints to every symbol in my design, then generating a netlist that tells the PCB editor exactly how everything connects. I worked through the Footprint Assignment tool (`Tools → Assign Footprints`), resolved missing footprint warnings, and verified my netlist before moving to layout. This step is where abstract logic becomes a real board—every resistor, capacitor, and connector gets a specific land pattern, and every net gets a name that will drive routing.

## The Core Concept

A schematic symbol is just a logical representation: it shows a resistor with two pins, but it doesn't say whether that resistor is 0402, 0603, or through-hole. The footprint is the physical land pattern—the copper pads, silkscreen outline, and 3D model that define how the component mounts on the board. Assigning footprints is the process of mapping each symbol to its physical counterpart.

The netlist is the bridge between these two worlds. It's a structured file (typically in KiCad's `.net` format) that lists every component, its footprint, and every electrical connection (net) between pins. The PCB editor (Pcbnew) reads this netlist to know which pads should be connected by copper traces. Without a correct netlist, your PCB layout will be disconnected from your schematic intent—a recipe for a dead board.

Why does this matter? Because a single footprint mismatch can break an entire design. If you assign a 0.5mm-pitch QFP footprint to a part that actually has 0.65mm pitch, every pin will be misaligned. If you forget to assign a footprint at all, the netlist will fail to generate, and you'll waste time debugging why Pcbnew shows no components. This step forces you to think about real-world component availability, package dimensions, and manufacturability before you lay a single trace.

## Key Commands / Configuration / Code

### Launching the Footprint Assignment Tool
From the schematic editor (Eeschema):
```
Tools → Assign Footprints   (or press Ctrl+Shift+F)
```
This opens a dialog showing all symbols in your design. Each symbol must have a footprint assigned (green checkmark) or you'll see a red warning.

### Assigning a Footprint
In the dialog, select a symbol (e.g., `R1` for a 10kΩ resistor). Click the footprint library browser button (folder icon). Filter by keyword, e.g., `Resistor_SMD:R_0603_1608Metric`. Double-click to assign.

**Example: Assigning a common 0603 resistor:**
```
Footprint: Resistor_SMD:R_0603_1608Metric
Library path: /usr/share/kicad/footprints/Resistor_SMD.pretty
```

**Example: Assigning a through-hole capacitor:**
```
Footprint: Capacitor_THT:CP_Radial_D5.0mm_P2.50mm
```

### Generating the Netlist
After all footprints are assigned, generate the netlist:
```
Tools → Generate Netlist File   (or click the netlist icon)
```
In the dialog, ensure the "Pcbnew" tab is selected. Click "Generate Netlist" and save as `project.net`. The file format is plain text—you can inspect it:

```netlist
(export (version D)
  (design
    (source "project.kicad_sch")
    (date "2026-07-16 09:30:00")
    (tool "Eeschema 8.0"))
  (components
    (comp (ref R1)
      (value 10k)
      (footprint "Resistor_SMD:R_0603_1608Metric")
      (datasheet "https://www.yageo.com/..."))
    (comp (ref C1)
      (value 100nF)
      (footprint "Capacitor_SMD:C_0603_1608Metric")
      (datasheet "")))
  (nets
    (net (code 1) (name "GND")
      (node (ref R1) (pin 2))
      (node (ref C1) (pin 2)))
    (net (code 2) (name "VCC")
      (node (ref R1) (pin 1))
      (node (ref C1) (pin 1)))))
```

### Verifying the Netlist
Before closing the dialog, click "Check Netlist" to validate. KiCad will report any unassigned footprints, duplicate reference designators, or missing pins. Fix all errors before proceeding.

### Updating PCB from Schematic
Once in Pcbnew, use:
```
Tools → Update PCB from Schematic   (or press F8)
```
This reads the netlist and places components (initially stacked) in the layout area.

## Common Pitfalls & Gotchas

1. **Mismatched pin counts between symbol and footprint.** A symbol might have 8 pins, but the footprint you assign has 10 pads. KiCad will warn you, but if you ignore it, the netlist will map pins incorrectly. Always verify pin count in the footprint preview (bottom of the assignment dialog).

2. **Forgetting to assign footprints to all symbols.** The netlist generator will refuse to create a valid file if any symbol lacks a footprint. The error message is clear: "No footprint assigned to component U1." Don't skip this—it's not optional.

3. **Using the wrong footprint variant.** A common mistake: assigning a `QFP-44` footprint to a `TQFP-44` part. The pitch might be the same (0.8mm), but the body size differs. Always cross-reference the datasheet's package drawing with the footprint dimensions. KiCad's footprint viewer (`Tools → Footprint Editor`) lets you measure pad spacing.

## Try It Yourself

1. **Assign footprints to a simple LED + resistor circuit.** Use `LED_SMD:LED_0603_1608Metric` for the LED and `Resistor_SMD:R_0603_1608Metric` for the resistor. Generate the netlist and inspect the `.net` file—notice how the net names match your schematic labels.

2. **Deliberately assign a wrong footprint.** Give a 2-pin resistor a 3-pin footprint (e.g., `Package_TO_SOT_SMD:SOT-23`). Generate the netlist and observe the error. Then fix it and re-validate.

3. **Export the netlist and manually edit it.** Change a component's footprint reference to a non-existent library path. Re-import into Pcbnew and watch the error. This teaches you how KiCad resolves footprint paths and why library management matters.

## Next Up

Tomorrow, I'll open Pcbnew and dive into the PCB Editor: setting up layers (copper, silkscreen, solder mask), defining board outlines and edge cuts, and creating power/ground zones. The netlist we generated today will finally come to life on a physical board.
