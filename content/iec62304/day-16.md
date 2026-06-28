---
title: "Day 16: Software System Testing: Plans, Cases & Reports"
date: 2026-06-28
tags: ["til", "iec62304", "system-testing", "class-c"]
---

## What I Explored Today

Today I dug into the formal requirements for Software System Testing under IEC 62304 Clause 6.2. This is the gate between integrated software and a validated medical device. The standard demands three distinct artifacts: a System Test Plan (defining scope, strategy, and pass/fail criteria), System Test Cases (concrete inputs, expected outputs, and environmental conditions), and a System Test Report (traceable evidence that every requirement was exercised). For Class C devices, every test case must trace to at least one SOUP or software requirement, and the report must explicitly state the software version under test. I built a minimal but compliant test harness in Python that generates these artifacts from a YAML specification, then ran it against a simulated infusion pump controller.

## The Core Concept

Why does IEC 62304 mandate this three-document structure instead of just "run tests and log results"? Because medical device recalls are almost always traced back to incomplete test coverage or ambiguous pass/fail criteria. The Plan forces you to declare *how* you'll test before you know the results—eliminating confirmation bias. The Cases force you to write down *exactly* what you expect, including tolerances for analog values. The Report forces you to prove *every* requirement was tested, with a signature block for the test engineer and a separate block for the reviewer (required for Class C). This isn't bureaucracy; it's forensic traceability. When a field failure occurs, you need to know: was this scenario tested? If yes, what was the result? If no, why wasn't it in the plan?

## Key Commands / Configuration / Code

Below is a Python script that reads a YAML test specification, executes the tests against a simulated device, and outputs a compliant test report in Markdown. The YAML format mirrors what you'd store in a requirements management tool like Jama or Polarion.

```python
# system_test_runner.py
# Reads a YAML test spec, runs tests, generates IEC 62304-compliant report

import yaml
import hashlib
from datetime import datetime

# Simulated device under test (DUT) - an infusion pump controller
class InfusionPumpSimulator:
    def __init__(self, version="2.1.0"):
        self.version = version
        self.flow_rate_ml_per_h = 0.0
        self.occlusion_detected = False

    def set_flow_rate(self, rate):
        if rate < 0 or rate > 1000:
            raise ValueError("Rate out of range")
        self.flow_rate_ml_per_h = rate

    def get_flow_rate(self):
        return self.flow_rate_ml_per_h

    def simulate_occlusion(self):
        self.occlusion_detected = True

    def check_occlusion_alarm(self):
        # Alarm must trigger within 3 seconds of occlusion
        return self.occlusion_detected

# Load test specification from YAML
def load_test_spec(yaml_path):
    with open(yaml_path, 'r') as f:
        return yaml.safe_load(f)

# Execute a single test case
def run_test_case(test_case, dut):
    result = {
        "test_id": test_case["id"],
        "requirement_ref": test_case["req_ref"],
        "description": test_case["description"],
        "status": "PASS",
        "actual_output": None,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        # Parse the test action from YAML
        action = test_case["action"]
        if action["type"] == "set_flow_rate":
            dut.set_flow_rate(action["value"])
            actual = dut.get_flow_rate()
            expected = action["expected_value"]
            # Tolerance: ±0.5% for Class C medical devices
            tolerance = expected * 0.005
            if abs(actual - expected) > tolerance:
                result["status"] = "FAIL"
                result["actual_output"] = actual
        elif action["type"] == "occlusion_test":
            dut.simulate_occlusion()
            actual = dut.check_occlusion_alarm()
            if actual != action["expected_value"]:
                result["status"] = "FAIL"
                result["actual_output"] = actual
        else:
            result["status"] = "ERROR"
            result["actual_output"] = f"Unknown action type: {action['type']}"
    except Exception as e:
        result["status"] = "ERROR"
        result["actual_output"] = str(e)
    return result

# Generate IEC 62304 compliant report
def generate_report(test_results, dut_version, test_engineer="Jane Doe"):
    report = f"""# Software System Test Report
**IEC 62304 Clause 6.2**  
**Software Version Under Test:** {dut_version}  
**Test Engineer:** {test_engineer}  
**Date:** {datetime.utcnow().strftime('%Y-%m-%d')}  
**Report Hash:** {hashlib.sha256(str(test_results).encode()).hexdigest()[:16]}

## Test Execution Summary
| Total | Pass | Fail | Error |
|-------|------|------|-------|
| {len(test_results)} | {sum(1 for r in test_results if r['status']=='PASS')} | {sum(1 for r in test_results if r['status']=='FAIL')} | {sum(1 for r in test_results if r['status']=='ERROR')} |

## Detailed Results
| Test ID | Requirement | Description | Status | Actual Output | Timestamp |
|---------|-------------|-------------|--------|---------------|-----------|
"""
    for r in test_results:
        report += f"| {r['test_id']} | {r['requirement_ref']} | {r['description']} | {r['status']} | {r['actual_output'] or 'N/A'} | {r['timestamp']} |\n"

    report += """
## Signatures
**Test Engineer:** _________________________  Date: ________  
**Reviewer (Class C required):** _________________________  Date: ________  
"""
    return report

# Main execution
if __name__ == "__main__":
    # Load test spec (example YAML content shown below)
    spec = load_test_spec("system_tests.yaml")
    dut = InfusionPumpSimulator(version=spec["software_version"])
    results = []
    for tc in spec["test_cases"]:
        results.append(run_test_case(tc, dut))
    report_md = generate_report(results, dut.version)
    with open("system_test_report.md", "w") as f:
        f.write(report_md)
    print(f"Report generated: system_test_report.md")
```

