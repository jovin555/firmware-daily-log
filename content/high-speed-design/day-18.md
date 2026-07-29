---
title: "Day 18: Full Review & Project: Route a DDR4 Fly-by Topology with Length Matching"
date: 2026-07-29
tags: ["til", "high-speed-design", "review", "project"]
---

## What I Explored Today

Today I pulled together everything from the past two weeks into a single, focused project: routing a complete DDR4 fly-by topology with length matching. Instead of isolated concepts, I walked through a real board layout scenario—4 x DDR4 components on a single rank, using fly-by for address/command/control and point-to-point for data. I verified timing budgets, set up constraint regions, routed the fly-by chain, and matched lengths across all byte lanes. This is the kind of task that separates simulation from production-ready layout.

## The Core Concept

DDR4 fly-by topology exists for one reason: signal integrity at high data rates (1600–3200 MT/s). In a traditional T-branch, each stub creates a reflection point. At DDR4 speeds, those reflections cause non-monotonic edges and setup/hold violations. Fly-by daisy-chains the clock, address, command, and control signals from one DRAM to the next, terminating at the last device. Each DRAM sees a clean, single-load stub instead of a multi-drop mess.

The trade-off is timing. Because each DRAM receives the clock at a slightly different delay, the data strobe (DQS) must be de-skewed per byte lane. This is handled by the DDR4 controller's write leveling and read training—but only if your PCB lengths are within the controller's programmable range (typically ±10–50 ps). Your job as the layout engineer is to keep the fly-by chain's propagation delay variation small enough that training can succeed, while also matching each data group (DQ/DQS/DM) to its associated clock.

Length matching isn't about making everything the same length. It's about controlling skew within each timing group. For a DDR4-2400 design, the data group must be matched to within ±5 ps of the DQS, and the DQS must be matched to within ±10 ps of the CK (clock) at each DRAM. The fly-by chain itself has a per-device delay of about 10–20 ps, which the controller's DLL compensates for—but only if you don't exceed the maximum skew budget.

## Key Commands / Configuration / Code

Below is a real Altium Designer constraint setup for a 4-layer DDR4 layout (6-layer preferred, but we work with what we have). The same principles apply to Cadence Allegro or Mentor PADS.

**Constraint Class Setup (Altium – PCB Rules and Constraints Editor):**

```
Rule: Differential Pair Routing
  Net Class: DDR4_CLK
  Min Gap: 0.2mm
  Max Gap: 0.3mm
  Tolerance: ±0.05mm
  Phase Tolerance: 0.1mm

Rule: Matched Lengths – Data Groups
  Net Class: DDR4_DQ0..DQ7, DDR4_DQS0_P, DDR4_DQS0_N, DDR4_DM0
  Scope: Within same byte lane (e.g., BYTE0)
  Target: Relative to DQS0
  Tolerance: ±0.5mm (≈ ±3.3 ps on FR4, Er=4.2)

Rule: Matched Lengths – Address/Command/Control
  Net Class: DDR4_ADDR_CMD_CTRL
  Scope: All nets in fly-by chain
  Target: Longest net in chain
  Tolerance: ±2.0mm (≈ ±13 ps)

Rule: Via Count Restriction
  Net Class: DDR4_CLK, DDR4_DQS
  Max Vias: 2 per net
  Reason: Each via adds ~5–10 ps delay and impedance discontinuity
```

**Length Matching Script (Python, for post-layout verification):**

```python
# ddr4_length_check.py
# Reads CSV export from PCB layout tool (Altium, Allegro)
# Columns: NetName, Length_mm, Group, Target_Net

import csv

with open('layout_lengths.csv', 'r') as f:
    reader = csv.DictReader(f)
    nets = list(reader)

# Group by byte lane
groups = {}
for net in nets:
    group = net['Group']
    groups.setdefault(group, []).append(net)

# Check each group
for group, nets in groups.items():
    target_len = None
    for net in nets:
        if net['NetName'] == net['Target_Net']:
            target_len = float(net['Length_mm'])
            break
    if target_len is None:
        print(f"ERROR: No target net found in group {group}")
        continue
    for net in nets:
        delta = float(net['Length_mm']) - target_len
        if abs(delta) > 0.5:  # mm
            print(f"FAIL: {net['NetName']} delta {delta:.2f} mm (>{0.5} mm)")
        else:
            print(f"PASS: {net['NetName']} delta {delta:.2f} mm")
```

**Fly-by Routing Order (from controller to termination):**

```
Controller -> DRAM0 -> DRAM1 -> DRAM2 -> DRAM3 -> Termination Resistor (VTT)
```

Each DRAM's address/command/control pins connect directly to the trace with a short stub (max 1.5mm). The clock pair runs parallel to the fly-by chain, with each DRAM's clock input tapped via a series resistor (0–10Ω) placed within 5mm of the pin.

## Common Pitfalls & Gotchas

1. **Stub Length Creep** – It's tempting to route address lines straight to the DRAM pin, then continue the chain. But if your stub exceeds 2mm, the reflection delay becomes significant. I've seen boards fail DDR4-2400 training because a single address line had a 5mm stub. Keep stubs under 1.5mm, or use via-in-pad for the chain.

2. **Mismatched Reference Planes** – The fly-by chain must have a continuous ground reference. If you switch layers, the return current path changes, creating impedance bumps. Always route the entire chain on one layer (top or inner) with a solid ground plane directly below. If you must change layers, add stitching vias every 5mm around the transition.

3. **Ignoring Via Delay in Length Matching** – Your length matching rule only accounts for trace length, but each via adds 5–10 ps of delay. If one data line has two vias and another has none, you've introduced 10 ps of skew. Either enforce equal via counts per group, or add the via delay to your length target (typically +0.5mm per via on FR4).

## Try It Yourself

1. **Extract and Analyze** – Open your last DDR4 layout (or a reference design). Export the net lengths for one byte lane (DQ0–7, DQS0, DM0). Calculate the skew relative to DQS0. Is it within ±0.5mm? If not, identify the longest and shortest nets and plan a serpentine adjustment.

2. **Route a Fly-by Chain** – In your EDA tool, place four DDR4 footprints in a line. Route a single address line (e.g., A0) from the controller to DRAM0, then DRAM1, DRAM2, DRAM3, and finally to a termination resistor. Keep the trace width 0.1mm and spacing 0.15mm from adjacent nets. Measure the total length and per-device stub lengths.

3. **Simulate the Timing** – Use a free tool like HyperLynx LineSim or Altium's SI simulation. Inject a 1.2V, 800 MHz clock into your fly-by chain. Probe the clock at each DRAM input. Measure the skew between DRAM0 and DRAM3. If it exceeds 50 ps, adjust your trace lengths or add delay compensation.

## Next Up

Tomorrow is **Full Review** – I'll walk through a complete DDR4 layout from start to finish, including stackup planning, decoupling capacitor placement, and a checklist for your design review. Bring your red pen.
