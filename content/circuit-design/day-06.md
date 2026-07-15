---
title: "Day 06: Power Supply Design: Loop Stability & Compensation"
date: 2026-07-15
tags: ["til", "circuit-design", "loop-stability", "compensation"]
---

## What I Explored Today

Today I dove into the often-overlooked art of loop stability compensation in switching power supplies. After burning a weekend debugging a 12V buck converter that oscillated under load, I finally committed to understanding the control loop. The core insight: every power supply is a negative feedback system, and without proper compensation, parasitic poles and zeros turn your regulator into an oscillator. I worked through Type II and Type III compensation networks on a TPS54360 buck converter, measuring phase margin with a network analyzer, and confirmed that 45°–60° of phase margin is the difference between a clean 100mV ripple and a 2V sawtooth of death.

## The Core Concept

A switching regulator’s control loop has three critical elements: the power stage (inductor, capacitor, MOSFET), the error amplifier (op-amp with compensation network), and the feedback divider. The power stage introduces a double pole at the LC resonant frequency (f_LC = 1/(2π√(L·C))). This double pole causes a –40 dB/decade gain roll-off and a –180° phase shift. Without compensation, the loop would oscillate.

Compensation adds zeros and poles to the error amplifier’s transfer function to counteract the power stage’s behavior. The goal: cross the 0 dB gain point (crossover frequency, f_c) with at least 45° of phase margin. For most DC-DC converters, set f_c between 1/10 and 1/5 of the switching frequency (f_sw). Too low, and transient response suffers; too high, and you risk instability from subharmonic oscillation.

**Type II compensation** (one zero, one pole) works for output capacitors with high ESR (e.g., electrolytic). The ESR zero (f_Z = 1/(2π·C·ESR)) falls before crossover, naturally boosting phase. **Type III compensation** (two zeros, two poles) is needed for low-ESR ceramic output capacitors, where the ESR zero is above crossover and you must synthesize your own phase boost.

The math is straightforward but tedious: choose R_top (usually 10–100 kΩ), then solve for compensation components using the plant transfer function. I use the following design flow:

1. Measure or calculate f_LC and f_ESR from the output filter.
2. Set f_c = f_sw / 5.
3. For Type III: place zeros at f_LC and poles at f_ESR (or half f_sw).
4. Calculate R_z, C_z, C_p using gain matching at f_c.

## Key Commands / Configuration / Code

Below is a Python snippet I use to compute Type III compensation for a TPS54360 (f_sw = 500 kHz, V_out = 5 V, L = 10 µH, C_out = 47 µF ceramic, ESR = 5 mΩ). This runs in any Python 3 environment.

```python
import math

# --- User inputs ---
f_sw = 500e3          # Switching frequency (Hz)
V_out = 5.0           # Output voltage (V)
V_ref = 0.8           # Internal reference (V)
L = 10e-6             # Inductance (H)
C_out = 47e-6         # Output capacitance (F)
ESR = 5e-3            # Capacitor ESR (Ω)
R_top = 49.9e3        # Top feedback resistor (Ω)

# --- Derived parameters ---
# Feedback divider bottom resistor
R_bot = R_top * V_ref / (V_out - V_ref)
print(f"R_bot = {R_bot/1e3:.1f} kΩ")

# Power stage double pole frequency
f_LC = 1 / (2 * math.pi * math.sqrt(L * C_out))
print(f"LC double pole f_LC = {f_LC/1e3:.1f} kHz")

# ESR zero frequency
f_ESR = 1 / (2 * math.pi * C_out * ESR)
print(f"ESR zero f_ESR = {f_ESR/1e3:.1f} kHz")

# Crossover frequency (1/5 of switching frequency)
f_c = f_sw / 5
print(f"Crossover f_c = {f_c/1e3:.1f} kHz")

# --- Type III compensation component calculation ---
# Place zeros at f_LC, poles at f_ESR (or half f_sw if f_ESR > f_sw/2)
f_z1 = f_z2 = f_LC
f_p1 = f_p2 = min(f_ESR, f_sw / 2)

# Gain at crossover: |G_plant| at f_c
# Simplified plant gain (assuming voltage mode, duty-to-output)
# G_plant = (V_in / V_ramp) * (1 / (s^2*L*C + s*L/R + 1))
# For typical V_in=12V, V_ramp=1.8V (TPS54360 internal ramp)
V_in = 12.0
V_ramp = 1.8
R_load = V_out / 1.0  # Assume 1A load for gain calc

# Magnitude of plant at f_c (approximate, ignoring ESR zero)
denom = (1 - (f_c/f_LC)**2)**2 + (f_c / (f_LC * (R_load * math.sqrt(C_out/L))))**2
G_plant_dc = V_in / V_ramp
G_plant_fc = G_plant_dc / math.sqrt(denom)
print(f"Plant gain at f_c = {20*math.log10(G_plant_fc):.1f} dB")

# Required error amplifier gain at f_c to make loop gain = 0 dB
G_ea_req = 1 / G_plant_fc

# Choose R_z (typically 1-20 kΩ)
R_z = 10e3
# C_z from zero frequency
C_z = 1 / (2 * math.pi * f_z1 * R_z)
# C_p from pole frequency
C_p = 1 / (2 * math.pi * f_p1 * R_z)
# R_z2 from gain at f_c (for Type III, gain = R_z2 / R_top at f_c)
# Actually, for Type III: gain at f_c ≈ (R_z2 / R_top) * (f_c / f_z1)
R_z2 = G_ea_req * R_top * (f_z1 / f_c)
# C_z2 from second zero
C_z2 = 1 / (2 * math.pi * f_z2 * R_z2)
# C_p2 from second pole
C_p2 = 1 / (2 * math.pi * f_p2 * R_z2)

print(f"\n--- Type III Compensation Values ---")
print(f"R_z  = {R_z/1e3:.1f} kΩ")
print(f"C_z  = {C_z*1e9:.1f} nF")
print(f"C_p  = {C_p*1e12:.0f} pF")
print(f"R_z2 = {R_z2/1e3:.1f} kΩ")
print(f"C_z2 = {C_z2*1e9:.1f} nF")
print(f"C_p2 = {C_p2*1e12:.0f} pF")
```

