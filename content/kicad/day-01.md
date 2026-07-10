---
title: "Day 01: KiCad Overview: Project Structure & Workflow"
date: 2026-07-10
tags: ["til", "kicad", "workflow", "eda"]
---

## What I Explored Today

After years of using proprietary EDA tools, I finally committed to learning KiCad for an upcoming open-source hardware project. Today I focused on understanding KiCad's project structure and the fundamental workflow that connects its various tools. Unlike the monolithic file approach of some commercial suites, KiCad treats each design stage as a separate, linked file—a decision that has deep implications for version control, collaboration, and design reuse. I created my first project from the command line, inspected the generated file tree, and walked through the complete design flow from schematic to PCB layout without placing a single component.

## The Core Concept

KiCad is not a single application but a suite of tightly integrated tools, each responsible for one stage of the PCB design process. The project file (`.kicad_pro`) is the central manager—it stores project metadata, paths to all associated files, and configuration settings like grid spacing, layer colors, and design rules. Everything else is a separate file that the project references.

The key insight: **KiCad's file-per-stage architecture makes it trivial to version control individual design artifacts.** You can diff schematic changes without touching the PCB layout, or share a footprint library without distributing the entire project. This is a deliberate design choice that mirrors how professional engineering teams work—each discipline owns their files.

The workflow is strictly linear in the forward direction: Schematic → Netlist → PCB Layout → Gerber Output. But KiCad supports iterative refinement—you can update the schematic and forward-annotate changes to the PCB without losing placement or routing. The reverse (back-annotation from PCB to schematic) is also supported for pin swaps and gate swaps.

## Key Commands / Configuration / Code

### Creating a Project from the Command Line

```bash
# Create a new project directory and project file
mkdir ~/kicad_projects/my_first_board
cd ~/kicad_projects/my_first_board
kicad-cli project new my_first_board.kicad_pro

# This creates:
#   my_first_board.kicad_pro   - project file
#   my_first_board.kicad_sch   - empty schematic (created on first save)
#   my_first_board.kicad_pcb   - empty PCB (created on first save)
```

### Project File Tree (After First Schematic Save)

```
my_first_board/
├── my_first_board.kicad_pro      # Project metadata & settings
├── my_first_board.kicad_sch      # Schematic data (S-expression format)
├── my_first_board.kicad_pcb      # PCB layout data
├── my_first_board.kicad_prl      # Project local settings (window positions, etc.)
├── my_first_board-cache.lib      # Local copy of all used symbols
├── fp-info-cache                 # Footprint library cache (binary)
└── sym-lib-table                 # Symbol library table (project-specific)
```

### Essential Configuration: Library Tables

KiCad uses two library table files to manage component libraries:

```bash
# Global symbol library table (user-wide)
~/.config/kicad/8.0/sym-lib-table

# Global footprint library table (user-wide)
~/.config/kicad/8.0/fp-lib-table

# Project-specific tables override globals
# Located in the project directory as:
#   sym-lib-table
#   fp-lib-table
```

### The Design Flow in One Command

```bash
# Full forward annotation pipeline (schematic → PCB)
kicad-cli sch export netlist my_first_board.kicad_sch -o my_first_board.net
kicad-cli pcb import netlist my_first_board.kicad_pcb my_first_board.net

# Generate Gerber files for fabrication
kicad-cli pcb export gerbers my_first_board.kicad_pcb -o gerber_output/
```

## Common Pitfalls & Gotchas

### 1. The `.kicad_prl` File Is Not Portable
The project local settings file (`*.kicad_prl`) stores window positions, zoom levels, and last-opened tabs. It's regenerated automatically and should be added to `.gitignore`. Including it in version control causes constant merge conflicts because every user's window geometry differs.

### 2. Symbol vs. Footprint Confusion
New users often confuse symbols (logical representation in the schematic) with footprints (physical land pattern on the PCB). KiCad enforces this separation strictly—you assign a footprint to a symbol during the schematic capture phase. If you skip this step, the PCB editor will show unplaced components with no footprint, and the design rule check (DRC) will fail.

### 3. The Cache Library Is a Trap
KiCad automatically creates a `*-cache.lib` file in your project directory containing copies of all symbols used. This is great for portability—you can zip the project and share it without worrying about missing libraries. However, if you edit a symbol in the original library, the cached version in your project won't update automatically. You must explicitly run "Update Symbols from Library" to refresh the cache.

## Try It Yourself

1. **Create a project from scratch using only the CLI.** Run `kicad-cli project new` to create a project, then open it in KiCad. Verify the file tree matches what I described above. Add `*.kicad_prl` to your `.gitignore` and commit the rest.

2. **Inspect the S-expression format.** Open the `.kicad_sch` file in a text editor. Find the `(symbol` entries and identify how KiCad stores component references, values, and footprint assignments. This is the same format used by the internal tools—understanding it helps with debugging.

3. **Set up a project-specific library table.** Create a `sym-lib-table` file in your project directory that points to a local `lib/` folder containing your custom symbols. Verify that KiCad loads these symbols before the global libraries by checking the library priority in the Symbol Editor.

## Next Up

Tomorrow, we dive into the Schematic Editor (Eeschema). I'll cover how to place symbols, connect them with wires and buses, assign footprints, and run the electrical rules check (ERC) to catch floating pins and unconnected nets before they become PCB layout headaches.
