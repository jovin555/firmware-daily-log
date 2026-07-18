---
title: "Day 09: Interactive Router: Push & Shove, Diff Pair Routing"
date: 2026-07-18
tags: ["til", "kicad", "interactive-router", "diff-pair"]
---

## What I Explored Today

Today I dove deep into KiCad's interactive router, specifically the push-and-shove engine and differential pair routing. After weeks of manual track placement and tweaking, I decided it was time to let the autorouter assist without losing control. The interactive router in KiCad 7+ is surprisingly capable—it's not a full autorouter, but a semi-automatic tool that respects your design rules while dynamically pushing existing tracks out of the way. I also tackled differential pair routing for a USB 2.0 interface, which requires precise length matching and controlled impedance. The results were clean, repeatable, and saved me hours of manual adjustment.

## The Core Concept

The interactive router (often called the "push-and-shove" router) works on a simple but powerful principle: instead of you fighting against existing traces, the router dynamically moves them aside as you lay new ones. This is fundamentally different from the classic "avoid obstacles" mode, which simply refuses to route through occupied space. Push-and-shove actively repositions existing tracks to maintain clearance, then restores them after you pass. The router uses a constraint solver that evaluates your design rules (clearances, track widths, via sizes) in real-time, ensuring every move is DRC-clean.

For differential pairs, the router extends this concept to two nets simultaneously. It maintains a constant gap between the P and N traces while routing them as a unit. The router also supports length tuning—you can add meanders to one trace to match the other's length, critical for signal integrity in high-speed interfaces like USB, HDMI, or LVDS. The key insight is that the router doesn't just place tracks; it optimizes the pair's geometry to meet your impedance and skew requirements.

## Key Commands / Configuration / Code

### Enabling the Interactive Router

First, ensure you're in the correct routing mode. In the PCB Editor, select the **Route Tracks** tool (shortcut `X`). The mode selector appears in the top toolbar:

- **Highlight collisions** (default) – shows conflicts but doesn't resolve them
- **Shove** – pushes existing tracks aside
- **Walk around** – routes around obstacles without moving them
- **Ignore obstacles** – dangerous, use only for manual override

For push-and-shove, select **Shove** mode.

### Differential Pair Routing

To route a differential pair, you must first assign the nets to a differential pair class:

1. Open **Board Setup** → **Net Classes**.
2. Create a new net class (e.g., `USB_DP_DM`).
3. Set the **Track Width** (e.g., 0.3 mm) and **Clearance** (e.g., 0.2 mm).
4. In the **Differential Pairs** tab, add a pair: Net A = `USB_DP`, Net B = `USB_DM`.
5. Set **Pair Width** (same as track width) and **Pair Gap** (e.g., 0.2 mm for 90Ω differential impedance on a standard 4-layer stackup).

Now, activate the differential pair router:

- Press `X` to start routing.
- Click on the pad of either net in the pair. The router automatically selects both nets.
- Route as a single track—the router maintains the gap and width.

### Length Tuning

After routing, you may need to match lengths. Select the differential pair track, then press `D` to enter **Tune Differential Pair Length** mode. A dialog appears:

- **Target Length** – enter the desired length (e.g., 50 mm for USB 2.0).
- **Tolerance** – set to 0.5 mm or tighter.
- **Style** – choose **Accordion** or **Sawtooth** meanders.

The router inserts meanders automatically. Use the mouse wheel to adjust amplitude and spacing.

### Keyboard Shortcuts (While Routing)

| Shortcut | Action |
|----------|--------|
| `V` | Toggle via insertion |
| `F` | Flip layer (adds via automatically) |
| `Ctrl+Z` | Undo last segment |
| `Shift+Space` | Cycle through corner styles (45°, 90°, arc) |
| `G` | Toggle grid snapping |

### Configuration File Snippet

In `kicad_common.json`, you can adjust router behavior:

```json
{
  "pcbnew": {
    "router": {
      "shove_tolerance": 0.01,
      "optimizer_effort": 2,
      "smooth_drag": true,
      "drag_mode": "shove"
    }
  }
}
```

- `shove_tolerance`: how close tracks can be before shoving (in mm).
- `optimizer_effort`: 0=off, 1=moderate, 2=aggressive (slower but cleaner).
- `smooth_drag`: enables smooth dragging of existing tracks during shove.

## Common Pitfalls & Gotchas

1. **Shove mode fails on locked tracks.** If you have intentionally locked critical traces (e.g., RF lines), the router will stop or produce DRC errors. Always unlock tracks you want the router to move, or use "Walk around" mode for those sections.

2. **Differential pair gap is not automatically impedance-controlled.** KiCad does not calculate impedance from stackup. You must compute the required gap using a calculator (e.g., Saturn PCB Toolkit) and set it manually in the net class. The router only maintains the gap you specify—it won't warn you if the impedance is wrong.

3. **Length tuning can create acute angles.** When meandering, the router may produce angles < 90°, which are manufacturing no-nos. After tuning, run DRC and visually inspect meanders. Use the `Shift+Space` shortcut to force 45° corners during tuning.

4. **Via shoving is limited.** The router can push vias, but only if they are not locked and if there's enough space. In dense designs, you may need to manually relocate vias before routing.

## Try It Yourself

1. **Practice push-and-shove routing:** Create a simple board with two ICs and route a 0.5 mm track between them. Then route a second track parallel to the first, using shove mode. Observe how the first track is displaced. Try routing a third track in between—the router should maintain clearance automatically.

2. **Route a USB differential pair:** Set up a net class with 0.3 mm width and 0.2 mm gap. Route a 50 mm differential pair from a USB connector to an MCU. Use the length tuning tool to match the pair to within 0.5 mm. Verify with the length measurement tool (Ctrl+L).

3. **Experiment with router settings:** Change `optimizer_effort` in the config file to 0 and route a complex area. Then set it to 2 and re-route the same area. Compare the track quality and routing time. Which do you prefer for production?

## Next Up

Tomorrow, we'll tackle **Design Rules in KiCad: Netclasses, Clearances & Constraints**. We'll set up a complete rule hierarchy, define net classes for power, signal, and high-speed nets, and configure custom clearances for BGA fanout. You'll learn how to enforce your design constraints automatically, so DRC catches mistakes before you send the board to fabrication.
