---
title: "Day 20: Design Verification Planning Driven by the DFMEA"
date: 2026-10-30
tags: ["til", "medical-iot-dfmea", "verification", "test-planning"]
---

# Day 20: Design Verification Planning Driven by the DFMEA

## What I Explored Today

Today I closed the loop between the DFMEA we've been building over the past three weeks and the actual Design Verification (DV) plan. The realization that hit me: a DFMEA that doesn't generate traceable verification activities is just expensive documentation. I spent the day mapping every high-RPN failure mode to a concrete verification method, acceptance criterion, and test artifact — and building a small Python tool to keep the traceability matrix honest. This is the bridge between "we analyzed risk" and "we proved the risk is controlled," which is exactly what a 510(k) reviewer or ISO 13485 auditor wants to see.

## The Core Concept

Design Verification answers one question: *does the design output meet the design input?* The DFMEA answers a different but complementary question: *where can the design fail, and how bad is it?* The linkage is what matters. Every failure mode with a Detection score above 1 is essentially an admission that we don't yet have proof the failure is controlled. Verification is how we buy that proof down.

The mechanism is a **traceability matrix**: each DFMEA line item (failure mode + cause + effect) maps to one or more verification activities, each with a method (Test, Analysis, Inspection, Demonstration — TAID), a sample size, an acceptance criterion, and a linked test protocol ID. The RPN (or better, Action Priority per AIAG-VDA) drives *how much* verification rigor you apply. A severity-9, occurrence-4, detection-6 failure mode on a battery charging circuit gets a dedicated bench test with accelerated cycling; a severity-3 cosmetic issue gets a visual inspection in the DVT build.

The subtle part: verification must target the **cause**, not just the failure mode. If the DFMEA says "solder fatigue on BGA due to thermal cycling," a functional power-on test doesn't verify anything useful — you need a thermal cycling test with in-situ resistance monitoring (IPC-9701 style) to actually stress the cause. This is where most DV plans I've reviewed fall apart: they test the function, not the failure mechanism.

## Key Commands / Configuration / Code

I built a lightweight traceability checker. The DFMEA lives in a CSV export; the DV plan in another. The script flags orphaned high-RPN items.

```python
# dfmea_dv_trace.py — flag DFMEA items lacking verification coverage
import csv
from dataclasses import dataclass

@dataclass
class DfmeaItem:
    id: str
    failure_mode: str
    severity: int
    occurrence: int
    detection: int
    @property
    def rpn(self) -> int:
        return self.severity * self.occurrence * self.detection

# Load DFMEA (columns: id, failure_mode, sev, occ, det)
dfmea = []
with open("dfmea.csv") as f:
    for row in csv.DictReader(f):
        dfmea.append(DfmeaItem(
            id=row["id"], failure_mode=row["failure_mode"],
            severity=int(row["sev"]), occurrence=int(row["occ"]),
            detection=int(row["det"])))

# Load DV plan (columns: dfmea_id, method, protocol_id, acceptance)
covered = set()
with open("dv_plan.csv") as f:
    for row in csv.DictReader(f):
        covered.add(row["dfmea_id"])

# Threshold: anything with RPN >= 100 or Severity >= 9 must be covered
for item in dfmea:
    needs_cover = item.rpn >= 100 or item.severity >= 9
    if needs_cover and item.id not in covered:
        print(f"UNCOVERED: {item.id} RPN={item.rpn} S={item.severity} "
              f"-> {item.failure_mode}")
```

For the actual test execution, I tag each pytest case with the DFMEA ID so CI produces a machine-readable coverage report:

```python
# test_battery_thermal.py
import pytest

@pytest.mark.dfmea("FM-014")  # thermal runaway on charge
@pytest.mark.verification
def test_charge_thermal_cutoff():
    # Acceptance: cutoff before cell temp exceeds 45 C at 1C charge
    result = run_charge_profile(rate_c=1.0, ambient_c=40)
    assert result.max_cell_temp_c < 45.0
    assert result.cutoff_triggered is True
```

```bash
# Run only verification-tagged tests and emit JUnit XML for the traceability tool
pytest -m verification --junitxml=reports/dv_results.xml

# Generate the coverage cross-reference (pytest + junit parser)
python dfmea_dv_trace.py --results reports/dv_results.xml --out trace_matrix.csv
```

The `--junitxml` output is the key: it lets the traceability script confirm not just that a test *exists* but that it *passed* on the current build, which is what the DHF needs.

## Common Pitfalls & Gotchas

1. **Testing the effect, not the cause.** A DFMEA line for "MCU brownout due to insufficient bulk capacitance" gets verified by a supply-ramp test with a programmable source (e.g., a Keysight N6705C doing fast slew), not by a normal power-on. If your test doesn't reproduce the cause, it doesn't reduce Detection.

2. **RPN thresholds that ignore severity.** A severity-9 failure mode with RPN 90 (S9×O2×D5) falls below a naive RPN-100 cutoff but absolutely needs verification. Always gate on `severity >= 9 OR rpn >= threshold` — this is why AIAG-VDA moved to Action Priority tables.

3. **Sample size of one.** Verification with n=1 proves the design *can* work, not that it *does* across the population. For anything with an occurrence score ≥ 3, the DV plan needs a statistically justified sample (attribute sampling per ANSI/ASQ Z1.4, or variable sampling with a stated confidence/reliability target like 90/95).

## Try It Yourself

1. Export your current DFMEA to CSV and run the traceability script above. Count how many items with Severity ≥ 9 have no linked verification activity — that's your gap list for tomorrow's DV plan review.

2. Take one high-RPN failure mode and write a pytest (or equivalent) case that stresses the *cause* rather than the function. Tag it with the DFMEA ID and confirm it appears in the JUnit XML output.

3. Add an `acceptance_criterion` column to your DV plan CSV and populate it for every row. If you can't state a numeric pass/fail threshold, the verification isn't defined yet.

## Next Up

Tomorrow: **Reliability Testing: HALT, Accelerated Life & Environmental Testing** — how we take the failure modes that verification can't fully retire and stress them to destruction, plus how to translate HALT findings back into DFMEA occurrence scores.
