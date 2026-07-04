---
title: "Day 22: Agile & IEC 62304: Making Iterative Dev Compliant"
date: 2026-07-04
tags: ["til", "iec62304", "agile", "compliance"]
---

## What I Explored Today

I spent the day reconciling two worlds that often feel at odds: the iterative, fast-moving nature of Agile development and the rigid, documentation-heavy requirements of IEC 62304. The common belief is that Agile and medical device software compliance are mutually exclusive. That’s false. Today I mapped out how to run Scrum sprints while maintaining a compliant Software Development Plan (SDP), Software Maintenance Plan (SMP), and the traceability matrix required by the standard. The key is not to fight the process but to embed compliance artifacts into the definition of done for every user story.

## The Core Concept

IEC 62304 doesn’t prescribe a development methodology. It prescribes outcomes: documented plans, risk-controlled changes, and traceability from requirements to code to tests. Agile, at its heart, is about responding to change and delivering working software incrementally. The conflict arises when teams treat “documentation” as a separate waterfall phase that happens after the sprint. That’s a recipe for audit failure.

The solution is to treat compliance artifacts as first-class sprint deliverables. Every user story that touches software—whether it’s a new feature, a bug fix, or a refactor—must have acceptance criteria that include:
- A reference to the updated Software Requirements Specification (SRS) section.
- A link to the associated risk analysis (ISO 14971).
- A unit test or integration test that is checked into version control.
- A peer review record (which can be a pull request comment).

For a **Software Unit** (IEC 62304 Clause 5), the definition of done includes a verified implementation. For a **Software Item** (Clause 6), it includes integration tests and updated architecture documentation. For a **Software System** (Clause 7), it includes system-level verification and a release note.

The trick is to automate as much of this as possible. If your CI/CD pipeline doesn’t enforce that every commit has a linked requirement ID and a passing test suite, you will drown in manual paperwork.

## Key Commands / Configuration / Code

Here’s a practical example using a Git-based workflow with a `pre-commit` hook that enforces traceability. This ensures every commit references a requirement ID from your requirements management tool (e.g., Jama, Polarion, or a simple CSV).

**File: `.git/hooks/pre-commit`**

```bash
#!/bin/bash
# Pre-commit hook to enforce IEC 62304 traceability
# Requires commit message to contain a requirement ID like REQ-1234

COMMIT_MSG_FILE=$1
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Regex pattern for requirement IDs (adjust to your format)
REQ_PATTERN="REQ-[0-9]+"

if ! echo "$COMMIT_MSG" | grep -qE "$REQ_PATTERN"; then
    echo "ERROR: Commit message must include a requirement ID (e.g., REQ-1234)"
    echo "Example: 'Fix overflow in timer module (REQ-5678)'"
    exit 1
fi

# Optional: Check that the linked requirement exists in a local file
REQ_FILE="requirements.csv"
if [ -f "$REQ_FILE" ]; then
    REQ_ID=$(echo "$COMMIT_MSG" | grep -oE "$REQ_PATTERN")
    if ! grep -q "$REQ_ID" "$REQ_FILE"; then
        echo "ERROR: Requirement $REQ_ID not found in $REQ_FILE"
        exit 1
    fi
fi

exit 0
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

**Example `requirements.csv` snippet:**
```
REQ-1001,HeartRateMonitor,Calculate average BPM over 10-second window
REQ-1002,HeartRateMonitor,Detect arrhythmia and log event
REQ-1003,AlarmSystem,Trigger visual alarm within 500ms of event
```

For the CI pipeline (GitHub Actions example), add a step that validates traceability in pull requests:

```yaml
# .github/workflows/traceability-check.yml
name: IEC 62304 Traceability Check
on: [pull_request]
jobs:
  check-traceability:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify commit messages have requirement IDs
        run: |
          git log --format=%B origin/main..HEAD | while read line; do
            if ! echo "$line" | grep -qE "REQ-[0-9]+"; then
              echo "FAIL: Commit message missing requirement ID: $line"
              exit 1
            fi
          done
      - name: Check test coverage threshold (example: 80%)
        run: |
          # Assuming you use pytest with coverage
          pytest --cov=src --cov-fail-under=80 tests/
```

## Common Pitfalls & Gotchas

1. **Treating the SDP as a static document.** In Agile, the plan changes every sprint. Your Software Development Plan must be a living document. Update it at the end of each sprint to reflect the current state of the project. If an auditor sees a SDP dated six months ago with no revisions, they will flag it. Use version control for the SDP itself (e.g., a Markdown file in the repo) and tag it with each sprint release.

2. **Ignoring the Software Maintenance Plan until after release.** IEC 62304 Clause 6.1 requires a maintenance plan before you release the first version. In an Agile context, this means defining how you handle bug fixes, patches, and field-reported issues during the development phase. If you’re still in active development, you are already in maintenance mode for released features. Have a documented process for triaging defects that includes risk classification (e.g., “Critical” requires immediate SOUP update and regression test).

3. **Using Agile user stories that are too vague for traceability.** A user story like “As a user, I want the device to be fast” is not traceable to a testable requirement. Break it down: “The device shall compute the average heart rate within 200ms for a 10-second window (REQ-1001).” Each story must map to a single, verifiable requirement. If a story maps to multiple requirements, split it.

## Try It Yourself

1. **Add a pre-commit hook to your current project** that enforces requirement IDs in commit messages. Use the script above. If you don’t have a requirements file, create a dummy one with three entries. Commit a message without an ID and watch it fail.

2. **Review your last sprint’s user stories.** For each story, write down the IEC 62304 clause it touches (e.g., Clause 5.2 for software unit verification). If a story has no clause mapping, refactor it to include one. This exercise alone will reveal gaps in your traceability.

3. **Set up a CI pipeline step** that runs a coverage threshold check (e.g., `--cov-fail-under=80`). Then, intentionally write a commit that lowers coverage below the threshold. Observe how the pipeline blocks the merge. This is your safety net for Clause 5.2.3 (verification of software units).

## Next Up

Tomorrow, we dive into **Audit Preparation: DHF, DMR & Device History Records**. I’ll show you how to organize your Design History File (DHF) so it tells a coherent story from requirements to release, how to structure the Device Master Record (DMR) for manufacturing, and what auditors actually look for in Device History Records (DHR). Bring your checklists.
