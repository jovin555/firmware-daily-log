---
title: "Day 01: Circuit Design Fundamentals: Ohm's Law, KVL & KCL in Practice"
date: 2026-07-10
tags: ["til", "circuit-design", "ohms-law", "kvl-kcl"]
---

## What I Explored Today

Today I revisited the absolute bedrock of circuit design: Ohm's Law, Kirchhoff's Voltage Law (KVL), and Kirchhoff's Current Law (KCL). While these feel like second nature after years of work, I forced myself to go back to first principles and apply them rigorously to a real-world mixed-signal biasing network. The goal was to verify a transistor bias point by hand, then confirm with simulation — and catch any hidden assumptions that can bite you when moving from theory to PCB.

## The Core Concept

These three laws are not just academic; they are the constraint equations that define every DC operating point in a circuit. Ohm's Law (`V = IR`) gives the constitutive relationship for resistors. KVL says the sum of voltage drops around any closed loop is zero — this enforces energy conservation. KCL says the sum of currents entering a node equals the sum leaving — this enforces charge conservation.

The "why" matters: when you design a voltage divider for an ADC input, you're solving a KVL equation. When you size a pull-up resistor for an open-drain bus, you're applying Ohm's Law. When you calculate the base current in a BJT biasing network, you're using KCL at the base node. If you can't write these equations for your circuit, you don't understand its DC behavior.

A common trap: assuming ideal voltage sources can source infinite current. Real sources have output impedance. Another trap: forgetting that KVL loops must be traversed in a consistent direction, and that voltage polarity matters. I see junior engineers lose sign conventions constantly.

## Key Commands / Configuration / Code

I used a simple voltage divider with a transistor load to practice. Here's the circuit analysis and a quick LTSpice netlist to verify.

**Circuit:** A 10kΩ resistor (R1) from Vcc=5V to the collector of an NPN BJT (Q1, 2N2222). A 1kΩ emitter resistor (R2) to GND. Base biased via a 100kΩ resistor (R3) from Vcc. We want to find the DC collector voltage.

**Hand analysis (assuming β=200, Vbe=0.7V):**

1. **KCL at base node:** `(Vcc - Vb)/R3 = Ib`
2. **KVL base-emitter loop:** `Vb = Vbe + Ie * R2`
3. **KCL at collector node:** `Ic = β * Ib` (assuming active region)
4. **KVL collector-emitter loop:** `Vcc = Ic*R1 + Vce + Ie*R2`

Solving: `Ib = (5 - 0.7) / (100k + (201 * 1k)) ≈ 14.3µA` (using `Ie = (β+1)Ib`). Then `Ic ≈ 2.86mA`. `Vc = 5 - (2.86mA * 10k) = -23.6V` — clearly impossible, meaning the transistor is saturated. This is the kind of sanity check that saves a board spin.

**LTSpice netlist (save as `bias_check.asc`):**

```spice
* BJT Bias Check - Day 01
Vcc 1 0 DC 5
R1 1 2 10k
R2 3 0 1k
R3 1 4 100k
Q1 2 4 3 0 2N2222
.model 2N2222 NPN(Is=14.34f Xti=3 Eg=1.11 Vaf=74.03 Bf=200 Ne=1.5
+ Ise=34.72p Ikf=.2848 Xtb=1.5 Br=6.092 Nc=2 Isc=0 Ikr=0 Rc=1
+ Cjc=7.306p Mjc=.3416 Vjc=.75 Fc=.5 Cje=22.01p Mje=.377 Vje=.75
+ Tr=46.91n Tf=411.1p Itf=.6 Vtf=1.7 Xtf=3 Rb=10)
.op
.backanno
.end
```

Run with `ngspice -b bias_check.asc` or open in LTSpice. The `.op` analysis prints DC operating point. You'll see `V(2)` around 0.2V — confirming saturation.

**Python verification (using sympy for symbolic solve):**

```python
import sympy as sp

# Define variables
Vcc, R1, R2, R3, beta, Vbe = 5, 10e3, 1e3, 100e3, 200, 0.7
Ib, Ic, Ie, Vc, Vb, Ve = sp.symbols('Ib Ic Ie Vc Vb Ve')

# Equations
eq1 = sp.Eq(Vb, Vbe + Ve)                    # KVL base-emitter
eq2 = sp.Eq(Ve, Ie * R2)                     # Ohm's law on R2
eq3 = sp.Eq(Ib, (Vcc - Vb) / R3)             # KCL at base node
eq4 = sp.Eq(Ic, beta * Ib)                   # BJT relation
eq5 = sp.Eq(Ie, Ib + Ic)                     # KCL at emitter
eq6 = sp.Eq(Vc, Vcc - Ic * R1)               # KVL collector loop

sol = sp.solve([eq1, eq2, eq3, eq4, eq5, eq6],
               (Ib, Ic, Ie, Vc, Vb, Ve), dict=True)
print(sol)
# Output: [{Ib: 1.428e-5, Ic: 2.857e-3, Ie: 2.871e-3, Vc: -23.57, Vb: 3.57, Ve: 2.87}]
```

The negative Vc confirms saturation — our linear model broke down. In practice, you'd iterate with `Vce_sat ≈ 0.2V`.

## Common Pitfalls & Gotchas

1. **Sign convention in KVL:** When summing voltages around a loop, always pick a consistent direction (clockwise). A voltage drop across a resistor is `+IR` if you traverse from + to -, and `-IR` if from - to +. I've seen entire design reviews derailed by a sign error in a feedback loop analysis.

2. **Ignoring transistor saturation:** Hand calculations assuming active region can give absurd results (like negative supply voltages). Always check `Vce > Vce_sat` (typically 0.2V for silicon). If violated, re-solve with `Vce = Vce_sat` and recalculate currents.

3. **Neglecting source impedance:** A voltage divider driving an ADC input looks like a Thevenin equivalent. If the ADC's input impedance is comparable to the divider's output impedance, the voltage shifts. Always check: `Vout_loaded = Vth * R_load / (Rth + R_load)`.

## Try It Yourself

1. **Verify a voltage divider:** Design a divider to produce 3.3V from 5V using standard 1% resistors (E96 series). Calculate the output impedance. Then add a 10kΩ load and compute the loaded output voltage. Compare to your unloaded value.

2. **Saturation check:** Take the BJT circuit above but change R1 to 1kΩ. Recalculate by hand (assuming active region), then simulate. Does the transistor stay in active mode? What is the new collector voltage?

3. **KCL at a node:** Build a three-resistor network: R1=1k from 5V to node A, R2=2k from node A to GND, R3=3k from node A to 0V (yes, another GND). Write the KCL equation at node A. Solve for Va. Verify with a multimeter in simulation.

## Next Up

Tomorrow, we dive into **Op-Amp Circuits: Inverting, Non-Inverting & Buffer Configurations**. We'll derive the gain equations from first principles, discuss input/output impedance implications, and show how to avoid oscillation from capacitive loading. Bring your ideal op-amp assumptions — we're going to break them.
