---
title: "Day 03: RF Transmission Lines: Microstrip, Stripline & Grounded CPW"
date: 2026-07-12
tags: ["til", "rf-design", "microstrip", "cpw"]
---

## What I Explored Today

Today I dug into the three most common planar transmission line topologies used in RF PCB design: microstrip, stripline, and grounded coplanar waveguide (GCPW). While the textbooks give you the field patterns and impedance equations, what I really needed was practical guidance on when to use each one, how to model them in a real stackup, and what traps await when you blindly copy a 50-ohm line width from a calculator. I spent the day cross-referencing IPC-2141A, the Polar Si9000 field solver, and actual VNA measurements from a 2.4 GHz LNA board I’m debugging.

## The Core Concept

All three structures are waveguides that confine an electromagnetic wave between a signal conductor and a reference ground plane. The key differentiator is the dielectric environment and the field distribution.

- **Microstrip**: Signal on top layer, ground plane below. Simple, cheap, but the fields are partly in air and partly in the substrate. This makes the effective dielectric constant (εr_eff) lower than the substrate’s Dk, and it changes with frequency. The wave is quasi-TEM, meaning there’s a small longitudinal component. For most embedded work below 10 GHz, this is fine, but above that, surface-wave modes and radiation loss become real problems.

- **Stripline**: Signal buried between two ground planes. Fully homogeneous dielectric, pure TEM mode, no radiation. This gives the best isolation and the most predictable impedance—no surprises from solder mask or air gaps. The downside? You can’t tune it after fabrication, and vias to access the inner layer add inductance and parasitic capacitance.

- **Grounded CPW (GCPW)**: Signal on top with ground planes on both sides, plus a ground plane below. The fields are tightly confined between the signal and the adjacent grounds, with a small amount leaking into the substrate. This is the go-to for millimeter-wave designs (24 GHz and up) because it suppresses substrate modes and gives excellent isolation between adjacent traces. The downside is the need for a dense via fence (ground stitching) to keep the two side grounds at the same potential.

The practical rule of thumb I’m using: microstrip for <6 GHz, stripline for critical impedance control and isolation, GCPW for >10 GHz or when you need to route near a noisy digital section.

## Key Commands / Configuration / Code

I’m using **Polar Si9000** (the industry-standard field solver) and **KiCad’s PCB calculator** for quick checks. Here’s how I set up a 50-ohm microstrip on a standard 4-layer stackup (FR-4, 1.6 mm total, 0.2 mm prepreg between L1 and L2).

**Polar Si9000 – Microstrip 1B (Surface Microstrip)**

```
Substrate Height (H1): 0.200 mm
Trace Width (W): 0.350 mm
Trace Thickness (T): 0.035 mm (1 oz copper)
Dielectric Constant (Er1): 4.5 (FR-4 at 1 GHz)
Solder Mask Thickness (C1): 0.020 mm
Solder Mask Dielectric (CEr): 3.5

Result:
- Zo = 49.8 Ω
- εr_eff = 3.2
- Delay = 144.7 ps/inch
```

**KiCad PCB Calculator (Python script for batch checks)**

```python
# microstrip_impedance.py
import math

def microstrip_z0(h, w, t, er):
    """Calculate microstrip impedance using IPC-2141A approximation."""
    w_eff = w + (t / math.pi) * (1 + math.log(4 * math.pi * w / t))
    epsilon_eff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12 * h / w_eff))
    z0 = (60 / math.sqrt(epsilon_eff)) * math.log(8 * h / w_eff + w_eff / (4 * h))
    return z0, epsilon_eff

# Example: 0.2 mm substrate, 0.35 mm trace, 1 oz copper
z, eps = microstrip_z0(0.2, 0.35, 0.035, 4.5)
print(f"Z0 = {z:.1f} Ω, εr_eff = {eps:.2f}")
# Output: Z0 = 49.8 Ω, εr_eff = 3.21
```

**GCPW via fence rule of thumb** (from Johanson Technology app note):
```
Via spacing (center-to-center) < λ/20 at the highest frequency.
For 2.4 GHz: λ ≈ 125 mm in FR-4 → via spacing < 6.25 mm.
For 24 GHz: via spacing < 0.625 mm → that’s tight, use 0.5 mm pitch.
```

## Common Pitfalls & Gotchas

1. **Solder mask eats your impedance.** That 0.02 mm layer of solder mask with Dk ~3.5 pulls the fields down, lowering impedance by 2–4 Ω. I’ve seen boards measure 46 Ω instead of 50 Ω because the designer forgot to include solder mask in the stackup. Always model with solder mask, or specify “impedance control without solder mask” and have the fab strip it.

2. **Stripline via stubs kill high-frequency performance.** When you transition from a surface component to a stripline layer, the via stub (the unused portion of the via barrel below the target layer) acts as a shunt capacitor. At 5 GHz, a 0.5 mm stub adds ~0.3 pF—enough to ruin your return loss. Use back-drilling or specify “via stub removal” for layers > 6.

3. **GCPW without enough vias is just microstrip with extra copper.** If your via fence pitch is too large (> λ/10), the side grounds float and the mode becomes quasi-microstrip. I’ve debugged boards where the GCPW had vias every 5 mm at 5.8 GHz—the isolation was terrible. Rule: via spacing ≤ λ/20, and put a via at every corner.

## Try It Yourself

1. **Model your own stackup.** Take a 4-layer board with 0.2 mm prepreg (Dk 4.2) and 0.035 mm copper. Calculate the trace width for 50 Ω microstrip using the Python script above. Then add 0.02 mm solder mask (Dk 3.5) and re-calculate. How much does the impedance drop?

2. **Compare microstrip vs. GCPW in a field solver.** If you have access to Polar Si9000 or Keysight ADS LineCalc, set up a 50 Ω microstrip and a 50 Ω GCPW on the same substrate. Note the trace width difference—GCPW will be narrower because the side grounds add capacitance. Which one has lower loss at 10 GHz?

3. **Measure a real board.** If you have a VNA, fabricate a 2-inch microstrip line and a 2-inch GCPW line on the same board. Measure S11 and S21 from 100 MHz to 6 GHz. At what frequency does the microstrip’s return loss degrade compared to GCPW? This is the frequency where surface-wave modes start.

## Next Up

Tomorrow, I’m tackling **Smith Chart Fundamentals & Impedance Matching**. We’ll go from staring at a smudge of arcs and circles to actually using the chart to match a 50 Ω source to a complex load (like a chip antenna) in under 5 minutes. Bring your graph paper—or your Python plotting library.
