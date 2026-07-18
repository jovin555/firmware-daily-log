---
title: "Day 09: RF Front-End Design: LNAs, PAs & Filters"
date: 2026-07-18
tags: ["til", "rf-design", "lna", "pa", "filters"]
---

## What I Explored Today

Today I dove into the three critical active and passive blocks that define the performance of any RF front-end: the Low-Noise Amplifier (LNA), the Power Amplifier (PA), and the RF filters that sit between them. I focused on how these components interact in a typical receive/transmit chain, what figures of merit actually matter during selection and simulation, and how to avoid the cascade noise and linearity traps that plague first-pass designs. I spent the afternoon in ADS and LTspice, verifying noise figure cascades and IP3 budgets for a 2.4 GHz ISM-band front-end.

## The Core Concept

The RF front-end is the analog bottleneck of any wireless system. If you get the LNA, PA, and filter chain wrong, no amount of digital baseband magic will fix it. The core principle is a trade-off triangle: **noise figure (NF), linearity (IIP3/P1dB), and gain**. These three parameters are locked in a physics-driven tug-of-war, and every component choice shifts the balance.

For the **LNA**, the goal is to amplify a weak signal (often -100 dBm or lower) while adding as little noise as possible. The LNA’s noise figure dominates the receiver’s overall NF because of the Friis cascade formula: the first stage’s NF is the most critical. However, an LNA with too much gain can saturate the mixer or ADC, and an LNA with high gain often has poor linearity (low IIP3), which causes intermodulation distortion.

For the **PA**, the goal is to deliver maximum power to the antenna (often +20 dBm or more) with high efficiency. The key metrics here are output power at 1 dB compression (P1dB), power-added efficiency (PAE), and adjacent channel power ratio (ACPR). A PA that is too linear wastes battery; one that is too nonlinear splatters energy into adjacent channels and violates regulatory masks.

For **filters**, the goal is to suppress out-of-band blockers and image frequencies while minimizing insertion loss. A filter with 1 dB of loss before the LNA directly adds 1 dB to the system NF. After the PA, filter loss directly reduces radiated power. The filter’s bandwidth, rejection, and group delay variation all matter, but insertion loss is the first thing to optimize.

The key takeaway: never select an LNA, PA, or filter in isolation. You must simulate the cascade — including matching networks and inter-stage losses — to understand the real system NF, gain, and IP3.

## Key Commands / Configuration / Code

Below is a practical Python snippet using `scikit-rf` to cascade an LNA, a filter, and a PA, and compute the overall noise figure and IIP3. This is exactly what I ran today to sanity-check a BOM.

```python
import skrf as rf
import numpy as np

# Load S-parameter files (assumes .s2p files in working directory)
# LNA: Mini-Circuits PSA4-5043+ at 2.45 GHz
lna = rf.Network('PSA4-5043+_S2P.s2p')
# Filter: Johanson 2450BP15D0100 (BPF, 2.4-2.5 GHz)
bpf = rf.Network('2450BP15D0100.s2p')
# PA: Qorvo RFFM4501 (integrated PA + LNA, but we use PA path)
pa = rf.Network('RFFM4501_PA.s2p')

# Inter-stage matching networks (ideal 0 dB loss for demo)
# In real design, include microstrip or lumped element models
match1 = rf.Network('ideal_thru.s2p')  # 0 dB, 0 deg
match2 = rf.Network('ideal_thru.s2p')

# Cascade: Antenna -> BPF -> LNA -> Match1 -> PA -> Match2 -> Output
cascade = bpf ** lna ** match1 ** pa ** match2

# Print cascade results at 2.45 GHz
freq_idx = np.argmin(np.abs(cascade.f - 2.45e9))
print(f"Frequency: {cascade.f[freq_idx]/1e9:.3f} GHz")
print(f"Gain: {cascade.s21[freq_idx][0][0]:.2f} dB")
print(f"Noise Figure: {cascade.nf[freq_idx][0][0]:.2f} dB")

# Manual Friis cascade check (assuming known NF and gain per stage)
nf_lin = [bpf.nf[0][0][0], lna.nf[0][0][0], pa.nf[0][0][0]]
gain_lin = [bpf.s21[0][0][0], lna.s21[0][0][0], pa.s21[0][0][0]]
# Convert to linear
nf_lin = [10**(x/10) for x in nf_lin]
gain_lin = [10**(x/10) for x in gain_lin]

# Friis formula: F_total = F1 + (F2-1)/G1 + (F3-1)/(G1*G2)
f_total = nf_lin[0] + (nf_lin[1]-1)/gain_lin[0] + (nf_lin[2]-1)/(gain_lin[0]*gain_lin[1])
nf_total_db = 10*np.log10(f_total)
print(f"Friis NF: {nf_total_db:.2f} dB")
```

