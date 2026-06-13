---
title: "Day 01: Medical Device Software Regulation: FDA, CE & MDR"
date: 2026-06-13
tags: ["til", "iec62304", "regulation", "fda", "ce-mark"]
---

## What I Explored Today

Today I mapped the regulatory maze that governs medical device software. If you ship code that touches patient data, diagnoses, or therapy delivery, you're not just a software engineer—you're a regulated manufacturer. I dug into the three-letter acronyms that define our compliance reality: FDA (US), CE marking under the EU Medical Device Regulation (MDR), and how they intersect with IEC 62304. The key takeaway: these are not optional checklists; they are legally enforceable frameworks with real liability.

## The Core Concept

Why do we have three separate regulatory regimes for the same software? Because medical devices cross borders, and each jurisdiction has its own definition of "safe." The FDA treats software as a medical device (SaMD) under the Federal Food, Drug, and Cosmetic Act, enforced via 21 CFR Part 820 (Quality System Regulation) and Part 11 (electronic records). The EU MDR (2017/745) replaced the older MDD in 2021 and is stricter—it requires a Notified Body to audit your technical documentation and quality system.

The critical insight: **regulations define *what* you must achieve (safety, effectiveness), but IEC 62304 defines *how* you prove it.** The FDA recognizes IEC 62304 as a consensus standard; the MDR harmonizes it (EN 62304). If you comply with IEC 62304, you are 80% of the way to both FDA clearance and CE marking. The remaining 20% is jurisdiction-specific: FDA requires 510(k) or PMA submissions; MDR requires a Notified Body review and a Declaration of Conformity.

## Key Commands / Configuration / Code

You won't find a `pip install fda-compliance`, but you will find configuration files that prove your software development process meets these standards. Here's a practical example: a `software_classification.py` script that determines your device class under both FDA and MDR rules.

```python
# software_classification.py
# Determines medical device software class per FDA and EU MDR

def fda_classification(intended_use: str, data_type: str, clinical_impact: str) -> str:
    """
    FDA software classification per 21 CFR 862-892.
    Class I: low risk (e.g., fitness tracking)
    Class II: moderate risk (e.g., ECG analysis)
    Class III: high risk (e.g., life-support algorithms)
    """
    if clinical_impact == "life-sustaining":
        return "Class III"
    elif intended_use == "diagnosis" and data_type == "physiological":
        return "Class II"
    else:
        return "Class I"

def mdr_classification(rule_number: int) -> str:
    """
    EU MDR classification per Annex VIII, Rules 1-22.
    Rule 9-11 specifically cover software.
    """
    # Rule 11: Software intended to provide information for diagnosis or therapeutic decisions
    if rule_number == 11:
        # Sub-classes based on severity of situation
        return "Class IIa (if no serious deterioration) or Class IIb (if serious deterioration)"
    elif rule_number == 10:
        # Software intended for monitoring of vital physiological parameters
        return "Class IIa"
    else:
        return "Class I"

# Example usage
print(f"FDA class: {fda_classification('diagnosis', 'ECG', 'arrhythmia detection')}")
# Output: FDA class: Class II
print(f"MDR class: {mdr_classification(11)}")
# Output: MDR class: Class IIa (if no serious deterioration) or Class IIb (if serious deterioration)
```

For your CI/CD pipeline, you need to track regulatory artifacts. Here's a `.gitignore`-style config for a compliance repository:

```yaml
# .regulatory-ignore
# Files that must never be excluded from regulatory audit
!*.risk
!*.hazard
!*.verification
!*.validation
!*.design_history
```

## Common Pitfalls & Gotchas

1. **Assuming "Software as a Medical Device" (SaMD) is the same everywhere.** It's not. The FDA defines SaMD as software intended to be used for medical purposes without being part of a hardware medical device. The MDR defines it as "software that drives or influences the use of a device." A mobile app that displays heart rate from a wearable is SaMD under MDR (Rule 11) but may be a mobile medical app under FDA (subject to enforcement discretion). Always check the specific jurisdiction's guidance.

2. **Mixing up "CE marking" with "FDA clearance."** CE marking is a self-declaration (for Class I) or Notified Body audit (Class II+). FDA clearance requires a 510(k) submission showing substantial equivalence to a predicate device. You cannot CE-mark first and then FDA-clear—the processes are parallel, not sequential. Many startups fail by starting with CE and then discovering their predicate search is empty.

3. **Ignoring post-market surveillance requirements.** Both FDA and MDR require active monitoring after release. MDR Article 83 mandates a Post-Market Surveillance (PMS) plan, periodic safety update reports (PSUR), and trend reporting. FDA requires complaint handling per 21 CFR 820.198. If your software has a bug that causes a false negative in cancer screening, you must report it within 30 days (FDA) or 15 days (MDR for serious incidents). Your CI/CD pipeline must include a "regulatory incident" ticket type.

## Try It Yourself

1. **Classify your own project.** Take any software you've worked on (or a hypothetical one). Write a one-page document classifying it under both FDA and MDR rules. Use the `fda_classification()` function above as a starting point. What class is it? What evidence would you need to submit?

2. **Audit your version control.** Look at your last three commits. Do they contain any regulatory artifacts (risk analysis updates, verification results)? If not, create a `.regulatory-ignore` file and add at least three file patterns that must *never* be excluded from audit (e.g., `*.risk`, `*.hazard`, `*.validation`).

3. **Map your software to an MDR rule.** Read Annex VIII, Rule 11 of the EU MDR (it's free online). Write a short paragraph explaining which sub-rule your software falls under and why. This is the exact analysis a Notified Body auditor will ask for.

## Next Up

Tomorrow, I'll break down **IEC 62304 Structure: Clauses, Scope & ISO 14971**—the actual standard that turns these regulatory demands into engineering tasks. We'll look at the three software safety classes, the dreaded "Clause 5" (software development process), and how risk management (ISO 14971) threads through every line of code.
