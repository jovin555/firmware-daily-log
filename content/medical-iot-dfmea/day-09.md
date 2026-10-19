---
title: "Day 09: Severity Scales for Medical Devices: Patient Harm-Based Ratings"
date: 2026-10-19
tags: ["til", "medical-iot-dfmea", "severity", "patient-harm"]
---

## What I Explored Today

Today I dug into the severity (S) dimension of our DFMEA for the infusion pump controller. Severity is the one rating in the RPN that you *cannot* reduce through design controls — it's a property of the failure effect, not the failure cause. That distinction matters more in medical devices than in automotive or industrial DFMEA, because the "effect" is measured against a human being, not a machine. I spent the day mapping our failure modes onto a harm-based scale anchored to ISO 14971 harm categories, and reconciling it with the AIAG-VDA 1–10 scale our contract manufacturer's PFMEA already uses so the two documents don't contradict each other.

## The Core Concept

In classic AIAG DFMEA, severity answers: *"If this failure mode occurs, how bad is the effect on the end user?"* For a car, a severity 10 is "failure could cause death or injury without warning." For a medical device, that same number has to be traceable to a **harm** — physical injury or damage to health — per ISO 14971:2019. The trap is treating severity as a property of the *component*. It isn't. Severity is a property of the **failure effect at the patient**, and the same component failure can have wildly different severities depending on the use context.

Consider a stuck-high ADC reading on our pump's pressure sensor. If the firmware treats it as a valid reading, the pump may over-infuse → overdose → serious injury (S=9 or 10). If the same stuck reading is caught by a plausibility check and triggers a safe stop, the effect is "therapy interruption, clinician restarts" → negligible harm (S=2 or 3). The *failure mode* is identical; the *severity* is not. This is why severity must be assessed on the **effect after existing design controls**, and why you re-rate severity whenever you add a detection or mitigation that changes the end effect — not just the detection rating.

The practical consequence: build your severity scale around **harm severity categories**, then map those to numbers. I use a 1–10 scale anchored to ISO 14971 harm severity:

| S | Harm category | Medical example |
|---|---|---|
| 10 | Catastrophic — death | Overdose of high-alert drug, no alarm |
| 9 | Critical — permanent serious injury | Air embolism, tissue necrosis |
| 8 | Serious injury, reversible w/ intervention | Under-infusion of vasopressor |
| 7 | Moderate injury, medical intervention required | Minor infiltration, extravasation |
| 5–6 | Minor injury / temporary discomfort | Alarm fatigue, nuisance occlusion alarm |
| 3–4 | No injury, degraded therapy | Display lag, delayed log write |
| 1–2 | No effect on patient | Cosmetic UI glitch, log formatting |

Notice S=9 vs S=10 is a real line: "could kill" vs "will seriously injure." Regulators and your risk file care about that line because it drives whether you need independent redundant protection.

## Key Commands / Configuration / Code

I keep the severity scale as machine-readable YAML so the DFMEA worksheet, the risk management file, and our automated traceability check all read from one source of truth.

```yaml
# severity_scale.yaml — single source of truth for DFMEA + ISO 14971 risk file
scale_version: "2026.10"
anchors:
  - id: S10
    label: Catastrophic
    harm: death
    iso14971_severity: catastrophic
    requires_independent_protection: true   # drives architecture review gate
  - id: S9
    label: Critical
    harm: permanent_serious_injury
    iso14971_severity: critical
    requires_independent_protection: true
  - id: S8
    label: Serious
    harm: serious_injury_reversible
    iso14971_severity: serious
    requires_independent_protection: false
  - id: S7
    label: Moderate
    harm: injury_requires_intervention
    iso14971_severity: moderate
  - id: S5
    label: Minor
    harm: temporary_discomfort
    iso14971_severity: minor
  - id: S3
    label: Negligible
    harm: no_injury_degraded_therapy
    iso14971_severity: negligible
  - id: S1
    label: None
    harm: no_patient_effect
    iso14971_severity: none
```

A small validator that fails CI if any DFMEA row references an undefined severity anchor or claims S≥9 without a linked independent protection:

```python
# validate_severity.py — run in CI on every DFMEA change
import yaml, sys

with open("severity_scale.yaml") as f:
    scale = {a["id"]: a for a in yaml.safe_load(f)["anchors"]}

with open("dfmea_rows.yaml") as f:
    rows = yaml.safe_load(f)["rows"]

errors = []
for r in rows:
    anchor = scale.get(r["severity_id"])
    if anchor is None:
        errors.append(f"{r['id']}: undefined severity {r['severity_id']}")
        continue
    if anchor["requires_independent_protection"] and not r.get("independent_protection"):
        errors.append(
            f"{r['id']}: {r['severity_id']} requires independent protection, none linked"
        )

if errors:
    print("\n".join(errors)); sys.exit(1)
print(f"OK: {len(rows)} rows validated against scale {scale}")
```

Example row that passes only because the protection is declared:

```yaml
rows:
  - id: FM-014
    failure_mode: "Pressure sensor stuck-high, treated as valid"
    effect: "Over-infusion -> overdose"
    severity_id: S10
    independent_protection: "FW plausibility check + independent HW comparator (IEC 62304 Class C)"
```

## Common Pitfalls & Gotchas

1. **Rating severity on the cause, not the effect.** Engineers instinctively write "S=7 because it's a cheap sensor." Severity is the *patient harm* if the effect reaches the patient. A cheap sensor that causes an undetected overdose is still S=10. Rate the effect, then let occurrence and detection carry the component-quality story.

2. **Forgetting to re-rate after adding a control.** When you add a plausibility check that converts "overdose" into "safe stop + alarm," the *effect* changed, so severity must drop (S10 → S3). Teams often leave S=10 and only improve detection, which inflates RPN and hides that the residual risk is actually low. Re-baseline severity whenever the end effect changes.

3. **Scale drift between DFMEA and PFMEA.** Your design team uses harm-based S; the contract manufacturer's PFMEA uses AIAG-VDA S. If a manufacturing failure mode maps to a design effect, the two numbers must reconcile through a documented mapping table, or your risk file will show contradictory severities for the same harm. Pin both to the same anchor IDs.

## Try It Yourself

1. **Build the anchor table.** Take three failure modes from your current device and write the *effect at the patient* for each, then assign an S value using the ISO 14971 harm categories above. Note where two failure modes share a component but land on different severities.

2. **Run the validator.** Drop `severity_scale.yaml` and `dfmea_rows.yaml` into a repo, add `validate_severity.py` to a pre-commit hook, and confirm it fails on a row with `severity_id: S10` and no `independent_protection`.

3. **Re-rate exercise.** Pick one S≥8 row, add a hypothetical independent protection, and rewrite the effect statement. Show the new severity and explain in one sentence why the number moved.

## Next up

Tomorrow: **Occurrence & Detection in Medical DFMEA: Design Verification as Detection** — how to rate O and D when your "detection" is a design verification activity rather than an in-line control, and why D=10 in a medical DFMEA usually means "we found it in the field."
