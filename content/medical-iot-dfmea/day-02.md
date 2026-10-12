---
title: "Day 02: Intended Use & Device Classification for Connected Medical Devices"
date: 2026-10-12
tags: ["til", "medical-iot-dfmea", "classification", "intended-use"]
---

## What I Explored Today

Today I dug into the regulatory foundation that everything else in a DFMEA hangs off: **Intended Use** and **Device Classification**. I've been treating these as paperwork chores for years, but the more I look at connected medical devices — where a firmware update can silently change risk profile — the more I realize that intended use is actually the *specification* that drives your risk analysis, your software safety class (IEC 62304), your cybersecurity posture (IEC 81001-5-1), and even your cloud architecture decisions. If you get intended use wrong, every downstream DFMEA line item is built on sand. I spent the day mapping the FDA and EU MDR classification pathways for a hypothetical connected pulse oximeter and writing a small script to sanity-check classification logic against the FDA product code database.

## The Core Concept

Intended use is not marketing copy. It is a legally binding statement of:

1. **What the device does** (function)
2. **Who it's for** (patient population, user — lay vs. professional)
3. **Where/how it's used** (clinical environment, home, ambulatory)
4. **Why** (diagnosis, monitoring, therapy, prevention)

Classification flows from intended use plus risk. In the US, FDA classifies into Class I, II, or III based on risk and the availability of controls (general, special, or PMA). In the EU under MDR 2017/745, you classify under Annex VIII rules (Rule 1–22), and software gets its own treatment under Rule 11 — which is where connected devices get interesting.

Here's the *why* that matters for DFMEA: **classification determines the rigor of your design controls, your software safety class, and your cybersecurity requirements.** A Class II connected device with a wireless radio is not just "Class II" — it inherits:

- IEC 62304 software safety class (A/B/C) derived from the *worst-case harm* the software can cause
- FDA cybersecurity premarket expectations (Section 524B of FD&C Act, effective March 2023)
- EU MDR Rule 11 software classification (Class I, IIa, IIb, or III)

If your intended use says "for informational purposes only, not for diagnosis," you may drop a class — but the moment you add "alerts clinician when SpO2 < 90%," you've crossed into diagnostic territory and your risk file, software class, and clinical evidence all change. That's the trap.

## Key Commands / Configuration / Code

I use the FDA's openFDA API to look up product codes and their classification. This is real, unauthenticated, and rate-limited (240 req/min without a key, 1000/min with one).

```bash
# Look up a product code — e.g., "DQA" is pulse oximeter
curl -s "https://api.fda.gov/device/classification.json?search=product_code:DQA&limit=1" \
  | jq '.results[0] | {device_name, device_class, regulation_number, medical_specialty_description}'
```

Output for `DQA`:

```json
{
  "device_name": "Oximeter",
  "device_class": "2",
  "regulation_number": "870.2700",
  "medical_specialty_description": "Cardiovascular"
}
```

Now a small Python helper to sanity-check EU MDR Rule 11 software classification. This is a *decision aid*, not a substitute for your regulatory lead — but it forces you to articulate the logic.

```python
# mdr_rule11.py — simplified Rule 11 decision aid (MDR 2017/745, Annex VIII)
# NOT a substitute for regulatory review. Log your reasoning in the DHF.

def classify_software(provides_info_for_diagnosis: bool,
                      serious_deterioration_possible: bool,
                      death_or_irreversible_possible: bool) -> str:
    """
    Rule 11: Software intended to provide information used for
    diagnostic or therapeutic purposes is Class IIa, unless...
    """
    if not provides_info_for_diagnosis:
        return "Class I"  # e.g., wellness, lifestyle, administrative
    if death_or_irreversible_possible:
        return "Class III"
    if serious_deterioration_possible:
        return "Class IIb"
    return "Class IIa"

# Example: connected SpO2 monitor that alarms on desaturation
print(classify_software(
    provides_info_for_diagnosis=True,
    serious_deterioration_possible=True,   # missed desaturation -> harm
    death_or_irreversible_possible=False
))
# -> Class IIb
```

And the corresponding IEC 62304 software safety class, which is *derived from* your risk analysis, not from the MDR class directly:

```text
Class A: No injury or damage to health is possible
Class B: Non-serious injury is possible
Class C: Death or serious injury is possible
```

For the SpO2 alarm example above, if a missed alarm can lead to serious injury, your software is **Class C** — which means full software architecture documentation, detailed design, unit verification, and integration testing. That's a huge cost delta versus Class A. This is why intended use wording is a *budget* decision, not just a compliance one.

## Common Pitfalls & Gotchas

**1. Confusing "intended use" with "indications for use."** Intended use is the general purpose; indications for use is the specific clinical condition/population. FDA reviewers will reject a 510(k) where these are conflated. Your DFMEA scope should be anchored to intended use, but your clinical evaluation anchors to indications.

**2. Letting the cloud "escape" the intended use statement.** If your device uploads data to a clinician dashboard, that dashboard is *part of the device* under FDA's 2022 guidance on device software functions. Your intended use must cover the whole system — sensor, gateway, cloud, and clinician-facing UI. Teams routinely scope the DFMEA to the hardware and forget the backend, then get surprised by a cybersecurity finding.

**3. Assuming EU and US classifications map 1:1.** They don't. A device can be Class II in the US and Class IIb under MDR. Build your risk file to the *stricter* of the two if you're pursuing both markets, and document the mapping explicitly in your regulatory strategy.

## Try It Yourself

1. **Query openFDA for your device.** Pick a product code relevant to your project (e.g., `DQD` for blood pressure, `MHX` for ECG software) and pull `device_class`, `regulation_number`, and `submission_type_id`. Note whether it's 510(k), De Novo, or PMA — that tells you the evidentiary bar.

2. **Write your intended use in one sentence, then stress-test it.** Add the words "and transmits data to a cloud service for clinician review." Does your classification change? Does your software safety class change? Write the before/after in your DHF.

3. **Run the `classify_software` function with three scenarios** for your device: (a) informational only, (b) alarms on a non-critical parameter, (c) alarms on a parameter where a miss causes serious harm. Document the MDR class and IEC 62304 class for each. This becomes the seed of your DFMEA scope statement.

## Next Up

Tomorrow: **Design Controls (21 CFR 820 / QMSR): Inputs, Outputs, Verification & Validation.** We'll take the intended use we nailed down today and turn it into design inputs, trace them to outputs, and build the V&V matrix that your DFMEA will live inside. Bring your requirements doc — we're going to find the gaps.
