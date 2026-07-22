---
title: "Day 13: Plugin & Scripting: KiCad Python API"
date: 2026-07-22
tags: ["til", "kicad", "python-api", "scripting"]
---

## What I Explored Today

Today I dove into KiCad's Python API for automating PCB design tasks. After weeks of manual routing and component placement, I needed a way to batch-edit footprint properties, generate fabrication data, and enforce design rules programmatically. KiCad exposes a full Python binding through `pcbnew` and `eeschema` modules, letting us script everything from netlist manipulation to footprint placement. I built a script that renumbers reference designators, updates silkscreen text sizes, and exports Gerber files—all without touching the GUI.

## The Core Concept

KiCad's Python API is not a separate tool—it's a direct binding to the C++ internals. When you `import pcbnew`, you get access to the same `BOARD` object that the KiCad PCB editor uses internally. This means any operation you can do through the GUI (move footprints, change layers, modify tracks) is available as a method call.

The key architectural insight: KiCad stores everything in a `BOARD` object, which is a tree of `BOARD_ITEM` objects. Footprints are `FOOTPRINT` objects (formerly `MODULE`), tracks are `TRACK`, and zones are `ZONE`. Each has properties like `GetPosition()`, `SetOrientation()`, `GetLayer()`, and `SetReference()`. You iterate the board using `GetFootprints()`, `GetTracks()`, or `GetDrawings()`.

Why this matters for automation: manual board editing is error-prone and slow for repetitive tasks. Need to change all 0402 resistor silkscreen outlines to 0.15mm width? That's a 10-line script. Need to verify that every via has a tenting layer? Script it. The API also gives you access to the design rules engine, so you can run DRC checks programmatically in CI pipelines.

## Key Commands / Configuration / Code

Here's a practical script that renumbers all reference designators to a sequential format and updates silkscreen text height to 1.0mm:

```python
#!/usr/bin/env python3
"""
Renumber footprints and standardize silkscreen text.
Usage: python renumber_footprints.py /path/to/board.kicad_pcb
"""

import pcbnew
import sys

def renumber_and_standardize(board_path):
    # Load the board - this is the entry point for all PCB operations
    board = pcbnew.LoadBoard(board_path)
    
    # Get all footprints (formerly MODULE objects)
    footprints = board.GetFootprints()
    
    # Sort by current reference for deterministic ordering
    footprints.sort(key=lambda fp: fp.GetReference())
    
    # Renumber sequentially: R1, R2, ... C1, C2, ...
    ref_counters = {}
    for fp in footprints:
        # Extract prefix (e.g., "R" from "R12")
        ref = fp.GetReference()
        prefix = ''.join([c for c in ref if not c.isdigit()])
        
        # Initialize counter if new prefix
        if prefix not in ref_counters:
            ref_counters[prefix] = 1
        
        # Set new reference
        new_ref = f"{prefix}{ref_counters[prefix]}"
        fp.SetReference(new_ref)
        ref_counters[prefix] += 1
        
        # Standardize silkscreen text properties
        # Get the reference text item (it's a TEXTE_FP item inside the footprint)
        ref_text = fp.Reference()  # Returns a FP_TEXT object
        ref_text.SetTextSize(pcbnew.VECTOR2I(1000000, 1000000))  # 1.0mm x 1.0mm in nm
        ref_text.SetTextThickness(150000)  # 0.15mm stroke width
        
        # Also update value text if present
        val_text = fp.Value()
        val_text.SetTextSize(pcbnew.VECTOR2I(800000, 800000))  # 0.8mm
        val_text.SetTextThickness(120000)
    
    # Save the modified board
    pcbnew.SaveBoard(board_path, board)
    print(f"Updated {len(footprints)} footprints in {board_path}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python renumber.py <board.kicad_pcb>")
        sys.exit(1)
    renumber_and_standardize(sys.argv[1])
```

To run this, you need KiCad's Python environment. On Linux, use `kicad-cli` or the bundled Python:  
`/usr/lib/kicad/python/bin/python3 renumber.py my_board.kicad_pcb`  
On Windows, use the Python shipped with KiCad:  
`"C:\Program Files\KiCad\8.0\bin\python.exe" renumber.py my_board.kicad_pcb`

