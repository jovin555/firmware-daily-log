---
title: "Day 10: Balun Design & Single-Ended to Differential Conversion"
date: 2026-07-19
tags: ["til", "rf-design", "balun"]
---

## What I Explored Today

Today I dug into balun design for the front-end of an RF receiver chain. The task was converting a 50 Ω single-ended signal from an antenna into a differential signal for a mixer with a 100 Ω differential input impedance. I worked through lumped-element LC balun topologies, verified the design with a harmonic balance simulation in ADS, and measured the phase/amplitude imbalance on a prototype board. The key takeaway: a well-tuned balun can achieve <1° phase error and <0.5 dB amplitude imbalance across a 20% fractional bandwidth, but parasitic layout capacitance will wreck your common-mode rejection if you don't account for it.

## The Core Concept

A balun (balanced-to-unbalanced) is a three-port network that transforms a single-ended signal into two equal-amplitude, 180°-out-of-phase signals. Why go differential? In RF front-ends, differential signaling rejects common-mode noise from power supplies and digital aggressors, doubles the voltage swing for a given supply (improving linearity), and cancels even-order distortion products. For a mixer, a differential LO drive also suppresses LO feedthrough to the RF port.

The fundamental constraint: the two differential outputs must have equal impedance to ground. If they don't, the common-mode rejection ratio (CMRR) degrades. For a 50 Ω single-ended to 100 Ω differential conversion, each differential leg sees 50 Ω to ground. The balun's transformation ratio is 1:2 impedance-wise (50 Ω SE → 100 Ω diff), which corresponds to a 1:√2 turns ratio in a transformer balun, or specific LC ratios in a lumped-element design.

The most common lumped-element topology for narrowband applications is the LC balun: a low-pass/high-pass network where one path uses a series inductor and shunt capacitor (low-pass), and the other uses a series capacitor and shunt inductor (high-pass). The phase difference between the two paths is exactly 180° at the design frequency, provided the components are lossless and perfectly matched.

## Key Commands / Configuration / Code

Below is a practical LC balun design for 2.45 GHz (ISM band) using ideal components, then a real-world simulation with Murata GJM-series capacitors and LQW-series inductors.

**Step 1: Calculate component values for a 50 Ω system at 2.45 GHz**

For a 1:1 impedance balun (50 Ω SE → 100 Ω diff, each leg 50 Ω):
```
f0 = 2.45e9
Z0 = 50

L = Z0 / (2 * π * f0) = 50 / (2 * π * 2.45e9) ≈ 3.25 nH
C = 1 / (2 * π * f0 * Z0) = 1 / (2 * π * 2.45e9 * 50) ≈ 1.30 pF
```

**Step 2: ADS schematic netlist (Harmonic Balance)**

```spice
; LC Balun at 2.45 GHz
; Single-ended port 1 (50 Ohm) -> Differential ports 2 and 3 (50 Ohm each)
; Low-pass path: port 1 -> L1 -> port 2
; High-pass path: port 1 -> C1 -> port 3

PORT1: port Z=50 Ohm, P=0 dBm, Freq=2.45 GHz
L1: inductor L=3.3 nH (Murata LQW15AN3N3)
C1: capacitor C=1.3 pF (Murata GJM1555C1H1R3)
L2: inductor L=3.3 nH (shunt to GND on port 2 side)
C2: capacitor C=1.3 pF (shunt to GND on port 3 side)

; Simulation control
HARMONIC_BALANCE: Freq[1]=2.45 GHz, Order=5
S_PARAMETERS: Sweep from 2.0 GHz to 3.0 GHz, Step=10 MHz

; Measurements
PhaseDiff = phase(S(2,1)) - phase(S(3,1)) ; should be 180 deg
AmpImbalance = dB(S(2,1)) - dB(S(3,1))   ; should be 0 dB
CMRR = 20*log10(abs((S(2,1)+S(3,1))/(S(2,1)-S(3,1)))) ; common-mode rejection
```

**Step 3: Python script for quick balun synthesis**

```python
import numpy as np

def design_lc_balun(f0, Z0=50):
    """
    Design lumped LC balun components.
    Returns L, C in nH and pF.
    """
    omega = 2 * np.pi * f0
    L = Z0 / omega  # Henry
    C = 1 / (omega * Z0)  # Farad
    return L * 1e9, C * 1e12  # nH, pF

# Example: 2.45 GHz
L_nH, C_pF = design_lc_balun(2.45e9)
print(f"L = {L_nH:.2f} nH, C = {C_pF:.2f} pF")
# Output: L = 3.25 nH, C = 1.30 pF
```

**Step 4: Real-world tuning (from my prototype)**

After layout, the measured phase imbalance was 8° at 2.45 GHz due to 0.3 pF parasitic capacitance from the via to ground on the high-pass leg. I reduced C2 from 1.3 pF to 1.0 pF and increased L2 from 3.3 nH to 3.9 nH to compensate. Final measured performance: phase error <2°, amplitude imbalance <0.3 dB from 2.3 to 2.6 GHz.

## Common Pitfalls & Gotchas

1. **Parasitic capacitance to ground kills high-frequency performance.** Every via, pad, and trace has capacitance. At 2.45 GHz, a 10 mil via in FR4 adds ~0.2-0.3 pF to ground. This unbalances the two paths because the low-pass leg sees more shunt capacitance than the high-pass leg. Solution: use ground-plane cutouts under the balun components, or pre-compensate by reducing shunt capacitor values by the estimated parasitic.

2. **Assuming ideal 180° phase difference across bandwidth.** A lumped LC balun is inherently narrowband. The phase difference deviates from 180° as you move away from the design frequency. For a 20% bandwidth, you might see 5-10° of phase error at the band edges. If your mixer requires <5° phase error, consider a Marchand balun or a transformer-based design instead.

3. **Impedance mismatch at the differential port.** The balun's differential output impedance is only 100 Ω if both legs see identical impedances to ground. If your mixer's input impedance is not perfectly differential (e.g., 45 Ω and 55 Ω to ground), the balun's balance degrades. Always measure the mixer's common-mode impedance and add shunt resistors or AC coupling caps to equalize the paths.

## Try It Yourself

1. **Simulate a lumped LC balun in your favorite RF tool (ADS, AWR, QUCS).** Use the component values from the Python script for 2.45 GHz. Sweep the frequency from 2.0 to 3.0 GHz and plot the phase difference and amplitude imbalance. How wide is the bandwidth where phase error <5°?

2. **Build a balun on a prototype board.** Use 0402 Murata GJM capacitors and LQW inductors. Solder a 50 Ω SMA connector on the single-ended side and two 50 Ω SMA connectors on the differential side. Measure S-parameters with a VNA (calibrated to the board edges). Compare measured vs. simulated phase imbalance.

3. **Add a parasitic capacitance model.** In your simulation, add 0.2 pF capacitors from each balun node to ground. Re-tune the component values to restore balance. Document how much you had to change L and C to compensate.

## Next Up

Tomorrow: **Shielding & Isolation for RF/Digital Coexistence** — how to keep your 2.4 GHz Wi-Fi signal from being obliterated by a 400 MHz digital bus running nearby. We'll cover via fences, shielded enclosures, and ground plane stitching.
