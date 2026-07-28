---
title: "Day 17: BOM Generation & Integration with JLCPCB/PCBWay"
date: 2026-07-28
tags: ["til", "kicad", "bom", "jlcpcb"]
---

## What I Explored Today

Today I tackled the final bridge between a finished PCB design and actual manufacturing: generating a clean, assembly-ready Bill of Materials (BOM) that plays nicely with JLCPCB and PCBWay. After spending weeks on schematic capture and layout, I realized that a sloppy BOM is the fastest way to get an email from your fab saying "parts not found" or "footprint mismatch." I walked through KiCad's BOM export tools, wrote a custom Python plugin for JLCPCB's specific format, and validated the output against both fabs' component databases.

## The Core Concept

A BOM is more than a parts list—it's the contract between your design intent and the assembly house's pick-and-place machines. JLCPCB and PCBWay both require specific column headers, part number formats, and designator ordering. The critical insight is that your KiCad schematic symbols contain metadata (like `MPN`, `Manufacturer`, `JLCPCB Part #`) that must be mapped correctly. If you skip this mapping, the fab's system will either reject your BOM or substitute parts you didn't intend.

The real engineering work is in normalizing your component fields. JLCPCB prefers their internal part numbers (e.g., `C15850` for a 100nF 0603 capacitor), while PCBWay accepts manufacturer MPNs directly. Both require that you strip out non-assembly components (test points, mounting holes, fiducials) and that you sort designators in alphanumeric order (R1, R10, R2—not R1, R2, R10). Getting this wrong means your board gets built with wrong-value passives or missing ICs.

## Key Commands / Configuration / Code

### 1. KiCad's Built-in BOM Generator (GUI)

The fastest path is `Tools > Generate Bill of Materials`. KiCad ships with several plugins. For JLCPCB, I use the "bom_csv_grouped_by_value" plugin as a starting point, then modify the output.

**Plugin selection:** Choose `bom_csv_grouped_by_value.py` from the dropdown. This groups identical components (e.g., all 10kΩ resistors) into one row, which is what assembly houses expect.

**Output file:** `bom_jlcpcb.csv`

### 2. Custom Python Plugin for JLCPCB Format

KiCad plugins are Python scripts in `~/.local/share/kicad/8.0/plugins/` (Linux) or `%APPDATA%/kicad/8.0/plugins/` (Windows). Here's a minimal plugin that outputs JLCPCB's exact column order:

```python
#!/usr/bin/env python
# bom_jlcpcb.py — KiCad BOM plugin for JLCPCB assembly format
# Place in KiCad plugins directory, then restart KiCad

import kicad_netlist_reader
import csv
import sys

def my_plugin(netlist):
    # netlist is a kicad_netlist_reader.netlist object
    components = netlist.getInterestingComponents()
    
    # Filter out non-assembly components (test points, mounting holes)
    # Assumes you've set Field "ExcludeFromBOM" = "1" in schematic
    assembly_components = [c for c in components 
                          if c.getField("ExcludeFromBOM") != "1"]
    
    # Sort by reference designator (alphanumeric: R1, R2, R10)
    assembly_components.sort(key=lambda c: c.getRef())
    
    with open("bom_jlcpcb.csv", "w", newline="") as f:
        writer = csv.writer(f)
        # JLCPCB required header row (exact order)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        
        for comp in assembly_components:
            # Get LCSC part number from field "LCSC" (you must fill this in schematic)
            lcsc_part = comp.getField("LCSC") or ""
            # Fallback: try to match value to JLCPCB database (not shown for brevity)
            
            writer.writerow([
                comp.getValue(),           # Comment (e.g., "100nF")
                comp.getRef(),             # Designator (e.g., "C1,C2")
                comp.getFootprint(),       # Footprint (e.g., "Capacitor_SMD:C_0603_1608Metric")
                lcsc_part                  # LCSC Part # (e.g., "C15850")
            ])

# Register plugin with KiCad
if __name__ == "__main__":
    # KiCad calls this with the netlist file path
    netlist = kicad_netlist_reader.netlist(sys.argv[1])
    my_plugin(netlist)
```

**Usage:** After saving the script, restart KiCad. In the BOM dialog, select `bom_jlcpcb.py` from the plugin dropdown. Click "Generate" — it outputs `bom_jlcpcb.csv` in the project directory.

### 3. Command-Line BOM Generation (for CI/CD)

For automated builds, use `kicad-cli`:

```bash
# Export netlist from schematic
kicad-cli sch export netlist -o output.net project.kicad_sch

# Then run your custom plugin against the netlist
python bom_jlcpcb.py output.net
```

### 4. BOM Validation Script (Python)

Before uploading to JLCPCB, I run this quick sanity check:

```python
#!/usr/bin/env python3
# validate_bom.py — Checks common BOM errors

import csv
import sys

def validate_bom(filename):
    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    errors = []
    for row in rows:
        # Check for empty LCSC part numbers
        if not row.get('LCSC Part #', '').strip():
            errors.append(f"Missing LCSC part for {row['Designator']}")
        
        # Check designator format (should be like R1, not R 1)
        refs = row['Designator'].split(',')
        for ref in refs:
            ref = ref.strip()
            if not ref or not ref[0].isalpha() or not ref[1:].isdigit():
                errors.append(f"Bad designator format: {ref}")
    
    if errors:
        print("BOM validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("BOM validation PASSED")

if __name__ == "__main__":
    validate_bom(sys.argv[1])
```

## Common Pitfalls & Gotchas

1. **Designator sorting order:** KiCad's default sort is alphabetical (R1, R10, R2). JLCPCB's system expects alphanumeric (R1, R2, R10). Always sort your designators in the BOM plugin or in a post-processing step. A mismatch here causes the pick-and-place machine to skip components.

2. **Missing LCSC part numbers:** JLCPCB's assembly service requires their internal part number (e.g., `C15850`), not the manufacturer MPN. If you leave this field blank, JLCPCB will either reject the BOM or substitute a part with different specs. I maintain a local CSV mapping file that cross-references value/footprint to LCSC part numbers.

3. **Including non-assembly components:** Test points, fiducials, and mounting holes should be excluded from the BOM. Use a custom field `ExcludeFromBOM` in your schematic symbols and filter on it in your plugin. Forgetting this adds $0.50+ per component to assembly costs and confuses the fab.

## Try It Yourself

1. **Create a custom BOM plugin:** Modify the Python script above to output PCBWay's format (columns: Comment, Designator, Footprint, Manufacturer Part Number). Test it on a small project with 10-15 components.

2. **Validate your existing BOM:** Run the validation script against a BOM from a previous project. Fix any designator sorting issues and missing part numbers. Upload the corrected BOM to JLCPCB's BOM tool (free, no order required) to see if it passes.

3. **Build a part mapping CSV:** Create a spreadsheet that maps your most-used components (resistors, caps, LEDs) to their LCSC part numbers. Write a script that reads this CSV and auto-fills the `LCSC` field in your KiCad schematic symbols.

## Next Up

Tomorrow: **Version Control for KiCad Projects: Git Workflow & KiCad-diff** — I'll show you how to stop emailing ZIP files and start using Git branches for design iterations, plus how KiCad-diff generates visual PCB diffs for peer review.
