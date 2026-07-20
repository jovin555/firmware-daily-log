---
title: "Day 11: Copper Pours & Zone Priorities"
date: 2026-07-20
tags: ["til", "kicad", "copper-pour", "zones"]
---

## What I Explored Today

Today I dove into KiCad’s zone system—specifically copper pours and their priority management. While I’ve used filled zones for ground planes before, I never fully understood how KiCad resolves overlapping zones, or how to properly sequence them for mixed-signal designs. After experimenting with a four-layer board containing analog, digital, and power domains, I now see why zone priority is one of the most critical—and most overlooked—settings in the PCB Editor.

## The Core Concept

A copper pour (zone) in KiCad is a polygon that fills with copper, connected to a net, and optionally hatched or solid. When you have multiple zones on the same layer—say, a GND pour and a 3.3V pour on the top layer—they can overlap. KiCad needs a deterministic rule to decide which net wins in the overlap region. That rule is **zone priority**.

Zone priority is an integer, with **higher numbers taking precedence**. The default is 0. If two zones have the same priority and overlap, KiCad will produce a DRC error (overlapping copper). This is by design: you must explicitly decide which zone dominates. Priority is set per-zone, not per-layer, so you can have a high-priority GND pour that cuts through a lower-priority 3.3V pour on the same layer.

Why does this matter? In practice, you often want a ground pour to fill the entire board, but you also need isolated islands for analog supplies or sensitive nets. By giving the ground pour a lower priority and the analog pour a higher priority, you ensure the analog island remains intact while the ground pour fills everything else. Without priority, you’d have to manually draw keepout zones or rely on net tie footprints—both fragile and error-prone.

## Key Commands / Configuration / Code

**Creating a zone (the manual way):**
- `Add a filled zone` (hotkey: `B` by default, or `Add > Filled Zone` from the menu).
- Click to define polygon vertices, then right-click to close.
- In the zone properties dialog (double-click the zone edge), set:
  - **Net**: e.g., `GND`
  - **Layer**: e.g., `F.Cu`
  - **Priority**: integer (default 0)
  - **Fill style**: Solid, Hatched, or None
  - **Thermal relief**: Enable for hand-soldered pads, disable for high-current

**Setting priority via the Zone Properties dialog:**
```
Zone Properties > Priority
  - Enter a number (e.g., 10 for high priority, 1 for low)
  - Higher number = wins in overlap
```

**Using the Zone Manager (advanced):**
- `Tools > Zone Manager` (or `Z` hotkey).
- Lists all zones in the board. You can sort by layer, net, or priority.
- Double-click any zone to edit its properties.
- **Pro tip**: The Zone Manager shows a preview of the fill order. Zones with higher priority are filled last, so they “cut into” lower-priority zones.

**Example: Two overlapping zones on F.Cu:**
```
Zone A: Net=GND, Priority=0, Layer=F.Cu
Zone B: Net=3V3, Priority=10, Layer=F.Cu
```
Result: In the overlap region, the copper belongs to net 3V3. The GND pour will have a void where Zone B exists.

**Zone fill and refill:**
- After editing zone properties, you must refill: `Tools > Fill All Zones` (hotkey: `B` then `F`? No—actually `Ctrl+F` or `Tools > Fill All Zones`).
- To refill a single zone: right-click the zone edge > `Fill Zone`.
- **Critical**: Always refill before running DRC. Stale fills cause false DRC errors.

## Common Pitfalls & Gotchas

1. **Same priority, overlapping zones → DRC error.**  
   If two zones on the same layer have the same priority and their polygons intersect, KiCad flags a `Zone overlap` error. This is not a warning—it’s a hard DRC violation. Always assign distinct priorities to overlapping zones, or ensure they don’t overlap (e.g., by using keepout zones).

2. **Zone priority does not affect thermal relief.**  
   Thermal relief spokes are generated per-pad, not per-zone. If a pad is connected to two overlapping zones (e.g., a GND pad in a GND pour that overlaps a 3V3 pour), the pad will connect to the higher-priority zone. But the thermal relief settings (spoke width, gap) come from the zone properties of the *winning* zone. If you want different thermal behavior, you must adjust the winning zone’s settings.

3. **Zones on different layers do not interact.**  
   Priority only matters for zones on the same layer. A GND pour on F.Cu and a GND pour on B.Cu can have the same priority—they’re on different layers, so no conflict. However, if you have a zone on F.Cu and another on In1.Cu, they are independent. Don’t waste time setting cross-layer priorities.

4. **Zone fill order matters for performance.**  
   KiCad fills zones in priority order (highest first). If you have many zones with high priority, the fill algorithm may take longer. For large boards, group zones by priority tier (e.g., all GND pours at 0, all power pours at 10, all analog pours at 20). This reduces the number of priority levels and speeds up refill.

## Try It Yourself

1. **Create two overlapping zones on the same layer.**  
   Draw a GND zone (priority 0) covering most of the board. Then draw a 3.3V zone (priority 10) as a small island inside the GND zone. Fill all zones and verify that the 3.3V island is solid copper, while the GND zone has a void around it. Run DRC—there should be no overlap errors.

2. **Swap priorities and observe the difference.**  
   Change the 3.3V zone priority to 0 and the GND zone priority to 10. Refill. Now the GND zone should dominate the overlap region. The 3.3V zone will be fragmented or completely absorbed. This demonstrates why you must carefully assign priorities for power and ground pours.

3. **Use the Zone Manager to audit your board.**  
   Open the Zone Manager (`Tools > Zone Manager`). Sort by priority. Identify any zones with the same priority that might overlap. If you find any, either adjust their polygons to avoid overlap or change one zone’s priority. This is a great sanity check before final DRC.

## Next Up

Tomorrow, I’ll tackle **KiCad Libraries: Managing Global vs Project Libraries**—how to avoid the “missing footprint” nightmare by properly organizing symbols and footprints across projects. We’ll cover library tables, environment variables, and the `fp-lib-table` file.
