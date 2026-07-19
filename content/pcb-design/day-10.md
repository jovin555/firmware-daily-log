---
title: "Day 10: Panelization & Fabrication Panel Design"
date: 2026-07-19
tags: ["til", "pcb-design", "panelization"]
---

## What I Explored Today

Today I dove into the practical reality of PCB panelization — the process of combining multiple individual PCB designs into a single manufacturing panel. While it sounds like a simple layout task, panelization directly impacts yield, cost, and assembly throughput. I worked through standard panel sizes, breakaway methods (V-scoring vs. tab-routing), and the critical design rules that make or break a fabrication panel. The goal: understand how to design a panel that survives the fab house and the pick-and-place line without warping, breaking, or costing a fortune.

## The Core Concept

Panelization exists because PCB fabrication and assembly are batch processes. A single 100x100 mm board costs nearly the same to process as a 400x500 mm panel containing 20 of them. The panel is the unit of work for solder paste printing, component placement, and reflow. If your panel is poorly designed, you get tombstoning from uneven support, broken rails during depaneling, or excessive scrap from edge clearance violations.

The key trade-off is between **panel utilization** (maximizing boards per panel) and **process robustness** (ensuring each board survives depaneling). The standard panel sizes in the industry are 18x24 inches (457x610 mm) for most fabs, with a usable area typically 2-5 mm smaller on each edge for tooling rails. You must also account for fiducials, tooling holes, and mouse bites or V-scoring lanes.

The two primary breakaway methods are:
- **V-scoring**: A V-shaped groove cut along a straight line between boards. Works only for rectangular boards with straight edges. Leaves a thin web (~0.3-0.4 mm) that snaps after assembly. Cheapest, but requires boards to be aligned in rows/columns.
- **Tab-routing**: A router cuts the board outline, leaving small tabs (typically 3-5 per side) with mouse bites (small drilled holes) that snap. Works for any shape, including irregular or circular boards. More expensive per panel, but essential for complex outlines.

## Key Commands / Configuration / Code

In KiCad, panelization is done in the PCB editor by creating a new panel project that references the individual board file. Here’s the workflow and key settings:

### Creating a Panel in KiCad (v7+)

```python
# Example: KiCad Python scripting for panelization
# This script places a board design into a panel array

import pcbnew

# Load the panel board file
panel = pcbnew.LoadBoard("panel.kicad_pcb")

# Load the single-board design to replicate
board_file = pcbnew.LoadBoard("my_design.kicad_pcb")

# Define panel parameters
board_width = 50.0  # mm
board_height = 40.0  # mm
x_count = 4          # boards in X direction
y_count = 3          # boards in Y direction
x_spacing = 2.0      # gap between boards (for V-scoring or routing)
y_spacing = 2.0
edge_rail_width = 5.0  # mm for tooling rails

# Place boards in a grid
for row in range(y_count):
    for col in range(x_count):
        # Calculate position (origin at bottom-left of panel)
        x_pos = edge_rail_width + col * (board_width + x_spacing)
        y_pos = edge_rail_width + row * (board_height + y_spacing)
        
        # Create a footprint-like module for the board outline
        # In practice, you'd use KiCad's "Append Board" or manual copy
        # This is a simplified representation
        print(f"Place board at ({x_pos:.1f}, {y_pos:.1f})")
```

**Real-world KiCad settings for V-scoring panel:**
- Set `Board Setup > Design Rules > Constraints > Minimum track width` to 0.15 mm (for V-scoring web)
- Add a `Edge.Cuts` layer line along the V-score line — this tells the fab where to cut
- For V-scoring, the score line must be a continuous straight line across the entire panel width/height
- For tab-routing, add small cutouts (mouse bites) on the `Edge.Cuts` layer at tab locations

### Gerber Output for Panelization

When generating Gerbers for a panel, you must include:
- **Tooling holes**: 3.175 mm (1/8") holes at panel corners, typically on the `Drill` layer
- **Fiducials**: 1.0 mm copper pads on the top layer, placed at opposite corners of the panel
- **Panel outline**: A separate `GM1` (mechanical 1) layer showing the full panel boundary

```bash
# Example: Using gerbv to verify panel Gerbers
gerbv panel_top_copper.gbr panel_bottom_copper.gbr panel_outline.gbr
```

## Common Pitfalls & Gotchas

1. **Ignoring the copper-to-edge clearance on V-score lines.** V-scoring cuts through copper. If your traces run parallel and close to the V-score line, they can short after depaneling. Always maintain at least 0.5 mm clearance from the V-score centerline to any copper. For high-voltage designs, increase this to 1.0 mm.

2. **Uneven panel support causing solder defects.** If your panel has a mix of large and small boards, the smaller boards may have less support during reflow. This leads to warpage and tombstoning. Always add breakaway rails or support tabs to ensure every board has at least two points of mechanical connection to the panel frame.

3. **Forgetting to add fiducials on the panel, not just the individual board.** Pick-and-place machines need global panel fiducials to align the entire panel, plus local fiducials on each board for fine-pitch components. Without panel-level fiducials, the machine cannot correct for panel warpage or rotation. Place at least two fiducials on the panel frame, diagonally opposite.

## Try It Yourself

1. **Design a simple 2x2 panel for a 30x20 mm board.** Use V-scoring with a 2 mm gap between boards. Add 5 mm tooling rails on all four sides. Generate Gerbers and verify the panel outline matches the fab house requirements (check their website for standard panel sizes).

2. **Convert a non-rectangular board (e.g., circular or L-shaped) into a tab-routed panel.** Add at least 4 tabs per board, each with 2 mouse bites (0.5 mm diameter). Ensure the tabs are placed on straight edges, not on corners, to avoid stress risers.

3. **Calculate the maximum number of your current design that fits on a standard 18x24 inch panel.** Account for 5 mm edge rails and 3 mm gaps between boards. Compare the cost per board for a 10-board prototype run vs. a 100-board production run (assume $50 setup + $0.10 per square inch of panel).

## Next Up

Tomorrow, I’ll tackle **DFM/DFA: Design for Manufacturing & Assembly Checks** — the systematic review process that catches panelization errors, clearance violations, and assembly showstoppers before you hit "order." We’ll cover automated DRC rules, common fab house feedback, and how to interpret a DFM report.
