---
title: "Day 01: Designing Medical IoT Devices: FDA, EU MDR, ISO 13485 & IEC 60601 Landscape"
date: 2026-10-11
tags: ["til", "medical-iot-dfmea", "regulatory", "medical-device"]
---

## What I Explored Today

I kicked off this series by mapping the regulatory terrain that governs any connected medical device before a single line of firmware gets written. Coming from a background in consumer IoT, I assumed the hard part would be the radio certification or the cloud backend. It turns out the hard part is that the *entire engineering process* is a regulated artifact. Today I focused on four pillars: FDA's 510(k)/De Novo pathways in the US, the EU Medical Device Regulation (MDR 2017/745), ISO 13485 as the quality management system (QMS) backbone, and IEC 60601-1 as the electrical safety standard for anything that touches a patient. The key insight is that these aren't checkboxes at the end of a project — they shape your architecture, your documentation, and even your git workflow from day one.

## The Core Concept

The reason medical device engineering feels different from consumer electronics is **risk management as a first-class design input**. ISO 14971 (referenced by both FDA and MDR) requires you to identify hazards, estimate risk, and demonstrate mitigation *before* you ship. That means your DFMEA isn't a post-hoc document — it's a living artifact that drives design decisions.

The four pillars fit together like this:

- **ISO 13485** is the *process* standard. It says: you must have documented design controls, traceability from requirements → design → verification → validation, and a CAPA (Corrective and Preventive Action) system. FDA recognizes ISO 13485:2016 as a harmonized standard, so a good QMS satisfies both.
- **FDA 510(k)** is the *premarket* pathway for Class II devices. You demonstrate "substantial equivalence" to a predicate device. De Novo is for novel low-to-moderate risk devices with no predicate.
- **EU MDR 2017/745** replaced the MDD in 2021. It's stricter: clinical evaluation reports, UDI (Unique Device Identification), and a Notified Body audit. Class IIa and above require Notified Body involvement.
- **IEC 60601-1** is the *electrical safety* standard. Third edition introduced the concept of "essential performance" — the performance that, if lost, creates unacceptable risk. For a connected device, that might be "the device must alarm within 10 seconds of a sensor fault."

The critical engineering takeaway: **your software architecture must support traceability**. If a requirement says "alarm latency < 10s," you need a test that proves it, and that test needs to be linked in your requirements management tool (Jama, DOORS, or even a well-structured Git repo with YAML).

## Key Commands / Configuration / Code

Here's a practical example of how I structure a requirements file in Git so that traceability is machine-checkable. This is a lightweight approach that works for small teams before they invest in Jama or Polarion.

```yaml
# requirements/REQ-001-alarm-latency.yaml
id: REQ-001
title: "Alarm latency on sensor fault"
description: >
  When the SpO2 sensor reports a fault condition, the device shall
  annunciate a high-priority alarm within 10 seconds.
rationale: "IEC 60601-1-8 alarm system requirements"
risk_control: true
verification_method: test
verification_ref: "tests/alarm_latency_test.py::test_sensor_fault_alarm"
standards:
  - IEC 60601-1-8:2020
  - ISO 14971:2019
status: implemented
```

And a corresponding test stub that the CI pipeline can enforce:

```python
# tests/alarm_latency_test.py
import time
import pytest
from device.alarm import AlarmManager
from device.sensors import SpO2Sensor

def test_sensor_fault_alarm():
    """Verifies REQ-001: alarm within 10s of sensor fault."""
    sensor = SpO2Sensor()
    alarm = AlarmManager()
    sensor.inject_fault("disconnected")

    start = time.monotonic()
    alarm.wait_for_annunciation(timeout=15)
    elapsed = time.monotonic() - start

    assert elapsed < 10.0, f"Alarm latency {elapsed:.2f}s exceeds REQ-001"
    assert alarm.priority == "high"
```

A simple CI check that every `risk_control: true` requirement has a passing test:

```bash
#!/usr/bin/env bash
# scripts/check_traceability.sh
set -euo pipefail

for req in requirements/*.yaml; do
  risk=$(yq '.risk_control' "$req")
  if [ "$risk" = "true" ]; then
    ref=$(yq '.verification_ref' "$req")
    echo "Checking $req -> $ref"
    pytest "$ref" -q || { echo "FAILED: $req"; exit 1; }
  fi
done
```

This gives you a defensible traceability matrix that auditors can inspect, without a six-figure tooling budget.

## Common Pitfalls & Gotchas

1. **Treating IEC 60601-1 as a test-only concern.** Engineers often assume safety is validated at the end. In reality, third edition requires you to define *essential performance* during design input. If your device's essential performance includes "wireless connectivity for remote monitoring," then a dropped BLE connection is a safety event, not just a UX bug. This changes your watchdog and failover design.

2. **Confusing FDA "clearance" with EU "CE marking."** A 510(k) clearance does not grant you EU market access. MDR requires a separate technical file, a clinical evaluation, and a Notified Body. Teams routinely budget for one and get blindsided by the other. Plan for both from the start if you're targeting global markets.

3. **Ignoring software lifecycle standards until late.** IEC 62304 (medical device software lifecycle) is referenced by both FDA and MDR. It mandates software safety classification (Class A/B/C based on harm potential), architecture documentation, and unit-level verification. If you're writing firmware in C on an RTOS, your SOUP (Software of Unknown Provenance) list — every third-party library — must be documented with version and risk analysis. Start that list on day one.

## Try It Yourself

1. **Build a minimal traceability repo.** Create a `requirements/` directory with three YAML files, each with an `id`, `verification_ref`, and `risk_control` field. Write a bash script that fails if any `risk_control: true` requirement lacks a corresponding test file.

2. **Classify your software under IEC 62304.** Pick a hypothetical connected device (e.g., a BLE pulse oximeter). Write down which software items are Class A (no injury possible), Class B (non-serious injury possible), and Class C (death or serious injury possible). Justify each in one sentence.

3. **Draft an essential performance statement.** For the same device, write the one-sentence IEC 60601-1 essential performance claim. Then list two design decisions that change because of it (e.g., watchdog timer, redundant sensor path).

## Next Up

Tomorrow: **Intended Use & Device Classification for Connected Medical Devices** — how a single word in your intended use statement can move you from Class I to Class IIa, and why your Bluetooth stack's failure modes matter to a regulator.
