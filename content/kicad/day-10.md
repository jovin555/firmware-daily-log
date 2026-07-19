---
title: "Day 10: Design Rules in KiCad: Netclasses, Clearances & Constraints"
date: 2026-07-19
tags: ["til", "kicad", "netclasses", "design-rules"]
---

## What I Explored Today

Today I dug into KiCad's design rules engine—specifically how netclasses, clearance matrices, and physical constraints interact in the PCB Editor. After fighting a few DRC violations on a mixed-signal board last week, I realized I'd been treating the Design Rules dialog as a set-it-and-forget-it form. That was a mistake. KiCad 8's constraint system is surprisingly expressive when you understand how the rule precedence works, and today I mapped out exactly how to configure netclasses for power, high-speed, and sensitive analog nets without driving yourself crazy with false positives.

## The Core Concept

Design rules in KiCad aren't just a list of minimums—they're a layered precedence system. At the bottom sits the global rule set (Board Setup > Design Rules > Constraints). Above that, netclasses override global values for groups of nets. At the top, individual net-specific rules (via the "Rules" tab) can override netclasses. The key insight: KiCad evaluates rules in order of specificity, not in the order you type them. A rule that matches a single net always beats a netclass rule, which always beats the global default.

The clearance matrix deserves special attention. Most engineers set a single global clearance (say 0.15mm) and call it done. But the matrix lets you define pairwise clearances between different netclasses. For example, you might want 0.5mm clearance between a 240VAC net and any low-voltage signal, while keeping 0.15mm between two digital signals. The matrix rows and columns correspond to netclasses, and the diagonal entries define intra-class clearance. Off-diagonal entries define inter-class clearance. If you leave a cell blank, KiCad falls back to the global clearance—which is often not what you want.

## Key Commands / Configuration / Code

**Accessing the Design Rules Editor:**
- Main menu: `File > Board Setup > Design Rules` (or `Preferences > Board Setup` on macOS)
- Keyboard shortcut: `Ctrl+Shift+D` (opens directly to Design Rules)

**Creating a Netclass:**
1. In the `Net Classes` tab, click the green `+` icon
2. Name it (e.g., `POWER_12V`, `DIFF_90R`, `ANALOG_SENSITIVE`)
3. Set clearance, via size, via drill, track width
4. Assign nets by clicking the `...` button next to "Assigned Netlist"

**Example netclass configuration for a mixed-signal board:**
```
Netclass: POWER_12V
  Clearance: 0.5mm
  Track Width: 0.8mm
  Via Size: 0.8mm
  Via Drill: 0.4mm

Netclass: ANALOG_SENSITIVE
  Clearance: 0.3mm
  Track Width: 0.25mm
  Via Size: 0.5mm
  Via Drill: 0.25mm
  (Enable "Allow gaps" if you want to route near other nets)

Netclass: DEFAULT (global)
  Clearance: 0.15mm
  Track Width: 0.25mm
  Via Size: 0.5mm
  Via Drill: 0.25mm
```

**Custom Rule Syntax (for net-specific overrides):**
```
(rule "High-voltage clearance"
  (condition "A.NetClass == 'POWER_12V' && B.NetClass == 'ANALOG_SENSITIVE'")
  (constraint clearance (min 1.0mm))
)
```
This rule forces 1.0mm clearance between any POWER_12V net and any ANALOG_SENSITIVE net, regardless of the matrix settings.

**Constraint Categories in Board Setup:**
- `Physical` — track width, via size, via drill, differential pair gap/width
- `Electrical` — clearance, hole-to-hole clearance, edge clearance
- `SMD` — solder mask sliver, paste mask margin, pad-to-pad clearance
- `Other` — silk-to-silk clearance, courtyard clearance, copper-to-edge

**DRC Toggle:**
- `Tools > Design Rules Checker` or `Ctrl+Alt+D`
- Check "Test all violations" vs "Test only selected" — use the latter when iterating on a specific netclass

## Common Pitfalls & Gotchas

**1. The clearance matrix is not symmetric by default.** If you set a clearance from `POWER_12V` to `ANALOG_SENSITIVE` to 0.5mm, but leave the `ANALOG_SENSITIVE` to `POWER_12V` cell blank, KiCad uses the global default for that direction. Always fill both sides of the matrix, or use a custom rule with symmetric condition logic (`A.NetClass == 'X' && B.NetClass == 'Y'` handles both directions because KiCad checks both orderings).

**2. Netclass assignment via schematic doesn't always propagate.** If you assign netclasses in the schematic editor (via the net label properties), you must re-annotate the PCB (`Tools > Update PCB from Schematic`). Even then, nets that were manually assigned in the PCB Editor may get overwritten. I now assign all netclasses in the PCB Editor's Design Rules dialog to avoid this confusion.

**3. Differential pair constraints are hidden in the netclass editor.** You set the differential pair width and gap in the netclass's `Diff Pair Width` and `Diff Pair Gap` fields, but the actual routing tool (`Route > Differential Pair`) also respects the `Diff Pair Tolerance` setting. If your diff pair looks wrong, check both the netclass and the routing tool's properties panel.

**4. The "Allow gaps" checkbox is per-netclass and can cause DRC silence.** If you enable "Allow gaps" on a netclass, KiCad will not flag open circuits on that netclass. This is useful for test points or jumper pads, but disastrous if you forget to disable it on a power net.

## Try It Yourself

**Task 1: Create a power netclass with 0.5mm clearance.** Assign your VCC and GND nets to it. Run DRC and verify that all power-to-signal violations are now flagged correctly. Then add a custom rule to force 1.0mm clearance between power and any net named "HV_SENSE".

**Task 2: Build a clearance matrix for three netclasses: POWER, DIGITAL, ANALOG.** Set DIGITAL-to-DIGITAL at 0.15mm, ANALOG-to-ANALOG at 0.2mm, POWER-to-anything at 0.5mm. Leave one cell blank intentionally, run DRC, and observe the fallback behavior.

**Task 3: Configure a differential pair netclass for 90-ohm impedance.** Set width to 0.2mm, gap to 0.15mm, tolerance to 10%. Route a short diff pair, then use `Tools > Design Rules Checker` with "Test diff pair coupling" enabled to verify your gap is within tolerance.

## Next Up

Tomorrow: **Copper Pours & Zone Priorities** — we'll cover how to create solid and hatched copper zones, set net priorities so GND pours don't short to VCC, and use thermal relief settings to avoid soldering nightmares.