**Key inline comments:**
- The cascade order matters: filter first to reject out-of-band blockers that would saturate the LNA.
- The `ideal_thru.s2p` is a placeholder — in real designs, replace with measured or EM-simulated matching networks.
- The Friis check validates the `scikit-rf` cascade; if they disagree, check S-parameter data alignment.

## Common Pitfalls & Gotchas

1. **Ignoring inter-stage mismatch.** You can have a perfect LNA and a perfect PA, but if the output impedance of the LNA doesn’t match the input impedance of the PA (usually 50 Ω), you lose gain and degrade NF. Always simulate the full cascade with realistic matching networks, not just ideal 50 Ω thru lines.

2. **Confusing P1dB and IP3.** P1dB is the 1 dB compression point (gain drops by 1 dB). IP3 is the third-order intercept point (extrapolated). For a cascade, the overall IIP3 is dominated by the last stage, but the overall P1dB is dominated by the first stage that saturates. Use the cascade IP3 formula: `1/IIP3_total = 1/IIP3_1 + G1/IIP3_2 + (G1*G2)/IIP3_3`. Never assume they track linearly.

3. **Filter insertion loss before the LNA.** A 1 dB filter loss before the LNA adds 1 dB to the system NF. If your LNA has a 0.5 dB NF, you just tripled the noise floor. Always place the filter *after* the LNA if you can tolerate the LNA seeing blockers, or use a high-rejection filter with <0.5 dB loss.

## Try It Yourself

1. **Cascade simulation with real S-parameters.** Download S2P files for a common LNA (e.g., Mini-Circuits PSA4-5043+), a SAW filter (e.g., Murata SF1186B), and a PA (e.g., Skyworks SKY66115). Use `scikit-rf` to cascade them and compare the simulated NF and gain to the datasheet’s typical application circuit. Note the discrepancy from inter-stage mismatch.

2. **Noise figure measurement with a spectrum analyzer.** If you have access to a lab, build a simple LNA + filter chain on a PCB. Use a noise source (e.g., Noisecom NC346) and a spectrum analyzer to measure the cascade NF via the Y-factor method. Compare to your simulation. Expect 0.5–1 dB difference due to connector and trace losses.

3. **Linearity budget spreadsheet.** Create a spreadsheet with three stages: LNA (NF=0.8 dB, G=18 dB, IIP3=+10 dBm), BPF (IL=2 dB, IIP3=+50 dBm), PA (G=30 dB, P1dB=+30 dBm, IIP3=+40 dBm). Compute the cascade NF, gain, and IIP3. Then swap the LNA and BPF order — observe how NF degrades by 2 dB. This is the classic “filter-first vs. LNA-first” trade-off.

## Next Up

Tomorrow, I’ll tackle **Balun Design & Single-Ended to Differential Conversion** — the critical passive network that bridges unbalanced antennas to balanced LNAs and mixers. We’ll cover Marchand baluns, lumped-element LC baluns, and how to simulate common-mode rejection ratio (CMRR) in ADS.
