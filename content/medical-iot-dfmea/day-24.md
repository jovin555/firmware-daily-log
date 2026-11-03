---
title: "Day 24: Post-Market Surveillance: Complaints, CAPA & Keeping the DFMEA Alive"
date: 2026-11-03
tags: ["til", "medical-iot-dfmea", "post-market", "capa"]
---

# Day 24: Post-Market Surveillance: Complaints, CAPA & Keeping the DFMEA Alive

## What I Explored Today

Today I closed the loop on the DFMEA lifecycle by looking at what happens *after* the device ships. A DFMEA that gets signed off at design freeze and never touched again is a compliance artifact, not a risk management tool — and ISO 14971 explicitly requires that risk management be an ongoing process. I spent the day wiring up the feedback path: how complaint data from the field (support tickets, RMA logs, app telemetry) flows into a CAPA system, and how a CAPA that traces back to a failure mode should trigger a DFMEA revision. I also looked at the practical mechanics of post-market surveillance (PMS) under EU MDR Article 83–86 and 21 CFR 803 (MDR reporting), and how to keep the DFMEA's RPN/AP scores honest as field data accumulates.

## The Core Concept

The DFMEA is a *prediction*. Post-market surveillance is the *measurement*. The whole point of keeping the DFMEA alive is to compare predicted severity/occurrence/detection against observed reality and correct the model when it's wrong.

Two things drive a DFMEA revision:

1. **A new failure mode appears in the field** that wasn't in the DFMEA at all. This is the worst case — it means your design review missed something. The CAPA must add the failure mode, re-score it, and evaluate whether design controls (verification, labeling, IFU) need to change.
2. **An existing failure mode occurs more (or less) often than predicted.** Occurrence (O) is the score most directly informed by field data. If you predicted O=3 (occasional) but the complaint rate says otherwise, you update O and re-run the Action Priority (AIAG-VDA) or RPN.

The key discipline: **every CAPA gets a DFMEA impact assessment**. Not every CAPA changes the DFMEA, but every CAPA must be *evaluated* against it. That evaluation is the audit trail that proves your risk file is a living document. Under MDR Annex I and 21 CFR 820.30(g), a stale risk file is a finding waiting to happen.

The data plumbing matters. Complaint intake → triage → CAPA → DFMEA is a chain, and if the complaint record doesn't carry a device identifier and firmware version, you can't correlate field failures to a design revision. That's why UDI and firmware version must be captured at complaint intake.

## Key Commands / Configuration / Code

A minimal complaint-triage schema that carries the fields you need to trace back to a DFMEA line item. This is the kind of structure you'd put in a lightweight PMS database or a JSON intake form:

```json
{
  "complaint_id": "CMP-2026-0417",
  "received_date": "2026-11-02",
  "device_udi": "(01)00812345678903(21)SN-0042",
  "firmware_version": "2.3.1",
  "hardware_rev": "C",
  "complaint_category": "loss_of_connection",
  "description": "BLE link drops after ~40 min during overnight monitoring",
  "patient_harm": "none",
  "dfmea_ref": {
    "item": "BLE radio / connection management",
    "failure_mode_id": "FM-014",
    "predicted_severity": 7,
    "predicted_occurrence": 3,
    "predicted_detection": 4
  },
  "capa_required": true,
  "capa_id": "CAPA-2026-0088"
}
```

A small script to flag when observed complaint rate exceeds the DFMEA's predicted occurrence band — this is the trigger for a re-score. Occurrence bands in AIAG-VDA map roughly to ppm ranges; here I use a simplified threshold:

```python
# occurrence_trigger.py
# Flag DFMEA lines where field complaint rate exceeds predicted occurrence band.
# Simplified: O=1..10 maps to a ppm ceiling; adjust to your risk file's scale.

OCCURRENCE_PPM_CEILING = {
    1: 10, 2: 100, 3: 1000, 4: 5000, 5: 20000,
    6: 50000, 7: 100000, 8: 250000, 9: 500000, 10: 1_000_000,
}

def check_line(fm_id, predicted_o, units_shipped, complaints):
    if units_shipped == 0:
        return None
    ppm = (complaints / units_shipped) * 1_000_000
    ceiling = OCCURRENCE_PPM_CEILING[predicted_o]
    if ppm > ceiling:
        return {
            "fm_id": fm_id,
            "predicted_o": predicted_o,
            "observed_ppm": round(ppm, 1),
            "ceiling_ppm": ceiling,
            "action": "REVIEW_OCCURRENCE_SCORE",
        }
    return None

# Example: FM-014 predicted O=3 (ceiling 1000 ppm), 12 complaints / 8,000 units
print(check_line("FM-014", 3, 8000, 12))
# -> observed 1500 ppm > 1000 ppm ceiling -> triggers re-score
```

And the DFMEA revision record — every re-score needs a rationale and a link to the CAPA, or the auditor will ask "why did O change from 3 to 5?":

```yaml
# dfmea_revision_log.yaml (excerpt)
revision: 4
date: 2026-11-03
trigger: CAPA-2026-0088
changes:
  - fm_id: FM-014
    field: occurrence
    old: 3
    new: 5
    rationale: >
      Observed 1500 ppm over 8,000 shipped units (Q3-Q4 2026),
      exceeding O=3 band. Root cause: BLE supervision timeout too
      short for low-power sleep transitions. Design change DCR-221
      raises timeout and adds reconnect backoff.
    verification: V&V-2026-0312
```

## Common Pitfalls & Gotchas

- **Complaint records without firmware version.** If your intake form doesn't capture FW rev and hardware rev, you cannot tell whether a spike in "connection drops" is a new regression or the same old failure mode on old units. UDI + FW version at intake is non-negotiable for an IoT device.
- **Treating CAPA closure as the end.** A CAPA that fixes the process but never touches the DFMEA leaves the risk file stale. Build a mandatory "DFMEA impact assessment" field into the CAPA template with a yes/no and a justification — auditors look for exactly this.
- **Re-scoring occurrence without re-checking severity.** Field data rarely changes severity, but a new failure mode discovered in the field can have a *higher* severity than anything predicted (e.g., a connection drop that delays an alarm). Re-evaluate S independently; don't just bump O.

## Try It Yourself

1. **Add a DFMEA impact field to your CAPA template.** Create a required field `dfmea_impact_assessment` with values `none | rescore | new_failure_mode` and a free-text justification. If you don't have a CAPA system, mock it in a spreadsheet with a data-validation dropdown.
2. **Run the occurrence trigger on real or synthetic data.** Take one DFMEA line, plug in your shipped-unit count and complaint count for the last quarter, and run `occurrence_trigger.py`. Does it flag? If yes, draft the revision-log entry with a rationale.
3. **Audit one complaint record end-to-end.** Pick a recent complaint and trace it: does it carry UDI, FW version, and a DFMEA reference? If any are missing, that's a gap in your PMS data model — fix the intake form.

## Next Up

Tomorrow: **Full Review & Project — DFMEA for a BLE Wearable Patient Monitor.** We'll pull the whole series together into one end-to-end DFMEA for a realistic BLE wearable (SpO₂ + HR + fall detection), from boundary diagram through structure/function analysis, failure analysis, risk scoring, and the post-market feedback loop we built today — a complete worked example you can adapt to your own device.
