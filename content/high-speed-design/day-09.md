---
title: "Day 09: Power Integrity: Decoupling Capacitor Placement & PDN Impedance"
date: 2026-07-18
tags: ["til", "high-speed-design", "power-integrity", "decoupling"]
---

## What I Explored Today

Today I dove deep into the practical reality of Power Distribution Network (PDN) design: decoupling capacitor placement isn't just about capacitance value—it's about minimizing the impedance loop at the frequencies your IC actually switches. I spent the morning simulating a 1.2V core rail for a 1 GHz FPGA, measuring the impedance profile from DC to 10 GHz, and discovered that a 10 nF capacitor placed 50 mils away resonates beautifully, while the same cap at 500 mils is practically invisible above 200 MHz. The takeaway: inductance kills decoupling, and placement is everything.

## The Core Concept

A PDN's job is to deliver clean, stable voltage to every transistor on a die as it draws current in nanosecond bursts. The impedance of the PDN—from VRM through PCB planes, vias, and decoupling caps to the die—must be kept below a target impedance Z_target = V_rail × V_ripple / I_transient. For a 1.2V rail with 3% ripple and a 5A transient, that's about 7.2 mΩ.

Here's the critical insight: decoupling capacitors are only effective at frequencies where their impedance is dominated by capacitance, not parasitic inductance. A capacitor's self-resonant frequency (SRF) is f_SRF = 1 / (2π √(L_ESL × C)). Above SRF, the cap looks inductive and its impedance rises at 20 dB/decade.

But the real problem is mounting inductance. Every via, every trace, every millimeter of PCB copper between the capacitor pad and the IC power pin adds inductance. A 0402 100 nF cap might have 400 pH ESL, but add two vias at 500 pH each and a 200 mil trace at 10 nH/inch, and you've got over 1.5 nH of loop inductance. That shifts the effective SRF from ~25 MHz down to ~13 MHz—and above that, the cap is useless.

The solution: place decoupling caps as close as possible to the IC power pins, use multiple vias in parallel to reduce inductance, and choose capacitor values that create a flat impedance profile across the frequency band of interest. For high-speed designs, this means using a mix of bulk (10-100 µF), mid-frequency (0.1-1 µF), and high-frequency (10-100 nF) caps, each placed at distances proportional to their effective frequency range.

## Key Commands / Configuration / Code

Here's a Python snippet using `scikit-rf` to simulate PDN impedance with and without proper placement. This is what I used today to visualize the difference a few hundred mils makes.

```python
import skrf as rf
import numpy as np
import matplotlib.pyplot as plt

# Define frequency sweep from 1 MHz to 10 GHz
freq = rf.Frequency(1, 10000, npoints=1000, unit='MHz')

# Model a 100 nF capacitor with 400 pH ESL and 20 mOhm ESR
C = 100e-9
ESL = 400e-12
ESR = 0.020
Z_cap = 1/(1j*2*np.pi*freq.f * C) + 1j*2*np.pi*freq.f * ESL + ESR

# Model mounting inductance: 2 vias (500 pH each) + 200 mil trace (10 nH/inch)
# 200 mils = 0.2 inches -> 2 nH trace inductance
L_mount = 2 * 500e-12 + 0.2 * 10e-9  # 3 nH total
Z_mount = 1j*2*np.pi*freq.f * L_mount

# Total impedance with and without mounting parasitics
Z_total_ideal = Z_cap
Z_total_real = Z_cap + Z_mount

# Plot
plt.figure(figsize=(10, 6))
plt.semilogx(freq.f/1e6, 20*np.log10(np.abs(Z_total_ideal)), label='Ideal (no mounting)')
plt.semilogx(freq.f/1e6, 20*np.log10(np.abs(Z_total_real)), label='Real (3 nH mounting)')
plt.axhline(y=20*np.log10(0.0072), color='r', linestyle='--', label='Z_target = 7.2 mΩ')
plt.xlabel('Frequency (MHz)')
plt.ylabel('Impedance (dBΩ)')
plt.title('PDN Impedance: Ideal vs. Real Placement')
plt.legend()
plt.grid(True)
plt.show()
```

For a real PCB, use your EDA tool's PDN analyzer (e.g., Altium PDN Analyzer, HyperLynx PI) to extract loop inductance from layout. A typical rule of thumb: for a 0402 cap, keep the via-to-pad distance under 20 mils, and use at least two vias per cap for high-speed rails.

## Common Pitfalls & Gotchas

**1. Ignoring the anti-resonance peak.** When you parallel capacitors of different values (e.g., 10 µF and 0.1 µF), their ESL and ESR create a parallel LC tank at the frequency where one cap's inductive impedance equals the other's capacitive impedance. This anti-resonance can spike impedance 10-100x above target. Solution: use capacitors with the same case size and dielectric to keep ESL similar, or add a lossy ferrite bead to damp the peak.

**2. Placing caps too far from the IC.** I've seen designs where a 0.1 µF cap is placed 1 inch away "because it's close enough." At 500 MHz, a 1-inch trace has ~10 nH inductance, which makes that cap look like a 31 Ω resistor—completely useless for high-frequency decoupling. Always place the smallest-value caps (10-100 nF) within 50 mils of the power pin, ideally on the same layer as the IC.

**3. Using too few vias for the return path.** A single via has about 500 pH inductance. For a 1 GHz IC drawing 5 A transient, that via alone creates 3.14 V of L di/dt noise—catastrophic. Always use multiple vias in parallel (4-8 for high-current rails) to reduce effective inductance. And don't forget the ground vias: the loop must include the return path.

## Try It Yourself

1. **Simulate your own PDN.** Use the Python script above with your actual capacitor values (check datasheets for ESL/ESR). Vary the mounting inductance from 0.5 nH to 5 nH and note where the impedance crosses Z_target. This will tell you the maximum distance you can place a cap.

2. **Measure loop inductance on your PCB.** If you have a VNA, measure the S11 of a power-gnd pair at the IC location. Convert to impedance: Z = 50 × (1+S11)/(1-S11). Compare the resonant frequency to your cap's datasheet SRF—the shift tells you your mounting inductance.

3. **Optimize a decoupling network.** Pick three capacitor values (e.g., 10 µF, 0.1 µF, 10 nF) and simulate their parallel impedance with realistic ESL. Adjust values until the impedance stays below Z_target from 1 MHz to 10 GHz. Try adding a 1 nF cap and see if it helps or hurts the anti-resonance.

## Next up

Tomorrow, we move from power to signals: **Signal Integrity Simulation: S-Parameters & Eye Diagrams**. I'll show you how to extract S-parameters from a differential pair, simulate an eye diagram, and diagnose issues like ISI and crosstalk before you spin a board.