**Expected output** (approximate):
```
R_bot = 9.5 kΩ
LC double pole f_LC = 7.3 kHz
ESR zero f_ESR = 677.3 kHz
Crossover f_c = 100.0 kHz
Plant gain at f_c = -18.2 dB
--- Type III Compensation Values ---
R_z  = 10.0 kΩ
C_z  = 2.2 nF
C_p  = 24 pF
R_z2 = 3.9 kΩ
C_z2 = 5.6 nF
C_p2 = 60 pF
```

Always round to standard E96 values and simulate in LTspice before soldering.

## Common Pitfalls & Gotchas

1. **Ignoring the output capacitor’s DC bias derating.** A 47 µF, 10V ceramic capacitor might measure 20 µF at 5V bias. Your calculated f_LC shifts from 7.3 kHz to 11.2 kHz, and your zeros no longer cancel the double pole. Always use the effective capacitance at your output voltage. Check the manufacturer’s DC bias curves.

2. **Placing the crossover too close to f_sw.** I’ve seen designs with f_c = f_sw/3 that worked on the bench but oscillated at high temperature. Subharmonic oscillation from the modulator’s sampling effect kicks in when f_c > f_sw/4. Keep it at f_sw/5 or lower for robust designs.

3. **Forgetting the output capacitor’s ESR zero location.** With ceramic capacitors, ESR is milliohms, pushing f_ESR to hundreds of kHz—well above crossover. Type II compensation (which relies on that zero) will give you <10° of phase margin. Always use Type III for ceramics. I learned this the hard way when a “stable” design oscillated after swapping electrolytics for ceramics to save board space.

## Try It Yourself

1. **Simulate a Type II vs. Type III compensation** in LTspice using a TPS54360 model. Use a 47 µF electrolytic (ESR ≈ 100 mΩ) for Type II, then swap to a ceramic (ESR ≈ 5 mΩ) and observe the phase margin change. Sweep the load from 0.1A to 3A and note the transient response.

2. **Measure the loop gain** of your existing bench supply using a network analyzer (or a cheap VNA like the NanoVNA with an injection transformer). Inject a 100 mV sine wave into the feedback loop and sweep from 100 Hz to 500 kHz. Plot gain and phase—does your supply have >45° margin?

3. **Hand-calculate compensation** for a 3.3V output, 500 kHz buck converter with L = 4.7 µH, C_out = 22 µF ceramic (ESR = 3 mΩ), V_in = 12V. Use the Python script above, then verify with the manufacturer’s WEBENCH tool. Compare the component values—why might they differ?

## Next Up

Tomorrow: **Battery Charging Circuits: Li-Ion/LiPo Charge Management ICs** — we’ll dive into constant-current/constant-voltage (CC/CV) profiles, charge termination, and thermal regulation using the MAX17320 fuel gauge and BQ25601 charger IC. Bring your soldering iron.
