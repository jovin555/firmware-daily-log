---
title: "Day 12: D8: Closure & Team Recognition"
date: 2026-07-21
tags: ["til", "fmea-rca", "d8", "closure"]
---

## What I Explored Today

Today I closed out the 8D process on a persistent UART baud-rate mismatch that had been causing intermittent communication failures across three product lines. D8—Closure and Team Recognition—is the step that formalizes the end of the corrective action cycle. It’s not a victory lap; it’s a documented, auditable handoff that ensures the fix survives personnel changes, production shifts, and next-generation designs. I spent the morning writing the final report, updating the FMEA, and—most importantly—sending a recognition email that named every engineer who contributed to the root cause analysis.

## The Core Concept

D8 exists because problem-solving is a team sport, and the artifacts of that effort must outlive the immediate crisis. Without formal closure, three things happen:

1. **Institutional amnesia** — The fix gets applied, but the *why* evaporates. Six months later, a new engineer refactors the baud-rate calibration routine and reintroduces the same bug.
2. **Team burnout** — Engineers who pulled late nights debugging a race condition get no acknowledgment. Next time, they’re less willing to go the extra mile.
3. **Audit failure** — ISO 9001, IATF 16949, and AS9100 all require evidence of corrective action closure. A missing D8 report can trigger a non-conformance.

The closure deliverable is a living document that includes:
- The final corrective action (permanent and interim)
- Updated FMEA with new detection and prevention controls
- Lessons learned (what worked, what didn’t)
- Team recognition (names, roles, contributions)
- Sign-off from management

The recognition piece is not optional fluff. In embedded systems, where root causes often span firmware, hardware, and test, the team is cross-functional. Acknowledging each discipline’s contribution builds trust for the next 8D.

## Key Commands / Configuration / Code

Here’s the template I use for the D8 closure report. It’s a Markdown file stored in the project’s `docs/rca/` directory, version-controlled alongside the firmware.

```markdown
# 8D Closure Report: D8 — Closure & Team Recognition

## 1. Final Corrective Action Summary
- **Permanent Corrective Action (PCA):**  
  Replaced software UART baud-rate calculation from `F_CPU / 16 / desired_baud` to `F_CPU / 16 / (desired_baud + 0.5)` to fix rounding error at 115200 baud with 16 MHz clock.
- **Interim Containment:**  
  Added runtime baud-rate validation in `uart_init()` — assert if actual vs. requested deviates > 2%.
- **Verification:**  
  Passed 10,000-cycle soak test across 12 units at 3 temperature points (-40°C, 25°C, 85°C).

## 2. Updated FMEA Entry
| Function | Failure Mode | Effect | Cause | Current Controls | RPN (old) | RPN (new) | Recommended Action |
|----------|--------------|--------|-------|------------------|-----------|-----------|-------------------|
| UART init | Baud rate error > 3% | Frame errors, data loss | Integer truncation in baud divisor | None | 144 | 12 | Add rounding + runtime check |

## 3. Lessons Learned
- **Root cause tool used:** 5-Whys + fishbone diagram (clock tree analysis)
- **What delayed us:** Assumed hardware PLL was stable; it was, but the integer division was wrong.
- **What accelerated us:** Logic analyzer capture of actual TX bit timing vs. expected.

## 4. Team Recognition
| Name | Role | Contribution |
|------|------|--------------|
| Alice Chen | Firmware Lead | Identified rounding error in baud divisor macro |
| Bob Torres | Hardware Engineer | Measured actual bit timing with scope; confirmed PLL jitter was in spec |
| Carol Nguyen | Test Engineer | Designed soak test and automated baud-rate validation script |
| Dave Kim | Systems Engineer | Facilitated 5-Whys session; documented fishbone |

## 5. Management Sign-off
- [ ] Engineering Manager: _________________ Date: ___________
- [ ] Quality Manager: _________________ Date: ___________
```

For the recognition email, I use a simple script that pulls contributor names from the report and sends a formatted message:

```bash
#!/bin/bash
# send_recognition.sh — sends team recognition email from D8 report
# Usage: ./send_recognition.sh docs/rca/d8_closure_uart.md

REPORT="$1"
if [ ! -f "$REPORT" ]; then
    echo "Error: Report not found: $REPORT"
    exit 1
fi

# Extract team members (lines after "| Name | Role | Contribution |" until next blank line)
TEAM=$(sed -n '/^| Name | Role | Contribution |/,/^$/p' "$REPORT" | grep -v '^|.*---' | grep '|' | tail -n +2)

echo "Sending recognition to:"
echo "$TEAM" | while IFS='|' read -r _ name role contrib; do
    name=$(echo "$name" | xargs)
    echo "  - $name ($role): $contrib"
    # In production, pipe to `mail` or `sendmail`
    # mail -s "8D Closure Recognition - UART Baud Fix" "$name@company.com" <<< "Thank you for your contribution..."
done
```

## Common Pitfalls & Gotchas

1. **Skipping the FMEA update** — I’ve seen teams close D8 but never update the FMEA. The next time someone runs a PFMEA, the old RPN of 144 still shows, and management asks why no action was taken. Always update the FMEA row with new controls and recalculated RPN.

2. **Generic recognition** — “Thanks to the team” means nothing. Name names. Specify contributions. In embedded systems, a hardware engineer who spent three days probing clock lines deserves explicit credit. Generic praise demotivates the very people you need for the next crisis.

3. **No management sign-off** — Without a signature (or digital approval), the closure is not auditable. If your QMS requires it, get the engineering manager and quality manager to sign the PDF or approve the ticket in your tracking system (Jira, Azure DevOps, etc.). I use a simple `git tag` on the closure report commit: `git tag -a d8-closure-uart-20260721 -m "D8 closure signed off by EM and QM"`.

## Try It Yourself

1. **Write a D8 closure report for a past bug** — Pick a bug you fixed in the last 3 months. Write the full report, including the FMEA update and team recognition. If you didn’t have a cross-functional team, list the people you *should* have involved.

2. **Run the recognition script** — Copy the `send_recognition.sh` script above. Create a dummy report file and run it. Modify it to actually send an email (use `mail` or `sendmail`). Send a test to yourself.

3. **Update an existing FMEA** — Find an FMEA in your project that has a closed 8D but no updated controls. Add the new detection method (e.g., runtime assertion, soak test) and recalculate the RPN. Commit the change with a message referencing the 8D report.

## Next Up

Tomorrow: **Field Failure Analysis: Returned Unit Triage for Firmware/Hardware** — We’ll walk through the physical inspection, log extraction, and reproducible test setup for a returned unit that fails intermittently in the field. Bring your JTAG debugger and a logic analyzer.
