---
title: "Day 03: Design Controls (21 CFR 820 / QMSR): Inputs, Outputs, Verification & Validation"
date: 2026-10-13
tags: ["til", "medical-iot-dfmea", "design-controls", "qmsr"]
---

## What I Explored Today

Today I mapped the design control requirements from 21 CFR 820.30 onto the firmware architecture of our wearable ECG patch. The FDA's Quality Management System Regulation (QMSR) now harmonizes 21 CFR 820 with ISO 13485:2016, which means the vocabulary shifts slightly (design inputs become "design and development inputs") but the engineering discipline stays the same: every requirement must trace forward to a design output, then to a verification test, then to a validation activity. I spent the afternoon building a traceability matrix in a spreadsheet and wiring our CI pipeline to emit test artifacts that reference requirement IDs. The surprising part was how much of this is just disciplined naming — if your Git commits, unit tests, and hardware test logs all carry the same requirement ID, the audit trail writes itself.

## The Core Concept

Design controls exist because medical device failures are expensive and sometimes fatal, and because "we tested it and it worked" is not evidence. The regulation forces a closed loop:

**Design Inputs** are the *what* — measurable, verifiable requirements derived from user needs, regulatory requirements, and risk analysis. "The device shall sample ECG at 250 Hz ± 1%" is an input. "The device should be accurate" is not.

**Design Outputs** are the *how* — the actual artifacts: schematics, firmware source, PCB layouts, BOMs, and specifications. Each output must be traceable back to at least one input, and each output must be verified against acceptance criteria.

**Verification** answers "did we build the thing right?" — does the firmware sample at 250 Hz? This is objective, testable, and usually automated.

**Validation** answers "did we build the right thing?" — does the clinician find the ECG usable in the intended environment? This requires human factors testing, clinical evaluation, or simulated-use studies.

The QMSR (effective February 2026) replaces the old 820 with ISO 13485 language, but the four pillars remain. The practical difference for engineers is that ISO 13485 explicitly requires a *design and development file* per project, and risk management (ISO 14971) is now baked into the design process rather than bolted on.

The reason this matters for DFMEA is that your failure modes should map directly to design inputs. If a failure mode has no corresponding input, you either have a missing requirement or an irrelevant failure mode.

## Key Commands / Configuration / Code

Here's how I encode requirements in firmware so the traceability is machine-checkable. I use a `requirements.yaml` file at the repo root:

```yaml
# requirements.yaml — single source of truth for design inputs
requirements:
  - id: REQ-ECG-001
    text: "ECG sampling rate shall be 250 Hz ± 1%"
    source: "IEC 60601-2-25 §201.12.1.101"
    verification: "unit test + scope measurement"
    risk_ref: "RISK-0042"  # links to ISO 14971 hazard
  - id: REQ-ECG-002
    text: "Sample timestamp jitter shall be < 1 ms RMS"
    source: "internal design input, derived from REQ-ECG-001"
    verification: "unit test"
    risk_ref: "RISK-0043"
```

Then in firmware, I tag the implementation and the test with the same ID:

```c
// ecg_sampler.c
// Implements REQ-ECG-001, REQ-ECG-002
// Timer configured for 250 Hz on 16 MHz clock:
//   ARR = (16_000_000 / 250) - 1 = 63999
#define ECG_TIMER_ARR  63999U
#define ECG_SAMPLE_HZ  250U

void ecg_timer_init(void) {
    // Prescaler 0, ARR set for 250 Hz update event
    TIM2->PSC = 0;
    TIM2->ARR = ECG_TIMER_ARR;
    TIM2->CR1 |= TIM_CR1_CEN;
}
```

And the unit test carries the ID in its name so CI can grep it:

```python
# test_ecg_sampler.py
def test_REQ_ECG_001_sampling_rate():
    """Verifies REQ-ECG-001: 250 Hz ± 1%"""
    arr = read_register("TIM2_ARR")
    freq = 16_000_000 / (arr + 1)
    assert abs(freq - 250) / 250 < 0.01

def test_REQ_ECG_002_timestamp_jitter():
    """Verifies REQ-ECG-002: jitter < 1 ms RMS"""
    timestamps = capture_timestamps(n=1000)
    jitter_rms = compute_rms_jitter(timestamps)
    assert jitter_rms < 1e-3
```

A small CI script then generates the traceability matrix:

```bash
#!/usr/bin/env bash
# trace.sh — emit requirement → test mapping for the design history file
set -euo pipefail
for req in $(yq '.requirements[].id' requirements.yaml); do
  if grep -rq "$req" tests/; then
    echo "$req: COVERED"
  else
    echo "$req: MISSING TEST" >&2
    exit 1
  fi
done
```

This is the minimum viable design control loop for firmware. The design history file (DHF) is just the collection of these artifacts plus the review records.

## Common Pitfalls & Gotchas

**1. Treating verification and validation as synonyms.** Verification is bench-level and objective; validation is use-level and often subjective. A unit test proving your BLE stack transmits at the correct power is verification. A study showing a nurse can pair the device in under 30 seconds during a code blue is validation. Auditors will ask for both, and they are not interchangeable.

**2. Orphan design outputs.** Every schematic net, every firmware module, every mechanical part must trace back to at least one input. If you add a feature "because it was easy," you now have an untraceable output. Either write the input retroactively (with justification) or remove the feature. I've seen 510(k) submissions delayed weeks over orphan features.

**3. Requirements that aren't verifiable.** "The device shall be reliable" fails design control review. Rewrite as "The device shall have a mean time between failures (MTBF) of ≥ 50,000 hours per Telcordia SR-332." If you can't write a test for it, it's not a requirement — it's a wish.

**4. Forgetting to version the requirements.** When REQ-ECG-001 changes from 250 Hz to 500 Hz, the old test must be archived, not deleted. The DHF is a historical record. Use Git tags or a requirements management tool (DOORS, Jama, or even a well-disciplined Git repo) so you can reconstruct what the design looked like at any point.

## Try It Yourself

1. **Build a minimal traceability matrix.** Take an existing firmware project and create a `requirements.yaml` with 5 requirements. Add a `trace.sh` script that fails CI if any requirement lacks a matching test. Run it against your current test suite and count the gaps.

2. **Classify your tests.** Go through your test suite and label each test as either *verification* (objective, bench-level) or *validation* (use-level, human factors). Most embedded projects have zero validation tests — identify what a validation test would look like for your device's primary use case.

3. **Write a design input from a risk.** Pick one hazard from your preliminary risk analysis (e.g., "loss of ECG signal during arrhythmia detection"). Write a measurable design input that mitigates it, then write the verification test that proves the mitigation works. This is the DFMEA-to-design-control handoff in miniature.

## Next Up

Tomorrow: **ISO 14971 Risk Management & Where DFMEA Fits.** We'll walk through the risk management file structure, the difference between hazard, hazardous situation, and harm, and why DFMEA is a *tool* inside ISO 14971 rather than a replacement for it. Bring your severity and probability tables — we're going to build a risk matrix that actually maps to your design inputs.
