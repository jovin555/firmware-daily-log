---
title: "Day 05: Switching Regulators: Buck, Boost & Buck-Boost Topologies"
date: 2026-07-14
tags: ["til", "circuit-design", "buck", "boost"]
---

## What I Explored Today

Today I dove into the three fundamental switching regulator topologies that form the backbone of modern power electronics: buck (step-down), boost (step-up), and buck-boost (inverting or non-inverting). While linear regulators are simple and quiet, they dissipate excess voltage as heat—unacceptable for battery-powered or high-efficiency designs. Switching regulators use an inductor and switching element to transfer energy in packets, achieving efficiencies of 85-95% across wide input/output voltage ranges. I focused on understanding the steady-state operation, component selection heuristics, and the critical distinction between continuous conduction mode (CCM) and discontinuous conduction mode (DCM).

## The Core Concept

The fundamental principle behind all switching regulators is *energy storage and transfer*. An inductor stores energy in its magnetic field when a switch closes, then releases that energy to the load when the switch opens. The ratio of on-time to total switching period—the duty cycle (D)—determines the output voltage relative to the input.

For a **buck converter** operating in CCM: Vout = Vin × D. Since D is always < 1, output is always lower than input.

For a **boost converter** in CCM: Vout = Vin / (1 - D). Since (1 - D) < 1, output is always higher.

For a **buck-boost converter** (inverting topology): Vout = -Vin × D / (1 - D). This gives you a negative output voltage, or if you use a four-switch topology, you can get positive output above or below the input.

Why does this matter? Because real loads aren't static. A microcontroller may need 3.3V from a 4.2V Li-ion battery (buck), but an OLED display might need 12V from that same battery (boost). A battery-powered sensor node might need a regulated 3.3V when the battery is 4.2V (buck) or 2.8V (boost) — that's where a buck-boost shines.

The inductor current ripple, output voltage ripple, and switching losses are the key design trade-offs. Larger inductors reduce ripple but increase size and cost. Higher switching frequencies shrink magnetics but increase switching losses.

## Key Commands / Configuration / Code

Below is a practical LTspice netlist for a buck converter design. This is what I simulate before touching a soldering iron.

```spice
* Buck Converter: 12V input to 3.3V output @ 1A
* Switching frequency: 500kHz

VIN 1 0 DC 12
L1 2 3 10uH Rser=0.05  ; Inductor with DCR
C1 3 0 22uF Rser=0.01  ; Output cap with ESR
RLOAD 3 0 3.3           ; 1A load (3.3V / 1A = 3.3 ohms)
D1 0 2 SS34             ; Schottky diode (Vf ~0.4V)
M1 2 4 1 0 NMOS W=10m L=0.18u ; Power MOSFET

* PWM generator at 500kHz, duty cycle for 3.3V out
* Vout = Vin * D - Vf_diode * (1-D)  (approximate)
* With Vf=0.4V, D ~ 0.3
Vpwm 4 0 PULSE(0 5 0 10n 10n 0.6u 2u)

* Diode model
.model D1 D(Is=1e-8 Rs=0.1 Cjo=100p)

* MOSFET model (simplified)
.model NMOS NMOS(Vto=2.0 Kp=50m)

.tran 0 200u 0 10n startup
.measure I_load AVG I(RLOAD) from=100u to=200u
.measure Vout AVG V(3) from=100u to=200u
.measure ripple PP V(3) from=100u to=200u
.backanno
.end
```

For a **boost converter**, the key change is topology and duty cycle calculation:

```spice
* Boost Converter: 3.3V input to 5V output @ 500mA
* For boost: Vout = Vin / (1-D)  (ideal, ignoring diode drop)
* D = 1 - (Vin / Vout) = 1 - (3.3/5) = 0.34

VIN 1 0 DC 3.3
L1 1 2 4.7uH Rser=0.03
D1 3 4 SS34               ; Diode from switch node to output
C1 4 0 10uF Rser=0.02
RLOAD 4 0 10               ; 500mA load
M1 2 5 0 0 NMOS W=10m L=0.18u

Vpwm 5 0 PULSE(0 5 0 10n 10n 0.68u 2u)  ; D=0.34
```

For a **buck-boost** (inverting), the output is negative relative to input ground:

```spice
* Inverting Buck-Boost: 5V input to -12V output @ 200mA
* Vout = -Vin * D / (1-D)  =>  D = Vout / (Vout - Vin) = 12/(12+5) = 0.706

VIN 1 0 DC 5
L1 2 3 22uH Rser=0.08
C1 3 0 47uF Rser=0.02    ; Note: output referenced to input ground
RLOAD 3 0 60              ; 200mA load
D1 0 2 SS34               ; Cathode to switch node, anode to ground
M1 2 4 1 0 NMOS W=10m L=0.18u

Vpwm 4 0 PULSE(0 5 0 10n 10n 1.412u 2u)  ; D=0.706
```

## Common Pitfalls & Gotchas

**1. Inductor saturation kills efficiency instantly.** When the inductor current exceeds its saturation rating, inductance plummets, current spikes uncontrolled, and the MOSFET or diode can fail. Always design for peak inductor current = I_load + (ΔI_L / 2), then add 20% margin. A saturated inductor looks like a short circuit.

**2. Loop stability is not optional.** Switching regulators are negative feedback systems. Without proper compensation (Type II or Type III error amplifiers), the output will oscillate at sub-harmonic frequencies or ring excessively during load transients. The output capacitor's ESR creates a zero that can either help or hurt stability—ceramic caps with very low ESR often require external series resistance or feed-forward compensation.

**3. Layout parasitics dominate at high frequencies.** A 500kHz switcher has harmonics well into the MHz range. A 1nH parasitic inductance in the power loop (input cap → MOSFET → inductor → output cap) creates a 6.28mV voltage spike per amp of switched current at 1MHz. Keep the high-current loop as tight as a figure-8 race track. Use a solid ground plane and place the input decoupling capacitor within 2mm of the MOSFET drain-source path.

## Try It Yourself

1. **Simulate a buck converter with a 5V input and 1.8V output at 2A.** Choose the inductor value so that the current ripple (ΔI_L) is 30% of the load current. Verify your duty cycle matches theory. Then, change the load to 0.2A and observe the transition from CCM to DCM—note the change in output voltage ripple.

2. **Design a boost converter from a single Li-ion cell (3.0-4.2V) to 5V at 1A.** Calculate the inductor value for 500kHz switching with 40% ripple. Add a 10µF input cap and 22µF output cap. Simulate the startup transient and measure the output overshoot. Adjust the soft-start time by adding a capacitor to the feedback pin (if using a controller IC).

3. **Build a non-inverting buck-boost topology in simulation** using four switches (two MOSFETs, two diodes, or a full H-bridge). Set Vin=3.3V, Vout=5V at 500mA. Compare the efficiency to a standard boost converter at the same operating point. Note the additional conduction losses from the extra switch.

## Next Up

Tomorrow, we dive into **Power Supply Design: Loop Stability & Compensation** — where we'll analyze the control-to-output transfer function, design Type II and Type III compensators, and measure phase margin using a network analyzer. Bring your Bode plots.
