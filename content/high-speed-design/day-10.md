---
title: "Day 10: Signal Integrity Simulation: S-Parameters & Eye Diagrams"
date: 2026-07-19
tags: ["til", "high-speed-design", "s-parameters", "eye-diagram"]
---

## What I Explored Today

I spent the day validating a 6-layer PCIe Gen 4 channel using S-parameter extraction and eye diagram simulation. The goal was to confirm that a 16-inch differential trace pair through two via transitions and one AC-coupling capacitor could meet the 0.5 UI eye opening at 16 GT/s. I ran into the classic problem: the raw S-parameters looked fine, but the eye diagram told a different story once I included the package model and RX CTLE.

## The Core Concept

S-parameters and eye diagrams are two sides of the same coin, but they answer fundamentally different questions. S-parameters characterize the *linear, time-invariant* behavior of the channel in the frequency domain. They tell you how much signal gets through (S21), how much reflects back (S11), and how much crosstalk couples into adjacent lanes (S41, S31). An eye diagram, on the other hand, is a *non-linear, time-domain* measurement that shows the cumulative effect of all impairments—ISI, jitter, noise, and crosstalk—on the actual data pattern.

Why both? Because S-parameters alone can be misleading. A channel might have -3 dB insertion loss at Nyquist (8 GHz for PCIe Gen 4), which looks acceptable. But if that loss is due to a sharp resonance from a stub, the resulting group delay variation will close the eye in ways that a simple loss number doesn't capture. Conversely, an eye diagram without S-parameters is blind to the root cause. You see the eye is closed, but you don't know if it's due to impedance mismatch, dielectric loss, or crosstalk.

The workflow is: extract S-parameters from the PCB layout, validate passivity and causality, then convolve the S-parameter impulse response with a PRBS data pattern to generate the eye diagram. The simulation must include the transmitter de-emphasis, receiver equalization (CTLE, DFE), and the package model to be realistic.

## Key Commands / Configuration / Code

I used Keysight ADS for this, but the principles apply to any SI tool (HyperLynx, CST, etc.). Here's the critical setup for a differential channel simulation.

**S-Parameter Extraction Setup (in ADS Momentum or EMPro):**
```text
! Port impedance: 100 ohms differential (50 ohms single-ended)
! Frequency sweep: DC to 20 GHz (1.25x the 16 GHz fundamental)
! Step size: 10 MHz (fine enough to capture resonances)
! De-embedding: Use 2x-thru or TRL calibration to remove launch effects

! After extraction, run this sanity check in the Data Display:
passivity(S2P)  ! Should return < 1 for all frequencies
causality(S2P)  ! Should return 1 (true)
```

**Eye Diagram Simulation (Channel Simulator):**
```text
! Transmitter setup
Tx_Amplitude = 0.8 Vppd (PCIe Gen 4 typical)
Tx_Deemphasis = -3.5 dB (first post-cursor tap)
Tx_RiseTime = 20 ps (20%-80%)
Data_Rate = 16 GT/s
Pattern = PRBS13 (long enough for worst-case ISI)

! Receiver setup
Rx_CTLE = AC_GAIN(0 dB, 8 GHz)  ! Boost at Nyquist
Rx_CTLE_LF = -6 dB  ! Low-frequency attenuation
Rx_DFE = 1 tap, tap1 = 0.15  ! First post-cursor tap

! Eye measurement (post-equalization)
Eye_Height = eye_height(EyeDiagram, 1e6 bits)  ! In mV
Eye_Width = eye_width(EyeDiagram, 1e6 bits)    ! In ps
Eye_Jitter = eye_jitter(EyeDiagram, 1e6 bits)  ! Peak-to-peak in ps
```

**Critical Python snippet for post-processing S-parameters (using scikit-rf):**
```python
import skrf as rf
import numpy as np

# Load S-parameters
ch = rf.Network('pcie_channel.s4p')
# Extract differential mode from mixed-mode S-parameters
ch_diff = ch.se2gmm(p=1, n=1)  # Port 1+2 -> diff, Port 3+4 -> diff
# Check passivity
passivity = np.max(np.linalg.svd(ch.s, compute_uv=False), axis=1)
if np.any(passivity > 1.001):
    print("WARNING: Non-passive S-parameters at", 
          ch.f[passivity > 1.001][0]/1e9, "GHz")
# Compute impulse response for convolution
ch.write_touchstone('pcie_diff.s2p')
```

## Common Pitfalls & Gotchas

**1. The "Passivity Violation" Trap**
I once spent two days chasing an eye diagram that showed negative eye height. The root cause: my S-parameter file had passivity violations at 12.4 GHz (S-parameter magnitude > 1.0). This happened because I used too coarse a frequency step (50 MHz) near a sharp resonance. The fix: re-simulate with 5 MHz step around the resonance, or use a passivity enforcement algorithm (`skrf.network.enforce_passivity()`). Always check `passivity(S2P)` before running any time-domain simulation.

**2. The "PRBS Pattern Length" Gotcha**
Using PRBS7 (127 bits) instead of PRBS13 (8191 bits) for a 16 GT/s channel with 20 inches of FR4 will give you an overly optimistic eye. The short pattern doesn't excite the worst-case ISI from the long-tail channel response. I've seen engineers claim a 0.4 UI eye opening with PRBS7, only to see it collapse to 0.2 UI with PRBS13. Rule of thumb: use PRBS length >= 2^(channel memory in UI). For a 16-inch trace with 20 ps rise time, that's about PRBS11 or longer.

**3. The "Equalization-Free" Assumption**
Simulating the eye without including the receiver's CTLE and DFE is like testing a car's top speed without the engine. The channel might have 12 dB loss at Nyquist, but a 3-tap DFE can recover 6-8 dB of that. Always include at least a 1-tap DFE and a peaking CTLE in your simulation. The spec for PCIe Gen 4 requires a minimum of 2-tap DFE. If you don't model it, you'll over-design the channel and add unnecessary cost.

## Try It Yourself

1. **Extract and validate S-parameters from your own design.** Take a 4-inch differential trace from your current board. Export the S-parameters and run the passivity and causality checks. Plot Sdd21 (differential insertion loss) and Sdd11 (differential return loss). Identify the -3 dB and -6 dB points. Compare against your target loss budget.

2. **Run a "before and after" eye diagram simulation.** First, simulate the eye with no equalization (just the raw channel). Measure the eye height and width. Then add a 1-tap CTLE with 6 dB peaking at Nyquist. Re-measure. How much does the eye open? Now add a 1-tap DFE with tap1 = 0.15. What's the improvement? This exercise shows you exactly where your margin comes from.

3. **Find the resonance that kills your eye.** Inject a 10 ps rise-time step into your channel model and look at the TDR response. Identify any impedance discontinuities (vias, connectors, AC caps). Then sweep the via stub length from 5 mils to 50 mils and re-extract S-parameters. Plot Sdd21 at 8 GHz vs. stub length. You'll see a clear resonance dip. This is why back-drilling is non-negotiable above 10 Gbps.

## Next Up

Tomorrow, we tackle **DDR Routing: Fly-by Topology & Length Matching Rules**. We'll break down why fly-by topology replaced T-branch for DDR4/DDR5, how to calculate the exact length mismatch budget for DQ vs. DQS vs. CLK, and why a 10 ps skew on a DDR5-6400 interface can cost you 50 mV of timing margin. Bring your routing calculator.
