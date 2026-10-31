---
title: "Day 21: Reliability Testing: HALT, Accelerated Life & Environmental Testing"
date: 2026-10-31
tags: ["til", "medical-iot-dfmea", "halt", "reliability"]
---

# Day 21: Reliability Testing: HALT, Accelerated Life & Environmental Testing

## What I Explored Today

Today I moved from paper-based DFMEA analysis into the physical verification loop: reliability testing. For a wearable ECG patch with a BLE radio and a lithium-polymer cell, the DFMEA flagged "solder joint fatigue on the flex-to-PCB interconnect" and "battery seal breach under thermal cycling" as high-RPN failure modes. The question is how to prove those risks are actually mitigated before we commit to a design freeze. I spent the day working through the three-tier reliability test strategy — HALT to find the operating and destruct limits, accelerated life testing (ALT) to quantify field life against a target, and environmental testing to verify compliance against the standards our notified body will audit (IEC 60601-1, IEC 60068-2-x). The key insight: these are not interchangeable. HALT is qualitative and exploratory; ALT is quantitative and statistical; environmental testing is pass/fail against a published spec.

## The Core Concept

The "why" here is that you cannot test your way to reliability at use conditions. A device rated for 5 years at 25 °C would need 5 years of testing — unacceptable for a development cycle. So we accelerate the physics of failure and then map results back to field conditions using a model.

**HALT** (Highly Accelerated Life Test) steps stress — typically temperature and vibration, often combined — in increments until the device fails, then you push further to find the destruct limit. The goal is not a pass/fail; it's to discover the margin between your spec and where things actually break, and to force latent design weaknesses to surface in hours instead of months. A common rule of thumb: you want at least 10 °C of margin beyond your operating spec on both hot and cold sides.

**ALT** uses a known acceleration model to translate accelerated failures into field-life estimates. For electronics dominated by thermal cycling, the Coffin-Manson model relates cycles-to-failure to the temperature swing:

$$N_f = C \cdot (\Delta T)^{-n}$$

where $n$ is typically 1.9–2.7 for solder joints. For Arrhenius-type (temperature-driven) chemical/insulation failures, you use the Arrhenius acceleration factor:

$$AF = \exp\left[\frac{E_a}{k}\left(\frac{1}{T_{use}} - \frac{1}{T_{stress}}\right)\right]$$

with $E_a$ the activation energy (commonly 0.7 eV for many electronics failure mechanisms) and $k$ the Boltzmann constant. The whole game is picking the right model for the dominant failure mechanism — pick wrong and your life projection is fiction.

**Environmental testing** is the compliance layer: IEC 60068-2-1 (cold), -2-2 (dry heat), -2-14 (thermal shock), -2-27 (shock), -2-64 (random vibration), plus IEC 60529 IP ratings for the seal. These are pass/fail against a defined profile, and the profiles must match your intended use environment (a patch worn on skin during exercise is not the same as a benchtop monitor).

## Key Commands / Configuration / Code

A representative HALT thermal step profile and an ALT life calculation in Python:

```python
import numpy as np

# --- HALT thermal step profile (per chamber setpoint, °C) ---
# Start at 20 °C, step down 10 °C per dwell until failure, then up.
# Dwell 10 min at each step; monitor DUT current + BLE RSSI continuously.
halt_cold_steps = [20, 10, 0, -10, -20, -30, -40, -50]
halt_hot_steps  = [20, 30, 40, 50, 60, 70, 80, 90]
DWELL_MIN = 10

# --- Coffin-Manson ALT projection for solder-joint fatigue ---
# N_f = C * (dT)^-n ; calibrate C from accelerated test result.
n = 2.0                      # fatigue exponent for SAC305, typical 1.9-2.7
dT_use    = 15.0             # °C, field thermal swing (skin-worn patch)
dT_stress = 80.0             # °C, chamber swing during ALT
N_stress  = 1200             # cycles to failure observed in ALT

C = N_stress * (dT_stress ** n)
N_use = C * (dT_use ** -n)
print(f"Projected field cycles to failure: {N_use:,.0f}")
# ~34,000 cycles -> at 2 cycles/day = ~46 years. Comfortable margin.

# --- Arrhenius acceleration factor for a 85 °C / 85 %RH biased test ---
k  = 8.617e-5                # eV/K
Ea = 0.7                     # eV, typical for corrosion/ion migration
T_use_K   = 25 + 273.15
T_stress_K = 85 + 273.15
AF = np.exp((Ea / k) * (1/T_use_K - 1/T_stress_K))
print(f"Acceleration factor: {AF:.1f}x")
# 1000 h at 85 °C ≈ {1000*AF/8760:.1f} years at 25 °C
```

A minimal IEC 60068-2-14 thermal-shock profile as a chamber recipe (pseudo-YAML for a common controller):

```yaml
profile: thermal_shock_iec60068_2_14
cold_chamber: -40      # °C
hot_chamber:  +85      # °C
dwell: 30              # minutes each chamber
transfer_time: 5       # minutes max, per standard
cycles: 100
monitor:
  - dut_current_mA     # detect open/short during dwell
  - ble_rssi_dbm       # detect antenna/interconnect degradation
```

## Common Pitfalls & Gotchas

1. **Using the wrong acceleration model.** Applying Arrhenius to a fatigue mechanism (or Coffin-Manson to a chemical one) produces a confident-looking but meaningless life number. Identify the dominant failure mechanism first — often via HALT and failure analysis — then select the model. Document the assumption; auditors will ask.

2. **HALT on a non-representative build.** HALT results are only meaningful on hardware that matches production intent (same solder alloy, same potting, same battery). Running HALT on a hand-soldered prototype and declaring margin is a classic DFMEA-to-verification disconnect.

3. **Forgetting the monitoring during environmental test.** A device that "passes" 100 thermal cycles but whose BLE link silently degraded at cycle 40 is a field failure waiting to happen. Instrument the DUT (current draw, RF, seal integrity) throughout, not just at the end.

## Try It Yourself

1. **Build the ALT calculator.** Take your own device's field thermal swing and a plausible ALT chamber profile, and compute the Coffin-Manson projection. Then vary the fatigue exponent `n` from 1.9 to 2.7 and note how much the projected life changes — this is your sensitivity to model choice.

2. **Draft a HALT step plan.** Write the cold and hot step sequences for your product, including dwell time and the pass/fail criteria you'll monitor at each step. Define in advance what "failure" means (functional, parametric, or cosmetic).

3. **Map your DFMEA high-RPN items to a test.** For each failure mode with RPN above your threshold, assign it to HALT (find margin), ALT (quantify life), or environmental (compliance). Any high-RPN item with no assigned test is a gap to close before design freeze.

## Next Up

Tomorrow: **Design for Manufacturability & Linking DFMEA to PFMEA for Medical Devices** — how the failure modes we verified today flow into the process FMEA, and why a design that passes HALT can still fail on the line if the process isn't controlled.
