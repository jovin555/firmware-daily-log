---
title: "Day 08: PCB Editor (Pcbnew): Layers, Zones & Board Setup"
date: 2026-07-17
tags: ["til", "kicad", "pcbnew", "zones"]
---

## What I Explored Today

Today I dove into the PCB Editor (Pcbnew) to understand the physical stackup, layer management, and copper zone creation—the foundation of any real board. After schematic capture, the first thing you do in Pcbnew is define your board outline, set up the layer stack, and pour copper planes. I worked through a 4-layer board design, configuring signal layers, power planes, and zone connectivity rules. The key takeaway: getting the layer stack and zone parameters right before routing saves hours of rework.

## The Core Concept

Pcbnew treats layers as physical copper, dielectric, or mechanical entities, each with a specific role. The layer stack defines the board's impedance, current capacity, and manufacturability. Zones are not just copper pours—they are intelligent polygons that can be assigned nets, clearance rules, and thermal relief patterns. The critical insight is that zones are *dynamic*: they automatically fill around traces and vias, but only if you configure the clearance and thermal spoke parameters correctly. If you don't set up zones before routing, you'll fight with copper islands and orphaned fills later.

The board setup dialog (`File > Board Setup`) is where you define the physical stackup. This includes layer count, thickness, copper weight, and dielectric material. For a standard 4-layer board, the typical stackup is: Top Signal (1oz) → Prepreg (0.2mm) → Inner Ground (1oz) → Core (1.2mm) → Inner Power (1oz) → Prepreg (0.2mm) → Bottom Signal (1oz). Pcbnew uses this information for impedance calculations and design rule checks (DRC).

## Key Commands / Configuration / Code

### 1. Setting Up the Layer Stack

Navigate to `File > Board Setup > Board Stackup`. Here you define each layer:

```text
Layer Stackup (4-layer example):
- Layer 0: F.Cu (Top Signal) — 1oz copper, 35µm
- Prepreg: FR-4, εr=4.5, thickness=0.2mm
- Layer 1: In1.Cu (Ground Plane) — 1oz copper
- Core: FR-4, εr=4.5, thickness=1.2mm
- Layer 2: In2.Cu (Power Plane) — 1oz copper
- Prepreg: FR-4, εr=4.5, thickness=0.2mm
- Layer 3: B.Cu (Bottom Signal) — 1oz copper
```

To add a layer: right-click in the layer list → `Add Layer`. For inner layers, set the net assignment in the `Net Classes` editor if you want automatic plane clearance.

### 2. Drawing the Board Outline

Use the `Edge.Cuts` layer to define the physical board shape:

```text
1. Select the Edge.Cuts layer from the layer selector (right sidebar)
2. Press 'B' to activate the graphic line tool
3. Draw a closed polygon (e.g., 100mm x 80mm rectangle)
4. Use 'M' to move edges, 'D' to delete segments
5. Press 'Ctrl+Shift+M' to measure distances
```

Pro tip: Use the `Graphics` layer for mechanical dimensions, but keep the actual board outline strictly on `Edge.Cuts`. Pcbnew uses this layer for 3D model generation and DRC.

### 3. Creating Copper Zones

Zones are created with the `Add a filled zone` tool (shortcut: `Ctrl+Z`):

```text
1. Select the target layer (e.g., F.Cu for top ground pour)
2. Press 'Ctrl+Z' or click the zone tool icon (paint bucket)
3. Draw a polygon around the board edge (snap to Edge.Cuts)
4. In the zone properties dialog:
   - Net: GND (or VCC for power plane)
   - Fill mode: Solid (for copper pours)
   - Clearance: 0.3mm (default, adjust for high voltage)
   - Thermal relief: 0.5mm spoke width, 4 spokes
   - Minimum width: 0.25mm (for thin copper islands)
5. Press 'B' to fill the zone (or right-click → Zone Actions → Fill All Zones)
```

For power planes on inner layers, set `Fill mode` to `Solid` and `Clearance` to 0.5mm to avoid accidental shorts. For signal layers, use `Thermal relief` to ensure solderability.

### 4. Zone Priority and Islands

Multiple zones on the same layer can overlap. Pcbnew uses priority (higher number = higher priority) to determine which zone fills first. To set priority:

```text
Right-click zone → Zone Properties → Priority: 1 (default)
- Priority 0: lowest, filled last
- Priority 10: highest, filled first
- Use for: keepout zones (priority 10) vs. ground pour (priority 0)
```

To remove copper islands (orphaned fills), enable `Remove islands` in zone properties. Islands smaller than 1mm² are automatically deleted during fill.

## Common Pitfalls & Gotchas

1. **Zones not filling after routing** — If you route traces after creating zones, the zones won't automatically update. Always press `B` (Fill All Zones) after any routing change. Better yet, enable `Auto-fill zones` in `Preferences > PCB Editor > Display Options`.

2. **Thermal relief causing DRC errors** — Default thermal spoke width (0.5mm) may violate your minimum trace width rule. If your design rules specify 0.3mm minimum, set spoke width to 0.3mm or adjust the rule. Check `Tools > Design Rules Check` after filling zones.

3. **Board outline not closed** — Pcbnew requires a closed polygon on `Edge.Cuts` for 3D export and DRC. Use `Inspect > List Unconnected` to find gaps. A common mistake: drawing the outline with overlapping endpoints instead of snapping to grid.

## Try It Yourself

1. **Set up a 4-layer stackup**: Open a new board, go to `Board Setup > Board Stackup`, and add two inner layers. Set copper weight to 1oz for all layers, and dielectric thickness to 0.2mm between layers. Verify the total board thickness is ~1.6mm.

2. **Draw a board outline and pour a ground zone**: On `Edge.Cuts`, draw a 50mm x 50mm square. Create a zone on `F.Cu` assigned to net GND. Fill the zone, then route a single trace across the board. Refill the zone and observe how the trace creates a clearance moat.

3. **Experiment with thermal relief**: Create a through-hole pad (e.g., a 2.54mm header) on a ground zone. Change the thermal spoke width from 0.5mm to 0.3mm and refill. Run DRC to see if the spoke width violates your design rules.

## Next Up

Tomorrow, we'll dive into the **Interactive Router: Push & Shove, Diff Pair Routing**. I'll show you how to use the interactive router to push existing traces out of the way, route differential pairs with controlled impedance, and set up net classes for high-speed signals. Bring your most tangled board—we're going to clean it up.
