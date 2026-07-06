---
title: "Day 24: Full Review: Compliance Checklist & Mock Audit"
date: 2026-07-06
tags: ["til", "iec62304", "review", "checklist"]
---

## What I Explored Today

Today I ran a full compliance review against our Class B medical device firmware, using a structured checklist derived from IEC 62304:2006 + AMD1:2015. The goal was to simulate a mock audit—identifying gaps before the real notified body visit. I walked through every clause from software development planning (clause 5) through software maintenance (clause 6), verifying traceability, risk management integration, and documentation artifacts. The exercise revealed three critical findings: missing anomaly resolution records for two low-severity bugs, an untagged baseline for our RTOS configuration, and a gap in SOUP (Software of Unknown Provenance) anomaly handling. Here’s the full breakdown of the checklist and audit process.

## The Core Concept

A compliance checklist is not a bureaucratic exercise—it’s a risk control. IEC 62304 requires that every software item (including SOUP) be developed under a quality management system (ISO 13485) with documented evidence. A mock audit forces you to prove, not just claim, compliance. The key insight: auditors look for *traceability chains*. For example, a software requirement must link to a design specification, which links to a unit test, which links to a risk control measure. If any link is missing, it’s a non-conformance. The checklist I built today covers five domains: planning, requirements, architecture, detailed design/unit implementation, and integration/testing. Each domain has pass/fail criteria based on explicit clause references.

## Key Commands / Configuration / Code

Below is the core of my compliance checklist script, written in Python, that scans a Git repository for required artifacts and validates traceability. I run this weekly in CI.

```python
#!/usr/bin/env python3
"""
iec62304_compliance_checker.py
Scans repo for required artifacts and validates traceability.
Assumes: requirements in docs/reqs/, design in docs/design/, tests in tests/
"""

import os
import re
import subprocess
from pathlib import Path

REQUIRED_ARTIFACTS = {
    "SDP": "docs/planning/software_development_plan.md",
    "SRS": "docs/reqs/software_requirements_specification.md",
    "SAS": "docs/design/software_architecture_specification.md",
    "SDS": "docs/design/software_detailed_design.md",
    "STR": "docs/test/software_test_report.md",
    "ANOMALY_LOG": "docs/anomaly_log.md",
}

def check_artifact_exists(path):
    """Return True if file exists and is non-empty."""
    p = Path(path)
    return p.exists() and p.stat().st_size > 0

def check_traceability():
    """
    Verify that every requirement ID in SRS has a corresponding test case.
    Pattern: REQ-XXX
    """
    srs_path = REQUIRED_ARTIFACTS["SRS"]
    if not check_artifact_exists(srs_path):
        return False, "SRS missing"
    
    with open(srs_path) as f:
        content = f.read()
    
    req_ids = re.findall(r'REQ-\d{3}', content)
    if not req_ids:
        return False, "No REQ-XXX patterns found in SRS"
    
    # Check each REQ appears in at least one test file
    test_dir = Path("tests")
    test_files = list(test_dir.rglob("*.py")) + list(test_dir.rglob("*.c"))
    test_content = ""
    for tf in test_files:
        test_content += tf.read_text()
    
    missing = [rid for rid in req_ids if rid not in test_content]
    if missing:
        return False, f"Missing tests for: {', '.join(missing)}"
    return True, "All requirements traced"

def check_git_tags():
    """Ensure at least one release tag exists for baseline."""
    result = subprocess.run(
        ["git", "tag", "--list", "v*"],
        capture_output=True, text=True
    )
    tags = result.stdout.strip().split("\n")
    if not tags or tags[0] == "":
        return False, "No version tags found"
    return True, f"Found {len(tags)} tags"

def run_audit():
    findings = []
    # 1. Check all required artifacts exist
    for name, path in REQUIRED_ARTIFACTS.items():
        if not check_artifact_exists(path):
            findings.append(f"MISSING: {name} at {path}")
    
    # 2. Traceability check
    trace_ok, trace_msg = check_traceability()
    if not trace_ok:
        findings.append(f"TRACE FAIL: {trace_msg}")
    
    # 3. Baseline check
    tag_ok, tag_msg = check_git_tags()
    if not tag_ok:
        findings.append(f"BASELINE FAIL: {tag_msg}")
    
    return findings

if __name__ == "__main__":
    issues = run_audit()
    if issues:
        print("COMPLIANCE ISSUES FOUND:")
        for i in issues:
            print(f"  - {i}")
        exit(1)
    else:
        print("All checks passed.")
```

**Configuration snippet** for a `.gitlab-ci.yml` job that runs this weekly:

```yaml
compliance-audit:
  stage: test
  script:
    - python3 iec62304_compliance_checker.py
  only:
    - schedules  # runs every Monday at 08:00
  artifacts:
    reports:
      junit: compliance-report.xml
```

## Common Pitfalls & Gotchas

1. **Assuming SOUP is exempt from anomaly handling.** IEC 62304 clause 8.2.2 requires that anomalies in SOUP (e.g., a known bug in FreeRTOS) be documented and risk-assessed. I found a team that had a known SOUP crash bug but no entry in the anomaly log—this is a major non-conformance. Always treat SOUP anomalies like your own code.

2. **Forgetting to baseline configuration items.** Auditors will ask: “Show me the exact software version that was verified.” If your Git tags are missing or your build artifacts aren’t pinned to a commit hash, you fail. Use `git tag -a v1.2.3 -m "Release candidate for audit"` and store the hash in your release notes.

3. **Traceability only forward, not backward.** Many teams trace requirements to tests, but not tests back to requirements. IEC 62304 clause 5.2.6 demands bidirectional traceability. Your test report must reference the requirement ID, and your requirement spec must reference the test case ID. I use a simple cross-reference table in Markdown:

```markdown
| Requirement ID | Test Case ID | Risk Control ID |
|----------------|--------------|-----------------|
| REQ-001        | TC-001       | RC-001          |
```

## Try It Yourself

1. **Run the compliance checker** on your own repo. Copy the Python script above, adjust the `REQUIRED_ARTIFACTS` paths to match your project, and execute it. Fix any missing artifacts.

2. **Perform a manual traceability audit** on one software requirement. Pick a requirement from your SRS, then manually trace it to: design document, unit test, integration test, and risk control measure. Document any gaps.

3. **Create a mock audit checklist** for your team. Use the five domains (planning, requirements, architecture, design/unit, integration/test) and list 3-5 pass/fail criteria per domain. Run a 30-minute meeting where each team member presents evidence for one domain.

## Next Up

Tomorrow, we’ll do a **Full Review** of the entire IEC 62304 lifecycle—from concept to decommissioning—with a focus on how to prepare for a real notified body audit. We’ll cover common auditor questions and how to handle findings.
