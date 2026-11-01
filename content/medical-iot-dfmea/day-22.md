---
title: "Day 22: Design for Manufacturability & Linking DFMEA to PFMEA for Medical Devices"
date: 2026-11-01
tags: ["til", "medical-iot-dfmea", "dfm", "pfmea"]
---

# Day 22: Design for Manufacturability & Linking DFMEA to PFMEA for Medical Devices

## What I Explored Today

Today I dug into the seam between design and manufacturing — specifically how the failure modes I've been cataloging in the DFMEA for our wearable ECG patch need to flow into a PFMEA that the contract manufacturer (CM) can actually act on. The naive assumption is that these are two separate documents owned by two separate teams. In practice, for a Class II device under 21 CFR 820.30(g) and ISO 14971, they're two views of the same risk picture, and if the linkage is broken, you get a design that's robust on paper but yields 12% fallout at the CM's SMT line. I spent the day building a traceability bridge between the two and reworking three design decisions that were quietly unmanufacturable.

## The Core Concept

DFMEA asks "how can this design fail to meet requirements?" PFMEA asks "how can this *process* fail to produce the design as intended?" The trap is treating them as independent. They aren't: every DFMEA failure mode that has a *manufacturing* cause code (as opposed to a field/use cause) is a candidate PFMEA line item, and every PFMEA high-RPN process step should trace back to a design characteristic that the DFMEA flagged as special.

The mechanism that connects them is the **Critical-to-Quality (CTQ) characteristic** and the **special characteristic symbol**. When the DFMEA identifies a failure mode whose severity is high (e.g., S=9 or 10 for a patient-safety hazard) and whose occurrence is driven by a manufacturing variation, you promote that design feature to a special characteristic. That symbol then becomes a control-plan requirement in the PFMEA, which forces the CM to add detection (SPC, AOI, functional test) at that step. Break the chain and you've got a DFMEA claiming RPN reduction via "design controls" that the factory never implements.

For medical devices there's an extra regulatory bite: ISO 13485 §7.3.3 requires design outputs to be verifiable, and 820.30(g) requires design validation. If a DFMEA mitigation is "manufacturing process control," that control must appear in the PFMEA and control plan or your design history file has a hole an auditor will find.

## Key Commands / Configuration / Code

I keep the DFMEA and PFMEA as structured data (YAML) so I can lint the linkage automatically rather than eyeballing two spreadsheets. Here's the schema fragment and a validation script:

```yaml
# dfmea.yaml — one item, abbreviated
items:
  - id: DF-014
    item: "ECG front-end AFE"
    failure_mode: "Solder void under AFE thermal pad"
    effect: "Intermittent lead-off detection, false asystole alarm"
    severity: 9            # patient safety
    occurrence: 4
    detection: 6
    special_char: true     # promoted: manufacturing-driven, high severity
    linked_pfmea: [PF-021]
```

```yaml
# pfmea.yaml
items:
  - id: PF-021
    process_step: "Reflow — AFE QFN"
    failure_mode: "Insufficient paste / voiding under thermal pad"
    cause: "Stencil aperture < 50% pad area, poor paste release"
    severity: 9
    occurrence: 5
    detection: 4
    controls: ["SPC on paste volume", "X-ray void inspection AQL"]
    linked_dfmea: [DF-014]
```

```python
# link_check.py — run in CI on every DFMEA/PFMEA commit
import yaml, sys

def load(p):
    with open(p) as f:
        return {i["id"]: i for i in yaml.safe_load(f)["items"]}

df, pf = load("dfmea.yaml"), load("pfmea.yaml")
errors = []

for did, d in df.items():
    if d.get("special_char"):
        # every special characteristic MUST have a PFMEA control
        if not d.get("linked_pfmea"):
            errors.append(f"{did}: special char with no PFMEA link")
        for pid in d.get("linked_pfmea", []):
            if pid not in pf:
                errors.append(f"{did}: dangling link to {pid}")
            elif not pf[pid].get("controls"):
                errors.append(f"{pid}: linked but no controls defined")

# bidirectional check: PFMEA severity must match DFMEA severity
for pid, p in pf.items():
    for did in p.get("linked_dfmea", []):
        if did in df and df[did]["severity"] != p["severity"]:
            errors.append(f"{pid}/{did}: severity mismatch "
                          f"({p['severity']} vs {df[did]['severity']})")

if errors:
    print("\n".join(errors)); sys.exit(1)
print(f"OK: {len(df)} DFMEA / {len(pf)} PFMEA items linked")
```

The severity-match rule is the one that catches real problems: a PFMEA that downgrades severity relative to its parent DFMEA is almost always a copy-paste error, and it silently weakens your risk file.

## Common Pitfalls & Gotchas

**1. Treating RPN as the promotion criterion.** RPN (S×O×D) is a poor gate for special-characteristic promotion because a low-occurrence, high-severity failure can score below a high-occurrence cosmetic one. Use **severity ≥ 9 as an absolute trigger** regardless of RPN, per AIAG-VDA guidance. Our AFE void case had RPN 216 — not alarming — but S=9 forced the control.

**2. One-way traceability.** Teams link DFMEA→PFMEA and stop. The reverse link matters because a PFMEA control change (CM swaps to a new stencil vendor) must trigger DFMEA re-review. My script enforces bidirectionality; without it, a process change silently invalidates a design risk assumption.

**3. Ignoring the CM's process capability data.** A PFMEA occurrence rating is a guess unless you have Cp/Cpk from the actual line. I now require the CM to supply Cpk for every special-characteristic step; a Cpk < 1.33 on a S=9 feature means the design isn't manufacturable as specified and the DFMEA mitigation is fiction.

## Try It Yourself

1. **Build the link checker.** Take two small DFMEA/PFMEA CSVs from any project (or the YAML above), convert to the schema, and run `link_check.py`. Deliberately introduce a severity mismatch and a dangling link and confirm both are caught.

2. **Promote by severity, not RPN.** List your DFMEA items sorted by severity descending. For every S≥9 item, verify a PFMEA control exists. Count how many were missed by an RPN-only review — that number is your audit exposure.

3. **Request Cpk data.** For one special characteristic on your current build, ask your CM for Cpk over the last 3 lots. Compare it to the occurrence rating in your PFMEA. If they disagree, you've found a risk-file correction.

## Next Up

Tomorrow: **Risk Management File, Design History File & Traceability Matrix** — how the DFMEA/PFMEA pair plugs into the RMF per ISO 14971, what actually goes in the DHF, and building a traceability matrix that survives an FDA inspection without a scavenger hunt.
