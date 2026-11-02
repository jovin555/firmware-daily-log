---
title: "Day 23: Risk Management File, Design History File & Traceability Matrix"
date: 2026-11-02
tags: ["til", "medical-iot-dfmea", "dhf", "traceability-matrix"]
---

# Day 23: Risk Management File, Design History File & Traceability Matrix

## What I Explored Today

Today I stopped treating the Risk Management File (RMF) and Design History File (DHF) as "paperwork that happens after the design" and started treating them as build artifacts. The turning point was realizing that a traceability matrix is just a join table — a relational structure linking requirements, hazards, risk controls, verification tests, and design outputs. Once I modeled it that way, I could generate it, lint it, and diff it in CI like any other artifact. I spent the day building a minimal but real traceability toolchain: a YAML source of truth, a Python script that validates referential integrity, and a rendered matrix that maps cleanly onto ISO 14971 and 21 CFR 820.30 expectations.

## The Core Concept

Three documents, one underlying graph:

- **Risk Management File (RMF)** — per ISO 14971, the living record of hazard identification, risk estimation, risk control, and residual risk evaluation. It is *not* a single document; it's a set of linked records.
- **Design History File (DHF)** — per 21 CFR 820.30(j), the compilation of records describing the design history of a finished device. It demonstrates the design was developed per the design control plan.
- **Traceability Matrix** — the connective tissue. It proves that every user need → design input → design output → verification → risk control is accounted for, and that every hazard has a control with evidence.

The *why*: auditors and reviewers don't read your code — they read the matrix. If a hazard has no linked control, or a control has no verification evidence, the matrix exposes it instantly. The practical move is to make the matrix **generated from structured data**, so gaps are caught by a script, not by a human at 11pm before an audit. The RMF and DHF then become *views* over the same data, not separate hand-maintained documents that drift apart.

The key insight: **referential integrity is the whole game**. A traceability matrix is only as trustworthy as its ability to fail loudly when a link dangles.

## Key Commands / Configuration / Code

A minimal YAML source of truth. Every node has an ID and typed links:

```yaml
# traceability.yaml — single source of truth for RMF + DHF views
requirements:
  - id: UN-001
    text: "Clinician can view SpO2 trend within 2s of measurement"
    inputs: [DI-001]
  - id: DI-001
    text: "Firmware shall render SpO2 trend at >= 1 Hz"
    outputs: [DO-001]
    hazards: [HZ-001]

hazards:
  - id: HZ-001
    text: "Stale SpO2 displayed after sensor disconnect"
    severity: 4          # 1-5 per ISO 14971 Annex C
    probability: 3
    controls: [RC-001]

risk_controls:
  - id: RC-001
    text: "Watchdog flags sensor timeout; UI shows STALE banner"
    verification: [VT-001]

verification:
  - id: VT-001
    text: "Fault-injection test: disconnect sensor, assert banner in <=500ms"
    result: pass
    evidence: "test-results/vt-001.xml"

design_outputs:
  - id: DO-001
    text: "ui_trend.c, ui_stale_banner.c"
```

A validator that enforces referential integrity and computes residual risk. This is the part that actually earns its keep:

