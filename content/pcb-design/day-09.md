---
title: "Day 09: Via Types: Through-Hole, Blind, Buried & Via-in-Pad"
date: 2026-07-18
tags: ["til", "pcb-design", "vias", "via-in-pad"]
---

## What I Explored Today

Today I dug into the four major via types used in modern PCB layout: through-hole, blind, buried, and via-in-pad. While through-hole vias are the default in every EDA tool, the real engineering decisions come when you need to route dense BGA packages, manage signal integrity at high frequencies, or shrink a design to fit a form factor. I spent the morning in Altium Designer and KiCad 8, comparing stackup definitions and via placement rules, and confirmed that choosing the wrong via type can blow your fabrication budget or kill your signal eye diagram.

## The Core Concept

A via is a plated hole that connects copper layers. The "why" behind choosing one type over another comes down to three constraints: **routing density**, **signal integrity**, and **fabrication cost**.

- **Through-hole vias** drill through every layer. They’re cheap ($0.01–$0.03 each in volume) but consume routing channels on all layers and create stubs that degrade high-speed signals above 1 GHz.
- **Blind vias** connect an outer layer to one or more inner layers, but stop before reaching the opposite side. They free up routing space on the backside and reduce stub length, but require sequential lamination—adding 20–30% to board cost per blind via layer pair.
- **Buried vias** connect only inner layers, invisible from the surface. They’re essential for HDI (High-Density Interconnect) designs with multiple power planes, but they require additional drilling and plating steps before lamination.
- **Via-in-pad** places a via directly inside a surface-mount pad. It’s the go-to for fine-pitch BGAs (0.5 mm or less) and thermal management, but it must be filled and planarized (typically with conductive epoxy or copper plating) to prevent solder wicking and voids.

The key trade-off: every via type beyond through-hole adds fabrication steps. A standard 6-layer board with only through-holes costs ~$50 for 10 pieces. Add two blind via pairs and buried vias, and you’re looking at $200–$300. The engineer’s job is to use the minimum via complexity that meets the electrical and mechanical requirements.

## Key Commands / Configuration / Code

### Altium Designer — Via Type Definition in Layer Stack Manager

```
Design → Layer Stack Manager
  → Select a via type (e.g., "Through", "Blind & Buried")
  → Define start/stop layers for each via class
  → Set via diameter: 0.3 mm (drill) / 0.6 mm (pad) for standard
  → For via-in-pad: enable "Tented" or "Filled & Capped" in Via Properties
```

### KiCad 8 — Via Configuration in Board Setup

```python
# In pcbnew, via types are set per-net or per-via in the footprint editor
# For blind/buried vias, define the layer pair in the via properties dialog

# Example: Set a blind via from F.Cu to In1.Cu
via.SetLayerPair(F_Cu, In1_Cu)  # Python scripting in pcbnew
via.SetDrill(0.3)               # mm
via.SetWidth(0.6)               # mm
```

### IPC-4761 Via Protection Types (for via-in-pad)

| Type | Description | Use Case |
|------|-------------|----------|
| Type I | Tented (solder mask over both sides) | Low-cost, no-fill needed |
| Type IV | Filled & Capped (non-conductive fill + copper cap) | Via-in-pad for BGAs |
| Type VII | Conductive fill (copper or silver epoxy) | High-current or thermal vias |

### Fabrication Note Example (for your README or fab drawing)

```
FABRICATION NOTES:
- All vias: IPC-4761 Type IV fill & cap for BGA pads (0.5 mm pitch)
- Blind vias: L1-L2 and L5-L6 only. No buried vias.
- Minimum via drill: 0.2 mm for blind, 0.3 mm for through-hole.
- Via-in-pad: Conductive epoxy fill, copper cap, planarized to ±0.05 mm.
```

## Common Pitfalls & Gotchas

1. **Via stub resonance kills high-speed signals.** A through-hole via on a 10-layer board with a signal on L2 creates a stub from L2 to L10. At 5 GHz, that stub acts as a quarter-wave resonator. Always back-drill or use blind vias for signals above 3 GHz. In Altium, you can set back-drill depth in the Layer Stack Manager.

2. **Via-in-pad without fill causes tombstoning and voids.** If you place a via inside a 0402 pad without filling it, solder wicks down the via hole during reflow. The component lifts on one side (tombstoning) or you get a voided joint. Always specify filled and capped vias for any pad smaller than 0.5 mm pitch. In KiCad, you can set `via_type` to `Filled` in the footprint properties.

3. **Blind vias require sequential lamination—plan your stackup early.** You cannot add a blind via from L1 to L3 on a standard 6-layer board without splitting the lamination into two press cycles. This increases lead time by 5–7 days. If your prototype house doesn’t support sequential lamination, you’re stuck with through-holes or microvias (laser-drilled, ≤0.15 mm). Always check your fabricator’s capabilities before finalizing the stackup.

## Try It Yourself

1. **Open your current design and identify every via type.** Count how many are through-hole, blind, or buried. If you have a BGA, check whether any vias are inside pads. Write down the fabrication cost impact if you converted all through-holes to blind vias on the top two layers.

2. **In your EDA tool, create a 4-layer stackup with one blind via pair (L1-L2) and one buried via pair (L2-L3).** Route a single net from L1 to L3 using the blind via to L2, then the buried via to L3. Verify the via drill sizes are compatible with your fabricator’s minimum (typically 0.2 mm for laser-drilled microvias).

3. **Simulate via stub effect.** Use a free tool like Saturn PCB Toolkit or HyperLynx to calculate the resonant frequency of a 0.3 mm drill through-hole via on a 1.6 mm board. If your signal is 2.5 GHz, what stub length causes a 10 dB insertion loss? Adjust the via type to blind (L1-L2 only) and re-run the calculation.

## Next Up

Tomorrow: **Panelization & Fabrication Panel Design** — how to arrange multiple PCBs on a panel for cost-effective manufacturing, including mouse bites, V-scoring, and fiducial placement. We’ll also cover the math behind panel utilization and why a 95% panel fill rate can save you 30% per board.
