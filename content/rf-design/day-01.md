---
title: "Day 01: RF Fundamentals: Frequency, Wavelength & the RF Spectrum for Embedded"
date: 2026-07-10
tags: ["til", "rf-design", "rf", "spectrum"]
---

## What I Explored Today

I started this RF design journey by getting rock-solid on the two parameters that govern every RF decision: frequency and wavelength. In embedded systems, we don't have the luxury of infinite board space or ideal components — every trace, via, and ground plane is a transmission line once we cross into RF territory. Today I mapped out the RF spectrum bands relevant to embedded work (ISM, cellular, GPS, BLE, Wi-Fi) and internalized why wavelength dictates everything from antenna size to PCB stackup.

## The Core Concept

Here's the fundamental truth: **at RF frequencies, the physical dimensions of your circuit become electrically significant.** The rule of thumb I'm committing to memory: when a trace length exceeds λ/20 (one-twentieth of a wavelength), you can no longer treat it as a simple wire — it's a transmission line with impedance, reflections, and standing waves.

The relationship is brutally simple:

```
λ = c / f
```

Where:
- λ = wavelength in meters
- c = speed of light in vacuum (3×10⁸ m/s)
- f = frequency in Hz

But here's the embedded engineer's twist: signals don't travel through vacuum. They travel through FR-4, Rogers, or ceramic substrates. The velocity factor (VF) slows things down by 40-60% depending on the dielectric. The effective wavelength in your PCB is:

```
λ_eff = (c / f) × VF
```

For FR-4 with εr ≈ 4.5, VF ≈ 0.47. At 2.4 GHz, a free-space wavelength is 12.5 cm, but on your board it's only about 5.9 cm. That means a λ/4 antenna element is just 1.5 cm — suddenly fitting a quarter-wave monopole on a compact IoT board becomes feasible.

The RF spectrum for embedded engineers breaks down into practical bands:

| Band | Frequency Range | Common Use | λ range (free space) |
|------|----------------|------------|----------------------|
| ISM 900 | 902-928 MHz | LoRa, Zigbee | 33-32 cm |
| ISM 2.4 | 2.4-2.4835 GHz | BLE, Wi-Fi, Thread | 12.5-12.1 cm |
| ISM 5 | 5.15-5.85 GHz | Wi-Fi 5/6 | 5.8-5.1 cm |
| Sub-GHz | 315/433/868 MHz | Proprietary, Z-Wave | 95-35 cm |
| GPS L1 | 1.57542 GHz | GNSS | 19 cm |
| Cellular LTE | 700-2600 MHz | NB-IoT, LTE-M | 43-11.5 cm |

The key insight: **lower frequency = longer wavelength = larger antennas but better penetration.** That's why sub-GHz radios (LoRa at 868 MHz) can go kilometers while 5 GHz Wi-Fi struggles through one wall.

## Key Commands / Configuration / Code

When prototyping RF circuits, I use Python to quickly visualize wavelength vs. frequency and calculate trace lengths. Here's the utility I wrote today:

```python
# rf_wavelength_calc.py — Quick wavelength calculator for RF design
import numpy as np

def wavelength(freq_mhz, er=1.0):
    """
    Calculate wavelength in meters.
    er = 1.0 for free space, ~4.5 for FR-4, ~3.5 for Rogers 4350B
    """
    c = 3e8  # speed of light m/s
    freq_hz = freq_mhz * 1e6
    vf = 1 / np.sqrt(er)  # velocity factor
    lam = (c / freq_hz) * vf
    return lam

# Common embedded frequencies
freqs = [315, 433, 868, 915, 2400, 2450, 5200, 5800]
print("Frequency (MHz) | Free-space λ (cm) | FR-4 λ (cm) | λ/4 on FR-4 (cm)")
print("-" * 75)
for f in freqs:
    lam_free = wavelength(f, er=1.0) * 100
    lam_fr4 = wavelength(f, er=4.5) * 100
    lam_quarter = lam_fr4 / 4
    print(f"{f:>14d} | {lam_free:>16.1f} | {lam_fr4:>11.1f} | {lam_quarter:>16.1f}")
```

Output for reference:
```
Frequency (MHz) | Free-space λ (cm) | FR-4 λ (cm) | λ/4 on FR-4 (cm)
---------------------------------------------------------------------------
           315 |               95.2 |          44.9 |             11.2
           433 |               69.3 |          32.7 |              8.2
           868 |               34.6 |          16.3 |              4.1
           915 |               32.8 |          15.5 |              3.9
          2400 |               12.5 |           5.9 |              1.5
          2450 |               12.2 |           5.8 |              1.4
          5200 |                5.8 |           2.7 |              0.7
          5800 |                5.2 |           2.4 |              0.6
```

For quick field calculations at the bench, I use this awk one-liner on my Linux workstation:

```bash
# Calculate wavelength in cm for a given frequency in MHz
# Usage: ./wl.sh 2450
echo "scale=2; 30000 / $1" | bc  # free space λ in cm
echo "scale=2; 30000 / ($1 * sqrt(4.5))" | bc  # FR-4 λ in cm
```

## Common Pitfalls & Gotchas

**1. Ignoring the dielectric when estimating antenna length**
I've seen engineers cut a λ/4 wire for 868 MHz as 8.6 cm (free space) and wonder why the antenna is detuned. On FR-4, that same quarter-wave is 4.1 cm. Always use the effective wavelength for your substrate.

**2. Confusing ISM band center frequencies with channel spacing**
The 2.4 GHz ISM band spans 2.4-2.4835 GHz, but BLE uses 40 channels at 2 MHz spacing, while Wi-Fi uses 14 channels at 20/40/80 MHz. Your filter and matching network must cover the full band, not just the center frequency.

**3. Treating ground planes as infinite at RF**
A ground plane that's smaller than λ/2 at your operating frequency will radiate and couple. For a 433 MHz design, that means you need at least 34 cm of ground plane — often impossible on a compact PCB. This forces you into ground-plane-free antenna designs (e.g., meandered monopoles).

## Try It Yourself

1. **Calculate your project's λ/20 threshold.** Take the highest frequency in your current design and compute the trace length at which you must switch from lumped to distributed element models. Measure your longest signal trace — is it over that threshold?

2. **Bandwidth check.** For your target ISM band, calculate the fractional bandwidth: (f_max - f_min) / f_center × 100%. If it's >10%, your matching network needs to be broadband — a simple LC match won't cut it.

3. **Substrate velocity factor.** Measure or look up the εr of your PCB material. Calculate the VF and the effective wavelength at your operating frequency. Compare to free space — note the 40-60% reduction.

## Next Up

Tomorrow I'm diving into **RF PCB Materials: Dielectric Constant, Loss Tangent & Substrate Choice**. We'll compare FR-4, Rogers 4350B, and ceramic-filled PTFE, and I'll show you how to use a VNA to measure dielectric constant from a test coupon. The material choice alone can make or break your RF link budget.
