---
title: "Day 20: Full Review & Project: Design a Complete Board in KiCad from Schematic to Gerbers"
date: 2026-07-31
tags: ["til", "kicad", "review", "project"]
---

## What I Explored Today

Today is the capstone of this series. Over the past 19 days, we've covered schematic capture, symbol and footprint creation, PCB layout, routing, copper pours, silkscreen, and design rule checking. Today, I pulled all of that together into a single, complete workflow: taking a fresh schematic from a blank canvas all the way to manufacturing-ready Gerber files. The goal was to time myself, note every friction point, and produce a board that passes ERC, DRC, and generates clean outputs. I chose a simple but non-trivial design: an STM32F030F4P6 breakout with an LDO, a status LED, and a USB-C connector for power and UART. This exercise forces you to confront the *integration* of all the individual skills—not just the mechanics of each tool.

## The Core Concept

The real skill in KiCad isn't knowing where the "Add Symbol" button is. It's understanding the **data flow** and the **constraints** that propagate through the design. Every decision you make upstream—pin assignment, footprint selection, net naming—has downstream consequences. A resistor value chosen for a pull-up affects the schematic's readability. A footprint's courtyard size affects the board's density. A net name like `VBUS` vs `+5V` affects your ability to read the layout later. The complete workflow forces you to think in terms of *state transitions*: schematic → netlist → board → routed board → manufacturing outputs. Each transition is a checkpoint where errors are either caught or propagated. The most efficient engineers I know treat each transition as a gate: nothing moves forward until the current stage is clean. This is why I always run ERC *before* generating the netlist, and DRC *before* generating Gerbers. It's not about catching every error—it's about preventing error *amplification*.

## Key Commands / Configuration / Code

Here's the exact sequence I used, with the commands that matter.

**1. Schematic Setup and Annotation**

```bash
# Start with a project, not a blank file
kicad-cli sch export netlist --output board.net board.kicad_sch

# Annotate symbols (C, R, U, etc.) in order
# In GUI: Tools > Annotate Schematic > "Annotate all symbols"
# Use "Numbering scheme: Sheet number + X" for multi-sheet clarity
```

**2. The Critical ERC Check**

```bash
# Run ERC from the command line to catch unconnected pins and power issues
kicad-cli sch erc --output erc.rpt board.kicad_sch

# Look for these specific error codes:
# ErrType(3): Unconnected pin
# ErrType(4): Power pin not driven
# ErrType(5): Output pin connected to output pin
```

**3. Board Setup and Import**

```bash
# Import netlist into PCB editor
# In GUI: Tools > Update PCB from Schematic (F8)
# Critical: Set board outline FIRST via Edge.Cuts layer
# Use: Draw > Rectangle, then Edit > Set Board Outline

# Set design rules before routing
# In GUI: Board Setup > Design Rules > Constraints
# Typical: Clearance 0.2mm, Track Width 0.25mm (signal), 0.5mm (power)
# Via: 0.6mm drill, 1.0mm pad
```

**4. Routing and Copper Pour**

```bash
# Route critical nets manually first: power, ground, crystal, USB
# Use interactive router (X) for differential pairs if needed

# Add copper pour on both layers
# In GUI: Add Filled Zone (B) > Select layer (F.Cu/B.Cu) > Net: GND
# Set "Pad Connection" to "Solid" for thermal relief on small pads
# Set "Zone Clearance" to 0.3mm for pour-to-track spacing

# After routing, fill zones:
# In GUI: Edit > Fill All Zones (B)
```

**5. DRC and Gerber Generation**

```bash
# Run DRC from CLI for a clean report
kicad-cli pcb drc --output drc.rpt board.kicad_pcb

# Generate Gerbers (RS-274X) and drill files
kicad-cli pcb export gerbers --output gerber/ board.kicad_pcb
kicad-cli pcb export drill --output gerber/ board.kicad_pcb

# Generate a 3D render to visually verify
kicad-cli pcb render --output render.png board.kicad_pcb
```

**6. The Final Gate: Gerber Viewer**

```bash
# Load Gerbers into a viewer (I use gerbv on Linux)
gerbv gerber/*.gbr

# Check: All layers present, no missing silkscreen, no copper slivers
# Verify drill file matches pad sizes
```

## Common Pitfalls & Gotchas

**1. The "Silent" Netlist Mismatch.** When you update the PCB from the schematic, KiCad will happily add new footprints but *will not* remove old ones that no longer exist in the netlist. If you delete a component from the schematic and forget to run "Update PCB" with the "Remove unused footprints" checkbox, you'll have phantom copper on your board. Always run the update with "Delete Stale Footprints" enabled.

**2. Zone Fill Order Matters.** If you have multiple zones (e.g., GND on both layers), the fill order affects thermal relief and clearance. KiCad fills zones in the order they were created. If you create a GND zone on the bottom layer *after* routing a signal on the top, the bottom zone will not automatically avoid the top-layer tracks. Always fill zones *last*, after all routing is complete, and re-fill after any track edit.

**3. Silkscreen Reference Designators.** By default, KiCad places reference designators (R1, C2) at the footprint origin. For small SMD parts, this often overlaps the pad or is unreadable. I always manually reposition them to the top-left corner of the component, rotated 90 degrees for vertical parts. This is a 10-minute task that makes your board look professional and prevents assembly errors.

## Try It Yourself

1. **Take a previous design from this series** (e.g., the LED blink board from Day 5) and run the complete workflow: ERC → netlist → PCB import → route → DRC → Gerbers. Time yourself. Note where you spend the most time. That's your bottleneck.

2. **Create a new project from scratch** with a single IC (e.g., an ATtiny85) and a few passives. Force yourself to use only keyboard shortcuts (E for edit, R for rotate, X for route, V for via). No mouse clicks on menus. This will dramatically speed up your workflow.

3. **Generate Gerbers and load them into an external viewer** (gerbv, or a free online Gerber viewer). Check for: missing silkscreen text, copper slivers, and drill holes that don't align with pads. Fix any issues and regenerate. This is your final quality gate before sending to a fab.

## Next Up

Tomorrow is the full review: a deep dive into the entire 20-day series. I'll compile the most common mistakes, the best shortcuts, and a checklist you can use for *any* KiCad project. We'll also look at advanced topics we didn't cover—like hierarchical sheets, bus routing, and custom DRC rules—and decide if they deserve a follow-up series. See you then.
