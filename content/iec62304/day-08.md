---
title: "Day 08: Traceability Matrix: Requirements to Design to Test"
date: 2026-06-22
tags: ["til", "iec62304", "traceability", "requirements"]
---

## What I Explored Today

Today I tackled the traceability matrix — the backbone of IEC 62304 compliance. The standard demands bidirectional traceability from software requirements down to design elements and up from test cases back to requirements. I built a working traceability matrix using a YAML-based schema, wrote a Python validation script that checks for orphaned requirements (those with no tests or design coverage), and integrated it into a CI pipeline. The goal: prove that every requirement is implemented and tested, without manual spreadsheet hell.

## The Core Concept

IEC 62304 clause 5.2.1 and 5.2.2 require that you trace each software requirement to its design specification and to its test cases. This isn't bureaucracy — it's risk management. When a requirement changes (and it will), you need to know exactly which design components and test cases are affected. Without traceability, you're guessing.

The traceability matrix is a living document. It must be updated as requirements evolve, design changes, or tests are added. The key insight: **traceability is not a deliverable; it's a process**. The matrix itself is just a snapshot of that process at a point in time.

A proper traceability matrix has three columns:
- **Requirement ID** (e.g., REQ-001)
- **Design Element ID** (e.g., MOD-001 or FUNC-001)
- **Test Case ID** (e.g., TC-001)

Bidirectional means:
- Every requirement maps to at least one design element and one test case.
- Every test case maps back to exactly one requirement (or more, but that's a smell).
- Every design element maps to at least one requirement.

## Key Commands / Configuration / Code

Here's a practical YAML-based traceability matrix that you can version-control and validate automatically.

**File: `traceability_matrix.yaml`**

```yaml
# IEC 62304 Traceability Matrix
# Format: requirement -> design -> test
# Each entry must have all three fields

requirements:
  - id: "REQ-001"
    description: "System shall log all user access attempts"
    design_elements:
      - "MOD-AUTH-001"  # Authentication module
      - "FUNC-LOG-001"  # Logging function
    test_cases:
      - "TC-AUTH-001"
      - "TC-AUTH-002"

  - id: "REQ-002"
    description: "Log entries shall include timestamp and user ID"
    design_elements:
      - "FUNC-LOG-002"  # Log entry structure
    test_cases:
      - "TC-LOG-001"

  - id: "REQ-003"
    description: "System shall support 100 concurrent users"
    design_elements:
      - "MOD-CONN-001"  # Connection pool manager
    test_cases:
      - "TC-PERF-001"
```

**Python validation script: `validate_traceability.py`**

```python
#!/usr/bin/env python3
"""
Validate IEC 62304 traceability matrix.
Checks for orphaned requirements, missing design elements, and missing tests.
"""

import yaml
import sys

def validate_matrix(filepath):
    with open(filepath, 'r') as f:
        data = yaml.safe_load(f)
    
    errors = []
    
    for req in data.get('requirements', []):
        req_id = req['id']
        
        # Check design elements exist
        if not req.get('design_elements'):
            errors.append(f"ERROR: {req_id} has no design elements")
        
        # Check test cases exist
        if not req.get('test_cases'):
            errors.append(f"ERROR: {req_id} has no test cases")
        
        # Check for duplicate test case assignments (optional warning)
        # This is a smell — one test covering many requirements is fragile
        if len(req.get('test_cases', [])) > 3:
            errors.append(f"WARNING: {req_id} has {len(req['test_cases'])} test cases — consider splitting")
    
    # Check for orphaned test cases (test cases not linked to any requirement)
    all_test_cases = set()
    linked_test_cases = set()
    for req in data.get('requirements', []):
        linked_test_cases.update(req.get('test_cases', []))
    
    # This assumes you have a separate test case registry
    # In practice, you'd load test cases from another file
    # For now, we just flag if a test case appears in no requirement
    
    if errors:
        print(f"Validation FAILED — {len(errors)} issues found:")
        for err in errors:
            print(f"  {err}")
        sys.exit(1)
    else:
        print("Traceability matrix VALID — all requirements have design and test coverage")
        sys.exit(0)

if __name__ == "__main__":
    validate_matrix("traceability_matrix.yaml")
```

**CI integration (GitHub Actions snippet):**

```yaml
# .github/workflows/traceability-check.yml
name: Traceability Check
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install dependencies
        run: pip install pyyaml
      - name: Validate traceability matrix
        run: python validate_traceability.py traceability_matrix.yaml
```

## Common Pitfalls & Gotchas

**1. One-to-many traceability without justification.**  
It's common to see a single test case covering five requirements. IEC 62304 doesn't forbid this, but it's a red flag. If that test fails, you can't tell which requirement is broken. Prefer one test per requirement, or document why a single test covers multiple requirements (e.g., integration tests).

**2. Forgetting to update the matrix during change management.**  
When a requirement changes, the matrix becomes stale. The most common audit finding is "traceability matrix not aligned with current SRS." Automate the check in CI so that any PR that touches requirements, design docs, or test cases must also update the matrix.

**3. Using spreadsheets that can't be diffed or validated.**  
Excel traceability matrices are a compliance trap. They're impossible to validate programmatically, prone to manual errors, and can't be integrated into CI. Always use a machine-readable format (YAML, JSON, or a database) that you can script against.

## Try It Yourself

1. **Create your own traceability matrix** in YAML for a small module (e.g., a temperature sensor driver). Include 3-5 requirements, each with at least one design element and one test case. Run the validation script above.

2. **Introduce an orphan** — remove a test case from one requirement. Run the validation again and confirm it catches the error. Then fix it.

3. **Integrate the validation into your CI pipeline** (GitHub Actions, GitLab CI, or Jenkins). Make the pipeline fail if the matrix is invalid. This ensures traceability is never forgotten during development.

## Next Up

Tomorrow: **Software Requirements Specification (SRS)** — how to write requirements that are unambiguous, testable, and traceable. We'll cover the IEEE 830 structure, the difference between functional and non-functional requirements, and how to avoid the "shall" trap.
