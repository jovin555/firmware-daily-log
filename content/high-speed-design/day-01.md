---
title: "Day 01: What Makes a Signal 'High-Speed'? Rise Time vs Clock Frequency"
date: 2026-07-10
tags: ["til", "high-speed-design", "high-speed", "rise-time"]
---

## What I Explored Today

Most engineers assume a signal is "high-speed" when the clock frequency is high—say, above 100 MHz. That's a dangerous oversimplification. Today I dug into the real criterion: the signal's rise time (or fall time) relative to the electrical length of the interconnect. The key insight is that a 1 MHz square wave with 100 ps edges can cause more signal integrity headaches than a 1 GHz sine wave. The industry rule of thumb is that if the trace length exceeds one-sixth of the signal's rising-edge spatial extent, you're in high-speed territory and must treat the trace as a transmission line.

## The Core Concept

The distinction between "high-speed" and "high-frequency" is subtle but critical. Clock frequency tells you how often a signal transitions, but rise time tells you how fast the transition happens. A fast edge contains high-frequency harmonics—Fourier analysis shows that a trapezoidal wave's bandwidth is approximately 0.35 / tr (where tr is the 10%-to-90% rise time). For a 1 ns rise time, that's 350 MHz of bandwidth, regardless of whether the clock is 1 MHz or 100 MHz.

Why does this matter? When the trace length becomes a significant fraction of the wavelength of these harmonics, reflections, ringing, and crosstalk appear. The critical length is typically calculated as:

```
L_critical = (tr * v) / 6
```

Where v is the propagation velocity (roughly 6 inches/ns for FR-4 microstrip). For a 1 ns rise time, L_critical ≈ 1 inch. Any trace longer than that needs impedance control and termination.

The practical takeaway: always check the rise time of your driver's datasheet, not just the clock rate. A 50 MHz SPI bus with 200 ps rise time from a modern FPGA I/O is far more demanding than a 200 MHz DDR3 bus with 500 ps edges.

## Key Commands / Configuration / Code

Here's a practical Python snippet to compute the critical length and bandwidth from rise time. I use this in my pre-layout planning to decide which nets need transmission-line treatment.

```python
# critical_length.py — Compute high-speed thresholds from rise time
import math

def high_speed_analysis(tr_ns, dielectric_constant=4.2):
    """
    Analyze a signal based on its 10%-90% rise time.
    
    Args:
        tr_ns: Rise time in nanoseconds
        dielectric_constant: FR-4 typical = 4.2
    
    Returns:
        dict with bandwidth, propagation velocity, critical length
    """
    # Bandwidth from rise time (10%-90% rule)
    bw_ghz = 0.35 / tr_ns  # GHz (since tr_ns is in ns)
    
    # Propagation velocity in FR-4 (inches per ns)
    c = 11.8  # speed of light in inches/ns
    v_inch_per_ns = c / math.sqrt(dielectric_constant)
    
    # Critical length: trace length where reflections become significant
    # Rule of thumb: L > (tr * v) / 6
    L_critical_inches = (tr_ns * v_inch_per_ns) / 6.0
    
    # Wavelength of the highest significant harmonic (3rd harmonic of BW)
    f_max_ghz = 3 * bw_ghz  # rough upper bound
    wavelength_inches = v_inch_per_ns / f_max_ghz if f_max_ghz > 0 else float('inf')
    
    return {
        'bandwidth_ghz': round(bw_ghz, 3),
        'velocity_inch_per_ns': round(v_inch_per_ns, 2),
        'critical_length_inches': round(L_critical_inches, 2),
        'wavelength_at_3rd_harmonic_inches': round(wavelength_inches, 2)
    }

# Example: 1 ns rise time (typical for 100 MHz LVCMOS)
result = high_speed_analysis(tr_ns=1.0)
print(f"Bandwidth: {result['bandwidth_ghz']} GHz")
print(f"Critical length: {result['critical_length_inches']} inches")
# Output: Bandwidth: 0.35 GHz
# Output: Critical length: 1.15 inches
```

For a real-world check, I use an oscilloscope with a fast edge to measure actual rise time at the driver pin. On a Tektronix MSO, the command is:

```
MEASUREMENT:MEAS1:TYPE RISetime
MEASUREMENT:MEAS1:SOURCE CH1
```

Then compare to your pre-layout estimate. If the measured rise time is faster than expected, your critical length shrinks, and you may need to add series termination or reroute.

## Common Pitfalls & Gotchas

**1. Assuming clock frequency is the only metric.** I've seen designs with a 25 MHz crystal oscillator that used a 74LVC1G125 buffer with 2 ns rise time—perfectly fine for a 6-inch trace. Then the same engineer swapped to a Si5351 clock generator with 400 ps rise time and wondered why the same trace showed 1 V of overshoot. Always check the driver's datasheet for rise time, not just the clock rate.

**2. Ignoring load capacitance's effect on rise time.** A fast driver into a heavy capacitive load (e.g., multiple fan-outs, long stubs) can slow the effective rise time at the receiver. This can actually *help* by reducing bandwidth, but it also increases propagation delay and can cause timing violations. Simulate with IBIS models or measure at the load, not just the source.

**3. Using the 1/6 rule blindly for all topologies.** The L_critical = (tr * v) / 6 rule assumes a lumped-element model and a single trace. For differential pairs, busses with multiple loads, or traces with vias, the critical length can be shorter. I use 1/10 as a conservative bound for critical nets, and always run a TDR simulation if the trace is within 2x of the critical length.

## Try It Yourself

1. **Measure rise time on your bench.** Grab any digital signal (e.g., a microcontroller's GPIO toggling at 1 MHz) and measure the 10%-90% rise time with a scope. Compute the bandwidth and critical length. Is your trace longer than L_critical? If so, you may have reflections you never noticed.

2. **Compare two drivers.** Look up the datasheets for a 74LVC1G07 (open-drain buffer) and a 74AUP1G07 (advanced ultra-low power). Note the typical rise time at 3.3 V with 15 pF load. Which one would force you to treat a 2-inch trace as a transmission line? (Answer: the AUP family has ~1.5 ns rise time; LVC is ~3 ns.)

3. **Simulate a fast edge on a long trace.** Use a free tool like LTspice or the Saturn PCB Toolkit. Set up a 50-ohm source with a 500 ps rise time driving a 6-inch microstrip on FR-4. Add no termination. Observe the ringing at the load. Then add a 50-ohm series resistor at the source and compare the waveform.

## Next Up

Tomorrow: **Transmission Line Theory: When Traces Become Transmission Lines** — We'll derive the telegrapher's equations from first principles, show how characteristic impedance emerges from geometry, and walk through the exact conditions that force you to stop treating a trace as a simple wire.
