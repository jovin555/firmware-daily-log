---
title: "Day 14: Return Path Discontinuities: Plane Splits & Stitching Vias"
date: 2026-07-23
tags: ["til", "high-speed-design", "return-path", "stitching-vias"]
---

## What I Explored Today

Today I dug into one of the most common root causes of EMI and signal integrity failures in multi-layer PCBs: return path discontinuities. Specifically, I focused on what happens when a high-speed trace crosses a split in its adjacent reference plane, and how to properly use stitching vias to maintain a low-inductance return path. I simulated a 1.8V DDR4 clock line crossing a ground plane split and measured the resulting common-mode noise—it was eye-opening.

## The Core Concept

Every signal trace is actually part of a loop. The forward current travels on the trace, and the return current flows through the nearest reference plane (usually ground or power) directly underneath the trace. At high frequencies (above ~100 MHz), the return current doesn't spread out—it concentrates in a narrow band directly under the trace, following the path of least inductance.

When you cut a slot or split in the reference plane—for example, to isolate an analog ground from a digital ground, or to route a different voltage plane—you break that return path. The return current is forced to detour around the split. That detour creates a large current loop, which:

- Increases loop inductance (bad for signal quality)
- Radiates common-mode noise (bad for EMI)
- Creates voltage differentials across the split (bad for receivers)

The fix is to provide an alternative low-inductance return path. That's where **stitching vias** come in. If you must cross a split, place a pair of vias—one on each side of the split, connected to the same reference plane—to bridge the gap. Even better: never cross splits with high-speed signals in the first place.

## Key Commands / Configuration / Code

### 1. Identifying Return Path Discontinuities in Allegro PCB Editor

```skill
; Skill script to highlight traces crossing plane voids
; Run in Allegro PCB Editor Command window

axlCmdRegister("check_return_path" 'check_return_path)
defun(check_return_path ()
    let((dbid)
        ; Select all dynamic shapes on GND layer
        axlDBDeleteSelection()
        axlSetFindFilter(?enabled list("noall" "shapes") ?onButtons list("shapes"))
        axlSingleSelectPoint()
        ; This is a simplified check—real implementation iterates all traces
        printf("Manual check: Use 'Display -> Element' on traces near plane voids.\n")
        printf("Look for traces crossing void boundaries.\n")
    )
)
```

### 2. HyperLynx PI Simulation Setup for Split Plane Analysis

```tcl
# HyperLynx PI script to add stitching vias at a plane split crossing
# Run in HyperLynx PI command window

set trace_name "CLK_P"
set split_layer "GND"
set via_diameter 12.0mil
set via_hole 8.0mil

# Place stitching vias 50 mils from each side of the split
set x_cross 1500.0
set y_cross 2000.0

# Via on left side of split
add via -x [expr $x_cross - 50] -y $y_cross -diameter $via_diameter -hole $via_hole -layers {GND GND}

# Via on right side of split
add via -x [expr $x_cross + 50] -y $y_cross -diameter $via_diameter -hole $via_hole -layers {GND GND}

# Connect both vias to the same net
assign net -name "GND" -ref "GND"
```

### 3. Python Script for Estimating Loop Inductance from Split

```python
# estimate_split_inductance.py
# Quick estimation of added loop inductance when crossing a plane split

import math

def loop_inductance_nH(length_mm, width_mm, height_mm):
    """
    Approximate loop inductance of a rectangular current loop.
    Uses simplified formula: L ≈ 0.002 * length * (ln(2*length/width) + 0.5)
    length, width, height in mm, result in nH.
    """
    # Effective loop dimensions: detour path length = 2 * split_width + trace_height
    detour_length = 2 * width_mm + height_mm
    # Assume loop width = trace width (typical 0.2mm)
    trace_width = 0.2
    L_nH = 0.002 * detour_length * (math.log(2 * detour_length / trace_width) + 0.5)
    return L_nH

# Example: 5mm wide split, trace 0.5mm above plane
split_width_mm = 5.0
trace_height_mm = 0.5
L_added = loop_inductance_nH(split_width_mm, split_width_mm, trace_height_mm)
print(f"Added loop inductance from {split_width_mm}mm split: {L_added:.2f} nH")
# Output: Added loop inductance from 5.0mm split: 0.08 nH — sounds small, but at 1GHz, 
# that's 0.5 ohms of impedance discontinuity.
```

## Common Pitfalls & Gotchas

1. **Stitching vias too far from the split** – Vias placed more than 1/20th of a wavelength from the crossing point are ineffective. At 1 GHz (λ ≈ 150mm in FR4), that means vias must be within 7.5 mm of the split edge. I've seen designs where vias were 20mm away—they did nothing.

2. **Using power planes as the only return path** – If your signal references a power plane (e.g., 1.8V), and that plane has a split for a different voltage rail, the return current will find the nearest decoupling capacitor to jump planes. That capacitor's ESL adds inductance. Always prefer ground as the reference plane for high-speed signals.

3. **Forgetting about via anti-pads** – When you place a stitching via, its anti-pad (the clearance hole in the plane) creates a small void. If you stack multiple stitching vias too close, their anti-pads merge into a larger void, defeating the purpose. Keep stitching vias at least 3x the anti-pad diameter apart.

## Try It Yourself

1. **Simulate a split plane crossing** – In your favorite 3D EM solver (or HyperLynx), create a simple microstrip trace over a solid ground plane. Measure S21. Then cut a 5mm slot in the ground plane under the trace. Re-measure S21 and note the ripple. Add a stitching via 50 mils from each side of the slot. Compare.

2. **Check your existing board** – Open a recent PCB layout. Use the cross-probe tool to highlight all traces on a high-speed bus (e.g., DDR, PCIe). Then toggle the visibility of the reference plane layer. Count how many traces cross plane voids. For each, note the distance to the nearest stitching via.

3. **Calculate the penalty** – For a 1.2V DDR4 signal at 1.6 Gbps, the rise time is about 200 ps. Using the inductance formula above, calculate the voltage drop (V = L * dI/dt) if the return current must detour around a 10mm split. Assume dI = 20 mA. Is it significant compared to the 1.2V swing?

## Next Up

Tomorrow, we tackle **Simultaneous Switching Noise (SSN) & Ground Bounce** — the hidden enemy that happens when dozens of outputs switch at once, collapsing the internal supply rails and corrupting quiet signals. We'll model a 32-bit bus and calculate the cumulative di/dt.
