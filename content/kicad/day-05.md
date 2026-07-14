---
title: "Day 05: ERC (Electrical Rules Check): Catching Schematic Errors"
date: 2026-07-14
tags: ["til", "kicad", "erc"]
---

## What I Explored Today

Today I dove into KiCad's Electrical Rules Check (ERC) system—the schematic equivalent of a compiler catching type mismatches before runtime. After spending Day 4 wiring up a mixed-signal board with analog sensors, digital logic, and a switching regulator, I ran ERC and was humbled by 47 errors. Most were trivial (unconnected pins, missing power flags), but three revealed real design issues: a net name collision between an analog reference and a digital bus, and two output pins shorted together through a poorly thought-out mux connection. ERC saved me from a board respin.

## The Core Concept

ERC is not a connectivity checker—it's a **design rule auditor** that validates electrical intent. Where DRC (Design Rules Check) later checks physical spacing and copper clearances, ERC operates purely on the schematic's logical graph: nets, pins, power domains, and hierarchical interfaces.

The engine works by building a netlist from your schematic, then checking every pin-to-pin connection against a matrix of allowed electrical types. KiCad's default matrix defines which pin types (Input, Output, Tri-State, Passive, Power Input, Power Output, etc.) can legally connect. An output driving an output is flagged as a conflict—likely a wiring mistake. A floating input is a warning—potential noise susceptibility.

Why this matters: In a 100+ component schematic, you cannot visually verify every connection. ERC catches:
- Nets with multiple drivers (outputs shorted together)
- Unconnected power pins on ICs (silent failures)
- Missing pull-ups on open-drain buses (I²C, 1-Wire)
- Hierarchical label mismatches in multi-sheet designs
- Power domains that aren't properly flagged (e.g., 3.3V net missing a PWR_FLAG)

Treat ERC like a linter for your circuit—run it early, run it often.

## Key Commands / Configuration / Code

**Running ERC:**
```
In Eeschema: Inspect → Electrical Rules Checker (or hotkey: Alt+E, then E)
Click "Run ERC" button
```

**The ERC Matrix** (critical to understand):
```
Tools → Electrical Rules Check → "ERC Matrix" tab
```
This 10x10 grid defines severity for every pin-type pair. Defaults are sane, but I always modify:
- **Output → Output**: Error (default) — keep this. Two outputs shorted is a design error.
- **Passive → Passive**: No error (default) — correct for resistors/caps.
- **Power Output → Power Input**: No error (default) — correct for regulators feeding loads.

**Power Flags — the most common fix:**
```markdown
Place a PWR_FLAG symbol (from `power` library) on every power net that doesn't
have an explicit voltage source symbol. Without it, ERC complains:
"Input Power pin not driven by any Output Power pin"

Example: On a +3V3 net that comes from a connector (not a regulator symbol),
place PWR_FLAG on the net. This tells ERC: "I know this net has power, trust me."
```

**Custom ERC Exclusions:**
```markdown
Right-click an ERC error marker → "Exclude ERC warning/error"
Use sparingly! Only for intentional violations (e.g., a test point that's
deliberately floating). Always add a comment explaining why.
```

**Net Inspector for debugging:**
```
Tools → Net Inspector (or hotkey: Alt+3)
```
Shows every net, its connected pins, and their electrical types. Invaluable when ERC says "Pin connected to others but no driver" — you can see exactly which pins are on that net.

## Common Pitfalls & Gotchas

**1. The "No Driver" False Positive on Connectors**
You place a 2-pin header for an external sensor. ERC flags both pins as "Input Power pin not driven." Solution: Add PWR_FLAG symbols on the connector's power net. The flag tells ERC the power originates off-board. Without it, every connector-based design generates dozens of spurious errors.

**2. Hierarchical Sheet Port Mismatches**
In multi-sheet designs, a hierarchical label on Sheet A named `I2C_SCL` (type: Bidirectional) must match exactly on Sheet B. A typo (`I2C_SDL`) creates two separate nets—ERC won't catch this as a connection error, but it will flag the port type mismatch if you use different electrical types. Always run ERC after adding or renaming hierarchical labels.

**3. Ignoring Warnings About Unused Pins**
ERC's "unconnected pin" warning on a microcontroller's unused GPIO is safe to ignore—but only if you've explicitly left it floating. If you intended to connect it to a pull-up and forgot, that warning is a real bug. My rule: never exclude a warning until I've verified the pin's datasheet-recommended termination.

## Try It Yourself

1. **Run ERC on your existing schematic.** Count the errors. For each one, trace the net using the Net Inspector. Fix all "no driver" errors by adding PWR_FLAG symbols on power nets. Re-run ERC until zero errors.

2. **Modify the ERC matrix.** Go to Tools → Electrical Rules Check → ERC Matrix. Change "Output → Output" from Error to Warning. Run ERC again. Now add a second output to a net that already has one—observe the warning. Change it back to Error.

3. **Create an intentional violation.** Place two output pins (e.g., from two different op-amps) on the same net. Run ERC and confirm it flags the conflict. Exclude the error with a comment. Then remove the exclusion and fix the design properly.

## Next Up

Tomorrow, I'm diving into the Footprint Editor to create a custom footprint for a non-standard connector and pair it with a 3D model from StepUp. We'll cover pad stack design, 3D model alignment, and the workflow for importing STEP files into KiCad's 3D viewer.
