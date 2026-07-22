---
title: "Day 13: PCB Fabrication Notes: Gerbers, Drill Files & Stackup Specs"
date: 2026-07-22
tags: ["til", "pcb-design", "gerbers", "drill-files"]
---

## What I Explored Today

Today I dove into the final handoff between design and fabrication: the manufacturing data package. After weeks of schematic capture, layout, and routing, I finally faced the reality that a beautiful PCB in the CAD tool is worthless if the fab house can't interpret the files. I spent the day generating Gerber RS-274X files, Excellon drill files, and writing a proper stackup specification. The key insight? These files are the *contract* between designer and manufacturer — every ambiguity here becomes a delay or a defect on the board.

## The Core Concept

The manufacturing data package serves one purpose: to unambiguously describe every copper layer, solder mask opening, silkscreen mark, and drill hole on the board. The industry standard for decades has been Gerber format (now RS-274X, the extended format that embeds aperture definitions directly in the file). Drill files use the Excellon format, which is essentially G-code for a CNC drilling machine.

Why does this matter? Because your CAD tool's internal representation is proprietary. The fab house doesn't have your license. They need open, standard files that any CAM station can read. More critically, the *stackup specification* — the layer order, material types, copper weights, and dielectric thicknesses — determines the board's impedance, mechanical stiffness, and manufacturability. If you specify 1 oz copper but need 0.5 oz for fine-pitch BGAs, you'll get boards that fail at the assembly house.

The real engineering work here is not just exporting files, but *validating* them. I learned to use a free Gerber viewer (like Gerbv or KiCad's built-in viewer) to check each layer independently, verify alignment, and confirm that the drill hits land exactly on the pads. A 0.1 mm offset between the copper and drill file means every via is shorted or open.

## Key Commands / Configuration / Code

### Gerber Export Settings (KiCad 8.x example)

When exporting Gerbers from KiCad, I use these settings for every project:

```
Plot format: Gerber X2 (RS-274X)
Include extended attributes: YES
Subtract soldermask from silkscreen: YES
Use auxiliary axis origin: YES (set to board edge corner)
Coordinate format: 4.6 (metric, 0.01 mm resolution)
```

The auxiliary axis origin is critical — it sets the zero point for all coordinates. I always place it at the bottom-left corner of the board outline. This makes it trivial for the fab to align layers.

### Drill File Export (Excellon)

For the drill file, I export with these parameters:

```
Drill units: Millimeters
Zeros format: Suppress leading zeros
Coordinate format: 4.6 (same as Gerbers)
Mirror Y axis: NO
Minimal header: YES
```

The "suppress leading zeros" format is standard for Excellon. A coordinate of 12.7 mm becomes `127000` (4 integer digits, 6 decimal digits, no leading zeros). The drill file also includes a tool table listing each drill diameter and its corresponding "T" code.

### Stackup Specification (Example for 4-layer board)

Here's a typical stackup I specify in a separate text file or PDF:

```
Layer Stackup (Top to Bottom):
----------------------------------------
1. Top Copper: 1 oz (35 µm) + plating
2. Prepreg: 7628 (0.007" / 0.178 mm) @ 50% resin
3. Layer 2 (GND): 1 oz (35 µm)
4. Core: 2116 (0.004" / 0.102 mm) @ 55% resin
5. Layer 3 (PWR): 1 oz (35 µm)
6. Prepreg: 7628 (0.007" / 0.178 mm) @ 50% resin
7. Bottom Copper: 1 oz (35 µm) + plating
----------------------------------------
Total thickness: 0.062" ±10% (1.57 mm)
Impedance targets: 50 Ω ±10% on outer layers
Dielectric constant (Dk): 4.2 @ 1 GHz (FR-4)
```

I include the resin content because it affects the final dielectric thickness after lamination. The fab uses this to calculate trace widths for controlled impedance.

## Common Pitfalls & Gotchas

### 1. Mismatched Coordinate Systems
I once exported Gerbers in inches but the drill file in millimeters. The fab's CAM system scaled the drill file by 25.4, placing every hole 25.4x too far from the origin. The fix: always export both in the same unit (metric is safer), and use a Gerber viewer to overlay the drill file on the copper layers before sending.

### 2. Missing or Incorrect Soldermask Expansion
The soldermask layer must have a *clearance* around each pad — typically 0.05-0.1 mm larger than the copper pad. If you export the soldermask as an exact copy of the copper layer, the mask will cover the pads entirely. I always set the soldermask expansion to 0.1 mm in the CAD tool, and verify that the soldermask layer shows donut-shaped openings, not solid circles.

### 3. Forgetting the Board Outline Layer
The fab needs a dedicated "board outline" or "mechanical" layer (usually layer 20 in KiCad, or "GM1" in Altium). This layer should be a closed polyline with no gaps. If you forget it, the fab will guess the board shape from the copper boundaries — and they'll guess wrong. I always draw the outline as a 0.01 mm wide line on a mechanical layer, and verify it's included in the Gerber export.

## Try It Yourself

1. **Export and validate a 2-layer board**: Open any completed PCB design. Export Gerbers and drill files using the settings above. Open them in a free Gerber viewer (Gerbv or KiCad's built-in viewer). Overlay the top copper, top soldermask, and top silkscreen. Verify that soldermask openings are larger than pads, and silkscreen doesn't overlap pads.

2. **Write a stackup specification**: For a 4-layer board you're designing, write a complete stackup spec including layer order, copper weights, dielectric materials, and target impedance. Use the example above as a template. Include a note about the total thickness tolerance (±10% is standard for FR-4).

3. **Detect a drill-to-copper offset**: Deliberately export a drill file with a different origin than the Gerbers (e.g., set the auxiliary axis to the top-right corner instead of bottom-left). Load both files in a viewer and measure the offset. This simulates the most common fab rejection reason.

## Next Up: Flex & Rigid-Flex PCB Design Basics

Tomorrow, I'm moving from rigid boards to flexible circuits. We'll cover material selection (polyimide vs. polyester), bend radius calculations, and the critical "flex-to-rigid transition zone" design rules. If you've ever wondered how those foldable phone boards work without breaking, stay tuned.
