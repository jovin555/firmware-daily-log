---
title: "Day 11: Shielding & Isolation for RF/Digital Coexistence"
date: 2026-07-20
tags: ["til", "rf-design", "shielding", "isolation"]
---

## What I Explored Today

Today I dug into the practical reality of keeping RF and digital circuits from interfering with each other on the same PCB. After weeks of impedance matching and filter design, I realized that even a perfectly matched RF front-end is useless if the digital noise from a microcontroller or switching regulator couples directly into the RF trace. I spent the day measuring isolation between a 2.4 GHz RF section and a 48 MHz digital bus on a 4-layer board, testing different shielding strategies, and validating the results with a spectrum analyzer and a VNA. The key takeaway: isolation isn't about magic materials—it's about intentional current return paths and physical separation.

## The Core Concept

The fundamental problem is that digital signals are broadband noise sources. A 48 MHz clock has harmonics that extend well into the GHz range. When a digital trace switches, it creates a transient current loop. If that loop shares ground impedance with an RF trace, the noise couples through what's called *common-impedance coupling*. The solution is twofold: **physical separation** and **ground-plane partitioning**.

Isolation is measured in dB of coupling (S21) between two ports. For RF/digital coexistence, you typically want at least 40 dB of isolation at the RF operating frequency. This is achieved by:
- Maintaining a solid, unbroken ground plane beneath both domains
- Physically separating RF and digital sections by at least 3–5 mm (more for higher frequencies)
- Using a ground fence (stitched vias) to create a waveguide-below-cutoff barrier
- Never routing digital traces over the RF ground plane or vice versa

The critical insight: a ground plane is only as good as its return path. If you cut a slot in the ground plane to route a trace, you've just created a slot antenna that will radiate noise directly into your RF section.

## Key Commands / Configuration / Code

### 1. Measuring Isolation with a VNA (Keysight PNA or similar)

```bash
# Setup: Calibrate VNA for 2-port S-parameter measurement (2.4–2.5 GHz)
# Connect Port 1 to RF trace (with 50-ohm launch), Port 2 to digital trace (with 50-ohm launch)

# Key SCPI commands for automated measurement (over GPIB or LAN)
SYST:PRES                    # Preset instrument
SENS:FREQ:STAR 2.4 GHz      # Start frequency
SENS:FREQ:STOP 2.5 GHz      # Stop frequency
SENS:SWE:POIN 1601          # Number of points
CALC:PAR:SDEF "S21", "S21"  # Define S21 measurement
CALC:PAR:SEL "S21"          # Select S21 trace
CALC:FORM MLOG              # Magnitude in dB
INIT:CONT ON                # Continuous sweep

# Read marker value at 2.44 GHz (typical BLE/Wi-Fi channel)
CALC:MARK1:STAT ON
CALC:MARK1:X 2.44 GHz
CALC:MARK1:Y?               # Returns isolation in dB (e.g., -45.2)
```

### 2. Ground Fence Via Stitching (KiCad / Altium)

```python
# Python script for KiCad to generate ground fence vias
# Place vias along a line at lambda/20 spacing for 2.4 GHz
import pcbnew

board = pcbnew.GetBoard()
# lambda = c/f = 3e8/2.4e9 = 125 mm
# lambda/20 = 6.25 mm — use 5 mm for margin
via_spacing_mm = 5.0
fence_start_x = 50.0  # mm
fence_start_y = 30.0  # mm
fence_end_y = 60.0    # mm

# Create vias along a vertical line
y = fence_start_y
while y <= fence_end_y:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(
        pcbnew.FromMM(fence_start_x),
        pcbnew.FromMM(y)
    ))
    via.SetViaType(pcbnew.VIA_THROUGH)
    via.SetDrill(0.3 * 1e6)  # 0.3 mm drill in nm
    via.SetWidth(0.6 * 1e6)  # 0.6 mm pad in nm
    board.Add(via)
    y += via_spacing_mm
```

### 3. Ground Plane Slot Check (Altium DRC)

```bash
# Altium Designer: Custom DRC rule to detect ground plane slots
# Rule: Clearance Constraint
# Where the first object matches: 'InPolygon' AND 'IsGround'
# Where the second object matches: 'IsTrack' AND 'InNet('DigitalBus')'
# Constraint: Minimum Clearance = 1.0 mm
# This flags any digital trace that comes within 1 mm of a ground plane edge
```

## Common Pitfalls & Gotchas

1. **The "Slotted Ground" Trap**: I once routed a digital signal through a ground plane via a narrow trace, thinking it was fine because the ground plane was "solid." The 0.5 mm slot I created acted as a slot antenna at 2.4 GHz, coupling -25 dB of noise into the RF section. The fix: never route any trace through a ground plane. Use a dedicated signal layer instead.

2. **False Isolation from Copper Pour**: Many engineers pour copper on the top layer and call it a "shield." If that copper pour isn't stitched to the ground plane with vias every λ/20 (6.25 mm at 2.4 GHz), it becomes a parasitic patch antenna. I measured 10 dB *worse* isolation with an unstitched copper pour compared to no pour at all.

3. **Ignoring the Power Supply**: The most common coupling path I see is through the shared power rail. A 48 MHz digital supply ripple couples directly into the RF LDO's input. The fix: use a ferrite bead (e.g., Murata BLM18PG121SN1, 120 Ω at 100 MHz) and a 10 µF + 0.1 µF cap on the digital supply *before* it branches to the RF section. Never share a single LDO between digital and RF.

## Try It Yourself

1. **Measure Your Own Isolation**: On your current board, use a VNA to measure S21 between the closest digital clock trace and the RF trace. If you don't have a VNA, use a spectrum analyzer with a near-field probe (e.g., Langer RF-R 400-1). Sweep from 100 MHz to 3 GHz. If you see any peak above -40 dB, you have a coupling problem.

2. **Add a Ground Fence**: In your EDA tool, place a row of vias (0.3 mm drill, 0.6 mm pad) spaced 5 mm apart along the boundary between your digital and RF sections. Re-measure S21. You should see at least 10 dB improvement at 2.4 GHz.

3. **Check for Ground Slots**: Export your ground plane layer as a Gerber and load it into a Gerber viewer. Zoom in on any area where a signal trace crosses the ground plane. If you see a gap (slot) in the copper, that's a problem. Redesign to avoid that routing.

## Next Up

Tomorrow, I'll cover **BLE/Wi-Fi/Sub-GHz RF Layout Guidelines for SoC Modules** — the specific do's and don'ts for placing antenna matching networks, crystal oscillators, and decoupling caps around integrated RF SoCs like the ESP32, nRF52840, and CC1352. We'll look at reference design layouts and what happens when you deviate from them.
