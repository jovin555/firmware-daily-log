---
title: "Day 18: Use-Related Failure Modes: IEC 62366 Usability Engineering & uFMEA"
date: 2026-10-28
tags: ["til", "medical-iot-dfmea", "iec62366", "usability"]
---

# Day 18: Use-Related Failure Modes: IEC 62366 Usability Engineering & uFMEA

## What I Explored Today

Today I dug into the intersection of usability engineering and DFMEA for our connected infusion pump controller. The insight that landed hardest: a device can pass every hardware and software FMEA with flying colors and still kill someone because a nurse misreads a status LED at 3 a.m. IEC 62366-1 treats *use error* as a legitimate failure mode with its own risk analysis path, and the uFMEA (use FMEA) is how you systematically capture those modes. I spent the day mapping our UI flows to use scenarios, building a use-error taxonomy, and wiring the results back into the master DFMEA so the risk numbers don't get double-counted or, worse, ignored.

## The Core Concept

Traditional DFMEA asks "what happens when this component fails?" uFMEA asks a different question: "what happens when a *correctly functioning* device meets a *reasonable* human?" That distinction matters because use-related failures are not random — they're predictable, systematic, and often the dominant risk contributor in medical IoT. A pump that delivers exactly 5 mL/hr as designed still causes harm if the nurse programs 50 mL/hr because the keypad debounce made a double-press look like a single press.

IEC 62366-1 (the current standard, superseding 62366:2007) requires a *usability engineering file* that traces use scenarios → hazard-related use scenarios → user interface evaluation → residual risk. The uFMEA is the bridge artifact: it takes the use scenarios from the summative evaluation and asks, for each task, what use errors are credible, what's the severity, and what's the detectability *by the user* (not by the firmware watchdog). Crucially, detectability in uFMEA is about whether the *operator* notices the error before harm — a very different axis than hardware detectability. That's why you can't just copy your DFMEA RPN columns over.

The other thing that clicked: use errors are classified by cause, not by symptom. IEC 62366 and the AAMI HE75 guidance converge on categories like *slip* (attention failure), *lapse* (memory failure), *mistake* (rule/knowledge-based error), and *violation* (deliberate shortcut). Tagging each uFMEA line with the cause category tells you which risk control will actually work — a slip needs a forcing function or confirmation, a mistake needs better information or a constraint, a violation needs redesign of the workflow incentive.

## Key Commands / Configuration / Code

I keep the uFMEA as a structured YAML file so it can be diffed in git and validated in CI. Here's the schema and a validator snippet:

```yaml
# ufmea.yaml — use-FMEA entries for infusion pump UI
# severity: 1-10 per IEC 62366 harm severity scale
# occurrence: 1-10, likelihood of the use error given the task
# detectability: 1-10, likelihood the USER catches it before harm (10 = never caught)
- id: UF-014
  use_scenario: "Program continuous infusion rate"
  task_step: "Enter rate via numeric keypad"
  use_error: "Double keypress registers as single digit (e.g., 50 -> 5)"
  cause_category: slip          # attention failure, not a device fault
  severity: 9                   # 10x underdose on a vasopressor
  occurrence: 4
  detectability: 7              # user unlikely to re-read the field
  rpn: 252
  risk_control: "Add leading-zero suppression + explicit confirmation dialog"
  control_type: protective      # see tomorrow's post on hierarchy
  residual_rpn: 84
```

```python
# validate_ufmea.py — CI gate for the uFMEA file
import yaml, sys

REQUIRED = {"id", "use_scenario", "task_step", "use_error",
            "cause_category", "severity", "occurrence",
            "detectability", "rpn", "risk_control"}

VALID_CAUSES = {"slip", "lapse", "mistake", "violation"}

def check(path):
    errors = []
    with open(path) as f:
        entries = yaml.safe_load(f)
    for e in entries:
        missing = REQUIRED - e.keys()
        if missing:
            errors.append(f"{e.get('id','?')}: missing {missing}")
        if e.get("cause_category") not in VALID_CAUSES:
            errors.append(f"{e['id']}: bad cause_category")
        # RPN must equal S*O*D — catch hand-edit drift
        if e["rpn"] != e["severity"] * e["occurrence"] * e["detectability"]:
            errors.append(f"{e['id']}: RPN mismatch")
        # Any severity >= 9 requires a risk control, no exceptions
        if e["severity"] >= 9 and not e.get("risk_control"):
            errors.append(f"{e['id']}: S>=9 with no risk control")
    return errors

if __name__ == "__main__":
    errs = check(sys.argv[1])
    for e in errs:
        print(e)
    sys.exit(1 if errs else 0)
```

Run it as a pre-commit hook so nobody merges a uFMEA with a hand-typed RPN that doesn't match S×O×D:

```bash
# .git/hooks/pre-commit
#!/bin/sh
python validate_ufmea.py ufmea.yaml || exit 1
```

The traceability link back to the DFMEA is a single field — `dfmea_ref` — pointing at the hardware/software line that the use error *exposes*. That way when the DFMEA team lowers a severity because "the firmware catches it," the uFMEA reviewer can push back: the firmware catching it is *device* detectability, not *user* detectability, and the uFMEA D-value stays high.

## Common Pitfalls & Gotchas

**1. Reusing DFMEA detectability for uFMEA.** This is the single most common error I see. In DFMEA, D measures whether your controls (inspection, test, watchdog) catch the failure. In uFMEA, D measures whether the *human operator* catches their own error before harm. A firmware that logs "rate entered: 5 mL/hr" has D=1 in DFMEA terms but does nothing for the nurse who never looks at the log. Keep the two D-columns separate or your RPNs will be dangerously optimistic.

**2. Forgetting that use errors compound.** A slip on the keypad plus a lapse in the confirmation step is one credible scenario, not two independent ones. If your uFMEA treats each task step in isolation, you'll undercount occurrence. Model the *scenario* end-to-end, and let occurrence reflect the joint probability of the error chain.

**3. Treating "training" as a risk control.** IEC 62366-1 explicitly de-prioritizes information-for-safety and training in the risk control hierarchy (which is tomorrow's topic). If your only control for a severity-9 use error is "add a line to the IFU," your reviewer will flag it. The uFMEA should force you to ask: can I make the error *impossible* (forcing function) or *obvious* (constraint) before I reach for the manual?

## Try It Yourself

1. **Build a 5-entry uFMEA for a device you know.** Pick any medical IoT UI you've worked on — a glucose meter, a patient monitor, a pump. Write five use-error entries in the YAML schema above, tagging each with a cause category. Then run the validator and fix whatever it flags.

2. **Cross-check one entry against your DFMEA.** Take the highest-severity uFMEA line and find the corresponding DFMEA line. Compare the two detectability values and write one sentence explaining why they differ (or why they legitimately match).

3. **Run a slip-injection test.** On a bench unit, deliberately double-press a numeric key at 200 ms intervals and observe whether the UI registers one or two digits. Log the result as an occurrence data point for your uFMEA — real measurement beats a guess.

## Next Up

Tomorrow: **Risk Control Hierarchy: Inherent Safety, Protective Measures & Information for Safety.** We'll take the uFMEA output and walk it through the ISO 14971 control hierarchy — why "inherently safe by design" beats "protective measure" beats "information for safety," and how to document the justification when you're forced down the hierarchy. Bring your severity-9 lines; we'll see which ones survive the hierarchy test.
