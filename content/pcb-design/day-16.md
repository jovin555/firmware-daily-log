---
title: "Day 16: Silkscreen, Assembly Drawings & Fab Notes"
date: 2026-07-27
tags: ["til", "pcb-design", "silkscreen", "assembly-drawing"]
---

## What I Explored Today

Today I dug into the documentation layer that turns a routed board into a manufacturable product: silkscreen legends, assembly drawings, and fabrication notes. While layout gets the glory, these deliverables are where the design engineer communicates intent to the fab house and assembly line. A board with perfect impedance control and flawless routing is worthless if the assembler can't tell which way to orient D1 or if the fab house doesn't know you want 1 oz copper with ENIG finish. I spent the day cleaning up my silkscreen layers, generating proper assembly drawings in KiCad 8, and writing a comprehensive fab note block.

## The Core Concept

Silkscreen, assembly drawings, and fab notes serve three distinct audiences with overlapping needs. The silkscreen layer (typically "F.SilkS" and "B.SilkS" in KiCad) is for human technicians during assembly, rework, and debugging. It must be legible, unambiguous, and survive the soldering process. Assembly drawings are the official visual contract between the design engineer and the assembly house — they show component outlines, reference designators, polarity marks, and orientation indicators in a clean, machine-readable format. Fab notes are the textual specification that tells the PCB manufacturer exactly how to build the board: stackup, material, copper weights, surface finish, impedance requirements, and testing criteria.

The critical insight is that these documents must be self-consistent. If your silkscreen says "C1 — 10µF" but your BOM says "C1 — 22µF", you've created a manufacturing error. If your assembly drawing shows U3 rotated 90° from the silkscreen, the pick-and-place machine will tombstone the part. The documentation layer is where design intent becomes manufacturing reality, and any inconsistency here costs real money in rework or scrapped boards.

## Key Commands / Configuration / Code

In KiCad 8, I use the following workflow for silkscreen cleanup and documentation generation.

**Silkscreen cleanup script (Python, run in KiCad's pcbnew console):**

```python
import pcbnew

board = pcbnew.GetBoard()

# Set silkscreen reference font size to 1.0mm (minimum for legibility)
# KiCad stores text size in nanometers
MIN_TEXT_SIZE = 1000000  # 1.0mm

for drawing in board.GetDrawings():
    if drawing.GetLayerName() in ['F.SilkS', 'B.SilkS']:
        if drawing.GetClass() == 'TEXTE_PCB':
            # Only resize reference designators, not logos or warnings
            if drawing.GetText().startswith('REF**'):
                drawing.SetTextSize(pcbnew.VECTOR2I(MIN_TEXT_SIZE, MIN_TEXT_SIZE))
                drawing.SetTextThickness(150000)  # 0.15mm stroke width

# Move silkscreen away from pads (0.2mm clearance rule)
CLEARANCE = 200000  # 0.2mm
for footprint in board.GetFootprints():
    for pad in footprint.Pads():
        pad_bbox = pad.GetBoundingBox()
        # Expand bounding box by clearance
        pad_bbox.Inflate(CLEARANCE)
        # Check all silkscreen text in this footprint
        for text in footprint.Reference().GetDrawings():
            if text.GetLayerName() in ['F.SilkS', 'B.SilkS']:
                if pad_bbox.Contains(text.GetPosition()):
                    # Move text outside pad bounding box
                    # Simple heuristic: move up by pad height + clearance
                    new_y = pad_bbox.GetY() + pad_bbox.GetHeight() + CLEARANCE
                    text.SetPosition(pcbnew.VECTOR2I(text.GetPosition().x, new_y))
```

**Assembly drawing generation (KiCad command line):**

```bash
# Generate Gerber files with assembly layer
kicad-cli pcb export gerbers \
  --layers "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts" \
  --output ./gerbers/ \
  my_board.kicad_pcb

# Generate assembly drawing PDF (top side, with component outlines)
kicad-cli pcb export pdf \
  --layers "F.Cu,F.SilkS,F.Mask,Edge.Cuts" \
  --include-border-title \
  --output ./docs/assembly_top.pdf \
  my_board.kicad_pcb

# Generate drill file
kicad-cli pcb export drill \
  --format excellon \
  --output ./gerbers/ \
  my_board.kicad_pcb
```

**Example fab note block (for inclusion in Gerber readme or separate PDF):**

```
FABRICATION NOTES — Rev A
==========================
1.  MATERIAL: FR-4, Tg 170°C, IPC-4101/21
2.  LAYER STACKUP: 4-layer, 1.6mm total thickness
    - Top: 1oz copper
    - Layer 2: GND plane, 1oz copper
    - Layer 3: Power plane, 1oz copper
    - Bottom: 1oz copper
    - Prepreg: 7628 x 2 between L1-L2 and L3-L4
    - Core: 0.5mm 2116 between L2-L3
3.  SURFACE FINISH: ENIG (Electroless Nickel Immersion Gold), 3-5µ" Au over 120-200µ" Ni
4.  SOLDER MASK: Green, LPI, 0.3mm minimum web, 0.1mm minimum sliver
5.  SILKSCREEN: White, epoxy-based, 0.15mm minimum stroke width
6.  IMPEDANCE: 50Ω ±10% on top layer traces > 10mm length
    - Trace width: 0.35mm, clearance to GND: 0.2mm (coplanar)
    - Reference plane: Layer 2 (continuous GND)
7.  ELECTRICAL TEST: 100% netlist testing, 10V isolation test
8.  DELIVERABLES: Gerber RS-274X, Excellon drill, IPC-356 netlist
```

## Common Pitfalls & Gotchas

**1. Silkscreen over vias or pads.** This is the most common rookie mistake. When silkscreen ink sits on a solderable surface, it prevents wetting and creates a cold solder joint. Always run a DRC rule that checks silkscreen-to-copper clearance (I use 0.2mm minimum). In KiCad, this is under Board Setup → Design Rules → Constraints → Silkscreen clearance.

**2. Assembly drawings that don't match the silkscreen.** I've seen boards where the assembly drawing shows a SOIC-8 rotated 180° from the silkscreen outline. The pick-and-place machine follows the assembly drawing, so the part gets placed backwards. Always generate assembly drawings from the same KiCad project that produced the Gerbers, and visually verify the first article against the drawing.

**3. Fab notes that are too vague.** "Standard FR-4" means different things to different fab houses. Specify Tg (130°C vs 170°C), copper weight (0.5oz vs 1oz vs 2oz), and surface finish explicitly. I once had a board come back with HASL instead of ENIG because I wrote "standard finish" — that cost me a week of rework because the fine-pitch QFN wouldn't solder properly.

## Try It Yourself

1. **Silkscreen audit:** Open your most recent PCB design. Run a DRC with silkscreen clearance set to 0.2mm. Fix every violation by moving text or adjusting footprint reference positions. Document how many violations you found — this is your baseline for future designs.

2. **Generate an assembly drawing:** Export a PDF of your top-layer assembly drawing with component outlines, reference designators, and polarity marks visible. Print it at 1:1 scale and physically place a few components on the paper to verify orientation matches your silkscreen.

3. **Write a fab note block:** Create a complete fab note block for your current design using the template above. Include stackup, material, surface finish, impedance requirements, and testing criteria. Send it to your preferred fab house and ask if anything is ambiguous or missing.

## Next Up

Tomorrow we'll tackle Pre-Compliance EMI/EMC Considerations at the Layout Stage — how to design for electromagnetic compatibility from the first trace, including stackup planning for return current control, guard traces, and ferrite bead placement strategies that save you from costly radiated emissions testing failures.
