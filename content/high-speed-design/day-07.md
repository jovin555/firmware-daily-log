---
title: "Day 07: Via Stubs & Backdrilling for High-Speed Signals"
date: 2026-07-16
tags: ["til", "high-speed-design", "via-stubs", "backdrilling"]
---

## What I Explored Today

Today I dove deep into via stubs—the single most common impedance discontinuity that kills signal integrity on multilayer PCBs at 5+ Gbps. I simulated the resonant nulls caused by a 40-mil stub on a 10 Gbps channel, then validated the fix: backdrilling. The difference between a 12-layer board with and without backdrilling is the difference between a clean eye diagram and a closed one.

## The Core Concept

When you route a high-speed signal on an inner layer (say Layer 4 of a 12-layer stackup), the via barrel continues all the way down to the bottom layer. That unused portion of the via—from the signal layer to the bottom—is the *stub*. It acts as an open-circuit transmission line stub, creating a quarter-wave resonance that introduces a deep notch in the insertion loss (S21) at the frequency where the stub length equals λ/4.

The math: a 50-mil stub in FR4 (εr ≈ 4.0) has a quarter-wave resonance at roughly:

f_res = (c / (4 * L_stub * sqrt(εr_eff))) ≈ (3e8 m/s) / (4 * 0.050" * 0.0254 m/in * 2.0) ≈ 29.5 GHz

That’s a problem at 10 Gbps (5 GHz fundamental) because the third harmonic (15 GHz) lands right in the resonant dip. The stub doesn't just cause loss—it causes *frequency-dependent* loss that closes your eye.

Backdrilling removes that stub. A controlled-depth drill bit (typically +6 mil tolerance) drills out the unused via barrel from the bottom, stopping just past the signal layer. The remaining stub is typically 2–8 mils—short enough that its resonant frequency is pushed well above your signal’s bandwidth.

## Key Commands / Configuration / Code

### 1. Simulating Via Stub Resonance in Keysight ADS (or similar)

```python
# Python pseudo-code using scikit-rf for via stub modeling
import skrf as rf
import numpy as np

# Define stub parameters
stub_length = 50e-3 * 0.0254  # 50 mils in meters
z0 = 50                       # characteristic impedance
f = np.linspace(1e9, 30e9, 1000)

# Open-circuit stub input impedance
# Z_in = -j * Z0 * cot(beta * L)
beta = 2 * np.pi * f * np.sqrt(4.0) / 3e8
z_in = -1j * z0 * 1 / np.tan(beta * stub_length)

# Reflection coefficient
gamma = (z_in - z0) / (z_in + z0)
s11 = 20 * np.log10(np.abs(gamma))

# Find the first resonant null
null_idx = np.argmin(s11)
print(f"Resonant null at {f[null_idx]/1e9:.1f} GHz, S11 = {s11[null_idx]:.1f} dB")
```

### 2. Backdrill Stackup Definition (Altium Designer / Cadence Allegro)

In your PCB layout tool, define backdrill layers in the layer stack manager:

```
Layer Stack (12-layer, 1.6 mm total):
  Top (L1): Signal
  GND (L2): Plane
  Signal (L3): High-speed route
  GND (L4): Plane
  Signal (L5): High-speed route  <-- target layer
  PWR (L6): Power
  GND (L7): Plane
  Signal (L8): Low-speed
  GND (L9): Plane
  Signal (L10): Low-speed
  GND (L11): Plane
  Bottom (L12): Signal

Backdrill specification:
  Drill from bottom (L12) up to L5 + 6 mil clearance
  Backdrill diameter = via pad diameter + 10 mil
  Remaining stub = 6 mils (from L5 bottom to drill stop)
```

### 3. Gerber Backdrill Layer Export (Altium)

In the Gerber output configuration, enable:
- Drill Drawing: `Backdrill.drl`
- NC Drill Format: `4:4` (4 integer, 4 decimal digits for precision)
- Check: "Generate separate drill files for backdrills"

### 4. Simulation Comparison (HyperLynx / SIwave)

Typical insertion loss results for a 10 Gbps channel:

| Condition | S21 at 5 GHz | S21 at 15 GHz | Eye Height |
|-----------|--------------|---------------|------------|
| No backdrill (50 mil stub) | -2.1 dB | -8.7 dB | 180 mV |
| Backdrilled (6 mil stub) | -1.8 dB | -2.3 dB | 420 mV |

The 15 GHz notch drops from -8.7 dB to -2.3 dB—that's the stub resonance being pushed out of band.

## Common Pitfalls & Gotchas

1. **Backdrill tolerance eats your margin.** Most PCB fabs guarantee ±6 mil depth tolerance. If your signal is on Layer 4 and you ask for a 6 mil remaining stub, the *actual* stub could be 0 mil (drill into the signal via) or 12 mil (resonant frequency drops to ~12 GHz). Always design for worst-case: specify remaining stub = 2× tolerance + desired max stub. For a 6 mil target, ask for 18 mil remaining stub, then verify with TDR.

2. **Backdrilling doesn't work on blind/buried vias.** Backdrilling only removes material from the outer layers inward. If your high-speed signal uses a buried via (inner layers only), you can't backdrill it. You must use stacked microvias or skip-layer routing instead.

3. **Don't backdrill power/ground vias.** The stub on a PWR via creates a parallel resonance with the plane capacitance, which can actually *help* decoupling at certain frequencies. Only backdrill signal vias. Mark them with a specific net class in your constraint manager.

4. **Backdrill bits are expensive and slow.** A standard drill hits 150k RPM; backdrill bits run at 30k RPM to control depth. This adds 2–3× to drilling time. Plan for 2–3 week lead time on backdrilled boards.

## Try It Yourself

1. **Simulate a via stub resonance.** Use any RF simulator (or even a Smith chart) to calculate the resonant frequency of a 30-mil stub in FR4. Then calculate what stub length pushes the first resonance above 20 GHz. Verify with a quick Python script.

2. **Inspect your current design.** Open your PCB layout and find the longest via stub on a high-speed differential pair. Measure the distance from the signal layer to the bottom of the board. Is it longer than 20 mils? If yes, add a backdrill constraint for that net class.

3. **Request a backdrill quote.** Call your preferred PCB fab and ask: "What is your minimum remaining stub tolerance for backdrilling? What is the cost adder for a 12-layer board with 50 backdrilled vias?" Compare two fabs. You'll be surprised at the variation.

## Next Up

Tomorrow: **Crosstalk: Near-End & Far-End Coupling Mitigation**—why your 5 mil trace spacing is killing your margin, and how to use guard traces, stripline routing, and differential pair skew to push NEXT/FEXT below -40 dB.
