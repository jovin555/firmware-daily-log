---
title: "Day 15: 3D Viewer & Mechanical Fit Checks"
date: 2026-07-24
tags: ["til", "kicad", "3d-viewer", "mechanical-fit"]
---

## What I Explored Today

Today I ran the full 3D Viewer workflow on a mixed-signal board that needs to slide into a CNC-milled aluminum enclosure with only 1.5mm clearance on each side. I needed to verify connector heights, component keepouts, and mounting hole alignment before committing to fabrication. The 3D Viewer in KiCad isn't just a pretty render—it's a mechanical verification tool that can catch clearance violations, reverse-mount components, and enclosure interference before you spend money on prototypes.

## The Core Concept

The 3D Viewer bridges the gap between electrical design and mechanical integration. Every PCB is a physical object with height constraints, thermal zones, and assembly tolerances. The viewer uses STEP and VRML models from your component footprints to build an accurate assembly. When you rotate, zoom, and measure in 3D space, you're validating:

- **Z-axis clearance**: Tall connectors, electrolytic caps, and heatsinks must fit under enclosure lids or between stacked boards.
- **Keepout zones**: Components must not overlap mechanical features like screw bosses, standoffs, or panel-mount cutouts.
- **Mounting hole alignment**: Board outline and hole positions must match the enclosure's threaded inserts.
- **Reverse-side components**: Bottom-mounted parts (e.g., USB-C connectors, SD card slots) need clearance from the mounting surface.

KiCad's 3D Viewer is not a full MCAD tool—it won't do FEA or dynamic interference detection—but it gives you a rapid, interactive check that catches the most common mechanical mismatches.

## Key Commands / Configuration / Code

### Launching the 3D Viewer

From PCB Editor (Pcbnew), press **Alt+3** or go to *View → 3D Viewer*. The default view shows the board with copper layers, solder mask, and silkscreen.

### Essential Navigation

| Action | Mouse / Keyboard |
|--------|------------------|
| Rotate | Left-click drag |
| Pan | Ctrl + left-click drag |
| Zoom | Scroll wheel |
| Reset view | Home key |
| Orthographic toggle | *View → Projection → Orthographic* (critical for checking alignment) |

**Pro tip**: Switch to orthographic projection when checking edge-to-edge clearances. Perspective distorts relative sizes.

### Loading Realistic 3D Models

KiCad ships with basic 3D models for common footprints, but for mechanical fit checks you need accurate STEP models from manufacturers.

1. **Assign a 3D model to a footprint**: In Footprint Editor, select the footprint, click the *3D Settings* tab, then *Add 3D Shape*.
2. **Use STEP files when possible**: STEP preserves exact geometry and units. KiCad supports `.step`, `.stp`, `.wrl`, and `.x3d`.
3. **Set model offset and rotation**: For connectors that mount at an angle or need a specific orientation, use the *Offset* and *Rotation* fields in the 3D Settings dialog.

Example: Assigning a USB-C connector model with correct orientation:
```
Model path: /path/to/usb_c_receptacle.step
Offset X: 0 mm, Y: 0 mm, Z: 1.6 mm  (board thickness)
Rotation: 0, 0, 90  (rotate 90° around Z axis)
```

### Measuring in 3D Viewer

KiCad 8+ has a measurement tool in the 3D Viewer. Press **M** or click the ruler icon, then click two points. The distance appears in the status bar. Use this to:
- Measure from board edge to tallest component top
- Check clearance between two tall parts
- Verify mounting hole center-to-center distances

### Layer Visibility Toggle

In the 3D Viewer sidebar, you can toggle:
- **Board body**: Show/hide the PCB substrate
- **Copper layers**: Visualize trace and plane locations
- **Solder mask**: See actual mask openings
- **Silkscreen**: Verify reference designators are readable
- **3D models**: Show/hide component bodies

For mechanical fit, I always disable copper and silkscreen layers to focus on the physical envelope.

### Exporting for MCAD Collaboration

If your mechanical engineer uses SolidWorks, Fusion 360, or FreeCAD, export the board as STEP:
- *File → Export → STEP*
- Choose *Board with components* or *Board only*
- Set *Export footprint outlines* to include component bodies

## Common Pitfalls & Gotchas

### 1. Missing or Wrong 3D Models
The biggest trap. KiCad's default models are often simplified cubes or cylinders. A "generic" capacitor model might be 5mm tall when your actual part is 8mm. **Always** download manufacturer STEP files for critical height-sensitive components (connectors, electrolytics, relays). Store them in a project-local `3dmodels/` folder with relative paths so they work across machines.

### 2. Board Thickness Mismatch
The 3D Viewer uses the board stackup thickness from the Board Setup. If you set a 1.6mm stackup but your actual board is 0.8mm, all Z-axis clearances will be wrong. Verify *File → Board Setup → Board Stackup → Thickness* before trusting measurements.

### 3. Ignoring Solder Joint Height
The 3D Viewer shows component bodies but not solder joints. A through-hole connector's pins extend below the board by 1-2mm. For bottom-clearance checks, add a 1mm safety margin or create a simple "solder tail" model.

### 4. Orthographic vs Perspective Confusion
In perspective mode, a 10mm gap at the far end of the board looks smaller than it is. Always switch to orthographic for critical measurements.

## Try It Yourself

1. **Envelope check**: Open your current board in 3D Viewer, switch to orthographic projection, and measure the Z-axis height from the bottom of the PCB to the top of the tallest component. Compare this to your enclosure's internal height. Is there at least 1mm margin?

2. **Mounting hole alignment**: Export your board as STEP (with components). Import it into a free MCAD viewer (e.g., FreeCAD or Fusion 360's free tier). Overlay your enclosure model and verify that all mounting holes align within 0.2mm.

3. **Reverse-side clearance**: In the 3D Viewer, flip the board (press **F** or use the *Flip* button). Identify any components on the bottom layer that protrude more than 0.5mm. If you're mounting the board on standoffs, ensure these parts don't hit the mounting surface.

## Next Up

Tomorrow, we'll generate Gerber and drill files for fabrication—the final step before sending your design to a board house. We'll cover layer mapping, drill file formats, and the critical pre-flight checklist that catches 90% of fab rejects.
