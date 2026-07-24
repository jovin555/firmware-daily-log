---
title: "Day 15: Connectors & Mechanical Considerations in PCB Layout"
date: 2026-07-24
tags: ["til", "pcb-design", "connectors", "mechanical"]
---

## What I Explored Today

Today I dove into the mechanical side of PCB layout—specifically how connectors and physical constraints dictate board success. It’s easy to focus on signal integrity and power delivery, but a board that doesn’t fit its enclosure, has connectors that shear off under cable strain, or fails thermal cycling is a board that never ships. I explored connector footprint selection, mounting hole placement, keep-out zones, and the critical interplay between the PCB outline, component height, and mating cycles. This is where the schematic meets the real world of screws, cables, and hands.

## The Core Concept

Connectors are the weakest mechanical link in any PCB assembly. They transfer forces from cables, panels, and user interaction directly into solder joints and copper pads. If you don’t design for those forces, you’ll see lifted pads, cracked solder joints, or connectors that simply pull off.

The why is simple: a connector’s electrical performance is meaningless if it physically fails. Mechanical considerations include:

- **Strain relief**: Cable ties, right-angle exits, and mounting ears reduce stress on solder joints.
- **Keep-out zones**: No components under or near connectors where mating cables or hands might collide.
- **Mounting hole placement**: Connectors with integrated mounting ears need corresponding PCB holes, and those holes must be tied to chassis ground (or left isolated) with proper clearance.
- **Board-to-board alignment**: Stacked connectors (e.g., mezzanine, board-to-board) require tight tolerance on board edge placement and connector height matching.
- **Thermal expansion**: Large connectors (e.g., D-sub, USB-C) can exert force on the board during reflow and in operation.

The golden rule: **always prototype the mechanical fit before finalizing the layout.** A 0.5 mm offset in a connector’s mounting hole can make the entire assembly unusable.

## Key Commands / Configuration / Code

Below are practical KiCad and Altium settings I use daily for connector mechanical design. Adjust for your EDA tool.

### KiCad: Adding Mounting Holes with Mechanical Layers

```kicad
# In PCB Editor, use the "Add Footprint" tool (hotkey 'A')
# Search for "MountingHole" or "MountingHole_3.2mm"
# Place on the mechanical layer (typically User.Comments or Dwgs.User)

# To define a keep-out zone around a connector:
# 1. Switch to "Edge.Cuts" layer
# 2. Draw a polygon around the connector area (e.g., 5mm clearance)
# 3. Assign a "keepout" rule via the Design Rules > Custom Rules

# Example custom rule for connector keep-out:
(rule "connector_keepout"
  (layer "F.Cu")
  (condition "A.zone == 'connector_zone'")
  (constraint clearance (min 2.0mm)))
```

### Altium: Mechanical Layer Setup for Connector Clearance

```altium
# In PCB Editor, go to Design > Board Layers & Colors
# Enable "Mechanical Layer 1" and rename to "Connector Keepout"
# Set layer type to "Mechanical" (not signal)

# To define a keep-out region:
# Place > Keepout > Solid Region (shortcut: P, K, R)
# Draw polygon on "Connector Keepout" layer
# In properties, set "Layer" to "Connector Keepout" and "Keepout Type" to "All"

# For mounting holes:
# Place > Pad (shortcut: P, P)
# Set hole size to 3.2mm (for M3 screw), pad diameter to 6.0mm
# Set layer to "Multi-Layer" (plated through-hole)
# Add a mechanical attribute: Parameters > Add > "MountingHole" = "True"
```

### 3D Step Model Export for Mechanical Fit Check

```bash
# KiCad: File > Export > Step
# Ensure "Board Body" and "Components" are checked
# Export with "Overwrite existing files" and "Use board color"

# Altium: File > Export > STEP 3D
# Select "Export board outline" and "Export components as solids"
# Set "Tolerance" to 0.01mm for accurate fitment
```

### Gerber X2 for Mechanical Layers (Fab Notes)

```gerber
# In KiCad, generate Gerbers with mechanical layers:
# File > Plot > Include layers: "Edge.Cuts", "User.Comments", "Dwgs.User"
# Use Gerber X2 format (File > Plot > Format > Gerber X2)
# This embeds layer metadata for the fab house

# Altium: Output Job > Gerber X2
# Add mechanical layers to "Plot Layers" > "Mechanical Layer 1"
# Set "Plot on all layers" to "No" to avoid duplication
```

## Common Pitfalls & Gotchas

1. **Mounting hole clearance vs. copper pour**  
   I’ve seen boards where mounting holes were placed directly over a ground plane with no thermal relief. During reflow, the hole acts as a heat sink, causing cold solder joints. Always use a thermal spoke (4 spokes, 0.3mm width) or leave a 0.5mm clearance ring around the hole if it’s not tied to ground.

2. **Connector orientation and cable exit**  
   A right-angle header that exits toward a tall component (e.g., an electrolytic capacitor) will physically interfere. I once had a board where the USB connector’s cable exit was blocked by a 10mm inductor. Always run a 3D clearance check with the cable model inserted. In KiCad, use the `3D Viewer` with the connector’s step model to verify.

3. **Ignoring mating cycle forces**  
   High-cycle connectors (e.g., HDMI, SD card) require additional mechanical support. Without mounting ears or a metal shield soldered to the board, the connector will fatigue after ~500 cycles. Use connectors with through-hole mounting tabs (e.g., TE 292303-1) and solder them to a large copper area for heat dissipation.

## Try It Yourself

1. **Add mounting holes to an existing board**  
   Take a simple two-layer board design. Add four M3 mounting holes at the corners (3.2mm hole, 6mm pad). Use a keep-out zone of 5mm around each hole to prevent component placement. Export the STEP file and check clearance in a 3D viewer.

2. **Create a connector keep-out region**  
   Place a USB-C connector footprint on your board. Draw a keep-out polygon on the mechanical layer that extends 3mm beyond the connector body on all sides. Add a design rule that prevents any component from being placed inside that region. Run a DRC to verify.

3. **Simulate cable strain**  
   In your EDA tool, add a cable tie anchor point (a 2mm hole) near a board-to-wire connector (e.g., a JST XH header). Route a dummy cable in the 3D viewer and verify the cable exits at a 90-degree angle without bending the connector pins. Adjust the hole position if needed.

## Next Up

Tomorrow: **Day 16: Silkscreen, Assembly Drawings & Fab Notes** — we’ll cover how to annotate your board for manufacturing, including reference designator placement, polarity markers, version numbers, and the critical fab notes that prevent a $10k prototype run from being scrapped.
