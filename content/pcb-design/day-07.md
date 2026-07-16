---
title: "Day 07: Thermal Design: Copper Pours, Thermal Vias & Heat Sinking"
date: 2026-07-16
tags: ["til", "pcb-design", "thermal", "copper-pour"]
---

## What I Explored Today

Today I dove into the thermal side of PCB layout — specifically how to move heat from components to the board and out to the environment. I focused on three practical techniques: copper pours for spreading heat, thermal vias for conducting it through the board, and heatsink attachment strategies. I also ran some quick thermal simulations in KiCad to validate a design for a 3.3V LDO regulator dropping 12V at 500mA — that’s 4.35W of waste heat, enough to fry a TO-220 package without proper management.

## The Core Concept

Heat in a PCB moves primarily by conduction through copper, then by convection from board surfaces to air. FR-4 is a terrible thermal conductor (~0.3 W/m·K), while copper is excellent (~400 W/m·K). The trick is to use copper pours and vias to create low-thermal-resistance paths from hot components to larger cooling surfaces.

The key metric is **thermal resistance**, usually given in °C/W. For a junction-to-ambient path, you want the total resistance as low as possible. A copper pour on the top layer directly under a power component acts as a heat spreader. Thermal vias then conduct that heat to inner ground planes or bottom-layer copper, which acts as a radiator. Heatsinks add forced or natural convection surfaces.

A rule of thumb: every 10°C reduction in junction temperature doubles component lifetime. So thermal design isn’t just about preventing immediate failure — it’s about reliability.

## Key Commands / Configuration / Code

### 1. Copper Pour Setup (KiCad 7.x)

In KiCad’s PCB editor, a copper pour is a zone. For a power regulator, I define a zone on the top layer under the component, connected to the GND net:

```
Zone Properties:
- Layer: F.Cu
- Net: GND
- Fill style: Solid (not hatched)
- Clearance: 0.25mm (default)
- Thermal relief: None (for high-current paths, use direct connection)
```

For thermal performance, set the zone to **solid fill** and **no thermal relief** on the pad connected to the heat source. Thermal reliefs (spokes) reduce thermal conductivity — they’re for soldering, not heat transfer.

### 2. Thermal Via Array (KiCad via stitching)

To create a thermal via array under a component, I place vias manually or use the “Via Stitching” tool:

```
# Via parameters for thermal vias:
- Diameter: 0.6mm
- Drill: 0.3mm
- Layers: F.Cu -> B.Cu (or to inner plane)
- Clearance: 0.25mm
- Spacing: 1.0mm grid (or tighter, 0.8mm if space allows)
```

In KiCad, select the zone, then `Tools > Via Stitching > Add Stitching Vias`. Set the grid to 1.0mm and select the target layer (e.g., B.Cu). This places a grid of vias that conduct heat from the top copper pour to the bottom layer.

### 3. Heatsink Pad Pattern (for SMD packages)

For a D2PAK or TO-263, the exposed pad must be connected to the copper pour with multiple vias:

```
# Recommended via pattern for D2PAK exposed pad (6.5mm x 5.0mm):
- 9 vias in a 3x3 grid
- Via diameter: 0.5mm, drill: 0.3mm
- Solder mask tented on bottom side (to prevent solder wicking)
- Top-side solder mask opened over vias (to allow solder fill)
```

In the footprint editor, add vias directly to the pad. In KiCad, you can add a custom pad with via properties, or place vias inside the pad area after assigning the same net.

### 4. Quick Thermal Calculation (Python snippet)

```python
# Thermal resistance estimation for a copper pour
# Assumptions: 1oz copper, 35um thickness, natural convection

def copper_spreader_Rth(area_mm2, thickness_um=35):
    # Copper thermal conductivity: 400 W/m·K
    # Convert area to m^2, thickness to m
    area_m2 = area_mm2 * 1e-6
    thickness_m = thickness_um * 1e-6
    Rth = thickness_m / (400 * area_m2)  # °C/W
    return Rth

# Example: 25mm x 25mm copper pour (625 mm^2)
Rth_spreader = copper_spreader_Rth(625)
print(f"Spreader thermal resistance: {Rth_spreader:.3f} °C/W")
# Output: ~0.00014 °C/W — negligible, so bottleneck is junction-to-case and via resistance
```

The real bottleneck is the junction-to-case resistance (typically 1-5 °C/W for TO-220) and the via thermal resistance (each 0.3mm drill via adds ~70 °C/W in series — but with 9 in parallel, that drops to ~8 °C/W).

## Common Pitfalls & Gotchas

1. **Thermal reliefs on power pads** — This is the #1 mistake. By default, PCB tools add thermal reliefs (spokes) to pads to ease soldering. But for a pad that’s the primary heat path, those spokes create a high thermal resistance. Always set the zone connection to “Direct” (no relief) for the thermal pad. If soldering is a concern, use a larger pad or a solder paste stencil with a window.

2. **Vias without solder mask tenting** — If you place vias under a component and don’t tent the bottom-side solder mask, solder will wick through during reflow, starving the joint. Always tent the bottom side (or fill vias with non-conductive epoxy). For high-reliability designs, use plugged or filled vias.

3. **Ignoring the PCB stackup** — A 2-layer board with 1oz copper on top and bottom has limited thermal mass. For high-power designs, use 2oz copper on all layers and add inner ground planes. A 4-layer board with 2oz outer and 1oz inner layers can handle 2-3x more heat than a standard 2-layer board.

## Try It Yourself

1. **Calculate your own thermal budget**: Take a component you’re using (e.g., an LDO or MOSFET). Look up its junction-to-case thermal resistance (RθJC) and maximum junction temperature. Calculate the maximum power it can dissipate with a 25°C ambient. Then design a copper pour area (in mm²) that keeps the case below 85°C using the rule of thumb: 1 square inch of copper per watt for natural convection.

2. **Add a thermal via array in KiCad**: Open an existing PCB design with a power component. Create a copper pour on the top layer under the component, connected to GND. Use the Via Stitching tool to add a 3x3 grid of 0.6mm vias connecting to the bottom GND pour. Check the DRC for clearance violations.

3. **Simulate with a thermal camera**: Build a simple test board with a 1W resistor on a large copper pour (25mm x 25mm) and another on a small pad (5mm x 5mm). Power both at 1W and measure temperature rise with a thermal camera. Compare the difference — it’s a great visual lesson in thermal spreading.

## Next Up

Tomorrow, I’ll cover **Component Placement Strategy: Grouping, Orientation & Test Points** — how to arrange components for signal integrity, manufacturability, and testability, including decoupling capacitor placement, connector orientation, and test point planning.
