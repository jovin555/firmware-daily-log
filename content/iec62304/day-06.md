---
title: "Day 06: Software Development Plan (SDP): What It Must Contain"
date: 2026-06-18
tags: ["til", "iec62304", "sdp", "planning"]
---

## What I Explored Today

I dove into Clause 5.1.1 of IEC 62304, which mandates the Software Development Plan (SDP). This isn't just a project schedule or a Gantt chart—it's the binding contract between your engineering team and the regulatory framework. The SDP must define *how* you will execute every activity from software development planning through maintenance. I spent the day mapping out the required elements, cross-referencing them with real-world embedded projects (think RTOS-based infusion pumps and bootloader updates for implantable devices), and figuring out what actually matters when you're writing this document for a Class B or C device.

## The Core Concept

The SDP exists because IEC 62304 is a process standard, not a product standard. It doesn't care if your code is beautiful; it cares that you followed a repeatable, auditable process. The SDP is your process blueprint. Without it, a Notified Body auditor has no baseline to judge your compliance. The plan must cover the entire software lifecycle: development, risk management integration, verification, validation, and maintenance. Crucially, it must also define the *interfaces* between software development and other activities (hardware development, system engineering, clinical evaluation). If your SDP says "we use Git for version control" but your team actually uses SVN, that's a non-conformance. The plan must be followed, or it must be updated. It's a living document, not a shelf-ware artifact.

## Key Commands / Configuration / Code

The SDP is a document, not a script, but you can structure it using a template repository. Here's a minimal SDP outline in Markdown, which you can version-control alongside your code:

```markdown
# Software Development Plan (SDP) — Project Medtronic-Pump-v3

## 1. Purpose and Scope
- Applies to all software for the Medtronic-Pump-v3 (Class C)
- Excludes: third-party bootloader (separate SDP)

## 2. Lifecycle Model
- V-model with iterative sprints (2-week cycles)
- Reference: SDP_Figure_1_Lifecycle.pdf

## 3. Roles and Responsibilities
| Role | Name | Responsibilities |
|------|------|------------------|
| Software Manager | J. Doe | SDP maintenance, audit readiness |
| Lead Developer | A. Smith | Code reviews, unit tests |
| Tester | L. Chen | Integration tests, test report sign-off |

## 4. Risk Management Integration
- Per IEC 62304 Clause 7: risk control measures linked to software items
- Risk management file: `./risk_management/`

## 5. Verification and Validation
- Unit tests: Ceedling (C), Google Test (C++)
- Integration tests: HIL (Hardware-in-the-Loop) weekly
- Validation: Clinical simulation every release

## 6. Configuration Management
- Git repository: `git@gitlab.internal:medtronic/pump-firmware.git`
- Branching: `main` (release), `develop` (integration), `feature/*`
- Tagging: `v1.2.3` (semver)

## 7. Problem Resolution
- Bug tracker: Jira project `PUMP`
- Severity levels: Critical (stop-ship), Major (fix within 5 days), Minor (next release)

## 8. Documentation
- All documents in `./docs/` as PDF + Markdown source
- Approval via GitLab merge request with two reviewers
```

To automate SDP compliance checks, you can use a simple shell script that verifies the SDP exists and contains required sections:

```bash
#!/bin/bash
# sdp_audit.sh — verify SDP presence and required sections
# Usage: ./sdp_audit.sh <path-to-sdp.md>

SDP_FILE="$1"
REQUIRED_SECTIONS=("Purpose and Scope" "Lifecycle Model" "Roles and Responsibilities" 
                   "Risk Management Integration" "Verification and Validation"
                   "Configuration Management" "Problem Resolution" "Documentation")

if [ ! -f "$SDP_FILE" ]; then
    echo "FAIL: SDP file not found at $SDP_FILE"
    exit 1
fi

for section in "${REQUIRED_SECTIONS[@]}"; do
    if ! grep -q "^## $section" "$SDP_FILE"; then
        echo "FAIL: Missing section '$section'"
        exit 1
    fi
done

echo "PASS: All required sections present in SDP"
```

## Common Pitfalls & Gotchas

1. **Treating the SDP as a one-time document.** I've seen teams write the SDP at project kickoff, get it approved, and never touch it again. Then six months later, they've switched from static analysis to dynamic analysis, added a new compiler, or changed their branching strategy. The SDP must be updated whenever the process changes. A stale SDP is worse than no SDP—it proves you're not following your own plan.

2. **Omitting the interface to risk management.** Clause 5.1.1 explicitly requires the SDP to describe how software development interacts with risk management. Many engineers write a beautiful SDP but leave out the risk management integration section. Then during audit, they can't explain how a risk control (e.g., a watchdog timer) was implemented, tested, and verified. The SDP must trace from risk control to software item to test case.

3. **Using vague language like "team will follow best practices."** Auditors hate this. "Best practices" is undefined. Instead, say: "All code shall be reviewed by at least one peer using GitLab merge requests. Static analysis shall be performed with Cppcheck version 2.9 using the `--suppress=unmatchedSuppression` flag." Concrete, verifiable, auditable.

## Try It Yourself

1. **Audit your current project.** Find your existing SDP (or create one from scratch). Run the `sdp_audit.sh` script above. If it fails, add the missing sections. If you don't have a risk management integration section, write one paragraph describing how your team links risk controls to software items.

2. **Version-control your SDP.** If your SDP isn't in your Git repository, move it there. Create a `docs/` folder and commit the SDP as Markdown. Then set up a Git hook that runs `sdp_audit.sh` on every commit to `main`—this prevents merging without a valid SDP.

3. **Map your actual process to the SDP.** List your team's current branching strategy, test framework, and bug tracker. Compare it to what your SDP says. If they differ, update the SDP to match reality. Then schedule a monthly review to keep it current.

## Next Up

Tomorrow, we'll tackle the **Software Configuration Management Plan (SCMP)** — the document that tells auditors exactly how you track every version of every file, every tool, and every build environment. We'll cover baseline identification, change control boards, and why your `.gitignore` is a regulatory artifact.
