---
title: "Day 04: Reflections & Termination Strategies: Series, Parallel & AC Termination"
date: 2026-07-13
tags: ["til", "high-speed-design", "termination", "reflections"]
---

## What I Explored Today

Today I dug into the physics of signal reflections and the three practical termination strategies that keep our high-speed traces from ringing like a bell. I’ve seen boards where a 50 MHz clock looked like a damped sine wave on the scope—turns out the root cause was a simple impedance mismatch at the receiver. I worked through the math behind the reflection coefficient, then simulated and measured series, parallel, and AC termination on a 100 mm microstrip trace. The key takeaway: termination isn’t about “matching” in the abstract; it’s about absorbing the reflected energy so the driver and receiver see a clean, single-trip waveform.

## The Core Concept

Reflections happen when a signal encounters an impedance discontinuity. The reflection coefficient at any interface is:

```
Γ = (Z_load - Z_0) / (Z_load + Z_0)
```

If Z_load equals Z_0, Γ = 0 and no reflection occurs. In practice, we have three ways to force this match:

**Series Termination (Source Termination)**  
Place a resistor (typically R_s = Z_0 - R_driver) in series with the driver output, right at the pin. The driver now sees a total impedance of Z_0, so the launched voltage is half the supply. The wave travels to the open receiver, reflects with Γ ≈ +1, and doubles to the full rail. No further reflection because the source resistor absorbs the return. This is the most power-efficient method—no DC current flows after the line settles.

**Parallel Termination (Load Termination)**  
Place a resistor from the receiver input to ground (or VCC/2 for SSTL) equal to Z_0. The wave sees a matched load on the first arrival, so no reflection occurs. The driver must supply DC current through the resistor, which increases power consumption. Common values: 50 Ω to ground for single-ended, or a Thevenin pair (e.g., 50 Ω to VCC and 50 Ω to GND) for differential-like termination.

**AC Termination**  
A capacitor in series with the parallel resistor (RC network) at the load. The capacitor blocks DC, so the termination only acts on the signal edges. This is useful when you need to match the line’s characteristic impedance for high-speed edges but cannot tolerate the DC power penalty of a pure parallel term. The RC time constant should be about 3–5× the signal rise time to avoid distorting the edge.

## Key Commands / Configuration / Code

Below is a real HyperLynx simulation setup for a 50 Ω microstrip, comparing all three terminations. The driver is a 3.3 V LVCMOS buffer with 10 Ω output impedance.

```
* HyperLynx LineSim netlist snippet
* Trace: 100 mm, Z0=50 Ω, tpd=6.5 ps/mm

* Driver model (IBIS: LVC1G125)
U1 A1 0 DRV_PAD
.MODEL LVC1G125_33 D_INV ...
+ VCC=3.3 RON=10

* Series termination (R_s = 50 - 10 = 40 Ω)
R_SERIES DRV_PAD TRACE 40

* Trace model
T1 TRACE 0 LOAD_PAD Z0=50 TD=650p

* Parallel termination (50 Ω to ground)
R_PAR LOAD_PAD 0 50

* AC termination (50 Ω + 100 pF)
R_AC LOAD_PAD C_NODE 50
C_AC C_NODE 0 100p

* Probe at load
.PROBE V(LOAD_PAD)
.TRAN 0.1n 20n
```

**Oscilloscope measurement tip:**  
To verify termination on a real board, use a TDR (Time Domain Reflectometer) or a fast pulse generator + scope. Inject a 200 mV, 200 ps rise-time step into the trace. With no termination, expect a staircase of reflections. With correct series termination, the incident wave is half amplitude and the reflection is invisible at the source. With parallel termination, the first wave is full amplitude and flat.

## Common Pitfalls & Gotchas

1. **Series termination resistor placed at the wrong end.**  
   The resistor must be at the *driver*, as close to the output pin as possible. If you put it at the receiver, the line sees a low-impedance source and high-impedance load—ringing guaranteed. I’ve seen layout engineers drop a 33 Ω resistor at the far end “because it’s near the connector.” Don’t.

2. **AC termination time constant too fast.**  
   If the RC time constant (R × C) is shorter than the signal rise time, the capacitor charges during the edge and the termination appears as a short to ground, killing the signal amplitude. Rule of thumb: τ = R × C ≥ 3 × t_rise. For a 1 ns rise time and 50 Ω, use at least 60 pF.

3. **Parallel termination creates DC power waste.**  
   A 50 Ω pull-down on a 3.3 V signal draws 66 mA continuously. On a 16-bit bus, that’s over 1 A just for termination. Always check the total power budget before choosing parallel termination. Series termination draws near-zero DC current.

## Try It Yourself

1. **Simulate a 50 Ω microstrip with no termination.**  
   Use a 100 MHz square wave, 1 ns rise time. Measure the voltage at the load. Calculate the reflection coefficient for a high-impedance load (1 MΩ). Confirm the overshoot is about 100% of the incident wave.

2. **Add series termination.**  
   Choose R_s = Z_0 - R_driver. For a 50 Ω line and 10 Ω driver, use 40 Ω. Simulate and verify the load waveform reaches full amplitude after one round-trip delay (2 × TD). Measure the voltage at the driver—it should show a half-amplitude step.

3. **Swap to parallel termination.**  
   Replace the series resistor with a 50 Ω to ground at the load. Observe the waveform is clean on the first edge, but measure the DC current through the resistor. Compare power dissipation to the series case.

## Next Up

Tomorrow I’ll tackle **Differential Pairs: USB, LVDS, PCIe Routing Rules**—impedance matching for differential signals, intra-pair skew, and the critical “no stubs on the pair” rule. We’ll look at real layout examples from USB 2.0 and PCIe Gen 3.
