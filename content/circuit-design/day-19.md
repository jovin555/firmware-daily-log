---
title: "Day 19: Circuit Simulation: SPICE Basics & Model Selection"
date: 2026-07-30
tags: ["til", "circuit-design", "spice", "simulation"]
---

## What I Explored Today

Today I dug into SPICE simulation fundamentals—specifically how to set up a robust simulation environment and, more importantly, how to select the right device models. I’ve been guilty of grabbing the first MOSFET model I found online and hoping for the best. That approach fails in real engineering. I focused on understanding the difference between vendor-provided models, generic SPICE models, and behavioral models, and how each affects simulation accuracy versus speed. I also ran through a complete .DC sweep and .TRAN analysis on a simple common-source amplifier, verifying that the model parameters matched the datasheet’s typical curves.

## The Core Concept

SPICE is a numerical solver that approximates the behavior of electronic circuits using mathematical models of each component. The “why” behind model selection is straightforward: every model is a trade-off between accuracy, convergence, and simulation time.

- **Vendor models (e.g., from Infineon, TI, ON Semi)** are extracted from actual silicon measurements. They include parasitic capacitances, temperature coefficients, and process corners. Use these for final verification and worst-case analysis. They are slow but accurate.
- **Generic models (e.g., NMOS level 1, 2, or 3)** are simplified. They use basic equations (Shichman-Hodges for MOSFETs) and ignore many second-order effects like channel-length modulation, subthreshold conduction, and gate overlap capacitance. Use these for topology exploration and initial biasing.
- **Behavioral models (e.g., using ABM sources in PSpice)** are mathematical constructs that mimic a block’s I/O without modeling internal physics. Use these for system-level simulation where you care about transfer functions, not transistor-level details.

The key insight: never simulate a final design with a generic model. You will get optimistic results. Always cross-check with a vendor model that includes parasitics and temperature effects.

## Key Commands / Configuration / Code

Below is a complete SPICE netlist for a common-source amplifier using an N-channel MOSFET. I’m using the **2N7002** vendor model from ON Semiconductor. The netlist includes a .DC sweep to find the transfer curve and a .TRAN analysis to check small-signal gain.

```spice
* Common-Source Amplifier with 2N7002
* Vendor model: 2N7002 (ON Semiconductor)

.title CS_Amp_2N7002

* --- Model inclusion ---
* Place the vendor model file in the same directory
.lib 2N7002.lib

* --- Components ---
VDD 1 0 DC 5.0
VIN 2 0 DC 1.5 AC 0.1
* Input source: 1.5V DC bias + 100mV AC for gain measurement

R1 1 3 10k   * Drain resistor
R2 2 0 1M    * Gate pulldown (bias stability)

M1 3 2 0 0 2N7002  * Drain Gate Source Bulk Model

* --- Analysis commands ---
.DC VIN 0 5 0.01      * Sweep input from 0 to 5V in 10mV steps
.TRAN 0.1u 10u        * Transient analysis: 100ns steps, 10us total
.AC DEC 100 1 10MEG   * AC analysis: 100 points/decade, 1Hz to 10MHz

* --- Output commands ---
.PRINT DC V(3) V(2)   * Print DC drain voltage and gate voltage
.PLOT DC V(3)         * Plot drain voltage vs input sweep
.PROBE                 * Enable graphical output (for most SPICE variants)

.END
```

**Inline comments explanation:**
- The `.lib` statement loads the vendor model. Without it, SPICE uses a default NMOS model (often level 1) which will give wildly different results.
- The `.DC` sweep from 0 to 5V lets you see the entire transfer curve. You can identify the linear region, saturation region, and the threshold voltage.
- The `.TRAN` analysis with a small AC signal on VIN lets you measure gain by looking at V(3) ripple amplitude.
- The `.AC` analysis gives frequency response directly.

**Model selection in action:** If I replace the `.lib` with a generic model like `.MODEL NMOS1 NMOS (VTO=2 KP=100u)`, the simulated gain might be 20% higher and the bandwidth 50% wider than reality. Always verify with the vendor model.

## Common Pitfalls & Gotchas

1. **Missing or incorrect model file path.** SPICE will silently fall back to a default model if it cannot find the `.lib` file. Always check the simulation log for “Model not found” warnings. I once spent two hours debugging a circuit that worked perfectly in simulation but failed on the bench—turns out the model wasn’t loaded and SPICE used a generic MOSFET with a different threshold voltage.

2. **Ignoring convergence issues from model complexity.** Vendor models often have hundreds of parameters. If your circuit has tight feedback loops or very small time constants (e.g., fast switching), SPICE may fail to converge. Solutions: add `.OPTIONS RELTOL=1m ABSTOL=1p` to loosen tolerances, or use `.IC` (initial conditions) to set node voltages close to the expected operating point.

3. **Using a model from a different process node.** A 5V-rated MOSFET model (like 2N7002) has different gate oxide thickness and channel length than a 20V-rated part. If you simulate a 12V circuit with a 5V model, the model may not break down in simulation (SPICE doesn’t model oxide breakdown), but the real part will fail. Always match the model’s maximum ratings to your circuit’s voltage levels.

## Try It Yourself

1. **Compare generic vs. vendor model.** Run the netlist above with the 2N7002 vendor model. Then replace `.lib 2N7002.lib` with a generic NMOS model: `.MODEL M1 NMOS (VTO=2.0 KP=100u)`. Compare the DC transfer curves. What is the difference in Vgs(th) and drain current at Vgs=3V?

2. **Add a load capacitor.** Insert a 10pF capacitor from drain (node 3) to ground. Rerun the .AC analysis. Measure the -3dB bandwidth. Then change the capacitor to 100pF. How does bandwidth scale? Does it match the expected RC time constant (R1 * C_load)?

3. **Temperature sweep.** Add a `.TEMP -40 25 85` line to the netlist. Rerun the .DC sweep. Plot the drain current at Vgs=3V for each temperature. Does the current increase or decrease with temperature? (Hint: think about threshold voltage temperature coefficient.)

## Next Up

Tomorrow, I’ll tackle **Thermal Design for Circuits: Derating & Heat Dissipation**—how to calculate junction temperature, select heatsinks, and apply derating curves to ensure your design survives worst-case conditions.
