---
title: "Day 04: PCB Stackup Design: 2-Layer to 8-Layer Boards"
date: 2026-07-13
tags: ["til", "pcb-design", "stackup", "layers"]
---

## What I Explored Today

Today I dove into the engineering decisions behind PCB stackup design, from the simplest 2-layer boards up to 8-layer high-speed designs. The stackup—the arrangement of copper layers, prepreg, and core materials—is the single most impactful decision you make for signal integrity, power distribution, and EMC performance. I focused on real-world layer assignments, dielectric material choices, and the impedance control math that separates a working prototype from a noisy, failing board.

## The Core Concept

A PCB stackup isn't just a list of layers; it's a controlled transmission line environment. Every signal trace is a microstrip or stripline, and its impedance is determined by the distance to the nearest reference plane (ground or power) and the dielectric constant (Dk) of the material between them.

**Why this matters:** A poorly planned stackup creates impedance discontinuities, crosstalk, and ground bounce. For digital signals with edge rates below 1 ns, even a 2-layer board needs careful return path planning. For 4-layer and above, you're building a planar capacitor between power and ground layers—this provides high-frequency decoupling that discrete capacitors can't match.

The golden rule: **Always place a solid reference plane adjacent to your signal layers.** For 2-layer boards, that means routing signals on one side and dedicating the other as a ground plane. For 4-layer, the classic stackup is Signal-Ground-Power-Signal, where the inner planes provide both reference and power distribution.

## Key Commands / Configuration / Code

### Impedance Calculation with Saturn PCB Toolkit (or similar)

When designing a stackup, you'll calculate trace width for a target impedance. Here's the math for a microstrip (outer layer) using the IPC-2141 approximation:

```
Z0 = (87 / sqrt(Er + 1.41)) * ln(5.98 * H / (0.8 * W + T))

Where:
  Z0 = characteristic impedance (Ohms)
  Er = dielectric constant (FR4 ~4.2-4.5)
  H  = height from signal to reference plane (mils)
  W  = trace width (mils)
  T  = copper thickness (mils, 1oz = 1.4 mils)
```

**Example for 50 Ohm microstrip on 4-layer board:**
- Core thickness: 10 mils (0.254 mm) between L1 and L2
- Er = 4.3
- Copper: 1 oz (1.4 mils)
- Solve for W: approximately 17.5 mils (0.445 mm)

### Stackup Definition in KiCad (Layer Stackup Manager)

```kicad
# 4-layer stackup example (KiCad PCB Editor → Setup → Board Stackup)
# Physical stack (top to bottom):
Layer 1 (F.Cu): Signal, 1 oz copper
  Prepreg: 7628 (7.4 mils, Er=4.5)
Layer 2 (GND): Ground plane, 1 oz copper
  Core: 2116 (4.5 mils, Er=4.5) + 7628 (7.4 mils, Er=4.5) = 11.9 mils total
Layer 3 (PWR): Power plane, 1 oz copper
  Prepreg: 7628 (7.4 mils, Er=4.5)
Layer 4 (B.Cu): Signal, 1 oz copper

# Total thickness: ~1.6 mm (standard 1/16 inch)
```

### 8-Layer High-Speed Stackup (DDR4/PCIe)

```
Layer 1: Signal (top, microstrip)
  Prepreg: 106 (2.0 mils, Er=3.9)
Layer 2: Ground (reference for L1)
  Core: 2116 (4.5 mils, Er=4.5)
Layer 3: Signal (stripline, inner)
  Prepreg: 1080 (2.5 mils, Er=4.0)
Layer 4: Ground (reference for L3 & L5)
  Core: 7628 (7.4 mils, Er=4.5)
Layer 5: Power (VCC plane)
  Prepreg: 1080 (2.5 mils, Er=4.0)
Layer 6: Signal (stripline, inner)
  Core: 2116 (4.5 mils, Er=4.5)
Layer 7: Ground (reference for L6 & L8)
  Prepreg: 106 (2.0 mils, Er=3.9)
Layer 8: Signal (bottom, microstrip)
```

**Key insight:** Layers 2 and 7 are dedicated ground planes. Layer 4 is a second ground plane. This gives every signal layer an adjacent reference. The power plane (L5) is sandwiched between two grounds, forming a low-inductance planar capacitor.

## Common Pitfalls & Gotchas

1. **Splitting reference planes under high-speed signals.** Never route a differential pair or clock line across a gap in the ground plane (e.g., where a split between analog and digital ground exists). The return current must detour, creating a large loop antenna. Always provide a continuous ground reference, or use a bridge capacitor if a split is unavoidable.

2. **Assuming all FR4 is the same.** The dielectric constant (Er) varies from 4.0 to 4.7 depending on resin content and weave style. For impedance-controlled designs, specify the exact prepreg and core materials to your fab house. A 10% variation in Er shifts impedance by ~5%, which can push you out of tolerance for high-speed interfaces.

3. **Ignoring copper weight vs. thickness.** 1 oz copper is 1.4 mils thick, but after plating and etching, outer layers end up thicker than inner layers. Your stackup must account for this asymmetry. Many designers use 0.5 oz (0.7 mils) for inner layers to save cost and reduce thickness variation.

4. **Stacking multiple signal layers without intermediate planes.** In a 6-layer board, a common mistake is Signal-Signal-Ground-Power-Signal-Signal. The two top signal layers have no reference plane between them, leading to massive crosstalk. Always interleave signal and plane layers.

## Try It Yourself

1. **Calculate trace width for 50 ohms.** Using the IPC-2141 formula (or Saturn PCB Toolkit), compute the required microstrip width for a 4-layer board with 8 mil dielectric height and 1 oz copper. Then repeat for 10 mil height. How much does width change?

2. **Design a 6-layer stackup.** Create a stackup that supports two high-speed signal layers (DDR4, 1.2V) and four general-purpose signal layers. Ensure every signal layer has an adjacent ground or power plane. Calculate the total board thickness (aim for 1.6 mm).

3. **Audit an existing board.** Open a 4-layer or 6-layer PCB design you've worked on. Check the stackup definition: Are there any signal layers without an adjacent reference plane? Is the power plane adjacent to ground? Measure the distance between a high-speed trace and its reference plane—is it consistent?

## Next Up

Tomorrow, we'll tackle **Ground Plane & Return Path Design**—how to ensure your signals have the shortest, lowest-inductance return path, why stitching vias are critical, and how to handle mixed-signal ground splits without destroying your EMC performance.
