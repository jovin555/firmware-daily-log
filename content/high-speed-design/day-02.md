---
title: "Day 02: Transmission Line Theory: When Traces Become Transmission Lines"
date: 2026-07-11
tags: ["til", "high-speed-design", "transmission-line"]
---

## What I Explored Today

Today I dug into the threshold where a simple PCB trace stops behaving like a lumped-element wire and starts acting like a distributed transmission line. The critical rule of thumb—when the one-way propagation delay exceeds 1/10th of the signal's rise time—is taught in every SI class, but I wanted to understand the physics behind it and, more importantly, how to detect and model it in real designs. I spent the morning running TDR simulations and comparing lumped vs. distributed models in SPICE to see exactly where the breakpoint lies.

## The Core Concept

A trace becomes a transmission line when the electrical length of the interconnect is significant relative to the signal's edge rate. The rule is simple: if the propagation delay (t_pd) of the trace is greater than 1/10th of the signal's 10%-to-90% rise time (t_r), you must treat it as a transmission line.

Why 1/10th? Because at that point, reflections from the load can arrive back at the driver while the edge is still transitioning, causing overshoot, undershoot, and logic errors. In lumped-element thinking, we assume the entire trace charges simultaneously—that fails when the signal's wavelength components are comparable to the trace length.

For a typical FR4 PCB, propagation velocity is roughly 6 inches per nanosecond (v = c / √ε_r, with ε_r ≈ 4.2 for FR4, so v ≈ 1.8e8 m/s ≈ 6 in/ns). A 1 ns rise time signal becomes transmission-line-aware at trace lengths above:  
t_pd = length / v → length > (t_r / 10) × v = (1 ns / 10) × 6 in/ns = 0.6 inches.

That's only 15 mm. Any trace longer than 0.6 inches with a 1 ns edge needs transmission line analysis. For faster edges (e.g., 100 ps), that threshold drops to 0.06 inches—essentially any via-to-pin stub.

The key parameters that define a transmission line are its characteristic impedance (Z₀), propagation delay (t_pd), and the load impedance (Z_L). When Z_L ≠ Z₀, reflections occur with a reflection coefficient Γ = (Z_L - Z₀) / (Z_L + Z₀).

## Key Commands / Configuration / Code

Here's a practical SPICE netlist to compare lumped vs. distributed behavior for a 2-inch FR4 trace with a 500 ps rise time driver:

```spice
* Transmission Line vs Lumped RC Comparison
* Driver: 50 ohm source, 500ps rise time, 1V step
* Trace: 2 inches on FR4 (Z0=50, t_pd=333ps)

* --- Driver ---
V1 in 0 PULSE(0 1 0 500p 500p 10n 20n)
Rsrc in 1 50

* --- Distributed model (lossless) ---
T1 1 0 2 0 Z0=50 TD=333p

* --- Lumped model (bad approximation) ---
* 2 inches of 8mil trace: ~2pF/in, ~0.1 ohm/in
Rlump 1 3 0.2
Clump 3 0 4p

* --- Load ---
Rload 2 0 1k   * high-impedance load (worst case)
Rload2 3 0 1k

* --- Analysis ---
.TRAN 10p 5n
.PROBE
.END
```

Run this in LTspice or ngspice. The distributed model (T1) will show a delayed, possibly ringing waveform at the load. The lumped RC model will show a simple exponential charge—completely missing the reflection behavior.

For real-world measurement, use a Time Domain Reflectometer (TDR) or simulate with:

```bash
# Using open-source PyEDA or scikit-rf for TDR simulation
python3 -c "
import numpy as np
import matplotlib.pyplot as plt

# Simulate a 50 ohm TDR into a 2-inch open stub
c = 3e8  # m/s
er = 4.2
v = c / np.sqrt(er)  # 1.46e8 m/s
length = 0.0508  # 2 inches in meters
td = length / v  # 348 ps

# Step response with 35 ps rise time
t = np.linspace(0, 2e-9, 1000)
step = 0.5 * (1 + np.tanh((t - 100e-12) / 15e-12))

# Reflection from open end (Gamma = 1)
reflection = np.roll(step, int(td / (t[1]-t[0]))) * 0.5
v_tdr = step + reflection

plt.plot(t*1e9, v_tdr)
plt.xlabel('Time (ns)')
plt.ylabel('Voltage (V)')
plt.title('TDR Response: 2-inch Open Stub')
plt.grid(True)
plt.show()
"
```

## Common Pitfalls & Gotchas

**1. Ignoring rise time, only looking at frequency**  
Many engineers check if the clock frequency is "high" and call it done. But a 10 MHz clock with 1 ns rise time has significant energy at 350 MHz (f_knee = 0.35 / t_r). That 2-inch trace is a transmission line even at "low" clock rates. Always use rise time, not clock frequency, as your metric.

**2. Assuming 50 ohms everywhere**  
FR4's dielectric constant varies with frequency (it's not exactly 4.2 at all frequencies) and with board stackup. A 50 ohm microstrip on a 4-layer board with 8 mil prepreg is different from one on a 2-layer board with 62 mil core. Always verify with a field solver (e.g., Saturn PCB Toolkit or Polar Si9000) for your actual stackup.

**3. Forgetting the return path**  
Transmission line theory assumes a well-defined return path. A trace over a split ground plane or near a slot in the reference plane will have wildly different impedance—and you'll see reflections even if your Z₀ calculation was perfect. The return current flows directly under the trace; if you cut that path, you create an impedance discontinuity.

## Try It Yourself

1. **Calculate your threshold**  
   Find the rise time of a signal in your current design (from the datasheet or measure with an oscilloscope). Compute the critical trace length using t_pd = length / (6 in/ns). Identify all traces in your layout that exceed this length.

2. **Simulate a mismatch**  
   Modify the SPICE netlist above to change Rload to 25 ohms (Γ = -0.333) and 150 ohms (Γ = +0.5). Observe the reflected wave amplitude and polarity on the load node. Verify it matches Γ × V_incident.

3. **Measure with a TDR**  
   If you have access to a TDR (or a fast oscilloscope with TDR capability), probe a known 50 ohm trace on your board. Compare the impedance profile to your calculated Z₀. Note any discontinuities at vias or connectors.

## Next Up

Tomorrow I'll dive into **Controlled Impedance: Microstrip & Stripline Calculations**—how to actually design traces to hit a target Z₀ using your PCB stackup, including the exact formulas, field solver setup, and how to handle solder mask effects. We'll also cover why 50 ohms became the default and when you might want 75 or 90 ohms instead.
