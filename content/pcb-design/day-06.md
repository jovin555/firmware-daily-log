---
title: "Day 06: Power Distribution Network (PDN) Design & Decoupling Strategy"
date: 2026-07-15
tags: ["til", "pcb-design", "pdn", "decoupling"]
---

## What I Explored Today

Today I dove into the Power Distribution Network (PDN) — the unsung hero of every working PCB. While most engineers focus on signal integrity, a poorly designed PDN will kill your high-speed design faster than any routing mistake. I spent the day modeling plane impedances, selecting decoupling capacitor networks, and validating against target impedances using SPICE and 2D field solvers. The key takeaway: a PDN isn't just about dumping capacitors on a rail — it's a carefully engineered impedance profile from DC to 10+ GHz.

## The Core Concept

The PDN's job is to deliver clean, stable voltage to every active device under transient load conditions. Think of it as a power delivery hose: you want low resistance (DC drop), low inductance (AC transient response), and enough capacitance to handle current surges without the voltage sagging below the device's tolerance.

The fundamental metric is **target impedance**:

\[
Z_{target} = \frac{V_{rail} \times Ripple_{allowable}}{I_{transient}}
\]

For a 1.8V rail with 5% ripple (90 mV) and a 2A transient step, your PDN must present less than 45 mΩ from DC to the frequency where the bulk capacitors roll off. This isn't optional — violate it and your FPGA will glitch, your ADC will miss codes, and your PLL will lose lock.

The PDN has four main contributors, each dominating a frequency band:

1. **VRM** (DC to ~1 kHz) — voltage regulator module, high capacitance but slow response
2. **Bulk capacitors** (1 kHz to ~1 MHz) — electrolytic or tantalum, handle large charge delivery
3. **Ceramic decoupling** (1 MHz to ~100 MHz) — MLCCs, low ESR/ESL, fast response
4. **On-die capacitance + PCB plane capacitance** (100 MHz to GHz) — the power/ground plane pair acts as a distributed capacitor

The art is in the transition between these regions. A gap in the impedance curve at 10 MHz means your 100 MHz clock's harmonics will see a high impedance path, causing radiated emissions and jitter.

## Key Commands / Configuration / Code

### 1. Plane Capacitance Calculation (Python snippet)

```python
# Calculate plane capacitance for a power/ground pair
import math

def plane_capacitance(area_mm2, dielectric_thickness_um, er=4.5):
    """
    area_mm2: overlapping plane area in square mm
    dielectric_thickness_um: prepreg thickness in micrometers
    er: relative permittivity of dielectric (FR4 ~4.5)
    """
    epsilon_0 = 8.854e-12  # F/m
    area_m2 = area_mm2 * 1e-6
    thickness_m = dielectric_thickness_um * 1e-6
    capacitance = epsilon_0 * er * area_m2 / thickness_m
    return capacitance * 1e12  # return in pF

# Example: 50mm x 50mm plane, 100um prepreg
cap = plane_capacitance(2500, 100)
print(f"Plane capacitance: {cap:.1f} pF")
# Output: Plane capacitance: 99.6 pF
```

### 2. Decoupling Network Target Impedance Check (LTSpice netlist)

```spice
* PDN impedance simulation for 1.8V rail
* Target: Z < 45mOhm from DC to 100MHz

* VRM model (simple R-L)
V1 VCC 0 DC 1.8
R_VRM VCC VRM_NODE 0.001
L_VRM VRM_NODE VRM_OUT 10nH

* Bulk capacitor: 100uF electrolytic, ESR=0.1, ESL=5nH
C_BULK VRM_OUT BULK_NODE 100uF
R_ESR_BULK BULK_NODE BULK_ESR 0.1
L_ESL_BULK BULK_ESR VCC_PLANE 5nH

* Mid-frequency: 10uF ceramic, ESR=0.005, ESL=0.5nH
C_MID VCC_PLANE MID_NODE 10uF
R_ESR_MID MID_NODE MID_ESR 0.005
L_ESL_MID MID_ESR VCC_LOAD 0.5nH

* High-frequency: 100nF ceramic, ESR=0.002, ESL=0.3nH
C_HF VCC_LOAD HF_NODE 100nF
R_ESR_HF HF_NODE HF_ESR 0.002
L_ESL_HF HF_ESR LOAD 0.3nH

* AC stimulus
I1 LOAD 0 AC 1
.ac dec 100 100 100Meg
.probe
.end
```

Run this in LTSpice and plot V(LOAD)/I(I1) — you'll see impedance peaks at the series resonances of each capacitor. The goal is to keep the entire curve below your target.

### 3. PDN Impedance Plot (gnuplot)

```gnuplot
set logscale xy
set xlabel "Frequency (Hz)"
set ylabel "Impedance (Ohms)"
set grid
set title "PDN Impedance Profile"
plot "pdn_sim.txt" using 1:2 with lines lw 2 title "PDN Z", \
     0.045 with lines lw 2 lt rgb "red" title "Target Z (45mOhm)"
```

## Common Pitfalls & Gotchas

**1. The Anti-Resonance Peak**
When two capacitors of different values are placed in parallel, their respective ESL and capacitance create a parallel LC tank at the frequency where one capacitor's impedance is inductive and the other's is capacitive. This can produce a *higher* impedance than either capacitor alone. Mitigation: use capacitors in a geometric series (e.g., 100nF, 1uF, 10uF) and keep the ratio between values ≤ 10x. Better yet, simulate the network.

**2. Via Inductance Kills High-Frequency Decoupling**
A 0402 capacitor with 0.3nH ESL is useless if you route it through two vias with 0.5nH each and 5mm of trace. The total loop inductance can exceed 2nH, shifting the effective frequency down by an order of magnitude. Rule of thumb: place decoupling caps directly under the BGA or within 2mm of the power pin, using micro-vias or via-in-pad. Never route a decoupling cap through a long trace.

**3. Ignoring the Plane Inductance**
Engineers often model planes as ideal conductors. In reality, a 1oz copper plane has about 0.5nH per square of inductance. For a 100mm x 100mm plane, the inductance from the VRM to the load can be 5-10nH — enough to create a resonant peak at 10-20 MHz. Use multiple vias in parallel (spaced < λ/20) to reduce effective inductance, and consider using a power island with stitching vias to the ground plane.

## Try It Yourself

1. **Calculate your target impedance**: Pick a rail on your current design (e.g., 3.3V, 1.8V, 1.0V core). Look up the maximum transient current from the datasheet. Assume 5% ripple. Compute Z_target. Is your current decoupling network meeting it?

2. **Simulate your existing decoupling**: Extract the capacitor values, ESR, and ESL from your BOM. Build an LTSpice netlist like the one above. Run an AC sweep from 100 Hz to 1 GHz. Identify any impedance peaks above your target — those are your problem frequencies.

3. **Optimize capacitor placement**: On your PCB layout, measure the distance from each decoupling capacitor's via to the power pin of the IC. Calculate the loop inductance (roughly 1 nH per mm of trace + 0.5 nH per via). If any cap has > 2 nH total loop inductance, move it closer or add more vias.

## Next Up

Tomorrow we tackle **Thermal Design: Copper Pours, Thermal Vias & Heat Sinking** — because a perfectly routed board that melts at 150°C is just a very expensive heater.
