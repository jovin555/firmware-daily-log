---
title: "Day 17: EMI Considerations in High-Speed Layout"
date: 2026-07-28
tags: ["til", "high-speed-design", "emi", "high-speed"]
---

## What I Explored Today

Today I dug into the practical side of electromagnetic interference (EMI) control during high-speed PCB layout. While theory often focuses on far-field radiation and antenna models, the real battle happens on the board itself—between traces, planes, vias, and connectors. I focused on three actionable areas: stack-up design for return current control, via stitching to reduce cavity resonance, and filtering techniques that actually work without killing signal integrity. The goal was to understand how layout decisions made today directly determine whether a board passes FCC/CE radiated emissions testing on the first spin.

## The Core Concept

EMI in high-speed digital design is fundamentally a problem of **unintentional antennas**. Every signal trace, every via barrel, every power plane edge can become a radiator if the return current path is disrupted. The key insight is that current always returns via the path of least impedance—not resistance. At high frequencies (above ~100 MHz), that path is the plane directly adjacent to the signal layer, not a distant ground pin.

When you route a trace over a split plane, or change layers without a nearby return via, the return current is forced to detour. That detour creates a loop antenna. The loop area times the di/dt of the signal defines the radiated field strength. Your job as a layout engineer is to minimize every loop area to near zero. This means continuous reference planes, tight via stitching at layer transitions, and keeping high-speed signals away from board edges (where fringing fields couple to cables).

The second core concept is **common-mode conversion**. Differential signals inherently cancel fields when perfectly balanced. But skew, impedance mismatch, or asymmetric via stubs convert differential energy into common-mode current. That common-mode current flows on cables and chassis, turning your product into a broadcast tower. Controlling common-mode means controlling symmetry—in trace length, via placement, and component loading.

## Key Commands / Configuration / Code

### Stack-up Definition (Altium Designer example)

```text
Layer Stack Manager Settings:
- Top Layer: Signal (microstrip, 1.5 oz Cu)
- Layer 2: GND Plane (solid, no splits)
- Layer 3: Power Plane (3.3V, 1.8V islands)
- Layer 4: Bottom Signal (microstrip, 1.5 oz Cu)

Dielectric: FR4, Er=4.2, thickness=0.2mm between signal and plane
Target impedance: 50Ω single-ended, 100Ω differential
```

### Via Stitching Rule (KiCad DRC rule example)

```python
# KiCad DRC rule for via stitching along board edge
(rule "Edge_stitch_vias"
    (condition "A.via")
    (constraint distance (min 2.5mm) (max 5.0mm))
    (constraint clearance (min 0.5mm))
)

# Manual stitching command (via array)
# Place vias every 3mm along all ground plane boundaries
# Use 0.3mm drill, 0.6mm pad for 6-layer boards
```

### Common-Mode Filter Layout (Schematic snippet)

```text
CMF Component: Wurth 744232090 (90Ω common-mode choke)
Placement rules:
- Keep traces symmetrical within 0.5mm length
- No vias between CMF and connector
- Ground flood under CMF, connected with 4 vias per pad
- Route differential pair with 100Ω impedance, 0.2mm spacing
```

### Return Via Calculation (Python helper)

```python
# Calculate required number of return vias at layer transition
def return_vias(freq_ghz, di_dt_A_ns):
    # Rule of thumb: 1 return via per 1 GHz per 1 A/ns
    n_vias = int(freq_ghz * di_dt_A_ns) + 1
    return max(n_vias, 2)  # minimum 2 for redundancy

# Example: 2.4 GHz signal with 0.5 A/ns edge rate
print(return_vias(2.4, 0.5))  # Output: 2
```

## Common Pitfalls & Gotchas

**1. Routing over split planes without stitching capacitors.**  
If you must cross a plane split (e.g., analog/digital boundary), place a 0.1 µF capacitor bridging the split directly under the trace. Many engineers forget this and create a slot antenna. The capacitor provides a low-impedance return path at high frequencies. Use 0402 or smaller, with two vias per pad to minimize inductance.

**2. Ignoring via stub resonance.**  
A via stub longer than λ/20 at the signal frequency acts as a resonant cavity. For DDR4 at 1.6 GHz, λ/20 ≈ 4.7 mm in FR4. If your board is 1.6 mm thick and you route on the top layer, the via stub is 1.6 mm—safe. But on a 2.4 mm board with bottom-layer routing, the stub is 2.4 mm, which resonates at ~3.1 GHz. Use back-drilling or change layer assignments to keep stubs under 1 mm.

**3. Assuming differential routing guarantees low EMI.**  
Differential pairs only cancel fields if they are perfectly balanced. A 1 mm length mismatch at 2.4 GHz creates ~8 ps skew, which converts ~5% of the signal to common-mode. That common-mode current can fail FCC Class B limits. Always length-match within 0.5 mm for high-speed pairs, and keep the pair tightly coupled (edge-to-edge spacing ≤ 2× trace width).

## Try It Yourself

1. **Audit your current board for return current paths.** Open your layout and identify three high-speed traces (e.g., DDR data lines, USB 3.0, Ethernet). For each trace, verify there is a continuous ground plane directly below it for the entire route. If you find a split plane crossing, add a stitching capacitor (0.1 µF, 0402) bridging the split under the trace.

2. **Measure via stub length on your stack-up.** Calculate the via stub length for your thickest board layer. Use the formula: stub = (board thickness) - (routing layer depth). If stub > 1 mm, add a back-drill layer in your fab notes or move the signal to a layer closer to the bottom. Document the change in your design rules.

3. **Simulate common-mode conversion from skew.** Use a free tool like HyperLynx SI or even a Python script to model a differential pair with 2 mm length mismatch at 1.6 GHz. Calculate the common-mode voltage amplitude. Then adjust the pair to <0.5 mm mismatch and re-simulate. Compare the radiated field estimate (E-field ∝ common-mode current × loop area).

## Next Up

Tomorrow is Day 18: **Full Review & Project: Route a DDR4 Fly-by Topology with Length Matching**. We’ll take everything from the past 17 days—impedance control, timing closure, EMI mitigation—and apply it to a real DDR4 memory interface. You’ll route a fly-by topology, match all address/command traces to within 5 ps, and verify the design with a post-layout simulation. Bring your layout tool and a strong cup of coffee.
