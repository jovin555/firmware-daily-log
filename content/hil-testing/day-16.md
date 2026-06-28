---
title: "Day 16: IEC 62304-Compliant Test Documentation from CI"
date: 2026-06-28
tags: ["til", "hil-testing", "iec62304", "documentation"]
---

## What I Explored Today

Today I tackled the gap between running automated HIL tests and producing the documentation required for IEC 62304 software classification. Specifically, I automated the generation of Software Unit Verification Reports and Integration Test Reports directly from CI pipeline artifacts. The goal: every test run produces a traceable, version-controlled document that maps requirements → test cases → results → code changes — without manual copy-paste.

## The Core Concept

IEC 62304 requires documented evidence that software units and integrated components have been verified. For Class B and C devices, this means:

- Each software unit must have a corresponding verification result
- Integration tests must trace to software architecture items
- All test results must be linked to a specific software version
- Documentation must be auditable and reproducible

The naive approach is to write these reports by hand after testing. That fails because: (1) it’s slow, (2) it introduces transcription errors, (3) the report date never matches the test execution date, and (4) auditors will notice.

The better approach: generate the report *from the same CI run that executed the tests*. Use the test runner’s output (JUnit XML, JSON, or custom logs) plus the Git commit hash and a requirements traceability matrix (RTM) stored as YAML. A post-processing script assembles these into a compliant PDF or HTML report.

## Key Commands / Configuration / Code

Here’s the pipeline stage I built today. It runs after all HIL tests pass (or fail) and generates the IEC 62304 report.

```yaml
# .gitlab-ci.yml (or GitHub Actions equivalent)
generate_iec62304_report:
  stage: documentation
  needs: ["hil_tests"]
  script:
    - pip install junit2html reportlab pyyaml
    - |
      python3 generate_report.py \
        --junit-xml results/hil_results.xml \
        --rtm config/requirements_traceability.yaml \
        --commit-hash $CI_COMMIT_SHA \
        --build-id $CI_PIPELINE_ID \
        --output reports/verification_report_$CI_PIPELINE_ID.pdf
  artifacts:
    paths:
      - reports/verification_report_*.pdf
    expire_in: 1 year
```

The core Python script:

```python
# generate_report.py
import sys, yaml, xml.etree.ElementTree as ET
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def parse_junit(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    testsuite = root[0]
    results = []
    for tc in testsuite.findall('testcase'):
        name = tc.get('name')
        classname = tc.get('classname')
        failure = tc.find('failure')
        status = 'PASS' if failure is None else 'FAIL'
        results.append({'name': name, 'class': classname, 'status': status})
    return results

def load_rtm(yaml_path):
    with open(yaml_path) as f:
        return yaml.safe_load(f)

def build_report(test_results, rtm, commit, build_id, output_path):
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(f"IEC 62304 Verification Report", styles['Title']))
    story.append(Paragraph(f"Build ID: {build_id} | Commit: {commit}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Traceability table
    story.append(Paragraph("Requirements Traceability", styles['Heading2']))
    table_data = [['Requirement ID', 'Test Case', 'Status']]
    for req in rtm['requirements']:
        for test_name in req['test_cases']:
            match = [t for t in test_results if t['name'] == test_name]
            status = match[0]['status'] if match else 'NOT EXECUTED'
            table_data.append([req['id'], test_name, status])
    t = Table(table_data)
    story.append(t)
    story.append(Spacer(1, 12))

    # Detailed results
    story.append(Paragraph("Detailed Test Results", styles['Heading2']))
    for tr in test_results:
        story.append(Paragraph(f"{tr['class']}.{tr['name']}: {tr['status']}", styles['Code']))

    doc.build(story)

if __name__ == '__main__':
    results = parse_junit(sys.argv[1])
    rtm = load_rtm(sys.argv[2])
    build_report(results, rtm, sys.argv[3], sys.argv[4], sys.argv[5])
```

The RTM YAML file that lives in your repo:

```yaml
# config/requirements_traceability.yaml
requirements:
  - id: "REQ-SW-001"
    description: "System shall initialize ADC at boot"
    test_cases: ["test_adc_init", "test_adc_voltage_range"]
  - id: "REQ-SW-002"
    description: "BLE advertisement interval shall be 100ms ±10ms"
    test_cases: ["test_ble_adv_interval", "test_ble_adv_power"]
```

## Common Pitfalls & Gotchas

1. **JUnit XML schema variations** – Different test frameworks (pytest, Google Test, Unity) emit JUnit XML with slightly different element names. Google Test uses `<testcase>` with `name` and `classname`, but pytest may nest `<testcase>` inside `<test suite>`. Always validate with `xmllint --schema junit.xsd` before feeding to your report generator. I wasted an hour debugging a missing `classname` attribute.

2. **RTM drift** – The YAML traceability matrix will inevitably fall out of sync with actual test names. Mitigate by adding a CI job that validates every test name in the RTM exists in the test binary. Fail the pipeline if there’s a mismatch. I use a simple grep: `grep -r "def test_" tests/ | cut -d' ' -f2 | sort > actual_tests.txt` then diff against the RTM.

3. **Report generation on test failure** – IEC 62304 requires documenting failures too. Don’t gate the report generation on test success. Run it in a `after_script` or `always()` block so the report captures the failure evidence. Auditors want to see *what failed and when*, not just green checkmarks.

## Try It Yourself

1. **Add an RTM validation job** – In your CI pipeline, add a stage that parses your RTM YAML and checks every `test_cases` entry exists in your test binary. Fail the pipeline if there’s a mismatch.

2. **Generate a PDF report from a real HIL run** – Take your existing HIL test JUnit output and feed it into the script above. Modify the table to include timestamps and test duration columns. Verify the PDF opens and contains correct data.

3. **Version-stamp the report** – Embed the Git commit hash and CI build ID into the PDF metadata (not just the page content). Use `reportlab`’s `pdfinfo` dictionary. Then write a quick script to extract that metadata and confirm it matches the pipeline run.

## Next Up

Tomorrow: **HIL for Zephyr BLE: Testing BLE Advertisements** – We’ll set up a Zephyr-based BLE peripheral on an nRF52840 DK, use a second board as a scanner, and verify advertisement interval, payload content, and TX power under real RF conditions — all automated in CI.
