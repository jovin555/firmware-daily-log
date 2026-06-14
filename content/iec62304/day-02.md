---
title: "Day 02: IEC 62304 Structure: Clauses, Scope & ISO 14971"
date: 2026-06-14
tags: ["til", "iec62304", "iec62304", "overview"]
---

## What I Explored Today

Today I mapped the skeleton of IEC 62304:2006 + AMD1:2015. The standard is organized into nine clauses, but only Clauses 5–9 contain the normative requirements for software lifecycle processes. I also dug into the scope boundary—this standard covers *software as a medical device* (SaMD) and software embedded in hardware—and the critical linkage to ISO 14971:2019 (risk management). The key insight: IEC 62304 is not a standalone document; it depends on ISO 14971 for risk management and ISO 13485 for quality management. Without those, you’re building on sand.

## The Core Concept

Why does the structure matter? Because IEC 62304 is a *process standard*, not a product standard. It doesn’t tell you how to write safe code; it tells you what processes you must follow to demonstrate that the software is reasonably safe. The clauses form a waterfall-like progression:

- **Clause 4 (General Requirements)**: Quality system, risk management integration, and software maintenance plan.
- **Clause 5 (Software Development Process)**: Planning, requirements, architectural design, detailed design, unit implementation, integration, testing, and release.
- **Clause 6 (Software Maintenance Process)**: Handling changes after release.
- **Clause 7 (Software Risk Management Process)**: This is where ISO 14971 is invoked directly.
- **Clause 8 (Software Configuration Management Process)**: Traceability, version control, change control.
- **Clause 9 (Software Problem Resolution Process)**: Logging, analyzing, and closing defects.

The scope explicitly excludes:
- Hardware-only medical devices (e.g., a scalpel).
- Software that is not intended for medical purposes (e.g., a hospital billing system).
- Final validation of the medical device (that’s the manufacturer’s responsibility under ISO 13485).

The critical bridge to ISO 14971 is in Clause 7. It requires you to:
1. Identify hazardous situations (e.g., a drug infusion pump software miscalculates dose).
2. Analyze and evaluate risks.
3. Implement risk control measures (e.g., range checks, watchdog timers).
4. Verify that controls are effective.

Every software safety classification (Class A, B, C) determines how much of Clause 7 you must apply. Class C (highest risk) requires full risk management for every software item.

## Key Commands / Configuration / Code

Here’s a practical example of how you might document a risk control in a requirements management tool (e.g., DOORS, Jama, or even a YAML file). This is a real pattern used in regulatory submissions.

```yaml
# risk_control_item.yaml
# Example: Software risk control for infusion pump dose calculation
hazard_id: "H-001"
hazard_description: "User enters dose > max safe limit, causing overdose"
cause: "Software fails to validate input range"
risk_control_id: "RC-001"
risk_control_description: "Implement input validation: reject dose > 500 mL/hr"
verification_method: "Unit test: assert dose_rejected when dose > 500"
verification_result: "PASS"
safety_class: "C"
linked_requirement: "REQ-INF-042: Dose input validation"
```

In practice, you’d also create a traceability matrix. Here’s a minimal SQLite query to generate one:

```sql
-- traceability_matrix.sql
-- Assumes tables: hazards, risk_controls, requirements, tests
SELECT 
    h.hazard_id,
    rc.risk_control_id,
    r.requirement_id,
    t.test_id,
    t.test_result
FROM hazards h
JOIN risk_controls rc ON h.hazard_id = rc.hazard_id
JOIN requirements r ON rc.risk_control_id = r.risk_control_id
JOIN tests t ON r.requirement_id = t.requirement_id
WHERE t.test_result = 'FAIL';
-- This query finds any broken trace links
```

For a real embedded system, you might implement the risk control in C:

```c
// dose_validation.c
// Risk control RC-001: Reject dose > 500 mL/hr
#define MAX_DOSE_ML_PER_HR 500.0f

typedef enum { DOSE_OK, DOSE_TOO_HIGH, DOSE_NEGATIVE } dose_status_t;

dose_status_t validate_dose(float dose_ml_per_hr) {
    if (dose_ml_per_hr < 0.0f) {
        return DOSE_NEGATIVE;   // Also a hazard: negative dose
    }
    if (dose_ml_per_hr > MAX_DOSE_ML_PER_HR) {
        return DOSE_TOO_HIGH;   // Risk control active
    }
    return DOSE_OK;
}
```

## Common Pitfalls & Gotchas

1. **Ignoring the “software item” definition.** IEC 62304 defines a *software item* as any identifiable part of the software (e.g., a module, a library, a configuration file). Many teams treat the entire codebase as one item. This fails when you need to assign different safety classes to different modules. For example, a UI module might be Class A, while the dose calculation engine is Class C. You must decompose.

2. **Assuming ISO 14971 is optional.** Clause 4.1 says the manufacturer shall establish a risk management process *in accordance with ISO 14971*. If your QMS doesn’t include a formal risk management file (with FMEA/FTA, risk evaluation, and residual risk acceptance), your IEC 62304 audit will fail. The standard is explicit: risk management is not a separate activity—it’s woven into every development phase.

3. **Misinterpreting “software of unknown provenance” (SOUP).** SOUP items (e.g., FreeRTOS, a cryptographic library) are not exempt from risk management. Clause 7 requires you to analyze hazards introduced by SOUP. For example, if you use a real-time OS with a known bug in its scheduler, you must document the risk and either mitigate it (e.g., add a watchdog) or accept it with justification. Many teams skip this and get non-conformances.

## Try It Yourself

1. **Map your current project to IEC 62304 clauses.** Take a software module you’re working on (e.g., a sensor driver). Write down which clauses apply (5–9). Identify one risk control you already have (e.g., a bounds check) and document it in a YAML file similar to the example above.

2. **Create a traceability query.** If you have a test database, write a SQL query that joins hazards → risk controls → requirements → tests. Run it and see if any tests are missing for a known hazard. If you don’t have a database, sketch the traceability on paper for a simple feature (e.g., a button press that starts a motor).

3. **Review a SOUP component.** Pick a third-party library in your project (e.g., a JSON parser). Search its documentation or issue tracker for known bugs. Write a brief risk assessment: what happens if the parser crashes? Is the crash hazardous? Document your conclusion and whether you need a risk control.

## Next Up

Tomorrow: **Software Safety Classification: Class A, B & C**. We’ll break down the criteria for each class, how to classify your software items, and the exact development activities required for each. Bring your risk analysis—we’ll need it.
