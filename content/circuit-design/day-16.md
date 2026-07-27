---
title: "Day 16: Reverse Polarity & Overcurrent Protection Circuits"
date: 2026-07-27
tags: ["til", "circuit-design", "reverse-polarity", "overcurrent"]
---

## What I Explored Today

I spent the day designing and simulating protection front-ends for a 12V DC-powered embedded system. The goal was to protect a downstream load (a Raspberry Pi + motor controller) from two common real-world failures: a user plugging in a power supply with reversed polarity, and a downstream short circuit drawing excessive current. I prototyped three approaches: a P-channel MOSFET reverse polarity protector, a resettable PTC fuse for overcurrent, and a combined circuit using a high-side current-sense amplifier driving a latch-off MOSFET. Each has trade-offs in voltage drop, cost, and reset behavior.

## The Core Concept

Reverse polarity protection prevents destruction when the power supply is connected backwards. A simple series diode works but drops 0.6–0.9V—problematic for 3.3V or 5V rails where every millivolt matters. The P-channel MOSFET solution uses the transistor's body diode to initially conduct, then the gate-source voltage turns the FET fully on, creating a low-resistance path (Rds(on) ~10–50 mΩ) with negligible voltage drop. The key: the MOSFET must be placed in the high-side path with its gate pulled to ground through a resistor, so when the input is reversed, the gate-source voltage is zero and the FET blocks.

Overcurrent protection must respond faster than the power supply's own current limit (often 2–5A for bench supplies, but a short can draw 20A before the supply reacts). A PTC fuse is simple and resettable, but its trip time is slow (seconds) and it has a high post-trip resistance. For faster protection, a current-sense resistor feeding a comparator (like the MAX4372 or a discrete op-amp) can drive a logic-level MOSFET to latch off the load within microseconds. The latch requires a manual reset or a timer—critical for unattended systems.

## Key Commands / Configuration / Code

### 1. P-Channel MOSFET Reverse Polarity Protection

This circuit assumes a 12V input, 2A load. The MOSFET must have Vgs(th) < 4V (typical for logic-level parts like IRF9540N or FQP27P06).

```
Schematic connections:
- Source: connected to input positive (VIN+)
- Drain: connected to load positive (VOUT+)
- Gate: connected to GND through R1 (10kΩ)
- Optional: Zener diode D1 (15V) from gate to source for overvoltage protection

Component values:
R1 = 10kΩ (pulls gate to GND, enabling Vgs when VIN is correct)
D1 = 15V Zener (clamps Vgs to safe level if VIN > 15V)
```

When VIN+ is positive relative to GND: body diode conducts briefly, Vgs ≈ -12V (gate at 0V, source at 12V), FET turns on hard. When reversed: source at GND, gate at 0V through R1, Vgs = 0V, FET blocks.

### 2. PTC Fuse Overcurrent Protection

Select a PTC with hold current > load current and trip current < supply limit. For a 2A load:

```
PTC selection:
- Hold current: 2.5A (20% margin)
- Trip current: 5.0A (typical)
- Example: Bourns MF-R250 (2.5A hold, 5A trip)
- Max voltage: 30V (must exceed VIN)
- Time to trip at 8A: < 5 seconds
```

Place the PTC in series with the input, before the reverse polarity MOSFET. This protects both the load and the MOSFET from sustained overcurrent.

### 3. Fast Latch-Off Overcurrent Protection (Discrete)

This circuit uses a 0.1Ω sense resistor and a PNP transistor as a comparator:

```
Components:
R_sense = 0.1Ω, 1W (current sense)
Q1 = 2N3906 (PNP, used as comparator)
Q2 = IRLZ44N (N-channel logic-level MOSFET, latch)
R2 = 10kΩ (base resistor for Q1)
R3 = 100kΩ (pull-up for Q2 gate)
R4 = 1kΩ (gate resistor for Q2)
C1 = 10µF (debounce, optional)

Operation:
- When load current exceeds ~1.5A, voltage across R_sense > 0.15V
- Q1 turns on, pulling Q2 gate high
- Q2 turns on, shorting Q1 base to GND through R2 — latch is set
- Load is disconnected until power is cycled
- Trip threshold: I_trip ≈ 0.6V / R_sense = 6A (adjust R_sense)
```

For a precise threshold, replace Q1 with a comparator (e.g., LM393) and a voltage reference.

## Common Pitfalls & Gotchas

**1. MOSFET gate-source voltage exceeds rating.** A 12V input is fine for most MOSFETs (Vgs max ±20V), but a 24V system can destroy the gate oxide. Always add a Zener diode (15V) from gate to source. I once fried three FETs before remembering this on a 24V industrial sensor.

**2. PTC fuse doesn't trip fast enough for sensitive loads.** A PTC can take 10+ seconds to trip at 2x rated current. During that time, your 3.3V rail may droop below reset threshold, causing undefined behavior. For loads that can't tolerate brownouts, use a fast electronic fuse (latch-off) instead.

**3. Reverse polarity MOSFET conducts when input is floating.** If the gate resistor is too high (e.g., 1MΩ), leakage current through the body diode can charge the gate capacitance and partially turn on the FET. Use a 10kΩ–100kΩ pull-down resistor. Also, ensure the load has a path to GND—if the load is disconnected, the FET may not turn on because there's no current through the body diode to pull the source up.

## Try It Yourself

1. **Simulate a P-channel reverse polarity circuit** in LTspice or Falstad. Use a 12V source, a 10Ω load, and an IRF9540N model. Reverse the source polarity and verify the load voltage is zero. Measure the voltage drop when correct—should be < 50mV at 1A.

2. **Build the discrete latch-off overcurrent protector** on a breadboard with a 12V supply and a variable resistor as load. Start with R_sense = 0.22Ω (trip ~2.7A). Slowly decrease load resistance until the circuit latches. Measure the trip current and compare to the calculated value. Add a pushbutton to reset the latch (short Q2 gate to GND).

3. **Combine both circuits** on a perfboard: PTC fuse → reverse polarity MOSFET → latch-off overcurrent protector → load. Test with a dead short (momentarily touch a wire across the output) and verify the latch trips within microseconds. Measure the voltage drop across the entire protection chain at 2A—should be less than 0.3V total.

## Next Up

Tomorrow, I'm diving into **Motor Driver Circuits: H-Bridges & Gate Drivers**. We'll cover discrete N/P-channel H-bridge design, shoot-through prevention, bootstrap capacitors for high-side N-channel drivers, and how to drive a brushed DC motor with PWM from a microcontroller. Bring your logic-level FETs and dead-time calculations.
