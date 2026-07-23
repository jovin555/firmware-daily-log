---
title: "Day 14: Flex & Rigid-Flex PCB Design Basics"
date: 2026-07-23
tags: ["til", "pcb-design", "flex-pcb", "rigid-flex"]
---

## What I Explored Today

Today I dove into the world of flexible and rigid-flex PCB design—a domain where traditional rigid board rules bend (literally). I worked through stackup constraints for dynamic vs. static flex applications, learned why copper thickness and bend radius are non-negotiable, and set up a rigid-flex project in KiCad 8. The key takeaway: flex design is as much about mechanical engineering as electrical, and ignoring the material science leads to cracked traces on the first flex cycle.

## The Core Concept

Why not just use a ribbon cable or wire harness? Because flex PCBs eliminate connectors, reduce assembly cost, and survive thousands of bending cycles when designed correctly. The core physics: copper work-hardens and fractures under repeated strain. The solution: use rolled-annealed (RA) copper instead of electro-deposited (ED) copper for dynamic flex areas, and never route 90° corners in the flex region—always use filleted corners with a radius ≥ 10× the material thickness.

The "why" behind rigid-flex is even more compelling: you get a single, unified PCB that folds into a 3D shape, eliminating multiple boards and their interconnects. But this comes at a cost: the transition zone between rigid and flex sections is a stress concentration point. Every via in the flex area is a potential failure site. The rule of thumb: keep vias out of the bend region entirely, or use staggered, teardropped vias with at least 0.2mm annular ring.

## Key Commands / Configuration / Code

I set up a rigid-flex stackup in KiCad 8. Here’s the critical configuration for a 4-layer rigid-flex with two flex layers:

```kicad
# In pcbnew, go to Board Setup → Board Stackup
# Define layers from top to bottom:

Layer 0: F.Cu (rigid, 1oz ED copper, 0.035mm)
Layer 1: FR4 prepreg (0.1mm, rigid region only)
Layer 2: In1.Cu (rigid, 1oz ED copper)
Layer 3: FR4 core (0.2mm, rigid region only)
Layer 4: In2.Cu (rigid, 1oz ED copper)  
Layer 5: Flex adhesive (0.025mm, polyimide)
Layer 6: Flex.Cu (0.5oz RA copper, 0.018mm)
Layer 7: Flex coverlay (0.025mm, polyimide)
Layer 8: Flex.Cu (0.5oz RA copper, 0.018mm)
Layer 9: Flex adhesive (0.025mm, polyimide)
Layer 10: In3.Cu (rigid, 1oz ED copper)
Layer 11: FR4 core (0.2mm, rigid region only)
Layer 12: In4.Cu (rigid, 1oz ED copper)
Layer 13: FR4 prepreg (0.1mm, rigid region only)
Layer 14: B.Cu (rigid, 1oz ED copper)
```

To define rigid and flex regions in KiCad, use the `Board Setup → Board Stackup → Regions` tab. Create a region polygon for the flex area and assign it a custom stackup:

```python
# Python script to add flex region in KiCad (pcbnew API)
import pcbnew

board = pcbnew.GetBoard()
# Create a rectangular flex region (50mm x 20mm)
flex_region = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
flex_region.SetPosition(pcbnew.VECTOR2I(100000000, 100000000))  # 100mm in nm
flex_region.SetWidth(50000000)   # 50mm
flex_region.SetHeight(20000000)  # 20mm
flex_region.SetLayer(pcbnew.F_Cu)
board.Add(flex_region)

# Assign stackup index 1 (flex) to this region
# In practice, use BoardSetup dialog; this is for automation
```

For bend radius calculation, I use this Python snippet during layout:

```python
def min_bend_radius(thickness_mm, copper_type="RA", dynamic=True):
    """
    Calculate minimum bend radius per IPC-2223.
    thickness_mm: total flex stackup thickness (copper + coverlay + adhesive)
    copper_type: "RA" or "ED"
    dynamic: True if flexing during operation, False for static (one-time bend)
    """
    if dynamic:
        factor = 10 if copper_type == "RA" else 20
    else:
        factor = 6 if copper_type == "RA" else 10
    return thickness_mm * factor

# Example: 0.018mm RA copper + 0.025mm coverlay + 0.025mm adhesive = 0.068mm total
# Dynamic bend: 0.068 * 10 = 0.68mm minimum radius
print(f"Min bend radius: {min_bend_radius(0.068, 'RA', True):.2f}mm")
```

## Common Pitfalls & Gotchas

1. **Copper fatigue from sharp bends** — I once routed a flex trace with a 45° mitered corner, thinking it was fine. After 500 cycles, the copper cracked at the inner corner. The fix: use arcs with radius ≥ 1.5mm for dynamic flex, and never use 90° corners anywhere in the flex region. IPC-2223B specifies that trace corners in flex must have a radius ≥ 3× the conductor width.

2. **Ignoring the neutral bend axis** — In a multi-layer flex, the neutral axis (where strain is zero) sits at the geometric center. Traces on the outer layers experience tension/compression. If you must route on outer layers, use thinner copper (0.5oz RA max) and keep trace widths under 0.3mm. I learned this the hard way when a 0.5mm trace on the outer layer delaminated after 200 cycles.

3. **Via-in-flex-pad without teardrops** — Vias in the flex region are stress risers. Without teardrops (aka "filleted" connections), the via barrel cracks at the pad junction. In KiCad, enable teardrops globally: `Tools → Teardrops → Add Teardrops`, set `Style` to "Curved" and `Max radius` to 0.3mm. For flex vias, also increase the annular ring to 0.2mm minimum.

## Try It Yourself

1. **Calculate your bend radius**: Take a 2-layer flex stackup (0.5oz RA copper, 0.025mm coverlay each side, 0.025mm adhesive). Compute the minimum bend radius for both static and dynamic applications using the formula above. Then, in your EDA tool, set a keepout rule that enforces this radius for all flex traces.

2. **Set up a rigid-flex stackup in KiCad**: Create a new project, define a 4-layer rigid-flex stackup with two flex layers (as shown above). Draw a flex region polygon on the `Edge.Cuts` layer, then assign it a custom stackup in `Board Setup → Board Stackup → Regions`. Verify the region appears correctly in 3D viewer.

3. **Route a flex trace with proper corners**: Place two pads 30mm apart in the flex region. Route a trace between them using only arc segments (not 45° or 90° corners). Set the arc radius to 2mm minimum. Measure the trace length and verify the bend radius constraint is met. Export a Gerber and inspect the trace corners in a Gerber viewer.

## Next Up

Tomorrow: **Connectors & Mechanical Considerations in PCB Layout** — we’ll cover mounting hole placement, connector strain relief, and how to avoid the classic "connector ripped off the board" failure mode. Bring your calipers.
