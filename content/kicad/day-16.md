---
title: "Day 16: Gerber & Drill File Generation for Fabrication"
date: 2026-07-27
tags: ["til", "kicad", "gerbers", "drill-files"]
---

## What I Explored Today

Today I went through the entire Gerber and drill file generation workflow in KiCad, targeting a 4-layer board for a JLCPCB prototype run. I’ve generated Gerbers before, but this time I focused on the exact settings that match each fabricator’s requirements — and I learned that the difference between a board that passes DRC and one that actually gets fabricated correctly often comes down to a few checkbox toggles and layer naming conventions. I also validated the output files using GerbView and a free online Gerber viewer to catch common issues before hitting "upload."

## The Core Concept

Gerber files (RS-274X format) are the universal language of PCB fabrication. They describe each copper layer, solder mask, silkscreen, and paste layer as a set of 2D polygons and apertures. Drill files (Excellon format) define hole locations, sizes, and whether they are plated-through or non-plated. The "why" here is simple: fabricators cannot use your KiCad project file. They need standardized, self-contained files that include all layer definitions, aperture definitions, and coordinate data. If you omit a layer, misname it, or use an incompatible format, the fab will either reject the order or produce a board with missing features.

The critical nuance is that Gerber files are *not* just images. They contain embedded aperture definitions (flash vs. draw commands), and modern fabricators rely on the file’s metadata to interpret layer polarity (positive vs. negative) and copper clearance. A common mistake is assuming that what you see in the PCB editor is exactly what the fab gets — but hidden layers like Edge.Cuts, Margin, or F.CrtYd can cause confusion if not handled correctly.

## Key Commands / Configuration / Code

### Step 1: Plot Settings (File → Plot)

In the Plot dialog, I use these exact settings for a 4-layer board:

```
Output directory: gerber/
Plot format: Gerber (RS-274X)
Layers to plot:
  - F.Cu
  - In1.Cu
  - In2.Cu
  - B.Cu
  - F.Mask
  - B.Mask
  - F.Silkscreen
  - B.Silkscreen
  - Edge.Cuts
  - F.Paste (optional, for stencil)
  - B.Paste (optional, for stencil)
```

**Critical checkboxes:**
- [x] Use auxiliary axis origin (ensures all files share a common reference point)
- [x] Subtract soldermask from silkscreen (prevents silkscreen on pads)
- [x] Include footprint attributes (some fabs use this for fiducials)
- [x] Generate DRC violations as separate file (helps debug)

**Do NOT check:**
- [ ] Plot footprint references (creates text artifacts on copper)
- [ ] Plot Pcbnew attributes (not standard Gerber)

### Step 2: Drill File Generation (File → Fabrication Outputs → Drill Files)

```
Drill file format: Excellon (Gerber compatible)
Drill units: Millimeters
Zeros format: Suppress trailing zeros (most fabs prefer this)
Drill origin: Absolute
Minimal header: Yes (avoids non-standard commands)
```

**Map file:**
- [x] Generate map file (helps verify hole locations)
- Map file format: PostScript (human-readable)

### Step 3: Generate the Files

Click "Generate Drill File" and "Generate Map File". Then go back to Plot and click "Plot". All files land in the `gerber/` directory.

### Step 4: Validate with GerbView

Open GerbView (included with KiCad) and load all Gerber files plus the drill file. I always check:
- Layer alignment (zoom to a corner via-hole — all layers should match)
- Silkscreen does not overlap pads (the "Subtract soldermask" option handles this, but verify)
- Edge.Cuts is a closed, continuous outline (no gaps)

### Example: Naming Convention for JLCPCB

JLCPCB expects these exact file suffixes:
```
project_name.gbr          -> F.Cu
project_name.gbr          -> In1.Cu (rename to .g2)
project_name.gbr          -> In2.Cu (rename to .g3)
project_name.gbr          -> B.Cu
project_name.gbr          -> F.Mask (rename to .gts)
project_name.gbr          -> B.Mask (rename to .gbs)
project_name.gbr          -> F.Silkscreen (rename to .gto)
project_name.gbr          -> B.Silkscreen (rename to .gbo)
project_name.gbr          -> Edge.Cuts (rename to .gko)
project_name.drl          -> Drill file
```

KiCad’s default naming appends `-F_Cu.gbr`, etc. I batch-rename using a simple script or the fab’s upload tool (most accept the KiCad defaults now, but double-check).

## Common Pitfalls & Gotchas

1. **Missing Edge.Cuts layer** — This is the #1 reason for fab rejection. If Edge.Cuts is not plotted, the fab doesn’t know the board outline. Always include it, and ensure it’s a single continuous closed polyline (use the "Close shape" tool in the PCB editor).

2. **Drill file units mismatch** — If your PCB is designed in inches but you generate drill files in millimeters (or vice versa), holes will be off by a factor of 25.4. I always set the PCB editor to millimeters (File → Page Settings → Units) and keep drill units consistent.

3. **Unplated holes defined as plated** — If you have mounting holes that should be non-plated (NPTH), you must assign them to the `NPTH` drill layer in KiCad. If you leave them on the default `Drill` layer, the fab will plate them. Use the "Track/Via" properties dialog to set hole type to "Non-plated."

4. **Silkscreen on pads** — Even with "Subtract soldermask from silkscreen" enabled, some text or graphics may still overlap pads if they are on the footprint itself. I run a DRC with the "Silkscreen over pad" check enabled (in DRC rules) to catch these.

## Try It Yourself

1. **Generate Gerbers for your current project** — Use the exact settings above. Then open the output folder and count the files. You should have at least: 4 copper layers, 2 mask, 2 silkscreen, 1 edge cuts, 1 drill, and 1 map file. If any are missing, go back and check the layer list.

2. **Validate with an online Gerber viewer** — Upload your zip to a free viewer like gerber-viewer.com or the one built into JLCPCB’s order page. Zoom into a dense area and toggle layers on/off. Look for silkscreen bleeding onto pads or missing copper on inner layers.

3. **Test a different fab’s requirements** — Download the "Gerber Generation Guide" from PCBWay or OSH Park. Compare their required file suffixes and polarity settings with what you used. Adjust your plot settings and regenerate. This exercise reveals how much variation exists between fabs.

## Next Up

Tomorrow, I’ll tackle **BOM Generation & Integration with JLCPCB/PCBWay**. We’ll go from schematic to a sorted, manufacturer-ready BOM, including how to handle alternate part numbers, LCSC part codes, and automated cross-referencing. See you then.
