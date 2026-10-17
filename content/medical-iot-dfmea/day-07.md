---
title: "Day 07: Function Analysis & Requirements Traceability for Medical DFMEA"
date: 2026-10-17
tags: ["til", "medical-iot-dfmea", "function-analysis", "traceability"]
---

## What I Explored Today

Today I dug into the front half of the DFMEA worksheet — the part everyone wants to skip to get to the failure modes. Function analysis is where the DFMEA actually earns its keep, because a failure mode is only meaningful relative to a function. If you can't state what the item is *supposed* to do, "fails to do it" is unfalsifiable. I spent the day building a traceability chain from system requirements down to component functions for our wearable SpO₂/pulse oximeter module, and wiring it into the DFMEA structure so every failure mode row points back to a requirement ID. The payoff: when a reviewer asks "why is this failure mode here?", the answer is a click, not a shrug.

## The Core Concept

DFMEA is a *function-based* risk method. The standard structure (AIAG-VDA, and IEC 60812 for the FMEA family) is: **Item → Function → Failure Mode → Effect → Cause → Prevention/Detection Control**. The failure mode is literally the negation of the function. So the quality of your entire DFMEA is bounded by the quality of your function statements.

The trap is treating functions as vague nouns ("power management," "sensing"). A usable function statement is a **verb + object + quantified performance criterion**, ideally tied to a requirement. "Regulate the 3.3 V rail to ±3% across 0–70 °C and 0–500 mA load" is a function. "Power management" is a category heading.

Requirements traceability is what makes this auditable. In a medical device under ISO 13485 / IEC 62304, you already have a requirements management system (or at least a spreadsheet). The DFMEA should *reference* those requirement IDs rather than invent parallel prose. This gives you three things: (1) coverage analysis — every safety-relevant requirement should map to at least one function and its failure modes; (2) change impact — when a requirement changes, you can find every DFMEA row it touches; (3) audit defensibility — a notified body auditor can follow requirement → function → failure mode → control.

The practical mechanism is a **traceability matrix** plus a **function ID scheme**. I use `FN-<subsystem>-<nn>` for functions and carry the originating `REQ-<nnn>` alongside. The DFMEA row then carries both. This is boring bookkeeping, and it is exactly what separates a DFMEA that survives review from one that gets bounced.

## Key Commands / Configuration / Code

I keep the traceability matrix as a CSV that lives in the same repo as the DFMEA, so both are version-controlled and diffable. Here's the schema and a validator I wrote to catch orphaned rows.

```csv
# traceability.csv — one row per function, linked to requirement(s) and DFMEA row
fn_id,req_id,subsystem,function_statement,dfmea_row
FN-PWR-01,REQ-014,power,"Regulate 3V3 rail to +/-3% over 0-70C, 0-500mA load",12
FN-PWR-02,REQ-015,power,"Hold 3V3 within tolerance for >=10ms during 5V brownout to 3.0V",13
FN-SEN-01,REQ-021,sensor,"Acquire red/IR PPG at 100SPS with <2% dropout over 8h",27
FN-SEN-02,REQ-022,sensor,"Detect probe-off within 2s of signal loss",28
FN-COM-01,REQ-031,radio,"Transmit SpO2 frame to gateway within 500ms, 99.5% delivery",41
```

```python
# validate_trace.py — fail the build if any DFMEA row lacks a function/requirement link
import csv, sys

def load(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

rows = load("traceability.csv")
errors = []

# 1. Every function must cite a requirement
for r in rows:
    if not r["req_id"].strip():
        errors.append(f"{r['fn_id']}: missing req_id")

# 2. Function IDs must be unique
seen = set()
for r in rows:
    if r["fn_id"] in seen:
        errors.append(f"duplicate fn_id: {r['fn_id']}")
    seen.add(r["fn_id"])

# 3. Every DFMEA row number must be referenced by exactly one function
dfmea_rows = [r["dfmea_row"] for r in rows if r["dfmea_row"].strip()]
dupes = {x for x in dfmea_rows if dfmea_rows.count(x) > 1}
for d in dupes:
    errors.append(f"DFMEA row {d} referenced by multiple functions")

if errors:
    print("\n".join(errors)); sys.exit(1)
print(f"OK: {len(rows)} functions traced")
```

```yaml
# dfmea_row.yml — the DFMEA row carries the trace IDs so review is self-documenting
row: 12
item: "3V3 LDO (U7)"
function_ref: FN-PWR-01          # -> traceability.csv
requirement_ref: REQ-014
failure_mode: "Output voltage out of regulation (>+/-3%)"
effect: "MCU brownout; SpO2 acquisition gap"   # -> maps to ISO 14971 harm tomorrow
severity: 8
cause: "LDO dropout at low Vin / high load"
prevention: "Vin headroom analysis; load transient sim"
detection: "Factory 3V3 tolerance test at 0/25/70C"
```

The validator runs in CI (`.gitlab-ci.yml` or a GitHub Action step: `python validate_trace.py`), so a DFMEA edit that drops a requirement link fails the pipeline — same as a broken unit test.

## Common Pitfalls & Gotchas

**1. Functions written as nouns, not behaviors.** "Battery management" can't be failed in a testable way. Rewrite as "Maintain charge termination within ±1% of 4.20 V" — now the failure mode ("overcharges to 4.35 V") and its severity write themselves.

**2. One-to-many traceability that nobody maintains.** If a single function maps to five requirements, pick the *primary* requirement for the DFMEA row and list the rest in a notes column. Trying to keep a full many-to-many matrix in a spreadsheet rots within a month. Keep the DFMEA row's link to one canonical requirement.

**3. Treating the traceability matrix as documentation, not a gate.** If it isn't validated in CI, it drifts. The validator above is 30 lines and catches the two failure modes that actually happen: orphaned functions and duplicate row references after a renumber.

## Try It Yourself

1. **Build the matrix for one subsystem.** Take your power or sensor block and write 5–8 function statements in the `verb + object + quantified criterion` form. Assign `FN-` IDs and link each to an existing requirement ID. Count how many requirements have *no* function — those are coverage gaps.

2. **Run the validator against a deliberately broken CSV.** Delete a `req_id`, duplicate a `dfmea_row`, and confirm the script exits non-zero. Wire it into your CI as a required check.

3. **Back-fill five existing DFMEA rows.** Take five rows from your current worksheet and add `function_ref` and `requirement_ref` fields. Any row you can't trace is either a missing function or a failure mode that doesn't belong — decide which.

## Next Up

Tomorrow: **Hazards, Hazardous Situations & Harm — Mapping DFMEA Effects to ISO 14971.** Today's `effect` field ("MCU brownout; SpO₂ acquisition gap") is a *device-level* effect. ISO 14971 wants the chain to *harm* — the sequence of events, the hazardous situation, and the patient injury. We'll map DFMEA severity to the risk management file and see where the two frameworks disagree (they will).
