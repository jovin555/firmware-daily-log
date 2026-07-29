---
title: "Day 18: Version Control for KiCad Projects: Git Workflow & KiCad-diff"
date: 2026-07-29
tags: ["til", "kicad", "git", "version-control"]
---

## What I Explored Today

Today I tackled the messy reality of version-controlling KiCad projects. While Git handles source code beautifully, it chokes on KiCad's binary and complex text formats. I explored a practical Git workflow for KiCad projects, including `.gitignore` strategies, commit discipline, and the essential tool `kicad-diff` for visualizing schematic and board changes in pull requests. The goal: make PCB design review as clean as code review.

## The Core Concept

KiCad stores designs in two primary files: the schematic (`.kicad_sch`) and the PCB layout (`.kicad_pcb`). Both are S-expression text files, which is a huge win—they are diffable. But they are also *noisy*. A single component move can rewrite hundreds of lines of coordinate data. A netlist change can ripple through dozens of symbol references. Raw `git diff` on these files is nearly useless for review.

The solution is twofold:
1. **Structure your repository** to track only the source files, not the generated artifacts (cache, backups, libraries).
2. **Use `kicad-diff`** to generate visual, human-readable diffs of schematics and board layouts. This tool renders the before/after as images, highlighting moved, added, or deleted elements.

Without this workflow, you either commit giant binary blobs (like Gerbers) or you lose traceability entirely. With it, you can review a colleague's footprint change or a routing adjustment as clearly as a code diff.

## Key Commands / Configuration / Code

### 1. The `.gitignore` for KiCad

Start with this minimal `.gitignore` in your project root:

```gitignore
# KiCad auto-generated cache and backup files
*.bak
*-cache.lib
*-rescue.lib
*-save.pro
*-save.kicad_sch
*-save.kicad_pcb

# Simulation and analysis artifacts
*.raw
*.dat
*.csv

# OS files
.DS_Store
Thumbs.db

# Generated output directories (Gerbers, drill files, etc.)
output/
gerber/
```

**Why these?** The `-cache.lib` and `-rescue.lib` files are regenerated every time you open the schematic. The `-save.*` files are KiCad's auto-save mechanism. None of these belong in version history.

### 2. Basic Git Workflow

```bash
# Initialize repo (do this before first commit)
git init
git add .gitignore
git commit -m "chore: add KiCad .gitignore"

# Add project files
git add *.kicad_pro *.kicad_sch *.kicad_pcb
git add *.lib *.dcm  # only if you have custom symbols
git add *.pretty/    # only if you have custom footprints
git commit -m "feat: initial design import"

# Typical commit cycle
# After moving a component or rerouting a trace:
git add *.kicad_pcb
git commit -m "fix: adjust C5 placement to avoid D2 clearance violation"
```

**Commit discipline:** Keep schematic and PCB changes in separate commits when possible. A single commit that touches both files makes it harder to isolate issues.

### 3. Installing and Using `kicad-diff`

`kicad-diff` is a Python tool that generates visual diffs. Install it:

```bash
pip install kicad-diff
```

Basic usage to compare two commits:

```bash
# Compare current HEAD with a previous commit
kicad-diff HEAD~1 HEAD --output-dir ./diff_output

# Compare two specific commits
kicad-diff abc123 def456 --output-dir ./diff_output

# Compare working tree with last commit (uncommitted changes)
kicad-diff HEAD --output-dir ./diff_output
```

The tool outputs a set of PNG images in `./diff_output/`. For schematics, it highlights added wires in green, removed in red. For PCBs, it shows layer-by-layer overlay with color-coded changes.

### 4. Integrating into Code Review (GitHub/GitLab)

Add a CI step to generate diffs on pull requests. Example GitHub Actions snippet:

```yaml
- name: Generate KiCad diff
  run: |
    pip install kicad-diff
    kicad-diff origin/main HEAD --output-dir ./diff
- name: Upload diff artifacts
  uses: actions/upload-artifact@v4
  with:
    name: kicad-diff
    path: ./diff/
```

Reviewers can then download the artifact and inspect the visual diff alongside the code changes.

## Common Pitfalls & Gotchas

1. **Committing `-cache.lib` files.** These are regenerated from the schematic's symbol references. If you commit them, you'll get constant merge conflicts when two people open the same schematic. Always add `*-cache.lib` to `.gitignore`.

2. **Binary diff on `.kicad_pcb` files.** Even though the PCB file is text, a `git diff` of a rerouted board is unreadable—thousands of coordinate lines change. Never rely on raw text diff for PCB review. Always use `kicad-diff` or a similar visual tool.

3. **Forgetting to commit `.kicad_pro`.** The project file stores design settings (grid, layers, net classes). If you don't commit it, every team member will have different defaults, leading to "works on my machine" issues. It's small and text-based—commit it.

4. **Merging without checking for board file conflicts.** KiCad's PCB file format is not merge-friendly. If two people edit the same board, a merge conflict can corrupt the file. Best practice: assign one person per board at a time, or use a locking mechanism (e.g., Git LFS with file locking).

## Try It Yourself

1. **Set up a KiCad project with proper Git hygiene.** Create a new project, initialize Git, add the `.gitignore` above, and make your first commit. Then make a small schematic change (add a resistor), commit again, and run `git diff HEAD~1 HEAD` to see the raw text diff. Note how noisy it is.

2. **Install `kicad-diff` and generate a visual diff.** Make a second change—move a component on the PCB. Run `kicad-diff HEAD~1 HEAD --output-dir ./diff`. Open the generated PNGs and compare them to the raw text diff. Observe how much easier the visual diff is to review.

3. **Simulate a team workflow.** Create a second branch, make a conflicting change (e.g., move the same component to a different position), and attempt a merge. See what happens. Then practice resolving the conflict by manually editing the `.kicad_pcb` file (hint: look for the component's `(at ...)` line).

## Next Up

Day 19: Simulation with ngspice Integration in KiCad — we'll wire up a circuit, run transient analysis, and plot the results, all from within the KiCad environment.
