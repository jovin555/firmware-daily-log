---
title: "Day 04: ISO 14971 Risk Management & Where DFMEA Fits"
date: 2026-10-14
tags: ["til", "medical-iot-dfmea", "iso14971", "risk-management"]
---

# Day 04: ISO 14971 Risk Management & Where DFMEA Fits

## What I Explored Today

Today I stopped treating DFMEA as the center of the universe and read ISO 14971:2019 end-to-end as the *parent* process that DFMEA lives inside. The mental shift: DFMEA is a bottom-up, component-level technique for finding failure modes; ISO 14971 is a top-down, product-level framework that starts with patient harm and works backward. They are not competitors — DFMEA is one of several risk analysis tools you invoke *inside* the ISO 14971 lifecycle. I mapped our wearable SpO₂ monitor's risk file against the standard's clauses and found two gaps: no explicit production/post-production feedback loop, and risk acceptability criteria that weren't documented before analysis began (a classic audit finding).

## The Core Concept

ISO 14971 defines risk as the combination of the **probability of occurrence of harm** and the **severity of that harm**. Note the word *harm* — injury to people or damage to property/environment. This is deliberately different from DFMEA's "failure mode," which is a technical deviation (e.g., "I²C bus lockup"). A failure mode only becomes a risk when you trace it to a hazardous situation and then to harm.

The standard's process is a loop, not a document:

1. **Define scope and risk acceptability criteria** *before* analysis. You must state, in writing, what risk is acceptable. Common approach: a 5×5 severity/probability matrix with an "ALARP" (As Low As Reasonably Practicable) region.
2. **Risk analysis** — identify hazards, estimate severity and probability. This is where DFMEA, FTA (Fault Tree Analysis), and HAZOP feed in.
3. **Risk evaluation** — compare against your criteria.
4. **Risk control** — apply the hierarchy: (a) inherent safety by design, (b) protective measures, (c) information for safety (labels/manuals). DFMEA drives option (a) and (b).
5. **Residual risk evaluation** — after controls, is the remaining risk acceptable? Include benefit-risk analysis if not.
6. **Risk management report** and **production/post-production monitoring**.

The "why" is regulatory: FDA 21 CFR 820.30(g) and EU MDR Annex I require a documented risk management process. An auditor will ask: *show me the traceability from a hazard to a design control to a verification test.* DFMEA rows are the raw material for that traceability matrix.

## Key Commands / Configuration / Code

I keep the risk file as structured YAML so it can be linted and traced in CI. Here's a minimal schema fragment for one hazard:

```yaml
# risk_file.yaml — ISO 14971 hazard traceability
hazard:
  id: HAZ-007
  description: "SpO2 sensor over-heats and contacts skin"
  hazardous_situation: "LED drive current exceeds safe limit during continuous mode"
  foreseeable_sequence: "Firmware bug sets PWM duty > 60% -> LED junction temp rises -> enclosure > 43C"
  harm: "First-degree skin burn"
  severity: 4          # 1-5, per ISO 14971 Annex C guidance
  probability: 2       # 1-5
  risk_index: 8        # severity * probability
  # Link to the DFMEA line item that analyzes the technical cause
  dfmea_ref: "DFMEA-ROW-042"
  risk_control:
    - type: "inherent_safety_by_design"   # hierarchy step (a)
      action: "Hardware current-limit resistor R17 sets max LED current to 20mA"
      verification: "TEST-ELEC-019: measure LED current at max PWM"
    - type: "protective_measure"          # hierarchy step (b)
      action: "Firmware watchdog clamps PWM duty to 40% if temp sensor > 40C"
      verification: "TEST-FW-033: fault injection on NTC reading"
  residual_severity: 4
  residual_probability: 1
  residual_risk_index: 4
  acceptable: true       # per pre-defined criteria
```

A quick CI check with `yq` to enforce that every hazard has at least one control and a verification test:

```bash
# Fail the build if any hazard lacks a risk_control or verification
yq -e '.hazards[] | select(.risk_control == null or (.risk_control | length) == 0)' risk_file.yaml \
  && echo "FAIL: hazard without control" && exit 1 || echo "OK: all hazards controlled"

# Verify residual risk index never exceeds the acceptability threshold (e.g. 8)
yq -e '.hazards[] | select(.residual_risk_index > 8)' risk_file.yaml \
  && echo "FAIL: residual risk above threshold" && exit 1 || echo "OK: residuals acceptable"
```

For the DFMEA side, the link is the `dfmea_ref`. In our DFMEA spreadsheet (or `dfmea.csv`), row 042 would carry the failure mode "PWM duty register corrupted" with its own S/O/D RPN — but note the RPN is *not* the ISO 14971 risk index. Keep them separate; auditors conflate them and it causes confusion.

## Common Pitfalls & Gotchas

1. **Defining acceptability criteria after the analysis.** If you pick your severity/probability thresholds once you see the numbers, the whole file is invalid. Write and approve the criteria first, version-control them, and reference the revision in every hazard.
2. **Treating RPN as a risk index.** DFMEA's Risk Priority Number (Severity × Occurrence × Detection) is a *prioritization* tool, not a measure of patient risk. Detection doesn't reduce harm — it only reduces the chance the failure escapes. ISO 14971 cares about harm probability, not detection. Don't copy RPN into your residual risk column.
3. **Skipping the production/post-production clause (Clause 10).** The risk file isn't done at design freeze. You need a feedback mechanism — complaint handling, CAPA, trending — that feeds back into risk analysis. Our audit gap was exactly this: no documented trigger for re-evaluating risk when field complaints cross a threshold.

## Try It Yourself

1. **Write your acceptability matrix first.** Before touching any hazard, define a 5×5 severity/probability grid and mark which cells are acceptable, ALARP, or unacceptable. Commit it to git with a version tag. This is your Clause 4.4 artifact.
2. **Trace one hazard end-to-end.** Pick a real failure mode from your device (e.g., "BLE pairing drops during a critical alarm"). Write the YAML block above for it, then verify every `risk_control` has a named verification test. If a control has no test, you have a gap.
3. **Run the `yq` lint in CI.** Add the two checks to your pipeline and deliberately break one hazard (remove its control) to confirm the build fails. A risk file that can't fail a build won't survive an audit.

## Next Up

Tomorrow: **Medical IoT System Architecture: Sensor, MCU, Radio, Power, App & Cloud** — how the six subsystems partition, where the risk boundaries sit, and why your DFMEA scope has to match your architecture diagram.