For Gerber export automation:

```python
import pcbnew
import os

def export_gerbers(board_path, output_dir):
    board = pcbnew.LoadBoard(board_path)
    plot_controller = pcbnew.PLOT_CONTROLLER(board)
    
    # Configure plot options
    plot_opts = plot_controller.GetPlotOptions()
    plot_opts.SetOutputDirectory(output_dir)
    plot_opts.SetPlotFrameRef(False)  # No frame/coordinates
    plot_opts.SetPlotValue(False)     # Don't plot value text
    plot_opts.SetPlotReference(True)  # Do plot reference designators
    plot_opts.SetUseAuxOrigin(True)   # Use auxiliary origin for coordinates
    
    # Define layers to plot (Gerber format)
    layers_to_plot = [
        (pcbnew.F_Cu, "F_Cu"),
        (pcbnew.B_Cu, "B_Cu"),
        (pcbnew.F_SilkS, "F_SilkS"),
        (pcbnew.B_SilkS, "B_SilkS"),
        (pcbnew.F_Mask, "F_Mask"),
        (pcbnew.B_Mask, "B_Mask"),
        (pcbnew.Edge_Cuts, "Edge_Cuts"),
    ]
    
    for layer_id, layer_name in layers_to_plot:
        plot_controller.OpenPlotfile(layer_name, pcbnew.PLOT_FORMAT_GERBER, "gerber")
        plot_controller.PlotLayer(layer_id)
        plot_controller.ClosePlot()
    
    print(f"Gerbers exported to {output_dir}")
```

## Common Pitfalls & Gotchas

1. **Unit confusion**: KiCad's internal units are nanometers (nm), but the GUI displays in millimeters. A common mistake is setting text size to `1.0` (thinking mm) when the API expects `1e6` (1mm in nm). Always use `pcbnew.VECTOR2I(1000000, 1000000)` or convert with `pcbnew.FromMM(1.0)`.

2. **Footprint vs Module naming**: In KiCad 7+, the old `MODULE` class was renamed to `FOOTPRINT`. If you're reading older tutorials, they use `board.GetModules()`—that's deprecated. Use `board.GetFootprints()`. Similarly, `fp.GetPosition()` returns a `VECTOR2I`, not a tuple.

3. **Script execution context**: The Python API only works when KiCad's Python environment is active. Running `python3 script.py` with your system Python will fail with `ModuleNotFoundError: No module named 'pcbnew'`. You must use the Python interpreter bundled with KiCad, or set `PYTHONPATH` to include KiCad's site-packages.

4. **Board save path**: `pcbnew.SaveBoard()` expects an absolute path. Relative paths may silently fail or write to the wrong directory. Always use `os.path.abspath()`.

## Try It Yourself

1. **Batch silkscreen cleanup**: Write a script that finds all footprints with silkscreen text overlapping pads (check `fp.GetBoundingBox()` against pad positions) and moves the text 0.5mm away. Use `fp.Reference().SetPosition()`.

2. **Via tenting automation**: Create a script that iterates all vias (`board.GetTracks()` filtered by `track.Type() == pcbnew.TRACE_T` and `track.IsVia()`) and sets bottom/top solder mask expansion to 0mm for tenting. Use `via.SetBottomSolderMaskMargin(0)` and `via.SetTopSolderMaskMargin(0)`.

3. **Net class validator**: Write a script that checks every track's width against its net class's minimum width. Use `board.GetDesignSettings().GetNetClasses()` to get net class definitions, then compare `track.GetWidth()` against the class minimum. Print violations.

## Next Up

Tomorrow, I'll tackle **Custom Design Rule Checks with KiCad's DRC Engine**—writing Python scripts that hook into KiCad's DRC system to enforce company-specific rules like "no 90-degree angles on high-speed nets" or "all bypass capacitors must be within 5mm of their IC." This is where the API really shines for production-quality board design.
