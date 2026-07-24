---
title: "Day 15: ESD Protection: TVS Diodes & Layout Considerations"
date: 2026-07-24
tags: ["til", "circuit-design", "esd", "tvs-diode"]
---

## What I Explored Today

I spent the day digging into the practical realities of ESD protection for production designs. While TVS diodes seem simple—just a diode that clamps voltage—the real challenge is making sure they actually work when a 15 kV discharge hits your board. I focused on selecting the right TVS for signal vs. power lines, and more importantly, the PCB layout rules that separate a working clamp from a fried IC.

## The Core Concept

ESD events are fast: rise times under 1 ns, peak currents exceeding 30 A for an 8 kV contact discharge (IEC 61000-4-2 level 4). A TVS diode works by breaking down in avalanche mode, shunting that current to ground and clamping the voltage to a safe level. But the key parameter isn't just the breakdown voltage—it's the **clamping voltage** at the peak pulse current (V_CL at I_PP). If your layout adds inductance between the TVS and the protected IC, the L * di/dt voltage drop can push the voltage at the IC pin well above the TVS's rated clamp.

The real trick: the TVS must be the *lowest impedance path* for the ESD current, and that path must have minimal inductance. Every via, every trace length, every stray loop adds inductance. At 1 ns rise times, even 10 nH of inductance creates a 300 V drop for a 30 A pulse. That's enough to kill a 5 V tolerant input.

## Key Commands / Configuration / Code

### TVS Selection Checklist (for a 3.3 V signal line)

```text
Parameter              Requirement                  Why
---------------------  --------------------------   ---------------------------
Standoff Voltage (V_RWM)  > 3.3 V (e.g., 3.6 V)    Must not conduct at normal operation
Breakdown Voltage (V_BR)  ~4.0 V (at 1 mA)         Avalanche starts here
Clamping Voltage (V_CL)   < 5.0 V at I_PP          Must protect 3.3 V IC's absolute max
Peak Pulse Current (I_PP) >= 30 A (8/20 µs)        Handles IEC 61000-4-2 level 4
Capacitance (C_j)         < 5 pF for high-speed     Avoids signal integrity issues
```

### Layout Rule of Thumb (in code-like form)

```text
// Critical: TVS must be closest component to connector
// Rule: Trace length from connector pin to TVS anode < 5 mm
// Rule: TVS cathode to ground plane via distance < 2 mm
// Rule: Use at least 2 vias to ground, 0.3 mm drill minimum
// Rule: No other components between TVS and connector
// Rule: Keep protected signal trace away from TVS return path

// Example: USB D+/D- protection layout priority
1. Place TVS within 3 mm of USB connector pins
2. Route D+/D- through TVS first, then to IC
3. Place GND vias directly at TVS ground pad
4. Avoid routing protected traces under TVS body
```

### Example: Using a PESD5V0S1UB (NXP) for a 3.3 V UART

```text
// PESD5V0S1UB key specs:
// V_RWM = 5.0 V, V_BR = 6.4 V, V_CL = 9.8 V at I_PP = 5 A
// C_j = 0.9 pF, I_PP (8/20 µs) = 5 A
// 
// WARNING: This part is for low-speed signals only.
// For 3.3 V UART at 115200 baud, it works.
// For USB 2.0 (480 Mbps), use a part with C_j < 0.5 pF.
```

## Common Pitfalls & Gotchas

1. **Placing the TVS too far from the connector**  
   I've seen designs where the TVS was placed 2 cm away from the HDMI connector, with a long trace in between. That trace acts as an inductor, and the ESD current creates a voltage spike *before* it reaches the TVS. The IC sees that spike and dies. Rule: the TVS must be the *first* component after the connector, with the shortest possible trace.

2. **Using a single via for the TVS ground connection**  
   A single 0.2 mm via has about 1 nH of inductance. At 30 A/ns, that's 30 V of ground bounce. The TVS clamps to 5 V, but the IC's ground reference jumps by 30 V—the IC sees 35 V between its pin and its own ground. Always use multiple vias (at least 2, preferably 4) in parallel to reduce inductance.

3. **Ignoring the TVS capacitance on high-speed lines**  
   A standard 5 V TVS might have 50 pF of capacitance. On a 100 MHz SPI clock line, that capacitance creates a low-pass filter that rounds off the edges and causes timing violations. For high-speed interfaces (USB, HDMI, Ethernet), you need low-capacitance TVS arrays (C_j < 1 pF). Always check the datasheet's capacitance spec.

## Try It Yourself

1. **Select a TVS for a 5 V power input**  
   Find a TVS diode that can handle a 24 V automotive load dump (60 V, 2 A, 400 ms pulse). Calculate the required power rating (P_PPM = V_CL * I_PP). Verify your part can survive 10 such events.

2. **Measure the inductance of a single via**  
   Use a 2-layer board with a ground plane. Drill a 0.3 mm via, solder a wire through it, and measure the inductance with an LCR meter at 1 MHz. Compare to the theoretical value (approximately 1 nH per mm of via height).

3. **Layout a TVS for a USB 2.0 differential pair**  
   Using any EDA tool, place a low-capacitance TVS array (e.g., USBLC6-2SC6) within 3 mm of a USB micro-B connector. Route the D+ and D- traces through the TVS first, then to the IC. Add two ground vias at the TVS ground pad. Measure the trace length from connector pin to TVS pin—keep it under 5 mm.

## Next Up

Tomorrow, I'll cover reverse polarity protection (using P-channel MOSFETs vs. Schottky diodes) and overcurrent protection with resettable PTC fuses and eFuses. We'll compare dropout voltage, cost, and reverse leakage for automotive and battery-powered designs.
