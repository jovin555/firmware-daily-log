---
title: "Day 03: Creating Custom Symbols in KiCad Symbol Editor"
date: 2026-07-12
tags: ["til", "kicad", "symbol-editor", "custom-symbols"]
---

## What I Explored Today

Today I dove into the KiCad Symbol Editor (`eeschema`) to create custom schematic symbols from scratch. While KiCad ships with an extensive library (over 50,000 parts via the `kicad-symbols` package), real-world designs always demand custom parts—a specific voltage regulator with an exposed pad, a connector with non-standard pinout, or a complex FPGA with hundreds of pins. I walked through creating a multi-unit symbol for a dual operational amplifier, complete with hidden power pins, proper pin electrical types, and footprint association. The process is surprisingly ergonomic once you understand the editor's modal workflow and the underlying `.kicad_sym` file format.

## The Core Concept

A KiCad symbol is not a physical component—it's a logical representation of a part's pins and their electrical behavior. The symbol editor separates three concerns: **graphical appearance** (lines, arcs, text), **pin definitions** (name, number, electrical type, position), and **metadata** (datasheet link, footprint filter, fields). This separation is deliberate: you can reuse the same symbol with different footprints, or create hierarchical symbols where one symbol contains multiple units (e.g., a quad op-amp with four identical amplifier units).

The critical insight is that **pin electrical types matter for ERC (Electrical Rules Check)**. A `Passive` pin on a power supply output will not flag when connected to another output, but `Power Output` will. Getting these types wrong leads to false ERC errors or, worse, silent rule violations. The symbol editor enforces no constraints on pin placement—you can put a VCC pin in the middle of a logic gate—but convention dictates power pins go top, ground bottom, inputs left, outputs right.

## Key Commands / Configuration / Code

### Creating a New Symbol

```bash
# Launch symbol editor from KiCad project manager
# File > New Symbol (or Ctrl+N)
# Choose: "Create empty symbol" for full control
```

### Essential Hotkeys (Symbol Editor)

| Key | Action |
|-----|--------|
| `P` | Add pin (opens pin properties dialog) |
| `L` | Draw line (graphic, not electrical) |
| `A` | Add arc or circle |
| `T` | Add text (labels, notes) |
| `M` | Move item |
| `G` | Drag item (preserves connections) |
| `E` | Edit properties of selected item |
| `R` | Rotate 90° CW |
| `X` | Mirror horizontally |
| `Y` | Mirror vertically |
| `Del` | Delete selected |
| `Ctrl+Z` | Undo |

### Pin Properties Dialog Fields

When you press `P` and click to place a pin, the dialog requires:

```
Pin Name:   "IN+"          # Logical signal name
Pin Number: "3"            # Physical pin number (matches footprint pad)
Electrical Type: "Input"   # Critical for ERC: Input, Output, Bidirectional, 
                           # Power Input, Power Output, Open Collector, Passive, 
                           # Unspecified
Graphic Style: "Line"      # Line, Inverted, Clock, Inverted Clock, 
                           # Low Level In, Low Level Out
Orientation: "Right"       # Direction pin points (Right=output, Left=input)
Length: "200"              # mils (default 200, can be 100-300 typical)
```

### Multi-Unit Symbol Setup

For a dual op-amp (e.g., LM358), configure in Symbol Properties:

```
# Symbol Properties > Symbol Units
Number of units: 2
Unit name style: "Unit A, Unit B"  # or "1, 2"
# Check: "Units are interchangeable" (ERC will allow swapping)
# Check: "Show pin numbers by side" (pins on body edge)
```

Then create each unit separately using the unit selector dropdown (top toolbar). Unit 1 gets pins 1,2,3; Unit 2 gets pins 5,6,7. The power pins (4=VCC, 11=GND) go on a **power unit** (Unit 0) that is always visible.

### Hidden Power Pins

```yaml
# In pin properties for power unit:
Pin Name:   "VCC"
Pin Number: "4"
Electrical Type: "Power Input"
# Check: "Visible" = NO (hidden)
# Check: "Connect to power symbol" = YES (auto-connects to net VCC)
```

### Footprint Association

```
# Symbol Properties > Footprint Filters
Add filter: "SOIC*8*"       # Matches any SOIC-8 footprint
Add filter: "DIP*8*"        # Matches any DIP-8 footprint
# Then assign default footprint:
# Symbol Properties > Footprint field
# Value: "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
```

### Exporting to Library

```bash
# File > Save to Library
# Choose existing library or create new:
# Preferences > Manage Symbol Libraries
# Add new library: "custom.kicad_sym" (KiCad 7+ format)
# Save symbol into that library
```

## Common Pitfalls & Gotchas

1. **Pin number mismatch with footprint**: The most common ERC failure. Your symbol pin "3" must match pad "3" on the footprint. KiCad does not auto-validate this. Always cross-reference the datasheet pinout diagram against both your symbol and the chosen footprint. I once spent an hour debugging a regulator that wouldn't power up because I swapped the enable and feedback pins.

2. **Hidden power pins without global net labels**: If you hide VCC/GND pins but don't have a global power label (e.g., `PWR_FLAG`) on the schematic, ERC will report "Input pin not driven." Always place `PWR_FLAG` symbols on your power nets. Alternatively, set the hidden pin's electrical type to `Power Input` and ensure the net is driven elsewhere.

3. **Forgetting to set "Units are interchangeable"**: For multi-unit symbols like op-amps or logic gates, if you don't check this box, ERC will flag an error if you swap which unit instance drives which net. The default is unchecked, so you must explicitly enable it for interchangeable parts.

4. **Pin graphic style confusion**: The "Inverted" style (bubble) is purely cosmetic—it does not change the electrical type. A pin with `Electrical Type: Input` and `Graphic Style: Inverted` is still an input, not an active-low input. Use the electrical type for ERC, the graphic style for readability.

## Try It Yourself

1. **Create a 2-pin header symbol**: Make a simple CONN_02 with pins 1 and 2, electrical type `Passive`. Add a footprint filter for `PinHeader_1x02_P2.54mm`. Save to a custom library. Place it in a schematic and run ERC—it should pass with no warnings.

2. **Build a dual op-amp with power unit**: Create a 3-unit symbol (Unit A, Unit B, Power Unit). Unit A: pins 1 (OUT), 2 (IN-), 3 (IN+). Unit B: pins 7 (OUT), 6 (IN-), 5 (IN+). Power Unit: pin 4 (VCC, hidden), pin 11 (GND, hidden). Set electrical types correctly. Verify ERC passes when you place both op-amp instances and connect power.

3. **Add a custom field for ordering**: Open your symbol properties, add a field named `MPN` (Manufacturer Part Number) with value `LM358P`. Add a field `Digikey` with a URL. These fields propagate to the BOM and can be used in automated ordering scripts.

## Next Up

Tomorrow I'll tackle **Hierarchical Sheets & Multi-Sheet Schematics**. When your design outgrows a single A3 sheet—say a 12-layer board with separate power, analog, digital, and FPGA sections—hierarchical sheets let you decompose the schematic into manageable blocks. I'll cover sheet symbols, hierarchical labels, and how to pass global nets between sheets without creating a rat's nest of wires.
