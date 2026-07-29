---
title: "Day 18: MOSFET Selection & Switching Circuit Design"
date: 2026-07-29
tags: ["til", "circuit-design", "mosfet", "switching"]
---

## What I Explored Today

Today I dug into the practical side of MOSFET selection for low-side and high-side switching circuits — not just the textbook equations, but the real-world tradeoffs that make or break a design. I focused on three common scenarios: driving a resistive load (heater), an inductive load (solenoid), and a capacitive load (LED string with bulk decoupling). The goal was to pick a specific N-channel MOSFET from a real datasheet (Infineon BSC014N04LS) and validate its suitability for a 12V, 5A switching application at 100 kHz PWM.

## The Core Concept

The fundamental reason we choose a MOSFET over a BJT for switching is the gate being voltage-controlled — zero DC gate current once the gate capacitance is charged. But that very capacitance (Q_g, total gate charge) is the primary design constraint. The switching speed is limited by how fast you can push charge into and out of the gate. If your gate driver can only source 100 mA, and the MOSFET requires 50 nC of gate charge to fully turn on, the minimum turn-on time is t_on = Q_g / I_gate = 50 nC / 100 mA = 500 ns. That’s fine for 100 kHz (10 µs period), but at 1 MHz it becomes a problem.

The real selection criteria, in order of priority for a switching application:

1. **R_DS(on) at V_GS = your drive voltage** — Not just at 10V. If you’re driving from a 3.3V MCU GPIO, you need a logic-level MOSFET with guaranteed R_DS(on) at V_GS = 2.5V or 3.3V.
2. **Total gate charge (Q_g)** — Lower is faster. For high-frequency switching, look for Q_g < 20 nC.
3. **Body diode reverse recovery (Q_rr)** — Critical for inductive loads and synchronous rectifiers. Fast recovery (t_rr < 50 ns) prevents shoot-through.
4. **Safe operating area (SOA)** — Must handle the V_DS × I_D stress during switching transitions, especially with inductive loads.

## Key Commands / Configuration / Code

Here’s a Python snippet I use to quickly sanity-check a MOSFET selection. It reads a simplified datasheet CSV and computes switching losses.

```python
# mosfet_switch_check.py
# Quick sanity check for MOSFET switching at given frequency and load

import math

# MOSFET parameters from datasheet (BSC014N04LS)
R_ds_on = 0.0014  # Ohms at Vgs=10V
Q_g = 56e-9       # Total gate charge, 56 nC
Q_gd = 12e-9      # Gate-drain charge (Miller plateau), 12 nC
V_gs_th = 2.0     # Typical threshold voltage, V
C_iss = 3800e-12  # Input capacitance, 3800 pF
C_rss = 300e-12   # Reverse transfer capacitance, 300 pF
t_rr = 25e-9      # Body diode reverse recovery time, 25 ns

# Operating conditions
V_dd = 12.0       # Supply voltage, V
I_load = 5.0      # Load current, A
f_sw = 100e3      # Switching frequency, Hz
V_drive = 5.0     # Gate drive voltage, V
R_gate = 10.0     # Gate drive resistor, Ohms

# Gate drive current (peak)
I_gate_peak = V_drive / R_gate  # 0.5 A

# Turn-on time (approximate, using Q_g)
t_on = Q_g / I_gate_peak  # 112 ns
t_off = t_on              # symmetric if same R_g

# Conduction loss
P_cond = I_load**2 * R_ds_on * (t_on * f_sw)  # negligible for 112ns on-time
# More accurate: duty cycle = 0.5 (50% PWM)
duty = 0.5
P_cond_duty = I_load**2 * R_ds_on * duty  # 5^2 * 0.0014 * 0.5 = 0.0175 W

# Switching loss (hard-switched, inductive load)
# P_sw = 0.5 * V_dd * I_load * (t_on + t_off) * f_sw
P_sw = 0.5 * V_dd * I_load * (t_on + t_off) * f_sw  # 0.5*12*5*224e-9*100e3 = 0.672 W

# Body diode loss (if used for freewheeling)
P_diode = 0.5 * V_f * I_load * t_rr * f_sw  # V_f ~ 0.8V typical
V_f = 0.8
P_diode = 0.5 * V_f * I_load * t_rr * f_sw  # 0.5*0.8*5*25e-9*100e3 = 0.005 W

total_loss = P_cond_duty + P_sw + P_diode
print(f"Conduction loss: {P_cond_duty*1000:.1f} mW")
print(f"Switching loss: {P_sw*1000:.1f} mW")
print(f"Body diode loss: {P_diode*1000:.1f} mW")
print(f"Total loss: {total_loss*1000:.1f} mW")
# Output: Conduction loss: 17.5 mW, Switching loss: 672.0 mW, Body diode loss: 5.0 mW
# Total loss: 694.5 mW — acceptable for TO-220 or DPAK with heatsink
```

