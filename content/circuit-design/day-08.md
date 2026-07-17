---
title: "Day 08: Filter Design: RC, RL & Active Filters"
date: 2026-07-17
tags: ["til", "circuit-design", "filters", "rc"]
---

## What I Explored Today

Today I dove into the practical design of analog filters—specifically first-order RC, RL, and active filter topologies using op-amps. While textbooks often treat these as academic exercises, real embedded systems demand filters that handle noise, anti-aliasing, and signal conditioning without distorting the passband. I built and simulated several designs in LTSpice, measured cutoff frequencies, and compared passive vs. active implementations for a 1 kHz low-pass application driving an ADC input.

## The Core Concept

Filters exist because real-world signals are never clean. A sensor output might have 50/60 Hz power-line hum, high-frequency switching noise from a buck converter, or aliasing components that fold into your ADC’s bandwidth. The goal is to attenuate unwanted frequencies while preserving the signal of interest.

**Why not just use a capacitor?** A single capacitor across a signal line creates a first-order low-pass filter, but its cutoff frequency depends on the source impedance and the load impedance—both of which are often unknown or variable. That’s where the RC and RL topologies come in: they provide a predictable, impedance-controlled rolloff.

**Passive vs. Active:**
- **Passive (RC, RL):** No power supply needed, simple, but the load impedance affects the response. Gain is always ≤ 1 (0 dB). Cascading stages loads the previous stage.
- **Active (op-amp based):** Provides gain, high input impedance, low output impedance, and can implement complex responses (Butterworth, Chebyshev) without magnetic components. Requires a power supply and careful attention to op-amp bandwidth and slew rate.

The cutoff frequency for a first-order low-pass RC filter is:
```
f_c = 1 / (2πRC)
```
For an RL low-pass:
```
f_c = R / (2πL)
```

But the real engineering happens when you choose component values that account for source impedance, ADC input capacitance, and noise floor.

## Key Commands / Configuration / Code

### 1. Passive RC Low-Pass Filter (1 kHz cutoff)

Design target: f_c = 1 kHz, with R = 1.6 kΩ (standard value).

```
C = 1 / (2π * 1600 * 1000) ≈ 99.5 nF → use 100 nF (standard)
```

LTSpice netlist:
```spice
* RC Low-Pass Filter, f_c = 1 kHz
V1 1 0 SINE(0 1 1000) AC 1
R1 1 2 1.6k
C1 2 0 100n
.ac dec 100 10 100k
.meas AC fc WHEN V(2)=V(1)/sqrt(2)
.backanno
.end
```

### 2. Active Second-Order Low-Pass (Sallen-Key, Butterworth)

For a unity-gain Sallen-Key with f_c = 1 kHz and Q = 0.707 (Butterworth):

Choose R1 = R2 = 10 kΩ, then:
```
C1 = 2 * Q / (2π * f_c * R) = 2*0.707 / (6283 * 10e3) ≈ 22.5 nF → 22 nF
C2 = 1 / (2 * Q * 2π * f_c * R) = 1 / (1.414 * 6283 * 10e3) ≈ 11.25 nF → 10 nF
```

LTSpice netlist:
```spice
* Sallen-Key Low-Pass, f_c = 1 kHz, Butterworth
V1 1 0 SINE(0 1 1000) AC 1
R1 1 2 10k
R2 2 3 10k
C1 3 0 22n
C2 2 4 10n
XU1 4 3 5 6 OP07  ; op-amp: non-inv input=3, inv input=4, V+=5, V-=6
VCC 5 0 15
VEE 6 0 -15
.ac dec 100 10 100k
.meas AC fc WHEN V(4)=V(1)/sqrt(2)
.backanno
.end
```

### 3. RL Low-Pass Filter (for power supply filtering)

For a 10 kHz cutoff with R = 100 Ω:
```
L = R / (2π * f_c) = 100 / (62832) ≈ 1.59 mH → use 1.5 mH
```

LTSpice netlist:
```spice
* RL Low-Pass, f_c ≈ 10.6 kHz
V1 1 0 SINE(0 1 10000) AC 1
R1 1 2 100
L1 2 0 1.5m
.ac dec 100 100 1Meg
.backanno
.end
```

## Common Pitfalls & Gotchas

1. **Ignoring source and load impedance in passive filters.**  
   An RC filter’s cutoff shifts if the source impedance is comparable to R, or if the load impedance is less than ~10× R. Always buffer with an op-amp if driving a low-impedance load (e.g., ADC input with 10 pF + 1 kΩ mux resistance).  
   *Fix:* Use an active filter or add a voltage follower.

2. **Op-amp bandwidth limitations in active filters.**  
   A Sallen-Key designed for 100 kHz will fail if the op-amp’s gain-bandwidth product (GBW) is only 1 MHz. The filter’s Q increases near the op-amp’s open-loop pole, causing peaking or oscillation.  
   *Fix:* Choose an op-amp with GBW ≥ 100× the filter cutoff frequency (e.g., OPA2134 for audio, LMV321 for low-power).

3. **Capacitor dielectric absorption and tolerance.**  
   Using X7R ceramic capacitors for filter caps introduces voltage coefficient (capacitance drops with DC bias) and dielectric absorption, which distorts the filter shape.  
   *Fix:* Use C0G/NP0 for precision filters, or film capacitors (polypropylene) for audio.

## Try It Yourself

1. **Simulate the RC filter with a 10 kΩ load.**  
   Add a 10 kΩ resistor from the output to ground in the RC filter netlist. Measure the new cutoff frequency. How much does it shift? Then add a unity-gain buffer (op-amp voltage follower) between the RC and the load—does the cutoff return to 1 kHz?

2. **Design a 2nd-order active high-pass filter.**  
   Modify the Sallen-Key topology: swap the positions of R and C in the feedback network. Calculate component values for a 500 Hz high-pass with Butterworth response. Simulate and verify the -3 dB point.

3. **Compare passive RL vs. RC for a 100 kHz cutoff.**  
   For R = 50 Ω, calculate L for RL and C for RC. Simulate both. Which one has better stopband rejection at 1 MHz? Which one would you choose for a power supply line filter?

## Next Up

Tomorrow, we cross the analog-to-digital boundary: **Analog-to-Digital Conversion: ADC Types & Sampling Theory**. We’ll compare SAR, delta-sigma, and flash ADCs, calculate required sampling rates to avoid aliasing, and design an anti-aliasing filter that actually works with a real ADC input stage.
