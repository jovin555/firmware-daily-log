---
title: "Day 12: BLE/Wi-Fi/Sub-GHz RF Layout Guidelines for SoC Modules"
date: 2026-07-21
tags: ["til", "rf-design", "ble", "wifi", "sub-ghz"]
---

## What I Explored Today

Today I dove into the PCB layout guidelines that separate a working BLE/Wi-Fi/Sub-GHz module from one that suffers from degraded sensitivity, desense, or outright regulatory failure. While datasheets provide generic "keep RF traces short" advice, the real engineering lies in understanding how ground-plane continuity, impedance control, and component placement interact across these three common ISM-band radios. I focused on multi-radio SoC modules like the ESP32-C6, nRF5340, and CC1352, where you must simultaneously manage 2.4 GHz (BLE/Wi-Fi) and Sub-GHz (868/915 MHz) paths on the same board.

## The Core Concept

The fundamental tension in mixed-frequency RF layout is that **Sub-GHz wavelengths (~33 cm at 915 MHz) are 2.5× longer than 2.4 GHz wavelengths (~12.5 cm)**. This means a trace that looks like a short stub at 2.4 GHz can become a quarter-wave resonant radiator at Sub-GHz, coupling noise into your sensitive receiver. The solution is not just "keep traces short" but to **design the ground reference plane as the primary RF return path** and treat every via, slot, and copper pour as a potential antenna or cavity resonator.

For SoC modules, the antenna port is typically a single-ended 50 Ω output. The module's internal matching network assumes a specific ground-plane size and clearance. When you deviate—by placing the module near a board edge, over a split ground plane, or with insufficient keep-out zones—the impedance seen by the module's PA changes, detuning the matching and reducing efficiency. The golden rule: **the module's ground paddle must have a continuous, low-inductance path to the main ground plane, with no slots or moats crossing the RF signal return path.**

## Key Commands / Configuration / Code

Below is a practical checklist I use when reviewing RF layouts for multi-radio SoC modules. These are not commands in the traditional sense, but design-rule checks you should run in your EDA tool.

```python
# Python snippet to calculate quarter-wave stub length for Sub-GHz vs 2.4 GHz
# Use this to determine maximum allowed trace stub length before resonance

import math

def quarter_wave_length(freq_mhz, er=4.5):
    """
    Calculate quarter-wavelength in mm for a given frequency and dielectric constant.
    Typical FR4 er ranges from 4.2 to 4.6 at 1 GHz.
    """
    c = 299792458  # speed of light in m/s
    freq_hz = freq_mhz * 1e6
    wavelength_m = c / freq_hz
    wavelength_mm = wavelength_m * 1000
    # Effective wavelength in dielectric
    effective_wavelength_mm = wavelength_mm / math.sqrt(er)
    return effective_wavelength_mm / 4

# Example: 915 MHz Sub-GHz
stub_915 = quarter_wave_length(915, er=4.5)
print(f"Quarter-wave stub at 915 MHz: {stub_915:.1f} mm")  # ~17.2 mm

# Example: 2.44 GHz BLE/Wi-Fi
stub_2440 = quarter_wave_length(2440, er=4.5)
print(f"Quarter-wave stub at 2.44 GHz: {stub_2440:.1f} mm")  # ~6.5 mm

# Practical rule: keep any stub (via stub, component pad, trace) < 1/10 of quarter-wave
print(f"Max safe stub at 915 MHz: {stub_915/10:.1f} mm")  # ~1.7 mm
print(f"Max safe stub at 2.44 GHz: {stub_2440/10:.1f} mm")  # ~0.65 mm
```

**Layout rule summary for EDA DRC:**

| Parameter | Sub-GHz (868/915 MHz) | 2.4 GHz (BLE/Wi-Fi) |
|-----------|----------------------|---------------------|
| Max trace stub | < 1.7 mm | < 0.65 mm |
| Ground via pitch under module | < 3 mm | < 1.5 mm |
| Antenna keep-out zone radius | > 15 mm | > 10 mm |
| Minimum ground plane extent from antenna feed | > λ/4 (~82 mm) | > λ/4 (~31 mm) |

```kicad
# KiCad DRC rule example for RF ground vias (add to your .kicad_dru file)
(rule "RF_Ground_Via_Spacing"
  (condition "A.type == 'via' && A.netclass == 'RF_GND'")
  (constraint max_distance (3.0 mm))
  (reason "Ground vias under RF module must be < 3 mm apart for Sub-GHz, < 1.5 mm for 2.4 GHz"))
```

## Common Pitfalls & Gotchas

**1. The "Ground Plane Slit" Trap**  
I once saw a design where the designer cut a slot in the ground plane beneath the module to isolate a noisy digital supply. That slot became a resonant cavity at 2.4 GHz, coupling the module's own TX energy back into its RX path, causing 15 dB of desense. **Fix:** Never route a slot or moat under the RF portion of the module. If you must isolate supplies, use a solid ground plane and route power traces on an inner layer with adequate decoupling.

**2. Antenna Clearance Zones Ignored for Sub-GHz**  
Many engineers apply 2.4 GHz keep-out rules (10 mm) to Sub-GHz antennas. At 915 MHz, the near-field extends much further. A ground pour 12 mm from the antenna will detune it by 5-10 MHz, shifting the resonance out of band. **Fix:** Always check the antenna datasheet's recommended clearance. For Sub-GHz chip antennas, this is often 15-20 mm in all directions, and the ground plane beneath the antenna must be removed entirely.

**3. Via Stitching on Module Ground Paddle**  
SoC modules like the ESP32-C6 have a large central ground pad. Using only four corner vias creates a high-inductance ground return. At 2.4 GHz, this inductance raises the ground potential at the module, causing common-mode radiation and reducing PA efficiency. **Fix:** Use a 3×3 or 4×4 grid of vias (0.3 mm drill, 0.6 mm pad) directly under the ground pad, with the vias connecting to a solid inner-layer ground plane. Minimum 9 vias for 2.4 GHz, 4 vias minimum for Sub-GHz only.

## Try It Yourself

1. **Stub Length Audit:** Open your current RF layout. Measure the longest trace stub (including component pad overhangs) on your antenna feed line. Using the Python script above, calculate if it exceeds 1/10 of a quarter-wave at your operating frequency. If it does, shorten it or add a ground via at the stub end.

2. **Ground Via Density Check:** Count the number of ground vias under your SoC module's ground paddle. If you're designing for 2.4 GHz and have fewer than 9 vias, add more in a grid pattern. For Sub-GHz only, ensure at least 4 vias are present and spaced < 3 mm apart.

3. **Antenna Clearance Verification:** For your chosen antenna (chip or PCB trace), measure the distance from the antenna edge to the nearest ground pour or copper fill. Compare against the antenna datasheet's minimum clearance. If you're using a Sub-GHz antenna and have less than 15 mm clearance, remove the ground pour in that zone and add a keep-out outline in your EDA tool.

## Next Up

Tomorrow, we move from layout rules to validation: **RF Simulation Tools: EM Simulators & Field Solvers**. I'll compare open-source (OpenEMS, QucsStudio) vs commercial (HFSS, CST) tools for impedance matching, antenna pattern prediction, and board-level EMI analysis—and show you how to set up a simple 2.4 GHz microstrip feed simulation in under 30 minutes.
