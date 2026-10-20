---
title: "Day 10: Occurrence & Detection in Medical DFMEA: Design Verification as Detection"
date: 2026-10-20
tags: ["til", "medical-iot-dfmea", "occurrence", "detection"]
---

## What I Explored Today

Today I dug into the two DFMEA rating columns that engineers most often fill in by gut feel: **Occurrence** and **Detection**. For a wearable SpO2/ECG patch we're designing, I rebuilt the rating rationale from scratch using AIAG-VDA logic, then mapped our design verification (DV) test suite directly onto the Detection scale. The insight that stuck: Detection in DFMEA is not "how good is our firmware at catching this" — it's "how likely is the *design control* to catch the failure mode *before* the device reaches the patient." That reframing changes which DV tests actually count as detection controls and which are just box-checking.

## The Core Concept

Occurrence answers: *given this design, how often will this failure mode occur?* It is a property of the design, not the manufacturing line (that's PFMEA). In AIAG-VDA, Occurrence is rated 1–10 based on prevention controls already baked into the design — derating, redundancy, tolerance stackup, proven-in-use components. If you have no prevention control, you cannot claim a low Occurrence no matter how "simple" the circuit looks.

Detection answers: *if the failure mode occurs, how likely is a design control to detect it before the product ships or before harm occurs?* This is where teams cheat. They list "firmware watchdog" as a detection control for a sensor failure when the watchdog only catches MCU lockups, not a drifted photodiode. The rating must reflect the *specific* failure mode.

The key mental model: **Detection rating is inversely proportional to the maturity and specificity of your design verification.** A DV test that directly exercises the failure mode and has a pass/fail criterion tied to a requirement is a strong detection control (rating 2–4). A test that "generally validates the subsystem" is weak (rating 6–8). No test = 10.

For medical devices under ISO 14971, this matters because Detection feeds your risk priority and, more importantly, your **risk control verification**. If you claim Detection = 3, you must be able to point to a DV protocol, a requirement ID, and a traceability link. An auditor will ask for exactly that.

## Key Commands / Configuration / Code

I keep the DFMEA as structured data so ratings and their justifications stay traceable. Here's a trimmed YAML schema and a Python check that flags any Detection rating not backed by a verification record:

```yaml
# dfmea_spo2.yaml — one row of the SpO2 subsystem DFMEA
failure_mode:
  id: FM-SPO2-014
  description: "Photodiode responsivity drift causes SpO2 reading error > 3%"
  effect: "Clinician acts on inaccurate oxygen saturation"
  severity: 8                      # harm potential, fixed by effect
  occurrence:
    rating: 4                      # derated LED drive + calibrated photodiode
    prevention_controls:
      - "LED current limited to 80% of datasheet max (derating)"
      - "Photodiode selected from proven-in-use supplier lot"
  detection:
    rating: 3                      # DV test directly exercises drift
    detection_controls:
      - control_id: DV-SPO2-07
        type: design_verification
        requirement: REQ-SPO2-021  # accuracy over temp & aging
        method: "Calibration drift test, 0-40C, 500h accelerated aging"
        pass_criterion: "SpO2 error <= 3% vs reference oximeter"
```

```python
# dfmea_check.py — enforce that low Detection ratings have DV evidence
import yaml

def validate_detection(dfmea_path):
    with open(dfmea_path) as f:
        rows = yaml.safe_load(f)["rows"]

    problems = []
    for r in rows:
        det = r["detection"]["rating"]
        controls = r["detection"].get("detection_controls", [])
        # Rule: Detection <= 4 requires at least one DV control with a requirement
        if det <= 4:
            has_dv = any(
                c.get("type") == "design_verification" and c.get("requirement")
                for c in controls
            )
            if not has_dv:
                problems.append(
                    f"{r['failure_mode']['id']}: Detection={det} "
                    f"but no DV control with requirement trace"
                )
    return problems

if __name__ == "__main__":
    issues = validate_detection("dfmea_spo2.yaml")
    for i in issues:
        print("FLAG:", i)
    print(f"{len(issues)} detection rating(s) need justification")
```

Running this against our draft flagged four rows where someone had written "Detection: 3 — firmware monitors sensor" without a DV protocol or requirement ID. Exactly the kind of gap an ISO 14971 reviewer loves to find.

## Common Pitfalls & Gotchas

1. **Confusing detection controls with prevention controls.** A watchdog timer *prevents* a lockup from persisting; it doesn't *detect* a drifted photodiode. If you list a prevention control in the Detection column, your rating is inflated and your risk file is inconsistent. Keep the two columns' control lists strictly separate.

2. **Rating Detection by "how good our team is" instead of by the control.** Detection is a property of the *specific control for the specific failure mode*, not of your QA culture. A brilliant team with no test for this failure mode still gets Detection = 10.

3. **Forgetting that DV tests must trace to a requirement.** A test with no requirement ID and no pass criterion is not a detection control — it's exploration. In the YAML above, `requirement: REQ-SPO2-021` is what makes `DV-SPO2-07` count. Auditors will trace Detection → control → requirement → test result; break any link and the rating collapses.

## Try It Yourself

1. **Audit one DFMEA row.** Take any failure mode from your current project, list its Detection controls, and for each ask: does it have a requirement ID and a pass criterion? Downgrade the Detection rating for any control that fails this test, then re-run the Python validator above.

2. **Map your DV suite to Detection.** Export your design verification test list to CSV, add a column `dfmea_failure_mode_id`, and tag each test to the failure mode(s) it detects. Any failure mode with Detection ≤ 4 and no tagged test is a traceability gap — fix it before your next design review.

3. **Split a prevention/detection pair.** Pick a failure mode where you currently list one control in both columns. Rewrite it as two distinct controls (one prevention, one detection) and confirm the Detection control actually exercises the failure mode rather than the prevention mechanism.

## Next Up

Tomorrow: **DFMEA: Sensor & Analog Front-End Failure Modes (ECG, SpO2, Temperature)** — we'll walk through the specific failure modes of the analog front end (electrode offset, LED aging, thermistor self-heating) and how each maps to Occurrence and Detection ratings.
