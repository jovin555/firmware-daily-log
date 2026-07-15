---
title: "Day 06: Footprint Editor: Custom Footprints & 3D Models"
date: 2026-07-15
tags: ["til", "kicad", "footprint-editor", "3d-models"]
---

## What I Explored Today

Today I dove deep into the KiCad Footprint Editor to understand how to create custom footprints from scratch and pair them with 3D models. After wrestling with a non-standard connector that had no existing library footprint, I realized that mastering the Footprint Editor is essential for any real-world PCB design. I walked through the entire workflow: setting grid and precision, placing pads with exact coordinates, drawing the courtyard and silkscreen, and finally attaching a STEP file for mechanical visualization. This isn't just about making something that looks right—it's about creating a footprint that passes DRC, aligns with the datasheet, and gives your mechanical team a correct 3D representation.

## The Core Concept

A footprint is the physical land pattern that connects your schematic symbol to the copper on the PCB. But it's more than just pad positions. A proper footprint includes:

- **Pads**: Copper lands with defined shape, size, drill hole, and layer assignment (SMD or through-hole).
- **Courtyard**: A keep-out zone that prevents other footprints from overlapping. KiCad uses a `F.Courtyard` and `B.Courtyard` layer.
- **Silkscreen**: Visual reference for assembly—outline of the component body, pin-1 indicator, and reference designator.
- **3D Model**: A mechanical representation (STEP, WRL, or X3D) that integrates with the PCB's 3D viewer and can be exported for mechanical CAD.

The *why*: Custom footprints are inevitable. You'll encounter parts with non-standard pitch, odd-shaped pads (e.g., thermal pads with multiple vias), or components from small manufacturers that don't provide KiCad libraries. Knowing how to build them correctly saves hours of debugging later—especially when your assembler rejects a board because the silkscreen overlaps a pad or the courtyard is too tight.

## Key Commands / Configuration / Code

### 1. Launching the Footprint Editor
```bash
# From KiCad main window, click the Footprint Editor icon (the chip with a pencil)
# Or use the keyboard shortcut: Ctrl+Shift+F
# Or from command line:
kicad --footprint-editor
```

### 2. Setting Up a New Footprint
```text
File → New Footprint (or Ctrl+N)
  - Name: "Connector_2x05_P2.54mm_THT"  (use KiCad naming convention)
  - Library: Select or create a custom library (e.g., "my_custom.pretty")
  - Pad count: 10 (for a 2x5 header)
```

### 3. Placing Pads with Precision
```text
# Set grid to 2.54 mm (100 mil) for through-hole headers
# Use 'Add Pad' tool (shortcut: P)

# For a DIP-8 footprint (example):
# Pad 1: Position (0, 0) — origin at pin 1
# Pad 2: Position (2.54, 0)
# Pad 3: Position (2.54, 2.54)
# Pad 4: Position (0, 2.54)
# Pad 5: Position (0, 5.08)
# Pad 6: Position (2.54, 5.08)
# Pad 7: Position (2.54, 7.62)
# Pad 8: Position (0, 7.62)

# To set pad properties precisely:
# Right-click pad → Properties (or double-click)
# Set:
#   - Pad number: "1"
#   - Pad type: Through-hole
#   - Shape: Circle
#   - Size X/Y: 1.8 mm (drill: 0.9 mm for standard DIP)
#   - Position X/Y: 0, 0
```

### 4. Drawing the Courtyard and Silkscreen
```text
# Courtyard (F.Courtyard layer):
# Use 'Add Graphic Line' (shortcut: L)
# Draw a rectangle around the component body with 0.25 mm clearance
# Set line width to 0.05 mm

# Silkscreen (F.Silkscreen layer):
# Draw component outline (usually 0.12 mm line width)
# Add pin-1 indicator: small circle or chamfered corner
# Add reference designator text: "REF**" (KiCad auto-fills this)
#   - Text size: 1.0 mm
#   - Line width: 0.15 mm
```

### 5. Attaching a 3D Model
```text
# In Footprint Editor:
# File → Footprint Properties → 3D Models tab
# Click '+' to add a model
# Browse to your .step or .wrl file
# Set offset and rotation if needed (e.g., rotate 90° around Z-axis)

# Example for a vertical USB connector:
# Model: "usb_a_vertical.step"
# Offset: X=0, Y=0, Z=0
# Rotation: X=0, Y=0, Z=90
```

### 6. Exporting/Importing Footprints
```bash
# Export single footprint to a file:
# File → Export → Footprint to File... → saves as .kicad_mod

# Import:
# File → Import → Footprint from File...
```

## Common Pitfalls & Gotchas

1. **Courtyard too tight or missing**: The DRC (Design Rule Check) uses the courtyard to detect overlapping components. If you omit it or make it too small, you'll get false positives or miss real collisions. Always leave at least 0.25 mm clearance from the component body outline.

2. **Pad numbering mismatch with schematic symbol**: This is the #1 cause of "rats nest" errors. If your schematic symbol has pin 1 on the top-left but your footprint has it on the bottom-right, the netlist will connect wrong pins. Always verify pin mapping against the datasheet before saving.

3. **3D model orientation wrong**: STEP files often come with arbitrary orientation. Use the 3D viewer (Alt+3) to check alignment. A common fix is rotating 90° or 180° around the Z-axis. Also, ensure the model's origin matches the footprint origin—otherwise it floats in space.

4. **Silkscreen overlapping pads**: This causes solder defects. KiCad's DRC checks this, but only if you run it. Set silkscreen line width to 0.12 mm and keep outlines at least 0.2 mm from pad edges.

## Try It Yourself

1. **Create a 2x5 pin header footprint**: Use the steps above. Set grid to 2.54 mm, place 10 through-hole pads with 1.8 mm diameter and 0.9 mm drill. Draw a rectangular courtyard 0.25 mm outside the pad edges. Add silkscreen outline and pin-1 dot. Save to a custom library.

2. **Attach a 3D model to an existing footprint**: Open the `PinHeader_2x05_P2.54mm_Vertical` footprint from the KiCad library. Download a matching STEP file from a vendor (e.g., Samtec). Use the 3D Models tab to attach it, then verify alignment in the 3D viewer.

3. **Create a footprint for a QFN-32 package**: Set grid to 0.5 mm. Place 32 SMD pads (0.3 mm x 0.8 mm) around the perimeter with a 2.0 mm x 2.0 mm thermal pad in the center. Add a 0.2 mm wide courtyard. This is a common challenge for custom MCU designs.

## Next Up

Tomorrow we'll tackle **Assigning Footprints & Netlist Generation**—the critical bridge between your schematic symbols and the physical board. You'll learn how to map symbols to footprints, resolve missing footprint warnings, and generate the netlist that drives the PCB layout. This is where your design starts becoming real.
