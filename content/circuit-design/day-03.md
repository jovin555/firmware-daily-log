---
title: "Day 03: Op-Amp Applications: Comparators, Integrators & Differentiators"
date: 2026-07-12
tags: ["til", "circuit-design", "comparator", "integrator"]
---

## What I Explored Today

Today I dove into three fundamental op-amp configurations that move beyond simple amplification: the comparator, the integrator, and the differentiator. While the inverting and non-inverting amplifiers are the bread and butter of linear circuits, these three topologies unlock entirely new domains—threshold detection, analog computation, and waveform shaping. I spent the afternoon simulating each circuit in LTspice and then breadboarding them with an LM358, paying close attention to real-world behavior versus ideal equations.

## The Core Concept

The key insight is that an op-amp's behavior is defined entirely by its feedback network. In a comparator, we intentionally remove feedback (or use positive feedback) to drive the output into saturation—it becomes a 1-bit analog-to-digital converter. In integrators and differentiators, we replace feedback resistors with capacitors to exploit the relationship between voltage and current in a capacitor: \( I = C \frac{dV}{dt} \). This turns the op-amp into an analog computer that can solve differential equations in real time.

Why does this matter? Comparators are everywhere: over-voltage protection, zero-crossing detectors, and window comparators for sensor thresholds. Integrators form the heart of analog filters (especially active low-pass filters) and are essential in control systems (PID controllers). Differentiators are less common due to noise amplification, but they appear in rate-of-change detectors and waveform edge detection.

## Key Commands / Configuration / Code

### 1. Comparator (Open-Loop)

The simplest comparator uses no feedback. The output swings to the positive or negative rail depending on which input is higher.

```
* Comparator circuit (LM358)
Vcc  V+  0  5V
Vee  V-  0  0V
Vin  IN+ 0  SIN(0 2.5 1kHz)  ; 2.5V offset, 2.5V amplitude
Vref IN- 0  DC 2.5
XU1  OUT IN- IN+ V+ V-  LM358
Rpu  OUT V+  10k  ; pull-up for open-collector output
```

**Key observation:** Without hysteresis, noise on the input near the threshold causes rapid, unwanted toggling. Add positive feedback (a resistor from OUT to IN+) to create hysteresis.

### 2. Inverting Integrator

The classic integrator places a capacitor in the feedback path and a resistor at the input.

```
* Inverting integrator
Vin  IN   0  PULSE(0 1 0 1u 1u 500u 1m)
Rin  IN   N  10k
Cfb  N    OUT 0.1uF
XU1  OUT  N 0 V+ V-  LM358
V+   V+   0  5V
V-   V-   0  0V
```

**Transfer function:** \( V_{OUT} = -\frac{1}{R_{IN}C_{FB}} \int V_{IN} \, dt \)

For a 1V step input: \( V_{OUT}(t) = -\frac{1}{10k \cdot 0.1\mu F} \cdot 1V \cdot t = -1000 \cdot t \) volts/second. The output ramps at 1V/ms.

**Critical addition:** Place a large resistor (e.g., 1MΩ) in parallel with \( C_{FB} \) to prevent DC offset integration from saturating the output. This creates a "leaky integrator" with a low-frequency pole at \( f = \frac{1}{2\pi R_{FB}C_{FB}} \).

### 3. Inverting Differentiator

The differentiator swaps the resistor and capacitor positions.

```
* Inverting differentiator
Vin  IN   0  PULSE(0 1 0 1u 1u 500u 1m)
Cin  IN   N  0.1uF
Rfb  N    OUT 10k
XU1  OUT  N 0 V+ V-  LM358
V+   V+   0  5V
V-   V-   0  0V
```

**Transfer function:** \( V_{OUT} = -R_{FB}C_{IN} \frac{dV_{IN}}{dt} \)

For a 1V/1µs rising edge: \( V_{OUT} = -10k \cdot 0.1\mu F \cdot 1V/\mu s = -1V \). The output spikes on edges and returns to zero during flat regions.

**Critical addition:** Add a small resistor in series with \( C_{IN} \) (e.g., 100Ω) to limit high-frequency gain and prevent oscillation. Also add a capacitor in parallel with \( R_{FB} \) (e.g., 100pF) to roll off gain at high frequencies.

## Common Pitfalls & Gotchas

1. **Comparator without hysteresis oscillates at threshold.** Every real-world signal has noise. Without positive feedback (a few mV of hysteresis), the comparator will chatter as the input crosses the reference. Always add 1-10mV of hysteresis using a resistor from output to non-inverting input.

2. **Integrator output drifts to rail.** Even with zero input, the op-amp's input offset voltage (typically 2-7mV for an LM358) integrates over time, causing the output to saturate. Always include a feedback resistor (1MΩ–10MΩ) to provide DC feedback. This creates a high-pass filter, so choose the resistor such that the corner frequency is below your lowest signal frequency.

3. **Differentiator amplifies high-frequency noise.** The gain of a differentiator increases with frequency (\( A_v = -2\pi f R_{FB}C_{IN} \)). At high frequencies, this amplifies noise and can cause oscillation. Always limit the bandwidth by adding a series resistor with the input capacitor and a feedback capacitor. A good rule of thumb: set the maximum gain to 20-40dB at the highest frequency of interest.

## Try It Yourself

1. **Build a window comparator** using two op-amps: one as a non-inverting comparator (threshold = 2V) and one as an inverting comparator (threshold = 3V). Combine their outputs with a diode-OR configuration to create a circuit that goes HIGH only when the input is between 2V and 3V. Test with a triangle wave.

2. **Design a triangle-to-sine wave converter** using an integrator. Feed a square wave into the integrator to produce a triangle wave. Then, use a diode shaping network (or a second op-amp as a differential pair) to round the triangle peaks into a sine wave. Measure the total harmonic distortion (THD) at 1kHz.

3. **Build a differentiator-based edge detector** for a 5V digital signal. Design the circuit so that a rising edge produces a 5V, 10µs pulse, and a falling edge produces a -5V, 10µs pulse. Use a comparator after the differentiator to convert the negative pulse to a positive logic pulse. Test with a 100Hz square wave.

## Next Up

Tomorrow, we step into the world of power management with **Power Supply Design: Linear Regulators (LDO) Basics**. We'll cover dropout voltage, quiescent current, PSRR, and how to choose the right LDO for noise-sensitive analog circuits.
