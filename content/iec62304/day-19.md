---
title: "Day 19: Usability Engineering: IEC 62366 Integration"
date: 2026-07-01
tags: ["til", "iec62304", "usability", "iec62366"]
---

## What I Explored Today

Today I dug into the practical integration of IEC 62366-1 (usability engineering) with IEC 62304 (medical device software lifecycle). While 62304 focuses on software safety classification and development process, 62366 demands that we systematically identify, analyze, and mitigate use errors that could lead to patient harm. The real work happens when you map usability engineering outputs—use specifications, task analyses, and formative test results—directly into your software V&V artifacts. I spent the afternoon refactoring our test plan to include usability-related software requirements and linking them to risk control measures.

## The Core Concept

Why does this integration matter? Because a perfectly bug-free device that’s impossible to use correctly is still dangerous. IEC 62366-1 requires you to perform a *use specification*, *identify hazardous use scenarios*, and *evaluate residual risk* from use errors. IEC 62304, meanwhile, demands that all software safety requirements be traced, verified, and validated.

The bridge is this: every use error that could cause harm must be translated into a **software safety requirement** under 62304. For example, if a user could accidentally press a "deliver bolus" button when they meant "pause," that use error becomes a software requirement: "The system shall require a two-step confirmation (press and hold for 2 seconds) before initiating bolus delivery." That requirement then gets a unique ID, a risk control link, and a verification test case.

The key artifact is the **Use Specification** (IEC 62366-1, Clause 5.2) feeding the **Software Requirements Specification** (IEC 62304, Clause 5.2). You can’t just write a usability report and file it—you must trace each hazardous use scenario to a software requirement that mitigates it.

## Key Commands / Configuration / Code

Below is a practical example of how I structure a requirements traceability matrix (RTM) that bridges usability engineering and software V&V. This is a CSV that we parse with a Python script to generate traceability reports.

```csv
# usability_to_software_rtm.csv
# Columns: UseErrorID, HazardousScenario, Severity, SoftwareReqID, RiskControlMeasure, VerificationTestID
UE-001, "User selects wrong patient from dropdown during infusion setup", Critical, SRS-042, "System shall display patient name and DOB on confirmation dialog before infusion start", VT-101
UE-002, "User misreads alarm threshold value on small display", Serious, SRS-043, "Alarm threshold values shall be displayed in font size >= 14pt on all screens", VT-102
UE-003, "User accidentally presses 'Start' instead of 'Configure' on touchscreen", Moderate, SRS-044, "Start button shall require a 1.5-second press-and-hold to activate", VT-103
```

Now, here’s a Python snippet we use to validate that every usability-related software requirement has a corresponding verification test:

```python
# validate_usability_trace.py
import csv

def check_traceability(csv_path):
    missing_tests = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['VerificationTestID'].strip():
                missing_tests.append(row['UseErrorID'])
    if missing_tests:
        print(f"ERROR: {len(missing_tests)} use errors lack verification tests:")
        for uid in missing_tests:
            print(f"  - {uid}")
        return False
    else:
        print("All use errors have corresponding verification tests.")
        return True

if __name__ == "__main__":
    check_traceability("usability_to_software_rtm.csv")
```

We run this in CI after every usability engineering review cycle. The output feeds directly into the Design History File (DHF) audit trail.

For the actual usability test protocol, I use a structured markdown template that maps to 62366-1 clauses:

```markdown
# Formative Usability Test Protocol: Infusion Pump Software v2.1
## Test ID: FUT-007
## Use Error ID: UE-002 (Alarm threshold misread)
## Task: User adjusts alarm threshold for heart rate
## Pass Criteria: User correctly identifies current threshold value within 3 seconds
## Data Collection: Eye tracking + screen recording
## Risk Control Verification: SRS-043 (font size >= 14pt)
```

## Common Pitfalls & Gotchas

1. **Treating usability as a separate silo.** I’ve seen teams hire a human factors consultant, get a glossy usability report, and then never link those findings to software requirements. The auditor will flag this immediately. Every hazardous use scenario must have a software requirement ID in your traceability matrix.

2. **Confusing formative vs. summative testing.** Formative tests (iterative, during development) identify use errors to fix. Summative tests (final validation) prove residual risk is acceptable. Many teams skip formative testing and go straight to summative, then fail because they didn’t catch obvious errors early. Under 62366-1, you need both.

3. **Ignoring the "use specification" as a living document.** Your use specification (patient population, use environment, training level) changes as the product evolves. If you add a new feature (e.g., wireless data export), you must update the use specification and re-evaluate hazardous scenarios. I’ve seen this missed in agile sprints where usability is only revisited at release.

## Try It Yourself

1. **Map one use error to a software requirement.** Pick a simple device feature (e.g., a "stop" button on a syringe pump). Write down one realistic use error (user presses stop instead of pause). Draft a software safety requirement that mitigates it, then write a verification test for that requirement.

2. **Run the traceability checker.** Create a CSV file with three rows of use errors (make one row intentionally missing the VerificationTestID). Run the Python script above and confirm it catches the missing test. Fix the CSV and re-run.

3. **Review your existing test plan.** Find one test case that tests a user interaction (e.g., button press, menu navigation). Ask: "Does this test case trace back to a documented use error from a usability study?" If not, write the use error ID and the associated software requirement ID into the test case metadata.

## Next Up

Tomorrow we tackle **Software Release: Notes, Version Labels & Archiving**—how to package your verified software for release, what goes into release notes (and what doesn’t), how to label versions for traceability, and the archiving requirements that keep auditors happy for years after the product ships.
