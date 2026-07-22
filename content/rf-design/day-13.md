---
title: "Day 13: RF Simulation Tools: EM Simulators & Field Solvers"
date: 2026-07-22
tags: ["til", "rf-design", "em-simulation", "field-solver"]
---

## What I Explored Today

Today I dove into the practical use of electromagnetic (EM) simulators and field solvers for RF design. After weeks of circuit-level simulation with SPICE and S-parameter analysis, I finally crossed the threshold into full-wave EM simulation. I worked through setting up a microstrip patch antenna in two different solvers—a Method of Moments (MoM) planar solver and a Finite Element Method (FEM) 3D solver—and compared their results for a 2.4 GHz design. The key takeaway: these tools are not magic black boxes; they require careful mesh control, boundary condition selection, and an understanding of which solver physics apply to your geometry.

## The Core Concept

Why do we need EM simulation at all? Circuit simulators treat interconnects as ideal lumped elements, but above a few hundred MHz, the physical dimensions of traces, vias, and connectors become comparable to the wavelength. At 2.4 GHz, a quarter-wavelength in FR4 is about 18 mm—shorter than many PCB edges. EM simulators solve Maxwell's equations in their full vector form, accounting for radiation, coupling, and substrate effects that circuit models simply cannot capture.

The three dominant solver technologies are:

- **Method of Moments (MoM)**: Solves surface currents on planar conductors. Best for microstrip, stripline, and patch antennas. Very efficient for 2.5D structures (planar with vertical vias). Examples: Keysight Momentum, Sonnet, Altair FEKO.
- **Finite Element Method (FEM)**: Volumetric mesh of tetrahedra. Handles arbitrary 3D geometries, including waveguide transitions, connectors, and cavity resonators. Examples: Ansys HFSS, CST Microwave Studio (FEM solver).
- **Finite-Difference Time-Domain (FDTD)**: Time-domain, Cartesian grid. Excellent for broadband responses from a single simulation. Examples: Lumerical, openEMS, CST (T-solver).

The critical engineering decision: **choose the solver that matches your geometry's dimensionality.** Simulating a simple microstrip line in a full 3D FEM solver wastes compute time; simulating a waveguide transition in a 2.5D MoM solver will give wrong results because it can't model vertical field components properly.

## Key Commands / Configuration / Code

Below is a practical workflow for setting up a 2.4 GHz patch antenna in Keysight ADS Momentum (MoM) and verifying the mesh. This assumes you have a substrate definition and a polygon for the patch.

```python
# Python script to generate a patch antenna layout for ADS Momentum
# This is a simplified geometry generator — real designs use the ADS GUI

import math

freq = 2.4e9          # Operating frequency (Hz)
epsilon_r = 4.5       # FR4 relative permittivity
h = 1.6e-3            # Substrate thickness (m)

# Calculate patch width and length using transmission line model
# Width (W) for efficient radiation:
W = (3e8 / (2 * freq)) * math.sqrt(2 / (epsilon_r + 1))
# Effective permittivity:
epsilon_eff = (epsilon_r + 1)/2 + (epsilon_r - 1)/2 * (1 / math.sqrt(1 + 12*h/W))
# Fringing extension delta_L:
delta_L = 0.412 * h * ((epsilon_eff + 0.3)*(W/h + 0.264)) / \
                    ((epsilon_eff - 0.258)*(W/h + 0.8))
# Actual patch length:
L = (3e8 / (2 * freq * math.sqrt(epsilon_eff))) - 2*delta_L

print(f"Patch dimensions: W={W*1000:.2f} mm, L={L*1000:.2f} mm")
```

**Momentum simulation setup (via ADS GUI or script):**

```
Substrate stackup (from bottom to top):
  - Ground plane: Copper, 35 um, infinite extent
  - Dielectric: FR4, epsilon_r=4.5, tan_d=0.02, thickness=1.6 mm
  - Top metal: Copper, 35 um, patch polygon

Port: Edge port at the feed edge (50-ohm microstrip feed line)
Mesh: Adaptive mesh, target frequency = 2.4 GHz, max edge length = lambda/20
      (lambda_eff = 3e8 / (freq * sqrt(epsilon_eff)) ≈ 72 mm → max edge ≈ 3.6 mm)

Sweep: Linear from 2.0 to 3.0 GHz, 101 points
```

**Key solver settings in Momentum:**

```
Simulation Type: Momentum Microwave (full-wave MoM)
Mesh Density: 30 cells per wavelength (in substrate)
Edge Mesh: Enabled (critical for accurate current at conductor edges)
Thin Conductor Model: Enabled (accounts for skin effect at 2.4 GHz)
```

**Verifying convergence (critical step):**

After the first simulation, check the mesh statistics:
- Number of unknowns (basis functions): Should be > 500 for a simple patch
- Residual error: < 1e-6
- Run a second pass with 50% more cells — if S11 changes by < 0.1 dB, mesh is converged

## Common Pitfalls & Gotchas

1. **Infinite ground plane assumption in MoM solvers.** Many planar solvers default to an infinite ground plane. For a real PCB with finite ground, this overestimates isolation and underestimates back-lobe radiation. Always check if your solver supports finite ground planes (e.g., via "box" boundary conditions or finite GND polygons). I wasted two days debugging a filter that had 10 dB more insertion loss than simulated—turns out the finite ground introduced parasitic inductance the infinite model ignored.

2. **Mesh convergence is not optional.** A single simulation at default mesh settings is almost certainly wrong. Always run a convergence study: double the mesh density and compare S-parameters. The rule of thumb: for microstrip, use at least 20 cells per wavelength in the dielectric; for structures with high field gradients (e.g., via transitions), use 40+ cells. If your simulation takes 10 minutes, a convergence check takes 30 minutes total—worth it.

3. **Port calibration confusion.** In MoM solvers, the port calibration (e.g., "internal port" vs "external port" in Momentum) defines the reference plane. If you simulate a microstrip line with an internal port, the de-embedding removes the feed line parasitics. If you want the S-parameters of the entire structure including the feed, use external ports. Mismatching these gives S11 that looks like a short or open when it's actually a calibration error.

## Try It Yourself

1. **Compare MoM vs FEM for a microstrip line.** Design a 50-ohm microstrip line on 1.6 mm FR4 at 2.4 GHz. Simulate it in a planar MoM solver (e.g., Sonnet Lite or ADS Momentum) and a 3D FEM solver (e.g., Ansys HFSS Student or openEMS). Compare the S21 magnitude and phase from 1-4 GHz. Note the simulation time difference—FEM should be 5-10x slower for this simple geometry.

2. **Mesh convergence study on a patch antenna.** Using the dimensions from the code above, simulate the patch antenna in your chosen EM tool. Start with a coarse mesh (10 cells/wavelength), then refine to 20, 30, and 40 cells/wavelength. Plot S11 vs frequency for each mesh. Identify the mesh density where S11 at resonance changes by less than 0.2 dB.

3. **Investigate finite ground effects.** Take the same patch antenna and change the ground plane from infinite to a finite size (e.g., 2x the patch dimensions). Compare the radiation pattern (gain, front-to-back ratio) and input impedance. You should see the resonant frequency shift by 1-3% and the back lobe increase by 3-6 dB.

## Next Up

Tomorrow, we leave the simulation world and get our hands on real hardware: **RF Measurement: Spectrum Analyzers & VNA Calibration**. We'll cover how to set up a SOLT calibration, interpret a spectrum analyzer's RBW/VBW settings, and measure the S-parameters of the patch antenna we just simulated—comparing simulation to reality.
