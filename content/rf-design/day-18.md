---
title: "Day 18: Full Review & Project: Design & Match an Antenna Front-End for a BLE Module"
date: 2026-07-29
tags: ["til", "rf-design", "review", "project"]
---

## What I Explored Today

Today we cap the first three weeks of this series with a full-stack review project: designing and matching a complete antenna front-end for a Bluetooth Low Energy (BLE) module operating at 2.44 GHz. Instead of isolated theory, we walk through a real-world workflow—selecting an antenna, simulating a pi-network matching circuit, validating on a VNA, and verifying radiated performance. This ties together impedance matching, S-parameters, PCB layout parasitics, and regulatory constraints into one coherent design cycle.

## The Core Concept

A BLE module’s RF output is typically a single-ended 50 Ω port, but the antenna you choose (chip, PCB trace, or external) rarely presents exactly 50 Ω at 2.44 GHz. Even if the antenna datasheet claims 50 Ω, the PCB ground plane, nearby components, and enclosure shift its impedance. The front-end matching network’s job is to transform the antenna’s actual impedance to 50 Ω, minimizing return loss and maximizing radiated power. Without proper matching, you lose link budget, fail FCC radiated emissions tests, and drain battery faster due to reflected power heating the PA.

The key insight: **matching is not a one-time calculation; it’s an iterative process** that must account for parasitic capacitance from solder pads, via inductance, and the module’s output impedance (which may not be exactly 50 Ω at the pin). Today’s project forces you to confront these real-world variables.

## Key Commands / Configuration / Code

We’ll use a typical BLE module (e.g., Nordic nRF52840) with a Johanson 2450AT18x100 chip antenna. The antenna’s datasheet specifies a 50 Ω impedance at 2.45 GHz, but on a 2-layer board with a 0.8 mm FR4 stackup, expect 40–60 Ω with a small inductive shift.

### Step 1: Measure Antenna Impedance with VNA

Calibrate VNA at the module’s RF output pin (use SMA edge-launch connector on a test board). Measure S11 of the antenna alone:

```
# VNA sweep: 2.4–2.48 GHz, 801 points
# Marker at 2.44 GHz: Z = 45.3 + j12.8 Ω
# This corresponds to Γ = 0.18 ∠ 45° (VSWR ≈ 1.44)
```

### Step 2: Design Pi-Network Matching in ADS or Qucs

Target: transform 45.3 + j12.8 Ω to 50 Ω. Use a low-pass pi-network (C1-L-C2) to also suppress harmonics.

```
# Qucs schematic (netlist excerpt)
# Port P1 (50 Ω) -> C1 (1.2 pF) -> L1 (2.7 nH) -> C2 (0.8 pF) -> Antenna Z
# Simulated S11 at 2.44 GHz: -28 dB
# Insertion loss: 0.15 dB
```

Component values from Smith chart solution:
- C1 = 1.2 pF (0402, COG/NP0)
- L1 = 2.7 nH (0402, multilayer ceramic)
- C2 = 0.8 pF (0402, COG/NP0)

### Step 3: Account for PCB Parasitics

Add 0.3 nH series inductance per via (two vias to ground for C1, C2) and 0.2 pF pad capacitance per component. Re-simulate:

```
# Updated netlist with parasitics
# C1_eff = 1.2 pF - 0.2 pF = 1.0 pF (pad capacitance subtracts)
# L1_eff = 2.7 nH + 0.3 nH = 3.0 nH (via inductance adds)
# C2_eff = 0.8 pF - 0.2 pF = 0.6 pF
# Re-simulated S11 at 2.44 GHz: -22 dB (still acceptable)
```

### Step 4: Layout and Tune

Place components in a straight line from module pin to antenna feed. Keep ground vias for shunt capacitors within 1 mm of the pad. Use a 50 Ω microstrip trace (width = 1.5 mm on 0.8 mm FR4, εr=4.5).

After assembly, measure S11 again. Expect shift due to solder fillet and enclosure. Tweak C1 and C2 in 0.1 pF steps.

### Step 5: Verify Radiated Power

Use a spectrum analyzer with a near-field probe or reference antenna. Transmit BLE advertising packets at 0 dBm. Measure peak power at 2.44 GHz:

```
# Expected: -2 to +1 dBm (cable loss + antenna efficiency)
# If < -5 dBm, recheck matching and ground plane
```

## Common Pitfalls & Gotchas

1. **Ignoring the module’s output impedance.** Many BLE modules have an internal balun or PA that is not exactly 50 Ω. Check the datasheet’s recommended matching network—some nRF52840 reference designs use a 1.5 nH shunt inductor at the output pin. If you match to 50 Ω but the module expects a different impedance, you’ll see degraded performance.

2. **Parasitic resonance from ground vias.** Shunt capacitors to ground require low-inductance vias. A single 0.3 mm via has ~0.5 nH inductance, which at 2.44 GHz is 7.7 Ω of reactance—enough to shift your match by 10–15 Ω. Use at least two vias per shunt node, placed symmetrically.

3. **Antenna detuning from enclosure.** Plastic enclosures with metal inserts, batteries, or LCD cables within 5 mm of the antenna will shift its resonance. Always measure the antenna impedance *in the final enclosure* before finalizing component values. A 1 mm change in ground plane clearance can shift resonant frequency by 20–30 MHz.

## Try It Yourself

1. **Simulate a pi-network match** for an antenna that measures 35 – j25 Ω at 2.44 GHz. Use Qucs or ADS to find L and C values that achieve S11 < -20 dB. Include 0.3 nH via inductance per shunt component.

2. **Build a test board** with a BLE module and chip antenna. Leave footprints for a pi-network (three 0402 pads). Measure S11 with a VNA before populating components, then tune C1 and C2 to minimize S11 at 2.44 GHz. Document the final values.

3. **Compare radiated power** with and without the matching network. Use a spectrum analyzer with a near-field H-probe held 5 mm above the antenna. Note the dB difference at 2.44 GHz. If the matched version is >3 dB higher, your network is working.

## Next Up

Tomorrow: **Full Review – RF Design for Embedded Systems, Days 1–18.** We’ll consolidate every key concept, formula, and rule of thumb into a single reference cheat sheet. Expect a downloadable PDF with impedance matching tables, PCB layout guidelines, and regulatory compliance checklists.
