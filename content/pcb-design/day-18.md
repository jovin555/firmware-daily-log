---
title: "Day 18: Full Review & Project: Layout a 4-Layer Sensor Board from Schematic to Fab"
date: 2026-07-29
tags: ["til", "pcb-design", "review", "project"]
---

## What I Explored Today

Today I ran a complete end-to-end layout of a 4-layer sensor board — from a validated schematic through stackup definition, component placement, routing, and final Gerber generation. The board is a simple I2C temperature/humidity sensor (SHT30) with an STM32G030 microcontroller, a 3.3V LDO, and a USB-C connector for power and data. The goal wasn't novelty; it was to cement the full workflow and catch any gaps in my process before moving to more complex designs. I used KiCad 8.0 for this run, but the principles are tool-agnostic.

## The Core Concept

A 4-layer board isn't just a 2-layer board with extra copper. The inner layers fundamentally change your design strategy. Layer 2 becomes a solid ground plane (GND), and Layer 3 becomes a power plane (e.g., 3.3V). This gives you a controlled impedance environment for critical traces, dramatically reduces loop inductance for high-speed signals, and provides natural shielding. The key insight: you don't route on inner layers unless absolutely necessary. Keep signal routing on the top and bottom layers; use the planes for return current paths and power distribution.

For a sensor board, the analog signals from the sensor (I2C SDA/SCL) are low-speed, but the USB 2.0 differential pair (D+/D-) requires 90Ω differential impedance. Without a proper 4-layer stackup, you'd need wide traces and a specific distance to a reference plane — which is exactly what we get with Layer 2 as GND.

## Key Commands / Configuration / Code

### 1. Stackup Definition (KiCad PCB Editor → Board Setup → Stackup)

```
Layer 1 (Top): 1 oz copper, signal
Prepreg: 0.2mm (8 mil) FR4, εr = 4.5
Layer 2 (GND): 1 oz copper, plane (solid)
Core: 1.2mm (47 mil) FR4
Layer 3 (PWR): 1 oz copper, plane (split if needed)
Prepreg: 0.2mm (8 mil) FR4
Layer 4 (Bottom): 1 oz copper, signal
```

For USB differential pair, the trace width for 90Ω (edge-coupled microstrip) on Layer 1 over Layer 2:
- Trace width: 0.35mm (14 mil)
- Trace gap: 0.15mm (6 mil)
- Distance to plane: 0.2mm (8 mil)

### 2. Net Class Setup (KiCad → Board Setup → Net Classes)

```
Net Class: DEFAULT
  Clearance: 0.15mm
  Track Width: 0.25mm
  Via Size: 0.5mm / 0.3mm (annular ring)

Net Class: POWER
  Clearance: 0.2mm
  Track Width: 0.5mm
  Via Size: 0.6mm / 0.35mm

Net Class: USB
  Clearance: 0.15mm
  Track Width: 0.35mm
  Differential Pair Gap: 0.15mm
```

### 3. Placement Strategy (pseudocode)

```python
# Placement order for a mixed-signal board
1. Place connector (USB-C) near board edge for mechanical stability
2. Place LDO and decoupling caps within 5mm of connector
   - Keep input cap (10µF) between USB 5V and LDO input
   - Keep output cap (1µF) between LDO output and GND via
3. Place STM32G030 near LDO, orient for shortest power trace
4. Place SHT30 sensor at least 10mm away from any high-current path
   - Avoid placing near USB connector or LDO (heat + noise)
5. Place pull-up resistors (4.7kΩ) for I2C lines within 5mm of sensor
6. Add a 0.1µF bypass cap per IC, within 2mm of each power pin
```

### 4. Routing Commands (KiCad hotkeys)

```
'X' : Start routing
'V' : Add via (while routing)
'D' : Toggle differential pair routing mode
'B' : Fill zone (after routing, assign net to GND/PWR)
```

### 5. Gerber Generation (File → Plot)

```
Layers to plot:
  F.Cu, B.Cu, F.Paste, B.Paste, F.SilkS, B.SilkS, F.Mask, B.Mask
  Edge.Cuts (always include)
  In1.Cu (GND), In2.Cu (PWR)

Drill files:
  Generate NPTH and PTH drill files separately
  Use Excellon format, metric units
```

## Common Pitfalls & Gotchas

### 1. Forgetting to assign net classes before routing
If you route with default 0.25mm traces and then try to change the USB pair to 0.35mm, you'll have to re-route everything. Always define net classes in the schematic or at the very start of layout. I wasted 20 minutes fixing this today.

### 2. Placing vias under the SHT30 sensor
The SHT30 has a small exposed pad on the bottom for thermal and GND connection. If you place vias directly under the sensor footprint, they can short to the pad or cause soldering issues. Always check the datasheet's recommended land pattern — some sensors require a thermal via array, but not under the pad itself.

### 3. Not splitting the power plane for analog vs digital
On a 4-layer board, Layer 3 is often a single 3.3V plane. But if you have an analog sensor and a digital MCU sharing the same plane, digital switching noise couples into the sensor supply. The fix: split the plane into an analog region (under the sensor) and a digital region (under the MCU), connected by a ferrite bead or a 0Ω resistor. I used a 100Ω @ 100MHz ferrite bead (e.g., BLM18PG101SN1) between the two plane islands.

## Try It Yourself

1. **Stackup calculation**: Take a 4-layer board with 0.2mm prepreg and 1.2mm core. Calculate the trace width for 50Ω single-ended impedance on the top layer. Use the microstrip formula: Z0 = (87 / sqrt(εr+1.41)) * ln(5.98h / (0.8w + t)), where h = dielectric height, w = trace width, t = copper thickness. Verify with an online calculator.

2. **Placement challenge**: Open any existing 2-layer design (or a simple Arduino shield). Manually move all components to fit a 4-layer stackup: put all decoupling caps within 2mm of IC power pins, move the sensor away from the power regulator, and add a ground plane pour on Layer 2. Don't route — just place and add vias.

3. **Gerber review**: Generate Gerber files for your 4-layer board. Open them in a free Gerber viewer (e.g., Gerbv or KiCad's built-in viewer). Check that the GND plane (In1.Cu) has no isolated copper islands (orphans) — if it does, add stitching vias to connect them to the top/bottom ground pours.

## Next Up: Full Review

Tomorrow is the final review of the PCB Design Fundamentals series. I'll walk through a complete checklist for sending a board to fabrication: DRC sign-off, netlist verification, impedance validation, and a bill-of-materials sanity check. We'll also cover what to do when your fab house asks for "impedance coupons" — and why you should always say yes.
