---
title: "Day 14: Custom Design Rule Checks with KiCad's DRC Engine"
date: 2026-07-23
tags: ["til", "kicad", "drc"]
---

## What I Explored Today

KiCad's built-in Design Rule Check (DRC) handles clearance, width, and annular ring violations out of the box. But real-world boards need more: differential pair impedance matching, via-in-pad restrictions, high-voltage creepage distances, or assembly-specific keepouts. Today I dug into KiCad's custom DRC engine—specifically the `kicad_drc` Python API—to write, register, and run bespoke design rules that catch layout errors the standard checker misses.

## The Core Concept

The standard DRC is a fixed set of geometric checks: "is this copper too close to that copper?" Custom DRC rules let you inject arbitrary Python logic into the verification pipeline. KiCad 7+ exposes a `pcbnew` module with a `DRC_RULE` class. You subclass it, override `doCheck()` or `doCheckArea()`, and register the rule in a Python script that runs inside KiCad's scripting console or as a standalone action.

Why not just use a post-layout script? Because custom DRC rules integrate directly into the DRC dialog—they run alongside standard checks, report violations in the same panel, and can be toggled on/off. This means your team sees the same error list without switching tools. The engine also provides access to the board's full data model: pads, tracks, zones, footprints, and their properties.

## Key Commands / Configuration / Code

### 1. The Minimal Custom DRC Rule

Save this as `my_custom_drc.py` in your project directory:

```python
import pcbnew

class ViaInPadCheck(pcbnew.DRC_RULE):
    def __init__(self):
        pcbnew.DRC_RULE.__init__(self)
        self.name = "Via-in-Pad Check"
        self.description = "Flags vias placed inside SMD pads"
        self.severity = pcbnew.VIOLATION_SEVERITY_ERROR

    def doCheck(self, aBoard, aCommit):
        violations = []
        # Iterate all footprints
        for footprint in aBoard.GetFootprints():
            # Get SMD pads only
            for pad in footprint.Pads():
                if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                    continue
                pad_bbox = pad.GetBoundingBox()
                # Check all vias on the board
                for track in aBoard.GetTracks():
                    if track.Type() != pcbnew.PCB_VIA_T:
                        continue
                    via_pos = track.GetPosition()
                    if pad_bbox.Contains(via_pos):
                        violation = pcbnew.DRC_VIOLATION()
                        violation.SetPosition(via_pos)
                        violation.SetMessage(
                            f"Via at ({via_pos.x//1e6},{via_pos.y//1e6}) "
                            f"inside pad {pad.GetNumber()} of {footprint.GetReference()}"
                        )
                        violations.append(violation)
        return violations
```

### 2. Registering the Rule

In KiCad's PCB Editor, open **Tools → Scripting Console** (or press **Alt+`**). Run:

```python
import sys
sys.path.insert(0, "/path/to/your/project")  # adjust path
import my_custom_drc

# Register the rule
rule = my_custom_drc.ViaInPadCheck()
pcbnew.GetBoard().GetDesignSettings().AddDRCRule(rule)

# Run DRC (triggers all rules)
pcbnew.GetBoard().GetDesignSettings().RunDRC()
```

After registration, the rule appears in **Inspect → Design Rules → Custom Rules** tab. You can enable/disable it and set severity. The violation appears in the DRC panel with a clickable location.

### 3. Advanced: Area-Based Check with Zone Clearance

For high-voltage creepage, you might want to enforce a larger clearance between two specific net classes:

```python
class HVtoLVCreepage(pcbnew.DRC_RULE):
    def __init__(self, min_creepage_nm=2e6):  # 2 mm
        pcbnew.DRC_RULE.__init__(self)
        self.name = "HV-to-LV Creepage"
        self.min_creepage = min_creepage_nm
        self.severity = pcbnew.VIOLATION_SEVERITY_ERROR

    def doCheckArea(self, aBoard, aCommit, aLayerSet, aBBox):
        # Only check on top and bottom copper layers
        violations = []
        for layer in [pcbnew.F_Cu, pcbnew.B_Cu]:
            # Get all copper items on this layer
            items = aBoard.GetArea(layer)
            # Simplified: check distance between HV and LV zones
            # (real implementation would iterate zone polygons)
            # ...
        return violations
```

The `doCheckArea` variant is called with a bounding box and layer set, enabling incremental checks during interactive routing.

## Common Pitfalls & Gotchas

1. **Coordinate Units Are Nanometers**  
   KiCad's internal unit is nanometers. A position `(x, y)` from `GetPosition()` returns integers in nm. If you compare against mm values, multiply by 1e6. Forgetting this leads to rules that never fire or fire everywhere.

2. **Rule Registration Is Not Persistent**  
   Custom rules added via the scripting console vanish when you close KiCad. To make them permanent, either:  
   - Add the registration code to your project's `kicad_drc.py` file (KiCad auto-loads it from the project directory).  
   - Or use a plugin that installs the rule via `pcbnew.GetBoard().GetDesignSettings().AddDRCRule()` in the plugin's `OnStart()`.

3. **Performance on Large Boards**  
   Iterating every pad and every track in `doCheck()` is O(n*m). For boards with 10k+ items, this can stall the DRC for seconds. Use `doCheckArea()` with spatial indexing (KiCad's `BOARD::GetBBox()` and layer filtering) to limit the search space. Alternatively, pre-build an R-tree using `pcbnew.BOARD::GetTracks()` and `GetFootprints()` once, then query.

## Try It Yourself

1. **Write a "No Silkscreen on Pads" rule**  
   Create a custom DRC rule that checks if any silkscreen text or graphic overlaps an SMD pad. Use `footprint.Reference().GetText()` and `pad.GetBoundingBox()` for overlap detection.

2. **Add a net-class-based clearance rule**  
   Extend the HV-to-LV example above. Use `pcbnew.NETCLASS` to get nets by name (e.g., "HV_*" and "LV_*"), then enforce a 3 mm clearance between any copper on those nets.

3. **Persist your rule as a project file**  
   Create a `kicad_drc.py` file in your project root. Move the registration code there so the rule loads automatically every time you open the PCB. Test by closing and reopening KiCad.

## Next Up

Tomorrow, I’ll switch from electrical verification to mechanical: **Day 15: 3D Viewer & Mechanical Fit Checks**. We’ll load STEP models, check enclosure clearances, and use the 3D canvas to spot connector alignment issues before the board goes to fab.
