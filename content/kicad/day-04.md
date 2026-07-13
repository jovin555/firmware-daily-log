---
title: "Day 04: Hierarchical Sheets & Multi-Sheet Schematics"
date: 2026-07-13
tags: ["til", "kicad", "hierarchical-sheets"]
---

## What I Explored Today

Today I tackled hierarchical sheets in KiCad—the mechanism for breaking a monolithic schematic into multiple, interconnected sheets. After wrestling with a 12-page flat schematic on a recent power distribution board, I needed a better way to organize functional blocks. KiCad’s hierarchical design lets you create reusable sheet symbols (think: subcircuit black boxes) that map to separate `.kicad_sch` files. I built a simple two-level hierarchy: a top sheet with a power supply block and a microcontroller block, each as a hierarchical sheet, then drilled into the net connectivity rules between them.

## The Core Concept

Hierarchical sheets solve a fundamental scaling problem. In a flat schematic, every net label is globally visible—fine for 50 nets, a nightmare for 500. With hierarchy, you partition the design into logical domains. Each hierarchical sheet has its own namespace: nets inside a sheet are private unless explicitly exported through hierarchical pins.

The real power is reuse. That LDO regulator circuit you designed for one project? Drop it as a hierarchical sheet into another project, and KiCad copies the `.kicad_sch` file. Change the regulator once, and every instance updates. This isn’t just organization—it’s the foundation for team workflows where different engineers own different sheets.

KiCad implements hierarchy through **sheet symbols** (rectangles with pins) placed on a parent sheet. Double-clicking a sheet symbol descends into the child sheet. Nets crossing the boundary use **hierarchical labels** (not global labels) that match the sheet symbol pin names. The ERC (Electrical Rules Check) enforces that every hierarchical label has a matching pin on the parent sheet symbol.

## Key Commands / Configuration / Code

### Creating a Hierarchical Sheet

1. **Place a sheet symbol**  
   `Place` → `Hierarchical Sheet` (or `S` hotkey)  
   Click to place, then name it (e.g., `POWER_SUPPLY`). KiCad auto-creates a `.kicad_sch` file with that name in the project directory.

2. **Add hierarchical pins to the sheet symbol**  
   Right-click the sheet symbol → `Edit Sheet Symbol Properties` → `Pins` tab.  
   Add pins with names matching the nets you want to expose (e.g., `VCC_3V3`, `GND`, `ENABLE`).  
   Pin type matters: `Bidirectional` for data, `Input` for control signals, `Output` for power rails.

3. **Wire the sheet symbol pins**  
   On the parent sheet, connect nets to the sheet symbol pins using normal wires or global labels.

4. **Design the child sheet**  
   Double-click the sheet symbol to open the child sheet.  
   Place `Hierarchical Label` (`Ctrl+L`) for each pin name you defined. These labels must match exactly (case-sensitive).  
   Wire them to your local components.

### Example: Top Sheet (root.kicad_sch)

```
[Sheet Symbol: POWER_SUPPLY]
  Pins:
    VIN (Input)
    VCC_3V3 (Output)
    GND (Bidirectional)
    EN (Input)

[Sheet Symbol: MCU_CORE]
  Pins:
    VCC (Input)
    GND (Bidirectional)
    UART_TX (Output)
    UART_RX (Input)
```

### Example: Child Sheet (POWER_SUPPLY.kicad_sch)

```
Hierarchical Label: VIN  ──┬── [LDO Regulator IN]
Hierarchical Label: GND  ──┼── [LDO Regulator GND]
Hierarchical Label: VCC_3V3 ──┼── [LDO Regulator OUT]
Hierarchical Label: EN   ──┴── [LDO Regulator EN]
```

### Navigating the Hierarchy

- **Go up one level**: `View` → `Go to Parent Sheet` (or `~` hotkey)
- **Go to specific sheet**: `View` → `Go to Sheet...` (or `Ctrl+Shift+G`)
- **List all sheets**: `Tools` → `Sheet Hierarchy` (opens a tree view)

### Importing an Existing Schematic as a Sheet

1. `File` → `Import` → `Schematic as Hierarchical Sheet...`
2. Select a `.kicad_sch` file. KiCad creates a sheet symbol with pins auto-generated from the hierarchical labels in that file.

## Common Pitfalls & Gotchas

### 1. Mismatched Pin Names (Case-Sensitive)
KiCad treats `VCC_3V3` and `vcc_3v3` as different nets. The ERC will flag an "unconnected hierarchical pin" error. Always copy-paste names from the sheet symbol pin properties to the hierarchical label text field.

### 2. Forgetting to Add GND Pins
It’s tempting to use global `GND` labels inside child sheets. Don’t—unless you want the ground plane to span the entire hierarchy. For isolated subcircuits (e.g., isolated DC-DC converter), explicitly pass `GND` through a hierarchical pin. Otherwise, you’ll create unintended ground loops that ERC won’t catch but the layout engineer will curse.

### 3. Sheet Symbol Pin Order vs. Visual Layout
KiCad doesn’t sort sheet symbol pins automatically. If you add pins in random order, the symbol looks messy. Right-click the sheet symbol → `Edit Sheet Symbol Properties` → `Pins` tab → use the up/down arrows to reorder. A common convention: inputs on the left, outputs on the right, power top, ground bottom.

### 4. Duplicate Sheet Names
You can’t have two sheets with the same name in one project. KiCad appends a number (e.g., `POWER_SUPPLY_1`) if you try. Rename the duplicate in the sheet symbol properties, then update the child file name manually in the project folder—KiCad won’t rename the file for you.

## Try It Yourself

1. **Build a two-sheet hierarchy**: Create a top sheet with one sheet symbol named `LED_DRIVER`. Add pins: `PWM_IN` (Input), `VLED` (Input), `GND` (Bidirectional). Open the child sheet, place a resistor and LED, connect them to hierarchical labels matching those pin names. Wire the top sheet to a simple PWM source.

2. **Reuse a sheet across pages**: Copy your `LED_DRIVER.kicad_sch` file to `LED_DRIVER_2.kicad_sch`. On the top sheet, place a second sheet symbol and point it to the new file (right-click → `Edit Sheet Symbol Properties` → `Sheet file` field). Wire it to a different PWM source. Verify both sheets update when you edit the original LED circuit.

3. **Practice navigation**: In a project with at least three hierarchical sheets, use `Ctrl+Shift+G` to jump between sheets. Open the Sheet Hierarchy tree (`Tools` → `Sheet Hierarchy`) and click through the tree to verify every sheet symbol maps to the correct file path.

## Next Up

Tomorrow: **ERC (Electrical Rules Check): Catching Schematic Errors**. We’ll run ERC on a hierarchical design, decode the cryptic error codes, fix unconnected pins and power mismatches, and configure custom rules for multi-supply nets.