Example YAML test specification (`system_tests.yaml`):

```yaml
software_version: "2.1.0"
test_cases:
  - id: "TC-001"
    req_ref: "REQ-FLOW-001"
    description: "Verify flow rate set to 100 mL/h"
    action:
      type: "set_flow_rate"
      value: 100
      expected_value: 100.0
  - id: "TC-002"
    req_ref: "REQ-ALARM-003"
    description: "Occlusion alarm triggers within 3 seconds"
    action:
      type: "occlusion_test"
      expected_value: true
```

## Common Pitfalls & Gotchas

1. **Missing software version in the report.** IEC 62304 auditors will flag this immediately. The report must state exactly which build/version was tested. I've seen recalls where the report said "v2.1" but the field device was "v2.1.1" with a critical patch. Always include the full version string and a hash of the binary if possible.

2. **Tolerance not defined for analog outputs.** If your test expects 100.0 mL/h but the ADC reads 99.8, is that a pass or fail? The standard requires explicit pass/fail criteria. For Class C, document the tolerance (e.g., ±0.5%) and justify it from the risk analysis. Don't use `assertEqual` on floats.

3. **Test cases that pass by accident.** A common trap: the test action doesn't actually exercise the requirement. For example, testing occlusion alarm by calling `simulate_occlusion()` then immediately checking the flag—but the real device has a debounce timer. Your test must match the real-world timing. Always include a timestamp in the test result to prove the test ran when expected.

## Try It Yourself

1. **Extend the test runner** to support a `wait` action type (e.g., `action: { type: "wait", duration_ms: 3000 }`) and add a test case that verifies the occlusion alarm doesn't trigger falsely after 2 seconds of normal operation.

2. **Create a negative test case** in the YAML spec that attempts to set a flow rate of 1500 mL/h (above the 1000 limit). Verify the runner catches the `ValueError` and marks the test as PASS (because the requirement is to reject invalid inputs).

3. **Add a traceability matrix** to the report generator: parse the YAML spec and output a table mapping each requirement reference to the test IDs that cover it. This is a direct audit artifact for IEC 62304 Clause 6.2.2.

## Next Up

Tomorrow we tackle Regression Testing & Change Control—how to prove that a bug fix didn't break three other things, and how IEC 62304 Clause 6.3 forces you to re-run the right subset of tests based on a change impact analysis. We'll build a Git hook that automatically selects and executes affected test cases.
