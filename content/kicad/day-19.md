---
title: "Day 19: Simulation with ngspice Integration in KiCad"
date: 2026-07-30
tags: ["til", "kicad", "ngspice", "simulation"]
---

## What I Explored Today

Today I integrated ngspice with KiCad’s EEschema to run SPICE simulations directly from the schematic editor. I set up a common-emitter amplifier, assigned SPICE models to transistors, configured simulation directives, and ran both DC operating point and transient analyses. The goal was to validate circuit behavior before committing to layout—catching a gain error that would have been expensive to fix on a physical board.

## The Core Concept

KiCad’s simulation workflow treats the schematic as the single source of truth. Instead of exporting a netlist to a separate SPICE tool, you embed simulation directives (`.op`, `.tran`, `.ac`) as text annotations on the schematic. When you run the simulation, KiCad invokes ngspice in the background, parses the results, and plots waveforms in a built-in viewer. This tight integration means your simulation model is always in sync with the design—no more chasing discrepancies between a “simulation schematic” and the real board.

The key insight is that KiCad’s SPICE engine is not a toy. ngspice is a mature, open-source SPICE3f5 derivative that handles BJTs, MOSFETs, op-amps, and even behavioral sources. The limitation is not the engine but the model library: KiCad ships with only a handful of generic models. For real work, you must supply manufacturer SPICE models or create your own.

## Key Commands / Configuration / Code

### 1. Assigning SPICE Models to Components
In EEschema, right-click a component → **Properties** → **Edit Symbol Fields…** → add a field named `Sim_Model` with the path to the model file. For a 2N3904 NPN transistor, I placed the model file in the project directory:

```
Sim_Model = 2N3904.mod
```

The model file itself (e.g., `2N3904.mod`) contains the standard SPICE model:

```spice
.MODEL 2N3904 NPN (IS=6.734f BF=416.4 VAF=74.03
+ IKF=66.78m ISE=6.734f NE=1.259 BR=.7371
+ VAR=24.36 IKR=55.17m ISC=0 NC=2 RB=10
+ RC=1 CJC=3.638p MJC=.3085 VJC=.75
+ CJE=4.493p MJE=.2593 VJE=.75 TR=239.5n
+ TF=301.2p ITF=.4 VTF=4 XTF=2 RB=10)
```

### 2. Simulation Directives
Place a text label (press `T` in EEschema) and prefix it with `.sim`. KiCad treats any text starting with `.sim` as a simulation directive. For a DC operating point:

```
.sim .op
```

For a transient analysis with a 1 kHz sine wave input:

```
.sim .tran 10u 5m
```

To define the input stimulus, add a voltage source (symbol `VSIN`) and set its parameters via the **Value** field or a SPICE directive:

```
.sim V1 0 SIN(0 0.1 1k 0 0 0)
```

### 3. Probing Nodes
After simulation, you probe nodes by adding net labels (e.g., `Vout`, `Vin`) to the schematic. In the waveform viewer, click **Add Signals** and select the labeled nets. KiCad automatically maps net labels to SPICE node names.

### 4. Running the Simulation
From EEschema: **Inspect** → **Simulator**. The ngspice window opens. Click **Run** (or press `F8`). The waveform viewer appears with any `.plot` directives or you can manually add signals.

### 5. Full Example: Common-Emitter Amplifier
Schematic directives:

```
.sim .op
.sim .tran 10u 5m
.sim V1 N001 0 SIN(0 0.1 1k 0 0 0)
.sim R1 N001 N002 10k
.sim R2 N002 0 4.7k
.sim R3 Vcc N003 1k
.sim R4 N003 0 470
.sim Q1 N003 N002 0 0 2N3904
.sim Vcc Vcc 0 DC 12
```

Note: `N001`, `N002`, `N003` are net names from the schematic. KiCad assigns these automatically; you can rename them with net labels.

## Common Pitfalls & Gotchas

### 1. Missing Ground Reference
ngspice requires a node named `0` (zero) for ground. If your schematic lacks a ground symbol (the triangle with GND label), the simulation will fail with “Floating nodes” errors. Always place a **PWR_FLAG** on the ground net to satisfy the ERC, and ensure the ground symbol’s net is named `GND` (KiCad maps this to node 0).

### 2. Model Path Resolution
KiCad searches for model files relative to the project directory, not the schematic directory. If you keep models in a subfolder (e.g., `models/2N3904.mod`), the `Sim_Model` field must be `models/2N3904.mod`. Relative paths are preferred; absolute paths break when sharing the project.

### 3. Convergence Failures with Default Solver
ngspice defaults to the `direct` solver, which can choke on circuits with high gain or feedback loops. If you see “Timestep too small” or “No convergence”, switch to the `gmres` solver by adding this directive:

```
.sim .options method=gmres
```

Also increase the iteration limit:

```
.sim .options itl1=500 itl2=500
```

## Try It Yourself

1. **DC Sweep of a Voltage Divider**: Create a resistive divider (R1=10k, R2=4.7k) with a DC voltage source. Add a `.sim .dc V1 0 12 0.1` directive. Run the simulation and verify that Vout = Vin * R2/(R1+R2). Plot both Vin and Vout.

2. **Transient Response of an RC Low-Pass Filter**: Place a 1k resistor and 1µF capacitor in series. Drive with a 1V, 1kHz square wave (use `VPULSE` symbol). Run `.tran 10u 5m`. Measure the 63% rise time and compare to τ = RC = 1ms.

3. **Common-Emitter Amplifier Gain Check**: Build the amplifier from the example above. Run `.op` to get the DC bias point (Vce should be ~6V for a 12V supply). Then run `.tran` and measure the AC gain (Vout_peak / Vin_peak). Expect ~50-100 for a 2N3904 with those resistor values.

## Next Up

Day 20: **Full Review & Project: Design a Complete Board in KiCad from Schematic to Gerbers** — I’ll walk through the entire flow for a simple LED flasher: schematic capture, SPICE simulation to verify timing, PCB layout, DRC, and Gerber export. This is the capstone exercise that ties together everything from the past 19 days.
