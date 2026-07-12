---
title: "Day 03: Controlled Impedance: Microstrip & Stripline Calculations"
date: 2026-07-12
tags: ["til", "high-speed-design", "impedance", "microstrip"]
---

## What I Explored Today

Today I dug into the practical math behind controlled impedance traces—specifically microstrip and stripline topologies. While many of us rely on the PCB fabricator to "just make it 50 Ω," understanding the underlying equations is critical when you're doing pre-layout stackup planning or troubleshooting impedance mismatches. I worked through the IPC-2141A approximations and validated them against field solvers, and I want to share the engineer's perspective: what matters, what doesn't, and where the approximations break.

## The Core Concept

Controlled impedance isn't magic—it's geometry and material properties. A trace becomes a transmission line when its length exceeds roughly one-tenth of the signal's rise-time edge length. At that point, the trace's inductance per unit length and capacitance per unit length form a distributed network with a characteristic impedance Z₀ = √(L/C).

For microstrip (trace on outer layer, one reference plane below), the fields are partly in air and partly in the dielectric. This mixed dielectric makes the effective permittivity (εᵣₑff) lower than the core material's Dk. For stripline (trace buried between two reference planes), the fields are fully contained in the dielectric, giving a cleaner, more predictable impedance—but at the cost of longer via stubs and reduced accessibility.

The key insight: **impedance is inversely proportional to trace width and directly proportional to dielectric height.** If you want 50 Ω, you're trading width against layer spacing. On a standard 4-layer board with 0.2 mm prepreg, a 50 Ω microstrip is roughly 0.35 mm wide. On the same stackup, a stripline might need 0.18 mm—half the width—because the fields are fully immersed in dielectric.

## Key Commands / Configuration / Code

Here's a Python snippet I use for quick pre-layout calculations. It implements the IPC-2141A microstrip and stripline approximations.

```python
import math

def microstrip_z0(w, h, t, er):
    """
    Microstrip characteristic impedance (IPC-2141A)
    w: trace width (mm)
    h: dielectric height to reference plane (mm)
    t: copper thickness (mm)
    er: relative permittivity (Dk)
    """
    # Effective dielectric constant
    ereff = (er + 1) / 2 + (er - 1) / 2 * (1 / math.sqrt(1 + 12 * h / w))
    # Impedance formula
    Z0 = (87 / math.sqrt(ereff + 1.41)) * math.log(5.98 * h / (0.8 * w + t))
    return Z0, ereff

def stripline_z0(w, h, t, er):
    """
    Symmetric stripline characteristic impedance (IPC-2141A)
    h: total dielectric height between planes (mm)
    w: trace width (mm)
    t: copper thickness (mm)
    er: relative permittivity
    """
    # Stripline formula (symmetric)
    Z0 = (60 / math.sqrt(er)) * math.log(4 * h / (0.67 * math.pi * w * (1 + t / (math.pi * w))))
    return Z0

# Example: 50 Ohm microstrip on FR4
# Typical 4-layer stackup: h=0.2mm, t=0.035mm (1oz), er=4.5
w_guess = 0.35  # mm
Z, ereff = microstrip_z0(w_guess, 0.2, 0.035, 4.5)
print(f"Microstrip: Z0={Z:.1f} Ohm, εreff={ereff:.2f}")

# Example: 50 Ohm stripline
# Same stackup, h=0.4mm (two prepreg layers), er=4.5
Z_strip = stripline_z0(0.18, 0.4, 0.035, 4.5)
print(f"Stripline: Z0={Z_strip:.1f} Ohm")
```

For quick field solving without a full 3D EM tool, I use **Saturn PCB Toolkit** (free) or **Polar Si8000** (industry standard). These handle edge-coupled differential pairs and asymmetric stripline, which the simple formulas don't.

## Common Pitfalls & Gotchas

1. **Etch factor and copper roughness kill your impedance.** The formulas assume a perfect rectangular trace. In reality, etching rounds the corners and undercuts the trace. For 1 oz copper, the actual trace width at the bottom is 10–15% narrower than the top. Always specify "after etch" width to your fabricator. Copper roughness also increases surface resistance and lowers the effective Dk at high frequencies—something the IPC formulas ignore entirely.

2. **Prepreg vs. core Dk is not the same.** Many engineers use a single Dk value for the whole stackup. Wrong. Core materials (e.g., 2116, 7628) have a different resin-to-glass ratio than prepreg. The effective Dk of a prepreg layer can be 0.3–0.5 lower than the core. If you're doing microstrip on a prepreg layer, use the prepreg Dk, not the core Dk.

3. **Stripline impedance tolerance is tighter—but only if you control the layer spacing.** Stripline is less sensitive to solder mask (which can drop microstrip impedance by 2–4 Ω), but it's highly sensitive to the total dielectric height. A ±10% variation in prepreg thickness translates to ±10% in impedance. Always request "impedance control" with a target tolerance (typically ±10%, but ±5% is achievable with tighter process control).

## Try It Yourself

1. **Calculate your own stackup.** Grab a 4-layer board design and measure the prepreg thickness from the stackup document. Use the microstrip formula above to compute the trace width for 50 Ω and 75 Ω. Compare with your fabricator's recommended widths.

2. **Simulate the solder mask effect.** Modify the microstrip code to include a solder mask layer (εr ≈ 3.5, thickness ≈ 0.025 mm). Use a weighted average for εᵣₑff and see how much the impedance drops. You'll be surprised—often 2–4 Ω.

3. **Validate with a field solver.** Download Saturn PCB Toolkit or use the free online Polar Si8000 calculator. Enter your stackup from task 1 and compare the results to the IPC formula. Note the difference for narrow traces (w < 0.15 mm) where the approximations are weakest.

## Next Up

Tomorrow, we'll move from impedance control to termination strategies. I'll cover series termination (source-side), parallel termination (load-side), and AC termination (RC networks)—when to use each, how to calculate the resistor values, and the gotchas that cause reflections even with "correct" termination. We'll also touch on the reflection coefficient and why a 50 Ω driver into a 50 Ω trace can still ring if you forget the receiver's input capacitance.

**Day 04: Reflections & Termination Strategies: Series, Parallel & AC Termination**
