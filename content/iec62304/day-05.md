---
title: "Day 05: Regulatory Submissions: 510(k), PMA & Technical Files"
date: 2026-06-17
tags: ["til", "iec62304", "510k", "submissions"]
---

## What I Explored Today

Today I dug into the three major regulatory submission pathways that determine how your IEC 62304-compliant software actually reaches the market: the FDA's 510(k) premarket notification, the Premarket Approval (PMA) process, and the EU's Technical File for CE marking. While the software development lifecycle is universal, the evidence package you assemble depends entirely on which submission route your device class requires. I focused on what embedded software engineers need to produce—not just paperwork, but actual traceability artifacts, risk management files, and verification evidence that regulators will inspect.

## The Core Concept

Regulatory submissions are not about proving your software works; they are about proving your *process* works. The FDA and notified bodies care more about how you arrived at your safety claims than the claims themselves. A 510(k) for a Class II device requires demonstrating "substantial equivalence" to a predicate device—meaning your software's intended use, algorithm behavior, and safety mechanisms must map to an existing legally marketed device. A PMA for Class III devices demands de novo clinical evidence and full lifecycle data. For EU MDR, the Technical File must show conformity with Annex II and III, including a rigorous description of the software's intended purpose, operating environment, and risk-benefit analysis.

The practical takeaway: your IEC 62304 software safety classification (Class A, B, or C) directly maps to the submission depth. A Class B device under 62304 typically aligns with a 510(k), while Class C often requires PMA or the most stringent Technical File content. Start your submission planning by identifying your device class *before* you write a single line of firmware.

## Key Commands / Configuration / Code

Below is a practical checklist in YAML format that I use to track submission artifacts. This is not a theoretical list—every item here has been requested by FDA reviewers or EU notified bodies in real audits.

```yaml
# submission_artifact_tracker.yaml
# Use this to map IEC 62304 deliverables to submission pathways

submission:
  type: "510(k)"  # Options: 510(k), PMA, Technical File
  device_class: "II"  # FDA: II, III | EU: IIa, IIb, III
  software_safety_class: "B"  # IEC 62304: A, B, C

required_artifacts:
  - artifact: "Software Requirements Specification (SRS)"
    iec62304_ref: "5.2"
    submission_section: "510(k) Premarket Notification - Section 5"
    format: "PDF with revision history and sign-off"
    
  - artifact: "Software Architecture Description"
    iec62304_ref: "5.3"
    submission_section: "Technical File - Annex II, Section 1.2"
    format: "UML diagrams + data flow diagrams"
    
  - artifact: "Risk Management File (ISO 14971)"
    iec62304_ref: "4.1, 7.1"
    submission_section: "510(k) Summary - Safety and Effectiveness"
    format: "FMEA table with risk control measures"
    
  - artifact: "Software Verification and Validation Report"
    iec62304_ref: "6.1, 6.2"
    submission_section: "PMA - Clinical Performance Data"
    format: "Test cases, pass/fail logs, coverage metrics"
    
  - artifact: "Software Change Log"
    iec62304_ref: "5.5, 6.3"
    submission_section: "Technical File - Annex IX"
    format: "Git log filtered by release tags + impact analysis"

# Example mapping for a Class B infusion pump software
mapping_example:
  predicate_device: "Model X-100 Infusion Pump (K123456)"
  substantial_equivalence_claims:
    - "Same algorithm for flow rate calculation"
    - "Identical alarm thresholds for occlusion detection"
    - "Equivalent user interface navigation logic"
  differences:
    - "Updated wireless protocol from Bluetooth 4.0 to 5.2"
    - "Added real-time data logging for post-market surveillance"
```

For actual submission document generation, I use a Python script to extract traceability from my DOORS or Jama requirements database:

```python
# extract_traceability.py
# Generates a CSV for submission reviewers showing SRS->Architecture->Test links

import csv
import sys

def generate_traceability_matrix(requirements_db, test_db, output_file):
    """
    requirements_db: list of dicts with keys: 'req_id', 'description', 'safety_class'
    test_db: list of dicts with keys: 'test_id', 'req_id', 'result'
    """
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Requirement ID', 'Safety Class', 'Test ID', 'Test Result', 'Risk Control'])
        
        for req in requirements_db:
            # Find all tests covering this requirement
            tests = [t for t in test_db if t['req_id'] == req['req_id']]
            for test in tests:
                writer.writerow([
                    req['req_id'],
                    req['safety_class'],
                    test['test_id'],
                    test['result'],
                    'Yes' if req['safety_class'] == 'C' else 'No'
                ])
    
    print(f"Traceability matrix written to {output_file}")
    return output_file

# Example usage
if __name__ == "__main__":
    reqs = [
        {'req_id': 'SRS-101', 'description': 'Flow rate accuracy ±2%', 'safety_class': 'B'},
        {'req_id': 'SRS-102', 'description': 'Occlusion alarm within 5 seconds', 'safety_class': 'C'}
    ]
    tests = [
        {'test_id': 'T-201', 'req_id': 'SRS-101', 'result': 'PASS'},
        {'test_id': 'T-202', 'req_id': 'SRS-102', 'result': 'PASS'}
    ]
    generate_traceability_matrix(reqs, tests, 'submission_traceability.csv')
```

## Common Pitfalls & Gotchas

1. **Assuming "substantial equivalence" means identical code.** The FDA expects you to prove that any differences in software (new algorithms, updated protocols) do not introduce new safety risks. I've seen 510(k) submissions rejected because the engineer changed a PID controller's gain values without providing a comparative risk analysis against the predicate device.

2. **Mixing IEC 62304 software safety classes with FDA device classes.** A Class II medical device can contain Class C software (e.g., an infusion pump with closed-loop control). Your Technical File must address the highest software safety class, not just the device class. Notified bodies will flag this immediately.

3. **Omitting the "intended purpose" statement in the Technical File.** EU MDR Annex II requires a precise description of the device's intended medical purpose, patient population, and anatomical application. Vague statements like "for general patient monitoring" will trigger a request for additional documentation. Be specific: "For continuous non-invasive blood pressure monitoring in adult ICU patients weighing 40-150 kg."

## Try It Yourself

1. **Map your current project to a submission pathway.** Identify your device's FDA class (I, II, III) or EU MDR class (I, IIa, IIb, III). Then list the top 5 IEC 62304 artifacts you would need to produce for that pathway. Cross-reference with the YAML tracker above.

2. **Write a substantial equivalence claim.** Pick a feature from your embedded software (e.g., a battery management algorithm). Write a one-paragraph claim explaining how it is equivalent to a known predicate device, and explicitly state any differences. This is exactly what goes into a 510(k) summary.

3. **Generate a traceability matrix.** Use the Python script provided (or your own tool) to extract requirements-to-test links from your current project. Ensure every Class C requirement has at least one test with a documented risk control measure. Run the script and inspect the output CSV.

## Next Up

Tomorrow we tackle the Software Development Plan (SDP): What It Must Contain. We'll build a real SDP template that satisfies both IEC 62304 clause 5.1 and FDA guidance, including the dreaded "software development environment description" that auditors love to pick apart.