```python
#!/usr/bin/env python3
# validate_trace.py — fail CI if any link dangles or risk is unmitigated
import sys, yaml

with open("traceability.yaml") as f:
    t = yaml.safe_load(f)

# Build ID -> node index across all sections
index = {}
for section, nodes in t.items():
    for n in nodes:
        if n["id"] in index:
            sys.exit(f"DUPLICATE ID: {n['id']}")
        index[n["id"]] = (section, n)

errors = []

def check_links(node, field, target_section):
    for ref in node.get(field, []):
        if ref not in index:
            errors.append(f"{node['id']}.{field} -> missing {ref}")
        elif index[ref][0] != target_section:
            errors.append(f"{node['id']}.{field} -> {ref} is {index[ref][0]}, expected {target_section}")

for hz in t["hazards"]:
    check_links(hz, "controls", "risk_controls")
    if not hz.get("controls"):
        errors.append(f"{hz['id']}: hazard with no risk control")
    # Residual risk must be re-evaluated after controls (ISO 14971 7.5)
    if hz["severity"] * hz["probability"] >= 15 and not hz.get("controls"):
        errors.append(f"{hz['id']}: unacceptable risk, unmitigated")

for rc in t["risk_controls"]:
    check_links(rc, "verification", "verification")
    if not rc.get("verification"):
        errors.append(f"{rc['id']}: control with no verification evidence")

for req in t["requirements"]:
    check_links(req, "inputs", "requirements")

if errors:
    print("\n".join(errors)); sys.exit(1)
print(f"OK: {len(index)} nodes, all links resolve")
```

Wire it into CI so a dangling link blocks the merge:

```bash
# .github/workflows/trace.yml (excerpt)
- run: pip install pyyaml
- run: python validate_trace.py
```

Render the matrix (the DHF/RMF view) with a tiny script — one row per requirement, columns for input/output/verification/hazard/control:

```python
# render_matrix.py — emits a Markdown traceability matrix for the DHF
import yaml
t = yaml.safe_load(open("traceability.yaml"))
print("| Req | Input | Output | Hazard | Control | Verification |")
print("|-----|-------|--------|--------|---------|--------------|")
for r in t["requirements"]:
    for di in r.get("inputs", []):
        node = next(n for n in t["requirements"] if n["id"] == di)
        for do in node.get("outputs", []):
            for hz in node.get("hazards", []):
                h = next(n for n in t["hazards"] if n["id"] == hz)
                for rc in h["controls"]:
                    c = next(n for n in t["risk_controls"] if n["id"] == rc)
                    for vt in c["verification"]:
                        print(f"| {r['id']} | {di} | {do} | {hz} | {rc} | {vt} |")
```

## Common Pitfalls & Gotchas

1. **Treating the RMF as a document, not a database.** If hazards live in a Word file and controls live in Jira, they will drift. Keep one structured source and generate both the RMF and DHF views from it. The moment you have two sources of truth, the matrix is already lying.

2. **Verification evidence that isn't linked to a specific control.** "We tested it" is not traceability. Each risk control needs a verification record with an evidence pointer (test report ID, log file, commit SHA). Auditors will ask "show me the test for RC-001" — if you can't resolve that ID to a file, you fail the trace.

3. **Forgetting residual risk re-evaluation.** ISO 14971 §7.5 requires you to evaluate residual risk *after* controls are applied. A common bug: the matrix shows the pre-control severity/probability and never updates it. Track both `initial_risk` and `residual_risk` fields, and have the validator assert residual ≤ acceptable threshold.

## Try It Yourself

1. **Build the validator.** Take the `traceability.yaml` above, add one deliberately dangling reference (e.g., point `RC-001.verification` at `VT-999`), and confirm `validate_trace.py` exits non-zero with a clear message. Then fix it and confirm a clean run.

2. **Add residual risk tracking.** Extend the schema with `initial_risk` and `residual_risk` objects per hazard, and add a validator rule that fails if any residual risk exceeds your acceptability threshold (e.g., score ≥ 15). This is the check that catches "we added a control but never proved it worked."

3. **Generate the DHF index.** Write a script that walks `traceability.yaml` and emits a DHF table of contents — one section per design output, listing the requirements it satisfies and the verification evidence backing it. This is the artifact a 21 CFR 820.30 reviewer actually reads.

## Next up

Tomorrow: **Post-Market Surveillance: Complaints, CAPA & Keeping the DFMEA Alive.** The matrix you built today is a snapshot — but a shipped device keeps generating data. We'll look at how complaint intake and CAPA records feed back into the DFMEA, how to version the risk file so changes are auditable, and why a DFMEA that never changes after launch is a red flag, not a sign of a stable design.
