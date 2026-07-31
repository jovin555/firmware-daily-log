---
title: "Day 20: Full Review & Project: DFMEA/PFMEA for an Embedded Sensor Module"
date: 2026-07-31
tags: ["til", "fmea", "review", "project"]
---

## What I Explored Today

Today I closed the loop on this 20-day FMEA journey by running a **combined DFMEA and PFMEA** on a real-world embedded sensor module — specifically a CAN-based ambient light sensor (ALS) with an I²C temperature sensor, an STM32L4 MCU, and a 3.3V LDO. Instead of treating DFMEA and PFMEA as separate documents, I merged them into a single risk register keyed by the **physical interface** (electrical, thermal, mechanical, communication). This forced me to trace failures across the design-to-manufacturing boundary. The result was a practical, actionable review that caught two real issues: a solder joint stress fracture from thermal cycling (PFMEA) and a missing brown-out reset strategy on the MCU (DFMEA). Here’s the full walkthrough.

## The Core Concept

The reason we do a **full review** at the end of an FMEA project is not to produce more paperwork — it’s to find the **cross-domain failures** that single-domain analyses miss. A DFMEA might say "MCU resets unexpectedly" with a high severity, but it won't tell you that the root cause is a **void in the QFN thermal pad** caused by a reflow profile issue. That's a PFMEA failure mode. Conversely, a PFMEA might say "sensor misaligned during pick-and-place," but the design mitigation (alignment pins) lives in the DFMEA.

When you merge them, you get a **single risk priority number (RPN)** per physical interface. This lets you prioritize actions based on the actual physics of the system, not the departmental silo. For embedded modules, the critical interfaces are:

1. **Electrical**: power supply, signal integrity, ESD.
2. **Thermal**: junction temperature, solder joint fatigue, PCB warpage.
3. **Mechanical**: mounting stress, connector retention, vibration.
4. **Communication**: protocol timing, bus contention, CRC errors.

The key insight: **a failure mode is only fully understood when you know both the design cause and the process cause.** Today's project demonstrates exactly that.

## Key Commands / Configuration / Code

I used a Python script to generate the merged risk register from two CSV files (DFMEA and PFMEA). Here's the core logic:

```python
# merge_fmea.py — merges DFMEA and PFMEA by physical interface
import csv

def load_fmea(path, fmea_type):
    rows = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            r['type'] = fmea_type
            rows.append(r)
    return rows

def merge_by_interface(dfmea_rows, pfmea_rows):
    # Key: (interface, failure_mode)
    merged = {}
    for row in dfmea_rows + pfmea_rows:
        key = (row['interface'], row['failure_mode'])
        if key not in merged:
            merged[key] = {
                'interface': row['interface'],
                'failure_mode': row['failure_mode'],
                'dfmea_sev': 0, 'dfmea_occ': 0, 'dfmea_det': 0,
                'pfmea_sev': 0, 'pfmea_occ': 0, 'pfmea_det': 0,
            }
        # Assign severity/occurrence/detection based on type
        if row['type'] == 'DFMEA':
            merged[key]['dfmea_sev'] = int(row['severity'])
            merged[key]['dfmea_occ'] = int(row['occurrence'])
            merged[key]['dfmea_det'] = int(row['detection'])
        else:
            merged[key]['pfmea_sev'] = int(row['severity'])
            merged[key]['pfmea_occ'] = int(row['occurrence'])
            merged[key]['pfmea_det'] = int(row['detection'])
    return merged

# Example usage
dfmea = load_fmea('dfmea_sensor.csv', 'DFMEA')
pfmea = load_fmea('pfmea_sensor.csv', 'PFMEA')
merged = merge_by_interface(dfmea, pfmea)

# Calculate combined RPN: max(sev) * max(occ) * max(det)
for key, data in merged.items():
    sev = max(data['dfmea_sev'], data['pfmea_sev'])
    occ = max(data['dfmea_occ'], data['pfmea_occ'])
    det = max(data['dfmea_det'], data['pfmea_det'])
    data['rpn'] = sev * occ * det
    print(f"{data['interface']:12s} | {data['failure_mode']:30s} | RPN={data['rpn']}")
```

For the actual hardware review, I used the STM32CubeMX-generated `main.c` to verify the brown-out reset (BOR) configuration:

```c
/* main.c — BOR level set to Level 2 (2.7V–2.9V) */
void SystemClock_Config(void)
{
    /* ... clock config ... */
    /* Ensure BOR is set before any peripheral init */
    HAL_PWR_EnableBORLevel(PWR_BOR_LEVEL2);  // 2.7V–2.9V threshold
    /* ... rest of init ... */
}
```

And for the PFMEA side, I checked the reflow profile against the solder paste datasheet:

```bash
# Check reflow profile against solder paste spec (SAC305)
# Peak temp: 245°C ± 5°C, Time above liquidus (217°C): 60-90s
# Use a thermocouple datalogger to verify
python3 -c "
peak = 246.2  # measured peak temp
tal = 72.0    # time above liquidus in seconds
assert 240 <= peak <= 250, 'Peak temp out of spec'
assert 60 <= tal <= 90, 'Time above liquidus out of spec'
print('Reflow profile OK')
"
```

## Common Pitfalls & Gotchas

1. **Treating DFMEA and PFMEA as independent documents.** This is the biggest mistake. A design change (e.g., moving a decoupling cap) affects the assembly process (solder paste stencil aperture). If you don't cross-reference, you'll miss the interaction. Use the physical interface as your join key.

2. **Using the same RPN threshold for both.** DFMEA severity is often higher (system-level impact), while PFMEA occurrence is higher (process variability). If you use a single RPN cutoff (e.g., >100), you'll either over-engineer the process or under-protect the design. Use **max(sev) * max(occ) * max(det)** as I did above — it captures the worst case across both domains.

3. **Forgetting that detection is different.** In DFMEA, detection is "can the design detect the failure?" (e.g., BIST). In PFMEA, detection is "can the process detect the failure?" (e.g., AOI). These are fundamentally different. When merging, don't average them — take the max, because the failure is only caught if *either* the design or the process catches it.

## Try It Yourself

1. **Take your last embedded project** and list the top 5 failure modes from your DFMEA. For each one, ask: "What manufacturing step could cause this?" Write a one-line PFMEA entry for each. You'll likely find at least one you missed.

2. **Write a Python script** (or modify mine) to merge your DFMEA and PFMEA CSVs. Use `max()` for severity, occurrence, and detection. Print the top 10 RPN items. Are any of them cross-domain failures you hadn't considered?

3. **Check your MCU's BOR configuration** in your current firmware. If you're using an STM32, verify the `PWR_BOR_LEVEL` setting matches your LDO output voltage. If you're using a different MCU, find the equivalent register. Document the threshold in your DFMEA as a design control.

## Next Up

Tomorrow, Day 21: **Full Review — The Complete FMEA Audit Checklist**. I'll walk through a 30-minute audit you can run on any existing FMEA document to catch common errors, missing fields, and stale risk assessments. We'll also cover how to present the final merged report to management without drowning them in spreadsheets.
