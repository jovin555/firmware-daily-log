---
title: "Day 25: Medical Device Software Regulation: FDA, CE & MDR"
date: 2026-07-07
tags: ["til", "iec62304", "regulation", "fda", "ce-mark"]
---

## What I Explored Today

Today I mapped the practical overlap between three regulatory frameworks that govern medical device software: the US FDA's approach (21 CFR 820 / 21 CFR Part 11), the EU's Medical Device Regulation (MDR 2017/745), and the CE marking process. The key insight: while IEC 62304 is the harmonized standard for software lifecycle, each regulator interprets its clauses differently. An engineer shipping to both markets needs to build a single software process that satisfies both, not maintain two parallel systems.

## The Core Concept

Regulators don't care about your code quality in the abstract. They care about **risk control traceability** and **evidence that your process produced safe software**. The FDA and EU MDR both require:

- A documented software development plan (IEC 62304 Clause 5)
- Software requirements traceable to risk analysis (ISO 14971)
- Verification and validation evidence for every safety-related function
- Post-market surveillance (PMS) data collection

The difference is in **enforcement posture**. The FDA requires a premarket submission (510(k), PMA, or De Novo) with a software description document. The EU MDR requires a Technical File reviewed by a Notified Body, plus a Declaration of Conformity. Both demand that your software classification (Class IIa, IIb, III in EU; Class II, III in US) determines how much evidence you need.

For software engineers, the practical consequence is: **your build pipeline must generate regulatory artifacts automatically**. You cannot manually trace requirements to tests for a 50,000-line embedded system.

## Key Commands / Configuration / Code

### 1. FDA Software Classification Decision Tree (Python snippet)

This is a simplified classifier for FDA software risk class based on 21 CFR 860 and FDA guidance "Guidance for the Content of Premarket Submissions for Software Contained in Medical Devices."

```python
# fda_software_classifier.py
def classify_fda_software(device_type: str, function_critical: bool, 
                          data_driven: bool, standalone: bool) -> str:
    """
    Determine FDA software class based on device function.
    Reference: FDA Guidance - Software as a Medical Device (SaMD)
    """
    if standalone and data_driven and function_critical:
        # e.g., AI-based diagnostic algorithm
        return "Class III"  # PMA required
    elif device_type in ["therapeutic", "life-support"]:
        return "Class III"
    elif function_critical and not data_driven:
        # e.g., infusion pump control logic
        return "Class II"   # 510(k) typically required
    else:
        # e.g., patient scheduling app
        return "Class I"    # general controls, no 510(k)
```

### 2. EU MDR Classification Rule Mapping (YAML config for traceability tool)

The EU MDR uses 22 classification rules (Annex VIII). This YAML maps software features to rules for automated classification.

```yaml
# mdr_classification_rules.yaml
rules:
  - rule: 11
    description: "Software intended to provide information for diagnosis or therapeutic decisions"
    applies_to: ["diagnostic", "therapeutic_decision"]
    class: "IIa"  # default; IIb if serious deterioration
  - rule: 22
    description: "Software intended to monitor physiological processes"
    applies_to: ["vital_signs_monitoring"]
    class: "IIa"
  - rule: 3
    description: "Software intended for administration of medicinal products"
    applies_to: ["drug_delivery_control"]
    class: "IIb"  # or III if life-threatening
```

### 3. CI Pipeline Artifact for Regulatory Submission (GitHub Actions snippet)

This is a real workflow step that generates a Software Bill of Materials (SBOM) and links it to risk IDs.

```yaml
# .github/workflows/regulatory_artifacts.yml
- name: Generate SBOM with risk traceability
  run: |
    # Use cyclonedx-bom to generate SBOM
    cyclonedx-bom -o sbom.xml --include-license-text
    # Extract risk IDs from git commit messages
    git log --oneline --grep="RISK-" --format="%s" > risk_ids.txt
    # Merge into a single regulatory report
    python scripts/merge_sbom_risk.py sbom.xml risk_ids.txt \
      --output regulatory_artifact.json
```

## Common Pitfalls & Gotchas

### 1. Assuming "CE Mark" means one certification
The CE mark is not a single certificate. For medical devices, you need:
- ISO 13485 certification for your QMS
- IEC 62304 compliance for software lifecycle
- ISO 14971 for risk management
- A Notified Body audit (for Class IIa and above)
- A Declaration of Conformity signed by your EU Authorized Representative

Many teams get stuck because they think a single audit covers everything.

### 2. Ignoring the "intended purpose" when classifying
The FDA and EU both classify based on what the software *claims* to do, not what it technically does. If your embedded system monitors heart rate but the label says "for wellness only," you might avoid Class II. But if a clinician uses it for diagnosis, you're in regulatory trouble. **Document your intended purpose explicitly in the Software Requirements Specification (SRS).**

### 3. Treating post-market surveillance as optional
Both FDA (21 CFR 803) and EU MDR (Article 83) require active collection of field data. For software, this means:
- Crash logs with patient impact assessment
- Cybersecurity vulnerability reporting
- Periodic safety update reports (PSUR) every 2 years for Class IIb/III

If your firmware doesn't have a telemetry module for error reporting, you're non-compliant.

## Try It Yourself

1. **Classify your own project**: Take a medical device software project you know. Use the Python classifier above to determine its FDA class. Then use the EU MDR rules YAML to assign an EU class. Are they the same? If not, why?

2. **Audit your CI pipeline**: Look at your current build system. Can it generate a regulatory artifact (SBOM, test traceability matrix, risk report) in under 5 minutes? If not, add a step that runs `cyclonedx-bom` and links output to your issue tracker.

3. **Write an intended purpose statement**: Draft a single paragraph that defines your software's intended medical purpose. Include: target patient population, clinical condition, and whether it's diagnostic, therapeutic, or monitoring. This is the first thing a regulator will read.

## Next Up

Tomorrow: **IEC 62304 Structure: Clauses, Scope & ISO 14971** — we'll dissect the standard's clause hierarchy, understand what's in scope (and what's not), and map the critical interface between software lifecycle and risk management. Bring your copy of the standard.
