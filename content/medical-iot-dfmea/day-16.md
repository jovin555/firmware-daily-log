---
title: "Day 16: DFMEA: Electrical Safety & EMC (IEC 60601-1, IEC 60601-1-2)"
date: 2026-10-26
tags: ["til", "medical-iot-dfmea", "iec60601", "emc"]
---

# Day 16: DFMEA: Electrical Safety & EMC (IEC 60601-1, IEC 60601-1-2)

## What I Explored Today

Today I dug into the electrical safety and EMC failure modes for our wearable SpO₂/ECG patch and mapped them into the DFMEA. The interesting part wasn't the standards themselves — it was realizing that most EMC and safety failures aren't "component failed" but "design margin was consumed by a decision made in another subsystem." A 2 mm creepage reduction to fit a smaller enclosure, a switching regulator placed 8 mm from the ECG front-end, a Y-capacitor omitted to save BOM cost — each of these is a DFMEA line item with a severity of 9 or 10 under IEC 60601-1 (patient-connected, Type BF applied part). I spent the afternoon converting test-lab findings from our pre-compliance run into failure modes, effects, and detection controls, and re-scoring RPNs.

## The Core Concept

IEC 60601-1 is about *not hurting the patient*; IEC 60601-1-2 is about *the device working in the electromagnetic environment it will actually live in*. In DFMEA terms these are two different failure families that share a root cause: insufficient design margin.

The "why" that matters for DFMEA is that both standards are **risk-management standards**, not pass/fail checklists. Clause 4.2 of 60601-1 explicitly requires a risk management process (ISO 14971) to justify any deviation. That means every DFMEA line item touching patient connections, isolation, or EMC must trace to a hazard, and the detection control must be something you can actually *measure* — not "design review." A DFMEA that says "Detection: EMC testing" with a detection score of 3 is lying to itself; the test either exists in the verification plan with a pass criterion or it doesn't.

The second "why": EMC failures are almost always **coupling-path failures**, not source failures. The DFMEA should model the coupling path (conducted, radiated, capacitive, inductive) as the failure mechanism, because that's where the design lever is. You rarely eliminate the noise source; you break the path.

For a Type BF applied part, the numbers that drive severity are: patient leakage current ≤ 100 µA (normal condition, AC), ≤ 500 µA (single fault), and 2× MOPP isolation between mains and applied part. Any DFMEA line where a single component failure could bridge that isolation is severity 10, period.

## Key Commands / Configuration / Code

Pre-compliance EMC testing is where DFMEA detection controls get validated. Here's what I actually run to correlate lab results with design intent.

```bash
# Conducted emissions pre-scan, 150 kHz–30 MHz, LISN on mains input
# (run against the AC/DC adapter feeding the patch charger)
emc32 --prescan --range 150k-30M --detector QP --lISN 50uH \
      --limit EN55011-ClassB --output conducted_scan.csv

# Radiated emissions pre-scan, 30 MHz–1 GHz, 3 m semi-anechoic
emc32 --prescan --range 30M-1G --antenna biconilog --distance 3m \
      --limit EN55011-ClassB --output radiated_scan.csv
```

```python
# DFMEA scoring helper — RPN with severity floor for patient-connected hazards
# Severity 9/10 items cannot be "accepted" on RPN alone; they require
# a design change or an explicit ISO 14971 risk-benefit justification.
def rpn(sev, occ, det):
    assert 1 <= sev <= 10 and 1 <= occ <= 10 and 1 <= det <= 10
    score = sev * occ * det
    if sev >= 9:
        return score, "REQUIRES DESIGN CONTROL — not RPN-acceptable"
    return score, "RPN-acceptable if below threshold"

# Example: single-fault bridge across 2× MOPP isolation barrier
print(rpn(sev=10, occ=2, det=4))   # (80, 'REQUIRES DESIGN CONTROL...')
```

```yaml
# Verification trace — each DFMEA detection control must point at a test
# with a numeric pass criterion, not a review.
dfmea_item:
  id: EMC-014
  failure_mode: "Radiated emissions from 2.4 GHz BLE exceed Class B limit"
  effect: "Interference with adjacent medical telemetry; not patient-harmful but regulatory fail"
  severity: 6
  mechanism: "Insufficient ground plane under antenna; harmonic coupling to flex cable"
  detection_control:
    method: "CISPR 11 radiated pre-scan, 3 m, biconilog"
    pass_criterion: "All emissions < Class B limit - 3 dB margin"
    verification_ref: "VTP-EMC-003"
```

```c
/* Firmware-side EMC mitigation: spread-spectrum clocking on the
 * switching regulator that feeds the analog front-end.
 * Reduces peak conducted emissions at the switching fundamental. */
#define REG_CLK_SPREAD_EN   (1U << 3)
#define REG_CLK_SPREAD_PCT  0x03   /* ±3% spread, per datasheet table */

void regulator_enable_ssc(void) {
    uint8_t v = i2c_read8(PMIC_ADDR, PMIC_REG_CLK);
    v |= REG_CLK_SPREAD_EN;
    v = (v & ~0x0C) | (REG_CLK_SPREAD_PCT << 2);
    i2c_write8(PMIC_ADDR, PMIC_REG_CLK, v);
}
```

## Common Pitfalls & Gotchas

**1. Scoring detection as "EMC test" when the test is at the end of the project.** If the only detection control for a radiated-emissions failure mode is the final compliance test, your detection score should be 8–10, not 3. The test exists, but it detects the failure too late to fix cheaply. Pre-compliance scans at each hardware revision are the real detection control.

**2. Treating IEC 60601-1-2 as a single test event.** The 4th edition requires immunity testing (ESD ±8 kV contact, radiated RF 3 V/m, etc.) *and* a documented rationale for the basic safety/essential performance the device must maintain during the disturbance. DFMEA items that say "device resets during ESD" need an essential-performance clause: is a reset acceptable, or is it a loss of essential performance? That distinction changes severity from 5 to 9.

**3. Forgetting that creepage/clearance is a *design* failure mode, not a manufacturing one.** A 0.5 mm creepage short across an isolation barrier is a severity-10 DFMEA line, but it's caused by a layout decision, not a bad solder joint. It belongs in the design FMEA with the PCB stackup and enclosure as the mechanism, and the detection control is a creepage audit against IEC 60601-1 Table 12 (or the applicable table for your pollution degree and material group), not incoming inspection.

## Try It Yourself

1. **Build a coupling-path DFMEA line.** Take one EMC finding from a recent pre-scan (or invent a plausible one for your device) and write the failure mode as a *coupling path*, not a source. Score severity, occurrence, and detection, and confirm your detection control points to a specific test with a numeric pass criterion.

2. **Audit your isolation barrier.** For every component that touches the patient-connected side, list its rated isolation voltage and the creepage/clearance on the PCB. Flag any part where a single component failure could bridge the 2× MOPP barrier — those are severity-10 items and must have a design control, not an RPN acceptance.

3. **Write the essential-performance clause.** For your device, define what "essential performance" means during an ESD or radiated-RF disturbance per 60601-1-2 §4.3. Then re-score any DFMEA line whose effect is "device resets" — does the reset violate essential performance? If yes, severity goes up.

## Next Up

Tomorrow: **Cybersecurity as a Failure Mode: FDA Premarket Guidance & Security Risk** — how to fold threat modeling into the same DFMEA/risk file, why "unauthorized access" is a failure mode with a severity score, and what the FDA's premarket cybersecurity guidance actually requires you to document.
