---
title: "Day 15: DFMEA: Enclosure, Ingress Protection & Biocompatibility (ISO 10993)"
date: 2026-10-25
tags: ["til", "medical-iot-dfmea", "enclosure", "iso10993"]
---

## What I Explored Today

Today I moved the DFMEA from the PCB out to the box that holds it. For a wearable medical IoT device, the enclosure is not cosmetic — it is a sterile barrier, an ingress barrier, and a biocompatibility boundary all at once. I worked through how to structure failure modes for ingress protection (IEC 60529), how to translate ISO 10993 biocompatibility requirements into DFMEA detection and prevention controls, and how to score severity when the failure mode is "patient develops a contact sensitization reaction three weeks after fitting." The interesting part is that mechanical DFMEA for medical devices has to carry regulatory evidence, not just engineering intuition — every control you claim has to map to a test report you can actually produce.

## The Core Concept

The reason enclosure DFMEA is different from consumer-product DFMEA is the coupling between *physical failure* and *clinical harm*. A gasket that fails an IPX7 immersion test on a fitness tracker is a warranty issue. The same gasket failure on an infusion pump controller is a shock hazard, and on an implantable-adjacent wearable it can be a pathway for bioburden ingress into a wound site. So the severity score in your DFMEA is driven by the *intended use environment and patient contact category*, not by the component itself.

ISO 10993 is a family of standards, and the part that matters for enclosure DFMEA is the categorization in ISO 10993-1: contact duration (A: <24h, B: 24h–30d, C: >30d) and nature of contact (surface device, external communicating device, implant). A skin-contact wearable housing is a *surface device, prolonged contact* — that pulls in cytotoxicity (10993-5), sensitization and irritation (10993-10), and often material characterization (10993-18) to justify why you're not running animal tests. The DFMEA failure mode is "housing material leaches a sensitizer above the tolerable contact threshold," and your prevention control is material selection + extractable/leachable screening, with detection being the biological evaluation report.

The other concept worth internalizing: **IP ratings are not a single number, they're a test condition.** IPX7 is 30 minutes at 1 m. IP68 is manufacturer-specified (often 1.5 m for 30 min, but you must state it). If your DFMEA says "IP67 enclosure" but your test plan only ran IPX7, you have a detection gap, and a good auditor will find it. Every ingress claim in the DFMEA must cite the exact clause and duration.

## Key Commands / Configuration / Code

There's no firmware here, but there is configuration — the DFMEA worksheet itself. Here's a representative row structure I use in a CSV that feeds our FMEA tool (APIS IQ or a Python pipeline):

```csv
item,function,failure_mode,effect,severity,potential_cause,occurrence,prevention_control,detection_control,detection,ap
Housing seal (silicone O-ring, 70 Shore A),"Maintain IP67 per IEC 60529 clause 14.2.7 (1 m, 30 min)","Seal compression set > 25% after 500 thermal cycles","Moisture ingress to PCB; corrosion of charging contacts; loss of charge","8","Silicone compression set at 60°C operating temp; inadequate groove fill ratio","4","Groove fill ratio 75–85%; compression set tested per ASTM D395 Method B at 70h/100°C","IP67 immersion test on 10 units after accelerated aging (IEC 60068-2-14 Nb)","3","96"
Housing material (PC/ABS, skin contact),"Biocompatible per ISO 10993-1 surface device, prolonged contact","Extractable sensitizer above tolerable contact threshold","Contact dermatitis; patient non-compliance; recall","9","Colorant or mold release agent not screened for sensitization","3","Material cert + ISO 10993-18 chemical characterization on final formulation; supplier CoA","ISO 10993-10 sensitization (guinea pig maximization or LLNA) on final article","4","108"
```

A few things to notice. Severity 8 for moisture ingress because it degrades a safety-relevant charging function; severity 9 for sensitization because it's a clinical harm with delayed onset and poor detectability in the field. The AP (action priority) column uses the AIAG-VDA 2019 table, not the old RPN — RPN is deprecated for a reason and medical auditors increasingly expect AP.

If you're scripting the DFMEA review, a quick sanity check that every IP claim has a matching test:

```python
# flag any DFMEA row claiming IP protection without a cited IEC 60529 clause
import csv

with open("dfmea_enclosure.csv") as f:
    for row in csv.DictReader(f):
        claims_ip = "IP" in row["function"]
        cites_clause = "IEC 60529" in row["detection_control"]
        if claims_ip and not cites_clause:
            print(f"GAP: {row['item']} claims ingress protection without test clause")
```

## Common Pitfalls & Gotchas

**1. Treating IP rating as a material property.** It's a *system* property of the assembled, aged unit. A gasket that passes IP67 on day one can fail after UV exposure, thermal cycling, or repeated mating cycles. Your DFMEA occurrence rating must reflect the aged condition, and your detection control must be an aged-sample test, not a fresh-build test.

**2. Missing the "biocompatibility by analogy" trap.** ISO 10993-1 allows you to leverage existing data for a material *only if* the formulation, processing, and sterilization are identical. A "same base resin" claim with a different colorant masterbatch is not the same material. DFMEA prevention controls should name the final article formulation, not the resin family.

**3. Confusing ingress protection with sterility maintenance.** IP67 does not mean the device stays sterile. If the enclosure is a sterile barrier (e.g., a reprocessed handle), you need ISO 11607 validation, and that's a separate failure mode with separate controls. Don't let one test report stand in for two claims.

## Try It Yourself

1. **Build the gap-checker.** Take your current enclosure DFMEA (or a sample one) and run the Python snippet above against it. Every row that claims an IP rating but doesn't cite IEC 60529 clause and duration is a detection gap — fix at least one.

2. **Map your contact category.** For your device, write down the ISO 10993-1 contact category (duration + nature) and list which 10993 sub-standards that pulls in. Then check whether each one appears as a detection control in your DFMEA. If a standard is missing, you have an unmitigated failure mode.

3. **Age a gasket.** If you have lab access, take three silicone O-rings, run them through 500 thermal cycles per IEC 60068-2-14 Nb, and measure compression set per ASTM D395. Compare against the fresh value. That delta is your real occurrence input — not the datasheet number.

## Next Up

Tomorrow I'm moving from the mechanical boundary to the electrical one: **DFMEA: Electrical Safety & EMC (IEC 60601-1, IEC 60601-1-2)**. Same discipline, different failure physics — creepage and clearance, patient leakage current, and why an EMC immunity failure on a medical device is a *safety* failure mode, not a nuisance one.
