---
title: "Day 07: Antenna Basics: Monopole, PIFA & Chip Antennas for Embedded"
date: 2026-07-16
tags: ["til", "rf-design", "antenna", "pifa"]
---

## What I Explored Today

Today I dug into the three most common antenna types for embedded RF designs: the quarter-wave monopole, the planar inverted-F antenna (PIFA), and the ubiquitous chip antenna. Each has a distinct place in the design space, and choosing wrong can kill a product’s range or force a respin. I focused on the practical tradeoffs: impedance, bandwidth, ground plane dependency, and the physical constraints that matter when you’re squeezing an antenna into a 50 mm × 30 mm PCB.

## The Core Concept

An antenna is a transducer that converts guided waves on a transmission line into free-space waves. For embedded engineers, the key parameter is **impedance bandwidth** — the frequency range over which the antenna presents a reasonable match (typically VSWR < 2:1, or return loss < -10 dB) to a 50 Ω feed.

The three antenna types differ fundamentally in how they achieve resonance and how they interact with the ground plane:

- **Monopole**: A quarter-wavelength (λ/4) vertical element above an infinite ground plane. The ground plane acts as the other half of a dipole via image theory. In practice, the “ground plane” is your PCB’s copper pour, which is never infinite. The monopole’s impedance is ~36 Ω at resonance, requiring a matching network. Bandwidth is proportional to the element’s diameter (or trace width). For 2.4 GHz, λ/4 ≈ 31 mm — too long for many products.

- **PIFA**: A shorted patch antenna folded to reduce height. It’s essentially a λ/4 resonator with a ground plane on one side and a radiating element on the other, shorted at one end. The feed point is placed along the shorted edge to set the input impedance (typically 50 Ω without external matching). The PIFA’s key advantage: it can be tuned by adjusting the shorting pin location and the gap between the patch and ground. Height above ground is critical — 3–5 mm for 2.4 GHz.

- **Chip Antenna**: A miniature ceramic package (typically 3.2 mm × 1.6 mm × 1.1 mm for 2.4 GHz) that uses high-dielectric-constant ceramics to shrink the effective wavelength. The chip itself is only part of the antenna — it requires a specific ground clearance pattern and matching network per the datasheet. Chip antennas are the easiest to integrate but have the narrowest bandwidth and lowest efficiency (often 40–60% vs. 80–90% for a good monopole).

## Key Commands / Configuration / Code

### 1. Simulating a Quarter-Wave Monopole with Python (using scikit-rf)

```python
import skrf as rf
import numpy as np

# Create a 50-ohm transmission line representing the feed
freq = rf.Frequency(2.4, 2.5, npoints=101, unit='GHz')
line = rf.media.DefinedGammaZ0(freq, gamma=1j*2*np.pi*freq.f/3e8, z0=50)

# Monopole model: series RLC resonance at 2.45 GHz
# R_rad = 36 ohms, L and C tuned for BW ~100 MHz
R_rad = 36
Q = 25  # typical for a thin trace monopole
f0 = 2.45e9
L_ant = R_rad / (2*np.pi*f0) * Q
C_ant = 1 / ((2*np.pi*f0)**2 * L_ant)

# Create the antenna as a one-port network
ant = rf.Network(name='Monopole')
ant.frequency = freq
s11 = (50 - (R_rad + 1j*2*np.pi*freq.f*L_ant - 1j/(2*np.pi*freq.f*C_ant))) / \
      (50 + (R_rad + 1j*2*np.pi*freq.f*L_ant - 1j/(2*np.pi*freq.f*C_ant)))
ant.s = s11.reshape(-1,1,1)

# Plot return loss
ant.plot_s_db(m=0, n=0)
```

### 2. PIFA Tuning in HFSS (pseudo-code for parametric sweep)

```matlab
' HFSS script snippet for PIFA parametric sweep
' Variables: feed_offset, short_width, patch_length
Dim oDesign As Object
Set oDesign = GetApp().GetActiveProject().GetActiveDesign()

' Sweep feed position along shorted edge
oDesign.ChangeProperty Array("NAME:AllTabs", _
    Array("NAME:LocalVariables", _
        Array("NAME:PropServers", "LocalVariables"), _
        Array("NAME:ChangedProps", _
            Array("NAME:feed_offset", "TAB", 2.0, "Unit", "mm"))))

' Run sweep
oDesign.Solve()
```

### 3. Chip Antenna Matching (from TDK ANT016008LCS2442MA1 datasheet)

```python
# Typical pi-network for chip antenna at 2.45 GHz
# Antenna impedance at resonance: ~15 - j30 ohms (varies by board)
# Target: 50 ohms

# Using a Smith chart or calculator:
# Series inductor: L1 = 2.2 nH (0402, Murata LQW15)
# Shunt capacitor: C1 = 1.0 pF (0402, Murata GJM15)
# Series capacitor: C2 = 0.8 pF (0402, Murata GJM15)

# Layout note: keep matching components within 2 mm of antenna feed pin
# Ground keep-out: 5 mm × 5 mm area under antenna, no copper on any layer
```

## Common Pitfalls & Gotchas

1. **The “infinite ground” myth for monopoles**: A quarter-wave monopole needs a ground plane at least λ/2 in diameter to approach its theoretical 36 Ω impedance. On a tiny IoT board (say 20 mm × 30 mm at 2.4 GHz), the ground is only ~0.16λ × 0.24λ. The actual impedance can be 20–80 Ω, and the resonance shifts up by 10–15%. Always simulate with your actual board geometry.

2. **PIFA height vs. bandwidth**: A PIFA’s bandwidth is directly proportional to its height above the ground plane. At 2.4 GHz, a 3 mm height gives ~80 MHz bandwidth; at 1 mm height, you’re lucky to get 30 MHz. If your enclosure forces a 1 mm gap, don’t use a PIFA — use a chip antenna with a wider bandwidth spec.

3. **Chip antenna ground clearance is non-negotiable**: Every chip antenna datasheet shows a specific ground clearance pattern (often a rectangular void on all copper layers). Ignoring this — e.g., running a ground pour under the antenna “because it’s only a small area” — can detune the antenna by 100 MHz or more. I’ve seen designs where a 0.5 mm ground extension into the clearance zone killed the 2.4 GHz match entirely.

## Try It Yourself

1. **Measure a chip antenna’s detuning**: Take a 2.4 GHz chip antenna evaluation board (e.g., TDK ANT016008LCS2442MA1). Measure S11 with a VNA. Then place a 10 mm × 10 mm copper tape patch on the ground clearance area and re-measure. Note the frequency shift and return loss degradation.

2. **Simulate a monopole with different ground plane sizes**: Using the Python script above, change the ground plane size by adjusting the Q factor (smaller ground = lower Q, wider bandwidth but worse match). Plot S11 for Q = 10, 20, 30. Which gives the best bandwidth at -10 dB?

3. **Design a PIFA feed position sweep**: In your favorite EM simulator (HFSS, CST, or even openEMS), create a simple PIFA model at 2.45 GHz with a fixed patch size (e.g., 15 mm × 8 mm, height 3 mm). Parametrically sweep the feed point along the shorted edge from 0.5 mm to 5 mm from the short. Plot input impedance on a Smith chart and find the position that gives 50 Ω.

## Next Up

Tomorrow: **Antenna Placement & PCB Keep-Out Zones** — how to avoid coupling to ground planes, batteries, and shields, and the specific keep-out rules that make or break an embedded antenna design.
