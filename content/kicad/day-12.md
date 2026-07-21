---
title: "Day 12: KiCad Libraries: Managing Global vs Project Libraries"
date: 2026-07-21
tags: ["til", "kicad", "libraries"]
---

## What I Explored Today

Today I dug into KiCad's library management system, specifically the distinction between global and project-level libraries. After a frustrating session where a colleague's board wouldn't open because of a missing symbol path, I realized I needed to understand how KiCad resolves library references. The key insight: KiCad 8.x uses a two-tier system where global libraries are available to every project, while project-specific libraries are only loaded when that project is active. Getting this wrong means broken links, missing footprints, and "Symbol not found" errors that waste hours.

## The Core Concept

KiCad's library table system (introduced in v6) is a database of key-value pairs mapping a library nickname to a file path. There are three separate tables: one for symbols (`sym-lib-table`), one for 3D models (`fp3d-lib-table`), and one for footprints (`fp-lib-table`). Each table exists at two levels:

- **Global**: Stored in `~/.config/kicad/8.0/` (Linux) or `%APPDATA%\kicad\8.0\` (Windows). Every project sees these.
- **Project-local**: Stored as `fp-lib-table` and `sym-lib-table` files inside the project directory. Only that project loads them.

The critical design decision: when you place a symbol or footprint, KiCad stores the *library nickname* and *entry name* in the schematic or board file—not the full path. At load time, KiCad first checks the project-local tables, then falls back to global tables. If neither has a matching nickname, you get a broken reference.

Why does this matter? If you use global libraries for your team's shared parts, everyone must have identical global library configurations. If you use project libraries, you can zip the project folder and send it to anyone—all symbols and footprints travel with the project. For production teams, I recommend a hybrid: global for standard vendor parts (resistors, caps, connectors), project-local for custom boards and application-specific symbols.

## Key Commands / Configuration / Code

**Viewing active library tables:**

In KiCad, go to `Preferences → Manage Symbol Libraries` (or `Manage Footprint Libraries`). This opens the table editor. The top half shows global libraries, the bottom half shows project libraries. Each row has: Nickname, Library Path, Library Format, and Options.

**Adding a project-local symbol library (CLI method):**

```bash
# Navigate to your project directory
cd /home/user/projects/my_board/

# Create a project-local symbol library table if it doesn't exist
# The file must be named exactly "sym-lib-table"
touch sym-lib-table

# Add a library entry using KiCad's command-line tool
# This appends a row to the table
kicad-cli sym-lib-table add \
  --nickname "MY_CUSTOM" \
  --uri "${KIPRJMOD}/lib/my_custom.kicad_sym" \
  --type "KiCad" \
  --descr "Custom symbols for this project" \
  sym-lib-table
```

**Adding a project-local footprint library (manual edit):**

```xml
<!-- fp-lib-table contents -->
<?xml version="1.0" encoding="utf-8"?>
<fp_lib_table>
  <lib>
    <name>PROJECT_FP</name>
    <uri>${KIPRJMOD}/footprints/project.pretty</uri>
    <type>KiCad</type>
    <options/>
    <descr>Project-specific footprints</descr>
  </lib>
</fp_lib_table>
```

The `${KIPRJMOD}` variable is critical—it expands to the project directory path at load time, making the library portable.

**Checking library resolution at load time:**

```bash
# From the command line, test if a symbol can be resolved
kicad-cli sym export --library "MY_CUSTOM:MY_PART" --output test.svg
# If the library isn't found, you'll get an error like:
# Error: Symbol 'MY_CUSTOM:MY_PART' not found in any library
```

**Migrating a global library to project-local:**

1. Copy the `.kicad_sym` file into your project's `lib/` folder.
2. Open `Preferences → Manage Symbol Libraries`.
3. In the "Project Specific Libraries" section, click the folder icon and browse to the copied file.
4. Give it a nickname (e.g., `PROJ_SYM`).
5. Remove the global reference if you want to avoid confusion.

## Common Pitfalls & Gotchas

**1. The "Symbol not found" error after sharing a project**
This happens when you used a global library nickname that doesn't exist on the recipient's machine. The fix: always use project-local libraries for any custom or non-standard parts. Before zipping a project, run `kicad-cli sym export --list` to see which libraries are referenced, then verify they're in the project's `sym-lib-table`.

**2. Editing the wrong table in the GUI**
KiCad's library manager shows both global and project tables in the same window. It's easy to add a library to the global section when you intended it to be project-local. Always check the section header before clicking "Add". The project section is clearly labeled and usually has fewer entries.

**3. Forgetting to update both symbol and footprint tables**
A common workflow: you create a custom symbol and assign a footprint. Later, you move the footprint library to a new path but forget to update the project's `fp-lib-table`. The symbol resolves fine, but the footprint doesn't. KiCad will show a warning during DRC, but only if you have "Check for missing footprints" enabled. Always verify both tables after any library reorganization.

## Try It Yourself

1. **Create a project-local footprint library**: In an existing project, create a `footprints/` directory. Add a single custom footprint (even a simple rectangle). Create a `fp-lib-table` file that points to this directory using `${KIPRJMOD}`. Verify the footprint appears in the footprint chooser when that project is open, but not in other projects.

2. **Break and fix a library reference**: Place a symbol from a global library. Then, in the global library manager, temporarily remove that library. Open the schematic—you should see the "Symbol not found" warning. Now add the library back as a project-local entry using the same nickname. The warning should disappear.

3. **Export a portable project**: Create a new project that uses only project-local libraries (copy any needed symbols/footprints into the project folder). Zip the entire project directory and send it to a colleague or a different machine. Open it—it should load without any missing library errors.

## Next Up

Tomorrow, we'll move beyond manual library management and into automation: **Plugin & Scripting: KiCad Python API**. I'll show you how to write a Python script that batch-updates footprint assignments across an entire schematic, automates BOM generation, and hooks into KiCad's action system. No more repetitive clicking—just clean, scriptable workflows.
