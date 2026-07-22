---
title: "Day 22: Compliance Artifacts: Auto-Generating Traceability from CI Runs"
date: 2026-07-22
tags: ["til", "embedded-cicd", "traceability", "compliance"]
---

## What I Explored Today

Today I tackled one of the most painful parts of embedded release engineering: generating traceability matrices from CI pipeline runs. In regulated environments (medical devices, automotive, aerospace), you need to prove that every requirement has a corresponding test case, every test case has a pass/fail result, and every binary was built from known source. I built a pipeline stage that scrapes Jira for requirements, parses test results from Zephyr Scale, and cross-references them against Git commit SHAs to produce a verifiable Requirements Traceability Matrix (RTM) as a CI artifact.

## The Core Concept

Traceability isn't just about checking boxes for auditors. It's the only way to answer "what changed and why" when a field failure occurs. In embedded systems, where firmware updates can brick devices, you need cryptographic proof that the binary in the field matches the source, tests, and requirements that were approved.

The key insight: **traceability must be generated at build time, not retrofitted**. If you wait until release day to map requirements to tests, you'll miss gaps. By embedding traceability generation into CI, every pipeline run produces a compliance artifact that links:
- Git commit → binary hash
- Binary hash → test results
- Test results → requirements

This creates an immutable chain of custody. When an auditor asks "show me the test that verified requirement REQ-042 for firmware v3.1.2," you point to the RTM artifact in your CI run, which contains the exact test output, the binary SHA256, and the commit that produced it.

## Key Commands / Configuration / Code

Here's a practical pipeline stage that generates a traceability matrix. I'm using GitLab CI with a Python script, but the pattern applies to any system.

First, the `.gitlab-ci.yml` stage:

```yaml
traceability:
  stage: compliance
  image: python:3.11-slim
  variables:
    JIRA_PROJECT: "EMB"
    TEST_MANAGEMENT: "zephyr"
    BINARY_HASH: "${CI_COMMIT_SHA}"
  script:
    - pip install jira python-dotenv requests
    - python generate_rtm.py
  artifacts:
    paths:
      - rtm_report.html
      - rtm_report.json
    expire_in: 1 year
  only:
    - tags
```

Now the core `generate_rtm.py` script:

```python
#!/usr/bin/env python3
"""Generate Requirements Traceability Matrix from CI run data."""

import os
import json
import hashlib
from jira import JIRA
from datetime import datetime

# Configuration from CI environment
JIRA_URL = os.environ.get('JIRA_URL')
JIRA_TOKEN = os.environ.get('JIRA_TOKEN')
CI_COMMIT_SHA = os.environ.get('CI_COMMIT_SHA')
CI_PIPELINE_ID = os.environ.get('CI_PIPELINE_ID')
CI_JOB_ID = os.environ.get('CI_JOB_ID')

# 1. Fetch requirements from Jira
jira = JIRA(server=JIRA_URL, token_auth=JIRA_TOKEN)
issues = jira.search_issues(
    f'project = {os.environ["JIRA_PROJECT"]} AND issuetype = Requirement AND status = Approved',
    fields='key,summary,description'
)

# 2. Parse test results from test report (assumes JUnit XML)
test_results = {}
with open('test-results.xml', 'r') as f:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(f.read())
    for testcase in root.iter('testcase'):
        test_name = testcase.get('name')
        # Extract requirement key from test name pattern: test_REQ-042_foo
        req_key = None
        if 'REQ-' in test_name:
            req_key = test_name.split('_')[1]
        test_results[test_name] = {
            'status': 'pass' if testcase.find('failure') is None else 'fail',
            'requirement': req_key,
            'time': testcase.get('time')
        }

# 3. Compute binary hash (assumes firmware.bin in artifacts)
binary_hash = None
binary_path = 'firmware.bin'
if os.path.exists(binary_path):
    with open(binary_path, 'rb') as f:
        binary_hash = hashlib.sha256(f.read()).hexdigest()

# 4. Build traceability matrix
rtm = {
    'pipeline_id': CI_PIPELINE_ID,
    'job_id': CI_JOB_ID,
    'commit_sha': CI_COMMIT_SHA,
    'binary_sha256': binary_hash,
    'generated_at': datetime.utcnow().isoformat(),
    'requirements': []
}

for issue in issues:
    req_entry = {
        'requirement_key': issue.key,
        'summary': issue.fields.summary,
        'test_cases': [],
        'coverage_status': 'untested'
    }
    # Find matching tests
    for test_name, result in test_results.items():
        if result['requirement'] == issue.key:
            req_entry['test_cases'].append({
                'test_name': test_name,
                'status': result['status'],
                'duration': result['time']
            })
    # Determine coverage
    if req_entry['test_cases']:
        all_pass = all(t['status'] == 'pass' for t in req_entry['test_cases'])
        req_entry['coverage_status'] = 'passed' if all_pass else 'failed'
    rtm['requirements'].append(req_entry)

# 5. Write artifacts
with open('rtm_report.json', 'w') as f:
    json.dump(rtm, f, indent=2)

# Generate HTML report for human readability
html = f"""<html><body>
<h1>Traceability Report - Pipeline {CI_PIPELINE_ID}</h1>
<p>Commit: {CI_COMMIT_SHA}</p>
<p>Binary SHA256: {binary_hash}</p>
<table border='1'>
<tr><th>Requirement</th><th>Test</th><th>Status</th><th>Coverage</th></tr>
"""
for req in rtm['requirements']:
    for tc in req['test_cases']:
        html += f"<tr><td>{req['requirement_key']}</td><td>{tc['test_name']}</td><td>{tc['status']}</td><td>{req['coverage_status']}</td></tr>"
html += "</table></body></html>"

with open('rtm_report.html', 'w') as f:
    f.write(html)

print(f"RTM generated: {len(rtm['requirements'])} requirements, {sum(len(r['test_cases']) for r in rtm['requirements'])} test cases")
```

## Common Pitfalls & Gotchas

**1. Test naming conventions must be strict.** If your test names don't embed requirement IDs in a parseable format (e.g., `test_REQ-042_validate_checksum`), your script can't map them. I've seen teams waste days manually mapping because someone used `test_validate_checksum_42` instead. Enforce a naming convention in your test framework and validate it in a pre-commit hook.

**2. Jira API rate limits will bite you.** If you have 500+ requirements and run this on every pipeline, you'll hit rate limits. Cache the requirements list in a CI cache keyed on the Jira project version, or only run the full traceability on tagged releases (as shown in the `only: - tags` clause above).

**3. Binary hash must be computed from the exact artifact, not the commit.** Two different builds from the same commit can produce different binaries if build timestamps or compiler flags differ. Always hash the actual `.bin` or `.hex` file, not the Git tree hash. Store this hash in your artifact metadata so you can verify field devices later.

## Try It Yourself

1. **Add a test naming convention check** to your CI pipeline that fails if any test case name doesn't match `test_REQ-\d+_.*`. Use a simple regex in a shell script or Python.

2. **Extend the RTM script** to include a "gaps" section that lists requirements with zero test coverage. Output this as a separate artifact file that your release manager can review.

3. **Integrate binary signing** into the traceability artifact: after generating the RTM JSON, sign it with your GPG release key and include the signature file as an artifact. This makes the traceability report itself tamper-evident.

## Next Up

Tomorrow's post: **Case Study: Building a Zero-Touch Pipeline from Commit to Field** — we'll walk through a complete end-to-end pipeline for a medical device firmware update, from developer commit through automated compliance checks, signed binary generation, and OTA deployment, all without human intervention.
