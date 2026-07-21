---
title: "Day 12: Design Rule Checks (DRC): Common PCB Layout Errors"
date: 2026-07-21
tags: ["til", "pcb-design", "drc", "layout-errors"]
---

## What I Explored Today

Today I dove deep into Design Rule Checks (DRC) — the automated verification step that catches physical and electrical violations before a PCB goes to fabrication. I ran DRC on a mixed-signal board I’ve been routing and was humbled by the sheer number of errors: clearance violations, unconnected nets, silkscreen overlaps, and even a few acid-trap angles. DRC isn’t just a checkbox; it’s the last line of defense between a prototype that works and a board that’s scrap. I spent the day learning how to configure, interpret, and fix the most common DRC flags that trip up even experienced layout engineers.

## The Core Concept

Design Rule Checks translate your electrical schematic constraints into geometric and physical rules that the layout must obey. The “why” is simple: a PCB is a manufactured object, and every fab house has limits on trace width, spacing, hole size, and copper-to-edge clearance. Violate these, and your board either won’t be manufacturable or will fail in the field (short circuits, signal integrity issues, or mechanical breakage).

But DRC is more than just a fab-rule pass/fail. It enforces electrical constraints like creepage distances for high-voltage nets, impedance-controlled trace geometries, and net class spacing rules (e.g., analog signals must stay 10 mils away from digital aggressors). The key insight: DRC rules should be set *before* you place a single component, not after routing is done. Every minute spent tuning rules upfront saves hours of rework later.

Modern EDA tools (Altium, KiCad, OrCAD) all implement DRC as a two-phase process: **batch DRC** (run on the entire board) and **online DRC** (real-time highlighting as you route). I rely on online DRC heavily — it’s like a spell-checker that underlines errors as you type.

## Key Commands / Configuration / Code

I’ll use KiCad 8.x for examples, since it’s open-source and widely used. The same concepts apply to commercial tools.

### 1. Setting Up a Basic DRC Rule File (KiCad)

KiCad stores DRC rules in a `*.drc` file (or inline in the PCB editor). Here’s a minimal but practical rule set for a 2-layer board with 6-mil clearance:

```kicad-drc
# Minimum clearance for all nets (default)
(rule "Default clearance"
    (constraint clearance (min 0.15mm))   # ~6 mils
    (condition "A"))
```

### 2. Net-Class Specific Rules (Analog vs Digital)

This is where DRC becomes powerful. Separate your nets into classes and assign tighter spacing for sensitive signals:

```kicad-drc
# Analog nets need 0.25mm clearance from everything
(rule "Analog clearance"
    (constraint clearance (min 0.25mm))
    (condition "A.netclass == 'Analog'"))

# High-voltage nets (>48V) need 0.5mm creepage
(rule "High voltage creepage"
    (constraint clearance (min 0.5mm))
    (condition "A.netclass == 'HV'"))
```

### 3. Running DRC from the Command Line (KiCad)

For CI/CD or batch verification, KiCad supports headless DRC:

```bash
# Run DRC on a PCB file, output report to JSON
kicad-cli pcb drc --output drc_report.json --format json my_board.kicad_pcb
```

### 4. Common DRC Error Codes and Fixes

| Error Code | Meaning | Typical Fix |
|------------|---------|-------------|
| `DRC_ERR_CLEARANCE` | Copper features too close | Increase trace spacing or move vias |
| `DRC_ERR_UNCONNECTED` | Net has no copper connection | Check schematic connectivity, add via or trace |
| `DRC_ERR_SILK_OVERLAP` | Silkscreen on pad or hole | Move text or disable silkscreen on pad layer |
| `DRC_ERR_ACID_TRAP` | Acute angle in copper (< 90°) | Reroute with 45° or 90° corners |
| `DRC_ERR_STARVED_THERMAL` | Thermal spoke too thin | Increase spoke width in pad properties |

## Common Pitfalls & Gotchas

### 1. **Ignoring “Ignore” Flags**
Many tools let you mark a violation as “exempt” (e.g., a deliberate clearance violation for a test point). The gotcha: these exemptions don’t survive a board revision. When you update the PCB, all exemptions reset, and you’ll miss the violation unless you re-review. Always document exemptions in a separate text file or schematic note.

### 2. **Minimum Annular Ring (MAR) Violations**
DRC often flags vias where the copper ring around the hole is too thin. The pitfall: the DRC engine uses the *finished hole size* (after plating), not the drill size. If you specify a 0.3mm drill but the fab drills at 0.35mm, your annular ring shrinks. Always set your DRC rule to use the *minimum annular ring* value from your fab’s capabilities (typically 0.05mm to 0.1mm).

### 3. **Silkscreen on Solder Mask Openings**
A classic rookie error: placing reference designators on top of exposed copper pads (e.g., for edge connectors or test points). The silkscreen ink will be removed during solder mask application, making the text disappear. DRC won’t catch this unless you explicitly enable “Silkscreen over pad” checks. Enable it, then move all text off pads.

## Try It Yourself

1. **Run a batch DRC on your current board.** Export the report as CSV or JSON. Categorize every error by type (clearance, unconnected, silkscreen). Fix the top 5 errors manually, then re-run DRC. Note how many errors were false positives (e.g., intentional test points) and how many were real layout bugs.

2. **Create a net-class rule for a high-speed differential pair.** Set a clearance of 0.2mm between the pair and 0.3mm to all other nets. Route a short differential pair (e.g., USB or LVDS) and verify DRC catches any spacing violations. Adjust the trace width to meet impedance targets (use a calculator like Saturn PCB Toolkit).

3. **Simulate a “starved thermal” error.** Place a large copper pour (e.g., GND) and connect a through-hole pad with a single thin thermal spoke (0.1mm wide). Run DRC — it should flag the spoke as too thin. Widen the spoke to 0.3mm and re-verify. This is a common issue in high-current power supplies.

## Next Up

Tomorrow, I’ll cover **PCB Fabrication Notes: Gerbers, Drill Files & Stackup Specs** — how to generate the exact files your fab house needs, what each Gerber layer means, and why a poorly written stackup spec can double your board cost.
