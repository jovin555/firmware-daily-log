---
title: "Day 21: Debugging Analog Circuits: Oscilloscope & Multimeter Techniques"
date: 2026-08-01
tags: ["til", "circuit-design", "oscilloscope", "multimeter"]
---

## What I Explored Today

Analog debugging is a different beast from digital. A logic analyzer won't tell you why your op-amp output is sitting at 2.3 V instead of 3.3 V, and a `printf` won't help you find the 50 mV ripple on your reference rail. Today I focused on the two tools that matter most for analog work: the oscilloscope for time-domain behavior and the multimeter for DC accuracy and continuity. I spent the day chasing a phantom offset in a transimpedance amplifier and learned more about probe compensation, ground lead inductance, and the difference between "measuring" and "believing" a multimeter reading than I have in the past month.

## The Core Concept

The fundamental rule of analog debugging is: **the measurement tool changes the circuit**. A multimeter has input impedance around 10 MΩ, which is fine for most nodes but will load a high-impedance source like a photodiode or a CMOS op-amp output. An oscilloscope probe has a 1 MΩ input impedance in 1x mode, but in 10x mode it presents 10 MΩ in parallel with ~10-15 pF. That capacitance matters at high frequencies and can shift the phase margin of a feedback loop.

The second concept is **ground is not ground**. The scope's ground clip is a wire with inductance. At 10 MHz, a 3-inch ground lead has roughly 100 nH, which gives an impedance of about 6 Ω. That's enough to inject switching noise into your measurement. The fix is to use a short ground spring or a ground plane directly under the probe tip.

The third concept is **DC accuracy vs. AC visibility**. A multimeter gives you a single number, averaged over time. It hides ripple, oscillation, and transient behavior. An oscilloscope shows you everything, but its vertical accuracy is typically only 8-12 bits. For a precise DC voltage, trust the multimeter. For understanding *why* that voltage is wrong, use the scope.

## Key Commands / Configuration / Code

Let's walk through a real scenario: you have a 10x probe and you're measuring a 1 kHz square wave from a function generator. The square wave looks rounded or has overshoot. That's a probe compensation problem.

**Step 1: Compensate the probe.**

Set the scope to 1 kHz, 1 Vpp square wave. Connect the probe to the calibration output (usually marked `CAL` or `1 kHz`). Adjust the trimmer capacitor on the probe body until the corners of the square wave are sharp and flat. This matches the probe's capacitance to the scope's input capacitance.

**Step 2: Set up the scope for analog work.**

```
# On a typical digital scope (Keysight, Tektronix, Rigol):
# 1. Set channel coupling to DC (AC coupling blocks DC offset, hides DC bias)
CH1: Coupling -> DC

# 2. Set bandwidth limit to 20 MHz if you're looking at low-frequency signals
#    This reduces high-frequency noise pickup
CH1: BW Limit -> 20 MHz

# 3. Use 10x probe, set the scope to match
CH1: Probe -> 10x

# 4. Trigger on the signal, not the noise
Trigger: Mode -> Edge, Source -> CH1, Slope -> Rising
Trigger: Level -> set to 50% of expected amplitude
```

**Step 3: Measure DC offset with the multimeter.**

```
# Use a 6.5-digit multimeter (Keysight 34461A or similar) for DC accuracy
# Set to DCV, use the front terminals, not the rear
# Connect in parallel with the node you're measuring
# Wait for the reading to settle (autorange can take 1-2 seconds)

# For low-impedance nodes (< 1 kΩ), use 4-wire resistance measurement
# to eliminate lead resistance error
```

**Step 4: Measure ripple on a DC rail.**

```
# Scope setup for ripple:
# 1. AC coupling (removes the DC level, lets you zoom into the ripple)
CH1: Coupling -> AC

# 2. Set vertical scale to 10-50 mV/div (not 1 V/div)
CH1: Scale -> 20 mV/div

# 3. Set horizontal scale to see the ripple frequency
#    For 100 kHz ripple, set timebase to 5 µs/div
Timebase -> 5 µs/div

# 4. Use "Math" function to measure peak-to-peak
Math: Source CH1, Function -> Vpp
```

**Step 5: Use the multimeter's AC mode correctly.**

```
# Multimeter AC mode measures RMS of the AC component
# It's only accurate for sine waves above ~10 Hz and below ~100 kHz
# For non-sinusoidal ripple, use the scope's Vpp measurement instead

# If you must use the multimeter, set it to AC+DC mode
# (some meters have this, e.g., Fluke 87V)
Mode -> AC+DC
```

## Common Pitfalls & Gotchas

**1. The ground lead inductance trap.** I've seen engineers chase a "50 MHz oscillation" that was actually the scope's ground lead picking up switching noise from a nearby buck converter. The fix is to remove the long ground lead and use a ground spring (a small coil that fits over the probe tip). This reduces the ground loop area from several square inches to a few square millimeters. If you see high-frequency noise that disappears when you touch the probe tip to the ground plane directly, it's your measurement setup, not the circuit.

**2. Multimeter loading on high-impedance nodes.** A 10 MΩ input impedance is fine for a voltage divider with 1 kΩ resistors. But if you're measuring the output of a photodiode transimpedance amplifier with a 10 MΩ feedback resistor, the meter's input impedance forms a divider with the feedback network. You'll read 5 V when the actual output is 10 V. Always check the source impedance before trusting a multimeter reading. If in doubt, use a scope with a 10x probe (10 MΩ) and verify the reading doesn't change when you switch to 1x (1 MΩ).

**3. AC coupling hides the DC bias point.** When you switch to AC coupling to look at ripple, you lose the DC level. That's fine for ripple, but if you're debugging an op-amp that's railed, you'll see a flat line at 0 V and think the circuit is dead. Always check the DC level first with DC coupling, then switch to AC for the fine details.

## Try It Yourself

1. **Probe compensation check.** Set up a 1 kHz square wave on your scope's calibration output. Connect a 10x probe and observe the waveform. Adjust the probe's trimmer capacitor until the corners are sharp. Now switch to 1x mode and observe the difference in bandwidth and loading. Note the change in amplitude and rise time.

2. **Ground lead experiment.** Build a simple circuit with a 1 MHz clock signal (any microcontroller or function generator). Measure the clock with a scope using the standard 3-inch ground lead. Then replace the ground lead with a ground spring or a short wire to the ground plane. Compare the noise and ringing on the waveform. You'll see a dramatic difference.

3. **Multimeter loading test.** Build a voltage divider with two 10 MΩ resistors across a 5 V supply. Measure the output with a multimeter. You'll read about 2.5 V. Now measure the same node with a scope using a 10x probe. The reading will be closer to 2.5 V but slightly different due to the probe's 10 MΩ in parallel. Now switch the scope to 1x mode (1 MΩ input) and watch the voltage drop. This demonstrates why you must always consider source impedance.

## Next Up

Tomorrow we'll do a full review and put everything together: **Design a Battery-Powered Sensor Front-End**. We'll combine low-power design, op-amp selection, filtering, and ADC interfacing into a complete, buildable circuit. We'll also revisit the debugging techniques from today to verify the design works as intended. Bring your multimeter and scope — we'll need them.
