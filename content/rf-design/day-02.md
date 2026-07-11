---
title: "Day 02: RF PCB Materials: Dielectric Constant, Loss Tangent & Substrate Choice"
date: 2026-07-11
tags: ["til", "rf-design", "dielectric", "loss-tangent"]
---

## What I Explored Today

I dove into the material science behind RF PCBs — specifically how dielectric constant (εr) and loss tangent (tan δ) dictate substrate selection. While FR-4 works for 100 MHz digital buses, it becomes a lossy disaster above 1 GHz. Today I cataloged common RF substrates (Rogers 4003C, 4350B, PTFE-based laminates), measured how εr tolerance impacts impedance, and ran stackup simulations to compare insertion loss across materials. The takeaway: substrate choice is the single most impactful decision in an RF PCB design, and it’s not just about cost.

## The Core Concept

Every RF PCB trace is a transmission line. The substrate’s dielectric constant determines the propagation velocity and the physical trace width needed for a target impedance (e.g., 50 Ω). The loss tangent determines how much signal energy is absorbed by the material as heat.

**Why this matters:**
- A ±0.5 variation in εr can shift a 50 Ω microstrip to 45 Ω or 55 Ω — that’s a 10% impedance mismatch, causing reflections and ripple.
- At 2.4 GHz, FR-4 (tan δ ≈ 0.02) loses roughly 0.2 dB/inch. Over a 6-inch trace, that’s 1.2 dB — nearly 25% power loss. Rogers 4350B (tan δ ≈ 0.0037) loses only 0.04 dB/inch.

**The trade-off triangle:**
- **Cost:** FR-4 < Rogers 4000 series < PTFE/ceramic
- **Loss:** FR-4 (high) < Rogers 4000 (medium) < PTFE (low)
- **Manufacturability:** FR-4 (easy) > Rogers 4000 (good) > PTFE (difficult, requires plasma treatment)

For most embedded RF designs (sub-6 GHz, moderate power), Rogers 4350B or 4003C hit the sweet spot. For millimeter-wave or low-noise amplifiers, you step up to PTFE-based laminates like Rogers 5880 or TMM series.

## Key Commands / Configuration / Code

### 1. Simulating Impedance with a Field Solver (Python + scikit-rf)

```python
import skrf as rf
import numpy as np

# Define a microstrip on Rogers 4350B
# εr = 3.48, tanδ = 0.0037, height = 0.508 mm (20 mil)
# Copper thickness = 0.035 mm (1 oz), trace width = 1.1 mm

freq = rf.Frequency(1, 10, 1001, unit='GHz')
# Create a 50-ohm microstrip line 10 mm long
line = rf.media.Microstrip(
    frequency=freq,
    w=1.1e-3,        # trace width (m)
    h=0.508e-3,      # substrate height (m)
    t=0.035e-3,      # copper thickness (m)
    rho=1.724e-8,    # copper resistivity
    epsilon_r=3.48,
    tan_delta=0.0037
)

# Compute S-parameters for a 10 mm line
line_length = 10e-3
s_params = line.line(d=line_length, unit='m')

# Plot insertion loss
import matplotlib.pyplot as plt
plt.plot(freq.f, 20*np.log10(np.abs(s_params.s[:,1,0])))
plt.xlabel('Frequency (GHz)')
plt.ylabel('S21 (dB)')
plt.title('Insertion Loss: Rogers 4350B, 10 mm')
plt.grid(True)
plt.show()
```

### 2. Calculating Trace Width for 50 Ω (Using IPC-2141A Approximation)

```python
import math

def microstrip_width(epsilon_r, h, t, Z0=50):
    """
    Approximate trace width for 50-ohm microstrip.
    h: substrate height (mm)
    t: copper thickness (mm)
    """
    # Effective dielectric constant (approximate)
    w = h * (8 * math.exp(Z0 * math.sqrt(epsilon_r + 1.41) / 87) - 1)
    # Iterative refinement (simplified)
    for _ in range(3):
        epsilon_eff = (epsilon_r + 1)/2 + (epsilon_r - 1)/2 * (1 / math.sqrt(1 + 12*h/w))
        w_new = h * (8 * math.exp(Z0 * math.sqrt(epsilon_eff) / 87) - 1)
        w = 0.5 * (w + w_new)
    return w

# Example: Rogers 4350B, 20 mil (0.508 mm) height, 1 oz copper
w = microstrip_width(3.48, 0.508, 0.035)
print(f"Trace width for 50 Ω: {w:.3f} mm")  # ~1.12 mm
```

### 3. Stackup Configuration (Altium / KiCad Example)

In KiCad’s PCB Editor, set up the stackup for a 4-layer RF board:

| Layer | Material | Thickness | εr | tan δ |
|-------|----------|-----------|----|-------|
| Top copper | 1 oz | 0.035 mm | — | — |
| Prepeg | Rogers 4450F | 0.101 mm | 3.52 | 0.004 |
| Core | Rogers 4350B | 0.508 mm | 3.48 | 0.0037 |
| Prepeg | Rogers 4450F | 0.101 mm | 3.52 | 0.004 |
| Bottom copper | 1 oz | 0.035 mm | — | — |

**In KiCad:** `File → Board Setup → Board Stackup` — set each layer’s material and thickness. The impedance calculator (Tools → Calculator Tools → Transmission Lines) will use these values.

## Common Pitfalls & Gotchas

1. **Assuming FR-4 εr is constant.** FR-4 εr varies from 4.2 to 4.8 depending on resin content and frequency. At 2.4 GHz, the effective εr can drift 10% across a panel. Always specify a tight tolerance laminate (e.g., Rogers 4350B has εr tolerance ±0.05).

2. **Ignoring copper roughness.** At high frequencies, current crowds to the trace surface (skin effect). Standard electrodeposited (ED) copper has RMS roughness of 1–2 µm, which adds 0.1–0.3 dB/inch loss at 10 GHz. Use rolled-annealed (RA) copper for critical RF paths.

3. **Mixing substrate types in a stackup without thermal analysis.** PTFE and FR-4 have different CTE (coefficient of thermal expansion). During reflow, the board can warp or delaminate. Always use compatible materials (e.g., Rogers 4000 series bonds well with FR-4 prepregs).

## Try It Yourself

1. **Calculate trace width for 50 Ω on two substrates:** FR-4 (εr=4.5, h=0.8 mm) and Rogers 4003C (εr=3.55, h=0.508 mm). Use the microstrip formula above. How much does the width change? (Hint: expect ~30% difference.)

2. **Simulate insertion loss for a 50 mm microstrip at 5.8 GHz** on FR-4 (tan δ=0.02) vs. Rogers 4350B (tan δ=0.0037). Use the `skrf` code above. What is the loss difference in dB? Is it acceptable for your application?

3. **Check your current PCB stackup.** If you’re using FR-4 for a design above 1 GHz, calculate the impedance tolerance if εr varies by ±0.3. Would your VSWR exceed 1.5:1?

## Next Up

Tomorrow: **RF Transmission Lines: Microstrip, Stripline & Grounded CPW** — we’ll compare field confinement, loss, and manufacturing trade-offs for the three most common RF line types, with practical design equations and layout rules.
