---
title: "Day 13: PFMEA for PCB Assembly: SMT, Reflow & Inspection Failure Modes"
date: 2026-07-22
tags: ["til", "fmea", "pfmea", "smt", "reflow"]
---

## What I Explored Today

Today I dug into the PFMEA for a typical PCB assembly line, focusing on the three most failure-prone process steps: solder paste printing (SMT), reflow soldering, and automated optical inspection (AOI). While many teams treat these as black boxes, the real value of a PFMEA emerges when you decompose each sub-step—paste deposition, component placement, thermal profiling, and inspection thresholds—and assign severity, occurrence, and detection ratings with hard data from your own line. I walked through a real PFMEA worksheet for a 0201 capacitor assembly process and identified the critical failure modes that drive yield loss in high-volume production.

## The Core Concept

The core idea is that PCB assembly failures are rarely random; they follow predictable patterns tied to process parameters. A PFMEA forces you to map each failure mode to a specific process step and control. For example, "solder bridging" isn't a single failure—it can originate from excessive paste volume (stencil thickness), poor pad design (land pattern), or incorrect reflow profile (soak time). By linking each failure mode to a process parameter (e.g., squeegee pressure, preheat ramp rate), you can define actionable prevention controls rather than relying solely on inspection to catch defects.

The "why" is simple: inspection (AOI, X-ray) adds cost and latency. A PFMEA shifts your line from detection-dependent to prevention-driven. For instance, if you identify "tombstoning" as a high-severity failure (RPN > 200), you can implement a control like "preheat ramp rate ≤ 2°C/s" and verify it with a thermocouple profile every shift. This reduces the need for 100% AOI on that specific defect class.

## Key Commands / Configuration / Code

Below is a practical PFMEA worksheet snippet for the SMT reflow process. I use a structured format that maps directly to the AIAG-VDA PFMEA handbook. The key is to include process parameters and measurement methods.

```python
# pfmea_smt_reflow.py
# Sample PFMEA data structure for reflow soldering
# Each entry: (process_step, failure_mode, effect, cause, prevention_control, detection_control, severity, occurrence, detection)

pfmea_entries = [
    {
        "step": "Solder Paste Printing",
        "failure_mode": "Insufficient paste volume",
        "effect": "Open solder joint (head-in-pillow)",
        "cause": "Stencil clogged (aperture aspect ratio < 1.5)",
        "prevention": "Weekly stencil wipe with isopropyl alcohol; vacuum assist",
        "detection": "SPI (Solder Paste Inspection) at 100% — volume threshold < 50% of pad area",
        "sev": 8,
        "occ": 4,
        "det": 3,
        "rpn": 96
    },
    {
        "step": "Component Placement",
        "failure_mode": "Component tombstoning (0201 capacitor)",
        "effect": "Open circuit, latent failure under vibration",
        "cause": "Uneven pad wetting due to thermal gradient > 5°C across board",
        "prevention": "Preheat ramp rate ≤ 2°C/s; soak zone 150–180°C for 60–90s",
        "detection": "AOI after reflow — check component tilt > 10° from horizontal",
        "sev": 7,
        "occ": 5,
        "det": 4,
        "rpn": 140
    },
    {
        "step": "Reflow Soldering",
        "failure_mode": "Solder balling (residue under QFN)",
        "effect": "Short circuit between adjacent pins (0.4mm pitch)",
        "cause": "Peak temperature > 260°C or ramp rate > 3°C/s in liquidus zone",
        "prevention": "Thermocouple profile verification every 8 hours; nitrogen atmosphere (O2 < 1000 ppm)",
        "detection": "X-ray inspection on sample (every 10th board) — look for spherical voids > 25% of joint area",
        "sev": 9,
        "occ": 3,
        "det": 5,
        "rpn": 135
    },
    {
        "step": "AOI (Post-Reflow)",
        "failure_mode": "False pass on missing component (0201)",
        "effect": "Field failure, customer return",
        "cause": "AOI algorithm threshold too loose (component height tolerance > ±30%)",
        "prevention": "Golden board validation every shift; algorithm retrained after 3 false negatives",
        "detection": "Manual visual inspection on first article per batch",
        "sev": 10,
        "occ": 2,
        "det": 6,
        "rpn": 120
    }
]

# Calculate RPN and flag high-risk items
for entry in pfmea_entries:
    rpn = entry["sev"] * entry["occ"] * entry["det"]
    entry["rpn"] = rpn
    if rpn > 100:
        print(f"CRITICAL: {entry['failure_mode']} — RPN={rpn}. Action required.")
```

**Configuration example** for a reflow oven (Heller 1912 MKIII):

```text
; reflow_profile.cfg
; Zone temperatures for SAC305 solder paste
Zone1_Temp=150    ; Preheat zone 1 (°C)
Zone2_Temp=170    ; Preheat zone 2
Zone3_Temp=190    ; Soak zone
Zone4_Temp=220    ; Ramp zone
Zone5_Temp=245    ; Peak zone
Conveyor_Speed=90 ; cm/min
N2_Flow=25        ; L/min (target O2 < 1000 ppm)
```

## Common Pitfalls & Gotchas

1. **Ignoring paste rheology in stencil design.** Many teams set stencil thickness based on the smallest component (e.g., 0.1mm for 0201) but forget that larger components (e.g., QFNs) need more paste. This causes head-in-pillow defects. Always calculate the area ratio (aperture area / wall area) — it must be > 0.66 for good release. A PFMEA entry for "paste transfer efficiency < 80%" should trigger a stencil redesign.

2. **AOI as a crutch for process control.** I've seen lines where AOI catches 99% of defects, but the RPN for "missing component" is still high because the detection control is after reflow. The real prevention is a pick-and-place verification (e.g., vacuum sensor on nozzle, or component presence check after placement). Move detection earlier in the process to lower the detection rating.

3. **Thermal profile validation on the wrong board.** Engineers often profile a test coupon, not the actual production board. The mass difference (e.g., 8-layer vs 2-layer board) changes the thermal gradient by 10–15°C. Always profile the heaviest board in the product family. Your PFMEA should list "profile on production board" as a prevention control, not "profile on coupon."

## Try It Yourself

1. **Create a PFMEA for your own SMT line's solder paste printing step.** List at least three failure modes (e.g., insufficient paste, bridging, smearing). For each, assign severity (1–10), occurrence (based on your line's historical data), and detection (based on your SPI or AOI capability). Calculate RPN and identify the top two items.

2. **Run a thermal profile on your reflow oven using a production board.** Measure the ramp rate in the preheat zone (25–150°C) and the soak time (150–180°C). Compare against your PFMEA's prevention control thresholds. If the ramp rate exceeds 2.5°C/s, document it as a deviation and update your occurrence rating.

3. **Review your AOI false call rate for the last month.** If it's above 5%, create a PFMEA entry for "false call" with the cause being "algorithm threshold too tight." Propose a new detection control (e.g., "auto-teach on golden board every 100 boards") and recalculate the detection rating.

## Next Up: Linking DFMEA to PFMEA: Special Characteristics

Tomorrow, I'll explore how to trace a DFMEA's "special characteristics" (e.g., critical safety parameters, key product features) into your PFMEA. You'll learn how to map a design-level failure mode like "capacitor short circuit under voltage stress" to a process-level control like "100% X-ray inspection on BGA joints." This is where the FMEA family tree becomes a single, traceable system.
