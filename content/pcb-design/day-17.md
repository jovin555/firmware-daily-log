---
title: "Day 17: Pre-Compliance EMI/EMC Considerations at the Layout Stage"
date: 2026-07-28
tags: ["til", "pcb-design", "emi", "emc"]
---

## What I Explored Today

Today I dove into the practical side of pre-compliance EMI/EMC engineering — specifically, what we can do *during PCB layout* to avoid failing radiated and conducted emissions tests later. I’ve been burned before by a board that passed functional tests but lit up a spectrum analyzer like a Christmas tree at 120 MHz. The root cause? A poorly routed clock trace and a missing stitching via. Today I focused on three concrete layout techniques: controlled impedance return paths, decoupling capacitor placement with via inductance modeling, and differential pair skew management. These aren’t theoretical — they’re the difference between a first-pass compliance and a costly respin.

## The Core Concept

EMI/EMC pre-compliance isn’t about adding ferrites or shielding after the fact. It’s about controlling the *loop area* of high-frequency currents. Every signal trace forms a loop with its return path. The larger the loop, the more efficient the antenna. At 100 MHz, a loop area of just 1 cm² can radiate well above FCC Class B limits. The key insight: *return current follows the path of least inductance, not least resistance*. For a microstrip trace over a ground plane, the return current flows directly under the trace, in a narrow band. If you cut that ground plane with a slot or a moat, the return current is forced to detour, increasing loop area and creating a slot antenna. The same logic applies to power planes — a split plane under a high-speed trace is a disaster.

## Key Commands / Configuration / Code

Below are practical examples using KiCad 8.0 and a Python script for quick loop-area estimation. These are tools I use daily.

### 1. KiCad Constraint Setup for Differential Pairs (USB 2.0)

In KiCad’s PCB Editor, set up a differential pair rule for D+ and D-:

```
# In PCB Editor → Board Setup → Design Rules → Constraints
# Add a new constraint:
#   Net class: USB_DP_DM
#   Track width: 0.25 mm
#   Clearance: 0.15 mm
#   Differential pair gap: 0.25 mm
#   Differential pair max skew: 0.5 mm
```

Then assign the nets:
```
# Right-click on D+ net → Net Class → Assign to USB_DP_DM
# Repeat for D-
# Route as differential pair using 'D' key
```

Why 0.5 mm skew? For USB 2.0 (480 Mbps), the rise time is ~500 ps. A 0.5 mm skew corresponds to ~3.3 ps delay mismatch (assuming FR4, εr ~4.5, v ~150 mm/ns). That’s well under 10% of the rise time, keeping common-mode conversion low.

### 2. Python Script for Loop Area Estimation

Save this as `loop_area.py`. It calculates the approximate loop area of a trace over a ground plane, given trace length and height above plane.

```python
#!/usr/bin/env python3
"""
loop_area.py — Estimate loop area for a microstrip trace.
Input: trace_length_mm, trace_height_mm (dielectric thickness)
Output: loop_area_cm2, approximate radiation efficiency at 100 MHz
"""
import math

def loop_area(trace_length_mm, trace_height_mm):
    # Loop area = length * height (return path is directly under trace)
    area_cm2 = (trace_length_mm * trace_height_mm) / 100.0  # mm^2 to cm^2
    return area_cm2

def radiation_efficiency(area_cm2, freq_mhz=100):
    # Simple dipole model: radiated power ~ (area * freq)^2
    # Threshold: FCC Class B at 3m, 100 MHz, limit ~150 uV/m
    # This is a rough sanity check, not a simulation.
    efficiency = (area_cm2 * freq_mhz) ** 2 * 1e-6
    return efficiency

if __name__ == "__main__":
    # Example: 50 mm trace, 0.2 mm dielectric (4-layer board, prepreg)
    L = 50.0  # mm
    H = 0.2   # mm
    area = loop_area(L, H)
    eff = radiation_efficiency(area, 100)
    print(f"Trace: {L} mm long, {H} mm above plane")
    print(f"Loop area: {area:.2f} cm²")
    print(f"Radiation efficiency factor at 100 MHz: {eff:.2e}")
    if area > 0.5:
        print("⚠️  Loop area > 0.5 cm² — consider shortening trace or reducing height.")
    else:
        print("✅ Loop area acceptable for typical low-speed digital.")
```

Run it:
```bash
python3 loop_area.py
```

Output:
```
Trace: 50 mm long, 0.2 mm above plane
Loop area: 0.10 cm²
Radiation efficiency factor at 100 MHz: 1.00e-04
✅ Loop area acceptable for typical low-speed digital.
```

### 3. Via Stitching for Ground Plane Integrity

In KiCad, use the “Add filled zone” tool to create a ground plane on the top layer, then stitch it to the inner ground plane:

```
# Place a via near every signal layer transition (e.g., near a clock via)
# Use "Route → Add via" (shortcut 'V') and set net to GND
# For a 100 MHz clock, place stitching vias every 5 mm along the trace
# Rule of thumb: via spacing < λ/20, where λ = c/(f * sqrt(εr))
# For FR4 at 100 MHz: λ ≈ 1500 mm, so spacing < 75 mm — but 5 mm is safer.
```

## Common Pitfalls & Gotchas

1. **Assuming a solid ground plane is enough.** A solid plane is necessary but not sufficient. If you have a via that transitions a high-speed signal from top to bottom layer without a nearby ground via, the return current must jump between planes through the nearest decoupling cap — often far away. This creates a large loop. Always place a ground via within 1 mm of every signal via for frequencies above 50 MHz.

2. **Ignoring the power plane as a return path.** For signals referenced to a power plane (e.g., 3.3V), the return current flows in that plane. If the power plane has a split or a narrow neck, the return path is forced to detour. Use a continuous power plane, or place stitching capacitors (100 nF) every 10 mm across the split to maintain a low-inductance path.

3. **Over-filtering with ferrite beads.** A ferrite bead on a power rail can create a resonance with the board’s decoupling capacitance, actually *amplifying* noise at certain frequencies. Always check the impedance vs. frequency curve. For example, a 600 Ω bead at 100 MHz might have only 50 Ω at 10 MHz, doing nothing for lower-frequency ripple. Use ferrites only after characterizing the noise spectrum.

## Try It Yourself

1. **Calculate loop area for your worst-case trace.** Pick the longest high-speed trace on your current board (clock, SPI, or USB). Measure its length and the dielectric height to the nearest plane. Use the Python script above. If the loop area exceeds 0.5 cm², redesign the routing to shorten the trace or move it to a layer closer to the plane.

2. **Audit your via transitions.** Open your PCB layout. For every via that carries a signal above 10 MHz, check if there is a ground via within 1 mm. If not, add one. Then run a DRC to ensure no ground plane slots are created by the new vias.

3. **Set up a differential pair constraint.** If your board has USB, Ethernet, or LVDS, define a differential pair rule in your EDA tool. Route a short test pair (10 mm) with the correct gap and skew. Measure the skew using the length tuning tool — ensure it’s under 0.5 mm for USB 2.0.

## Next Up

Tomorrow is Day 18: **Full Review & Project: Layout a 4-Layer Sensor Board from Schematic to Fab**. We’ll take a complete sensor board schematic (I2C, analog front-end, and a 100 MHz SPI bus) and lay it out step-by-step, applying every technique from this week: stackup design, return paths, decoupling, and pre-compliance checks. By the end, you’ll have a fab-ready design. Bring your EDA tool of choice.
