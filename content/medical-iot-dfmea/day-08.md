---
title: "Day 08: Hazards, Hazardous Situations & Harm: Mapping DFMEA Effects to ISO 14971"
date: 2026-10-18
tags: ["til", "medical-iot-dfmea", "hazard-analysis", "harm"]
---

## What I Explored Today

Today I tackled the most common failure mode in risk management documentation: teams writing DFMEA "Effects" that describe a *failure* instead of a *harm*, then wondering why their ISO 14971 risk file gets shredded in audit. The two standards use different vocabularies on purpose. DFMEA (per AIAG-VDA) talks about Failure Mode → Effect → Severity. ISO 14971 talks about Hazard → Hazardous Situation → Harm. If you don't explicitly trace one to the other, you end up with a risk file that says "loss of BLE connection" as an effect and no defensible link to "patient does not receive alarm." I spent the day building a traceability matrix that bridges the two, and wiring it into our requirements tooling so the linkage is machine-checkable rather than a Word table someone updates by hand.

## The Core Concept

The distinction matters because the two frameworks answer different questions. DFMEA asks: *if this component fails, what happens to the device function?* ISO 14971 asks: *how does the device, in its use environment, expose a person to harm?*

A **hazard** is a potential source of harm — it's a property of the device or its context (e.g., "electrical energy," "delayed alarm delivery"). A **hazardous situation** is when a person is exposed to the hazard (e.g., "clinician relies on an alarm that has not fired"). **Harm** is actual injury or damage to health (e.g., "delayed treatment of hypoxia"). The chain is: *hazard → hazardous situation → (sequence of events) → harm*.

DFMEA effects sit at the *device function* layer. A single DFMEA effect ("alarm not annunciated") can map to multiple hazardous situations depending on use context (bedside monitor vs. home wearable vs. nurse-call integration). Conversely, one hazardous situation can be reached via many failure modes across many DFMEAs. That many-to-many relationship is exactly why you need an explicit mapping artifact — and why auditors ask for it.

The practical rule I now enforce: **a DFMEA effect is never a harm.** If your effect column contains the word "patient," you've probably crossed the line into ISO 14971 territory and need to split the row.

## Key Commands / Configuration / Code

I keep the mapping in a YAML file that's version-controlled alongside the DFMEA export. It's the single source of truth for the traceability matrix.

```yaml
# risk-linkage.yaml — maps DFMEA effects to ISO 14971 hazard chain
# Each effect_id must exist in the DFMEA export (dfmea-export.csv)
# Each hazard_id must exist in the ISO 14971 hazard register
linkages:
  - effect_id: "DFMEA-ALM-014"        # Effect: "Alarm not annunciated within 10s"
    effect_text: "Alarm not annunciated within 10s"
    hazardous_situations:
      - hs_id: "HS-003"
        hs_text: "Clinician unaware of SpO2 desaturation"
        hazard_id: "HZ-ELEC-02"        # Hazard: loss of alarm signal
        foreseeable_sequence: "Sensor reads valid but alarm path suppressed by firmware state"
        harms:
          - harm_id: "HARM-001"
            harm_text: "Delayed treatment of hypoxia"
            severity_ref: "SEV-4"      # links to severity scale (tomorrow's topic)
      - hs_id: "HS-007"
        hs_text: "Remote nurse-call system not triggered"
        hazard_id: "HZ-ELEC-02"
        foreseeable_sequence: "Gateway drops alarm packet during BLE reconnect"
        harms:
          - harm_id: "HARM-002"
            harm_text: "Missed escalation to on-call staff"
            severity_ref: "SEV-3"
```

A small validator script catches the most common audit findings — orphaned effects and effects that leak harm language:

```python
#!/usr/bin/env python3
# validate_linkage.py — run in CI on every PR touching risk-linkage.yaml
import csv, sys, yaml

with open("risk-linkage.yaml") as f:
    linkage = yaml.safe_load(f)

# Load DFMEA effects from the tool export
with open("dfmea-export.csv") as f:
    dfmea_effects = {row["effect_id"]: row["effect_text"] for row in csv.DictReader(f)}

errors = []
for link in linkage["linkages"]:
    eid = link["effect_id"]
    if eid not in dfmea_effects:
        errors.append(f"ORPHAN: {eid} not found in DFMEA export")
        continue
    # Guard against harm language leaking into DFMEA effects
    if any(w in link["effect_text"].lower() for w in ("patient", "injury", "harm")):
        errors.append(f"HARM-LEAK: {eid} effect describes harm, not device function")
    if not link.get("hazardous_situations"):
        errors.append(f"UNMAPPED: {eid} has no hazardous situation")

if errors:
    print("\n".join(errors)); sys.exit(1)
print(f"OK: {len(linkage['linkages'])} effects mapped")
```

The CI job is a one-liner in the pipeline:

```bash
# Fail the build if the risk linkage is broken
python3 validate_linkage.py || exit 1
```

## Common Pitfalls & Gotchas

**1. Treating the DFMEA effect as the harm.** "Patient receives no therapy" is a harm, not a device effect. The device effect is "therapy output disabled." Auditors will flag this because it collapses two required analyses into one and hides the hazardous situation (the *exposure* step) entirely.

**2. Forgetting the foreseeable sequence of events.** ISO 14971 requires you to describe *how* the hazardous situation arises. A mapping that jumps straight from hazard to harm skips the sequence — and that's where your risk controls actually live (e.g., a watchdog that detects the suppressed alarm state). No sequence, no place to hang the control.

**3. One-to-one mapping by habit.** Engineers love tidy 1:1 tables. Real risk is many-to-many. If your matrix has exactly one hazardous situation per effect, you probably haven't thought about use context — the same firmware bug is a different risk in a hospital vs. a home.

## Try It Yourself

1. **Export your DFMEA effects** to CSV and grep for harm language: `grep -iE "patient|injury|harm|death" dfmea-export.csv`. Every hit is a candidate for splitting into effect + hazardous situation.
2. **Build a minimal `risk-linkage.yaml`** for your three highest-severity effects and run the validator above. Fix any `HARM-LEAK` or `UNMAPPED` errors.
3. **Pick one effect** and write out *two* distinct hazardous situations it could produce in different use environments. If you can only find one, revisit your intended-use statement.

## Next up

Tomorrow: **Severity Scales for Medical Devices: Patient Harm-Based Ratings** — how to build a severity scale that's anchored to patient harm rather than device function, and why the `severity_ref` field above needs to point at *that* scale, not your DFMEA's 1–10.
