---
title: "Day 08: Component Placement Strategy: Grouping, Orientation & Test Points"
date: 2026-07-17
tags: ["til", "pcb-design", "placement", "test-points"]
---

## What I Explored Today

Today I dug into the often-underestimated art of component placement—the single highest-leverage activity in PCB layout. A bad placement guarantees a nightmare routing session; a good one makes routing almost trivial. I focused on three pillars: functional grouping (keeping related circuitry together), orientation discipline (consistent part rotation for assembly and thermal symmetry), and test point integration (designing for debug from day one, not as an afterthought). I also validated these strategies against real DFM (Design for Manufacturability) and DFT (Design for Test) guidelines from IPC-7351 and common CM (Contract Manufacturer) checklists.

## The Core Concept

Placement is not "where do the parts fit?"—it's "how do signals flow?" Every component is a node in a signal chain, and its physical location defines the parasitic inductance, capacitance, and return path quality for that node. The goal is to minimize the loop area of every critical current path while keeping the board manufacturable and testable.

**Grouping** means placing components by function, not by schematic page order. A buck converter's input cap, inductor, output cap, and feedback divider must form a tight cluster—the switching loop area directly determines EMI. A microcontroller, its decoupling caps, and its crystal oscillator form another cluster. Crossing these groups with long traces invites crosstalk.

**Orientation** matters for two reasons: assembly yield and thermal symmetry. All polarized components (electrolytic caps, diodes, connectors) should face the same direction on a given side of the board—this prevents tombstoning during reflow and makes visual inspection faster. For high-speed differential pairs (USB, HDMI), both traces must have identical lengths and impedance, which is impossible if the source and load components are rotated 90° relative to each other.

**Test points** are the most commonly skipped step. Engineers tell themselves "I'll add them later" and then never do. The result: a board that passes functional test but fails in-system because you can't probe the SPI bus or measure the 3.3V rail under load. Test points must be placed on a single side (preferably bottom), spaced for probe clearance (100-mil minimum center-to-center), and connected to nets that are *not* already accessible via a header or connector.

## Key Commands / Configuration / Code

In KiCad 8, I use the following workflow for placement-driven grouping:

```python
# KiCad Python scripting: group components by reference prefix
# Run from pcbnew in KiCad's Python console

import pcbnew

board = pcbnew.GetBoard()
group_map = {
    "PWR": ["C", "L", "U"],   # power: caps, inductors, regulators
    "DIG": ["U", "R", "C"],   # digital: ICs, pull-ups, decoupling
    "ANA": ["U", "R", "C"],   # analog: op-amps, precision resistors
}

for footprint in board.GetFootprints():
    ref = footprint.GetReference()
    prefix = ref[0]
    for group_name, prefixes in group_map.items():
        if prefix in prefixes:
            footprint.SetPosition(pcbnew.VECTOR2I(0, 0))  # placeholder
            # In practice, move to a pre-defined group zone
            break
```

For orientation constraints in Altium, I use the PCB Rules and Constraints Editor:

```
Rule: ComponentOrientation
Scope: All components
Constraints:
  - Rotation: 0°, 90°, 180°, 270° only
  - For polarized parts (Capacitor, Diode, LED):
      Allowed rotations: 0° or 180° (consistent polarity)
```

For test point creation in KiCad, I add a dedicated footprint:

```python
# Add a test point via footprint assignment
# Footprint: TestPoint:TestPoint_2mm_Pad_D1.0mm

footprint = pcbnew.FootprintLoad(
    "TestPoint", "TestPoint_2mm_Pad_D1.0mm"
)
footprint.SetReference("TP101")
footprint.SetValue("TP101")
footprint.SetPosition(pcbnew.VECTOR2I(100000000, 80000000))  # 100mm, 80mm
board.Add(footprint)
```

For Allegro users, the `place` command with auto-grouping:

```
# Allegro placement script snippet
place refdes "C1" "C2" "C3" -group "DECOUPLING" -origin 1000 2000
place refdes "U1" -group "MCU" -origin 3000 2000
place refdes "Y1" -group "MCU" -origin 3200 1800
```

## Common Pitfalls & Gotchas

1. **Placing decoupling caps too far from IC pins.** A 0.1µF cap 10mm from a VDD pin is nearly useless above 10 MHz—the trace inductance (≈10 nH/inch) creates a resonant tank that actually amplifies noise. Rule of thumb: cap center within 2mm of the pin, with a via directly to the power plane *between* cap and IC, not on the far side of the cap.

2. **Ignoring test point clearance for probes.** A standard oscilloscope probe tip is 0.5mm diameter, but the ground clip adds 5mm of metal. If you place test points on 50-mil centers, you can't clip two probes simultaneously. Always use 100-mil (2.54mm) minimum spacing, and keep test points at least 200 mils from tall components (connectors, heatsinks) that block probe access.

3. **Rotating connectors 180° from the board edge.** A USB connector facing inward forces the cable to bend 180° around the board edge, causing mechanical stress and eventual failure. Always orient connectors so the cable exits directly away from the board edge, and add a strain relief footprint (two mounting holes) within 5mm of the connector body.

## Try It Yourself

1. **Group your last design by function.** Open a board you've already routed. Create three colored zones on the silkscreen: red for power, blue for digital, green for analog. Count how many traces cross zone boundaries. If more than 20% of your critical signals cross zones, re-place the components to minimize those crossings.

2. **Add test points to a single net.** Pick the 3.3V rail and the SPI clock line in your design. Add a 100-mil test point footprint (e.g., Keystone 5000 series) within 500 mils of the source IC. Verify in 3D view that no tall component blocks probe access from the top or bottom side.

3. **Audit orientation consistency.** Run a DRC rule that flags any polarized component (electrolytic cap, diode, LED) rotated more than 90° from the majority orientation. In KiCad, use the `drill` and `footprint` inspection tools; in Altium, use the PCB Filter to select all polarized parts and check their rotation property.

## Next Up

Tomorrow: **Via Types: Through-Hole, Blind, Buried & Via-in-Pad** — when to use each, how they affect layer stackup cost, and why via-in-pad can save your high-speed design (or ruin your assembly yield).
