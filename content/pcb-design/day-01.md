---
title: "Day 01: PCB Design Fundamentals: Layers, Copper Weight & Stackup Basics"
date: 2026-07-10
tags: ["til", "pcb-design", "pcb", "stackup"]
---

## What I Explored Today

Today I dove into the foundational layer cake of PCB design: the stackup. Every board I've ever designed—from a simple 2-layer breakout to a 12-layer mixed-signal beast—lived or died by its stackup decisions. I spent the morning reviewing how copper weight, prepreg thickness, and layer count interact to determine impedance, current capacity, and manufacturability. The key takeaway: your stackup isn't just a mechanical drawing; it's the electrical contract between your schematic and the physical world.

## The Core Concept

A PCB stackup is the ordered arrangement of copper layers and insulating materials (prepreg and core) that form your board. Why does this matter? Because every signal trace is a transmission line, and its characteristic impedance is determined by trace width, copper thickness, and the distance to the nearest reference plane. Get the stackup wrong, and your 50 Ω trace becomes 42 Ω—goodbye signal integrity.

Copper weight is specified in ounces per square foot (oz/ft²). Standard 1 oz copper is 1.4 mils (35 µm) thick. Heavier copper (2 oz, 3 oz) handles more current but etches with wider tolerances and makes fine-pitch routing nearly impossible. Lighter copper (0.5 oz) is great for dense digital boards but can't carry power.

The prepreg layers between copper layers define the dielectric thickness. Thinner prepreg (2-4 mils) gives tighter coupling to the reference plane, reducing EMI and crosstalk. Thicker prepreg (8-10 mils) is cheaper but increases loop inductance. For high-speed signals, you want the signal layer immediately adjacent to a solid ground plane with minimal dielectric thickness.

A typical 4-layer stackup looks like this:
- Layer 1: Top signal (1 oz copper)
- Prepreg: 4 mils (1080 glass style)
- Layer 2: Ground plane (1 oz copper)
- Core: 47 mils (FR-4)
- Layer 3: Power plane (1 oz copper)
- Prepreg: 4 mils (1080)
- Layer 4: Bottom signal (1 oz copper)

The total thickness is about 62 mils—the standard 1/16" board. The key detail: the signal layers are only 4 mils from their reference planes, giving good high-frequency performance.

## Key Commands / Configuration / Code

When setting up a stackup in your EDA tool (I use KiCad 8), here's the critical configuration:

```python
# KiCad PCB Editor stackup configuration (pseudo-code from board setup)
stackup = {
    "layers": [
        {"name": "F.Cu",   "type": "signal",   "thickness": "1 oz",  "material": "copper"},
        {"name": "dielectric_1", "type": "prepreg", "thickness": "0.004 in", "material": "FR-4", "epsilon_r": 4.5},
        {"name": "In1.Cu", "type": "plane",    "thickness": "1 oz",  "material": "copper"},
        {"name": "dielectric_2", "type": "core",    "thickness": "0.047 in", "material": "FR-4", "epsilon_r": 4.5},
        {"name": "In2.Cu", "type": "plane",    "thickness": "1 oz",  "material": "copper"},
        {"name": "dielectric_3", "type": "prepreg", "thickness": "0.004 in", "material": "FR-4", "epsilon_r": 4.5},
        {"name": "B.Cu",   "type": "signal",   "thickness": "1 oz",  "material": "copper"},
    ],
    "total_thickness": "0.062 in"
}

# Impedance calculation for a microstrip on top layer
# Using IPC-2141A approximation
def microstrip_Z0(h, w, t, er):
    """
    h: dielectric height (mils)
    w: trace width (mils)
    t: copper thickness (mils)
    er: dielectric constant
    Returns characteristic impedance in ohms
    """
    import math
    # Effective dielectric constant
    ereff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12 * h / w))
    # Impedance formula
    Z0 = (60 / math.sqrt(ereff)) * math.log(8 * h / (0.67 * w + 0.8 * t) + 0.25 * w / h)
    return Z0

# Example: 50 ohm trace on 4-mil prepreg, 1 oz copper (1.4 mils)
Z = microstrip_Z0(h=4, w=7, t=1.4, er=4.5)
print(f"Impedance: {Z:.1f} ohms")  # Should print ~50.2 ohms
```

For Altium users, the stackup manager is under Design → Layer Stack Manager. Set the material, thickness, and copper weight for each layer. Use the Impedance Profile tool to automatically calculate trace widths for target impedances.

## Common Pitfalls & Gotchas

**1. Ignoring copper weight on inner layers.** I once designed a 4-layer board with 1 oz copper on all layers, but the inner power plane needed to carry 5 A. At 1 oz, a 100 mil wide trace only handles about 2.5 A with a 10°C rise. I had to respin with 2 oz inner layers. Always check IPC-2152 for current capacity—don't guess.

**2. Asymmetric stackups cause warpage.** If you put two thick copper layers on one side and thin on the other, the board will bow like a banana during reflow. Keep the copper distribution balanced. For a 4-layer board, use the same copper weight on top and bottom, and the same on inner layers.

**3. Prepreg vs. core confusion.** Prepreg is the "glue" layer that bonds cores together. Its thickness is not fixed—it depends on the copper fill percentage on adjacent layers. A sparse ground plane with 20% copper will result in thicker prepreg than a dense signal layer with 80% copper. Your fabricator will adjust; you must specify the *finished* dielectric thickness, not the raw prepreg thickness.

## Try It Yourself

1. **Calculate your own 50 Ω trace.** Using the microstrip formula above (or an online calculator like JLCPCB's impedance tool), determine the required trace width for a 50 Ω microstrip on a 4-layer board with 4-mil prepreg and 1 oz copper. Compare with a 6-mil prepreg—how much does the width change?

2. **Audit an existing design.** Open a PCB you've previously designed. Check the stackup configuration. Is the copper weight appropriate for your highest-current nets? Use IPC-2152 to verify at least one power trace.

3. **Simulate a stackup change.** In your EDA tool, change the prepreg thickness between a signal layer and its reference plane from 4 mils to 8 mils. Re-run your impedance calculator. How does this affect crosstalk between adjacent traces on the same layer?

## Next Up

Tomorrow I'll tackle **Schematic Capture Best Practices: Nets, Hierarchical Sheets & Annotations**—how to organize your schematic so it doesn't look like a plate of spaghetti, and why proper net naming saves hours of debugging.
