---
title: "Day 11: DFM/DFA: Design for Manufacturing & Assembly Checks"
date: 2026-07-20
tags: ["til", "pcb-design", "dfm", "dfa"]
---

## What I Explored Today

Today I dug into the often-overlooked bridge between a perfect schematic and a physically realizable board: Design for Manufacturing (DFM) and Design for Assembly (DFA) checks. While DRC (Design Rule Check) ensures your layout respects electrical constraints like clearance and trace width, DFM/DFA focuses on whether a fab house can actually etch, drill, plate, and solder your board without yield loss or rework. I ran a full DFM audit on a 4-layer mixed-signal board using KiCad’s built-in DRC engine combined with an external Python-based DFM checker, and the results were humbling—over a dozen violations I’d never considered, from annular ring slivers to solder mask slivers between fine-pitch QFN pads.

## The Core Concept

DFM and DFA are not optional niceties; they are cost and reliability gates. A board that passes electrical DRC but fails DFM might have 20% of its vias with insufficient copper annulus, leading to barrel cracks during thermal cycling. Or it might have a 0.3mm gap between two QFN pads that the solder mask cannot reliably resolve, causing solder bridges on 80% of assemblies. The core idea is to design for the *process capabilities* of your target manufacturer, not for ideal theoretical limits.

DFM covers fabrication: minimum trace/space, hole-to-copper clearance, annular ring requirements, solder mask registration tolerances, and copper balancing to prevent warpage. DFA covers assembly: component-to-component clearance for pick-and-place nozzles, fiducial placement for vision alignment, thermal pad via tenting to prevent solder wicking, and edge clearance for panelization rails. Every fab house publishes a capability document—typically a PDF with tables like “Minimum annular ring: 0.15mm (outer layers), 0.20mm (inner layers)”—and your design must stay within those bounds. The trick is that many EDA tools default to overly aggressive values (e.g., 0.1mm annular ring) that no volume manufacturer can hit.

## Key Commands / Configuration / Code

I used KiCad 8.0, but the principles apply to Altium, Eagle, or any tool. Here’s how I set up a DFM-aware DRC rule file:

```python
# dfm_rules.kicad_dru — KiCad Design Rules file for DFM compliance
# Target: JLCPCB standard 4-layer process (1oz copper, 0.2mm min hole)

(version 20230708)

(rule "Minimum annular ring outer"
  (constraint annular_width (min 0.15mm))
  (condition "A.Layer == 'F.Cu' || A.Layer == 'B.Cu'")
  (comment "Outer layers: 0.15mm min annular ring for reliable plating"))

(rule "Minimum annular ring inner"
  (constraint annular_width (min 0.20mm))
  (condition "A.Layer == 'In1.Cu' || A.Layer == 'In2.Cu'")
  (comment "Inner layers: 0.20mm due to etch registration tolerance"))

(rule "Solder mask sliver clearance"
  (constraint solder_mask_clearance (min 0.10mm))
  (condition "A.Type == 'Pad' && B.Type == 'Pad'")
  (comment "Prevents mask slivers between adjacent pads"))

(rule "Copper to board edge"
  (constraint edge_clearance (min 0.30mm))
  (condition "A.Layer != 'Edge.Cuts'")
  (comment "Keep copper 0.3mm from board edge to avoid routing damage"))

(rule "Minimum hole size"
  (constraint hole_size (min 0.25mm))
  (condition "A.Type == 'Via' || A.Type == 'Pad'")
  (comment "0.25mm is standard for mechanical drills; 0.2mm for laser is special order"))
```

To run a quick DFM check on a generated Gerber set, I used the open-source `gerbv` with a Python script that checks annular ring ratios:

```bash
# Extract annular ring data from Gerber RS274X files
# Requires gerbv and pcb-tools (pip install pcb-tools)
python3 -c "
from pcb_tools import gerber
import numpy as np

# Load top copper and drill file
copper = gerber.load('top_copper.gbr')
drill = gerber.load('drill.drl')

# For each drill hit, compute annular ring = (pad diameter - hole diameter)/2
violations = []
for hole in drill.holes:
    pad_diam = copper.get_pad_diameter_at(hole.x, hole.y)
    if pad_diam:
        ring = (pad_diam - hole.diameter) / 2
        if ring < 0.15:  # mm threshold
            violations.append(f'Hole at ({hole.x:.2f},{hole.y:.2f}): ring={ring:.3f}mm')
            
print(f'Found {len(violations)} annular ring violations')
for v in violations[:5]:
    print(v)
"
```

For assembly checks, I exported a centroid file (pick-and-place CSV) and ran a clearance check between component bodies:

```bash
# Check minimum component-to-component clearance for pick-and-place
# Using kicad-utils (pip install kicad-utils)
kicad-utils centroid --input board.kicad_pcb --output centroid.csv
python3 -c "
import csv
from itertools import combinations

with open('centroid.csv') as f:
    reader = csv.DictReader(f)
    parts = [(r['Ref'], float(r['X']), float(r['Y']), float(r['Rotation'])) for r in reader]

min_clearance = 0.5  # mm, typical for 0603 passives
for (ref1, x1, y1, r1), (ref2, x2, y2, r2) in combinations(parts, 2):
    dist = ((x1-x2)**2 + (y1-y2)**2)**0.5
    if dist < min_clearance:
        print(f'COLLISION: {ref1} and {ref2} distance={dist:.3f}mm')
"
```

## Common Pitfalls & Gotchas

1. **Assuming your EDA tool’s default DRC matches your fab’s capabilities.** KiCad’s default annular ring is 0.13mm; JLCPCB’s standard is 0.15mm. That 0.02mm difference causes 100% yield loss on inner layers. Always import the fab’s design rule file (many provide `.kicad_dru` or `.rul` files) before routing.

2. **Ignoring solder mask slivers between fine-pitch QFN pads.** A 0.5mm pitch QFN has 0.25mm pad width and 0.25mm gap. Solder mask registration tolerance is typically ±0.075mm. If you use a 0.05mm solder mask clearance, the remaining web between pads is 0.15mm—below most fabs’ 0.1mm minimum. The mask will peel, exposing copper and causing bridges. Solution: use “solder mask defined” pads or increase clearance to 0.075mm.

3. **Forgetting about copper balancing for panelization.** If one area of the board has 90% copper and another has 10%, the board will warp during reflow due to uneven thermal expansion. Most fabs require copper density to be within 20% across the board. Use copper pour with hatched patterns (e.g., 70% fill) on large empty areas to balance.

## Try It Yourself

1. **Run a DFM audit on your last board.** Download your fab’s capability PDF (e.g., JLCPCB, PCBWay, or OSH Park). Create a custom DRC rule file with their minimum annular ring, hole size, and solder mask clearance values. Re-run DRC and count how many violations appear.

2. **Check annular rings manually.** Export your top copper Gerber and drill file. Use the Python script above to find all holes with annular ring below 0.15mm. For each violation, decide whether to increase pad diameter or move the via.

3. **Simulate a pick-and-place collision.** Export a centroid file from your EDA tool. Write a short script to compute distances between all component centers. Identify any components closer than 0.5mm (for 0603) or 1.0mm (for QFN). Adjust placement to meet assembly house minimums.

## Next Up

Tomorrow: **Design Rule Checks (DRC): Common PCB Layout Errors** — we’ll move from manufacturing constraints back to electrical integrity, covering the top 10 DRC violations that plague intermediate designers, from starved thermals to stub lengths on high-speed nets.