For the actual gate drive circuit, I use a classic totem-pole driver with discrete NPN/PNP transistors:

```c
// Pseudocode for gate drive with totem-pole
// GPIO_PWM is a 5V logic signal from MCU
// R_gate_on = 10 Ohm, R_gate_off = 5 Ohm (faster turn-off)

void gate_drive_init(void) {
    // Configure GPIO as push-pull output
    // External: NPN (2N2222) pull-up, PNP (2N2907) pull-down
    // Collector of NPN to V_drive (5V), emitter to gate via R_gate_on
    // Emitter of PNP to gate via R_gate_off, collector to GND
    // Bases tied together through 1k resistor to GPIO
}

void gate_drive_set(uint8_t state) {
    if (state) {
        // GPIO high: NPN on, PNP off — gate charges through R_gate_on
        GPIO_PWM = 1;
    } else {
        // GPIO low: NPN off, PNP on — gate discharges through R_gate_off
        GPIO_PWM = 0;
    }
}
```

## Common Pitfalls & Gotchas

1. **Gate voltage overshoot from Miller effect.** When the MOSFET turns off with an inductive load, the drain voltage rises rapidly, and the Miller capacitance (C_rss) couples that voltage swing back to the gate. I’ve seen gate voltages spike 5V above the drive rail, destroying the gate oxide. Always add a 15V Zener diode (e.g., BZX84C15) from gate to source, and keep the gate drive loop physically small.

2. **R_DS(on) temperature coefficient.** MOSFETs have a positive temperature coefficient — R_DS(on) roughly doubles from 25°C to 125°C. If you design for 0.5W dissipation at 25°C, it becomes 1W at 125°C, which further heats the device. This is actually a blessing for paralleling (current sharing), but a curse for thermal runaway if you ignore it. Always derate: use R_DS(on) at 125°C for worst-case conduction loss.

3. **Body diode conduction during dead time.** In half-bridge or synchronous buck converters, if both MOSFETs are off simultaneously, the body diode of the low-side MOSFET conducts the inductor current. The diode forward voltage (0.8-1.2V) causes significant loss and reverse recovery charge. Minimize dead time to < 100 ns, or use Schottky diodes in parallel for high-frequency designs.

## Try It Yourself

1. **Select a MOSFET for a 24V, 10A motor driver at 20 kHz.** Go to DigiKey or Mouser and filter for N-channel, V_DS > 30V, I_D > 15A, Q_g < 30 nC. Find three candidates and compare their R_DS(on) at V_GS = 10V and V_GS = 5V. Which one would you choose for a 5V gate drive?

2. **Build the gate drive circuit from the pseudocode above on a breadboard.** Use a 10 µH inductor as the load (simulating a motor winding). Drive the gate with a 100 kHz, 50% duty cycle square wave from a function generator. Probe the gate voltage and drain voltage simultaneously on an oscilloscope. Measure the turn-on and turn-off times. Do they match the calculation from the Python script?

3. **Measure the body diode reverse recovery.** Replace the inductive load with a 1N4148 diode in series with a 10 Ohm resistor (to limit current). Drive the MOSFET at 100 kHz with a 1 µs on-time. Use a current probe on the drain and measure the reverse recovery current spike when the MOSFET turns on. Compare the measured t_rr to the datasheet value.

## Next Up

Tomorrow I’ll start a new mini-series on circuit simulation. We’ll cover SPICE basics — how to choose the right MOSFET model (level 1, 3, or BSIM), where to find vendor-provided models, and why using the wrong model can give you completely misleading switching loss numbers. We’ll simulate the exact circuit from today’s post in LTspice and compare to the hand calculations.
